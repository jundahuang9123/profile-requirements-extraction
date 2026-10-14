"""Role selection failures must remain inspectable without appearing active."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import api, engine
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def pending(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(
        name='needs.md', content='Transport operators need to discover datasets.'), source_role='stakeholder_need'))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = engine.new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='mock', role_selection='automatic'))
    return store, run, TestClient(app)


def fail_selection(store, run, monkeypatch):
    def broken_selector(store, run, client):
        assert store.get('run', run['run_id'])['stages']['role_selection'] == 'running'
        raise ValueError('Quotation not found in cited passage.')
    monkeypatch.setattr(engine, 'select_roles', broken_selector)
    engine.execute_run(store, run['run_id'])
    return store.get('run', run['run_id'])


def test_failed_selection_releases_worker_and_has_terminal_stage(pending, monkeypatch):
    store, run, _ = pending
    result = fail_selection(store, run, monkeypatch)
    assert result['status'] == result['stages']['role_selection'] == result['role_manifest']['status'] == 'failed'
    assert result['role_manifest']['last_error'] == 'Quotation not found in cited passage.'
    assert result['stages']['elicitation'] == 'pending'
    assert result['worker_id'] is None
    assert not result['model_calls']


def test_cancel_marks_incomplete_selection_cancelled(pending):
    store, run, client = pending
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/cancel', json={'expected_version': run['version']})
    assert response.status_code == 200
    result = store.get('run', run['run_id'])
    assert result['role_manifest']['status'] == result['stages']['role_selection'] == 'cancelled'


def test_resume_keeps_old_failure_in_history_and_clears_current_error(pending, monkeypatch):
    store, run, client = pending
    failed = fail_selection(store, run, monkeypatch)
    monkeypatch.setattr(api, 'execute_run', lambda *args: None)
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': failed['version']})
    assert response.status_code == 202, response.text
    resumed = store.get('run', run['run_id'])
    assert resumed['diagnostics'] == []
    assert resumed['role_manifest']['status'] == resumed['stages']['role_selection'] == 'pending'
    history = resumed['attempt_history'][-1]
    assert history['diagnostics'] == failed['diagnostics']
    assert history['role_manifest']['status'] == history['stages']['role_selection'] == 'failed'
    assert history['role_manifest']['last_error'] == 'Quotation not found in cited passage.'


def test_legacy_incomplete_policy_rejected_before_provider_configuration(pending, monkeypatch):
    store, run, client = pending
    def legacy(r):
        r['status'] = 'failed'
        r['role_manifest']['policy_version'] = 'rq1-stakeholder-selection-v1'
    failed = store.mutate(run['run_id'], None, 'test_legacy', legacy)['run']
    def forbidden(*args):
        pytest.fail('Provider must not be configured for an incompatible resume.')
    monkeypatch.setattr(api, 'configured_client', forbidden)
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': failed['version']})
    assert response.status_code == 422
    assert 'new run' in response.json()['detail'].lower()
    assert store.get('run', run['run_id'])['version'] == failed['version']


@pytest.mark.parametrize('stale_assessment', [False, True])
def test_assessment_restart_preserves_exact_revision_checkpoints(tmp_path, monkeypatch, stale_assessment):
    from requirement_reuse_service.llm.client import LLMError, MockLLMClient
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'assessment.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md',
        content='Each dataset must publish its title.\nEach dataset must specify its language.'), source_role='stakeholder_need'))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = engine.new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='rules'))
    attempts = []
    def assessment(system, user):
        import json
        record = json.loads(user)['requirement']
        attempts.append(record['revision_id'])
        if len(attempts) == 2:
            raise LLMError('Simulated provider interruption on second assessment')
        return {'support': 'explicit', 'rationale': 'Fixture assessment', 'findings': [],
                'assessor': 'server-overrides', 'revision_hash': 'server-overrides'}
    client = MockLLMClient(assessment)
    engine.execute_run(store, run['run_id'], client)
    failed = store.get('run', run['run_id'])
    assert failed['status'] == 'failed' and failed['stages']['verification'] == 'failed'
    assert failed['worker_id'] is None
    completed = next(r for r in failed['requirements'] if r['qualification'])
    # A resume must preserve a measured old-policy qualification, not relabel
    # it with today's defaults or charge for another generation.
    def old_policy(r):
        item = next(x for x in r['requirements'] if x['revision_id'] == completed['revision_id'])
        item['qualification']['assessor'] = 'rq1-support-quality-v2.1/fixture-model'
    store.mutate(run['run_id'], None, 'fixture_old_policy', old_policy)
    completed = next(r for r in store.get('run', run['run_id'])['requirements'] if r['qualification'])
    original_qualification = completed['qualification'].copy()
    assert completed['revision_id'] == attempts[0]
    assert any(e['event_type'] == 'requirement_assessed' for e in store.events(run['run_id']))
    if stale_assessment:
        def invalidate(r):
            item = next(x for x in r['requirements'] if x['revision_id'] == completed['revision_id'])
            item['qualification']['revision_hash'] = 'stale-revision'
        store.mutate(run['run_id'], None, 'fixture_stale', invalidate)
    engine.execute_run(Store(str(tmp_path / 'assessment.sqlite3')), run['run_id'], client)
    result = store.get('run', run['run_id'])
    assert result['status'] == 'awaiting_human'
    assert result['stages']['verification'] == 'completed' and result['worker_id'] is None
    assert len(attempts) == (4 if stale_assessment else 3)
    assert attempts.count(completed['revision_id']) == (2 if stale_assessment else 1)
    if not stale_assessment:
        resumed = next(r for r in result['requirements'] if r['revision_id'] == completed['revision_id'])
        assert resumed['qualification'] == original_qualification
