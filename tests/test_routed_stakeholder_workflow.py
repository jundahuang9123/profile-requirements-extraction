"""Synthetic protocol contracts: never evaluator-side answers or live inference."""
import copy
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (SourceRequest, SnapshotRequest, RunRequest,
    DeriveRequest, Observation, EvidenceLink, NormalizedIntent, Qualification, DeliberationCase)
from requirement_reuse_service.workflow.storage import Store, digest
from requirement_reuse_service.workflow.stakeholder_workflow import (POLICY, EXTRACTION_POLICY, SHARED,
    SourceRouting, SourceRoute, routing_errors, plan_routing, MediationPlan, MediationChecks,
    mediation_errors, build_cases, apply_plan, deliberate, trace_run)
from requirement_reuse_service.workflow.needs import refresh_need


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER','disabled')
    monkeypatch.setattr(engine, 'freeze_step_models', lambda request: request)
    store=Store()
    sources=[register_source(store,SourceRequest(artifact=ArtifactPayload(name=f'input-{i}.txt',content=text),
        source_role='stakeholder_need')) for i,text in enumerate([
            'Users can find the access conditions for a dataset.',
            'Publishers can find the contact details for a dataset.'])]
    snap=engine.freeze_snapshot(store,SnapshotRequest(source_version_ids=[s['source_version_id'] for s in sources]))
    run=engine.new_run(store,RunRequest(snapshot_id=snap['snapshot_id'],strategy='multi_agent',output_form='needs',
        role_ids=['consumer_discovery','publisher_feasibility'],stakeholder_workflow='routed_mediated',
        base_check=False,discussion='automatic',scoping='off'))
    units=[store.get('evidence',e) for e in run['evidence_ids']]
    roles=engine.roles_for(RunRequest.model_validate(run['request']))
    return store,run,units,roles


class RoutingClient:
    def __init__(self):self.calls=[]
    def describe(self):return {'provider':'offline','model':'fixture'}
    def generate_structured(self,*,system,user,output_model,**kwargs):
        self.calls.append(output_model.__name__)
        data=json.loads(user)
        if output_model.__name__=='SourceRouting':
            return output_model.model_validate({'routes':[{'evidence_id':s['evidence_id'],
                'kind':'stakeholder_specific','role_ids':['consumer_discovery'],
                'rationale':'The section states a consumer access concern.'} for s in data['sections']]})
        if output_model.__name__=='NeedSpanElicitationResult':
            return output_model.model_validate({'observations':[]})
        raise AssertionError(output_model.__name__)


def make_record(store,run,unit,index=0):
    link=EvidenceLink(evidence_id=unit['evidence_id'],quote=unit['content'],quote_start=0)
    obs=Observation(observation_id=f'obs-synthetic-{index}',role_id='consumer_discovery',
        statement='Users can find access conditions for a dataset',evidence_links=[link],
        intent=NormalizedIntent(resource_type='Dataset',metadata_need='access conditions'))
    r=engine.record_from_observation(run['run_id'],obs)
    r.need_statement=r.normalized_statement
    refresh_need(r)
    r.verification=engine.verify(store,r,run['evidence_ids'])
    r.qualification=Qualification(support='explicit',rationale='Synthetic fixture.',findings=[],assessor='fixture',revision_hash=r.content_hash)
    return r


def install_records(store,run,records):
    def change(r):
        r.update(requirements=[x.model_dump(mode='json') for x in records],active_revision_ids=[x.revision_id for x in records])
        r['machine_snapshot']={'requirements':copy.deepcopy(r['requirements']),
            'active_revision_ids':list(r['active_revision_ids']),'created_at':'synthetic-freeze'}
    store.mutate(run['run_id'],None,'fixture',change)
    return store.get('run',run['run_id'])


def test_routing_accounts_full_corpus_and_reuses_frozen_plan(setup):
    store,run,units,roles=setup;client=RoutingClient()
    assignments=plan_routing(store,run,units,roles,client)
    assert set(assignments)==set(run['evidence_ids'])
    assert all(v==['consumer_discovery'] for v in assignments.values())
    count=len(client.calls)
    assert plan_routing(store,run,units,roles,client)==assignments
    assert len(client.calls)==count
    saved=store.get('run',run['run_id'])['stakeholder_audit']['routing_plan']
    assert saved['output_hash']==digest(saved['routes'])
    assert saved['source_unit_count']==len(units)


def test_uncertain_or_invalid_routes_fall_back_without_losing_content(setup):
    store,run,units,roles=setup
    class Invalid(RoutingClient):
        def generate_structured(self,**kwargs):
            self.calls.append('invalid')
            return SourceRouting(routes=[])
    client=Invalid();assignments=plan_routing(store,run,units,roles,client)
    assert set(assignments)==set(run['evidence_ids'])
    assert all(v==[SHARED] for v in assignments.values())
    assert len(client.calls)==2
    assert store.get('run',run['run_id'])['stakeholder_audit']['routing:0']['fallback']
    assert routing_errors(SourceRouting(routes=[SourceRoute(evidence_id='e',kind='uncertain',role_ids=['x'],rationale='uncertain')]),['e'],{'x',SHARED})


def test_extraction_reads_only_assigned_units_and_completed_resume_has_no_calls(setup):
    store,run,units,roles=setup
    run['strategy']='multi_agent'
    client=RoutingClient()
    observations,reports=engine.elicit(store,run,client)
    assert observations==[]
    by_id={r['role_id']:r for r in reports}
    assert by_id['consumer_discovery']['processed_unit_count']==len(units)
    assert by_id['publisher_feasibility']['evidence_unit_count']==0
    assert by_id[SHARED]['evidence_unit_count']==0
    n=len(client.calls)
    fresh=store.get('run',run['run_id'])
    engine.elicit(store,fresh,client)
    assert len(client.calls)==n
    fresh['step_models']['extraction']='changed-model'
    # Routing identity itself binds actual client settings, not a mutable label.
    class Changed(RoutingClient):
        def describe(self):return {'provider':'offline','model':'different'}
    with pytest.raises(ValueError,match='checkpoint mismatch'):
        plan_routing(store,fresh,units,roles,Changed())


def plan_for(record,action='revise'):
    return MediationPlan.model_validate({'summary':'Compatible wording, provisional.', 'concerns':[],
        'actions':[{'action_id':'a','action':action,'parent_revision_ids':[record.revision_id],
            'statement':'Users can find the access conditions for a dataset',
            'evidence_links':[l.model_dump(mode='json') for l in record.evidence_links],
            'rationale':'Same source-supported information need.'}]})


def checks_for(**override):
    values=dict(action_id='a',supported=True,preserves_distinctions=True,priority_supported=False,
        condition_supported=True,obligation_preserved=True,rationale='Supported by the synthetic source.')
    return MediationChecks(checks=[{**values,**override}])


