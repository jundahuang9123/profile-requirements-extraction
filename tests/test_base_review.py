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
        return output_model(checks=[{'item_id':key,'entries_express_need':self.checked,'nothing_lost':self.checked,'rationale':'Independent synthetic check.'} for key in p['needs']])


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
    br.review_base(store,run,client);assert len(client.calls)==4
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
    check=br.BaseVerdictCheck(item_id=rid,entries_express_need=True,nothing_lost=True,rationale='Checked.')
    br.apply_verdict(n,v,check,'before_discussion',cat,'key',{},p);refresh_need(n)
    assert n.revision_id==rid and n.content_hash==h
    assert ('covered_by_base'in n.processing_flags)==(state=='covered' or verdict=='restates_base')
    assert (n.base_relation['effect']=='dispute')==(state=='covered' and verdict in {'new','domain_use_of_base'})


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
    assert discussion_policy({'request':r.model_dump()})=='rq1-fa-dialogue-v2'
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
    assert any(fd.V2_ROLE_GUIDANCE in s for s in client.systems)
    assert any(fd.V2_MEDIATOR_GUIDANCE in s for s in client.systems)
    assert any(fd.V2_CHECK_GUIDANCE in s for s in client.systems)
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
        r['stakeholder_audit'].update({'fa_discussion_plan':{'old':True},'fa_task_groups:0':{'old':True}})
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
