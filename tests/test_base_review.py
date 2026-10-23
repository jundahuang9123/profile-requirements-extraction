"""Synthetic procedural-review tests; no evaluation answers or live generation."""
import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_routed_stakeholder_workflow import setup,make_record,install_records
from test_fa_workflow import enable
from requirement_reuse_service.workflow import base_review as br
from requirement_reuse_service.workflow.base_needs import load_catalogue
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.models import RequirementRecord,RunRequest
from requirement_reuse_service.workflow.needs import refresh_need,need_integrity
from requirement_reuse_service.workflow.storage import digest
from requirement_reuse_service.llm.client import OutputValidationError,validate_json_payload


def prepared(setup,count=1):
    store,run,units,_=setup;run=enable(store,run)
    records=[make_record(store,run,units[i%len(units)],i) for i in range(count)]
    run=install_records(store,run,records);profile,fingerprint=load_profile('dcat-ap-1.1.0')
    cat=load_catalogue(profile['id'],fingerprint)
    def pin(r):
        r.update(base_profile_id=profile['id'],base_profile_sha256=fingerprint,
            base_needs_catalogue={k:v for k,v in cat.items() if k!='entries'})
        r['request'].update(base_profile_id=profile['id'],base_check=False)
    store.mutate(run['run_id'],None,'fixture_pin',pin)
    return store,store.get('run',run['run_id']),cat

class Reviewer:
    def __init__(self,verdict='new',invalid=None,checked=True):self.calls=[];self.verdict=verdict;self.invalid=invalid;self.checked=checked
    def describe(self):return {'provider':'scripted','model':'default-reviewer'}
    def generate_structured(self,*,user,output_model,**kwargs):
        p=json.loads(user);self.calls.append((output_model.__name__,p))
        if output_model==br.BaseReview:
            rows=[]
            for key,n in p['needs'].items():
                v={'item_id':key,'verdict':self.verdict,'entry_ids':n['offered_entry_ids'][:1] if self.verdict in {'restates_base','domain_use_of_base'} else [],'rationale':'Synthetic comparison.'}
                if self.verdict=='domain_use_of_base':v.update(addition_kind='condition',addition='A stated source condition.',evidence_ids=n['excerpt_ids'][:1])
                if self.invalid:self.invalid(v,n)
                rows.append(v)
            return output_model(verdicts=rows)
        return output_model(checks=[{'item_id':key,'verdict_supported':self.checked,'nothing_lost':self.checked,'rationale':'Independent synthetic check.'} for key in p['needs']])

class Raw(Reviewer):
    """Answers as a provider client does: the contract, or OutputValidationError with the parsed JSON."""
    def __init__(self,edit,verdict='new'):super().__init__(verdict);self.edit=edit
    def generate_structured(self,*,user,output_model,**kw):
        out=super().generate_structured(user=user,output_model=output_model,**kw).model_dump(mode='json')
        self.edit(len(self.calls)-1,output_model.__name__,self.calls[-1][1],out)
        return validate_json_payload(json.dumps(out),output_model)


def test_pin_and_effect_checkpoint_resume_without_changing_revision(setup,monkeypatch):
    store,run,cat=prepared(setup);before=deepcopy(run['requirements'][0]);client=Reviewer('restates_base')
    br.review_base(store,run,client);saved=store.get('run',run['run_id']);n=saved['requirements'][0]
    assert n['base_relation']['status']=='checked' and n['base_relation']['effect']=='flag_added'
    assert n['base_relation']['human_accepted'] is False
    assert n['revision_id']==before['revision_id'] and n['content_hash']==before['content_hash']
    assert n['need_integrity_hash']!=before['need_integrity_hash']
    assert 'covered_by_base' in n['processing_flags']
    br.review_base(store,saved,client);assert len(client.calls)==2
    monkeypatch.setattr(br,'REVIEW_SYSTEM',br.REVIEW_SYSTEM+' changed')
    with pytest.raises(ValueError,match='checkpoint mismatch'):br.review_base(store,store.get('run',run['run_id']),client)


@pytest.mark.parametrize('invalid',[
    lambda v,n:v.update(entry_ids=['B999']),
    lambda v,n:v.update(entry_ids=[]),
])
def test_invalid_restating_verdict_gets_one_correction_then_pending(setup,invalid):
    store,run,_=prepared(setup);client=Reviewer('restates_base',invalid)
    br.review_base(store,run,client);saved=store.get('run',run['run_id'])
    assert len(client.calls)==2 and saved['requirements'][0]['base_relation']['status']=='not_reviewed'
    assert 'base_review_pending'in saved['requirements'][0]['processing_flags']


def test_domain_addition_requires_source_and_other_batches_continue(setup):
    store,run,_=prepared(setup,5)
    client=Reviewer('domain_use_of_base',lambda v,n:v.update(evidence_ids=[]) if len(n['offered_entry_ids']) else None)
    br.review_base(store,run,client)
    # The failed batch of four, then each of its needs alone; then the fifth need.
    assert [len(p['needs']) for _,p in client.calls]==[4,4]+[1]*10
    assert all(n['base_relation']['status']=='not_reviewed' for n in store.get('run',run['run_id'])['requirements'])


def test_condition_and_catalogue_pin(setup):
    store,run,_=prepared(setup)
    run['requirements'][0]['need_condition']='Only if an authorised recipient has signed a special agreement.'
    br.review_base(store,run,Reviewer('restates_base'))
    assert store.get('run',run['run_id'])['requirements'][0]['base_relation']['status']=='not_reviewed'
    run['base_needs_catalogue']['catalogue_hash']='changed'
    with pytest.raises(ValueError,match='catalogue changed'):br.review_base(store,run,Reviewer())


def test_older_catalogue_cannot_offer_or_accept_other_version_creator(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0]);n.need_statement='Users can find the creator of a resource.'
    p,a=br.make_payload(store,run,[n],cat,'before_discussion')
    assert all(e['property']!='dct:creator' for e in p['base']['entries'].values())
    other=next(e for e in load_catalogue('dcat-ap-2.1.1')['entries'] if e.get('property')=='dct:creator')
    bad=br.BaseReview(verdicts=[{'item_id':n.revision_id,'verdict':'restates_base','entry_ids':[other['id']],'rationale':'Wrong version.'}])
    assert br.verdict_errors(bad,[n],p)