def test_mediator_requires_exact_accounting_priority_and_human_question(setup):
    store,run,units,_=setup;r=make_record(store,run,units[0]);p=plan_for(r)
    assert not mediation_errors(p,[r.model_dump()],[],{units[0]['evidence_id']})
    p.actions[0].parent_revision_ids*=2
    assert mediation_errors(p,[r.model_dump()],[],{units[0]['evidence_id']})
    p=plan_for(r,'resolve');p.actions[0].parent_revision_ids.append('other')
    assert any('priority' in e for e in mediation_errors(p,[r.model_dump(),{'revision_id':'other'}],[],{units[0]['evidence_id']}))
    p=plan_for(r,'defer')
    assert any('human question' in e for e in mediation_errors(p,[r.model_dump()],[],{units[0]['evidence_id']}))
    p=plan_for(r);p.actions[0].evidence_links[0].evidence_id='invented'
    assert any('outside' in e for e in mediation_errors(p,[r.model_dump()],[],{units[0]['evidence_id']}))
    p=plan_for(r)
    msg=[{'concerns':[{'concern_id':'missing'}]}]
    assert any('concern' in e for e in mediation_errors(p,[r.model_dump()],msg,{units[0]['evidence_id']}))


def test_revision_rechecks_evidence_and_retains_lineage_without_human_acceptance(setup,monkeypatch):
    store,run,units,_=setup;r=make_record(store,run,units[0]);run=install_records(store,run,[r])
    case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    monkeypatch.setattr(engine,'assess',lambda store,record,client:Qualification(support='explicit',
        rationale='Synthetic independent assessment.',findings=[],assessor='fixture',revision_hash=record.content_hash))
    outcomes,added,replaced=apply_plan(store,run,case,plan_for(r),checks_for(),None)
    assert outcomes[0]['applied'] and outcomes[0]['human_accepted'] is False
    assert added[0]['parent_revision_ids']==[r.revision_id]
    assert added[0]['verification']['status']=='pass'
    assert added[0]['lifecycle_state']=='awaiting_human'
    assert 'base_and_scope_recheck_required' in added[0]['processing_flags']
    assert replaced[r.revision_id]==added[0]['revision_id']
    assert store.get('run',run['run_id'])['machine_snapshot']==run['machine_snapshot']
    bad=plan_for(r);bad.actions[0].evidence_links[0].quote='fabricated quote'
    outcomes,added,replaced=apply_plan(store,run,case,bad,checks_for(),None)
    assert not added and not replaced and outcomes[0]['status']=='blocked_change'
    outcomes,added,replaced=apply_plan(store,run,case,plan_for(r),checks_for(supported=False),None)
    assert not added and outcomes[0]['human_question']


def test_cross_case_conflict_is_preserved_for_human(setup):
    store,run,units,_=setup;r=make_record(store,run,units[0]);run=install_records(store,run,[r])
    case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    case['mediation']['related_conflicts']=[{'revision_ids':[r.revision_id,'outside-case']}]
    outcomes,added,replaced=apply_plan(store,run,case,plan_for(r),checks_for(),None)
    assert not added and not replaced and 'cross-case' in outcomes[0]['validation_error']


def test_bounded_review_mediation_resume_trace_and_immutable_snapshot(setup):
    store,run,units,_=setup;r=make_record(store,run,units[0]);run=install_records(store,run,[r])
    class Reviewer(RoutingClient):
        def generate_structured(self,*,user,output_model,**kwargs):
            self.calls.append(output_model.__name__);data=json.loads(user)
            if output_model.__name__=='StakeholderReview':
                return output_model.model_validate({'summary':'This addresses the documented concern.',
                    'finished':True,'concerns':[{'revision_ids':[r.revision_id],'kind':'satisfied',
                        'statement':'The user can find access conditions.','evidence_ids':[units[0]['evidence_id']]}]})
            if output_model.__name__=='MediationDraft':
                return output_model.model_validate({'summary':'Compatible needs retained.',
                    'actions':[{'action_id':'a','action':'retain','parent_revision_ids':[r.revision_id],
                        'rationale':'The supported concern is met.'}],
                    'concerns':[{'concern_id':c['concern_id'],'status':'satisfied','action_ids':['a'],
                            'rationale':'The retained need covers this concern.'} for c in data['concern_groups']]})
            raise AssertionError(output_model.__name__)
    client=Reviewer();deliberate(store,run['run_id'],client)
    done=store.get('run',run['run_id'])
    assert done['status']=='awaiting_human' and done['stages']['deliberation']=='completed'
    assert done['machine_snapshot']==run['machine_snapshot']
    assert all(c['status']=='mediated' for c in done['deliberations'])
    assert len(done['deliberations'][0]['mediation']['concern_dispositions'])==2
    assert not done['decisions']
    n=len(client.calls);deliberate(store,run['run_id'],client);assert len(client.calls)==n
    traced=trace_run(store,run['run_id'])
    assert traced['candidate_genealogy'][0]['revision_id']==r.revision_id
    assert traced['sources'][0]['raw_sha256']
    response=TestClient(app).get('/api/rq1/v2/runs/'+run['run_id']+'/trace')
    assert response.status_code==200
    assert response.json()['human_decisions']==[]
    exported=TestClient(app).get('/api/rq1/v2/runs/'+run['run_id']+'/export').json()
    assert exported['run']['stakeholder_audit']['post_discussion']


def test_legacy_protocol_and_changed_protocol_derivation_are_separate(setup):
    store,run,units,_=setup
    assert run['elicitation_policy_version']==EXTRACTION_POLICY
    legacy=engine.new_run(store,RunRequest(snapshot_id=run['snapshot_id'],strategy='multi_agent',output_form='needs',base_check=False))
    assert legacy['elicitation_policy_version']!=EXTRACTION_POLICY
    with pytest.raises(ValueError,match='automatic discussion'):
        engine.new_run(store,RunRequest(snapshot_id=run['snapshot_id'],strategy='multi_agent',output_form='needs',base_check=False,
            stakeholder_workflow='routed_mediated',discussion='on_request'))


def test_shared_overlap_and_unassigned_sections_are_explicit():
    valid=SourceRouting(routes=[SourceRoute(evidence_id='e',kind='shared',role_ids=['a','b'],
        rationale='The section separately states a producer obligation and a consumer access task.')])
    assert not routing_errors(valid,['e'],{'a','b',SHARED})
    assert routing_errors(valid,['e','missing'],{'a','b',SHARED})
    valid.routes[0].kind='stakeholder_specific'
    assert routing_errors(valid,['e'],{'a','b',SHARED})


