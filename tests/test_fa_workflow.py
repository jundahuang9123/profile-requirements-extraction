"""Synthetic F/A protocol tests: no benchmark answers and no live provider calls."""
import copy
import json
import pytest
from test_routed_stakeholder_workflow import setup, make_record, install_records
from requirement_reuse_service.workflow import engine, fa_requirements as fa, fa_discussion as discussion
from requirement_reuse_service.workflow.models import RunRequest
from requirement_reuse_service.workflow.storage import digest
from requirement_reuse_service.workflow.needs import statement_errors, NeedStatements
from requirement_reuse_service.llm.step_models import StepModelRouter
from requirement_reuse_service.llm.config import LLMConfig


def enable(store,run):
    def change(r):
        r['request'].update(stakeholder_workflow='fa_mediated',requirements_scope='find_access_v1')
        r['stakeholder_audit']['fa_contract']=fa.contract()
    store.mutate(run['run_id'],None,'fixture_fa',change)
    return store.get('run',run['run_id'])

def contract_name(model):
    """rq1-fa-dialogue-v6 and later ask for ExperienceReview and ExperiencePlan, which extend Review and
    Plan, and v8 for DefinedChecks, which extends Checks; scripted clients answer them alike."""
    return {'ExperienceReview':'Review','ExperiencePlan':'Plan','DefinedChecks':'Checks'}.get(model.__name__,model.__name__)


class Dialogue:
    def __init__(self,objection=False,set_aside=False):self.calls=[];self.objection=objection;self.set_aside=set_aside;self.step=None
    def describe(self):return {'provider':'scripted','model':self.step or 'fixture'}
    def for_step(self,step):
        parent=self
        class Bound:
            def describe(self):return {'provider':'scripted','model':'model-'+step,'reasoning_effort':'low'}
            def generate_structured(self,**kw):return parent.generate_structured(**kw,step=step)
        return Bound()
    def generate_structured(self,*,user,output_model,step=None,**kwargs):
        data=json.loads(user);name=contract_name(output_model);self.calls.append((step,name,data))
        if name=='TaskGroups':raw={'groups':[{'task':'Find contact and access conditions','revision_ids':[n['revision_id'] for n in data['needs']], 'rationale':'Same source-supported dataset selection task.'}]}
        # rq1-fa-dialogue-v5 labels needs by task; one shared label gives the same single case.
        elif name=='TaskLabels':raw={'labels':[{'need':a,'task':'Find contact and access conditions'} for a in data['needs']]}
        elif name=='Review':
            ids=[n['revision_id'] for n in data['packet']['needs']]
            concern={'revision_ids':ids,'kind':'interference' if self.objection and not data.get('draft') else 'satisfied',
                'statement':'Check the access condition before approving the wording.','evidence_ids':[data['packet']['excerpts'][0]['evidence_id']]}
            raw={'summary':'Source-supported task checked.','concerns':[concern] if self.objection else [],'finished':True,'evidence_queries':[]}
        elif name=='Plan':
            packet=data['packet'];ids=[n['revision_id'] for n in packet['needs']]
            actions=[{'action_id':'a'+str(i),'action':'set_aside' if self.set_aside else 'retain','parent_revision_ids':[rid],
                'rationale':'Review relevance without discarding evidence.','human_question':'Restore if a supported information task is established.' if self.set_aside else None} for i,rid in enumerate(ids)]
            raw={'actions':actions,'summary':'No source-backed priority is invented.','questions':[],
                'concerns':[{'concern_id':c['concern_id'],'status':'satisfied','action_ids':['a0'],'rationale':'Original source condition retained.'} for m in data['messages'] for c in m['concerns']]}
        elif name=='Checks':raw={'checks':[{'action_id':a['action_id'],'supported':True,'preserves_distinctions':True,
            'priority_supported':False,'condition_supported':True,'obligation_preserved':True,'fa_relevant':True,
            'disposition_justified':True,'rationale':'Synthetic evidence supports the saved disposition.'} for a in data['plan']['actions']]}
        # Scope contract v1 (v13): the needs a change writes pass both scope tests at apply.
        elif name=='FAScopeResult':raw={'decisions':[{'need_id':i,'support':'explicit','serves':'find','nature':'information_requirement',
            'actor':'Users','task':'Select a dataset','example':'Select a dataset by its access conditions.','rationale':'Synthetic F/A judgement.',
            'evidence_ids':list(row['excerpts'])[:1]} for i,row in data['needs'].items()]}
        elif name=='ProfileScope':raw={'decisions':[{'need_id':i,'record_resource':'dataset','record_statement':'dataset: what the need names',
            'catalogue_level':True,'serves':'find','example':'Filter datasets by it.','rationale':'Synthetic record judgement.'} for i in data['needs']]}
        else:raise AssertionError(name)
        return output_model.model_validate(raw)


