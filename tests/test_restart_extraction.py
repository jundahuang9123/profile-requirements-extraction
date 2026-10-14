"""A step-3b trial reuses the sealed panel, never historical extraction output."""
from copy import deepcopy
import time

import pytest
from fastapi.testclient import TestClient
from test_resume_discussions import setup
from test_role_selection import corpus, auto_run, SelectorClient
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow.evaluation import workflow_metrics
from requirement_reuse_service.workflow.models import DeriveRequest, NEEDS_ELICITATION_POLICY
from requirement_reuse_service.workflow.storage import ConflictError, digest


def restart(store, source, **options):
    return engine.derive_run(store, source['run_id'], DeriveRequest(
        start_from='elicitation', expected_version=source['version'], consolidation='exact',
        rationale='Retry extraction with the current contract and frozen panel.', **options))


def test_restart_partial_automatic_run_reuses_panel_and_preserves_source(corpus):
    store, _, _ = corpus
    parent = auto_run(corpus)
    client = SelectorClient()
    engine.execute_run(store, parent['run_id'], client)
    store.mutate(parent['run_id'], None, 'historical_partial', lambda r: (
        r.update(elicitation_policy_version='rq1-independent-elicitation-v3.2'),
        r['role_runs'][0].update(status='failed')))
    source = store.get('run', parent['run_id'])
    before = deepcopy(source)
    trial = restart(store, source)
    assert trial['observations'] == trial['role_runs'] == trial['model_calls'] == []
    assert not trial['catalogues'] and not trial['requirements']
    assert trial['role_manifest'] == source['role_manifest']
    assert trial['request']['role_selection'] == 'automatic'
    assert trial['elicitation_policy_version'] == engine.PROMPT_VERSION
    assert trial['derived_from']['stage'] == 'role_selection'
    assert trial['derived_from']['reuse_assessments'] is False
    assert workflow_metrics(trial)['extraction_reused'] is False
    assert trial['stages']['role_selection'] == 'completed'
    assert trial['stages']['elicitation'] == 'pending'
    mark = len(client.calls)
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert any(name == 'SpanElicitationResult' for name, _ in client.calls[mark:])
    assert not any(name.startswith('Role') for name, _ in client.calls[mark:])
    assert store.get('run', source['run_id']) == before


def test_restart_can_resume_its_own_partial_extraction(setup):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    source = store.get('run', parent['run_id'])
    trial = restart(store, source)
    client.failing_extraction = ('consumer_discovery', 'coverage')
    engine.execute_run(store, trial['run_id'], client)
    failed = store.get('run', trial['run_id'])
    assert any(role['status'] == 'failed' for role in failed['role_runs'])
    engine.ensure_elicitation_resumable(failed)
    completed = {role['role_id'] for role in failed['role_runs'] if role['status'] == 'completed'}
    mark = len(client.calls)
    client.failing_extraction = None
    store.mutate(trial['run_id'], None, 'resume_partial_trial', lambda r: (
        r.update(status='created'), r['stages'].update(elicitation='pending')))
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert all(role['status'] == 'completed' for role in saved['role_runs']), saved['diagnostics']
    assert not any(name == 'SpanElicitationResult' and data['role']['id'] in completed
                   for name, data in client.calls[mark:])


@pytest.mark.parametrize('change', ['panel', 'evidence', 'role_stage', 'policy'])
def test_restart_rejects_changed_checkpoint_before_calls(setup, change):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    trial = restart(store, store.get('run', parent['run_id']))
    if change == 'panel':
        trial['role_manifest']['created_at'] = 'changed'
    elif change == 'evidence':
        trial['evidence_ids'] = []
    elif change == 'role_stage':
        trial['stages']['role_selection'] = 'pending'
    else:
        trial['elicitation_policy_version'] = 'obsolete'
    with pytest.raises(ValueError):
        engine.ensure_elicitation_resumable(trial)


def test_restart_rejects_changed_snapshot_before_provider_calls(setup):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    trial = restart(store, store.get('run', parent['run_id']))
    trial['derived_from']['snapshot_hash'] = 'wrong'
    store.mutate(trial['run_id'], None, 'changed_snapshot',
                 lambda r: r.update(derived_from=trial['derived_from']))
    mark = len(client.calls)
    engine.execute_run(store, trial['run_id'], client)
    assert len(client.calls) == mark
    assert 'snapshot checkpoint hash mismatch' in store.get('run', trial['run_id'])['diagnostics'][0]


@pytest.mark.parametrize('change', ['worker', 'unfinished_panel', 'invalid_panel', 'source_units', 'version'])
def test_restart_refuses_unsafe_source(setup, change):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    source = store.get('run', parent['run_id'])
    if change == 'worker':
        source.update(worker_id='active', job_lease_until=time.time() + 900)
    elif change == 'unfinished_panel':
        source['stages']['role_selection'] = 'failed'
    elif change == 'invalid_panel':
        source['role_manifest']['created_at'] = 'changed'
    elif change == 'source_units':
        source['evidence_ids'] = []
    store.mutate(source['run_id'], None, 'unsafe_source', lambda r: r.update(
        worker_id=source.get('worker_id'), job_lease_until=source.get('job_lease_until', 0),
        stages=source['stages'], role_manifest=source['role_manifest'], evidence_ids=source['evidence_ids']))
    source = store.get('run', source['run_id'])
    if change == 'version':
        source['version'] -= 1
    with pytest.raises((ValueError, ConflictError)):
        restart(store, source)


def test_restart_needs_uses_current_contract_and_pins_catalogue(setup):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    trial = restart(store, store.get('run', parent['run_id']), output_form='needs',
                    scoping='off', base_profile_id='dcat-ap-2.0.1')
    assert trial['elicitation_policy_version'] == NEEDS_ELICITATION_POLICY
    assert trial['base_needs_catalogue']['catalogue_hash']
    assert trial['derived_from']['observations_hash'] != digest(trial['observations'])


def test_restart_endpoint_starts_extraction_in_a_separate_run(setup):
    store, parent, client = setup
    engine.execute_run(store, parent['run_id'], client)
    source = store.get('run', parent['run_id'])
    mark = len(client.calls)
    response = TestClient(app).post(f'/api/rq1/v2/runs/{source["run_id"]}/derive', json={
        'start_from': 'elicitation', 'expected_version': source['version'],
        'output_form': 'candidates', 'consolidation': 'exact', 'rationale': 'Restart step 3b.'})
    assert response.status_code == 202, response.text
    assert response.json()['run_id'] != source['run_id']
    assert client.count('SpanElicitationResult', mark) > 0
    assert store.get('run', source['run_id']) == source