def test_priority_requires_independent_support_and_distinctions_are_protected(setup):
    store,run,units,_=setup
    r=make_record(store,run,units[0]);other=make_record(store,run,units[0],index=2)
    run=install_records(store,run,[r,other]);case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    p=plan_for(r,'resolve');a=p.actions[0]
    a.parent_revision_ids.append(other.revision_id)
    a.priority_basis='A source priority must be verified, not assumed.'
    a.priority_links=[copy.deepcopy(r.evidence_links[0])]
    assert not mediation_errors(p,case['frozen_requirements'],[],{units[0]['evidence_id']})
    outcomes,added,replaced=apply_plan(store,run,case,p,checks_for(priority_supported=False),None)
    assert not added and not replaced and outcomes[0]['status']=='blocked_change'
    a.action='merge'
    outcomes,added,replaced=apply_plan(store,run,case,p,checks_for(preserves_distinctions=False),None)
    assert not added and not replaced


def test_routed_protocol_runs_all_machine_stages_offline_and_keeps_stage_audit(setup):
    from test_rq1_need_assessment import FullNeedsClient
    store,run,_,_=setup
    class Pipeline(FullNeedsClient):
        def generate_structured(self,*,user,output_model,**kwargs):
            data=json.loads(user);name=output_model.__name__
            if name=='NeedEquivalence':
                return output_model.model_validate({'decisions':[{'need_id':i,'equivalent_to':[],
                    'rationale':'Distinct synthetic information need.'} for i in data['needs']]})
            if name=='SourceRouting':
                return output_model.model_validate({'routes':[{'evidence_id':u['evidence_id'],
                    'kind':'shared','role_ids':[SHARED],'rationale':'Shared metadata information needs.'} for u in data['sections']]})
            if name=='SemanticGrouping':
                return output_model.model_validate({'groups':[{'member_ids':[r]} for r in data['candidates']]})
            if name=='NeedStatements':
                return output_model.model_validate({'needs':[{'group_id':i,
                    'statement':next(iter(g['members'].values()))['statement'],'condition':'',
                    'members':[{'member_id':m,'expresses_need':True} for m in g['members']]} for i,g in data['groups'].items()]})
            if name=='StakeholderReview':
                return output_model.model_validate({'summary':'No interference established from supplied evidence.',
                    'finished':True,'concerns':[]})
            if name=='MediationDraft':
                return output_model.model_validate({'summary':'Compatible needs retained for human review.',
                    'actions':[{'action_id':str(i),'action':'retain','parent_revision_ids':[r['revision_id']],
                        'rationale':'Source-supported information need; no priority claim.'} for i,r in enumerate(data['context']['needs'])],
                    'concerns':[]})
            return super().generate_structured(user=user,output_model=output_model,**kwargs)
    engine.execute_run(store,run['run_id'],Pipeline())
    done=store.get('run',run['run_id'])
    assert done['status']=='awaiting_human',done['diagnostics']
    assert done['stages']['elicitation']=='completed'
    assert done['stages']['deliberation']=='completed'
    assert done['active_revision_ids']
    assert done['stakeholder_audit']['stage:elicitation']['output_hash']
    assert done['stakeholder_audit']['discussion_plan']['reviewed_revision_ids']
    assert done['machine_snapshot']['active_revision_ids']
    assert done['decisions']==[]
    traced=TestClient(app).get('/api/rq1/v2/runs/'+run['run_id']+'/stages/elicitation').json()
    assert traced['results']['stakeholder_audit']['routing_plan']


def test_case_time_budget_is_preserved_on_resume_and_stops_before_call(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import execute_mediated_case
    store,run,units,_=setup;r=make_record(store,run,units[0]);run=install_records(store,run,[r])
    case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    case['model_seconds']=case['max_seconds']
    store.mutate(run['run_id'],None,'fixture',lambda row:row.update(deliberations=[case]))
    client=RoutingClient()
    with pytest.raises(ValueError,match='model time budget'):
        execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    assert not client.calls


def test_retain_cannot_hide_cross_case_conflict(setup):
    store,run,units,_=setup;r=make_record(store,run,units[0]);run=install_records(store,run,[r])
    case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    case['mediation']['related_conflicts']=[{'revision_ids':[r.revision_id,'other-case']}]
    plan=plan_for(r);plan.actions[0].action='retain'
    outcomes,added,replaced=apply_plan(store,run,case,plan,MediationChecks(checks=[]),None)
    assert outcomes[0]['status']=='human_review' and outcomes[0]['human_question']
    assert not added and not replaced


def test_derived_trial_restarts_only_extraction_and_preserves_source(setup):
    store,run,units,_=setup
    def finish_preparation(r):
        r['stages']['role_selection']='completed'
        r['observations']=[{'observation_id':'old-extraction-not-reusable'}]
        r['status']='awaiting_human'
    store.mutate(run['run_id'],None,'fixture',finish_preparation)
    source=store.get('run',run['run_id'])
    child=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        start_from='elicitation',stakeholder_workflow='routed_mediated',discussion='automatic',
        output_form='needs',scoping='off',base_check=False,rationale='Fresh routed extraction.'))
    assert child['observations']==[] and child['role_runs']==[]
    assert child['evidence_ids']==source['evidence_ids']
    assert child['role_manifest']==source['role_manifest']
    assert child['stages']['elicitation']=='pending'
    assert child['elicitation_policy_version']==EXTRACTION_POLICY
    assert store.get('run',source['run_id'])==source


def test_local_mediator_ids_are_field_scoped_and_lossless():
    from requirement_reuse_service.workflow.stakeholder_workflow import translate_ids
    original={'revision_id':'long-parent','parent_revision_ids':['long-parent'],
        'evidence_links':[{'evidence_id':'long-evidence','quote':'long-parent N1 C1'}],
        'rationale':'long-parent','concern_id':'long-concern','action_id':'N1'}
    aliases={'long-parent':'N1','long-evidence':'E1','long-concern':'C1'}
    wire=translate_ids(original,aliases)
    assert wire['revision_id']=='N1' and wire['evidence_links'][0]['evidence_id']=='E1'
    assert wire['evidence_links'][0]['quote']=='long-parent N1 C1'
    assert wire['rationale']=='long-parent' and wire['action_id']=='N1'
    assert translate_ids(wire,{v:k for k,v in aliases.items()})==original
    assert translate_ids({'revision_id':'N999'},{'N1':'long-parent'})['revision_id']=='N999'


def mediator_fixture(setup):
    store,run,units,_=setup
    record=make_record(store,run,units[0]);run=install_records(store,run,[record])
    case=build_cases(store,run,[{'id':'consumer_discovery'}])[0]
    case['messages']=[{'message_id':'saved-m','role_id':'consumer_discovery','round':1,'finished':True,
        'body':'Supported need; mandatory wording remains unspecified.',
        'concerns':[{'concern_id':'saved-concern','revision_ids':[record.revision_id],
            'kind':'missing_evidence','statement':'No obligation evidence supplied.','evidence_ids':[]}]}]
    store.mutate(run['run_id'],None,'fixture',lambda r:r.update(deliberations=[case]))
    return store,run,record,case


