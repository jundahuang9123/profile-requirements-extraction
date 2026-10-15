"""A registry too large for one panel request is judged in bounded blocks, then chosen once.

All generation is scripted and offline.
"""
from collections import Counter
from copy import deepcopy

import pytest

from test_role_selection import corpus  # noqa: F401  (pytest fixture, used by three_batches)
from test_stakeholder_registry import three_batches, panel_fixture  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import stakeholder_registry as registry
from requirement_reuse_service.workflow.storage import canonical


def scripted_panel(irrelevant=()):
    calls = []
    def call(system, payload, output_model, max_tokens=8000):
        calls.append((system, deepcopy(payload)))
        entries = payload['entries']
        if payload.get('entry_encoding') == 'rows_in_entry_fields_order':
            entries = [dict(zip(payload['entry_fields'], row, strict=True)) for row in entries]
        verdicts = [{'entry_id': e['entry_id'], 'relevant': e['entry_id'] not in irrelevant,
                     'reason': 'Scripted relevance.'} for e in entries]
        if system == registry.RELEVANCE_PROMPT:
            return output_model.model_validate({'verdicts': verdicts, 'kept_ids': []})
        ranked = sorted((e for e in entries if e['entry_id'] not in irrelevant), key=lambda e: (
            ('documented', 'inferred', 'proposed').index(e['basis']), e['entry_id']))
        return output_model.model_validate({'verdicts': verdicts,
                                            'kept_ids': [e['entry_id'] for e in ranked[:payload['max_roles']]]})
    return call, calls


def small_budget(monkeypatch, entries, manifest, relevant=None):
    """A budget the full view of the registry exceeds but the compact choice view still fits."""
    relevant = entries if relevant is None else relevant
    budget = len(canonical(registry.choice_payload(relevant, [], manifest['max_roles'], manifest['candidates'])))
    assert len(canonical(registry.panel_payload(entries, [], manifest['max_roles'], manifest['candidates']))) > budget
    monkeypatch.setattr(registry, 'PANEL_CHARS', budget)
    return budget


def test_large_registry_is_judged_in_blocks_then_chosen_once(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 4 + ['inferred'] * 2)
    dropped = sorted(e['entry_id'] for e in entries if e['basis'] == 'documented')[0]
    budget = small_budget(monkeypatch, entries, manifest, [e for e in entries if e['entry_id'] != dropped])
    call, calls = scripted_panel(irrelevant={dropped})
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    blocks = [payload for system, payload in calls if system == registry.RELEVANCE_PROMPT]
    finals = [payload for system, payload in calls if system.startswith(registry.PANEL_PROMPT)]
    assert len(blocks) >= 2 and len(finals) == 1
    assert all(len(canonical(payload)) <= budget for _, payload in calls)
    # Every entry is judged exactly once across the blocks; the choice sees only relevant entries.
    assert Counter(e['entry_id'] for payload in blocks for e in payload['entries']) == Counter(e['entry_id'] for e in entries)
    assert sorted(e['entry_id'] for e in finals[0]['entries']) == sorted(e['entry_id'] for e in entries if e['entry_id'] != dropped)
    assert all('focus_questions' not in e and all(isinstance(s, str) for s in e['sources']) for e in finals[0]['entries'])
    assert Counter(r['filled_via'] for r in manifest['selected_roles']) == {'documented': 3, 'fallback_inferred': 1}
    assert [r['scope'] for r in manifest['selection_rounds']][-1] == 'relevant_entries'
    assert {r['scope'] for r in manifest['selection_rounds'][:-1]} == {'relevance_block'}
    omitted = {o['entry_id']: o for o in manifest['omissions']}
    assert omitted[dropped]['relevant'] is False
    assert len(manifest['omissions']) + len(manifest['selected_roles']) == len(entries)


def test_saved_block_decisions_are_reused_on_resume(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 5)
    small_budget(monkeypatch, entries, manifest)
    call, calls = scripted_panel()
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    first = len(calls)
    selected = deepcopy(manifest['selected_roles'])
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == first and manifest['selected_roles'] == selected


def test_no_relevant_entry_in_any_block_fails_visibly(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 4)
    small_budget(monkeypatch, entries, manifest)
    call, calls = scripted_panel(irrelevant={e['entry_id'] for e in entries})
    with pytest.raises(ValueError, match='No relevant stakeholder'):
        registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert all(system == registry.RELEVANCE_PROMPT for system, _ in calls)


