"""Offline regression checks for documented-first registry representatives."""
from copy import deepcopy

import pytest

from test_stakeholder_registry import three_batches
from test_role_selection import corpus, SelectorClient
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.models import RoleRegistry
from requirement_reuse_service.workflow.stakeholder_registry import (
    REPRESENTATIVE_POLICY, REGISTRY_PROMPT, checked_decision,
    normalize_registry_representatives, registry_errors,
)
from requirement_reuse_service.workflow.storage import digest


@pytest.fixture
def decision():
    entries = [{'candidate_id': 'entry-' + i, 'basis': basis} for i, basis in (
        ('a', 'inferred'), ('b', 'documented'), ('c', 'documented'))]
    payload = {'candidates': entries}
    key = digest(['cross-source', REGISTRY_PROMPT, payload, RoleRegistry.model_json_schema(), {'model': 'scripted'}])
    answer = RoleRegistry(groups=[{'representative_id': 'entry-a',
        'member_ids': ['entry-c', 'entry-a', 'entry-b'], 'rationale': 'Scripted equivalent interests.'}])
    return entries, payload, key, answer


def no_call(*args, **kwargs):
    raise AssertionError('No new model call is allowed.')


def checked(manifest, decision, call=no_call):
    entries, payload, key, _ = decision
    return checked_decision(manifest, 'registry_calls', key, payload, RoleRegistry,
        REGISTRY_PROMPT, lambda answer: registry_errors(answer, entries), call, lambda event: None,
        representative_entries=entries)


def failed_record(decision):
    entries, payload, key, correction = decision
    original = correction.model_copy(deep=True)
    original.groups[0].member_ids.remove('entry-b')
    return {'key': key, 'input_hash': digest(payload), 'status': 'running',
        'original': original.model_dump(mode='json'), 'validation_errors': registry_errors(original, entries),
        'correction': {'status': 'invalid', 'original': correction.model_dump(mode='json'),
            'result': correction.model_dump(mode='json'), 'validation_errors': registry_errors(correction, entries)}}


def test_documented_member_normalized_before_a_correction_is_spent(decision):
    manifest, calls = {}, []
    def call(*args, **kwargs):
        calls.append(args)
        return decision[-1]
    raw = decision[-1].model_dump(mode='json')
    result = checked(manifest, decision, call)
    record = manifest['registry_calls'][0]
    assert len(calls) == 1 and 'correction' not in record
    assert result.groups[0].representative_id == 'entry-b'
    assert result.groups[0].member_ids == raw['groups'][0]['member_ids']
    assert result.groups[0].rationale == raw['groups'][0]['rationale']
    assert record['original'] == raw == decision[-1].model_dump(mode='json')
    assert record['representative_normalizations'][0]['policy'] == REPRESENTATIVE_POLICY
    assert record['representative_normalizations'][0]['phase'] == 'initial'
    assert 'duplicate_collapses' not in record


def test_representative_normalization_is_order_independent_and_does_not_upgrade(decision):
    entries, _, _, answer = decision
    first, changes = normalize_registry_representatives(answer, entries)
    reverse = answer.model_copy(deep=True)
    reverse.groups[0].member_ids.reverse()
    second, _ = normalize_registry_representatives(reverse, list(reversed(entries)))
    assert first.groups[0].representative_id == second.groups[0].representative_id == 'entry-b'
    assert changes and entries[0]['basis'] == 'inferred'
    for entry in entries:
        entry['basis'] = 'inferred'
    unchanged, changes = normalize_registry_representatives(answer, entries)
    assert unchanged == answer and not changes


@pytest.mark.parametrize('defect', ['missing', 'unknown', 'cross_group_duplicate', 'outside_representative'])
def test_accounting_defects_are_not_repaired_or_accepted(decision, defect):
    entries, _, _, answer = decision
    bad = answer.model_copy(deep=True)
    if defect == 'missing':
        bad.groups[0].member_ids.remove('entry-b')
    elif defect == 'unknown':
        bad.groups[0].member_ids.append('unknown')
    elif defect == 'cross_group_duplicate':
        bad.groups.append(bad.groups[0].model_copy(deep=True))
    else:
        bad.groups[0].representative_id = 'unknown'
    normalized, changes = normalize_registry_representatives(bad, entries)
    assert normalized == bad and not changes
    calls = []
    def call(*args, **kwargs):
        calls.append(args)
        return bad
    manifest = {}
    with pytest.raises(ValueError, match='single correction:'):
        checked(manifest, decision, call)
    assert len(calls) == 2
    before = deepcopy(manifest)
    with pytest.raises(ValueError, match='exhausted or interrupted'):
        checked(manifest, decision)
    assert manifest == before


def test_saved_representative_only_correction_recovers_without_repeating_scan_or_calls(decision):
    completed = [{'key': f'prior-{i}', 'status': 'completed', 'result': {'frozen': i}} for i in range(19)]
    manifest = {'policy_version': selector.POLICY_VERSION, 'mode': 'automatic', 'status': 'failed',
        'batch_reports': [{'batch_index': i} for i in range(48)],
        'registry_calls': deepcopy(completed) + [failed_record(decision)]}
    before = deepcopy(manifest)
    selector.ensure_selection_resumable(manifest)
    result = checked(manifest, decision)
    recovered = manifest['registry_calls'][-1]
    assert result.groups[0].representative_id == 'entry-b'
    assert manifest['registry_calls'][:19] == completed
    assert manifest['batch_reports'] == before['batch_reports']
    assert recovered['original'] == before['registry_calls'][-1]['original']
    assert recovered['correction'] == before['registry_calls'][-1]['correction']
    assert recovered['recovery']['policy'] == REPRESENTATIVE_POLICY
    assert recovered['recovery']['model_calls'] == 0
    assert recovered['representative_normalizations'][0]['phase'] == 'saved_correction_recovery'
    assert len(manifest['migration_notes']) == 1
    after = deepcopy(manifest)
    assert checked(manifest, decision) == result
    assert manifest == after


