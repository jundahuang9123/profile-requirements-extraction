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
    RolePanel, SnapshotRequest, SourceRequest)
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
                'source_span_ids': ['missing-span' if self.bad_quote else unit['source_spans'][0]['span_id']],
                'task_ids': ['CQ-1']}]}
        elif output_model.__name__ == 'RoleCitationCorrections':
            response = {'corrections': [{'candidate_index': item['candidate_index'],
                'source_span_ids': [], 'unresolved_reason': 'No valid quotation supplied by test client.'} for item in data['invalid_candidates']]}
        elif output_model.__name__ == 'RoleRegistry':
            ids = [c['candidate_id'] for c in data['candidates']]
            representative = next((c['candidate_id'] for c in data['candidates'] if c['basis'] == 'documented'), ids[0])
            response = {'groups': [{'representative_id': representative, 'member_ids': ids,
                                   'rationale': 'Equivalent scripted operational interests.'}]}
        elif output_model.__name__ == 'StakeholderPanel':
            if self.fail_reducer:
                raise RuntimeError('Interrupted selection')
            entries = data['entries']
            ids = sorted(entries, key=lambda c: (('documented', 'inferred', 'proposed').index(c['basis']), c['entry_id']))
            response = {'verdicts': [{'entry_id': c['entry_id'], 'relevant': True,
                                     'reason': 'Scripted operational relevance.'} for c in entries],
                        'kept_ids': [c['entry_id'] for c in ids[:data['max_roles']]]}
            if self.duplicate:
                response['verdicts'].append({'entry_id': entries[0]['entry_id'], 'relevant': False,
                                             'reason': 'Conflicting scripted verdict.'})
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
                'extension_kind': 'new_information_need', 'base_property': None,
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
    return new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_selection='automatic', **kwargs))


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
    assert metrics['role_selection']['model_calls'] == 4
    assert metrics['role_selection']['basis_counts'] == {'documented': 1}
    assert Store(str(store.path)).get('role_manifest', manifest['manifest_hash']) == manifest


def test_conflicting_panel_verdicts_are_repaired_and_audited_not_fatal(corpus):
    """An entry given both verdicts, twice, counts as relevant; the run continues with an audit."""
    from requirement_reuse_service.workflow.stakeholder_registry import ACCOUNTING_REPAIR_POLICY
    store, _, _ = corpus
    run = auto_run(corpus)
    client = SelectorClient(duplicate=True)
    execute_run(store, run['run_id'], client)
    result = store.get('run', run['run_id'])
    manifest = result['role_manifest']
    assert manifest['status'] == 'completed', result['diagnostics']
    record = manifest['panel_calls'][-1]
    assert [e['code'] for e in record['validation_errors']] == ['verdict_accounting']
    assert record['correction']['status'] == 'invalid'
    assert record['repair']['policy'] == ACCOUNTING_REPAIR_POLICY
    conflicts = record['repair']['changes']['correction']['conflicting_verdicts_counted_relevant']
    assert conflicts and all(v['relevant'] for v in record['result']['verdicts'] if v['entry_id'] in conflicts)
    assert sum(contract == 'StakeholderPanel' for contract, _ in client.calls) == 2
    assert result['stages']['role_selection'] == 'completed'


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


def test_panel_lineage_ids_stay_internal_and_accounting_gets_one_saved_correction(corpus):
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    old_id = 'role-candidate-previous-a'
    run['role_manifest']['selected_roles'] = [selector.as_selected(
        selector.proposed_defaults()[0], candidate_ids=[old_id])]
    class LineagePanelClient(SelectorClient):
        panel_calls = 0
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ != 'StakeholderPanel':
                return super().generate_structured(**kwargs)
            data = json.loads(kwargs['user'])
            self.calls.append(('StakeholderPanel', data)); self.panel_calls += 1
            ids = [entry['entry_id'] for entry in data['entries']]
            assert old_id not in ids
            if self.panel_calls == 1:
                return kwargs['output_model'].model_validate({'verdicts': [
                    {'entry_id': old_id, 'relevant': True, 'reason': 'Invalid historical ID.'}],
                    'kept_ids': [old_id]})
            assert data['validation_errors'][0]['code'] == 'verdict_accounting'
            return kwargs['output_model'].model_validate({'verdicts': [
                {'entry_id': i, 'relevant': True, 'reason': 'Relevant publication perspective.'} for i in ids],
                'kept_ids': ids[:data['max_roles']]})
    client = LineagePanelClient()
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    assert client.panel_calls == 2
    assert manifest['panel_calls'][0]['correction']['status'] == 'valid'
    assert manifest['panel_calls'][0]['validation_errors'][0]['code'] == 'verdict_accounting'
    assert all(old_id not in role['candidate_ids'] for role in manifest['selected_roles'])