def test_scope_contract_and_historical_compatibility():
    request=RunRequest(snapshot_id='s',strategy='multi_agent',stakeholder_workflow='fa_mediated')
    assert request.requirements_scope=='find_access_v1'
    assert not fa.enabled({'request':{'stakeholder_workflow':'routed_mediated'}})
    with pytest.raises(ValueError,match='contract changed'):
        fa.enabled({'request':request.model_dump(),'stakeholder_audit':{'fa_contract':{'wrong':True}}})


def test_independent_positions_reengage_finished_roles_and_resume_no_calls(setup):
    store,run,units,_=setup
    run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,u,i) for i,u in enumerate(units)])
    frozen=copy.deepcopy(run['machine_snapshot']);client=Dialogue(objection=True)
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human'
    assert saved['machine_snapshot']==frozen
    assert len(saved['deliberations'])==1  # Cross-document task case, not shared-quote grouping.
    case=saved['deliberations'][0]
    initial=[p for _,name,p in client.calls if name=='Review' and not p.get('draft')]
    assert len(initial)==2 and all(p['messages']==[] for p in initial)
    assert len(case['discussion_trace']['targeted_roles'])==2
    assert len(case['messages'])==4  # Finished initial positions cannot suppress new objections.
    assert all(m['evidence_ids'] for m in case['messages'])
    assert set(case['discussion_trace']['phases']) >= {'draft','final','check'}
    assert len(case['discussion_trace']['checks']['checks'])==2  # Retains also checked.
    assert {'stakeholder_review','mediation','mediation_check'} <= {s for s,_,_ in client.calls}
    calls=len(client.calls);discussion.deliberate(store,run['run_id'],client)
    assert len(client.calls)==calls
    assert not saved['decisions']


def test_reversible_set_aside_keeps_inventory_and_evidence(setup):
    store,run,units,_=setup;run=enable(store,run)
    rec=make_record(store,run,units[0]);run=install_records(store,run,[rec])
    discussion.deliberate(store,run['run_id'],Dialogue(set_aside=True))
    saved=store.get('run',run['run_id'])
    assert not saved['active_revision_ids']
    assert saved['requirements'][0]['evidence_links']==rec.model_dump()['evidence_links']
    aside=saved['set_aside_observations'][0]
    assert aside['reversible'] and not aside['restored'] and aside['observation_id']
    assert fa.coverage_ledger(saved)['inventory']