@pytest.mark.parametrize('tamper', ['input_hash', 'result', 'raw', 'errors'])
def test_saved_correction_recovery_rejects_tampering(decision, tamper):
    record = failed_record(decision)
    if tamper == 'input_hash':
        record['input_hash'] = 'wrong'
    elif tamper == 'result':
        record['correction']['result']['groups'][0]['rationale'] = 'Changed result.'
    elif tamper == 'raw':
        record['correction']['original']['groups'][0]['member_ids'].remove('entry-b')
    else:
        record['correction']['validation_errors'] = []
    manifest = {'registry_calls': [record]}
    before = deepcopy(manifest)
    with pytest.raises(ValueError):
        checked(manifest, decision)
    assert manifest == before


@pytest.mark.parametrize('status', ['started', 'provider_failed'])
def test_correction_that_returned_no_answer_is_issued_once_more(decision, status):
    from requirement_reuse_service.workflow.stakeholder_registry import CORRECTION_RETRY_POLICY, CORRECTION_SUFFIX
    record = failed_record(decision)
    record['correction'] = {'status': status, **({'error': 'ProviderError'} if status == 'provider_failed' else {})}
    manifest = {'registry_calls': [record]}
    calls = []
    def call(system, payload, *args, **kwargs):
        calls.append((system, payload))
        return decision[-1]
    result = checked(manifest, decision, call)
    assert len(calls) == 1 and calls[0][0].endswith(CORRECTION_SUFFIX)
    assert calls[0][1]['validation_errors'] == record['validation_errors']
    assert result.groups[0].representative_id == 'entry-b'
    assert record['status'] == 'completed' and record['correction']['status'] == 'valid'
    assert record['correction_retries'] == [{'policy': CORRECTION_RETRY_POLICY, 'status': status,
        **({'error': 'ProviderError'} if status == 'provider_failed' else {})}]
    assert checked(manifest, decision) == result  # completed: no further call


def test_valid_saved_correction_is_reused_in_preference_to_earlier_original(decision):
    record = failed_record(decision)
    # The earlier answer can now normalize successfully, but the later valid
    # correction chose a different documented representative. Keep that decision.
    record['original'] = decision[-1].model_dump(mode='json')
    record['correction']['result']['groups'][0]['representative_id'] = 'entry-c'
    record['correction'].update(status='valid', validation_errors=[])
    manifest = {'registry_calls': [record]}
    before = deepcopy(record)
    assert checked(manifest, decision).groups[0].representative_id == 'entry-c'
    assert record['correction'] == before['correction']
    assert 'representative_normalizations' not in record


def test_registry_recovery_keeps_real_citations_and_reuses_finished_decisions(three_batches, monkeypatch):
    """Integration: replay the registry from frozen candidates, not a discovery rerun."""
    from test_stakeholder_registry import registry_only
    from requirement_reuse_service.workflow.stakeholder_registry import registry_entry
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    for key in ('registry', 'registry_hash', 'registry_calls'):
        manifest.pop(key, None)
    original = manifest['candidates'][0]
    inferred = {**deepcopy(original), 'candidate_id': 'inferred-fixture', 'basis': 'inferred'}
    manifest['candidates'].append(inferred)
    # Save a v12 correction which grouped every entry but selected the inferred one.
    import requirement_reuse_service.workflow.stakeholder_registry as registry
    def old_normalization(answer, entries):
        return answer.model_copy(deep=True), []
    with monkeypatch.context() as context:
        context.setattr(registry, 'normalize_registry_representatives', old_normalization)
        class Invalid(SelectorClient):
            def generate_structured(self, **kw):
                import json
                payload = json.loads(kw['user'])
                if kw['output_model'].__name__ == 'RoleRegistry':
                    self.calls.append(('RoleRegistry', payload))
                    ids = [c['candidate_id'] for c in payload['candidates']]
                    rep = next(c['candidate_id'] for c in payload['candidates'] if c['basis'] == 'inferred')
                    return RoleRegistry(groups=[{'representative_id': rep, 'member_ids': ids,
                                                 'rationale': 'Scripted equivalent interests.'}])
                return super().generate_structured(**kw)
        with pytest.raises(ValueError, match='documented_representative_required'):
            registry_only(store, manifest, Invalid())
    before = deepcopy(manifest)
    class Continue(SelectorClient):
        def generate_structured(self, **kw):
            assert kw['output_model'].__name__ == 'RoleRegistry'
            return super().generate_structured(**kw)
    client = Continue()
    entries = registry_only(store, manifest, client)
    assert len(client.calls) == 1  # only the previously unattempted cross-source merge
    assert manifest['registry_calls'][0]['correction'] == before['registry_calls'][0]['correction']
    assert manifest['candidates'] == before['candidates']
    assert manifest['batch_reports'] == before['batch_reports']
    assert set(i for e in entries for i in e['member_candidate_ids']) == {c['candidate_id'] for c in manifest['candidates']}
    assert entries[0]['basis'] == 'documented'
    for entry in entries:
        expected = registry_entry(store, manifest, entry['member_candidate_ids'], entry['representative_id'])
        assert entry == expected
