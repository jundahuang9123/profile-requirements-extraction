import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.engine import (elicit, execute_case, execute_run, freeze_snapshot,
    new_run, record_from_observation, verify)
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import Observation, RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store

@pytest.fixture
def context(tmp_path, monkeypatch):
    path = str(tmp_path / 'workflow.sqlite3')
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', path)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    return Store(path), TestClient(app)

def setup_run(context, text='Each dataset must describe the represented asset.', strategy='rules'):
    store, client = context
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=text), source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy=strategy))
    execute_run(store, run['run_id'])
    return store.get('run', run['run_id'])

def assess(client, run, record, support='explicit'):
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/assessments', json={
        'expected_version': run['version'], 'idempotency_key': 'assess-' + record['revision_id'],
        'revision_id': record['revision_id'], 'qualification': {'support': support, 'rationale': 'Evidence supports this atomic need in its stated scope.',
            'findings': [], 'assessor': 'ignored-client-actor', 'revision_hash': record['content_hash']}})
    assert response.status_code == 200, response.text
    return response.json()['run']

def decision(client, run, record_ids, action='accept', **extra):
    payload = {'expected_version': run['version'], 'idempotency_key': action + '-' + '-'.join(record_ids),
               'revision_ids': record_ids, 'action': action, 'rationale': 'Documented human judgement.', **extra}
    return client.post(f'/api/rq1/v2/runs/{run["run_id"]}/decisions', json=payload), payload

def test_end_to_end_review_baseline_restores_and_exports_without_rerun(context):
    store, client = context
    run = setup_run(context)
    record = run['requirements'][0]
    denied, _ = decision(client, run, [record['revision_id']])
    assert denied.status_code == 422 and 'semantic' in denied.text
    run = assess(client, run, record)
    accepted, payload = decision(client, run, [record['revision_id']])
    assert accepted.status_code == 200, accepted.text
    run = accepted.json()['run']
    repeated = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/decisions', json=payload)
    assert repeated.json() == accepted.json()
    published = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json={
        'expected_version': run['version'], 'idempotency_key': 'baseline', 'revision_ids': [record['revision_id']]})
    assert published.status_code == 200, published.text
    baseline = published.json()['result']
    assert baseline['requirements'][0]['lifecycle_state'] == 'accepted'
    assert baseline['sources'][0]['raw_base64'] and baseline['evidence_units']
    assert baseline['provenance']['observations'] and baseline['provenance']['decisions']
    restored = TestClient(app).get(f'/api/rq1/v2/runs/{run["run_id"]}').json()
    assert restored['baselines'][0] == baseline
    exported = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/export').json()
    assert exported['export_kind'] == 'saved_review_state'
    assert exported['run']['requirements'][0]['lifecycle_state'] == 'accepted'
    metrics = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/evaluation').json()
    assert metrics['machine']['state_distribution'] == {'awaiting_human': 1}
    assert metrics['machine']['support_distribution'] == {'uncertain': 1}
    assert metrics['human_accepted']['count'] == 1
    assert baseline['provenance']['machine_snapshot']['requirements'][0]['lifecycle_state'] == 'awaiting_human'
    attachment = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/baselines/{baseline["baseline_id"]}?download=true')
    assert attachment.json() == baseline
    assert attachment.headers['content-disposition'] == 'attachment; filename="rq1-validated-baseline-v2.json"'


def test_human_added_need_is_not_counted_as_machine_output(context):
    store, client = context
    run = setup_run(context, text='Dataset ownership is described by the stakeholder.')
    assert not run['requirements']
    evidence = store.get('evidence', run['evidence_ids'][0])
    payload = {'expected_version': run['version'], 'idempotency_key': 'human-add',
        'rationale': 'A missed ownership need.', 'draft': {'statement': 'Describe dataset ownership.',
            'scope': 'Stakeholder datasets', 'evidence_links': [{'evidence_id': evidence['evidence_id'], 'quote': evidence['content']}],
            'requirement_type': 'quality_provenance', 'intent': {'resource_type': 'Dataset', 'metadata_need': 'ownership', 'obligation_hint': 'unknown'}}}
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/requirements', json=payload)
    assert response.status_code == 200, response.text
    run = response.json()['run']
    assert run['requirements'][0]['lifecycle_state'] == 'awaiting_human'
    assert client.post(f'/api/rq1/v2/runs/{run["run_id"]}/requirements', json=payload).json() == response.json()
    metrics = client.get(f'/api/rq1/v2/runs/{run["run_id"]}/evaluation').json()
    assert metrics['machine']['count'] == 0 and metrics['current_review']['count'] == 1
    assert metrics['human_added_revision_ids'] == run['active_revision_ids']
    denied, _ = decision(client, run, run['active_revision_ids'])
    assert denied.status_code == 422