def test_registry_within_budget_keeps_one_decision(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 3)
    call, calls = scripted_panel()
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert [system for system, _ in calls] == [registry.PANEL_PROMPT]
    assert [r['scope'] for r in manifest['selection_rounds']] == ['whole_registry']


@pytest.fixture
def many_entries(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 103)
    for entry in entries:
        entry['purpose'] = 'Examine documented publishing and use of transport data and the metadata people need to discover it.'
    legacy = registry.choice_payload(entries, [], manifest['max_roles'], manifest['candidates'])
    assert len(canonical(legacy)) > registry.PANEL_CHARS
    assert len(canonical(registry.compact_choice_payload(legacy))) < registry.PANEL_CHARS
    return manifest, entries


def test_table_choice_retains_every_exact_value_and_order(many_entries):
    manifest, entries = many_entries
    legacy = registry.choice_payload(entries, [], manifest['max_roles'], manifest['candidates'])
    before = deepcopy(legacy)
    table = registry.compact_choice_payload(legacy)
    decoded = [dict(zip(table['entry_fields'], row, strict=True)) for row in table['entries']]
    assert decoded == legacy['entries'] and legacy == before
    assert table['user_tasks'] == legacy['user_tasks'] and table['max_roles'] == legacy['max_roles']
    reverse = registry.choice_payload(list(reversed(entries)), [], manifest['max_roles'], list(reversed(manifest['candidates'])))
    assert registry.compact_choice_payload(reverse) == table


def test_oversized_saved_choice_reuses_all_relevance_calls_then_sees_every_entry(many_entries, monkeypatch):
    manifest, entries = many_entries
    call, calls = scripted_panel()
    # Reproduce v12's old failure without accepting a partial panel or adding a
    # final call. The previously completed relevance requests remain durable.
    with monkeypatch.context() as old:
        old.setattr(registry, 'compact_choice_payload', lambda payload: payload)
        with pytest.raises(ValueError, match='more than one panel request'):
            registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    completed = deepcopy(manifest['panel_calls'])
    prior_count = len(calls)
    assert all(system == registry.RELEVANCE_PROMPT for system, _ in calls)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == prior_count + 1
    assert manifest['panel_calls'][:-1] == completed
    final_payload = calls[-1][1]
    assert len(canonical(final_payload)) <= registry.PANEL_CHARS
    decoded = [dict(zip(final_payload['entry_fields'], row, strict=True)) for row in final_payload['entries']]
    assert {e['entry_id'] for e in decoded} == {e['entry_id'] for e in entries}
    assert len(manifest['selected_roles']) == 4 and len(manifest['omissions']) == len(entries) - 4
    assert manifest['panel_input_compactions'][0]['entry_count'] == len(entries)
    before = deepcopy(manifest)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == prior_count + 1 and manifest == before


def test_table_correction_keeps_the_same_entries_and_stays_within_request_bound(many_entries):
    manifest, entries = many_entries
    scripted, calls = scripted_panel()
    def call(system, payload, output_model, max_tokens=8000):
        assert len(canonical(payload)) <= 60000
        result = scripted(system, payload, output_model, max_tokens)
        if payload.get('entry_encoding') and 'invalid_answer' not in payload:
            result.kept_ids[0] = 'unknown-entry'
        return result
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    finals = [payload for system, payload in calls if system.startswith(registry.PANEL_PROMPT)]
    assert len(finals) == 2
    assert finals[0]['entries'] == finals[1]['entries']
    assert finals[0]['entry_fields'] == finals[1]['entry_fields']
    assert manifest['panel_calls'][-1]['correction']['status'] == 'valid'


def test_table_still_too_large_fails_without_dropping_entries(many_entries, monkeypatch):
    manifest, entries = many_entries
    legacy = registry.choice_payload(entries, [], manifest['max_roles'], manifest['candidates'])
    monkeypatch.setattr(registry, 'PANEL_CHARS', len(canonical(registry.compact_choice_payload(legacy))) - 1)
    before = deepcopy(entries)
    call, calls = scripted_panel()
    with pytest.raises(ValueError, match='even after lossless table encoding; no entry was dropped'):
        registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert entries == before and not manifest['selected_roles']
    assert all(system == registry.RELEVANCE_PROMPT for system, _ in calls)
    assert not manifest.get('panel_input_compactions')