@pytest.mark.parametrize('legacy', [False, True])
def test_final_mediator_transport_resume_reuses_saved_phases_with_longer_timeout(setup, legacy):
    from requirement_reuse_service.llm.client import LLMError

    class Interrupted(Dialogue):
        def __init__(self):
            super().__init__(objection=True)
            self.timeout = 240
            self.fail_final = True

        def for_step(self, step):
            parent = self
            bound = super().for_step(step)
            describe = bound.describe
            bound.describe = lambda: {**describe(), 'timeout_seconds': parent.timeout}
            return bound

        def generate_structured(self, *, user, output_model, step=None, **kwargs):
            data = json.loads(user)
            if contract_name(output_model) == 'Plan' and data.get('draft') and self.fail_final:
                raise LLMError('ReadTimeout: no response accepted')
            return super().generate_structured(user=user, output_model=output_model,
                                               step=step, **kwargs)

    store, run, units, _ = setup
    run = enable(store, run)
    run = install_records(store, run, [make_record(store, run, u, i) for i, u in enumerate(units)])
    client = Interrupted()
    with pytest.raises(LLMError, match='ReadTimeout'):
        discussion.deliberate(store, run['run_id'], client)
    if legacy:
        def legacy_layout(row):
            trace = row['deliberations'][0]['discussion_trace']
            trace.pop('message_replay_policy')
            for phase in trace['phases'].values():
                phase.pop('message', None)
        store.mutate(run['run_id'], None, 'fixture_legacy_message_layout', legacy_layout)
    before = store.get('run', run['run_id'])
    case = before['deliberations'][0]
    phases = copy.deepcopy(case['discussion_trace']['phases'])
    assert phases['draft']['output'] and not phases['final'].get('output')
    assert case['status'] == 'queued'
    completed_calls = len(client.calls)
    client.timeout = 480
    client.fail_final = False
    if legacy:
        original_trace = copy.deepcopy(before['deliberations'][0]['discussion_trace'])
        def changed_anchor(row):
            row['deliberations'][0]['discussion_trace']['phases']['draft']['input_hash'] = 'changed'
        store.mutate(run['run_id'], None, 'fixture_changed_anchor', changed_anchor)
        with pytest.raises(ValueError, match='checkpoint mismatch: draft'):
            discussion.deliberate(store, run['run_id'], client)
        assert len(client.calls) == completed_calls
        store.mutate(run['run_id'], None, 'fixture_restore_anchor',
            lambda row: row['deliberations'][0].update(discussion_trace=original_trace))
    discussion.deliberate(store, run['run_id'], client)
    after = store.get('run', run['run_id'])
    assert after['status'] == 'awaiting_human'
    assert [name for _, name, _ in client.calls[completed_calls:]] == ['Plan', 'Checks']
    for key, value in phases.items():
        if value.get('output'):
            replayed = after['deliberations'][0]['discussion_trace']['phases'][key]
            assert replayed['output'] == value['output']
            assert replayed['attempts'] == value['attempts']
            if not legacy:
                assert replayed == value
    replay = after['deliberations'][0]['discussion_trace']
    if legacy:
        recovery = replay['message_replay_recovery']
        assert recovery['status'] == 'completed'
        assert recovery['rebindings'] and recovery['draft_input_hash'] == phases['draft']['input_hash']
        assert all(m['old_input_hash'] != m['new_input_hash'] for m in recovery['rebindings'])
        assert all(p['message']['created_at'] is None for k, p in replay['phases'].items()
                   if k.startswith('response:'))
    else:
        assert 'message_replay_recovery' not in replay
    assert after['machine_snapshot'] == before['machine_snapshot']
    assert not after['decisions']


def test_retrieval_uses_only_frozen_ids_and_records_zero_results(setup):
    store,run,units,_=setup
    rows,audit=discussion.retrieve_frozen(store,run,['access conditions','nonexistentzxy'],set())
    assert rows and all(r['evidence_id'] in run['evidence_ids'] for r in rows)
    assert audit[-1]['unresolved']
    for row in rows:
        u=store.get('evidence',row['evidence_id'])
        assert u['content'][row['quote_start']:row['quote_start']+len(row['quote'])]==row['quote']


def test_ledger_never_claims_unprocessed_or_unaccounted_complete():
    run={'run_id':'r','snapshot_id':'s','evidence_ids':['a','b'],'observations':[
        {'observation_id':'o','evidence_links':[{'evidence_id':'a'}]}], 'role_runs':[
        {'role_id':'reader','citation_selections':[{'status':'materialized','evidence_ids':['a'],'observation_count':1}]}]}
    ledger=fa.coverage_ledger(run)
    assert ledger['counts']['processed_units']==1
    assert ledger['counts']['unaccounted_observations']==1
    assert ledger['source_units'][1]['state']=='unprocessed'