def valid_local_plan():
    return MediationPlan.model_validate({'summary':'Retain provisionally with a review question.',
        'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':['N1'],
            'rationale':'Source supports the need but does not establish a mandatory obligation.',
            'human_question':'Does an applicable source establish an obligation?',
            'alternatives':['Keep the obligation unspecified','Supply a source-backed obligation']}],
        'concerns':[{'concern_id':'C1','status':'unresolved','action_ids':['A1'],
            'rationale':'Retained need awaits obligation clarification.'}]})


def test_invalid_v1_mediator_recovery_keeps_messages_work_and_budgets(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (execute_mediated_case,
        case_context,save,MEDIATION_POLICY)
    from requirement_reuse_service.workflow.storage import canonical
    from requirement_reuse_service.llm.step_models import model_identity
    store,run,record,case=mediator_fixture(setup)
    case['model_attempts']=6;case['output_tokens_reserved']=24000;case['model_seconds']=42
    store.mutate(run['run_id'],None,'fixture',lambda r:r.update(deliberations=[case]))
    class OnlyMediator(RoutingClient):
        def generate_structured(self,*,user,output_model,**kwargs):
            self.calls.append(output_model.__name__)
            assert output_model.__name__=='MediationDraft','No completed stakeholder/extraction work may repeat.'
            data=json.loads(user)
            assert data['required_accounting']=={'parent_ids':['N1'],'concern_ids':['C1'],'evidence_ids':['E1']}
            assert 'concerns' not in data['messages'][0]
            assert data['concern_groups'][0]['concern_id']=='C1'
            return valid_local_plan()
    client=OnlyMediator()
    payload={'context':case_context(store,case['frozen_requirements']),'messages':case['messages'],
        'related_conflicts':case['mediation']['related_conflicts']}
    old=plan_for(record,'retain').model_dump(mode='json')
    old['actions'].append(copy.deepcopy(old['actions'][0]))
    checkpoint={'input_hash':digest({'policy':POLICY,'payload':payload,'model':model_identity(client)}),
        'policy_version':POLICY,'plan':old,'validation_errors':['duplicate parent and missing concern']}
    save(store,run['run_id'],'mediation:'+case['case_id'],checkpoint)
    execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    done=store.get('run',run['run_id']);actual=done['deliberations'][0]
    assert client.calls==['MediationDraft']
    assert actual['messages']==case['messages'] and actual['model_attempts']==7
    assert actual['output_tokens_reserved']==28000 and actual['model_seconds']>=42
    assert actual['status']=='mediated' and actual['mediation']['mediation_policy_version']==MEDIATION_POLICY
    assert done['active_revision_ids']==[record.revision_id] and not done['decisions']
    assert done['machine_snapshot']==run['machine_snapshot']
    assert done['stakeholder_audit']['mediation:'+case['case_id']]==checkpoint
    assert any(k.startswith('mediation_history:') for k in done['stakeholder_audit'])
    n=len(client.calls)
    execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    assert len(client.calls)==n


def test_v2_correction_gets_rejected_answer_and_exhaustion_never_repeats(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import obtain_mediation_plan,case_context
    store,run,record,case=mediator_fixture(setup);client=RoutingClient();offered=[]
    def request(model,system,payload):
        offered.append(copy.deepcopy(payload));bad=valid_local_plan()
        bad.concerns[0].concern_id='C999'
        return bad
    context=case_context(store,case['frozen_requirements'])
    with pytest.raises(ValueError,match='bounded correction'):
        obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],{record.evidence_links[0].evidence_id},client,request)
    assert len(offered)==2 and offered[1]['previous_answer']['concerns'][0]['concern_id']=='C999'
    assert any('C999' in e and 'C1' in e for e in offered[1]['validation_errors'])
    with pytest.raises(ValueError,match='remains invalid'):
        obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],{record.evidence_links[0].evidence_id},client,request)
    assert len(offered)==2


def test_mediator_groups_only_exact_repeated_concerns_and_expands_audited_links(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_mediation_plan,
        case_context,MEDIATION_POLICY)
    store,run,record,case=mediator_fixture(setup)
    original=case['messages'][0]['concerns'][0]
    repeated={**copy.deepcopy(original),'concern_id':'saved-concern-copy'}
    distinct={**copy.deepcopy(original),'concern_id':'distinct-concern','statement':'A different statement needs review.'}
    case['messages'].append({'message_id':'saved-copy','role_id':'publisher_feasibility','round':1,
        'finished':True,'body':'The same concern and a different one.',
        'concerns':[repeated,distinct]})
    context=case_context(store,case['frozen_requirements']);allowed={record.evidence_links[0].evidence_id}
    offered=[]
    def request(model,system,payload):
        offered.append(copy.deepcopy(payload))
        assert len(payload['concern_groups'])==2
        assert payload['required_accounting']['concern_ids']==['C1','C2']
        assert [group['member_count'] for group in payload['concern_groups']]==[2,1]
        return model.model_validate({'actions':[{'action_id':'A1','action':'retain',
            'parent_revision_ids':['N1'],'rationale':'Retain pending evidence review.'}],
            'questions':[{'question_id':'Q1','revision_ids':['N1'],'concern_ids':['C1'],
                'question':'Does the source establish the obligation?','alternatives':['Yes','No'],
                'rationale':'The source evidence is incomplete.'}],
            'concerns':[{'concern_id':'C1','status':'unresolved','action_ids':['A1'],
                'question_ids':['Q1'],'rationale':'The repeated concern remains open.'},
                {'concern_id':'C2','status':'satisfied','action_ids':['A1'],
                'rationale':'The distinct concern is covered.'}],
            'summary':'One exact repeated concern was accounted once and expanded to both saved records.'})
    plan,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],allowed,RoutingClient(),request)
    assert policy==MEDIATION_POLICY and len(offered)==1
    assert {row.concern_id for row in plan.concerns}=={'saved-concern','saved-concern-copy','distinct-concern'}
    question=plan.questions[0]
    assert set(question.concern_ids)=={'saved-concern','saved-concern-copy'}
    assert all('Q1' in row.question_ids for row in plan.concerns if row.concern_id in question.concern_ids)
    assert not mediation_errors(plan,case['frozen_requirements'],case['messages'],allowed)
    saved=store.get_run(run['run_id'])['stakeholder_audit']['mediation_v5:'+case['case_id']]
    grouping=saved['concern_grouping']
    assert grouping['input_concern_count']==3 and grouping['group_count']==2
    assert grouping['groups'][0]['member_ids']==['saved-concern','saved-concern-copy']


