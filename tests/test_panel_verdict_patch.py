"""Strict, offline composition of a correction containing only missing verdicts."""
from copy import deepcopy

import pytest

from test_role_selection import corpus  # noqa: F401 (fixture dependency)
from test_stakeholder_registry import three_batches, panel_fixture  # noqa: F401 (fixture)
from test_panel_relevance_blocks import small_budget
from requirement_reuse_service.workflow import stakeholder_registry as registry
from requirement_reuse_service.workflow.models import StakeholderPanel
from requirement_reuse_service.workflow.storage import digest


@pytest.fixture
def decision():
    entries = [{'entry_id': 'entry-' + name, 'basis': basis} for name, basis in (
        ('a', 'documented'), ('b', 'documented'), ('c', 'documented'),
        ('d', 'documented'), ('e', 'documented'), ('f', 'inferred'), ('g', 'inferred'))]
    initial = StakeholderPanel(verdicts=[{'entry_id': entry['entry_id'], 'relevant': True,
        'reason': 'Original judgement for ' + entry['entry_id']} for entry in entries[:5]],
        kept_ids=['entry-a', 'entry-b', 'entry-c', 'entry-d'])
    correction = StakeholderPanel(verdicts=[{'entry_id': entry['entry_id'], 'relevant': True,
        'reason': 'Correction judgement for ' + entry['entry_id']} for entry in entries[5:]],
        kept_ids=['entry-b', 'entry-c', 'entry-d', 'entry-e'])
    payload = {'max_roles': 4, 'user_tasks': [], 'entries': entries}
    validate = lambda answer: registry.panel_errors(answer, entries, 4)
    key = digest([registry.PANEL_PROMPT, payload, StakeholderPanel.model_json_schema(), {'model': 'scripted'}])
    return entries, initial, correction, payload, validate, key


def checked(manifest, decision, call=None, opt_in=True):
    _, _, _, payload, validate, key = decision
    if call is None:
        def call(*args, **kwargs):
            raise AssertionError('No model generation is permitted for saved recovery.')
    return registry.checked_decision(manifest, 'panel_calls', key, payload, StakeholderPanel,
        registry.PANEL_PROMPT, validate, call, lambda event: None,
        normalize_response=registry.collapse_panel_verdicts, complete_verdict_patch=opt_in)


def failed_record(decision):
    _, initial, correction, payload, validate, key = decision
    return {'key': key, 'input_hash': digest(payload), 'status': 'running',
        'original': initial.model_dump(mode='json'), 'validation_errors': validate(initial),
        'correction': {'status': 'invalid', 'original': correction.model_dump(mode='json'),
            'result': correction.model_dump(mode='json'), 'validation_errors': validate(correction)}}


def assert_exact_composition(answer, decision):
    _, initial, correction, _, validate, _ = decision
    assert not validate(answer)
    assert answer.verdicts == [*initial.verdicts, *correction.verdicts]
    assert answer.kept_ids == correction.kept_ids


def test_missing_verdict_patch_combines_exact_model_judgements_without_mutating_raw(decision):
    _, initial, correction, _, validate, _ = decision
    before = deepcopy((initial, correction))
    answer, audit = registry.complete_missing_verdicts(initial, correction, validate)
    assert audit
    assert_exact_composition(answer, decision)
    assert (initial, correction) == before


def test_fresh_patch_correction_is_audited_and_needs_only_the_two_scripted_answers(decision):
    _, initial, correction, _, _, _ = decision
    answers = iter([initial, correction])
    calls = []
    def call(*args, **kwargs):
        calls.append((args, kwargs))
        return next(answers).model_copy(deep=True)
    manifest = {}
    answer = checked(manifest, decision, call)
    assert len(calls) == 2
    assert_exact_composition(answer, decision)
    record = manifest['panel_calls'][0]
    assert record['original'] == initial.model_dump(mode='json')
    assert record['correction']['original'] == correction.model_dump(mode='json')
    assert record['status'] == 'completed'
    assert record['verdict_compositions']
    assert all(item['policy'] and item['phase'] for item in record['verdict_compositions'])


