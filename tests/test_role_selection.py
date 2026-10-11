"""Offline checks for role selection boundaries, provenance and actual role use."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.engine import (TrackedClient, execute_run, freeze_snapshot,
    make_case, new_run, record_from_observation)
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (Observation, RoleProposal, RunRequest,
    SnapshotRequest, SourceRequest)
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'roles.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='input.md', content=(
        'Transport data publishers must provide geographic coverage.\n'
        'Catalogue operators need stable dataset identifiers.')),
        source_role='stakeholder_need'))
    reference = register_source(store, SourceRequest(artifact=ArtifactPayload(name='answers.md', content=
        'SECRET REFERENCE ANSWER: use final property hidden:answer.'), source_role='evaluation_reference'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id'], reference['source_version_id']],
        user_tasks=[{'id': 'CQ-1', 'statement': 'Which datasets cover my region?', 'kind': 'competency_question'}]))
    return store, snapshot, reference


class SelectorClient:
    def __init__(self, fail_reducer=False, bad_quote=False, empty=False, duplicate=False):
        self.calls = []
        self.fail_reducer = fail_reducer
        self.bad_quote = bad_quote
        self.empty = empty
        self.duplicate = duplicate

    def describe(self):
        return {'provider': 'offline-test', 'model': 'scripted'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        data = json.loads(user)
        self.calls.append((output_model.__name__, data))
        if output_model.__name__ == 'RoleCandidates':
            unit = data['evidence_units'][0]
            response = {'candidates': [] if self.empty else [{
                'label': 'Catalogue operator', 'stakeholders': ['Catalogue operators'], 'basis': 'documented',
                'purpose': 'Examine catalogue maintenance needs.', 'rationale': 'The source states an operational responsibility.',
                'focus_questions': ['What metadata must be maintained?'],
                'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': 'invented quote' if self.bad_quote else unit['content']}],
                'task_ids': ['CQ-1']}]}
        elif output_model.__name__ == 'RoleCitationCorrections':
            response = {'corrections': [{'candidate_index': item['candidate_index'],
                'source_span_ids': [], 'unresolved_reason': 'No valid quotation supplied by test client.'} for item in data['invalid_candidates']]}
        elif output_model.__name__ == 'RolePanel':
            if self.fail_reducer:
                raise RuntimeError('Interrupted selection')
            ids = [c['candidate_id'] for c in data['candidates']]
            response = {'groups': [{'representative_id': ids[0], 'member_ids': ids, 'rationale': 'Shared operational perspective.'}], 'omitted': []}
            if self.duplicate:
                response['omitted'] = [{'candidate_id': ids[0], 'reason': 'Invalid duplicate disposition.'}]
        elif output_model.__name__ == 'SpanElicitationResult':
            unit = data['evidence_units'][0]
            response = {'observations': [{'observation_id': 'model-proposal', 'role_id': 'untrusted-model-id',
                'statement': 'Describe dataset geographic coverage.', 'scope': 'Datasets',
                'requirement_type': 'descriptive_metadata', 'intent': {'resource_type': 'Dataset', 'metadata_need': 'geographic coverage'},
                'evidence_links': [{'source_span_id': unit['source_spans'][0]['span_id']}]}]}
        elif output_model.__name__ == 'Qualification':
            response = {'support': 'uncertain', 'rationale': 'A scoped review is needed.', 'findings': [], 'assessor': 'test'}
        elif output_model.__name__ == 'Turn':
            response = {'body': 'Check scope without inventing stakeholder preferences.', 'evidence_ids': [], 'finished': True}
        else:
            raise AssertionError(output_model.__name__)
        return output_model.model_validate(response)


def auto_run(corpus, **kwargs):
    store, snapshot, _ = corpus
    return new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_selection='automatic', **kwargs))


def test_full_auto_run_uses_frozen_roles_in_extraction_discussion_and_exports(corpus):
    store, snapshot, reference = corpus
    run = auto_run(corpus)
    client = SelectorClient()
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    manifest = saved['role_manifest']
    selector.verify_manifest(manifest)
    assert manifest['status'] == 'completed'
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    assert manifest['selected_roles'][0]['basis'] == 'documented'
    assert 'SECRET REFERENCE ANSWER' not in json.dumps(client.calls)
    assert reference['source_version_id'] not in snapshot['source_version_ids']
    assert snapshot['exclusions'][0]['reason'] == 'evaluation_reference_not_evidence'
    extraction = next(data for contract, data in client.calls if contract == 'SpanElicitationResult')
    assert extraction['role']['id'] == manifest['selected_roles'][0]['role_id']
    assert extraction['stakeholder_perspective']['basis'] == 'documented'
    turns = [data for contract, data in client.calls if contract == 'Turn']
    assert any(data['role_definition']['purpose'] == 'Examine catalogue maintenance needs.' for data in turns)
    assert any(data['role'] == 'grounding_scope_critic' and data['role_definition'] for data in turns)
    assert saved['machine_snapshot']['role_manifest'] == manifest
    api = TestClient(app)
    assert api.get(f'/api/rq1/v2/runs/{run["run_id"]}/export').json()['run']['role_manifest'] == manifest
    metrics = api.get(f'/api/rq1/v2/runs/{run["run_id"]}/evaluation').json()
    assert metrics['role_selection']['model_calls'] == 2
    assert metrics['role_selection']['basis_counts'] == {'documented': 1}
    assert Store(str(store.path)).get('role_manifest', manifest['manifest_hash']) == manifest


@pytest.mark.parametrize('options, message', [({'bad_quote': True}, 'quotation'), ({'duplicate': True}, 'exactly once')])
def test_bad_selector_output_fails_before_extraction_without_fallback(corpus, options, message):
    store, _, _ = corpus
    run = auto_run(corpus)
    client = SelectorClient(**options)
    execute_run(store, run['run_id'], client)
    result = store.get('run', run['run_id'])
    assert result['status'] == 'failed'
    assert message in ' '.join(result['diagnostics'])
    assert not result['role_runs'] and not result['observations']
    assert not any(contract == 'SpanElicitationResult' for contract, _ in client.calls)
    assert result['role_manifest']['status'] != 'completed'
    assert result['role_manifest']['status'] == 'failed'
    assert result['stages']['role_selection'] == 'failed'


def test_interrupted_reducer_reuses_saved_discovery_and_completed_manifest(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    broken = SelectorClient(fail_reducer=True)
    execute_run(store, run['run_id'], broken)
    partial = store.get('run', run['run_id'])
    assert partial['status'] == 'failed' and len(partial['role_manifest']['batch_reports']) == 1
    assert partial['role_manifest']['selection_rounds'] == []
    repaired = SelectorClient()
    execute_run(store, run['run_id'], repaired)
    assert not any(contract == 'RoleCandidates' for contract, _ in repaired.calls)
    completed = store.get('run', run['run_id'])
    assert completed['role_manifest']['status'] == 'completed'
    no_calls = SelectorClient()
    same = selector.select_roles(store, completed, no_calls)
    assert same == completed['role_manifest'] and not no_calls.calls


def test_all_batches_scanned_with_bounded_panel_and_lineage(corpus, monkeypatch):
    store, snapshot, _ = corpus
    units = [store.get('evidence', eid) for eid in snapshot['evidence_ids']]
    from requirement_reuse_service.workflow.storage import canonical
    monkeypatch.setattr(selector, 'BATCH_CHARS', max(len(canonical(unit)) for unit in units) + 10)
    run = auto_run(corpus, max_roles=1)
    client = SelectorClient()
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    assert manifest['total_batches'] == 2
    assert len(manifest['batch_reports']) == len(manifest['selection_rounds']) == 2
    assert len(manifest['selected_roles']) == 1
    assert len(manifest['selected_roles'][0]['candidate_ids']) == 2
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])


def test_empty_scan_returns_explicit_proposals_but_model_failure_does_not(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    manifest = selector.select_roles(store, run, SelectorClient(empty=True))
    assert manifest['fallback_reason']
    assert all(role['basis'] == 'proposed' and not role['evidence_links'] for role in manifest['selected_roles'])


def test_role_basis_citation_scope_and_unknown_tasks(corpus):
    store, snapshot, reference = corpus
    proposal = selector.proposed_defaults()[0]
    data = proposal.model_dump()
    with pytest.raises(ValueError, match='source citations'):
        RoleProposal(**{**data, 'basis': 'documented'})
    with pytest.raises(ValueError, match='declared task'):
        RoleProposal(**{**data, 'basis': 'inferred'})
    proposal.task_ids = ['unknown']
    with pytest.raises(ValueError, match='undeclared'):
        selector.validate_proposal(store, proposal, snapshot['evidence_ids'], snapshot['user_tasks'])
    unit = next(u for u in store.list('evidence') if u['source_version_id'] == reference['source_version_id'])
    proposal = RoleProposal(**{**data, 'basis': 'documented', 'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': unit['content']}]})
    with pytest.raises(ValueError, match='outside'):
        selector.validate_proposal(store, proposal, snapshot['evidence_ids'], snapshot['user_tasks'])


def test_oversized_scan_is_not_silently_partial(corpus, monkeypatch):
    store, _, _ = corpus
    run = auto_run(corpus)
    monkeypatch.setattr(selector, 'BATCH_CHARS', 1)
    client = SelectorClient()
    with pytest.raises(ValueError, match='budget'):
        selector.select_roles(store, run, client)
    assert not client.calls


def two_batch_corpus(corpus, monkeypatch):
    from requirement_reuse_service.workflow.storage import canonical
    store, snapshot, _ = corpus
    units = [store.get('evidence', eid) for eid in snapshot['evidence_ids']]
    monkeypatch.setattr(selector, 'BATCH_CHARS', max(len(canonical(unit)) for unit in units) + 10)
    assert len(units) == 2


def test_scan_beyond_the_batch_limit_fails_before_any_call_and_names_the_needed_limit(corpus, monkeypatch):
    store, _, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '1')
    run = auto_run(corpus)
    assert run['role_manifest']['max_batches'] == 1
    client = SelectorClient()
    with pytest.raises(ValueError, match=r'exceeds 1 source batches \(2 needed\).*at least 2'):
        selector.select_roles(store, run, client)
    assert not client.calls


def test_batch_limit_is_recorded_with_the_run_and_kept_when_the_setting_changes(corpus, monkeypatch):
    store, snapshot, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '2')
    run = auto_run(corpus, max_roles=1)
    # The run keeps the limit it was created with, so a later, lower setting cannot strand it.
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '1')
    manifest = selector.select_roles(store, run, SelectorClient())
    assert manifest['status'] == 'completed' and manifest['max_batches'] == 2 and manifest['total_batches'] == 2
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    selector.verify_manifest(manifest)
    # A manifest saved before the limit was recorded is scanned under the default.
    legacy = auto_run(corpus, max_roles=1)
    assert legacy['role_manifest']['max_batches'] == 1
    del legacy['role_manifest']['max_batches']
    assert selector.select_roles(store, legacy, SelectorClient())['total_batches'] == 2


@pytest.mark.parametrize('value', ['0', '129', 'many', '-3', '2.5'])
def test_invalid_batch_limit_is_rejected_when_an_automatic_run_is_created(corpus, monkeypatch, value):
    store, snapshot, _ = corpus
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', value)
    with pytest.raises(ValueError, match='RQ1_ROLE_SELECTION_MAX_BATCHES'):
        auto_run(corpus)
    # Runs without a source scan do not read the setting.
    manual = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                      role_ids=['consumer_discovery']))
    assert 'max_batches' not in manual['role_manifest']


def test_default_batch_limit_is_unchanged(monkeypatch):
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES', raising=False)
    monkeypatch.setattr(selector, 'BATCH_CHARS', 100)          # one 61-character unit per batch
    assert selector.selection_batch_limit() == 32
    units = [{'evidence_id': f'u{i:02d}', 'content': 'x' * 30} for i in range(33)]
    assert len(selector.batches_for(units[:32])) == 32
    with pytest.raises(ValueError, match=r'exceeds 32 source batches \(33 needed\)'):
        selector.batches_for(units)
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '64')
    assert len(selector.batches_for(units)) == 33


def test_mock_automatic_and_override_api_keep_original_run_and_record_actor(corpus, monkeypatch):
    store, snapshot, _ = corpus
    api = TestClient(app)
    monkeypatch.setenv('RQ1_LOCAL_REVIEWER', 'researcher')
    first = api.post('/api/rq1/v2/runs', json={'snapshot_id': snapshot['snapshot_id'], 'strategy': 'mock', 'role_selection': 'automatic'})
    assert first.status_code == 202, first.text
    original = store.get('run', first.json()['run_id'])
    assert original['role_manifest']['execution'] == 'offline_demo'
    assert original['model_calls'] == []
    proposal = selector.proposed_defaults()[0].model_dump(mode='json')
    proposal['label'] = 'Regional data consumer'
    payload = {'snapshot_id': snapshot['snapshot_id'], 'strategy': 'mock', 'role_selection': 'override',
               'role_overrides': [proposal], 'based_on_run_id': original['run_id'], 'override_rationale': 'Scope the consumer role.'}
    response = api.post('/api/rq1/v2/runs', json=payload)
    assert response.status_code == 202, response.text
    revised = store.get('run', response.json()['run_id'])
    assert revised['role_manifest']['override']['actor'] == 'researcher'
    assert revised['role_manifest']['override']['parent_manifest_hash'] == original['role_manifest']['manifest_hash']
    assert revised['role_manifest']['selected_roles'][0]['label'] == 'Regional data consumer'
    assert store.get('run', original['run_id']) == original
    other = freeze_snapshot(store, SnapshotRequest(source_version_ids=snapshot['source_version_ids'], name='Different frozen corpus'))
    assert api.post('/api/rq1/v2/runs', json={**payload, 'snapshot_id': other['snapshot_id']}).status_code == 422
    assert api.post('/api/rq1/v2/runs', json={**payload, 'role_overrides': [proposal, proposal]}).status_code == 422


def test_critic_is_retained_even_with_many_contributors_and_manifest_tampering_fails(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    manifest = selector.select_roles(store, run, SelectorClient())
    run['role_manifest'] = deepcopy(manifest)
    run['role_manifest']['extraction_roles'][0]['purpose'] = 'Tampered purpose'
    with pytest.raises(ValueError, match='hash mismatch'):
        selector.panel_roles(run)
    record = record_from_observation(run['run_id'], Observation(observation_id='o', role_id='r0', statement='A need', evidence_links=[]))
    record.contributing_roles = ['r0', 'r1', 'r2', 'r3', 'r4']
    case = make_case(run, [record], ['scope'])
    assert case['participants'] == ['r0', 'r1', 'r2', 'grounding_scope_critic']


@pytest.mark.parametrize('quote, offset, expected_code, expected_offset', [
    ('need data', None, None, 20),
    ('Operators', None, 'quote_ambiguous', None),
    ('Operators', 10, None, 10),
    ('Operators', 1, 'invalid_offset', None),
    ('Operators  need data', None, 'quote_absent', None),
    ('Missing text', 0, 'quote_absent', None),
])
def test_role_citations_distinguish_exact_absent_repeated_and_bad_offsets(corpus, quote, offset, expected_code, expected_offset):
    store, _, _ = corpus
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(
        name='repeated.md', content='Operators Operators need data'), source_role='stakeholder_need'))
    unit = next(item for item in store.list('evidence') if item['source_version_id'] == source['source_version_id'])
    proposal = RoleProposal(**{**selector.proposed_defaults()[0].model_dump(), 'basis': 'documented',
        'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': quote, 'quote_start': offset}]})
    if expected_code:
        with pytest.raises(selector.RoleCitationError) as caught:
            selector.validate_proposal(store, proposal, [unit['evidence_id']], [])
        assert [error['code'] for error in caught.value.errors] == [expected_code]
        if expected_code == 'quote_absent':
            assert 'offset cannot repair' in str(caught.value)
    else:
        selector.validate_proposal(store, proposal, [unit['evidence_id']], [])
        assert proposal.evidence_links[0].quote_start == expected_offset


def test_overlapping_quote_occurrences_are_ambiguous(corpus):
    store, _, _ = corpus
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='overlap.md', content='banana'),
                                                source_role='stakeholder_need'))
    unit = next(item for item in store.list('evidence') if item['source_version_id'] == source['source_version_id'])
    proposal = RoleProposal(**{**selector.proposed_defaults()[0].model_dump(), 'basis': 'documented',
        'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': 'ana'}]})
    with pytest.raises(selector.RoleCitationError, match='more than once'):
        selector.validate_proposal(store, proposal, [unit['evidence_id']], [])


class RepairClient(SelectorClient):
    def __init__(self, repair='valid'):
        super().__init__()
        self.repair = repair
        self.discovery = None

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        data = json.loads(user)
        if output_model.__name__ == 'RoleCandidates':
            result = super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)
            bad = result.candidates[0].model_copy(deep=True)
            bad.label = 'Data publisher'
            bad.evidence_links[0].quote = 'Reconstructed text absent from the unit'
            result.candidates.append(bad)
            self.discovery = result.model_dump(mode='json')
            return result
        if output_model.__name__ == 'RoleCitationCorrections':
            self.calls.append((output_model.__name__, data))
            if self.repair == 'provider_failure':
                raise RuntimeError('Connection interrupted')
            span = data['source_spans'][0]
            response = {'corrections': [{'candidate_index': 0 if self.repair == 'wrong_target' else 1,
                'source_span_ids': ['missing-span' if self.repair == 'invalid' else span['span_id']]}]}
            return output_model.model_validate(response)
        return super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)


def test_citation_repair_is_targeted_once_and_keeps_originals_and_valid_roles(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    client = RepairClient()
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    assert [name for name, _ in client.calls] == ['RoleCandidates', 'RoleCitationCorrections', 'RolePanel']
    discovery, repair = manifest['validation_attempts']
    assert discovery['candidates'] == client.discovery['candidates']
    assert [item['status'] for item in discovery['validation_report']] == ['valid', 'invalid']
    assert discovery['validation_report'][1]['errors'][0]['code'] == 'quote_absent'
    assert discovery['candidates'][0]['evidence_links'][0]['quote_start'] is None
    assert discovery['candidates'][1]['evidence_links'][0]['quote'] == 'Reconstructed text absent from the unit'
    assert repair['status'] == 'valid'
    repair_input = next(data for name, data in client.calls if name == 'RoleCitationCorrections')
    assert [item['candidate_index'] for item in repair_input['invalid_candidates']] == [1]
    for index, candidate in enumerate(manifest['candidates']):
        original = discovery['candidates'][index]
        assert {key: candidate[key] for key in original if key != 'evidence_links'} == {
            key: value for key, value in original.items() if key != 'evidence_links'}
        assert candidate['basis'] == 'documented'
        assert candidate['evidence_links'][0]['quote_start'] == 0
    assert manifest['candidates'][0]['evidence_links'][0]['quote'] == discovery['candidates'][0]['evidence_links'][0]['quote']
    assert len(store.get('run', run['run_id'])['model_calls']) == 3


@pytest.mark.parametrize('mode', ['invalid', 'wrong_target', 'provider_failure'])
def test_failed_citation_repair_never_falls_back_or_repeats_on_resume(corpus, mode):
    store, _, _ = corpus
    run = auto_run(corpus)
    client = RepairClient(repair=mode)
    execute_run(store, run['run_id'], client)
    failed = store.get('run', run['run_id'])
    assert failed['status'] == failed['role_manifest']['status'] == failed['stages']['role_selection'] == 'failed'
    manifest = failed['role_manifest']
    assert manifest['selected_roles'] == [] and manifest['candidates'] == []
    assert 'fallback_reason' not in manifest
    assert len(manifest['validation_attempts']) == 2
    assert len(manifest['validation_attempts'][0]['candidates']) == 2
    assert [name for name, _ in client.calls] == ['RoleCandidates', 'RoleCitationCorrections']
    second_client = RepairClient()
    with pytest.raises(ValueError, match='already attempted or interrupted'):
        selector.select_roles(store, failed, second_client)
    assert not second_client.calls


def test_policy_change_and_interrupted_repair_require_new_run(corpus):
    store, _, _ = corpus
    old_run = auto_run(corpus)
    old_run['role_manifest']['policy_version'] = 'rq1-stakeholder-selection-v1'
    with pytest.raises(ValueError, match='new run'):
        selector.select_roles(store, old_run, SelectorClient())
    current = auto_run(corpus)
    current['role_manifest']['validation_attempts'] = [{'batch_index': 0, 'phase': 'citation_repair', 'status': 'started'}]
    with pytest.raises(ValueError, match='already attempted or interrupted'):
        selector.ensure_selection_resumable(current['role_manifest'])
    historical = {**old_run['role_manifest'], 'status': 'completed'}
    selector.ensure_selection_resumable(historical)


def test_non_citation_provider_error_does_not_trigger_repair(corpus):
    class FailingDiscovery(SelectorClient):
        def generate_structured(self, **kwargs):
            self.calls.append(kwargs['output_model'].__name__)
            raise RuntimeError('Provider unavailable')
    store, _, _ = corpus
    run = auto_run(corpus)
    client = FailingDiscovery()
    execute_run(store, run['run_id'], client)
    assert client.calls == ['RoleCandidates']
    failed = store.get('run', run['run_id'])
    assert failed['role_manifest']['validation_attempts'] == []
    assert failed['status'] == 'failed'


def test_discovery_schema_bounds_output_to_requested_panel_without_losing_source_scan(corpus):
    class CapturingSelector(SelectorClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCandidates':
                schema = kwargs['output_model'].model_json_schema()
                assert schema['properties']['candidates']['maxItems'] == 2
                assert json.loads(kwargs['user'])['max_candidates'] == 2
                assert schema['$defs']['ConciseRoleProposal']['properties']['purpose']['maxLength'] == 180
                assert kwargs['max_tokens'] == 8000
            return super().generate_structured(**kwargs)
    store, snapshot, _ = corpus
    run = auto_run(corpus, max_roles=2)
    manifest = selector.select_roles(store, run, CapturingSelector())
    assert manifest['discovery_candidate_limit'] == 2
    assert manifest['discovery_max_output_tokens'] == 8000
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    assert selector.discovery_contract(8).model_json_schema()['properties']['candidates']['maxItems'] == 8
    proposal = selector.proposed_defaults()[0].model_dump(mode='json')
    with pytest.raises(ValidationError, match='at most 2 items'):
        selector.discovery_contract(2).model_validate({'candidates': [proposal] * 3})


def test_discovery_allows_longer_exact_citation_without_truncating_it(corpus):
    store, snapshot, _ = corpus
    unit = store.get('evidence', snapshot['evidence_ids'][0])
    quote = unit['content'] + ' ' + ('Context about catalogue operations. ' * 5)
    assert 160 < len(quote) <= 400
    proposal = selector.proposed_defaults()[0].model_dump(mode='json')
    proposal['evidence_links'] = [{'evidence_id': unit['evidence_id'], 'quote': quote}]
    parsed = selector.discovery_contract(4).model_validate({'candidates': [proposal]})
    assert parsed.candidates[0].evidence_links[0].quote == quote
    # Accepting the length does not accept unsupported text as source evidence.
    with pytest.raises(selector.RoleCitationError):
        selector.validate_proposal(store, parsed.candidates[0], snapshot['evidence_ids'], [])


def test_cutoff_failure_records_provider_usage_without_proceeding_to_extraction(corpus, monkeypatch):
    import httpx
    from requirement_reuse_service.llm.client import OpenAICompatibleClient
    from requirement_reuse_service.llm.config import LLMConfig
    from requirement_reuse_service.workflow.evaluation import workflow_metrics

    store, _, _ = corpus
    run = auto_run(corpus)
    config = LLMConfig(provider='openai-compatible', model='scripted',
                       base_url='https://cutoff-test.invalid/v1', api_key='secret-not-for-audit')
    result = httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{"candidates":['}}],
        'usage': {'prompt_tokens': 1000, 'completion_tokens': 8000, 'total_tokens': 9000}},
        request=httpx.Request('POST', 'https://cutoff-test.invalid/v1/chat/completions'))
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: result)
    execute_run(store, run['run_id'], OpenAICompatibleClient(config))
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'failed'
    assert saved['role_manifest']['processed_evidence_ids'] == []
    assert not saved['observations'] and not saved['requirements']
    assert len(saved['model_calls']) == 1
    call = saved['model_calls'][0]
    assert call['finish_reason'] == 'length'
    assert call['token_usage'] == {'prompt_tokens': 1000, 'completion_tokens': 8000, 'total_tokens': 9000}
    assert 'output token limit' in call['error']
    assert 'secret-not-for-audit' not in json.dumps(saved)
    assert workflow_metrics(saved)['model_calls']['actual_token_usage'] == call['token_usage']
    saved['model_calls'].append({**call, 'token_usage': None})
    metrics = workflow_metrics(saved)['model_calls']
    assert metrics['actual_token_usage'] is None
    assert metrics['recorded_token_usage']['total_tokens'] == 9000
    assert metrics['calls_without_token_usage'] == 1


def test_source_span_catalogue_preserves_raw_text_offsets_and_full_coverage():
    content = 'Germany is split as Ger-\nmany. Same actor. Same actor.\n' + ('x' * 805)
    spans = selector.source_spans_for([{'evidence_id': 'unit-a', 'content': content}])
    assert len({span['span_id'] for span in spans}) == len(spans)
    position = 0
    for span in spans:
        start = span['quote_start']
        assert content[start:start + len(span['quote'])] == span['quote']
        assert 0 < len(span['quote']) <= 400
        assert span['evidence_id'] == 'unit-a'
        # Excerpts are ordered and only line breaks lie between them: no source text is hidden.
        assert start >= position and not content[position:start].strip()
        position = start + len(span['quote'])
    assert not content[position:].strip()
    # The two short lines form one excerpt that keeps the hyphenated line break as written.
    assert spans[0]['quote'] == 'Germany is split as Ger-\nmany. Same actor. Same actor.'
    assert [len(span['quote']) for span in spans[1:]] == [400, 400, 5]


def test_unresolved_span_selection_stays_failed_without_generic_fallback(corpus):
    class UnsupportedClient(RepairClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCitationCorrections':
                self.calls.append(('RoleCitationCorrections', json.loads(kwargs['user'])))
                return kwargs['output_model'].model_validate({'corrections': [
                    {'candidate_index': 1, 'source_span_ids': [], 'unresolved_reason': 'No excerpt supports this stakeholder.'}]})
            return super().generate_structured(**kwargs)
    store, _, _ = corpus
    run = auto_run(corpus)
    execute_run(store, run['run_id'], UnsupportedClient())
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'failed'
    attempt = saved['role_manifest']['validation_attempts'][-1]
    assert attempt['status'] == 'invalid'
    assert attempt['source_spans']
    assert attempt['validation_report'][0]['errors'][0]['message'] == 'No excerpt supports this stakeholder.'
    assert not saved['role_runs']