def test_invalid_v3_mediator_checkpoint_migrates_to_grouped_v4_without_replaying_messages(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_mediation_plan,
        case_context,save,MEDIATION_POLICY,MEDIATION_V3_POLICY)
    from requirement_reuse_service.llm.step_models import model_identity
    store,run,record,case=mediator_fixture(setup)
    context=case_context(store,case['frozen_requirements']);client=RoutingClient()
    legacy_payload={'context':context,'messages':case['messages'],
        'related_conflicts':case['mediation']['related_conflicts']}
    aliases={'N1':record.revision_id,'C1':'saved-concern','E1':record.evidence_links[0].evidence_id}
    invalid=valid_local_plan().model_dump(mode='json');invalid['concerns']=[]
    checkpoint={'policy_version':MEDIATION_V3_POLICY,'input_hash':digest({'policy':MEDIATION_V3_POLICY,
        'payload':legacy_payload,'aliases':aliases,'model':model_identity(client)}),
        'aliases':aliases,'attempts':[{'wire_output':{'concerns':[]},'validation_errors':['missing concern']}],
        'plan':invalid,'validation_errors':['missing concern']}
    key='mediation_v3:'+case['case_id'];save(store,run['run_id'],key,checkpoint)
    calls=[]
    def request(model,system,payload):
        calls.append(model.__name__)
        return valid_local_plan()
    plan,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],
        {record.evidence_links[0].evidence_id},client,request)
    done=store.get_run(run['run_id'])
    assert policy==MEDIATION_POLICY and calls==['MediationDraft']
    assert not mediation_errors(plan,case['frozen_requirements'],case['messages'],{record.evidence_links[0].evidence_id})
    assert done['stakeholder_audit'][key]==checkpoint
    history=[value for name,value in done['stakeholder_audit'].items() if name.startswith('mediation_history:')]
    assert len(history)==1 and history[0]['from_policy']==MEDIATION_V3_POLICY
    assert history[0]['to_policy']==MEDIATION_POLICY
    assert history[0]['preserved_message_ids']==['saved-m']


def test_v4_defer_recovery_uses_only_its_unique_reciprocal_question(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_mediation_plan,
        case_context,save,group_mediation_concerns,MEDIATION_POLICY,MEDIATION_V4_POLICY)
    from requirement_reuse_service.llm.step_models import model_identity
    store,run,record,case=mediator_fixture(setup);client=RoutingClient()
    context=case_context(store,case['frozen_requirements']);allowed={record.evidence_links[0].evidence_id}
    compact,groups,group_messages,member_map,grouping=group_mediation_concerns(case['messages'])
    payload={'context':context,'messages':compact,'concern_groups':groups,
        'related_conflicts':case['mediation']['related_conflicts']}
    aliases={'N1':record.revision_id,'C1':'saved-concern','E1':record.evidence_links[0].evidence_id}
    first={'summary':'Defer the unresolved scope decision for human review.',
        'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':['N1'],
            'rationale':'The source supports the metadata but not its scope.',
            'evidence_links':[{'evidence_id':'E1','quote':record.evidence_links[0].quote,
                'quote_start':record.evidence_links[0].quote_start,'relation':'supports','component':'statement'}]}],
        'questions':[{'question_id':'Q1','revision_ids':['N1'],'concern_ids':['C1'],
            'question':'Which scope should this need cover?','alternatives':['Catalogue-level','System-level'],
            'rationale':'The source does not choose between the alternatives.'}],
        'concerns':[{'concern_id':'C1','status':'unresolved','action_ids':['A1'],'question_ids':['Q1'],
            'rationale':'The scope remains unresolved.'}]}
    second=copy.deepcopy(first);second['questions']=[]
    second['actions'][0]['human_question']=first['questions'][0]['question']
    second['actions'][0]['alternatives']=first['questions'][0]['alternatives']
    key='mediation_v4:'+case['case_id']
    checkpoint={'policy_version':MEDIATION_V4_POLICY,
        'input_hash':digest({'policy':MEDIATION_V4_POLICY,'payload':payload,'aliases':aliases,
            'concern_grouping':grouping,'model':model_identity(client)}),
        'aliases':aliases,'concern_grouping':grouping,
        'attempts':[{'wire_output':first,'validation_errors':['Deferral requires a precise human question and preserved alternatives.']},
            {'wire_output':second,'validation_errors':['Concern disposition names an unknown question.']}],
        'plan':MediationDraftForTest(second,aliases),
        'validation_errors':['Concern disposition names an unknown question.']}
    save(store,run['run_id'],key,checkpoint)
    def no_new_call(*args):
        raise AssertionError('A saved v4 answer is recoverable without another model call.')
    plan,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],allowed,client,no_new_call)
    done=store.get_run(run['run_id']);audit_rows=done['stakeholder_audit']
    assert policy==MEDIATION_POLICY
    assert plan.actions[0].human_question==first['questions'][0]['question']
    assert plan.actions[0].alternatives==first['questions'][0]['alternatives']
    assert not mediation_errors(plan,case['frozen_requirements'],case['messages'],allowed)
    assert audit_rows[key]==checkpoint
    migrated=audit_rows['mediation_v5:'+case['case_id']]
    assert migrated['migration']['from_policy']==MEDIATION_V4_POLICY
    assert migrated['migration']['selected_saved_attempt_index']==0
    assert migrated['migration']['repairs']==[{'kind':'defer_fields_copied_from_linked_question',
        'action_id':'A1','question_id':'Q1','fields':['human_question','alternatives']}]
    history=[value for name,value in audit_rows.items() if name.startswith('mediation_history:')]
    assert len(history)==1 and history[0]['previous_checkpoint']==checkpoint
    assert history[0]['preserved_message_ids']==['saved-m']


def MediationDraftForTest(wire,aliases):
    from requirement_reuse_service.workflow.stakeholder_workflow import MediationDraft,translate_ids
    return MediationDraft.model_validate(translate_ids(wire,aliases)).plan().model_dump(mode='json')


def test_live_defer_output_copies_a_unique_linked_question_and_audits_repair(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_mediation_plan,
        case_context,MEDIATION_POLICY)
    store,run,record,case=mediator_fixture(setup);allowed={record.evidence_links[0].evidence_id}
    answer={'summary':'Defer scope decision for human review.',
        'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':['N1'],
            'rationale':'The source does not establish the scope.'}],
        'questions':[{'question_id':'Q1','revision_ids':['N1'],'concern_ids':['C1'],
            'question':'Which scope should this need cover?','alternatives':['Catalogue-level','System-level'],
            'rationale':'The source leaves scope open.'}],
        'concerns':[{'concern_id':'C1','status':'unresolved','action_ids':['A1'],'question_ids':['Q1'],
            'rationale':'The scope remains unresolved.'}]}
    class DeferClient(RoutingClient):
        def generate_structured(self,*,output_model,**kwargs):
            self.calls.append(output_model.__name__)
            assert output_model.__name__=='MediationDraft'
            return output_model.model_validate(answer)
    client=DeferClient();context=case_context(store,case['frozen_requirements'])
    plan,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],allowed,
        client,lambda model,system,payload:client.generate_structured(system=system,user=payload,output_model=model))
    assert policy==MEDIATION_POLICY and client.calls==['MediationDraft']
    assert plan.actions[0].human_question==answer['questions'][0]['question']
    assert plan.actions[0].alternatives==answer['questions'][0]['alternatives']
    saved=store.get_run(run['run_id'])['stakeholder_audit']['mediation_v5:'+case['case_id']]
    assert saved['attempts'][0]['repairs'][0]['question_id']=='Q1'
    assert saved['attempts'][0]['wire_output']['actions'][0].get('human_question') is None


