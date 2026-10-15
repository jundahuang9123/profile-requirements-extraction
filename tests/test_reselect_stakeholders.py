"""New panels reuse audited discovery, never mutate the source or reuse extraction."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from test_role_selection import corpus, auto_run, SelectorClient
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine, role_selection as selector
from requirement_reuse_service.workflow.models import DeriveRequest


def source_scan(corpus, legacy=False):
    store, _, _ = corpus
    run = auto_run(corpus)
    client = SelectorClient()
    manifest = selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    if legacy:
        manifest['policy_version'] = 'rq1-stakeholder-selection-v11'
        selector.seal_manifest(store, manifest)
    store.mutate(run['run_id'], None, 'fixture_completed_scan', lambda r: (
        r.update(role_manifest=manifest), r['stages'].update(role_selection='completed')))
    return store, store.get('run', run['run_id'])


def derive(store, source, **options):
    return engine.derive_run(store, source['run_id'], DeriveRequest(start_from='role_selection',
        expected_version=source['version'], output_form='candidates', execution_mode='stepwise',
        consolidation='exact', rationale='Review a new panel from the saved discovery.', **options))


@pytest.mark.parametrize('legacy', [False, True])
def test_trial_makes_no_discovery_calls_and_preserves_source(corpus, legacy):
    store, source = source_scan(corpus, legacy)
    before = deepcopy(store.get('run', source['run_id']))
    trial = derive(store, source)
    assert trial['role_manifest']['discovery_reused_from']['manifest_hash'] == source['role_manifest']['manifest_hash']
    assert trial['role_manifest']['candidates'] == source['role_manifest']['candidates']
    assert trial['role_manifest']['validation_attempts'] == source['role_manifest']['validation_attempts']
    assert not trial['observations'] and not trial['role_runs'] and not trial['model_calls']
    assert trial['stages']['role_selection'] == 'pending'
    assert trial['stages']['elicitation'] == 'pending'
    client = SelectorClient()
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert saved['status'] == 'paused', saved['diagnostics']
    assert saved['stages']['role_selection'] == 'completed'
    assert saved['stages']['elicitation'] == 'pending'
    assert not any(name in {'RoleCandidates', 'RoleCitationCorrections', 'SpanElicitationResult'} for name, _ in client.calls)
    assert {name for name, _ in client.calls} == {'RoleRegistry', 'StakeholderPanel'}
    assert sorted(i for e in saved['role_manifest']['registry'] for i in e['member_candidate_ids']) == sorted(
        c['candidate_id'] for c in source['role_manifest']['candidates'])
    assert store.get('run', source['run_id']) == before
    # The new run can then extract afresh after human review of its saved panel.
    store.mutate(trial['run_id'], None, 'fixture_continue', lambda r: r.update(status='created'))
    mark = len(client.calls)
    engine.execute_run(store, trial['run_id'], client)
    assert any(name == 'SpanElicitationResult' for name, _ in client.calls[mark:])
    assert store.get('run', source['run_id']) == before


@pytest.mark.parametrize('change', ['snapshot', 'prompt', 'contract', 'contract_hash', 'limit', 'missing_audit'])
def test_incompatible_discovery_is_refused_before_creating_trial(corpus, change):
    store, source = source_scan(corpus)
    def damage(r):
        manifest = r['role_manifest']
        if change == 'snapshot': manifest['snapshot_id'] = 'different-corpus'
        elif change == 'limit': manifest['discovery_candidate_limit'] = 8
        else:
            call = next(c for c in r['model_calls'] if c['output_contract'] == 'RoleCandidates')
            if change == 'prompt': call['system_hash'] = 'different-prompt'
            elif change == 'contract': call['output_contract'] = 'AnotherContract'
            elif change == 'contract_hash': call['output_contract_hash'] = 'different-schema'
            elif change == 'missing_audit': r['model_calls'] = []
    changed_source = deepcopy(source)
    damage(changed_source)
    selector.seal_manifest(store, changed_source['role_manifest'])
    store.mutate(source['run_id'], None, 'fixture_incompatible_scan',
                 lambda r: r.update(role_manifest=changed_source['role_manifest'], model_calls=changed_source['model_calls']),
                 hydrate=True, parts=True)
    changed = store.get('run', source['run_id'])
    before = deepcopy(store.list('run'))
    with pytest.raises(ValueError):
        derive(store, changed)
    assert store.list('run') == before


def test_legacy_v11_without_schema_hash_revalidates_saved_contract(corpus):
    store, source = source_scan(corpus, legacy=True)
    store.mutate(source['run_id'], None, 'fixture_v11_audit', lambda r: [
        c.pop('output_contract_hash', None) for c in r['model_calls']], hydrate=True, parts=True)
    source = store.get('run', source['run_id'])
    trial = derive(store, source)
    assert trial['role_manifest']['candidates'] == source['role_manifest']['candidates']


def test_copied_batches_do_not_bind_new_generation_to_the_old_model(corpus):
    store, source = source_scan(corpus)
    trial = derive(store, source)
    def new_model(r):
        r['step_models'] = {'role_selection': 'new-selector'}
        r['request']['step_models'] = r['step_models']
    store.mutate(trial['run_id'], None, 'fixture_new_model', new_model)
    trial = store.get('run', trial['run_id'])
    client = SelectorClient()
    client.describe = lambda: {'provider': 'offline-test', 'model': 'new-selector'}
    completed = selector.select_roles(store, trial, client)
    assert completed['status'] == 'completed'
    assert not any(name == 'RoleCandidates' for name, _ in client.calls)


def test_derive_api_exposes_stepwise_reselection_without_changing_source(corpus, monkeypatch):
    from requirement_reuse_service.workflow import api
    store, source = source_scan(corpus)
    before = deepcopy(source)
    jobs = []
    monkeypatch.setattr(api, 'execute_run', lambda store, identifier: jobs.append(identifier))
    response = TestClient(app).post(f'/api/rq1/v2/runs/{source["run_id"]}/derive', json={
        'start_from': 'role_selection', 'expected_version': source['version'], 'execution_mode': 'stepwise',
        'output_form': 'candidates', 'rationale': 'Inspect a separate panel trial.'})
    assert response.status_code == 202, response.text
    assert response.json()['request']['execution_mode'] == 'stepwise'
    assert jobs == [response.json()['run_id']]
    assert store.get('run', source['run_id']) == before


def test_a_second_trial_preserves_original_legacy_contract_lineage(corpus):
    store, source = source_scan(corpus, legacy=True)
    store.mutate(source['run_id'], None, 'fixture_legacy_audit', lambda r: [
        c.pop('output_contract_hash', None) for c in r['model_calls']], parts=True)
    source = store.get('run', source['run_id'])
    trial = derive(store, source)
    engine.execute_run(store, trial['run_id'], SelectorClient())
    completed = store.get('run', trial['run_id'])
    again = derive(store, completed)
    assert again['role_manifest']['discovery_reused_from']['original_policy'] == 'rq1-stakeholder-selection-v11'
    assert again['role_manifest']['candidates'] == source['role_manifest']['candidates']