def test_v2_unknown_intent_never_defaults_to_dataset_or_discovery():
    from requirement_reuse_service.workflow.models import RevisionDraft
    intent = RevisionDraft(statement='A possible need.', evidence_links=[]).intent
    assert intent.resource_type == 'Unknown' and intent.metadata_need == ''


def test_disabled_multi_agent_is_rejected_without_rule_fallback(context, monkeypatch):
    store, _ = context
    run = setup_run(context)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    with pytest.raises(ValueError, match='configured provider'):
        new_run(store, RunRequest(snapshot_id=run['snapshot_id'], strategy='multi_agent'))

def test_grounding_fabricated_quotes_and_real_but_irrelevant_quote(context):
    store, _ = context
    run = setup_run(context)
    observation = Observation.model_validate(run['observations'][0])
    observation.statement = 'Every dataset must expose proprietary personal data.'
    record = record_from_observation(run['run_id'], observation)
    report = verify(store, record, run['evidence_ids'])
    assert report['status'] == 'pass'  # Authenticity does not establish this statement.
    from requirement_reuse_service.workflow.engine import assess as qualify
    record.verification = report
    assert qualify(store, record).support == 'uncertain'
    observation.evidence_links[0].quote = 'fabricated quotation'
    record = record_from_observation(run['run_id'], observation)
    assert verify(store, record, run['evidence_ids'])['status'] == 'fail'
    observation.evidence_links[0].evidence_id = 'missing'
    assert verify(store, record_from_observation(run['run_id'], observation), run['evidence_ids'])['status'] == 'fail'

def test_missing_obligation_premise_blocks(context):
    store, _ = context
    run = setup_run(context)
    obs = Observation.model_validate(run['observations'][0])
    obs.evidence_links = obs.evidence_links[:1]
    assert verify(store, record_from_observation(run['run_id'], obs), run['evidence_ids'])['status'] == 'fail'

