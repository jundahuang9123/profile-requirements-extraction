"""Extension extraction contracts, pinned context, and frozen legacy reuse, offline."""
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_resume_discussions import setup, ROLES
from test_set_aside import extraction_only
from test_semantic_consolidation import GroupClient, inputs, semantic_consolidate
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.llm.step_models import model_settings
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.citations import elicitation_batch
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (
    DeriveRequest, Observation, RunRequest, SnapshotRequest, SourceRequest, SpanObservation)
from requirement_reuse_service.workflow.storage import canonical, digest


BASE = 'dcat-ap-2.0.1'


def span(**changes):
    value = dict(observation_id='x', role_id='x', statement='Publish a road direction.',
        extension_kind='new_information_need', base_property=None,
        evidence_links=[{'source_span_id': 's0'}])
    value.update(changes)
    return value


@pytest.mark.parametrize('key', ['extension_kind', 'base_property'])
def test_v3_provider_requires_each_annotation_key_but_frozen_observations_do_not(key):
    value = span()
    value.pop(key)
    with pytest.raises(ValidationError) as error:
        SpanObservation.model_validate(value)
    assert (key,) in [e['loc'] for e in error.value.errors()]
    assert SpanObservation.model_validate(span()).base_property is None
    legacy = Observation(observation_id='legacy', role_id='r', statement='Publish a title.', evidence_links=[])
    assert legacy.extension_kind is None and legacy.base_property is None


def test_v3_provider_rejects_an_invented_extension_kind():
    with pytest.raises(ValidationError):
        SpanObservation.model_validate(span(extension_kind='same_as_base'))


