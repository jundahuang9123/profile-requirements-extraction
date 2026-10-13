"""Uncited hypotheses remain auditable but never become machine review candidates."""
from fastapi.testclient import TestClient
from test_resume_discussions import setup
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import WorkflowRun
from requirement_reuse_service.workflow.evaluation import workflow_metrics


def extraction_only(setup):
    store, run, client = setup
    store.mutate(run['run_id'], None, 'test_stepwise', lambda r: r['request'].update(execution_mode='stepwise'))
    engine.execute_run(store, run['run_id'], client)
    store.mutate(run['run_id'], None, 'test_next', lambda r: r.update(status='created'))
    engine.execute_run(store, run['run_id'], client)
    return store, store.get('run', run['run_id']), client


def test_uncited_observations_are_audited_and_never_assessed_or_reviewed(setup):
    store, run, client = extraction_only(setup)
    def unlinked(r):
        for o in r['observations']:
            o['evidence_links'] = []
        r['request'].update(execution_mode='automatic', discussion='on_request')
        r['status'] = 'created'
    store.mutate(run['run_id'], None, 'test_uncited', unlinked)
    mark = len(client.calls)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human'
    assert saved['requirements'] == [] and saved['active_revision_ids'] == [] and saved['deliberations'] == []
    assert len(saved['set_aside_observations']) == len(saved['observations'])
    assert client.count('Qualification', mark) == client.count('Turn', mark) == 0
    assert saved['machine_snapshot']['set_aside_observations'] == saved['set_aside_observations']
    metrics = workflow_metrics(saved)
    assert metrics['set_aside']['count'] == len(saved['observations'])
    assert set(metrics['set_aside']['by_role']) == {r['role_id'] for r in saved['role_runs']}
    api = TestClient(app)
    assert api.get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/normalization').json()['results']['set_aside_observations'] == saved['set_aside_observations']
    assert api.get(f'/api/rq1/v2/runs/{run["run_id"]}/export').json()['run']['set_aside_observations'] == saved['set_aside_observations']


def test_context_only_links_stay_candidates_and_fail_the_source_gate(setup):
    store, run, client = extraction_only(setup)
    def contextual(r):
        for o in r['observations']:
            for link in o['evidence_links']:
                link['relation'] = 'contextualizes'
        r['request'].update(execution_mode='automatic', discussion='on_request')
        r['status'] = 'created'
    store.mutate(run['run_id'], None, 'test_contextual', contextual)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['set_aside_observations'] == []
    assert len(saved['requirements']) == len(saved['observations'])
    assert all(r['verification']['status'] == 'fail' for r in saved['requirements'])


def test_legacy_none_keeps_uncited_candidates(setup):
    store, run, client = extraction_only(setup)
    def legacy(r):
        r.pop('normalization_policy_version', None)
        for o in r['observations']:
            o['evidence_links'] = []
        r['request'].update(execution_mode='automatic', discussion='on_request')
        r['status'] = 'created'
    store.mutate(run['run_id'], None, 'test_legacy', legacy)
    loaded = WorkflowRun.model_validate(store.get('run', run['run_id']))
    assert loaded.normalization_policy_version is None
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert len(saved['requirements']) == len(saved['observations'])
    assert saved['set_aside_observations'] == []