def test_all_batches_scanned_with_bounded_panel_and_lineage(corpus, monkeypatch):
    store, snapshot, _ = corpus
    units = [store.get('evidence', eid) for eid in snapshot['evidence_ids']]
    from requirement_reuse_service.workflow.storage import canonical
    monkeypatch.setattr(selector, 'BATCH_CHARS', max(len(canonical(unit)) for unit in units) + 10)
    run = auto_run(corpus, max_roles=1)
    client = SelectorClient()
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    assert manifest['total_batches'] == 2
    assert len(manifest['batch_reports']) == 2
    assert len(manifest['selection_rounds']) == 1
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


def test_a_new_run_scans_the_whole_corpus_without_a_setting(corpus, monkeypatch):
    store, snapshot, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES', raising=False)
    run = auto_run(corpus, max_roles=1)
    # Known when the run is created, before any call, and shown in the workbench.
    assert run['role_manifest']['max_batches'] == run['role_manifest']['total_batches'] == 2
    manifest = selector.select_roles(store, run, SelectorClient())
    assert manifest['status'] == 'completed' and manifest['total_batches'] == 2
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])


def test_a_corpus_beyond_the_cap_or_the_ceiling_is_refused_when_the_run_is_created(corpus, monkeypatch):
    store, snapshot, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '1')
    with pytest.raises(ValueError, match=r'needs 2 role-selection batches, more than RQ1_ROLE_SELECTION_MAX_BATCHES=1'):
        auto_run(corpus)
    # Through the API the refusal is a 422 with the reason, and no run is saved.
    before = len(store.list('run'))
    response = TestClient(app).post('/api/rq1/v2/runs', json={
        'snapshot_id': snapshot['snapshot_id'], 'strategy': 'multi_agent', 'role_selection': 'automatic'})
    assert response.status_code == 422 and 'RQ1_ROLE_SELECTION_MAX_BATCHES=1' in response.text
    assert len(store.list('run')) == before
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES')
    monkeypatch.setattr(selector, 'MAX_BATCHES_CEILING', 1)
    with pytest.raises(ValueError, match=r'needs 2 role-selection batches, more than the 1 one scan may read'):
        auto_run(corpus)


def test_a_run_keeps_the_scan_size_it_was_created_with(corpus, monkeypatch):
    store, snapshot, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES', raising=False)
    run = auto_run(corpus, max_roles=1)
    # A cap set later does not strand a run that was already created.
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '1')
    manifest = selector.select_roles(store, run, SelectorClient())
    assert manifest['status'] == 'completed' and manifest['max_batches'] == 2
    selector.verify_manifest(manifest)
    # A run created under an earlier, lower limit keeps it: the scan fails before any call.
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES')
    earlier = auto_run(corpus, max_roles=1)
    earlier['role_manifest']['max_batches'] = 1
    client = SelectorClient()
    with pytest.raises(ValueError, match=r'needs 2 source batches, more than the 1 this run was created with.*new run'):
        selector.select_roles(store, earlier, client)
    assert not client.calls
    # A manifest that recorded no limit was scanned under the earlier default of 32.
    del earlier['role_manifest']['max_batches']
    assert selector.select_roles(store, earlier, SelectorClient())['total_batches'] == 2


@pytest.mark.parametrize('value', ['0', '129', 'many', '-3', '2.5', '\u00b2'])
def test_invalid_batch_limit_is_rejected_when_an_automatic_run_is_created(corpus, monkeypatch, value):
    store, snapshot, _ = corpus
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', value)
    with pytest.raises(ValueError, match='RQ1_ROLE_SELECTION_MAX_BATCHES'):
        auto_run(corpus)
    # Runs without a source scan do not read the setting.
    manual = new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                      role_ids=['consumer_discovery']))
    assert 'max_batches' not in manual['role_manifest']


