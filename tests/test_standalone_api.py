"""Exercise the migrated API boundary without the VPE proxy or model credentials."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from fastapi.testclient import TestClient
from requirement_reuse_service.main import app


def test_extract_review_save_load_and_export_without_vpe(monkeypatch, tmp_path):
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    monkeypatch.setenv('RRS_REQUIREMENT_STORE', str(tmp_path))
    client = TestClient(app)
    request = {'text': 'Each dataset must carry a license or access rights statement.', 'strategy': 'rules'}
    response = client.post('/api/requirements/extract-requirements', json=request)
    assert response.status_code == 200
    analysis = response.json()
    assert analysis['requirements'] and analysis['evidence_units']
    requirements = analysis['requirements']
    requirements[0]['status'] = 'approved'
    saved = client.post('/api/requirements/save-requirement-set', json={
        'name': 'Standalone review', 'requirements': requirements, 'analysis': analysis,
    })
    assert saved.status_code == 200, saved.text
    restored = client.post('/api/requirements/load-requirement-set', json={'id': saved.json()['id']})
    assert restored.status_code == 200
    assert restored.json()['requirements'][0]['status'] == 'approved'
    assert restored.json()['requirements'][0]['source_evidence']
    exported = client.post('/api/requirements/export-rq1-dataset', json=request)
    assert exported.status_code == 200
    assert exported.json()['schema_version'] == 'rq1-requirement-dataset-v1'
    # This API export reruns extraction. Reviewed-state export is provided by the UI.
    assert exported.json()['export_kind'] == 'reproducible_run'


def test_standalone_api_has_rq1_routes_and_no_profile_generation():
    paths = app.openapi()['paths']
    assert '/api/requirements/freeze-evaluation-package' in paths
    assert '/api/requirements/finalize-consensus' in paths
    assert not any('generate-profile' in path or 'generate-shacl' in path or 'rq2' in path for path in paths)


def test_invalid_request_and_unknown_requirement_set(monkeypatch, tmp_path):
    monkeypatch.setenv('RRS_REQUIREMENT_STORE', str(tmp_path))
    client = TestClient(app)
    assert client.post('/api/requirements/extract-requirements', json={'strategy': 'invented'}).status_code == 422
    assert client.post('/api/requirements/load-requirement-set', json={'id': 'missing'}).status_code == 404