def test_saved_patch_recovers_with_no_calls_and_keeps_finished_scan_and_audits(decision):
    prior = [{'key': 'completed-' + str(i), 'status': 'completed', 'result': {'saved': i}} for i in range(3)]
    manifest = {'panel_calls': [*deepcopy(prior), failed_record(decision)],
        'batch_reports': [{'batch_index': i, 'evidence_ids': ['evidence-' + str(i)]} for i in range(48)],
        'registry': [{'entry_id': 'frozen-entry', 'member_candidate_ids': ['frozen-candidate']}],
        'candidates': [{'candidate_id': 'frozen-candidate'}]}
    before = deepcopy(manifest)
    answer = checked(manifest, decision)
    assert_exact_composition(answer, decision)
    record = manifest['panel_calls'][-1]
    assert manifest['panel_calls'][:-1] == prior
    for key in ('batch_reports', 'registry', 'candidates'):
        assert manifest[key] == before[key]
    for key in ('original', 'validation_errors', 'correction'):
        assert record[key] == before['panel_calls'][-1][key]
    assert record['recovery']['model_calls'] == 0
    assert record['verdict_compositions']
    assert all(item['policy'] and item['phase'] for item in record['verdict_compositions'])
    assert manifest['migration_notes']
    recovered = deepcopy(manifest)
    assert checked(manifest, decision) == answer
    assert manifest == recovered


@pytest.mark.parametrize('defect', ['missing', 'extra', 'overlap', 'duplicate', 'contradiction',
    'basis_priority', 'irrelevant_kept', 'underfilled', 'unknown_kept', 'duplicate_kept'])
def test_patch_rejects_incomplete_or_conflicting_ids_and_every_panel_rule(decision, defect):
    _, initial, correction, _, validate, _ = decision
    patch = correction.model_copy(deep=True)
    if defect == 'missing':
        patch.verdicts.pop()
    elif defect == 'extra':
        verdict = patch.verdicts[0].model_copy(deep=True)
        verdict.entry_id = 'unknown-entry'
        patch.verdicts.append(verdict)
    elif defect in {'overlap', 'contradiction'}:
        verdict = initial.verdicts[0].model_copy(deep=True)
        verdict.relevant = defect != 'contradiction'
        patch.verdicts.append(verdict)
    elif defect == 'duplicate':
        patch.verdicts.append(patch.verdicts[0].model_copy(deep=True))
    elif defect == 'basis_priority':
        patch.kept_ids = ['entry-a', 'entry-b', 'entry-c', 'entry-f']
    elif defect == 'irrelevant_kept':
        patch.verdicts[0].relevant = False
        patch.kept_ids = ['entry-a', 'entry-b', 'entry-c', 'entry-f']
    elif defect == 'underfilled':
        patch.kept_ids.pop()
    elif defect == 'unknown_kept':
        patch.kept_ids[0] = 'unknown-entry'
    else:
        patch.kept_ids[-1] = patch.kept_ids[0]
    before = deepcopy((initial, patch))
    answer, audit = registry.complete_missing_verdicts(initial, patch, validate)
    assert audit is None
    assert (initial, patch) == before
    assert validate(answer)


@pytest.mark.parametrize('defect', ['unknown', 'repeated', 'other_error', 'complete_initial'])
def test_initial_answer_must_have_only_missing_verdicts(decision, defect):
    _, initial, correction, _, validate, _ = decision
    initial = initial.model_copy(deep=True)
    if defect == 'unknown':
        verdict = initial.verdicts[0].model_copy(deep=True)
        verdict.entry_id = 'unknown-entry'
        initial.verdicts.append(verdict)
    elif defect == 'repeated':
        initial.verdicts.append(initial.verdicts[0].model_copy(deep=True))
    elif defect == 'other_error':
        initial.kept_ids[0] = 'unknown-entry'
    else:
        initial.verdicts.extend(verdict.model_copy(deep=True) for verdict in correction.verdicts)
    _, audit = registry.complete_missing_verdicts(initial, correction, validate)
    assert audit is None


@pytest.mark.parametrize('tamper', ['input_hash', 'initial_result', 'initial_errors', 'correction_raw',
    'correction_result', 'correction_errors', 'interrupted', 'provider_failed'])
def test_saved_patch_recovery_rejects_tampered_or_unfinished_audits(decision, tamper):
    record = failed_record(decision)
    if tamper == 'input_hash':
        record['input_hash'] = 'wrong'
    elif tamper == 'initial_result':
        record['original']['verdicts'][0]['entry_id'] = 'unknown-entry'
    elif tamper == 'initial_errors':
        record['validation_errors'] = []
    elif tamper == 'correction_raw':
        record['correction']['original']['verdicts'][0]['reason'] = 'Changed raw judgement.'
    elif tamper == 'correction_result':
        record['correction']['result']['verdicts'][0]['reason'] = 'Changed normalized judgement.'
    elif tamper == 'correction_errors':
        record['correction']['validation_errors'] = []
    else:
        record['correction'] = {'status': 'started' if tamper == 'interrupted' else 'provider_failed'}
    manifest = {'panel_calls': [record]}
    before = deepcopy(manifest)
    with pytest.raises(ValueError):
        checked(manifest, decision)
    assert manifest == before


