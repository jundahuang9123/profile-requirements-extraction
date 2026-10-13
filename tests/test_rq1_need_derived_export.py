from copy import deepcopy
import json
from fastapi.testclient import TestClient
from test_resume_discussions import setup
from test_rq1_need_assessment import FullNeedsClient
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import DeriveRequest, RestoreRequest, Observation
from requirement_reuse_service.workflow.evaluation import workflow_metrics


def derived(setup):
    store,source,client=setup
    engine.execute_run(store,source['run_id'],client)
    store.mutate(source['run_id'],None,'historical-test',lambda r:r.update(elicitation_policy_version='rq1-independent-elicitation-v2.11'))
    source=store.get('run',source['run_id']);before=deepcopy(source)
    trial=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        base_profile_id=None,scoping='off',discussion='on_request',rationale='Offline needs trial from frozen legacy extraction.'))
    client=FullNeedsClient();engine.execute_run(store,trial['run_id'],client)
    saved=store.get('run',trial['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert all(name!='NeedSpanElicitationResult' for name,_ in client.calls)
    assert store.get('run',source['run_id'])==before
    assert saved['observations']==source['observations']
    return store,saved,client


def test_legacy_extraction_reused_with_new_needs_and_full_export(setup):
    store,run,client=derived(setup)
    export=needs.needs_export(store,run['run_id'])
    assert len(export['needs'])==1 and export['needs'][0]['need_statement']
    assert len(export['needs'][0]['members'])==6
    assert export['needs'][0]['rank']==1
    assert all(p in run['stage_results']['consolidation']['need_steps'] for p in ('source_check','grouping','need_statement','classification','scoping','assessment','ranking'))
    assert run['machine_snapshot']['needs_policies']==run['needs_policies']
    metrics=workflow_metrics(run)['needs']
    assert metrics['counts']['proposals']==6 and metrics['counts']['kept_needs']==1
    assert metrics['calls_by_step']['assessment']['calls']==1
    assert metrics['counts']['needs']==1
    with TestClient(app) as api:
        response=api.get(f'/api/rq1/v2/runs/{run["run_id"]}/needs?download=true')
    assert response.status_code==200 and 'needs.json' in response.headers['content-disposition']


def test_restore_is_audited_without_acceptance_or_frozen_output_change(setup):
    store,run,client=derived(setup);record=next(r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids'])
    original=deepcopy(run['machine_snapshot'])
    store.mutate(run['run_id'],None,'scripted-aside-test',lambda r:r.update(active_revision_ids=[],set_aside_observations=[{
        'observation_id':record['observation_ids'][0],'role_id':record['contributing_roles'][0],'reason':'no_use_case',
        'revision_id':record['revision_id'],'need_id':record['requirement_id'],'restored':False}]))
    run=store.get('run',run['run_id'])
    result=needs.restore_need(store,run['run_id'],RestoreRequest(expected_version=run['version'],idempotency_key='restore-test',
        observation_id=record['observation_ids'][0],reason='no_use_case',need_id=record['requirement_id'],rationale='Declared quality goal needs review.'),'test-reviewer')
    restored=result['run'];active=next(r for r in restored['requirements'] if r['revision_id'] in restored['active_revision_ids'])
    assert active['lifecycle_state']=='awaiting_human' and active['qualification'] is None
    assert restored['machine_snapshot']==original
    assert restored['decisions'][-1]['action']=='restore' and restored['set_aside_observations'][0]['restored']


def test_large_group_checks_every_member_with_bounded_followup(setup):
    store,run,candidates=need_inputs(setup)
    members=[]
    for index in range(81):
        observation=Observation(observation_id=f'large-{index}',role_id='test-role',statement='Datasets must include a title.',
            intent=candidates[0].normalized_intent,evidence_links=candidates[0].evidence_links)
        r=engine.record_from_observation(run['run_id'],observation);r.verification=engine.verify(store,r,run['evidence_ids']);members.append(r)
    class MemberClient(NeedsClient):
        def generate_structured(self,**kwargs):
            if kwargs['output_model'].__name__=='NeedMembership':
                data=json.loads(kwargs['user']);self.calls.append(('NeedMembership',data))
                return kwargs['output_model'].model_validate({'checks':[{'member_id':m,'expresses_need':True,
                    'rationale':'Same source-supported title need.'} for m in data['members']]})
            return super().generate_structured(**kwargs)
    client=MemberClient();out,events=needs.write_needs(store,run,[members],client,None)
    assert len(out)==1 and len(out[0].parent_revision_ids)==81
    assert sum(name=='NeedMembership' for name,_ in client.calls)==2
    assert sum(len(data['members']) for name,data in client.calls if name=='NeedMembership')==61


def test_source_failed_member_stays_blocked_and_does_not_contaminate_passing_need(setup):
    store,run,candidates=need_inputs(setup)
    bad=candidates[1].model_copy(deep=True)
    bad.evidence_links[0].quote='Invented quotation'
    # Regenerate its identity so this checks original-source failure, not only hash tampering.
    observation=Observation(observation_id='failed-source-test',role_id='test-role',statement=bad.raw_statement,
        intent=bad.normalized_intent,evidence_links=bad.evidence_links)
    bad=engine.record_from_observation(run['run_id'],observation);bad.verification=engine.verify(store,bad,run['evidence_ids'])
    run['request']['base_profile_id']=None;run['base_profile_id']=None;run['request']['scoping']='off'
    active,events,_=needs.process_needs(store,run,[candidates[0],bad],FullNeedsClient(),None)
    assert len(active)==2
    blocked=next(n for n in active if bad.revision_id in n.parent_revision_ids)
    assert blocked.lifecycle_state=='blocked_evidence' and blocked.verification['status']=='fail'
    passing=next(n for n in active if candidates[0].revision_id in n.parent_revision_ids)
    assert passing.verification['status']=='pass' and bad.revision_id not in passing.parent_revision_ids


def test_use_case_scoping_with_no_declared_tasks_refuses_before_processing(setup):
    import pytest
    from requirement_reuse_service.workflow.models import RunRequest
    store,original,_=setup
    with pytest.raises(ValueError,match='requires declared tasks'):
        engine.new_run(store,RunRequest(snapshot_id=original['snapshot_id'],scoping='use_cases',strategy='multi_agent'))