def test_without_a_cap_a_scan_may_read_up_to_the_ceiling(monkeypatch):
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES', raising=False)
    monkeypatch.setattr(selector, 'BATCH_CHARS', 100)          # one unit per batch
    assert selector.selection_batch_limit() is None
    units = [{'evidence_id': f'u{i:03d}', 'content': 'x' * 30} for i in range(129)]
    assert len(selector.batches_for(units[:128])) == 128
    with pytest.raises(ValueError, match=r'needs 129 source batches, more than the limit of 128'):
        selector.batches_for(units)
    monkeypatch.setenv('RQ1_ROLE_SELECTION_MAX_BATCHES', '32')
    with pytest.raises(ValueError, match=r'needs 33 source batches, more than the limit of 32'):
        selector.batches_for(units[:33])


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


def legacy_repair_run(corpus, unknown_tasks=False):
    """A saved pre-v10 discovery still receives its bounded citation correction."""
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    unit = selector.pack_batches(selector.selection_units(store, snapshot))[0][0]
    good = {'label': 'Catalogue operator', 'stakeholders': ['Catalogue operators'], 'basis': 'documented',
        'purpose': 'Examine catalogue maintenance needs.', 'rationale': 'The source states an operational responsibility.',
        'focus_questions': ['What metadata must be maintained?'],
        'evidence_links': [{'evidence_id': unit['evidence_id'], 'quote': unit['content']}],
        'task_ids': ['invented-CQ' if unknown_tasks else 'CQ-1']}
    bad = deepcopy(good)
    bad['label'] = 'Data publisher'
    bad['evidence_links'][0]['quote'] = 'Reconstructed text absent from the unit'
    candidates = [RoleProposal.model_validate(good), RoleProposal.model_validate(bad)]
    _, report = selector.validate_candidates(store, candidates, snapshot['evidence_ids'], snapshot['user_tasks'], {})
    run['role_manifest']['validation_attempts'] = [{'batch_index': 0, 'phase': 'discovery',
        'candidates': [c.model_dump(mode='json') for c in candidates], 'status': 'invalid', 'validation_report': report}]
    store.mutate(run['run_id'], None, 'test_legacy_discovery',
                 lambda current: current.update(role_manifest=deepcopy(run['role_manifest'])))
    return run


class RepairClient(SelectorClient):
    def __init__(self, repair='valid'):
        super().__init__()
        self.repair = repair

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        data = json.loads(user)
        if output_model.__name__ == 'RoleCitationCorrections':
            self.calls.append((output_model.__name__, data))
            if self.repair == 'provider_failure':
                raise RuntimeError('Connection interrupted')
            span = data['source_spans'][0]
            response = {'corrections': [{'candidate_index': 0 if self.repair == 'wrong_target' else 1,
                'source_span_ids': ([] if self.repair == 'unsupported' else
                    ['missing-span' if self.repair == 'invalid' else span['span_id']]),
                'unresolved_reason': 'The supplied excerpts do not establish this perspective.'
                    if self.repair == 'unsupported' else ''}]}
            return output_model.model_validate(response)
        return super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)


def test_citation_repair_is_targeted_once_and_keeps_originals_and_valid_roles(corpus):
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    original = deepcopy(run['role_manifest']['validation_attempts'][0]['candidates'])
    client = RepairClient()
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    names = [name for name, _ in client.calls]
    assert names.count('RoleCitationCorrections') == 1 and names.count('StakeholderPanel') == 1
    assert 'RoleRegistry' in names and 'RoleCandidates' not in names
    discovery, repair = manifest['validation_attempts']
    assert discovery['candidates'] == original
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
    assert len(store.get('run', run['run_id'])['model_calls']) == len(client.calls)


def test_unsupported_role_is_preserved_as_uncited_proposed_and_audited(corpus):
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    client = RepairClient(repair='unsupported')
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    proposed = next(candidate for candidate in manifest['candidates'] if candidate['label'] == 'Data publisher')
    assert proposed['basis'] == 'proposed' and proposed['evidence_links'] == []
    assert 'did not establish documentary support' in proposed['rationale']
    audit = manifest['validation_attempts'][-1]
    assert audit['status'] == 'valid'
    assert audit['unresolved_candidates'][0]['disposition'] == 'retained_as_proposed_without_citation'
    assert audit['unresolved_candidates'][0]['reason'] == 'The supplied excerpts do not establish this perspective.'
    assert manifest['unresolved_role_candidates'][0]['batch_index'] == 0
    assert 'RoleCitationCorrections' in [name for name, _ in client.calls]
    assert manifest['status'] == 'completed'
    selector.verify_manifest(manifest)