def test_scope_partial_invalid_preserves_valid_axes_and_uncertain_original(setup):
    store,run,units,_=setup;run=enable(store,run)
    needs=[make_record(store,run,u,i) for i,u in enumerate(units)]
    class Partial:
        def describe(self):return {'provider':'scripted','model':'fixture'}
        def generate_structured(self,*,user,output_model,**kw):
            offered=json.loads(user)['needs'];rows=[]
            if needs[0].requirement_id in offered:
                rows=[{'need_id':needs[0].requirement_id,'support':'explicit','serves':'find','nature':'information_requirement',
                    'actor':'Users','task':'Find access conditions','example':'Filter before applying for access',
                    'rationale':'The fixture states an information task.','evidence_ids':[units[0]['evidence_id']]}]
            return output_model.model_validate({'decisions':rows})
    retained=fa.judge_scope(store,run,needs,Partial())
    assert len(retained)==2
    assert retained[0].fa_scope['status']=='checked'
    assert retained[1].fa_scope['status']=='not_checked'
    assert 'fa_scope_review_required' in retained[1].processing_flags


def test_no_opinion_is_not_consensus_and_invalid_retention_is_visible(setup):
    store,run,units,_=setup;run=enable(store,run)
    rec=make_record(store,run,units[0]);run=install_records(store,run,[rec])
    roles=[r.model_dump(mode='json') for r in engine.roles_for(RunRequest.model_validate(run['request']))]
    case=discussion.build_cases(store,run,roles,Dialogue())[0]
    plan=discussion.Plan(actions=[{'action_id':'a','action':'retain','parent_revision_ids':[rec.revision_id],'rationale':'A citation exists.'}],summary='Check relevance separately.')
    checks=discussion.Checks(checks=[{'action_id':'a','supported':True,'preserves_distinctions':True,
        'priority_supported':False,'condition_supported':True,'obligation_preserved':True,'fa_relevant':False,
        'disposition_justified':False,'rationale':'A cited statistic alone does not establish an information task.'}])
    outcomes,added,replaced,asides=discussion.apply(store,run,case,plan,checks,None,{units[0]['evidence_id']})
    assert outcomes[0]['status']=='human_review' and not outcomes[0]['applied']
    assert not added and not replaced and not asides


def test_explicit_submodel_inherits_discussion_and_options_are_separate():
    made=[]
    class Client:
        def __init__(self,c):self.c=c;made.append(c)
    router=StepModelRouter(LLMConfig(provider='mock',model='default',reasoning_effort='low'),
        {'discussion':'inferenz-gpt-oss-120b','mediation':'inferenz-qwen3-8-27b'},Client,
        options={'mediation':{'reasoning_effort':'medium'}})
    assert router.for_step('stakeholder_review').c.model=='inferenz-gpt-oss-120b'
    assert router.for_step('mediation').c.model=='inferenz-qwen3-8-27b'
    assert router.for_step('mediation').c.reasoning_effort=='medium'
    assert router.for_step('mediation_check').c.reasoning_effort=='low'