def test_mock_perspectives_preserve_raw_and_merge_lineage(context):
    store, _ = context
    run = setup_run(context, strategy='mock')
    assert len(run['observations']) == 2
    assert len(run['active_revision_ids']) == 1
    merged = next(r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids'])
    assert len(merged['parent_revision_ids']) == 2
    assert set(merged['contributing_roles']) == {'construction_domain', 'consumer_discovery'}
    assert merged['qualification']['support'] == 'uncertain'
    assert run['strategy'] == 'mock'

def test_conflicting_obligations_remain_separate_and_need_resolution(context):
    store, client = context
    run = setup_run(context, 'Each dataset must publish its title.\nEach dataset should publish its title.')
    assert len(run['active_revision_ids']) == 2
    assert run['conflicts'][0]['kind'] == 'obligation'
    assert len(run['deliberations']) == 1
    first, second = run['requirements']
    run = assess(client, run, first)
    rejected, _ = decision(client, run, [second['revision_id']], 'reject')
    assert rejected.status_code == 200
    run = rejected.json()['run']
    result, _ = decision(client, run, [first['revision_id']])
    assert result.status_code == 422 and 'resolve' in result.text
    result, _ = decision(client, run, [first['revision_id']], conflict_ids=[run['conflicts'][0]['conflict_id']])
    assert result.status_code == 200, result.text
    run = result.json()['run']
    assert run['conflicts'][0]['status'] == 'resolved'
    assert run['requirements'][1]['lifecycle_state'] == 'rejected'

def test_edit_invalidates_assessment_and_acceptance_preserves_history(context):
    store, client = context
    run = setup_run(context)
    old = run['requirements'][0]
    run = assess(client, run, old)
    response, _ = decision(client, run, [old['revision_id']])
    run = response.json()['run']
    draft = {'statement': 'Each dataset must describe the construction asset represented.',
             'evidence_links': old['evidence_links'], 'requirement_type': old['requirement_type'],
             'intent': old['normalized_intent'], 'scope': old['scope']}
    edited, _ = decision(client, run, [old['revision_id']], 'edit', drafts=[draft])
    assert edited.status_code == 200, edited.text
    run = edited.json()['run']
    new = next(r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids'])
    assert new['requirement_id'] == old['requirement_id']
    assert new['parent_revision_ids'] == [old['revision_id']]
    assert new['qualification']['support'] == 'uncertain'
    assert new['decision_id'] is None
    denied, _ = decision(client, run, [new['revision_id']])
    assert denied.status_code == 422
    assert any(d['action'] == 'accept' for d in run['decisions'])

def test_idempotency_and_stale_versions_are_transactional(context):
    store, client = context
    run = setup_run(context)
    record = run['requirements'][0]
    before = len(store.events(run['run_id']))
    response, payload = decision(client, run, [record['revision_id']], 'defer')
    assert response.status_code == 200
    modified = {**payload, 'rationale': 'Different command'}
    assert client.post(f'/api/rq1/v2/runs/{run["run_id"]}/decisions', json=modified).status_code == 409
    stale = {**payload, 'idempotency_key': 'new-command'}
    assert client.post(f'/api/rq1/v2/runs/{run["run_id"]}/decisions', json=stale).status_code == 409
    assert len(store.events(run['run_id'])) == before + 1

def test_model_role_contexts_contain_no_peer_outputs_and_failures_are_visible(context):
    store, _ = context
    run = setup_run(context, strategy='mock')
    run['strategy'] = 'multi_agent'
    run['role_runs'] = []
    run['observations'] = []
    sentinel = 'PEER_OUTPUT_SENTINEL'
    def output(system, user):
        context_data = json.loads(user)
        assert sentinel not in user
        if context_data['role']['id'] == 'construction_domain':
            raise RuntimeError('role failed')
        unit = context_data['evidence_units'][0]
        return {'observations': [{'observation_id': 'model-id', 'role_id': 'model-role', 'statement': sentinel,
                                 'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': unit['content']}]}]}
    observations, reports = elicit(store, run, MockLLMClient(output))
    assert len(observations) == 1
    assert any(report['status'] == 'failed' for report in reports)
    assert any(report.get('raw_outputs') for report in reports)

def test_deliberation_is_bounded_preserves_dissent_and_cannot_accept(context):
    store, client = context
    run = setup_run(context, 'Each dataset must publish its title.\nEach dataset should publish its title.')
    case = run['deliberations'][0]
    mock = MockLLMClient({'body': 'Dissent: scope remains ambiguous.', 'evidence_ids': [], 'finished': False})
    execute_case(store, run['run_id'], case['case_id'], mock)
    updated = store.get('run', run['run_id'])
    case = updated['deliberations'][0]
    assert len(mock.calls) <= case['max_calls']
    assert case['status'] == 'budget_exhausted'
    assert case['messages'] and all('Dissent' in message['body'] for message in case['messages'])
    assert not updated['decisions']
    assert all(record['lifecycle_state'] != 'accepted' for record in updated['requirements'])
    assert len(updated['model_calls']) == len(mock.calls)
    assert all(c['system_hash'] and c['context_hash'] and c['token_usage'] is None for c in updated['model_calls'])

def test_live_provider_is_never_called_without_explicit_opt_in(context, monkeypatch):
    store, client = context
    run = setup_run(context)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('RRS_LLM_BASE_URL', 'https://api.openai.com/v1')
    monkeypatch.setenv('RRS_LLM_MODEL', 'test')
    response = client.post('/api/rq1/v2/runs', json={'snapshot_id': run['snapshot_id'], 'strategy': 'multi_agent'})
    assert response.status_code == 422 and 'explicit' in response.text