def test_v7_unfinished_scan_is_refused_without_repeating_inference(corpus):
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    batch = selector.pack_batches(selector.selection_units(store, snapshot))[0]
    evidence_id = batch[0]['evidence_id']
    bad = selector.proposed_defaults()[0].model_dump(mode='json')
    bad.update(basis='documented', evidence_links=[{'evidence_id': evidence_id, 'quote': 'not in source'}])
    spans = selector.source_spans_for(batch)
    run['role_manifest'].update(policy_version='rq1-stakeholder-selection-v7', status='failed',
        last_error='Role quotation repair could not select supporting source excerpts; inspect the validation audit.',
        validation_attempts=[
            {'batch_index': 0, 'phase': 'discovery', 'candidates': [bad],
             'validation_report': [{'candidate_index': 0, 'label': bad['label'], 'status': 'invalid',
                 'errors': [{'code': 'quote_absent', 'repairable': True, 'message': 'missing literal quote'}]}]},
            {'batch_index': 0, 'phase': 'citation_repair', 'status': 'invalid',
             'source_spans': spans, 'corrections': [{'candidate_index': 0, 'source_span_ids': [],
                 'unresolved_reason': 'No excerpt supports this role.'}]}
        ])
    before = deepcopy(run['role_manifest'])
    client = SelectorClient()
    with pytest.raises(ValueError, match='policy has changed'):
        selector.select_roles(store, run, client)
    assert not client.calls and run['role_manifest'] == before


@pytest.mark.parametrize('mode', ['invalid', 'wrong_target'])
def test_unsupported_candidate_after_its_single_repair_stays_proposed_and_uncited(corpus, mode):
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    client = RepairClient(repair=mode)
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    assert [name for name, _ in client.calls].count('RoleCitationCorrections') == 1
    repair = next(a for a in manifest['validation_attempts'] if a['phase'] == 'citation_repair')
    assert repair['status'] == 'valid'
    assert repair['fallback']['policy'] == selector.CITATION_FALLBACK_POLICY
    assert repair['fallback']['retained_as_proposed'] == [1]
    assert repair['fallback']['ignored_correction_indices'] == ([0] if mode == 'wrong_target' else [])
    proposed = [c for c in manifest['candidates'] if c['label'] == 'Data publisher']
    assert len(proposed) == 1 and proposed[0]['basis'] == 'proposed' and proposed[0]['evidence_links'] == []
    assert proposed[0]['rationale'] == selector.UNSUPPORTED_RATIONALE
    kept = [c for c in manifest['candidates'] if c['label'] == 'Catalogue operator']
    assert kept[0]['basis'] == 'documented' and kept[0]['evidence_links']
    assert [u['disposition'] for u in manifest['unresolved_role_candidates']] == ['retained_as_proposed_after_failed_repair']
    # The original generated candidates are unchanged in the audit.
    assert manifest['validation_attempts'][0]['candidates'][1]['basis'] == 'documented'