def test_defer_repair_refuses_ambiguous_linked_questions(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import repair_defer_from_linked_question
    store,run,record,case=mediator_fixture(setup)
    plan=MediationPlan.model_validate({'summary':'Needs human scope review.',
        'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':[record.revision_id],
            'rationale':'The scope remains unclear.'}],
        'questions':[{'question_id':qid,'revision_ids':[record.revision_id],'concern_ids':['saved-concern'],
            'question':question,'alternatives':['Narrow','Broad'],'rationale':'Source is unclear.'}
            for qid,question in [('Q1','Which narrow scope?'),('Q2','Which broad scope?')]],
        'concerns':[{'concern_id':'saved-concern','status':'unresolved','action_ids':['A1'],
            'question_ids':['Q1','Q2'],'rationale':'Two distinct choices remain.'}]})
    repaired,repairs=repair_defer_from_linked_question(plan)
    assert repairs==[] and repaired.actions[0].human_question is None
    assert any('Deferral requires' in error for error in mediation_errors(repaired,
        case['frozen_requirements'],case['messages'],{record.evidence_links[0].evidence_id}))


def test_v2_transport_interrupt_resumes_only_its_pending_correction(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import obtain_mediation_plan,case_context
    store,run,record,case=mediator_fixture(setup);client=RoutingClient();offered=[]
    def request(model,system,payload):
        offered.append(copy.deepcopy(payload))
        if len(offered)==2:raise ConnectionError('Synthetic interrupted correction')
        bad=valid_local_plan();bad.concerns=[];return bad
    context=case_context(store,case['frozen_requirements']);allowed={record.evidence_links[0].evidence_id}
    with pytest.raises(ConnectionError):
        obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],allowed,client,request)
    def recovery(model,system,payload):
        assert payload['previous_answer']['concerns']==[]
        return valid_local_plan()
    plan,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],allowed,client,recovery)
    assert plan.actions[0].parent_revision_ids==[record.revision_id]
    assert plan.concerns[0].concern_id=='saved-concern'
    assert not mediation_errors(plan,case['frozen_requirements'],case['messages'],allowed)


def test_accepted_v1_mediator_checkpoint_needs_no_new_plan_generation(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_mediation_plan,
        case_context,translate_ids,save)
    from requirement_reuse_service.llm.step_models import model_identity
    store,run,record,case=mediator_fixture(setup);client=RoutingClient()
    context=case_context(store,case['frozen_requirements'])
    payload={'context':context,'messages':case['messages'],'related_conflicts':case['mediation']['related_conflicts']}
    plan=translate_ids(valid_local_plan().model_dump(mode='json'),{'N1':record.revision_id,'C1':'saved-concern'})
    checkpoint={'policy_version':POLICY,'input_hash':digest({'policy':POLICY,'payload':payload,'model':model_identity(client)}),
        'plan':plan,'validation_errors':[]}
    save(store,run['run_id'],'mediation:'+case['case_id'],checkpoint)
    def no_call(*args):raise AssertionError('Accepted plan is immutable compatible completed work.')
    result,policy=obtain_mediation_plan(store,run['run_id'],case,context,case['messages'],
        {record.evidence_links[0].evidence_id},client,no_call)
    assert policy==POLICY and result.model_dump(mode='json')==plan


def separate_question_draft():
    from requirement_reuse_service.workflow.stakeholder_workflow import MediationDraft
    return MediationDraft.model_validate({'summary':'One retained need, two distinct review questions.',
        'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':['N1'],
            'rationale':'Keep the source-supported need provisionally; uncertainty does not invent an obligation.'}],
        'questions':[{'question_id':qid,'revision_ids':['N1'],'concern_ids':['C1'],
            'question':question,'alternatives':['Keep unspecified','Supply explicit source support'],
            'rationale':'The same supported need has distinct unresolved review dimensions.'}
            for qid,question in [('Q1','Which obligation is established by the source?'),
                                 ('Q2','Does the supplied source establish the narrower scope?')]],
        'concerns':[{'concern_id':'C1','status':'unresolved','action_ids':['A1'],
            'question_ids':['Q1','Q2'],'rationale':'Both review questions remain open.'}]})


