"""Human support judgements cannot bypass an inherited base obligation."""
from fastapi.testclient import TestClient
from test_resume_discussions import setup, ROLES
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow.engine import new_run, execute_run
from requirement_reuse_service.workflow.models import RunRequest
from copy import deepcopy


def test_manual_assessment_retains_blocking_base_finding(setup):
    store, source, scripted = setup
    run = new_run(store, RunRequest(snapshot_id=source['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    execute_run(store, run['run_id'], scripted)
    saved = store.get('run', run['run_id'])
    record = next(r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']
                  and r['base_check']['relation'] == 'loosened')
    client = TestClient(app)
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/assessments', json={
        'expected_version': saved['version'], 'revision_id': record['revision_id'], 'idempotency_key': 'base-review',
        'qualification': {'support': 'explicit', 'rationale': 'A scripted human support assessment.',
            'findings': [], 'assessor': 'ignored-client-name', 'revision_hash': record['content_hash']}})
    assert response.status_code == 200, response.text
    after = store.get('run', run['run_id'])
    checked = next(r for r in after['requirements'] if r['revision_id'] == record['revision_id'])
    assert any(f['criterion'] == 'conflicts_with_base' and f['severity'] == 'blocking'
               for f in checked['qualification']['findings'])
    accept = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/decisions', json={
        'expected_version': after['version'], 'revision_ids': [record['revision_id']], 'action': 'accept',
        'rationale': 'Try accepting a weakened base rule.', 'idempotency_key': 'cannot-relax-base'})
    assert accept.status_code == 422 and 'base-profile' in accept.text
    assert store.get('run', run['run_id']) == after


def test_human_addition_gets_base_check_without_mutating_machine_snapshot(setup):
    store, source, scripted = setup
    run = new_run(store, RunRequest(snapshot_id=source['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    execute_run(store, run['run_id'], scripted)
    saved = store.get('run', run['run_id'])
    machine = deepcopy(saved['machine_snapshot'])
    reference = next(r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']
                     and r['base_check']['relation'] == 'loosened')
    response = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/requirements', json={
        'expected_version': saved['version'], 'idempotency_key': 'manual-base-proposal',
        'rationale': 'A scripted addition to test the review guard.', 'draft': {
            'statement': 'Dataset title is optional.', 'requirement_type': 'descriptive_metadata',
            'scope': 'Dataset', 'intent': {'resource_type': 'Dataset', 'metadata_need': 'title',
                'value_kind': 'literal', 'obligation_hint': 'optional'}, 'evidence_links': reference['evidence_links']}})
    assert response.status_code == 200, response.text
    after = store.get('run', run['run_id'])
    added = next(r for r in after['requirements'] if r['revision_id'] not in {
        old['revision_id'] for old in saved['requirements']})
    assert added['base_check']['relation'] == 'loosened'
    assert any(f['criterion'] == 'conflicts_with_base' for f in added['qualification']['findings'])
    assert added['lifecycle_state'] != 'accepted'
    assert after['machine_snapshot'] == machine
