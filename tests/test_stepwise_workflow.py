"""Exercise stage pauses, immutable results and safe continuation without inference."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.engine import new_run, freeze_snapshot, execute_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import SourceRequest, SnapshotRequest, RunRequest
from requirement_reuse_service.workflow.storage import Store

@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'stepwise.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md',
        content='Each dataset must specify its title.'), source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='rules', execution_mode='stepwise'))
    return store, run, source, snapshot, TestClient(app)


def test_human_mode_pauses_once_per_stage_and_retains_earlier_results(workflow):
    store, run, _, _, client = workflow
    execute_run(store, run['run_id'])
    processing = ['role_selection', 'elicitation', 'normalization', 'verification', 'consolidation']
    for index, stage in enumerate(processing):
        current = store.get('run', run['run_id'])
        assert current['status'] == 'paused' and current['worker_id'] is None
        assert current['stages'][stage] == 'completed'
        assert all(current['stages'][later] == 'pending' for later in processing[index + 1:])
        exported = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/{stage}').json()
        assert exported['snapshot_kind'] == 'stage_checkpoint'
        assert exported['status'] == 'completed'
        response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/continue', json={'expected_version': current['version']})
        assert response.status_code == 202, response.text
    result = store.get('run', run['run_id'])
    assert result['status'] == 'awaiting_human' and result['worker_id'] is None
    original = result['stage_results']['normalization']['requirements'][0]
    assert original['qualification'] is None
    verified = result['stage_results']['verification']['requirements'][0]
    assert verified['qualification']['support'] == 'uncertain'
    # Later human assessments must not rewrite the stage checkpoint.
    record = result['requirements'][0]
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/assessments', json={
        'expected_version': result['version'], 'idempotency_key': 'human-assessment',
        'revision_id': record['revision_id'], 'qualification': {'support': 'explicit',
            'rationale': 'Human checked the source.', 'findings': [], 'assessor': 'ignored',
            'revision_hash': record['content_hash']}})
    assert response.status_code == 200, response.text
    historical = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/verification').json()
    assert historical['results']['requirements'][0]['qualification']['support'] == 'uncertain'
    assert store.get('run', run['run_id'])['requirements'][0]['qualification']['support'] == 'explicit'


def test_continue_rejects_wrong_state_and_stale_version(workflow):
    store, run, _, _, client = workflow
    path = f'/api/rq1/v2/runs/{run["run_id"]}/continue'
    assert client.post(path, json={'expected_version': run['version']}).status_code == 422
    execute_run(store, run['run_id'])
    assert client.post(path, json={'expected_version': run['version']}).status_code == 409
    assert store.get('run', run['run_id'])['status'] == 'paused'


def test_source_evidence_and_stage_downloads_use_saved_artifacts(workflow):
    _, run, source, snapshot, client = workflow
    evidence = client.get(f'/api/rq1/v2/sources/{source["source_version_id"]}/evidence').json()
    assert {item['evidence_id'] for item in evidence} == set(snapshot['evidence_ids'])
    assert client.get(f'/api/rq1/v2/snapshots/{snapshot["snapshot_id"]}').json() == snapshot
    result = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/acquisition?download=true')
    assert result.status_code == 200 and 'attachment' in result.headers['content-disposition']
    assert result.json()['results']['snapshot']['source_version_ids'] == snapshot['source_version_ids']
    assert client.get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/invented').status_code == 422