def base_run(setup, **changes):
    store, initial, client = setup
    request = RunRequest(output_form='candidates', snapshot_id=initial['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id=BASE, **changes)
    return store, engine.new_run(store, request), client


def test_each_independent_role_gets_the_exact_pinned_compact_base_context(setup):
    store, run, scripted = base_run(setup, base_check=False)
    systems = []
    class Captured:
        def describe(self):
            return scripted.describe()
        def generate_structured(self, **kwargs):
            systems.append(kwargs['system'])
            return scripted.generate_structured(**kwargs)
    observations, reports = engine.elicit(store, run, Captured())
    assert observations and all(report['status'] == 'completed' for report in reports)
    expected = engine.extraction_base_context(BASE, run['base_profile_sha256'])
    assert expected['id'] == BASE and expected['version'] == '2.0.1'
    assert expected['sha256'] == run['base_profile_sha256']
    assert 'dcat:Dataset:' in expected['table'] and 'dct:title (mandatory)' in expected['table']
    assert engine.extraction_role_context_chars(None) == 0
    assert engine.extraction_role_context_chars(BASE) == (
        len(canonical({'role': {}, 'base_profile': expected})) - len(canonical({'role': {}})))
    for name, data in scripted.calls:
        assert name == 'SpanElicitationResult' and data['base_profile'] == expected
        assert set(data) == {'role', 'user_tasks', 'base_profile', 'evidence_units', 'stakeholder_perspective'}
        assert len(canonical(data['evidence_units'])) <= engine.EXTRACTION_BATCH_CHARS
        assert len(canonical(data)) <= engine.EXTRACTION_UNIT_CHARS
    assert all('Propose only what changes or adds' in system and 'at least one supporting excerpt' in system
               and 'not_an_extension' in system and 'no peer outputs' in system for system in systems)
    assert all(o.extension_kind == 'new_information_need' and o.base_property is None for o in observations)
    units = [store.get('evidence', eid) for eid in run['evidence_ids']]
    for report, (_, data) in zip(reports, scripted.calls):
        context = {key: value for key, value in data.items() if key != 'evidence_units'}
        assert report['context_hash'] == digest({**context, 'units': units, 'model': model_settings(report['provider'])})


def test_new_run_preflight_counts_base_context_before_provider_construction(setup, monkeypatch):
    store, initial, _ = setup
    unit = store.get('evidence', initial['evidence_ids'][0])
    payload, _ = elicitation_batch([unit])
    allowance_without_base = len(canonical({'evidence_units': payload})) + 5000
    monkeypatch.setattr(engine, 'EXTRACTION_UNIT_CHARS', allowance_without_base)
    calls = []
    monkeypatch.setattr(engine, 'configured_client', lambda request: calls.append(request))
    with pytest.raises(ValueError, match='reserved extraction input budget'):
        engine.new_run(store, RunRequest(output_form='candidates', snapshot_id=initial['snapshot_id'], strategy='multi_agent',
            role_ids=ROLES, base_profile_id=BASE))
    assert calls == []


def test_actual_hard_input_limit_includes_the_compact_base_table(setup, monkeypatch):
    store, run, client = base_run(setup, base_check=False)
    _, second, _ = base_run(setup, base_check=False)
    units = [store.get('evidence', eid) for eid in run['evidence_ids']]
    # Force singleton batches using the complete-input cap, which includes the base.
    # Selected-role context is also present in the actual request.
    snapshot = store.get('snapshot', run['snapshot_id'])
    limits = [len(canonical({**engine.extraction_role_context(run, r, snapshot,
        engine.run_extraction_base_context(run)), 'evidence_units': engine.elicitation_batch([u])[0]}))
        for r in engine.panel_roles(run) for u in units]
    monkeypatch.setattr(engine, 'EXTRACTION_UNIT_CHARS', max(limits))
    observations, reports = engine.elicit(store, run, client)
    assert observations and all(report['status'] == 'completed' for report in reports)
    assert all(len(data['evidence_units']) == 1 for name, data in client.calls)
    # A clean run cannot send a single request larger than the actual unit bound.
    monkeypatch.setattr(engine, 'EXTRACTION_UNIT_CHARS', min(len(canonical(data)) for _, data in client.calls) - 1)
    mark = len(client.calls)
    rejected, rejected_reports = engine.elicit(store, second, client)
    assert rejected == [] and all(r['status'] == 'failed' and 'extraction budget' in r['error']
                                 for r in rejected_reports)
    assert client.calls[mark:] == []


def test_changed_base_fingerprint_is_refused_even_if_base_check_is_disabled(setup, monkeypatch):
    store, run, client = base_run(setup, base_check=False)
    original = engine.load_profile
    monkeypatch.setattr(engine, 'load_profile', lambda identifier: (original(identifier)[0], 'different'))
    configured = []
    monkeypatch.setattr(engine, 'configured_client', lambda request: configured.append(request))
    engine.execute_run(store, run['run_id'])
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'failed' and saved['stages']['elicitation'] == 'failed'
    assert any('registry changed' in line for line in saved['diagnostics'])
    assert configured == [] and not client.calls and saved['observations'] == []


@pytest.mark.parametrize('uncited', [False, True])
def test_declared_nonextensions_remain_auditable_and_are_never_verified_or_assessed(setup, monkeypatch, uncited):
    store, run, client = extraction_only(setup)
    def declared(saved):
        for observation in saved['observations']:
            observation['extension_kind'] = 'not_an_extension'
            if uncited:
                observation['evidence_links'] = []
        saved['request'].update(execution_mode='automatic', discussion='on_request')
        saved['status'] = 'created'
    store.mutate(run['run_id'], None, 'offline_declared', declared)
    checked = []
    monkeypatch.setattr(engine, 'verify', lambda *args, **kwargs: checked.append(args))
    mark = len(client.calls)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['requirements'] == []
    assert not checked and client.calls[mark:] == []
    expected = 'no_source_link' if uncited else 'declared_not_extension'
    assert {item['reason'] for item in saved['set_aside_observations']} == {expected}
    assert len(saved['set_aside_observations']) == len(saved['observations'])
    assert saved['stage_results']['normalization']['set_aside_observations'] == saved['set_aside_observations']
    assert saved['machine_snapshot']['set_aside_observations'] == saved['set_aside_observations']


def test_v2_normalization_keeps_its_previous_uncited_policy_without_v3_hint_semantics(setup):
    store, run, client = extraction_only(setup)
    def old(saved):
        saved['normalization_policy_version'] = 'rq1-normalization-v2'
        saved['observations'][0]['evidence_links'] = []
        for observation in saved['observations']:
            observation['extension_kind'] = 'not_an_extension'
        saved['request'].update(execution_mode='automatic', discussion='on_request')
        saved['status'] = 'created'
    store.mutate(run['run_id'], None, 'offline_v2', old)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert len(saved['set_aside_observations']) == 1
    assert saved['set_aside_observations'][0]['reason'] == 'no_source_link'
    assert saved['requirements'] and all(r['extension_kind'] == 'not_an_extension' for r in saved['requirements'])


def test_failed_v2_extraction_cannot_resume_or_select_new_roles(setup, monkeypatch):
    store, run, client = setup
    store.mutate(run['run_id'], None, 'offline_v2_failure', lambda saved: saved.update(
        status='created', elicitation_policy_version='rq1-independent-elicitation-v2.11'))
    configured = []
    monkeypatch.setattr(engine, 'configured_client', lambda request: configured.append(request))
    engine.execute_run(store, run['run_id'])
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'failed' and saved['stages']['elicitation'] == 'failed'
    assert any('policy has changed' in message for message in saved['diagnostics'])
    assert configured == [] and client.calls == []


def test_legacy_absent_annotations_and_saved_extraction_audits_are_copied_byte_for_byte(setup):
    store, run, client = setup
    engine.execute_run(store, run['run_id'], client)
    def legacy(saved):
        saved['elicitation_policy_version'] = 'rq1-independent-elicitation-v2.11'
        saved['normalization_policy_version'] = 'rq1-normalization-v2'
        for observation in saved['observations']:
            observation.pop('extension_kind', None)
            observation.pop('base_property', None)
        for role in saved['role_runs']:
            role['prompt_version'] = saved['elicitation_policy_version']
            for output in role['raw_outputs']:
                for observation in output['observations']:
                    observation.pop('extension_kind', None)
                    observation.pop('base_property', None)
        saved['stage_results']['elicitation'].update(
            observations=deepcopy(saved['observations']), role_runs=deepcopy(saved['role_runs']))
    store.mutate(run['run_id'], None, 'offline_legacy_annotations', legacy, parts=True)
    source = store.get('run', run['run_id'])
    before = deepcopy(source)
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(output_form='candidates', expected_version=source['version'],
        consolidation='exact', discussion='on_request', base_profile_id=BASE,
        rationale='Offline legacy extension test.'))
    assert trial['observations'] == source['observations']
    assert digest(trial['observations']) == trial['derived_from']['observations_hash']
    assert trial['role_runs'] == source['role_runs'] and trial['catalogues'] == source['catalogues']
    assert trial['stage_results']['elicitation'] == source['stage_results']['elicitation']
    mark = len(client.calls)
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert saved['status'] == 'awaiting_human' and client.count('SpanElicitationResult', mark) == 0
    assert saved['observations'] == source['observations'] and store.get('run', source['run_id']) == before


def test_legacy_content_hash_shape_is_unchanged_and_v3_annotations_are_bound(setup):
    store, run, client = setup
    observation = engine.elicit(store, run, client)[0][0]
    legacy = observation.model_copy(update={'extension_kind': None, 'base_property': None})
    record = engine.record_from_observation(run['run_id'], legacy)
    content = {'statement': record.normalized_statement, 'type': record.requirement_type,
        'intent': record.normalized_intent.model_dump(mode='json'), 'scope': record.scope,
        'links': [link.model_dump(mode='json') for link in record.evidence_links], 'rationale': record.rationale,
        'assumptions': record.assumptions, 'tasks': record.supports_user_tasks}
    assert record.content_hash == digest(content) and engine.verify(store, record, run['evidence_ids'])['status'] == 'pass'
    current = engine.record_from_observation(run['run_id'], observation)
    assert current.content_hash != record.content_hash
    assert engine.verify(store, current, run['evidence_ids'])['status'] == 'pass'
    current.extension_kind = 'not_an_extension'
    assert engine.verify(store, current, run['evidence_ids'])['message'] == 'Requirement content hash mismatch.'


@pytest.mark.parametrize('mode', ['exact', 'semantic'])
def test_merged_representative_keeps_v3_annotations_before_hashing(setup, mode):
    store, run, records = inputs(setup)
    observations = [Observation(observation_id=f'annotated-{index}', role_id=f'role-{index}',
        statement='Dataset title must be published.' if mode == 'exact' else record.raw_statement,
        requirement_type=record.requirement_type, intent=record.normalized_intent,
        scope=record.scope, evidence_links=record.evidence_links, rationale=record.rationale,
        extension_kind='stricter_obligation', base_property='dcat:Dataset/dct:title')
        for index, record in enumerate(records)]
    records = [engine.record_from_observation(run['run_id'], observation) for observation in observations]
    for record in records:
        engine.qualify_record(store, record, run['evidence_ids'])
    if mode == 'exact':
        run['consolidation_policy_version'] = 'rq1-exact-v2'
        active, _, _ = engine.consolidate(store, run, records)
    else:
        active, _, _ = semantic_consolidate(store, run, records, GroupClient())
    assert len(active) == 1 and active[0].parent_revision_ids
    assert active[0].extension_kind == 'stricter_obligation'
    assert active[0].base_property == 'dcat:Dataset/dct:title'
    assert engine.verify(store, active[0], run['evidence_ids'])['status'] == 'pass'


def test_generic_background_does_not_turn_normative_base_text_into_a_domain_tightening(setup):
    store, _, client = setup
    generic = register_source(store, SourceRequest(source_role='background',
        artifact=ArtifactPayload(name='README.md', content='Context for this collection.')))
    normative = register_source(store, SourceRequest(source_role='normative_spec',
        artifact=ArtifactPayload(name='DCAT-AP.pdf.txt', content='Each dataset must include dct:publisher.')))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[
        generic['source_version_id'], normative['source_version_id']]))
    run = engine.new_run(store, RunRequest(output_form='candidates', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id=BASE))
    context = engine.base_check_context(store, run)
    assert context['base_source_version_ids'] == set()
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['set_aside_observations'] == []
    for record in saved['requirements']:
        assert record['base_check']['relation'] == 'inherited' and record['base_check']['requires_review']
        assert any(f['criterion'] == 'unresolved_base_source_classification' for f in record['qualification']['findings'])
    # Configured names identify the authoritative document regardless of its corpus role.
    named = deepcopy(run)
    named['request']['background_source_names'] = ['DCAT-AP.pdf.txt']
    assert engine.base_check_context(store, named)['base_source_version_ids'] == {normative['source_version_id']}