def test_citation_repair_lost_to_the_provider_is_asked_once_more_on_resume(corpus):
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    broken = RepairClient(repair='provider_failure')
    execute_run(store, run['run_id'], broken)
    failed = store.get('run', run['run_id'])
    assert failed['status'] == 'failed' and 'Connection interrupted' in ' '.join(failed['diagnostics'])
    repair = next(a for a in failed['role_manifest']['validation_attempts'] if a['phase'] == 'citation_repair')
    assert repair['status'] == 'provider_failed'
    selector.ensure_selection_resumable(failed['role_manifest'])
    client = RepairClient()
    manifest = selector.select_roles(store, failed, TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    assert [name for name, _ in client.calls].count('RoleCitationCorrections') == 1
    repair = next(a for a in manifest['validation_attempts'] if a['phase'] == 'citation_repair')
    assert repair['status'] == 'valid' and 'fallback' not in repair
    assert repair['retries'] == [{'policy': selector.CITATION_RETRY_POLICY, 'previous_status': 'provider_failed',
                                  'error': 'Connection interrupted'}]
    assert all(c['basis'] == 'documented' for c in manifest['candidates'])


@pytest.mark.parametrize('basis, task_ids, with_evidence, expected_basis, expected_ids', [
    ('documented', ['unknown'], True, 'documented', []),
    ('documented', ['CQ-1', 'unknown'], True, 'documented', ['CQ-1']),
    ('inferred', ['unknown'], False, 'proposed', []),
    ('inferred', ['unknown', 'CQ-1'], False, 'inferred', ['CQ-1']),
    ('inferred', ['unknown'], True, 'inferred', []),
    ('proposed', ['unknown'], False, 'proposed', []),
    ('proposed', ['CQ-1'], False, 'proposed', ['CQ-1']),
])
def test_generated_task_links_do_not_invent_support_or_mutate_originals(
        corpus, basis, task_ids, with_evidence, expected_basis, expected_ids):
    store, snapshot, _ = corpus
    body = selector.proposed_defaults()[0].model_dump(mode='json')
    unit = store.get('evidence', snapshot['evidence_ids'][0])
    body.update(basis=basis, task_ids=task_ids, evidence_links=(
        [{'evidence_id': unit['evidence_id'], 'quote': unit['content']}] if with_evidence else []))
    original = RoleProposal.model_validate(body)
    before = original.model_dump(mode='json')
    normalized, audit = selector.normalize_generated_task_links([original], snapshot['user_tasks'])
    assert original.model_dump(mode='json') == before
    assert normalized[0].basis == expected_basis and normalized[0].task_ids == expected_ids
    assert normalized[0].evidence_links == original.evidence_links
    selector.validate_proposal(store, normalized[0], snapshot['evidence_ids'], snapshot['user_tasks'])
    if 'unknown' in task_ids:
        assert audit[0]['removed_task_ids'] == ['unknown']
        assert audit[0]['retained_task_ids'] == expected_ids
        assert audit[0]['resulting_basis'] == expected_basis
        with pytest.raises(selector.RoleCitationError, match='undeclared'):
            selector.validate_proposal(store, original, snapshot['evidence_ids'], snapshot['user_tasks'])
    else:
        assert not audit


@pytest.mark.parametrize('repair_mode', ['valid', 'unsupported'])
def test_unknown_task_and_bad_quote_are_independently_disposed_and_audited(corpus, repair_mode):
    store, _, _ = corpus
    run = legacy_repair_run(corpus, unknown_tasks=True)
    client = RepairClient(repair=repair_mode)
    manifest = selector.select_roles(store, run, TrackedClient(client, store, run['run_id']))
    names = [name for name, _ in client.calls]
    assert names.count('RoleCitationCorrections') == 1 and names.count('StakeholderPanel') == 1
    assert 'RoleRegistry' in names and 'RoleCandidates' not in names
    discovery, tasks, citation = manifest['validation_attempts']
    assert discovery['candidates'][0]['task_ids'] == ['invented-CQ']
    assert discovery['validation_report'][0]['errors'][0]['code'] == 'unknown_task'
    assert {error['code'] for error in discovery['validation_report'][1]['errors']} == {'unknown_task', 'quote_absent'}
    assert tasks['phase'] == 'task_reference_normalization' and len(tasks['corrections']) == 2
    assert not tasks['validation_report'][0]['errors']
    assert [error['code'] for error in tasks['validation_report'][1]['errors']] == ['quote_absent']
    assert citation['status'] == 'valid'
    assert all(candidate['task_ids'] == [] for candidate in manifest['candidates'])
    assert manifest['candidates'][0]['basis'] == 'documented'
    assert manifest['candidates'][1]['basis'] == ('documented' if repair_mode == 'valid' else 'proposed')
    repair_input = next(data for name, data in client.calls if name == 'RoleCitationCorrections')
    assert [item['candidate_index'] for item in repair_input['invalid_candidates']] == [1]
    assert all(error['code'] != 'unknown_task' for error in repair_input['invalid_candidates'][0]['validation_errors'])
    assert manifest['max_calls_per_batch'] == 2
    selector.verify_manifest(manifest)


def failed_unknown_task_run(corpus):
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    body = selector.proposed_defaults()[0].model_dump(mode='json')
    body.update(basis='inferred', task_ids=['not-a-declared-task'])
    _, report = selector.validate_candidates(store, [RoleProposal.model_validate(body)], snapshot['evidence_ids'],
                                             snapshot['user_tasks'], {})
    run['role_manifest'].update(policy_version='rq1-stakeholder-selection-v8', status='failed',
        last_error='Role selection contains non-repairable evidence/task validation errors; review the saved per-candidate validation audit.',
        validation_attempts=[{'batch_index': 0, 'phase': 'discovery', 'status': 'invalid',
                              'candidates': [body], 'validation_report': report}])
    return run


def test_v8_unfinished_scan_is_refused_without_changing_saved_discovery(corpus):
    store, _, _ = corpus
    run = failed_unknown_task_run(corpus)
    before = deepcopy(run)
    client = SelectorClient()
    with pytest.raises(ValueError, match='policy has changed'):
        selector.select_roles(store, run, client)
    assert not client.calls and run == before


@pytest.mark.parametrize('extra_error', ['source_unresolved', 'unrelated_failure', 'completed_batch'])
def test_v8_resume_migration_is_narrow_and_never_bypasses_integrity(corpus, extra_error):
    run = failed_unknown_task_run(corpus)
    manifest = run['role_manifest']
    if extra_error == 'source_unresolved':
        manifest['validation_attempts'][0]['validation_report'][0]['errors'].append(
            {'code': 'source_unresolved', 'repairable': False, 'message': 'invalid original bytes'})
    elif extra_error == 'unrelated_failure':
        manifest['last_error'] = 'Provider unavailable'
    else:
        manifest['selection_rounds'] = [{'batch_index': 0}]
    with pytest.raises(ValueError, match='new run'):
        selector.ensure_selection_resumable(manifest)


def test_resume_api_refuses_unfinished_old_policy_without_modifying_run(corpus, monkeypatch):
    from requirement_reuse_service.workflow import api as workflow_api
    store, _, _ = corpus
    run = failed_unknown_task_run(corpus)
    original_manifest = deepcopy(run['role_manifest'])
    def saved_failure(current):
        current.update(status='failed', role_manifest=deepcopy(original_manifest))
        current['stages']['role_selection'] = 'failed'
    saved = store.mutate(run['run_id'], None, 'test_failed_discovery', saved_failure)['run']
    monkeypatch.setattr(workflow_api, 'configured_client', lambda _request: SelectorClient())
    monkeypatch.setattr(workflow_api, 'execute_run', lambda *_args: None)
    response = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={
        'expected_version': saved['version'], 'idempotency_key': 'resume-v8-offline'})
    assert response.status_code == 422, response.text
    resumed = store.get('run', run['run_id'])
    assert resumed['role_manifest'] == original_manifest
    assert resumed['version'] == saved['version']
    assert not resumed['attempt_history']