@pytest.mark.parametrize('state',['covered','domain_use_of_base','domain',None])
@pytest.mark.parametrize('verdict',['restates_base','domain_use_of_base','new','uncertain'])
def test_effect_table_preserves_inventory(setup,state,verdict):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0]);n.need_class='domain' if state=='covered' else state
    if state=='covered':n.processing_flags=['covered_by_base']
    p,a=br.make_payload(store,run,[n],cat,'before_discussion');rid=n.revision_id;h=n.content_hash
    v=br.BaseVerdict(item_id=rid,verdict=verdict,entry_ids=[],rationale='Synthetic judgement.')
    check=br.BaseVerdictCheck(item_id=rid,verdict_supported=True,nothing_lost=True,rationale='Checked.')
    br.apply_verdict(n,v,check,'before_discussion',cat,'key',{},p);refresh_need(n)
    assert n.revision_id==rid and n.content_hash==h
    # The label follows a checked verdict in both directions; uncertainty changes nothing.
    assert ('covered_by_base'in n.processing_flags)==(verdict=='restates_base' or (state=='covered' and verdict=='uncertain'))
    expected = ('confirmed' if state=='covered' else 'flag_added') if verdict=='restates_base' else 'flag_removed' if state=='covered' and verdict in {'new','domain_use_of_base'} else 'agree' if (state=='domain_use_of_base' and verdict=='domain_use_of_base') or (state in {'domain',None} and verdict=='new') else 'note'
    assert n.base_relation['classifier_state']['covered_by_base']==(state=='covered')
    assert n.base_relation['effect']==expected


def test_failed_check_keeps_labels_and_surfaces_review(setup):
    store,run,_=prepared(setup);br.review_base(store,run,Reviewer('restates_base',checked=False))
    n=store.get('run',run['run_id'])['requirements'][0]
    assert n['base_relation']['status']=='check_failed' and 'covered_by_base'not in n['processing_flags']
    assert 'base_relation_review'in n['processing_flags']


def test_size_splits_and_single_need_pending(setup,monkeypatch):
    store,run,_=prepared(setup,5);monkeypatch.setattr(br,'MAX_PAYLOAD',1);client=Reviewer()
    br.review_base(store,run,client)
    assert client.calls==[]
    assert all(n['base_relation']['reason']=='payload_budget' for n in store.get('run',run['run_id'])['requirements'])


def test_request_opt_in_requires_fa_and_base_and_policy_is_per_run():
    from requirement_reuse_service.workflow.fa_discussion import discussion_policy
    with pytest.raises(ValueError,match='requires the F/A'):
        RunRequest(snapshot_id='s',base_review='expert_v1')
    r=RunRequest(snapshot_id='s',strategy='multi_agent',stakeholder_workflow='fa_mediated',base_profile_id='dcat-ap-1.1.0',base_review='expert_v1')
    assert discussion_policy({'request':r.model_dump()})=='rq1-fa-dialogue-v12'
    assert br.POLICY=='rq1-base-expert-v5'
    assert discussion_policy({'request':{}})=='rq1-fa-dialogue-v1'


def test_v2_packet_aliases_prompts_and_after_pass(setup):
    from requirement_reuse_service.workflow import fa_discussion as fd
    from test_fa_workflow import Dialogue
    store,run,cat=prepared(setup)
    def opt(r):r['request']['base_review']='expert_v1'
    store.mutate(run['run_id'],None,'fixture_expert',opt);run=store.get('run',run['run_id'])
    br.review_base(store,run,Reviewer('restates_base'));run=store.get('run',run['run_id'])
    packet=fd.freeze_packet(store,run,run['requirements'])
    assert packet['needs'][0]['base_relation']['verdict']=='restates_base'
    assert packet['base_entries'] and packet['base_catalogue_hash']==cat['catalogue_hash']
    class Both(Dialogue):
        def __init__(self):super().__init__();self.systems=[];self.wires=[]
        def generate_structured(self,*,user,output_model,system='',**kw):
            self.systems.append(system);self.wires.append(json.loads(user))
            if output_model in (br.BaseReview,br.BaseReviewChecks):return Reviewer('new').generate_structured(user=user,output_model=output_model,**kw)
            return super().generate_structured(user=user,output_model=output_model,**kw)
    client=Both();fd.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id']);assert saved['status']=='awaiting_human'
    assert any(fd.BASE_ROLE_GUIDANCE in s for s in client.systems)
    assert any(fd.BASE_MEDIATOR_GUIDANCE in s for s in client.systems)
    assert any(fd.BASE_CHECK_GUIDANCE in s for s in client.systems)
    assert any(any(k.startswith('B') for k in p.get('packet',{}).get('base_entries',{})) for p in client.wires)
    # A newly written revision is rechecked, and coverage changes only its working label.
    def recheck(r):r['requirements'][0]['processing_flags']=['base_recheck_required'];r['requirements'][0]['base_relation']=None
    store.mutate(run['run_id'],None,'fixture_revision',recheck)
    br.review_base(store,store.get('run',run['run_id']),Reviewer('restates_base'),phase='after_discussion')
    n=store.get('run',run['run_id'])['requirements'][0]
    assert 'base_recheck_required'not in n['processing_flags'] and 'covered_by_base'in n['processing_flags']
    assert n['base_relation']['phase']=='after_discussion'


def test_v1_packet_is_exactly_unchanged_and_has_no_base_block(setup):
    from requirement_reuse_service.workflow import fa_discussion as fd
    store,run,_=prepared(setup);records=run['requirements']
    old_packet=fd.freeze_packet(store,run,records);hash_before=digest(old_packet)
    records[0]['base_relation']={'policy':br.POLICY,'verdict':'new'}
    assert fd.freeze_packet(store,run,records)==old_packet
    assert digest(fd.freeze_packet(store,run,records))==hash_before
    assert 'base_entries'not in old_packet


