"""A derived trial reuses frozen extraction, never a source run's mutable review."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from test_resume_discussions import setup
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.engine import derive_run, execute_run
from requirement_reuse_service.workflow.models import DeriveRequest
from requirement_reuse_service.workflow.storage import ConflictError, digest


def completed(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    return store, store.get('run', run['run_id']), client


def test_derive_reuses_extraction_and_identical_assessments_and_preserves_source(setup):
    store, source, client = completed(setup)
    before = deepcopy(source)
    mark = len(client.calls)
    run = derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'], rationale='Compare downstream settings.'))
    assert run['model_calls'] == []
    assert run['derived_from']['observations_hash'] == digest(source['observations'])
    assert run['derived_from']['role_runs_hash'] == digest(source['role_runs'])
    assert run['catalogues'] == source['catalogues']
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human'
    assert client.count('SpanElicitationResult', mark) == 0
    assert client.count('Qualification', mark) == 0
    assert saved['metrics']['assessments_reused'] == len(source['observations'])
    assert store.get('run', source['run_id']) == before
    stage = TestClient(app).get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/elicitation').json()
    assert stage['results']['observations'] == source['observations']
    assert stage['results']['catalogues'] == source['catalogues']


def test_changed_hash_or_old_assessment_is_not_reused(setup):
    store, source, client = completed(setup)
    def change(run):
        for record in run['requirements']:
            record['qualification']['assessor'] = 'old-assessment-policy/test'
    store.mutate(source['run_id'], None, 'test_old_policy', change)
    source = store.get('run', source['run_id'])
    run = derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'], rationale='Policy check.'))
    mark = len(client.calls)
    execute_run(store, run['run_id'], client)
    assert client.count('Qualification', mark) > 0
    assert client.count('SpanElicitationResult', mark) == 0
    item = source['requirements'][0]
    assert engine.reusable_qualification(item, 'changed-content') is None


def test_derived_run_keeps_old_extraction_policy_but_refuses_extraction_reset(setup):
    store, source, client = completed(setup)
    store.mutate(source['run_id'], None, 'test_old_extraction', lambda r: r.update(elicitation_policy_version='legacy-policy'))
    source = store.get('run', source['run_id'])
    run = derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'], rationale='Reuse legacy extraction.'))
    assert run['elicitation_policy_version'] == 'legacy-policy'
    engine.ensure_elicitation_resumable(run)
    run['stages']['elicitation'] = 'pending'
    with pytest.raises(ValueError, match='Create a new run'):
        engine.ensure_elicitation_resumable(run)
    store.mutate(run['run_id'], None, 'test_reset', lambda r: r.update(status='failed', stages=run['stages']))
    response = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': store.get('run', run['run_id'])['version']})
    assert response.status_code == 422


def test_derive_rejects_partial_extraction_and_stale_source(setup):
    store, source, _ = completed(setup)
    with pytest.raises(ConflictError):
        derive_run(store, source['run_id'], DeriveRequest(expected_version=1, rationale='Stale.'))
    store.mutate(source['run_id'], None, 'test_partial', lambda r: r['role_runs'][0].update(status='failed'))
    source = store.get('run', source['run_id'])
    with pytest.raises(ValueError, match='complete extraction'):
        derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'], rationale='Partial.'))


def test_derive_endpoint_creates_separate_saved_run(setup):
    store, source, client = completed(setup)
    response = TestClient(app).post(f'/api/rq1/v2/runs/{source["run_id"]}/derive', json={'expected_version':source['version'], 'rationale':'API trial.'})
    assert response.status_code == 202, response.text
    assert response.json()['run_id'] != source['run_id']
    assert store.get('run', source['run_id']) == source