def test_background_sources_cannot_become_grounding_and_parse_failures_block(context):
    store, client = context
    background = register_source(store, SourceRequest(artifact=ArtifactPayload(name='background.md', content='Dataset must publish title.'), source_role='background'))
    result = client.post('/api/rq1/v2/snapshots', json={'source_version_ids': [background['source_version_id']]})
    assert result.status_code == 422
    bad = register_source(store, SourceRequest(artifact=ArtifactPayload(name='bad.json', content='not JSON')))
    result = client.post('/api/rq1/v2/snapshots', json={'source_version_ids': [bad['source_version_id']]})
    assert result.status_code == 422


def test_repeated_quote_needs_address_and_revision_tampering_fails(context):
    store, _ = context
    run = setup_run(context, 'Each dataset must name a dataset.')
    obs = Observation.model_validate(run['observations'][0])
    obs.evidence_links[0].quote = 'dataset'
    ambiguous = record_from_observation(run['run_id'], obs)
    assert verify(store, ambiguous, run['evidence_ids'])['status'] == 'fail'
    obs.evidence_links[0].quote_start = obs.statement.index('dataset')
    addressed = record_from_observation(run['run_id'], obs)
    assert verify(store, addressed, run['evidence_ids'])['status'] == 'pass'
    addressed.normalized_statement = 'Tampered after assessment.'
    assert verify(store, addressed, run['evidence_ids'])['status'] == 'fail'


def test_restart_resumes_expired_job_and_retains_completed_roles(context):
    store, client = context
    run = setup_run(context, strategy='mock')
    store.mutate(run['run_id'], run['version'], 'simulated_crash', lambda r: r.update(status='verifying', worker_id='lost-worker', job_lease_until=0))
    interrupted = store.get('run', run['run_id'])
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': interrupted['version']})
    assert response.status_code == 202, response.text
    restored = store.get('run', run['run_id'])
    assert restored['status'] == 'awaiting_human'
    assert restored['attempt_history'][0]['role_runs'] == run['role_runs']
    assert restored['observations'] == run['observations']
    assert restored['worker_id'] is None


def test_pending_deliberation_blocks_baseline_until_explicitly_closed(context):
    store, client = context
    run = setup_run(context)
    record = run['requirements'][0]
    opened = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/deliberations', json={
        'expected_version': run['version'], 'revision_ids': [record['revision_id']], 'question': 'Check the applicability.'})
    assert opened.status_code == 200
    run = opened.json()['run']
    case_id = opened.json()['result']['case_id']
    run = assess(client, run, record)
    accepted, _ = decision(client, run, [record['revision_id']])
    run = accepted.json()['run']
    request = {'expected_version': run['version'], 'idempotency_key': 'publish', 'revision_ids': [record['revision_id']]}
    assert client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json=request).status_code == 422
    closed = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/deliberations/{case_id}/close', json={
        'expected_version': run['version'], 'idempotency_key': 'close', 'body': 'Human inspected evidence and adjudicated applicability.', 'evidence_ids': []})
    run = closed.json()['run']
    assert run['stages']['deliberation'] == 'completed'
    published = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json={**request, 'expected_version': run['version']})
    assert published.status_code == 200, published.text
    assert published.json()['run']['status'] == 'completed'


def test_baseline_rechecks_source_and_never_adopts_changed_bytes(context):
    import base64
    from requirement_reuse_service.workflow.storage import canonical
    store, client = context
    run = setup_run(context)
    record = run['requirements'][0]
    run = assess(client, run, record)
    accepted, _ = decision(client, run, [record['revision_id']])
    run = accepted.json()['run']
    source = store.list('source')[0]
    source['raw_base64'] = base64.b64encode(b'Changed source').decode()
    with store.connect() as db:
        db.execute('UPDATE objects SET body=? WHERE kind="source" AND id=?', (canonical(source), source['source_version_id']))
    response = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json={
        'expected_version': run['version'], 'idempotency_key': 'bad-baseline', 'revision_ids': [record['revision_id']]})
    assert response.status_code == 422 and 'changed' in response.text
    assert not store.get('run', run['run_id'])['baselines']