def test_multiple_questions_do_not_duplicate_or_invent_need_dispositions(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import case_context,translate_ids
    store,run,record,case=mediator_fixture(setup)
    plan=MediationPlan.model_validate(translate_ids(separate_question_draft().plan().model_dump(mode='json'),
        {'N1':record.revision_id,'C1':'saved-concern'}))
    assert len(plan.actions)==1 and len(plan.questions)==2
    assert not mediation_errors(plan,case['frozen_requirements'],case['messages'],{record.evidence_links[0].evidence_id})
    outcomes,added,replaced=apply_plan(store,run,case,plan,MediationChecks(checks=[]),None)
    assert outcomes[0]['status']=='retained' and not added and not replaced
    assert [q.question_id for q in plan.questions]==['Q1','Q2']


def test_wire_contract_rejects_parentless_defer_and_parented_addition():
    from pydantic import ValidationError
    from requirement_reuse_service.workflow.stakeholder_workflow import MediationDraft
    data=separate_question_draft().model_dump(mode='json')
    data['actions'].append({'action_id':'bad','action':'defer','parent_revision_ids':[],
        'rationale':'A question is not a new need disposition.','human_question':'Which obligation?',
        'alternatives':['Unspecified','Explicit source']})
    with pytest.raises(ValidationError,match='parent_revision_ids'):
        MediationDraft.model_validate(data)
    data=separate_question_draft().model_dump(mode='json')
    data['additions']=[{'action_id':'bad-add','action':'add','parent_revision_ids':['N1'],'rationale':'Must not consume a current parent.'}]
    with pytest.raises(ValidationError,match='parent_revision_ids'):
        MediationDraft.model_validate(data)


def test_questions_require_current_needs_saved_concerns_and_reciprocal_links(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import translate_ids
    store,run,record,case=mediator_fixture(setup)
    plan=MediationPlan.model_validate(translate_ids(separate_question_draft().plan().model_dump(mode='json'),
        {'N1':record.revision_id,'C1':'saved-concern'}))
    plan.questions[0].revision_ids=['unknown-need']
    plan.questions[1].concern_ids=['unknown-concern']
    plan.concerns[0].question_ids=['Q1','unknown-question']
    errors=mediation_errors(plan,case['frozen_requirements'],case['messages'],set())
    assert any('current needs' in e for e in errors)
    assert any('saved concerns' in e for e in errors)
    assert any('reciprocal' in e for e in errors)
    assert any('unknown or repeated question' in e for e in errors)


def v2_checkpoint(store,run,record,case,client,plan):
    from requirement_reuse_service.workflow.stakeholder_workflow import case_context,MEDIATION_V2_POLICY
    from requirement_reuse_service.llm.step_models import model_identity
    payload={'context':case_context(store,case['frozen_requirements']),'messages':case['messages'],
        'related_conflicts':case['mediation']['related_conflicts']}
    aliases={'N1':record.revision_id,'C1':'saved-concern','E1':record.evidence_links[0].evidence_id}
    return {'policy_version':MEDIATION_V2_POLICY,'aliases':aliases,'attempts':[{},{}],
        'input_hash':digest({'policy':MEDIATION_V2_POLICY,'payload':payload,'aliases':aliases,'model':model_identity(client)}),
        'plan':plan,'validation_errors':mediation_errors(MediationPlan.model_validate(plan),case['frozen_requirements'],case['messages'],{aliases['E1']})}


def test_v2_parentless_question_failure_recovers_without_replaying_work(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import execute_mediated_case,save,translate_ids,MEDIATION_POLICY
    store,run,record,case=mediator_fixture(setup)
    case.update(model_attempts=6,output_tokens_reserved=24000,model_seconds=22)
    completed=copy.deepcopy(case);completed.update(case_id='already-completed-case',status='mediated')
    store.mutate(run['run_id'],None,'fixture',lambda r:r.update(deliberations=[completed,case]))
    class OnlyDraft(RoutingClient):
        def generate_structured(self,*,output_model,**kwargs):
            self.calls.append(output_model.__name__)
            assert output_model.__name__=='MediationDraft'
            return separate_question_draft()
    client=OnlyDraft()
    bad=valid_local_plan().model_dump(mode='json')
    bad['actions'].append({'action_id':'A2','action':'defer','parent_revision_ids':[],
        'rationale':'Separate scope question.','human_question':'What scope applies?',
        'alternatives':['Narrow','Broad']})
    bad=translate_ids(bad,{'N1':record.revision_id,'C1':'saved-concern'})
    checkpoint=v2_checkpoint(store,run,record,case,client,bad)
    assert checkpoint['validation_errors']==['Non-addition requires a current parent.']
    key='mediation_v2:'+case['case_id'];save(store,run['run_id'],key,checkpoint)
    execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    done=store.get('run',run['run_id']);actual=done['deliberations'][1]
    assert done['deliberations'][0]==completed
    assert done['stakeholder_audit'][key]==checkpoint
    history=[v for k,v in done['stakeholder_audit'].items() if k.startswith('mediation_history:')]
    assert history[0]['from_policy']=='rq1-evidence-mediation-v2' and history[0]['to_policy']==MEDIATION_POLICY
    assert actual['messages']==case['messages'] and actual['model_attempts']==7
    assert actual['output_tokens_reserved']==28000 and actual['model_seconds']>=22
    assert actual['status']=='mediated' and len(actual['mediation']['human_questions'])==2
    assert actual['mediation']['human_questions'][0]['revision_ids']==[record.revision_id]
    assert actual['mediation']['human_questions'][0]['concern_ids']==['saved-concern']
    assert actual['mediation']['human_accepted'] is False and not done['decisions']
    assert done['active_revision_ids']==[record.revision_id]
    assert done['machine_snapshot']==run['machine_snapshot']
    execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    assert client.calls==['MediationDraft']
    trace=trace_run(store,run['run_id'])
    assert 'Q1' in json.dumps(trace) and 'saved-concern' in json.dumps(trace)


def test_accepted_v2_plan_and_critic_keep_original_hash_and_need_no_calls(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import execute_mediated_case,save,translate_ids,case_context,MEDIATION_V2_POLICY
    from requirement_reuse_service.llm.step_models import model_identity
    store,run,record,case=mediator_fixture(setup);client=RoutingClient()
    plan=translate_ids(valid_local_plan().model_dump(mode='json'),{'N1':record.revision_id,'C1':'saved-concern'})
    plan.pop('questions')
    for d in plan['concerns']:d.pop('question_ids')
    old=v2_checkpoint(store,run,record,case,client,plan)
    assert old['validation_errors']==[]
    save(store,run['run_id'],'mediation_v2:'+case['case_id'],old)
    check_input={'context':case_context(store,case['frozen_requirements']),'plan':plan,'messages':case['messages']}
    checks={'input_hash':digest({'policy':MEDIATION_V2_POLICY,'payload':check_input,'model':model_identity(client)}),
        'output':{'checks':[]}}
    save(store,run['run_id'],'mediation_check:'+case['case_id'],checks)
    execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    done=store.get('run',run['run_id'])
    assert not client.calls and done['stakeholder_audit']['mediation_check:'+case['case_id']]==checks
    assert done['deliberations'][0]['mediation']['mediation_policy_version']==MEDIATION_V2_POLICY


def test_stakeholder_aliases_and_rejected_legacy_call_are_audited(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import (obtain_stakeholder_review,
        case_context,StakeholderReview,REVIEW_POLICY)
    from requirement_reuse_service.workflow.storage import canonical
    store,run,record,case=mediator_fixture(setup);case.update(messages=[],model_attempts=1,output_tokens_reserved=4000)
    store.mutate(run['run_id'],None,'fixture',lambda r:r.update(deliberations=[case]))
    client=RoutingClient();role={'id':'consumer_discovery'};context=case_context(store,case['frozen_requirements'])
    payload={'policy':POLICY,'role':role,'round':1,'context':context,'related_conflicts':[],'messages':[]}
    bad={'summary':'Unsupported obligation remains a question.','finished':True,
        'concerns':[{'revision_ids':['mistyped-current-parent'],'kind':'missing_evidence','statement':'No obligation evidence.'}]}
    call={'call_id':'legacy-rejected','output_contract':'StakeholderReview','context_hash':digest(canonical(payload)),
        'provider':client.describe(),'output':bad}
    store.append_run_part(run['run_id'],'model_calls',call)
    offered=[]
    def request(model,system,data):
        offered.append(data)
        assert data['allowed_references']=={'need_ids':['N1'],'evidence_ids':['E1']}
        assert data['context']['needs'][0]['revision_id']=='N1'
        return model.model_validate({'summary':'Review the current source-supported need.','finished':True,
            'concerns':[{'revision_ids':['N1'],'kind':'support','statement':'Exact supplied source supports it.','evidence_ids':['E1']}]})
    answer=obtain_stakeholder_review(store,run['run_id'],case,context,[],{record.evidence_links[0].evidence_id},role,1,client,request)
    assert answer.concerns[0].revision_ids==[record.revision_id]
    assert answer.concerns[0].evidence_ids==[record.evidence_links[0].evidence_id]
    done=store.get('run',run['run_id']);history=done['stakeholder_audit']['stakeholder_review_history:legacy-rejected']
    assert history['to_policy']==REVIEW_POLICY and history['output']==bad
    assert history['validation_errors'][0]['unknown_need_ids']==['mistyped-current-parent']
    assert done['model_calls']==[call] and done['machine_snapshot']==run['machine_snapshot']
    assert done['deliberations'][0]['model_attempts']==1 # Only the real request callback charges budgets.
    again=obtain_stakeholder_review(store,run['run_id'],case,context,[],{record.evidence_links[0].evidence_id},role,1,client,request)
    assert again==answer and len(offered)==1 # Recovery between validated output and message commit.


def test_stakeholder_bad_ids_get_one_correction_then_remain_blocked(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import obtain_stakeholder_review,case_context
    store,run,record,case=mediator_fixture(setup);case.update(messages=[],model_attempts=0)
    context=case_context(store,case['frozen_requirements']);offered=[]
    def request(model,system,payload):
        offered.append(copy.deepcopy(payload))
        return model.model_validate({'summary':'Invalid references must remain rejected.','finished':True,
            'concerns':[{'revision_ids':['N999'],'kind':'support','statement':'Test invalid references.','evidence_ids':['E999']}]})
    args=(store,run['run_id'],case,context,[],{record.evidence_links[0].evidence_id},{'id':'consumer_discovery'},1,RoutingClient(),request)
    with pytest.raises(ValueError,match='references invalid after bounded correction'):
        obtain_stakeholder_review(*args)
    assert len(offered)==2
    assert offered[1]['previous_answer']['concerns'][0]['revision_ids']==['N999']
    assert offered[1]['validation_errors']==[{'concern_index':0,'unknown_need_ids':['N999'],'unknown_evidence_ids':['E999']}]
    with pytest.raises(ValueError,match='remains invalid'):
        obtain_stakeholder_review(*args)
    assert len(offered)==2
    saved=next(v for k,v in store.get('run',run['run_id'])['stakeholder_audit'].items() if k.startswith('stakeholder_review_v2:'))
    assert len(saved['attempts'])==2 and saved['output']['concerns'][0]['revision_ids']==['N999']


def test_stakeholder_transport_interrupt_resumes_only_pending_correction(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import obtain_stakeholder_review,case_context
    store,run,record,case=mediator_fixture(setup);case.update(messages=[],model_attempts=0)
    context=case_context(store,case['frozen_requirements']);offered=[]
    def request(model,system,payload):
        offered.append(copy.deepcopy(payload))
        if len(offered)==2:raise ConnectionError('Synthetic transport interruption')
        return model.model_validate({'summary':'Rejected reference preserved.','finished':True,
            'concerns':[{'revision_ids':['N999'],'kind':'missing_evidence','statement':'Uncertain source support.'}]})
    args=(store,run['run_id'],case,context,[],{record.evidence_links[0].evidence_id},{'id':'consumer_discovery'},1,RoutingClient())
    with pytest.raises(ConnectionError):obtain_stakeholder_review(*args,request)
    recovered=[]
    def correction(model,system,payload):
        recovered.append(payload)
        assert payload['previous_answer']['concerns'][0]['revision_ids']==['N999']
        return model.model_validate({'summary':'Current need retained for review.','finished':True,
            'concerns':[{'revision_ids':['N1'],'kind':'missing_evidence','statement':'Uncertain source support.'}]})
    answer=obtain_stakeholder_review(*args,correction)
    assert len(recovered)==1 and answer.concerns[0].revision_ids==[record.revision_id]


def test_stakeholder_checkpoint_rejects_changed_input_and_model(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import obtain_stakeholder_review,case_context
    store,run,record,case=mediator_fixture(setup);case.update(messages=[],model_attempts=0)
    context=case_context(store,case['frozen_requirements'])
    def request(model,system,payload):return model.model_validate({'summary':'No additional concerns.','finished':True,'concerns':[]})
    args=(store,run['run_id'],case,context,[],{record.evidence_links[0].evidence_id},{'id':'consumer_discovery'},1)
    obtain_stakeholder_review(*args,RoutingClient(),request)
    changed=copy.deepcopy(context);changed['needs'][0]['scope']='Changed scope'
    with pytest.raises(ValueError,match='changed its context'):
        obtain_stakeholder_review(store,run['run_id'],case,changed,[],args[5],args[6],1,RoutingClient(),request)
    class OtherModel(RoutingClient):
        def describe(self):return {'provider':'offline','model':'different-model'}
    with pytest.raises(ValueError,match='changed its context'):
        obtain_stakeholder_review(*args,OtherModel(),request)


def test_stakeholder_reference_recovery_preserves_case_budgets_completed_cases_and_messages(setup):
    from requirement_reuse_service.workflow.stakeholder_workflow import execute_mediated_case,REVIEW_POLICY
    store,run,record,case=mediator_fixture(setup);case.update(messages=[],model_attempts=1,output_tokens_reserved=4000,model_seconds=1)
    completed=copy.deepcopy(case);completed.update(case_id='finished-case',status='mediated',messages=[{'message_id':'unchanged-message'}])
    store.mutate(run['run_id'],None,'fixture',lambda r:r.update(deliberations=[completed,case]))
    class ReviewAndPlan(RoutingClient):
        def generate_structured(self,*,output_model,**kwargs):
            self.calls.append(output_model.__name__)
            if output_model.__name__=='StakeholderReview':return output_model.model_validate({'summary':'No new concerns.','finished':True,'concerns':[]})
            assert output_model.__name__=='MediationDraft'
            return output_model.model_validate({'summary':'Retained provisionally.','actions':[{'action_id':'A1','action':'retain',
                'parent_revision_ids':['N1'],'rationale':'Unchanged source-supported need.'}],'concerns':[]})
    client=ReviewAndPlan();execute_mediated_case(store,run['run_id'],case['case_id'],client,[{'id':'consumer_discovery'}])
    done=store.get('run',run['run_id']);actual=done['deliberations'][1]
    assert done['deliberations'][0]==completed and actual['status']=='mediated'
    assert actual['model_attempts']==3 and actual['output_tokens_reserved']==12000 and actual['model_seconds']>=1
    assert actual['messages'][0]['policy_version']==REVIEW_POLICY
    assert done['machine_snapshot']==run['machine_snapshot'] and done['active_revision_ids']==run['active_revision_ids']
    assert not done['decisions'] and client.calls==['StakeholderReview','MediationDraft']