def test_v2_ledger_keeps_covered_in_inventory_and_excludes_working(setup):
    from requirement_reuse_service.workflow.fa_requirements import coverage_ledger
    store,run,_=prepared(setup)
    store.mutate(run['run_id'],None,'expert',lambda r:r['request'].update(base_review='expert_v1'))
    br.review_base(store,store.get('run',run['run_id']),Reviewer('restates_base'))
    saved=store.get('run',run['run_id']);ledger=coverage_ledger(saved);rid=run['requirements'][0]['revision_id']
    assert rid in [r['revision_id'] for r in ledger['inventory']]
    assert rid not in ledger['working_revision_ids'] and rid in ledger['covered_by_base_revision_ids']
    assert ledger['covered_by_base_by_source']['base_review']==[rid]
    assert ledger['base_relation_counts']['before_discussion']['effect']=={'flag_added':1}
    saved['request']['base_review']='none';old=coverage_ledger(saved)
    assert 'base_relation_counts'not in old and old['contract_hash']!=ledger['contract_hash']


def derivable(setup):
    store,run,cat=prepared(setup)
    def ready(r):
        r.update(status='failed')
        for s in ('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation'):r['stages'][s]='completed'
        r['machine_snapshot'].update(set_aside_observations=[],conflicts=[],consolidation_events=[])
        r['deliberations']=[{'case_id':'historical','status':'mediated','discussion_trace':{}}]
        r['stakeholder_audit'].update({'fa_discussion_plan':{'old':True},'fa_task_groups:0':{'old':True},'fa_task_labels:0':{'old':True}})
        r['metrics'].update(mediated_changes=2,experience_claims=3,noted_concerns=4,salvaged_cases=2,salvaged_nothing_kept=1,
            lost_after_salvage_nothing_kept=1)
    store.mutate(run['run_id'],None,'ready',ready,parts=True)
    return store,store.get('run',run['run_id'])


def test_derive_restores_snapshot_and_stepwise_pauses_before_discussion(setup):
    from requirement_reuse_service.workflow import engine
    from requirement_reuse_service.workflow.models import DeriveRequest
    store,source=derivable(setup);before=digest(source)
    req=DeriveRequest(start_from='base_review',expected_version=source['version'],rationale='Independent base trial.',execution_mode='stepwise',
        step_models={'base_review':'reviewer-a','base_review_check':'reviewer-b'})
    child=engine.derive_run(store,source['run_id'],req)
    assert digest(store.get('run',source['run_id']))==before
    for key in ('requirements','active_revision_ids','conflicts','set_aside_observations','consolidation_events'):
        assert child[key]==source['machine_snapshot'][key]
    assert child['deliberations']==[] and 'fa_discussion_plan'not in child['stakeholder_audit']
    # Grouping and task labels of the parent's discussion are not inherited.
    assert not [k for k in child['stakeholder_audit'] if k.startswith(('fa_task_groups:','fa_task_labels:'))]
    # Discussion counters, including v6 experience counts, are not inherited.
    assert not {'mediated_changes','experience_claims','noted_concerns','salvaged_cases','salvaged_nothing_kept',
        'lost_after_salvage_nothing_kept'}&set(child['metrics'])
    assert child['derived_from']['restored_from']=='machine_snapshot'
    assert child['derived_from']['inherited_discussions_hash']==digest(source['deliberations'])
    engine.execute_run(store,child['run_id'],Reviewer())
    saved=store.get('run',child['run_id'])
    assert saved['status']=='paused',saved['diagnostics']
    assert saved['stages']['base_review']=='completed' and saved['stages']['deliberation']=='pending'
    assert saved['deliberations']==[]


@pytest.mark.parametrize('change',[
    {'status':'deliberating'}, {'decisions':[{'test':'decision'}]}, {'baselines':[{'id':'b'}]},
    {'request':{'stakeholder_workflow':'independent'}},
])
def test_base_derivation_rejects_unsafe_source(setup,change):
    from requirement_reuse_service.workflow.models import DeriveRequest
    store,source=derivable(setup);source.update(change)
    with pytest.raises(ValueError):br.derive_base_review_run(store,source,
        DeriveRequest(start_from='base_review',expected_version=source['version'],rationale='Synthetic negative test.'),'fixture')


@pytest.mark.parametrize('extra',[{'base_profile_id':'dcat-ap-2.1.1'},{'scoping':'use_cases'},
    {'step_models':{'extraction':'other'}},{'step_model_options':{'writer':{'reasoning_effort':'low'}}}])
def test_base_derivation_refuses_upstream_changes(setup,extra):
    from requirement_reuse_service.workflow.models import DeriveRequest
    store,source=derivable(setup)
    with pytest.raises(ValueError,match='cannot change'):
        br.derive_base_review_run(store,source,DeriveRequest(start_from='base_review',
            expected_version=source['version'],rationale='Synthetic settings test.',**extra),'fixture')


def test_batch_splits_successfully_without_repeating_work(setup,monkeypatch):
    store,run,cat=prepared(setup,4)
    records=[RequirementRecord.model_validate(r) for r in run['requirements']]
    payload,aliases=br.make_payload(store,run,records,cat,'before_discussion')
    size=len(br.canonical(br.translate_ids(payload,{v:k for k,v in aliases.items()})))
    # The full review splits, but each smaller review/check payload fits.
    monkeypatch.setattr(br,'MAX_PAYLOAD',size-1)
    client=Reviewer();br.review_base(store,run,client)
    assert len(client.calls)>2
    assert all(r['base_relation']['status']=='checked' for r in store.get('run',run['run_id'])['requirements'])
    seen=[n for kind,p in client.calls if kind=='BaseReview' for n in p['needs']]
    assert len(seen)==4
    for _,p in client.calls:assert len(br.canonical(p))<=br.MAX_PAYLOAD
    br.review_base(store,store.get('run',run['run_id']),client)
    assert len([n for kind,p in client.calls if kind=='BaseReview' for n in p['needs']])==4


