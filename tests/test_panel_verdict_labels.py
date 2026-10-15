"""Each relevance verdict repeats its entry's label, so a verdict that drifted to another ID is caught.

In the functional Mobility run, 3 of 107 relevance reasons described a neighbouring entry
(for example, the Regulator's verdict carried the reason written for Businesses and SMEs).
All generation here is scripted and offline.
"""
from copy import deepcopy

from test_role_selection import corpus  # noqa: F401 (fixture dependency)
from test_stakeholder_registry import three_batches, panel_fixture  # noqa: F401 (fixtures)
from test_panel_relevance_blocks import small_budget
from requirement_reuse_service.workflow import stakeholder_registry as registry
from requirement_reuse_service.workflow.models import StakeholderPanel, StakeholderVerdict


def entries(*labels):
    return [{'entry_id': f'stakeholder-entry-{i:024x}', 'label': label, 'basis': 'documented'}
            for i, label in enumerate(labels)]


def panel(*verdicts, kept=()):
    return StakeholderPanel(verdicts=[{'label': label, 'entry_id': entry_id, 'relevant': relevant,
                                       'reason': f'Scripted reason about {label}.'}
                                      for label, entry_id, relevant in verdicts], kept_ids=list(kept))


def test_label_key_ignores_dash_variants_case_and_spacing():
    assert registry.label_key('Business & SME Re‑users') == registry.label_key(' business  &  SME re-users ')


def test_schema_puts_the_label_first_and_answers_without_one_stay_valid():
    assert list(StakeholderVerdict.model_json_schema()['properties'])[0] == 'label'
    assert StakeholderVerdict.model_validate({'entry_id': 'x', 'relevant': True, 'reason': 'r'}).label is None
    for prompt in (registry.PANEL_PROMPT, registry.RELEVANCE_PROMPT):
        assert "first copy that entry's exact label" in ' '.join(prompt.split())


def test_a_verdict_naming_another_entry_is_flagged_but_a_paraphrase_is_not():
    offered = entries('Regulator', 'Businesses and SMEs', 'Metadata Creator')
    a, b, c = (e['entry_id'] for e in offered)
    shifted = panel(('Businesses and SMEs', a, False), ('Regulator', b, False), ('Metadata Creator', c, False))
    errors = registry.relevance_errors(shifted, offered)
    assert [e['code'] for e in errors] == ['verdict_label_mismatch']
    assert {v['entry_id'] for v in errors[0]['verdicts']} == {a, b}
    paraphrase = panel(('Regulators', a, False), (None, b, False), ('metadata  creator', c, False))
    assert registry.relevance_errors(paraphrase, offered) == []


def test_repair_moves_a_verdict_to_the_entry_its_label_names_and_drops_shared_labels():
    offered = entries('Data Owner', 'Data Owner', 'Owner', 'Regulator')
    x, y, z, r = (e['entry_id'] for e in offered)
    answer = panel(('Data Owner', x, True), ('Data Owner', y, True), ('Data Owner', z, True),
                   ('Owner', r, False))
    verdicts, changes = registry.merge_verdicts(answer, answer, offered)
    # Z's verdict names a label two entries share: no way to tell which, so it is dropped.
    assert set(verdicts) == {x, y, z}
    assert verdicts[z].reason == 'Scripted reason about Owner.'   # moved here from R by its unique label
    assert changes['correction']['shared_labels_dropped'] == [z]
    assert changes['correction']['moved_to_the_entry_their_label_names'] == [
        {'answer_id': r, 'label': 'Owner', 'entry_id': z}]


def test_a_drifted_block_verdict_is_moved_and_its_vacated_entry_is_judged_in_a_follow_up(three_batches, monkeypatch):
    manifest, offered = panel_fixture(three_batches, ['documented'] * 6)
    small_budget(monkeypatch, offered, manifest)
    first_block = next(registry.relevance_blocks(offered, [], manifest['max_roles'], manifest['candidates']))
    drifted, neighbour = first_block[0]['entry_id'], first_block[1]['entry_id']
    calls = []
    def call(system, payload, output_model, max_tokens=8000):
        calls.append((system, deepcopy(payload)))
        rows = payload['entries']
        if payload.get('entry_encoding') == 'rows_in_entry_fields_order':
            rows = [dict(zip(payload['entry_fields'], row, strict=True)) for row in rows]
        verdicts = [{'label': e['label'], 'entry_id': e['entry_id'], 'relevant': True,
                     'reason': 'Judged on its own.'} for e in rows]
        if system.startswith(registry.RELEVANCE_PROMPT) and len(rows) > 1 and rows[0]['entry_id'] == drifted:
            # The first verdict carries the neighbour's label and reasoning under the drifted ID.
            neighbour_label = next(e['label'] for e in rows if e['entry_id'] == neighbour)
            verdicts[0] = {'label': neighbour_label, 'entry_id': drifted, 'relevant': False,
                           'reason': 'Reasoning about the neighbouring entry.'}
        kept = [] if system.startswith(registry.RELEVANCE_PROMPT) else [e['entry_id'] for e in rows][:payload['max_roles']]
        return output_model.model_validate({'verdicts': verdicts, 'kept_ids': kept})
    registry.choose_panel(manifest, offered, [], call, lambda event: None, {'model': 'scripted'})
    repaired = [r for r in manifest['panel_calls'] if r.get('repair')]
    assert len(repaired) == 1
    assert [e['code'] for e in repaired[0]['validation_errors']] == ['verdict_label_mismatch']
    changes = repaired[0]['repair']['changes']['correction']
    assert changes['moved_to_the_entry_their_label_names'][0]['entry_id'] == neighbour
    assert changes['conflicting_verdicts_counted_relevant'] == [neighbour]
    follow_ups = [p for s, p in calls if s == registry.RELEVANCE_PROMPT and [e['entry_id'] for e in p['entries']] == [drifted]]
    assert len(follow_ups) == 1
    final = {v['entry_id']: v for r in manifest['selection_rounds'][:-1] for v in r['verdicts']}
    assert final[drifted]['reason'] == 'Judged on its own.'   # its own follow-up verdict, not the drifted one
    assert len(manifest['selected_roles']) == 4