def test_full_fa_pipeline_freezes_contract_and_preserves_trace(setup):
    from test_rq1_need_assessment import FullNeedsClient
    store,original,_,_=setup
    class Full(FullNeedsClient):
        def __init__(self):super().__init__();self.dialogue=Dialogue()
        def generate_structured(self,**kw):
            name=kw['output_model'].__name__;data=json.loads(kw['user'])
            if name in {'TaskGroups','Review','Plan','Checks'}:return self.dialogue.generate_structured(**kw)
            if name=='SourceRouting':raw={'routes':[{'evidence_id':s['evidence_id'],'kind':'shared','role_ids':['shared_source_extractor'],'rationale':'Common source information task.'} for s in data['sections']]}
            elif name=='FAPreservation':raw={'checks':[{'group_id':g,'information_preserved':True,'actor_preserved':True,'purpose_preserved':True,'conditions_preserved':True,'obligation_preserved':True,'negation_preserved':True,'rationale':'Fixture distinctions preserved.'} for g in data['groups']]}
            elif name=='FAScopeResult':raw={'decisions':[{'need_id':i,'support':'explicit','serves':'find','nature':'information_requirement','actor':'Users','task':'Find a dataset','example':'Select a dataset using its title','rationale':'Synthetic source-supported discovery task.','evidence_ids':list(row['excerpts'])} for i,row in data['needs'].items()]}
            elif name=='NeedMembership':raw={'checks':[{'member_id':i,'expresses_need':True,'rationale':'Same fixture need.'} for i in data['members']]}
            else:return super().generate_structured(**kw)
            return kw['output_model'].model_validate(raw)
    run=engine.new_run(store,RunRequest(snapshot_id=original['snapshot_id'],strategy='multi_agent',
        role_ids=['consumer_discovery','publisher_feasibility'],stakeholder_workflow='fa_mediated',discussion='automatic',scoping='off',base_check=False))
    assert run['stakeholder_audit']['fa_contract']==fa.contract()
    engine.execute_run(store,run['run_id'],Full())
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert saved['active_revision_ids']
    assert saved['deliberations']
    assert saved['need_steps']['profile_scope']['policy_version']=='rq1-profile-scope-v10'
    assert saved['need_steps']['profile_scope']['fa_policy_version']=='rq1-find-access-v1'
    assert saved['need_steps']['dataset_applicability']['not_checked_ids']
    assert all(r['fa_scope']['status']=='checked' for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids'])
    ledger=fa.coverage_ledger(saved)
    assert ledger['counts']['unaccounted_observations']==0
    assert ledger['counts']['processed_units']==len(saved['evidence_ids'])
    from requirement_reuse_service.workflow.needs import needs_export
    exported=needs_export(store,run['run_id'])
    assert exported['fa_coverage']['counts']==ledger['counts']
    assert saved['machine_snapshot']['active_revision_ids']


def test_lossy_rewrite_keeps_originals_visibly(setup):
    from requirement_reuse_service.workflow.needs import NeedStatements
    store,run,units,_=setup;run=enable(store,run)
    members=[make_record(store,run,u,i) for i,u in enumerate(units)]
    payload={'groups':{'g':{'members':{m.revision_id:{'statement':m.need_statement} for m in members}}}}
    answer=NeedStatements(needs=[{'group_id':'g','statement':'Users can find metadata.',
        'members':[{'member_id':m.revision_id,'expresses_need':True} for m in members]}])
    class Lossy:
        def generate_structured(self,*,output_model,**kw):
            return output_model.model_validate({'checks':[{'group_id':'g','information_preserved':False,
                'actor_preserved':True,'purpose_preserved':True,'conditions_preserved':True,
                'obligation_preserved':True,'negation_preserved':True,'rationale':'A topic label loses specific information.'}]})
    failed=[]
    result=fa.preserve_rewrites(store,run,payload,answer,{'g':members},Lossy(),failed)
    assert not result.needs
    # rq1-need-statement-v3: the members are not set aside; write_needs rewrites them one by one.
    assert [f[0] for f in failed]==[members] and failed[0][2].startswith('Lossless rewrite not established: A topic label')
    assert all(m.lifecycle_state!='set_aside' for m in members)
    assert not store.get('run',run['run_id'])['set_aside_observations']


def test_expanded_source_cannot_escape_snapshot_and_false_revision_keeps_parent(setup):
    from requirement_reuse_service.workflow import stakeholder_workflow as old
    from test_routed_stakeholder_workflow import plan_for, checks_for
    store,run,units,_=setup;r=make_record(store,run,units[0])
    run=install_records(store,run,[r]);case=old.build_cases(store,run,[])[0]
    with pytest.raises(ValueError,match='outside frozen'):
        old.apply_plan(store,run,case,plan_for(r),checks_for(),None,allowed_evidence_ids={'outside'})


def test_material_case_budget_is_bounded_without_restarting_work(setup,monkeypatch):
    store,run,units,_=setup;run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,units[0])])
    client=Dialogue(objection=True)
    original=discussion.execute_case
    def exhausted(*args):raise discussion.DiscussionBudgetError('Recorded fourteen-call budget exhausted.')
    monkeypatch.setattr(discussion,'execute_case',exhausted)
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human'
    assert saved['metrics']['pending_human_cases']==1
    assert saved['metrics']['mediated_cases']==0
    assert saved['active_revision_ids']==run['active_revision_ids']
    assert saved['deliberations'][0]['stop_reason']=='budget_pending_human_review'