def test_removed_task_link_never_masks_an_unresolved_source(corpus, monkeypatch):
    store, _, _ = corpus
    run = auto_run(corpus)

    class UnknownTaskClient(SelectorClient):
        def generate_structured(self, **kwargs):
            result = super().generate_structured(**kwargs)
            if kwargs['output_model'].__name__ == 'RoleCandidates':
                result.candidates[0].task_ids = ['unknown']
            return result

    monkeypatch.setattr(selector, 'resolve_evidence', lambda *_args: {'status': 'fail'})
    client = UnknownTaskClient()
    with pytest.raises(ValueError, match='non-repairable'):
        selector.select_roles(store, run, client)
    assert [name for name, _ in client.calls] == ['RoleCandidates']
    manifest = store.get('run', run['run_id'])['role_manifest']
    report = manifest['validation_attempts'][-1]['validation_report']
    assert [error['code'] for error in report[0]['errors']] == ['source_unresolved']
    assert not manifest['batch_reports'] and not manifest['selected_roles']


def test_task_normalization_with_no_declared_tasks_proposes_unsupported_inference():
    body = selector.proposed_defaults()[0].model_dump(mode='json')
    original = RoleProposal(**{**body, 'basis': 'inferred', 'task_ids': ['CQ-1']})
    normalized, audit = selector.normalize_generated_task_links([original], [])
    assert normalized[0].basis == 'proposed' and normalized[0].task_ids == []
    assert audit[0]['removed_task_ids'] == ['CQ-1']


