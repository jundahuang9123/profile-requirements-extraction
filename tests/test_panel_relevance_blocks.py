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
    finals = [payload for system, payload in calls if system == registry.PANEL_PROMPT]
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