def test_checked_new_verdict_removes_the_classifier_label_and_saves_question(setup):
    from requirement_reuse_service.workflow.fa_requirements import coverage_ledger
    store,run,_=prepared(setup)
    def covered(r):
        r['requirements'][0].update(processing_flags=['covered_by_base']);r['request']['base_review']='expert_v1'
    store.mutate(run['run_id'],None,'covered',covered)
    br.review_base(store,store.get('run',run['run_id']),Reviewer('new'))
    saved=store.get('run',run['run_id']);n=saved['requirements'][0]
    assert 'covered_by_base'not in n['processing_flags'] and n['base_relation']['effect']=='flag_removed'
    assert n['base_relation']['classifier_state']['covered_by_base'] is True and n['base_relation']['human_accepted'] is False
    question=saved['stage_results']['base_review']['review_questions'][0]
    assert question['revision_id']==n['revision_id'] and question['effect']=='flag_removed'
    assert 'classifier'in question['question'] and 'new'in question['question'] and 'removed'in question['question']
    ledger=coverage_ledger(saved)
    assert ledger['base_label_removed_revision_ids']==[n['revision_id']] and n['revision_id'] in ledger['working_revision_ids']
    # Resuming re-applies the same saved judgement against the classifier's original label.
    br.review_base(store,saved,Reviewer('new'))
    assert store.get('run',run['run_id'])['requirements'][0]['base_relation']['effect']=='flag_removed'