def test_patch_recovery_requires_explicit_panel_opt_in(decision):
    manifest = {'panel_calls': [failed_record(decision)]}
    before = deepcopy(manifest)
    with pytest.raises(ValueError):
        checked(manifest, decision, opt_in=False)
    assert manifest == before


def test_choose_panel_composes_missing_verdicts_in_its_final_decision(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 5 + ['inferred'] * 2)
    ordered = sorted(entries, key=lambda entry: entry['entry_id'])
    missing = {entry['entry_id'] for entry in ordered[-2:]}
    kept = sorted(entry['entry_id'] for entry in entries if entry['basis'] == 'documented')[:4]
    calls = []
    def call(system, payload, output_model, max_tokens=8000):
        assert system.startswith(registry.PANEL_PROMPT)
        calls.append(deepcopy(payload))
        offered = payload['entries']
        chosen = [entry for entry in offered if (entry['entry_id'] in missing) == ('invalid_answer' in payload)]
        return output_model(verdicts=[{'entry_id': entry['entry_id'], 'relevant': True,
            'reason': 'Scripted final judgement for ' + entry['entry_id']} for entry in chosen], kept_ids=kept)

    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})

    assert len(calls) == 2
    assert {role['registry_entry_id'] for role in manifest['selected_roles']} == set(kept)
    assert len(manifest['omissions']) == len(entries) - len(kept)
    verdicts = manifest['selection_rounds'][-1]['verdicts']
    assert {verdict['entry_id'] for verdict in verdicts} == {entry['entry_id'] for entry in entries}
    assert len(verdicts) == len(entries)
    record = manifest['panel_calls'][0]
    assert record['status'] == 'completed' and record['verdict_compositions']
    assert {verdict['entry_id'] for verdict in record['correction']['original']['verdicts']} == missing


def test_choose_panel_composes_a_relevance_block_patch_with_no_kept_entries(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 5 + ['inferred'] * 2)
    small_budget(monkeypatch, entries, manifest)
    calls, patched = [], []
    def call(system, payload, output_model, max_tokens=8000):
        calls.append((system, deepcopy(payload)))
        offered = payload['entries']
        if system.startswith(registry.RELEVANCE_PROMPT):
            kept = []
            if 'invalid_answer' in payload:
                missing = set(payload['validation_errors'][0]['missing'])
                chosen = [entry for entry in offered if entry['entry_id'] in missing]
            elif not patched and len(offered) > 1:
                patched.extend(entry['entry_id'] for entry in offered)
                chosen = offered[:-1]
            else:
                chosen = offered
        else:
            assert system == registry.PANEL_PROMPT
            chosen = offered
            kept = sorted(entry['entry_id'] for entry in offered if entry['basis'] == 'documented')[:4]
        return output_model(verdicts=[{'entry_id': entry['entry_id'], 'relevant': True,
            'reason': 'Scripted block judgement for ' + entry['entry_id']} for entry in chosen], kept_ids=kept)

    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})

    assert patched
    blocks = [round_ for round_ in manifest['selection_rounds'] if round_['scope'] == 'relevance_block']
    block_verdicts = [verdict for round_ in blocks for verdict in round_['verdicts']]
    assert len(blocks) > 1 and all(not round_['kept_ids'] for round_ in blocks)
    assert len(block_verdicts) == len(entries)
    assert {verdict['entry_id'] for verdict in block_verdicts} == {entry['entry_id'] for entry in entries}
    composed = [record for record in manifest['panel_calls'] if record.get('verdict_compositions')]
    assert len(composed) == 1 and composed[0]['correction']['original']['kept_ids'] == []
    assert {verdict['entry_id'] for verdict in composed[0]['result']['verdicts']} == set(patched)
    assert len(manifest['selected_roles']) == 4
    assert all(role['basis'] == 'documented' for role in manifest['selected_roles'])
    before = deepcopy(manifest)
    count = len(calls)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == count and manifest == before