def test_context_budget_is_case_scoped_audited_and_preserves_saved_phases(setup,monkeypatch):
    store,run,units,_=setup;run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,units[0])])
    client=Dialogue()
    original=engine.bounded_stage_output
    def bounded(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs['output_model'] is discussion.Plan:
            monkeypatch.setattr(discussion,'MAX_CONTEXT',1)
        return result
    monkeypatch.setattr(engine,'bounded_stage_output',bounded)
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id']);case=saved['deliberations'][0]
    assert saved['status']=='awaiting_human'
    assert case['stop_reason']=='budget_pending_human_review'
    phases=case['discussion_trace']['phases']
    assert phases['draft']['output']
    assert not phases['check'].get('output') and not phases['check']['attempts']
    budget=phases['check']['context_budget']
    assert budget['measured_characters']>budget['limit_characters']==1
    assert budget['wire_hash'] and budget['policy_version']=='rq1-fa-context-budget-case-v1'
    assert saved['active_revision_ids']==run['active_revision_ids']
    assert saved['machine_snapshot']==run['machine_snapshot']
    calls=len(client.calls)
    discussion.deliberate(store,run['run_id'],client)
    assert len(client.calls)==calls


def test_modality_only_allowed_when_separately_source_checked():
    data=NeedStatements(needs=[{'group_id':'g','statement':'The metadata must let users find an access condition.',
        'members':[{'member_id':'m','expresses_need':True}]}])
    offered={'g':{'obligation':'unknown','members':{'m':{'statement':data.needs[0].statement}}}}
    assert statement_errors(data,offered,None,True)
    offered['g']['obligation']='mandatory'
    assert not statement_errors(data,offered,None,True)
    assert statement_errors(data,offered,None,False)  # Historical neutral contract is unchanged.


def test_matched_comparison_preparation_does_not_use_outcomes(setup):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('prepare_fa',Path(__file__).resolve().parents[1]/'scripts/prepare_fa_case_comparison.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    store,run,units,_=setup;run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,units[0])]);discussion.deliberate(store,run['run_id'],Dialogue())
    from requirement_reuse_service.workflow.stakeholder_workflow import trace_run
    trace=trace_run(store,run['run_id']);manifest=module.prepare(trace)
    assert manifest['arms']['qwen_mediator']['mediation']=='inferenz-qwen3-8-27b'
    assert manifest['arms']['qwen_mediator']['mediation_check']=='inferenz-gpt-oss-120b'
    assert 'outcomes' not in manifest['cases'][0]
    assert manifest['cases'][0]['packet_hash']==digest(manifest['cases'][0]['packet'])
    trace['discussions'][0]['discussion_trace']['packet']['source_snapshot_id']='changed'
    with pytest.raises(ValueError,match='changed'):module.prepare(trace)


def test_panel_gaps_are_explicit_without_inventing_task_coverage(setup):
    store,run,_,_=setup
    # Manual roles have no declared source-task endorsement.
    audit=fa.panel_task_coverage(store,run)
    assert not audit['declared_task_links']
    assert any('No formal tasks' in t for t in audit['limitations'])


def test_invalid_case_output_is_bounded_and_visible_not_silent_loss(setup,monkeypatch):
    store,run,units,_=setup;run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,units[0])])
    def invalid(*args):raise discussion.DiscussionValidationError('Final action accounting remains invalid after correction.')
    monkeypatch.setattr(discussion,'execute_case',invalid)
    discussion.deliberate(store,run['run_id'],Dialogue())
    saved=store.get('run',run['run_id'])
    assert saved['active_revision_ids']==run['active_revision_ids']
    assert saved['deliberations'][0]['stop_reason']=='invalid_output_pending_human_review'
    assert 'accounting' in saved['deliberations'][0]['mediation']['human_questions'][0]['question']
    assert saved['metrics']['pending_human_cases']==1