def test_saved_valid_panel_correction_is_reused_without_a_second_call(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    execute_run(store, run['run_id'], SelectorClient(fail_reducer=True))
    partial = store.get('run', run['run_id'])
    manifest = partial['role_manifest']
    ids = [entry['entry_id'] for entry in manifest['registry']]
    manifest['panel_calls'][0].update(original={'verdicts': [{'entry_id': 'unknown-entry', 'relevant': True, 'reason': 'Invalid entry ID.'}], 'kept_ids': []},
        correction={'status': 'valid', 'result': {'verdicts': [
            {'entry_id': i, 'relevant': True, 'reason': 'Saved relevant disposition.'} for i in ids],
            'kept_ids': ids[:manifest['max_roles']]}})
    client = SelectorClient()
    completed = selector.select_roles(store, partial, client)
    assert completed['status'] == 'completed' and not client.calls


@pytest.mark.parametrize('status', ['started', 'provider_failed', 'invalid'])
def test_panel_correction_budget_remains_exhausted_on_resume(corpus, status):
    store, _, _ = corpus
    run = auto_run(corpus)
    run['role_manifest']['panel_accounting_repairs'] = [{'batch_index': 0, 'status': status}]
    client = SelectorClient()
    with pytest.raises(ValueError, match='interrupted or failed'):
        selector.select_roles(store, run, client)
    assert not client.calls


def test_unsupported_repair_migration_never_accepts_missing_span_ids():
    manifest = {'validation_attempts': [{'batch_index': 0, 'phase': 'discovery',
        'validation_report': [
            {'candidate_index': index, 'errors': [{'code': 'quote_absent', 'repairable': True}]} for index in range(2)]}]}
    attempt = {'phase': 'citation_repair', 'status': 'invalid', 'batch_index': 0,
        'source_spans': [{'span_id': 'provided-span'}], 'corrections': [
            {'candidate_index': 0, 'source_span_ids': [], 'unresolved_reason': 'No support.'},
            {'candidate_index': 1, 'source_span_ids': ['missing-span'], 'unresolved_reason': ''}]}
    assert not selector._recoverable_unsupported_citation_repair(attempt, manifest)
    attempt['corrections'][1]['source_span_ids'] = ['provided-span']
    assert selector._recoverable_unsupported_citation_repair(attempt, manifest)


def test_policy_change_and_interrupted_repair_require_new_run(corpus):
    store, _, _ = corpus
    old_run = auto_run(corpus)
    old_run['role_manifest']['policy_version'] = 'rq1-stakeholder-selection-v1'
    with pytest.raises(ValueError, match='new run'):
        selector.select_roles(store, old_run, SelectorClient())
    current = auto_run(corpus)
    # An interrupted citation repair no longer blocks resume: it is asked again.
    current['role_manifest']['validation_attempts'] = [{'batch_index': 0, 'phase': 'citation_repair', 'status': 'started'}]
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
                assert schema['$defs']['SourceSpanRoleProposal']['properties']['purpose']['maxLength'] == 180
                assert 'evidence_links' not in schema['$defs']['SourceSpanRoleProposal']['properties']
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


def test_discovery_selects_exact_excerpts_without_generating_quotes_or_offsets(corpus):
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    client = SelectorClient()
    manifest = selector.select_roles(store, run, client)
    data = next(data for name, data in client.calls if name == 'RoleCandidates')
    assert all('content' not in unit and unit['source_spans'] for unit in data['evidence_units'])
    audit = manifest['validation_attempts'][0]
    assert audit['citation_policy'] == 'source-excerpt-ids-v1'
    assert 'evidence_links' not in audit['generated_candidates'][0]
    assert audit['generated_candidates'][0]['source_span_ids']
    catalogue = selector.source_spans_for(selector.pack_batches(selector.selection_units(store, snapshot))[0])
    assert audit['source_catalogue_hash'] == selector.digest(catalogue)
    chosen = catalogue[0]
    assert audit['candidates'][0]['evidence_links'] == [
        {key: chosen[key] for key in ('evidence_id', 'quote', 'quote_start')}]
    for candidate in manifest['candidates']:
        selector.validate_proposal(store, RoleProposal.model_validate(
            {key: candidate[key] for key in RoleProposal.model_fields}),
            snapshot['evidence_ids'], snapshot['user_tasks'])


def test_span_contract_rejects_unknown_duplicate_and_generated_text_without_discarding_roles():
    catalogue = selector.source_spans_for([{'evidence_id': 'u', 'content': 'Actor. ' * 150}])
    contract = selector.span_discovery_contract(4, catalogue)
    body = {**selector.proposed_defaults()[0].model_dump(mode='json', exclude={'evidence_links'}),
            'basis': 'documented', 'source_span_ids': [catalogue[1]['span_id']]}
    parsed = contract.model_validate({'candidates': [body]})
    original = parsed.model_dump(mode='json')
    roles = selector.materialize_roles(parsed, catalogue)
    assert roles[0].evidence_links[0].quote == catalogue[1]['quote']
    assert roles[0].evidence_links[0].quote_start == catalogue[1]['quote_start']
    assert parsed.model_dump(mode='json') == original
    assert len(roles[0].evidence_links[0].quote) <= 400
    for ids in (['absent'], [catalogue[0]['span_id']] * 2):
        with pytest.raises(ValidationError):
            contract.model_validate({'candidates': [{**body, 'source_span_ids': ids}]})
    with pytest.raises(ValidationError, match='extra_forbidden'):
        contract.model_validate({'candidates': [{**body, 'quote': 'x' * 401}]})
    # Defensive validation also protects against a nonconforming custom client.
    parsed.candidates[0].source_span_ids = ['outside-batch']
    with pytest.raises(ValueError, match='outside this batch'):
        selector.materialize_roles(parsed, catalogue)


def test_empty_span_catalogue_permits_only_proposed_or_task_supported_roles():
    contract = selector.span_discovery_contract(4, [])
    body = selector.proposed_defaults()[0].model_dump(mode='json', exclude={'evidence_links'})
    parsed = contract.model_validate({'candidates': [body]})
    assert selector.materialize_roles(parsed, [])[0].basis == 'proposed'
    with pytest.raises(ValidationError):
        contract.model_validate({'candidates': [{**body, 'basis': 'documented'}]})
    with pytest.raises(ValidationError):
        contract.model_validate({'candidates': [{**body, 'source_span_ids': ['s0']}]})


QUOTE_SCHEMA_FAILURE = ("LLM output failed schema validation for RoleCandidates: "
    "['candidates', 0, 'evidence_links', 0, 'quote']: string_too_long (provider finish_reason=stop).")


def test_v9_unfinished_scan_is_refused_and_preserves_completed_batches(corpus, monkeypatch):
    store, snapshot, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    run = auto_run(corpus)
    class FailsSecondDiscovery(SelectorClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCandidates' and any(
                    name == 'RoleCandidates' for name, _ in self.calls):
                raise RuntimeError(QUOTE_SCHEMA_FAILURE)
            return super().generate_structured(**kwargs)
    execute_run(store, run['run_id'], FailsSecondDiscovery())
    failed = store.get('run', run['run_id'])
    failed['role_manifest']['policy_version'] = 'rq1-stakeholder-selection-v9'
    before = deepcopy(failed['role_manifest'])
    assert not before['selection_rounds'] and len(before['batch_reports']) == 1
    client = SelectorClient()
    with pytest.raises(ValueError, match='policy has changed'):
        selector.select_roles(store, failed, client)
    assert not client.calls and failed['role_manifest'] == before


@pytest.mark.parametrize('failure', ['mixed_schema', 'unknown_finish', 'saved_discovery', 'saved_report', 'provider'])
def test_v9_quote_failure_migration_never_bypasses_other_failures(corpus, failure):
    manifest = auto_run(corpus)['role_manifest']
    manifest.update(policy_version='rq1-stakeholder-selection-v9', status='failed', last_error=QUOTE_SCHEMA_FAILURE)
    if failure == 'mixed_schema':
        manifest['last_error'] += '; another error: literal_error'
    elif failure == 'unknown_finish':
        manifest['last_error'] = QUOTE_SCHEMA_FAILURE.replace('finish_reason=stop', 'finish_reason=unknown')
    elif failure == 'saved_discovery':
        manifest['validation_attempts'] = [{'batch_index': 0, 'phase': 'discovery'}]
    elif failure == 'saved_report':
        manifest['batch_reports'] = [{'batch_index': 0}]
    else:
        manifest['last_error'] = 'Provider unavailable'
    with pytest.raises(ValueError, match='new run'):
        selector.ensure_selection_resumable(manifest)


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


def test_unresolved_span_selection_is_kept_as_proposed_without_claiming_support(corpus):
    class UnsupportedClient(RepairClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCitationCorrections':
                self.calls.append(('RoleCitationCorrections', json.loads(kwargs['user'])))
                return kwargs['output_model'].model_validate({'corrections': [
                    {'candidate_index': 1, 'source_span_ids': [], 'unresolved_reason': 'No excerpt supports this stakeholder.'}]})
            return super().generate_structured(**kwargs)
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    execute_run(store, run['run_id'], UnsupportedClient())
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human'
    attempt = saved['role_manifest']['validation_attempts'][-1]
    assert attempt['status'] == 'valid'
    assert attempt['source_spans']
    assert attempt['unresolved_candidates'][0]['reason'] == 'No excerpt supports this stakeholder.'
    candidate = next(item for item in saved['role_manifest']['candidates'] if item['label'] == 'Data publisher')
    assert candidate['basis'] == 'proposed' and candidate['evidence_links'] == []
    assert saved['role_manifest']['status'] == 'completed'