def test_stronger_obligation_cannot_be_restated(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    n.normalized_intent.obligation_hint='mandatory'
    payload,aliases=br.make_payload(store,run,[n],cat,'before_discussion')
    entry=payload['needs'][n.revision_id]['offered_entry_ids'][0]
    payload['base']['entries'][entry]['base_obligation']='optional'
    verdict=br.BaseReview(verdicts=[dict(item_id=n.revision_id,verdict='restates_base',entry_ids=[entry],rationale='Wrong obligation.')])
    assert any('stronger obligation'in e for e in br.verdict_errors(verdict,[n],payload))


def test_reviewer_slots_do_not_inherit_discussion_model(monkeypatch):
    from requirement_reuse_service.llm import step_models
    from requirement_reuse_service.llm.config import LLMConfig
    monkeypatch.setattr(step_models,'generation_models',lambda config:['default-model','discussion-model'])
    choices=step_models.resolve_models(LLMConfig(provider='openai-compatible',model='default-model'),{'discussion':'discussion-model'})
    assert choices['base_review']==choices['base_review_check']=='default-model'
    assert choices['mediation']=='discussion-model'


def test_v2_created_revision_requires_a_procedural_recheck(setup,monkeypatch):
    from requirement_reuse_service.workflow import fa_discussion as fd,stakeholder_workflow as old
    store,run,cat=prepared(setup)
    run['request']['base_review']='expert_v1'
    record=run['requirements'][0];case=fd.build_cases(store,run,[],__import__('test_fa_workflow').Dialogue())[0]
    revised=deepcopy(record);revised['revision_id']='synthetic-new-revision';revised['base_relation']={'status':'checked'}
    revised['processing_flags']=['covered_by_base']
    monkeypatch.setattr(old,'apply_plan',lambda *a,**kw:([{'applied':True}],[deepcopy(revised)],{record['revision_id']:revised['revision_id']}))
    link=deepcopy(record['evidence_links'][0]);link['quote_start']=None
    action={'action_id':'rev','action':'revise','parent_revision_ids':[record['revision_id']],
        'statement':'Users can identify resource access conditions.','evidence_links':[link],'rationale':'Cited wording.'}
    plan=fd.Plan(actions=[action],summary='Synthetic revision.')
    checks=fd.Checks(checks=[dict(action_id='rev',supported=True,fa_relevant=True,disposition_justified=True,
        preserves_distinctions=True,priority_supported=False,condition_supported=True,obligation_preserved=True,rationale='Checked.')])
    outcomes,added,_,_=fd.apply(store,run,case,plan,checks,None,set(run['evidence_ids']))
    assert outcomes[0]['applied'] and 'base_recheck_required'in added[0]['processing_flags']
    assert 'covered_by_base'not in added[0]['processing_flags'] and added[0]['base_relation'] is None
    assert outcomes[0]['citation_repairs']


def test_new_module_has_no_evaluation_reference_paths():
    from pathlib import Path
    text=Path(br.__file__).read_text()
    assert 'benchmark-data'not in text


def test_legacy_discussion_continuation_keeps_its_frozen_model_map(setup,monkeypatch):
    from requirement_reuse_service.workflow import engine,fa_discussion as fd
    from requirement_reuse_service.workflow.models import DeriveRequest
    from test_mediation_timeout_fallback import prepare,RoutedDialogue
    store,run=prepare(setup);fd.deliberate(store,run['run_id'],RoutedDialogue())
    def inactive(r):
        r['status']='failed'
        for stage in ('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation'):r['stages'][stage]='completed'
    store.mutate(run['run_id'],None,'interrupted_fixture',inactive)
    source=store.get('run',run['run_id']);frozen=deepcopy(source['step_models'])
    def freeze(req):
        req.step_models={**req.step_models,'base_review':'default','base_review_check':'default'}
        return req
    monkeypatch.setattr(engine,'freeze_step_models',freeze)
    child=fd.derive_discussion_run(store,source,DeriveRequest(start_from='deliberation',
        expected_version=source['version'],rationale='Legacy continuation.'),'fixture')
    assert child['step_models']==child['request']['step_models']==frozen


def test_aliases_never_rewrite_quoted_text(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    payload,aliases=br.make_payload(store,run,[n],cat,'before_discussion')
    payload['excerpts'][next(iter(payload['excerpts']))]['quote']='N1 B1 E1 '+n.revision_id
    wire=br.translate_ids(payload,{v:k for k,v in aliases.items()})
    assert next(iter(wire['excerpts'].values()))['quote']=='N1 B1 E1 '+n.revision_id


def test_v2_ledger_handles_classifier_covered_before_any_review(setup):
    from requirement_reuse_service.workflow.fa_requirements import coverage_ledger
    store,run,_=prepared(setup)
    run['request']['base_review']='expert_v1';run['requirements'][0]['processing_flags']=['covered_by_base']
    ledger=coverage_ledger(run)
    assert ledger['covered_by_base_by_source']['classifier']==run['active_revision_ids']
    assert ledger['covered_by_base_by_source']['base_review']==[]


def test_large_check_splits_without_repeating_accepted_review(setup,monkeypatch):
    store,run,cat=prepared(setup,4)
    records=[RequirementRecord.model_validate(r) for r in run['requirements']]
    payload,aliases=br.make_payload(store,run,records,cat,'before_discussion')
    size=len(br.canonical(br.translate_ids(payload,{v:k for k,v in aliases.items()})))
    monkeypatch.setattr(br,'MAX_PAYLOAD',size+8000)
    client=Reviewer('new',lambda v,n:v.update(rationale='\x00'*600))
    br.review_base(store,run,client)
    assert len([p for name,p in client.calls if name=='BaseReview'])==1
    assert len([p for name,p in client.calls if name=='BaseReviewChecks'])>1
    assert all(len(br.canonical(p))<=br.MAX_PAYLOAD for _,p in client.calls)
    before=len(client.calls);br.review_base(store,store.get('run',run['run_id']),client)
    assert len(client.calls)==before


def test_any_pinned_entry_is_citable_beyond_ranked_candidates(setup):
    # Word-overlap ranking misses paraphrases; the index keeps every pinned entry citable.
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    n.need_statement=n.normalized_statement='Users can know the year of public release of the resource.'
    n.need_condition='';n.matched_base_need_ids=[]
    issued=next(e['id'] for e in cat['entries'] if (e['class'],e.get('property'))==('dcat:Dataset','dct:issued'))
    payload,aliases=br.make_payload(store,run,[n],cat,'before_discussion')
    assert issued not in payload['needs'][n.revision_id]['offered_entry_ids']
    assert set(payload['base']['index'])=={e['id'] for e in cat['entries']}
    wire=br.translate_ids(payload,{v:k for k,v in aliases.items()})
    assert all(k.startswith('B') for k in wire['base']['index'])
    verdict=br.BaseReview(verdicts=[dict(item_id=n.revision_id,verdict='restates_base',entry_ids=[issued],rationale='Release year is the issue date.')])
    assert br.verdict_errors(verdict,[n],payload,cat)==[]
    check=br.BaseVerdictCheck(item_id=n.revision_id,verdict_supported=True,nothing_lost=True,rationale='Checked.')
    br.apply_verdict(n,verdict.verdicts[0],check,'before_discussion',cat,'key',{},payload)
    assert n.base_relation['entries'][0]['property']=='dct:issued' and 'covered_by_base' in n.processing_flags
    other=next(e['id'] for e in load_catalogue('dcat-ap-2.1.1')['entries'] if e.get('property')=='dct:creator')
    bad=br.BaseReview(verdicts=[dict(item_id=n.revision_id,verdict='restates_base',entry_ids=[other],rationale='Wrong version.')])
    assert br.verdict_errors(bad,[n],payload,cat)


def test_payload_carries_only_the_classifier_search_status(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    ids=[e['id'] for e in cat['entries']]
    n.base_gap={'status':'no_base_match','checked_entry_ids':ids,'search_chunks':[{'chunk':1,'entry_ids':ids}]}
    payload,aliases=br.make_payload(store,run,[n],cat,'before_discussion')
    state=payload['needs'][n.revision_id]['classifier']
    assert state['base_gap_status']=='no_base_match' and 'base_gap' not in state
    assert 'checked_entry_ids' not in br.canonical(br.translate_ids(payload,{v:k for k,v in aliases.items()}))


def test_v1_citation_repair_no_longer_stops_the_run(setup,monkeypatch):
    from requirement_reuse_service.workflow import fa_discussion as fd,stakeholder_workflow as old
    from test_fa_workflow import Dialogue
    store,run,_=prepared(setup);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    record=run['requirements'][0];case=fd.build_cases(store,run,[],Dialogue())[0]
    revised=deepcopy(record);revised['revision_id']='synthetic-new-revision'
    monkeypatch.setattr(old,'apply_plan',lambda *a,**kw:([{'applied':True}],[deepcopy(revised)],{record['revision_id']:revised['revision_id']}))
    link=deepcopy(record['evidence_links'][0]);link['quote_start']=None
    plan=fd.Plan(actions=[{'action_id':'rev','action':'revise','parent_revision_ids':[record['revision_id']],
        'statement':'Users can identify resource access conditions.','evidence_links':[link],'rationale':'Cited wording.'}],summary='Synthetic revision.')
    checks=fd.Checks(checks=[dict(action_id='rev',supported=True,fa_relevant=True,disposition_justified=True,
        preserves_distinctions=True,priority_supported=False,condition_supported=True,obligation_preserved=True,rationale='Checked.')])
    outcomes,added,_,_=fd.apply(store,run,case,plan,checks,None,set(run['evidence_ids']))
    assert outcomes[0]['applied'] and outcomes[0]['citation_repairs'][0]['from'] is None
    assert 'base_recheck_required' not in added[0]['processing_flags']


def test_a_supported_new_verdict_is_an_agreement_not_a_failed_check(setup):
    # rq1-base-expert-v1 asked whether the entries express the need; for a correct "new"
    # verdict the honest answer is no, and 31 of 35 JRC trial checks "failed" that way.
    store,run,_=prepared(setup);br.review_base(store,run,Reviewer('new'))
    n=store.get('run',run['run_id'])['requirements'][0]
    assert n['base_relation']['status']=='checked' and n['base_relation']['effect']=='agree'
    assert n['base_relation']['policy']==br.POLICY and 'base_relation_review' not in n['processing_flags']
    assert n['base_relation']['check']['verdict_supported'] is True
    assert 'verdict_supported' in br.CHECK_SYSTEM and 'entries_express_need' not in br.CHECK_SYSTEM
    with pytest.raises(Exception):
        br.BaseVerdictCheck.model_validate({'item_id':'x','entries_express_need':False,'nothing_lost':True,'rationale':'Old field.'})


def test_v2_mediator_may_defer_a_labelled_need_but_not_set_it_aside(setup):
    from requirement_reuse_service.workflow import fa_discussion as fd
    from test_fa_workflow import Dialogue
    store,run,_=prepared(setup);run['request']['base_review']='expert_v1'
    run['requirements'][0]['processing_flags']=['covered_by_base']
    case=fd.build_cases(store,run,[],Dialogue())[0];rid=run['requirements'][0]['revision_id']
    assert case['policy_version']==fd.BASE_POLICY
    rule='A labelled base-covered need must stay visible'
    def errors(action,**extra):
        plan=fd.Plan(actions=[{'action_id':'a','action':action,'parent_revision_ids':[rid],'rationale':'Synthetic disposition.',**extra}],summary='Synthetic plan.')
        return fd.plan_errors(plan,case,[],set(run['evidence_ids']))
    assert not any(rule in e for e in errors('defer',human_question='Is the base entry enough for this task?',alternatives=['Keep as covered by base','Treat as a domain requirement']))
    assert not any(rule in e for e in errors('retain'))
    assert any(rule in e for e in errors('set_aside',human_question='Restore?'))
    assert 'deferred with a question' in fd.BASE_MEDIATOR_GUIDANCE


def test_one_invalid_judgement_leaves_its_batch_mates_reviewed(setup):
    store,run,_=prepared(setup,4)
    # A source condition that no entry states makes this need's restatement invalid,
    # in its batch and alone; v2 marked all four needs not reviewed.
    bad=sorted(r['revision_id'] for r in run['requirements'])[1]
    def mark(r):next(x for x in r['requirements'] if x['revision_id']==bad)['need_condition']='Only if an authorised recipient has signed a special agreement.'
    store.mutate(run['run_id'],None,'fixture_condition',mark);run=store.get('run',run['run_id'])
    client=Reviewer('restates_base');br.review_base(store,run,client)
    saved=store.get('run',run['run_id']);rows={r['revision_id']:r for r in saved['requirements']}
    assert rows[bad]['base_relation']['status']=='not_reviewed' and 'base_review_pending' in rows[bad]['processing_flags']
    others=[r for rid,r in rows.items() if rid!=bad]
    assert all(r['base_relation']['status']=='checked' and r['base_relation']['effect']=='flag_added' for r in others)
    assert all(r['base_relation']['isolated_from_failed_batch']['review']==r['base_relation']['batch_key'] for r in others)
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReview',4),('BaseReviewChecks',3),('BaseReview',1),('BaseReview',1)]
    assert {q['effect'] for q in saved['stage_results']['base_review']['review_questions']}=={'flag_added'}
    assert len(saved['stage_results']['base_review']['review_questions'])==3
    before=len(client.calls);br.review_base(store,saved,client);assert len(client.calls)==before


def test_a_need_invalid_alone_keeps_its_errors(setup):
    # JRC re-normalized run: one need's condition-guard or entry-limit error left all four not reviewed.
    store,run,_=prepared(setup,4)
    client=Reviewer('new',lambda v,n:v.update(verdict='restates_base',entry_ids=['B999']) if v['item_id']=='N1' else None)
    br.review_base(store,run,client)
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReview',4),('BaseReviewChecks',3),('BaseReview',1),('BaseReview',1)]
    rows={r['revision_id']:r['base_relation'] for r in store.get('run',run['run_id'])['requirements']}
    first=sorted(rows)[0]
    assert rows[first]['status']=='not_reviewed' and rows[first]['reason']=='invalid_output'
    assert any('cite only entries' in e for e in rows[first]['errors'])
    assert all(rows[rid]['status']=='checked' for rid in sorted(rows)[1:])
    before=len(client.calls);br.review_base(store,store.get('run',run['run_id']),client)
    assert len(client.calls)==before


def test_a_missing_check_is_repeated_for_that_need_alone(setup):
    store,run,_=prepared(setup,4)
    class DropsFirstCheck(Reviewer):
        def generate_structured(self,*,user,output_model,**kw):
            result=super().generate_structured(user=user,output_model=output_model,**kw)
            return output_model(checks=result.checks[1:]) if output_model==br.BaseReviewChecks and len(result.checks)>1 else result
    client=DropsFirstCheck('new');br.review_base(store,run,client)
    saved=store.get('run',run['run_id'])
    assert all(r['base_relation']['status']=='checked' for r in saved['requirements'])
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReviewChecks',4),('BaseReviewChecks',4),('BaseReviewChecks',1)]
    isolated=[r['base_relation'].get('isolated_from_failed_batch') for r in saved['requirements']]
    assert sum(bool(i) for i in isolated)==3 and all(i['check'].startswith('base_review_check:') for i in isolated if i)


def test_correction_names_the_model_aliases_and_shows_the_rejected_answer(setup):
    store,run,_=prepared(setup)
    class Recorder(Reviewer):
        def __init__(self):super().__init__('restates_base',lambda v,n:v.update(entry_ids=['B999']) if not self.calls[:-1] else None);self.systems=[]
        def generate_structured(self,*,system,**kw):
            self.systems.append(system);return super().generate_structured(**kw)
    client=Recorder();br.review_base(store,run,client)
    rid=run['requirements'][0]['revision_id'];second=client.systems[1]
    assert 'Your previous answer was rejected: {' in second and 'N1: cite only entries' in second and '"B999"' in second
    assert rid not in second and 'rev-' not in second
    assert store.get('run',run['run_id'])['requirements'][0]['base_relation']['status']=='checked'


def test_a_listed_items_need_may_cite_up_to_twelve_entries():
    rows=[f'base-{i}' for i in range(13)]
    assert br.BaseVerdict(item_id='n',verdict='restates_base',entry_ids=rows[:12],rationale='Twelve items.')
    with pytest.raises(Exception):br.BaseVerdict(item_id='n',verdict='restates_base',entry_ids=rows,rationale='Thirteen items.')


def test_condition_error_tells_the_reviewer_how_to_answer(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    n.need_condition='Only if an authorised recipient has signed a special agreement.'
    payload,_=br.make_payload(store,run,[n],cat,'before_discussion')
    entry=payload['needs'][n.revision_id]['offered_entry_ids'][0]
    verdict=br.BaseReview(verdicts=[dict(item_id=n.revision_id,verdict='restates_base',entry_ids=[entry],rationale='Plain.')])
    assert any('domain_use_of_base' in e for e in br.verdict_errors(verdict,[n],payload,cat))


def test_derived_opt_in_run_shows_stage_6a_pending(setup):
    from requirement_reuse_service.workflow import engine
    from requirement_reuse_service.workflow.models import DeriveRequest
    store,source=derivable(setup)
    def opt_in(r):
        r['request']['base_review']='expert_v1';r['stages']['base_review']='completed'
        r['role_runs']=[{'role_id':'consumer_discovery','status':'completed'}]
    store.mutate(source['run_id'],None,'fixture_opt_in',opt_in);source=store.get('run',source['run_id'])
    child=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        rationale='Downstream trial.',output_form='needs',scoping='off',base_check=False,discussion='automatic'))
    assert child['request']['base_review']=='expert_v1' and child['stages']['base_review']=='pending'


def test_the_checker_reads_the_entry_the_classifier_relied_on(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    access=next(e['id'] for e in cat['entries'] if (e['class'],e.get('property'))==('dcat:Dataset','dct:accessRights'))
    n.matched_base_need_ids=[access];n.processing_flags=['covered_by_base']
    payload,aliases=br.make_payload(store,run,[n],cat,'before_discussion')
    verdict=br.BaseVerdict(item_id=n.revision_id,verdict='new',rationale='No entry names it.').model_dump(mode='json')
    check=br.make_check_payload(payload,[verdict],cat)
    # v2 showed no entry text for a "new" verdict, so its checker could not weigh the match.
    assert list(check['base']['entries'])==[access] and check['base']['entries'][access]['usage_notes']
    assert 'classifier' in br.CHECK_SYSTEM and 'domain_use_of_base' in br.REVIEW_SYSTEM.split('new:')[1]


def test_a_verdict_may_cite_up_to_twelve_of_its_own_excerpts(setup):
    # JRC run-fd39639e: one review call failed the schema for citing more than 4 excerpts.
    from requirement_reuse_service.workflow.models import EvidenceLink
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0])
    unit=store.get('evidence',n.evidence_links[0].evidence_id)
    n.evidence_links=[EvidenceLink(evidence_id=unit['evidence_id'],quote=unit['content'][i:i+10],quote_start=i) for i in range(0,39,3)]
    payload,_=br.make_payload(store,run,[n],cat,'before_discussion');own=payload['needs'][n.revision_id]['excerpt_ids']
    row=dict(item_id=n.revision_id,verdict='domain_use_of_base',entry_ids=payload['needs'][n.revision_id]['offered_entry_ids'][:1],
        addition_kind='condition',addition='A stated source condition.',rationale='The addition is spread over passages.')
    assert len(own)==13 and br.verdict_errors(br.BaseReview(verdicts=[{**row,'evidence_ids':own[:5]}]),[n],payload,cat)==[]
    with pytest.raises(Exception):br.BaseVerdict(**row,evidence_ids=own)
    # Repeating one excerpt is not more evidence (review probe: 12 copies of one passed).
    assert br.verdict_errors(br.BaseReview(verdicts=[{**row,'evidence_ids':own[:1]*12}]),[n],payload,cat)==[n.revision_id+': cite only this item’s excerpts, each once.']


@pytest.mark.parametrize('fault',[
    lambda rows:rows[0].update(evidence_ids=['E1']*13),
    lambda rows:rows.append({**rows[0],'rationale':''}),
    # Five rows for four needs fail the contract's row limit; the unrepeated rows are still valid.
    lambda rows:rows.append(dict(rows[0])),
],ids=['thirteen_excerpts','invalid_second_row','five_rows_one_repeated'])
def test_valid_rows_of_a_schema_invalid_answer_are_kept(setup,fault):
    # One row over a schema limit failed the whole call of four; its batch-mates' rows are valid.
    store,run,_=prepared(setup,4)
    client=Raw(lambda i,kind,p,out:fault(out['verdicts']) if kind=='BaseReview' and len(p['needs'])==4 else None)
    br.review_base(store,run,client)
    saved=store.get('run',run['run_id']);rows={r['revision_id']:r['base_relation'] for r in saved['requirements']};ids=sorted(rows)
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReview',4),('BaseReviewChecks',3),('BaseReview',1),('BaseReviewChecks',1)]
    assert all(r['status']=='checked' for r in rows.values()) and 'isolated_from_failed_batch' not in rows[ids[0]]
    assert all(rows[rid]['isolated_from_failed_batch']=={'review':rows[rid]['batch_key']} for rid in ids[1:])
    # The parsed answer is saved with internal IDs, so a resumed pass recovers the same rows.
    attempts=saved['stakeholder_audit'][rows[ids[1]]['batch_key']]['attempts']
    assert [a['output'] for a in attempts]==[None,None] and {v['item_id'] for v in attempts[-1]['parsed']['verdicts']}==set(ids)
    before=len(client.calls);br.review_base(store,saved,client);assert len(client.calls)==before


@pytest.mark.parametrize('second,alone',[('unparsed',0),('parsed',1)])
def test_isolation_reads_the_newest_answer_that_parsed(setup,second,alone):
    # A correction that does not parse falls back to the parsed first answer (P1); a parsed
    # correction is never mixed with a row the model replaced in it.
    store,run,_=prepared(setup,4)
    def edit(i,kind,p,out):
        if kind!='BaseReview' or len(p['needs'])!=4:return
        if i==0:out['verdicts'][0].update(verdict='restates_base',entry_ids=['B999'])
        elif second=='unparsed':raise OutputValidationError('BaseReview',[{'loc':[],'type':'json_object_missing'}])
        else:out['verdicts'][1].update(evidence_ids=['E1']*13)
    client=Raw(edit);br.review_base(store,run,client)
    rows={r['revision_id']:r['base_relation'] for r in store.get('run',run['run_id'])['requirements']};ids=sorted(rows)
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReview',4),('BaseReviewChecks',3),('BaseReview',1),('BaseReviewChecks',1)]
    assert all(r['status']=='checked' for r in rows.values())
    assert [rid for rid in ids if 'isolated_from_failed_batch' not in rows[rid]]==[ids[alone]]
    before=len(client.calls);br.review_base(store,store.get('run',run['run_id']),client);assert len(client.calls)==before


def test_a_check_that_stays_invalid_keeps_its_errors_and_no_verdict(setup):
    store,run,_=prepared(setup)
    client=Raw(lambda i,kind,p,out:out['checks'][0].update(item_id='N9') if kind=='BaseReviewChecks' else None)
    br.review_base(store,run,client)
    n=store.get('run',run['run_id'])['requirements'][0];rel=n['base_relation']
    assert [name for name,_ in client.calls]==['BaseReview','BaseReviewChecks','BaseReviewChecks']
    # The report reads 'verdict' as a reviewed judgement; this one was never checked.
    assert rel['status']=='not_reviewed' and rel['reason']=='check_invalid_output' and 'verdict' not in rel
    assert any('Check every item exactly once' in e for e in rel['errors']) and 'base_review_pending' in n['processing_flags']


def test_an_isolated_need_too_large_to_check_keeps_its_provenance(setup,monkeypatch):
    store,run,_=prepared(setup,4);make=br.make_check_payload
    monkeypatch.setattr(br,'make_check_payload',lambda *a:{**make(*a),'padding':'x'*br.MAX_PAYLOAD})
    client=Reviewer('new',lambda v,n:v.update(verdict='restates_base',entry_ids=['B999']) if v['item_id']=='N1' else None)
    br.review_base(store,run,client)
    rows={r['revision_id']:r['base_relation'] for r in store.get('run',run['run_id'])['requirements']};ids=sorted(rows)
    assert [(name,len(p['needs'])) for name,p in client.calls]==[('BaseReview',4),('BaseReview',4),('BaseReview',1),('BaseReview',1)]
    assert rows[ids[0]]['reason']=='invalid_output' and 'isolated_from_failed_batch' not in rows[ids[0]]
    assert all(rows[rid]['reason']=='payload_budget' and rows[rid]['isolated_from_failed_batch']=={'review':rows[rid]['batch_key']} for rid in ids[1:])


def test_ledger_reads_label_removal_by_the_recorded_policy(setup,monkeypatch):
    from requirement_reuse_service.workflow.fa_requirements import coverage_ledger
    store,run,_=prepared(setup,3);ids=sorted(r['revision_id'] for r in run['requirements'])
    # rq1-base-expert-v3 (run-fd39639e) wrote "dispute" for a removed label; v1/v2 for a kept one.
    relations={ids[0]:('rq1-base-expert-v3','dispute',[]),ids[1]:('rq1-base-expert-v2','dispute',['covered_by_base']),ids[2]:(br.POLICY,'flag_removed',[])}
    run['request']['base_review']='expert_v1'
    for r in run['requirements']:
        policy,effect,flags=relations[r['revision_id']];r.update(processing_flags=flags,base_relation={'policy':policy,'effect':effect,'status':'checked'})
    results=[{**r['base_relation'],'revision_id':r['revision_id']} for r in run['requirements']]
    run['stage_results']={'base_review':{'policy_version':'rq1-base-expert-v3','phases':{'before_discussion':{'results':results}},'review_questions':[]}}
    ledger=coverage_ledger(run)
    assert sorted(ledger['base_label_removed_revision_ids'])==[ids[0],ids[2]] and ledger['base_dispute_revision_ids']==[ids[1]]
    # The per-phase effect counts read the policy as well; the saved results keep "dispute".
    # Rows are in creation order and revision IDs are random, so look the v3 row up by ID.
    saved={x['revision_id']:x['effect'] for x in results}
    assert ledger['base_relation_counts']['before_discussion']['effect']=={'flag_removed':2,'dispute':1} and saved[ids[0]]=='dispute'
    assert not br.label_removed(None) and not br.legacy_dispute(None) and br.legacy_dispute({'effect':'dispute','policy':'rq1-base-expert-v1'})
    # The current prompts are bound only to records made under them; a run not yet reviewed will be.
    current=dict(run,stage_results={'base_review':{'policy_version':br.POLICY}});v4=coverage_ledger(current)['contract_hash']
    assert coverage_ledger(dict(run,stage_results={}))['contract_hash']==v4!=ledger['contract_hash']
    monkeypatch.setattr(br,'REVIEW_SYSTEM',br.REVIEW_SYSTEM+' changed')
    assert coverage_ledger(run)['contract_hash']==ledger['contract_hash'] and coverage_ledger(current)['contract_hash']!=v4


def test_correction_aliases_ids_inside_structured_problems():
    problems=[{'concern_index':0,'unknown_need_ids':['N9'],'known':['rev-1']},'rev-1: cite only entries']
    text=br.correction({'output':None,'errors':problems},{'N1':'rev-1'})
    assert '"known":["N1"]' in text and 'N1: cite only entries' in text and 'rev-1' not in text


def test_the_check_lets_a_domain_use_be_on_another_resource_class():
    # REVIEW_SYSTEM allows a domain use on another resource class; the v4 check required the
    # same resource for it, so such verdicts could only fail (JRC run-934df8ba: 2 of 4 failed checks).
    assert 'other resource class' in br.REVIEW_SYSTEM
    assert 'for restates_base the cited entries are about the same resource and property meaning' in br.CHECK_SYSTEM
    assert 'for domain_use_of_base they have the same property meaning, on the same resource unless the stated addition is another resource class' in br.CHECK_SYSTEM
    assert 'restates_base and domain_use_of_base' not in br.CHECK_SYSTEM


class SupportedButLost(Reviewer):
    """The checker agrees with the verdict but answers nothing_lost=false (JRC run-e1e4810f)."""
    def generate_structured(self,*,user,output_model,**kw):
        out=super().generate_structured(user=user,output_model=output_model,**kw)
        if output_model==br.BaseReviewChecks:
            return output_model(checks=[{**c.model_dump(),'nothing_lost':False} for c in out.checks])
        return out


@pytest.mark.parametrize('verdict,status',[('new','checked'),('uncertain','checked'),
    ('restates_base','check_failed'),('domain_use_of_base','check_failed')])
def test_nothing_lost_decides_only_restatements_and_domain_uses(setup,verdict,status):
    store,run,_=prepared(setup)
    def label(r):r['requirements'][0]['processing_flags']=[*r['requirements'][0].get('processing_flags',[]),'covered_by_base']
    store.mutate(run['run_id'],None,'fixture_label',label)
    br.review_base(store,store.get('run',run['run_id']),SupportedButLost(verdict))
    n=store.get('run',run['run_id'])['requirements'][0]
    assert n['base_relation']['status']==status and n['base_relation']['check']['nothing_lost'] is False
    # A checked new verdict removes the label; a failed check keeps it.
    assert ('covered_by_base' in n['processing_flags'])==(verdict!='new')
    assert 'for new and uncertain always true' in br.CHECK_SYSTEM