def test_split_uses_distinct_child_identities_and_original_obligation(setup,monkeypatch):
    from requirement_reuse_service.workflow import stakeholder_workflow as old
    from requirement_reuse_service.workflow.models import Qualification
    store,run,units,_=setup;run=enable(store,run)
    rec=make_record(store,run,units[0]);run=install_records(store,run,[rec])
    case=discussion.build_cases(store,run,[],Dialogue())[0]
    link=rec.evidence_links[0].model_dump(mode='json')
    action={'action_id':'split','action':'split','parent_revision_ids':[rec.revision_id],
        'statement':rec.need_statement,'evidence_links':[link],'rationale':'Two distinct source-supported information tasks.',
        'children':[{'action_id':name,'statement':statement,'evidence_links':[link],'rationale':'Fixture child.'} for name,statement in [('one','Users can find access conditions.'),('two','Users can identify applicable access conditions.')]]}
    plan=discussion.Plan(actions=[action],summary='Explicit child needs.')
    check={'action_id':'split','supported':True,'fa_relevant':True,'disposition_justified':True,
        'preserves_distinctions':True,'priority_supported':False,'condition_supported':True,'obligation_preserved':True,'rationale':'Synthetic split check.'}
    monkeypatch.setattr(engine,'assess',lambda store,record,client:Qualification(support='explicit',rationale='Fixture support.',assessor='fixture'))
    outcomes,added,replaced,asides=discussion.apply(store,run,case,plan,discussion.Checks(checks=[check]),None,{units[0]['evidence_id']})
    assert outcomes[0]['applied']
    assert len(added)==2 and len({r['requirement_id'] for r in added})==2
    assert all(r['parent_revision_ids']==[rec.revision_id] for r in added)
    assert all(r['normalized_intent']['obligation_hint']==rec.normalized_intent.obligation_hint for r in added)
    assert all(set(rec.observation_ids)<=set(r['observation_ids']) for r in added)


@pytest.mark.parametrize('offset',[None,999])
@pytest.mark.parametrize('link_kind',['evidence_links','priority_links'])
def test_unique_citation_offset_repair_uses_evidence_link_contract(setup,monkeypatch,offset,link_kind):
    store,run,units,_=setup
    rec=make_record(store,run,units[0]);parent=rec.model_dump(mode='json')
    quote=units[0]['content'][6:]
    action={'action_id':'repair','action':'revise','parent_revision_ids':[rec.revision_id],
            'statement':rec.need_statement,'rationale':'Keep exact source support.',
            link_kind:[{'evidence_id':units[0]['evidence_id'],'quote':quote,'quote_start':offset}]}
    plan=discussion.Plan(actions=[action],summary='Source-anchored repair.')
    checks=discussion.Checks(checks=[{'action_id':'repair','supported':True,'preserves_distinctions':True,
        'priority_supported':True,'condition_supported':True,'obligation_preserved':True,
        'fa_relevant':True,'disposition_justified':True,'rationale':'Verified synthetic source.'}])
    called=[]
    def downstream(store,run,case,plan,checks,client,**kwargs):
        link=getattr(plan.actions[0],link_kind)[0]
        assert link.quote_start==6
        assert units[0]['content'][link.quote_start:link.quote_start+len(link.quote)]==quote
        assert 'quote_end' not in link.model_dump()
        called.append(True)
        return [{'applied':False}],[],{}
    monkeypatch.setattr(discussion.old,'apply_plan',downstream)
    case={'frozen_requirements':[parent],'mediation':{'related_conflicts':[]}}
    outcomes,additions,replacements,asides=discussion.apply(store,run,case,plan,checks,Dialogue(),{units[0]['evidence_id']})
    assert called==[True]
    assert outcomes[0]['citation_repairs'][0]['from']==offset
    assert outcomes[0]['citation_repairs'][0]['to']==6
    assert not additions and not replacements and not asides
    assert plan.actions[0].model_dump()[link_kind][0]['quote_start']==offset
