"""Accounting slips after the single correction are completed by program rules, never fatal.

The first two tests replay the exact registry decision that stopped the functional Mobility
run (run-e74ad1de345c44ca92bcf078bafc15ef, registry call 11): the first answer placed one
entry in two groups and chose an inferred representative; the correction fixed both but
miscopied one 24-digit entry ID by a single hex digit. All generation here is scripted.
"""
from collections import Counter
from copy import deepcopy

import pytest

from test_role_selection import corpus, SelectorClient  # noqa: F401 (fixture dependency)
from test_stakeholder_registry import three_batches, panel_fixture, registry_only  # noqa: F401 (fixtures)
from test_panel_relevance_blocks import small_budget
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow import stakeholder_registry as registry
from requirement_reuse_service.workflow.models import RoleRegistry, StakeholderPanel
from requirement_reuse_service.workflow.storage import digest

E = 'stakeholder-entry-'
INFERRED = E + '37b0f52d7e1798b1e88f7a82'
OFFERED = [E + suffix for suffix in (
    '1aff7c968ab18e81de7c3188', '211147da98a03ee55b7c060f', '234415aae071f2f9b399faab',
    '26e478791d2a20c1ddde2923', '324e64c158f0450fe6baa305', '37b0f52d7e1798b1e88f7a82',
    '3fb2708701cdec8c05777f9b', '3fc59f1f2214418119396449', '48f40faa0f1ac043ed29e8d5',
    '4bb20a1ab48734f1d3846b4d', '4d570ca820f833977e9a2578', '4dedeffc844acfd21429f672',
    '51ba09c6e034569ad1742a24', '5480c726dbba570fdde0831c', '5cc850c4f81ebe4139c8e8c6',
    '625b71fa63af6a5294e1c836', '6663ae085fa0dbd44e25084a', '696ad70d98bcb75570985769',
    '6d31acd7e6eee3939bb78160', '6d600b031322ba83b34f236e', '6d86317cbf047d561e317344',
    '71804a3a83e6138756c96d83', '8a9ff6666ffd98ee6ca56aa0', '9058ea2cbf8b795962a90a9c',
    '9da48e76b0747fbfefda8e19', 'a1fdd4196411d958f2baceb5', 'aa934eca9a0e20046e6f1714',
    'b152c782a306b24cdd5428b1')]
TYPED, MEANT = E + '51ba09c4e034569ad1742a24', E + '51ba09c6e034569ad1742a24'
DUPLICATED = E + '4bb20a1ab48734f1d3846b4d'


def groups(*rows):
    return RoleRegistry(groups=[{'representative_id': E + rep, 'member_ids': [E + m for m in members],
                                 'rationale': f'Scripted rationale {index}.'}
                                for index, (rep, members) in enumerate(rows)])


FUNDERS = ['211147da98a03ee55b7c060f', '234415aae071f2f9b399faab', '6663ae085fa0dbd44e25084a',
           '8a9ff6666ffd98ee6ca56aa0', '9058ea2cbf8b795962a90a9c', '9da48e76b0747fbfefda8e19']
SHARED = [
    ('1aff7c968ab18e81de7c3188', ['1aff7c968ab18e81de7c3188', '26e478791d2a20c1ddde2923',
                                  '71804a3a83e6138756c96d83', 'a1fdd4196411d958f2baceb5']),
    ('324e64c158f0450fe6baa305', ['324e64c158f0450fe6baa305', '48f40faa0f1ac043ed29e8d5', '6d31acd7e6eee3939bb78160']),
]
TAIL = [
    ('3fb2708701cdec8c05777f9b', ['3fb2708701cdec8c05777f9b', '696ad70d98bcb75570985769']),
    ('3fc59f1f2214418119396449', ['3fc59f1f2214418119396449']),
    ('4bb20a1ab48734f1d3846b4d', ['4bb20a1ab48734f1d3846b4d']),
    ('4d570ca820f833977e9a2578', ['4d570ca820f833977e9a2578', '6d86317cbf047d561e317344',
                                  'aa934eca9a0e20046e6f1714', 'b152c782a306b24cdd5428b1']),
    ('5cc850c4f81ebe4139c8e8c6', ['5cc850c4f81ebe4139c8e8c6']),
]
STEWARDS = ['37b0f52d7e1798b1e88f7a82', '5480c726dbba570fdde0831c', '6d600b031322ba83b34f236e']


def mobility_answers():
    # First answer: the DMP-tools entry also sits in the funders group, and the data
    # stewardship group has an inferred representative although two members are documented.
    original = groups(SHARED[0], ('211147da98a03ee55b7c060f', FUNDERS + ['4bb20a1ab48734f1d3846b4d']), SHARED[1],
                      ('37b0f52d7e1798b1e88f7a82', STEWARDS), *TAIL,
                      ('51ba09c6e034569ad1742a24', ['51ba09c6e034569ad1742a24']),
                      ('4dedeffc844acfd21429f672', ['4dedeffc844acfd21429f672']),
                      ('625b71fa63af6a5294e1c836', ['625b71fa63af6a5294e1c836']))
    # Correction: both problems fixed, but one ID copied with a single wrong hex digit (c6 -> c4).
    correction = groups(SHARED[0], ('211147da98a03ee55b7c060f', FUNDERS), SHARED[1],
                        ('5480c726dbba570fdde0831c', STEWARDS), *TAIL,
                        ('51ba09c4e034569ad1742a24', ['51ba09c4e034569ad1742a24']),
                        ('4dedeffc844acfd21429f672', ['4dedeffc844acfd21429f672']),
                        ('625b71fa63af6a5294e1c836', ['625b71fa63af6a5294e1c836']))
    return original, correction


@pytest.fixture
def mobility():
    entries = [{'candidate_id': i, 'basis': 'inferred' if i == INFERRED else 'documented'} for i in OFFERED]
    payload = {'candidates': entries}
    key = digest(['source:fixture', registry.REGISTRY_PROMPT, payload, RoleRegistry.model_json_schema(), {'model': 'scripted'}])
    return entries, payload, key


def decide(manifest, mobility, call):
    entries, payload, key = mobility
    return registry.checked_decision(manifest, 'registry_calls', key, payload, RoleRegistry,
        registry.REGISTRY_PROMPT, lambda answer: registry.registry_errors(answer, entries), call, lambda event: None,
        representative_entries=entries,
        repair=lambda first, latest: registry.repair_registry_accounting(first, latest, entries))


def no_call(*args, **kwargs):
    raise AssertionError('No model call is allowed.')


def assert_meant_partition(result, entries):
    original, correction = mobility_answers()
    assert not registry.registry_errors(result, entries)
    expected = correction.model_copy(deep=True)
    expected.groups[9].member_ids = [MEANT]
    expected.groups[9].representative_id = MEANT
    assert result == expected
    assert Counter(i for g in result.groups for i in g.member_ids) == Counter(OFFERED)


def test_saved_mobility_failure_recovers_with_zero_calls(mobility):
    entries, payload, key = mobility
    original, correction = mobility_answers()
    validate = lambda answer: registry.registry_errors(answer, entries)
    initial, _ = registry.normalize_registry_representatives(original, entries)
    # The record exactly as the failed run saved it.
    record = {'key': key, 'input_hash': digest(payload), 'status': 'running',
              'original': original.model_dump(mode='json'), 'validation_errors': validate(initial),
              'correction': {'status': 'invalid', 'original': correction.model_dump(mode='json'),
                             'result': correction.model_dump(mode='json'), 'validation_errors': validate(correction)}}
    assert [e['code'] for e in record['validation_errors']] == ['duplicate_disposition', 'documented_representative_required']
    assert record['correction']['validation_errors'] == [
        {'code': 'unknown_candidate_ids', 'candidate_ids': [TYPED]},
        {'code': 'missing_candidate_ids', 'candidate_ids': [MEANT]}]
    manifest = {'policy_version': selector.POLICY_VERSION, 'mode': 'automatic', 'status': 'failed',
                'registry_calls': [deepcopy(record)]}
    selector.ensure_selection_resumable(manifest)
    result = decide(manifest, mobility, no_call)
    assert_meant_partition(result, entries)
    saved = manifest['registry_calls'][0]
    assert saved['status'] == 'completed'
    assert saved['original'] == record['original'] and saved['correction'] == record['correction']
    assert saved['recovery'] == {'policy': registry.ACCOUNTING_REPAIR_POLICY, 'input_hash': digest(payload),
                                 'from_correction_status': 'invalid', 'model_calls': 0}
    assert saved['repair']['changes'] == {'restored_ids': [
        {'answer_id': TYPED, 'restored_id': MEANT, 'edit_distance': 1}]}
    assert len(manifest['migration_notes']) == 1
    after = deepcopy(manifest)
    assert decide(manifest, mobility, no_call) == result
    assert manifest == after


def test_live_merge_completes_after_a_miscopied_correction(mobility):
    entries, _, _ = mobility
    answers = iter(mobility_answers())
    calls = []
    def call(system, payload, *args, **kwargs):
        calls.append(system)
        return next(answers)
    manifest = {}
    result = decide(manifest, mobility, call)
    assert len(calls) == 2 and calls[1].endswith(registry.CORRECTION_SUFFIX)
    assert_meant_partition(result, entries)
    record = manifest['registry_calls'][0]
    assert record['repair']['phase'] == 'correction' and record['repair']['model_calls'] == 0
    assert decide(manifest, mobility, no_call) == result


@pytest.mark.parametrize('defect', ['missing', 'unknown', 'duplicate', 'outside_representative', 'all'])
def test_registry_repair_keeps_every_entry_exactly_once_and_infers_no_merge(mobility, defect):
    entries, _, _ = mobility
    _, answer = mobility_answers()
    answer.groups[9].member_ids = [MEANT]; answer.groups[9].representative_id = MEANT
    bad = answer.model_copy(deep=True)
    if defect in {'missing', 'all'}:
        bad.groups[1].member_ids.remove(E + FUNDERS[-1])
    if defect in {'unknown', 'all'}:
        bad.groups[0].member_ids.append(E + 'ffffffffffffffffffffffff')
    if defect in {'duplicate', 'all'}:
        bad.groups[0].member_ids.append(E + FUNDERS[0])
    if defect in {'outside_representative', 'all'}:
        bad.groups[3].representative_id = E + FUNDERS[1]
    assert registry.registry_errors(bad, entries)
    result, changes = registry.repair_registry_accounting(bad, bad, entries)
    assert not registry.registry_errors(result, entries)
    assert Counter(i for g in result.groups for i in g.member_ids) == Counter(OFFERED)
    original_together = {frozenset(g.member_ids) for g in bad.groups}
    for group in result.groups:
        # Every repaired group is a subset of a group the model formed, or a separate entry.
        assert len(group.member_ids) == 1 or any(set(group.member_ids) <= g for g in original_together)
        members = {e['candidate_id']: e for e in entries}
        if any(members[i]['basis'] == 'documented' for i in group.member_ids):
            assert members[group.representative_id]['basis'] == 'documented'
    if defect == 'duplicate':
        assert changes['ids_in_several_groups_kept_separate'] == [E + FUNDERS[0]]
        assert [E + FUNDERS[0]] in [g.member_ids for g in result.groups]


def test_ambiguous_or_distant_copies_are_not_restored():
    expected = {E + 'aaaaaaaaaaaaaaaaaaaaaaaa', E + 'aaaaaaaaaaaaaaaaaaaaaaab', E + 'cccccccccccccccccccccccc'}
    # Two expected IDs within reach: ambiguous, so not restored.
    assert registry.restore_copied_ids({E + 'aaaaaaaaaaaaaaaaaaaaaaac'}, expected, expected) == {}
    # Three edits away: not a copy.
    assert registry.restore_copied_ids({E + 'cccccccccccccccccccccddd'}, expected, expected) == {}
    # One edit away, but the near ID was not left out: no restore.
    assert registry.restore_copied_ids({E + 'ccccccccccccccccccccccce'}, set(), expected) == {}
    # Two different copies of the same ID: neither is restored.
    assert registry.restore_copied_ids({E + 'ccccccccccccccccccccccce', E + 'cccccccccccccccccccccccf'},
                                       expected, expected) == {}
    assert registry.restore_copied_ids({E + 'ccccccccccccccccccccccc'}, expected, expected) == {
        E + 'ccccccccccccccccccccccc': {'restored_id': E + 'cccccccccccccccccccccccc', 'edit_distance': 1}}


def test_registry_build_never_stops_on_a_miscopied_merge(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    for key in ('registry', 'registry_hash', 'registry_calls'):
        manifest.pop(key, None)
    class Miscopies(SelectorClient):
        def generate_structured(self, **kw):
            import json
            if kw['output_model'].__name__ == 'RoleRegistry':
                payload = json.loads(kw['user'])
                self.calls.append(('RoleRegistry', payload))
                ids = [c['candidate_id'] for c in payload['candidates']]
                copied = [i[:-1] + ('0' if i[-1] != '0' else '1') for i in ids]
                return RoleRegistry(groups=[{'representative_id': copied[0], 'member_ids': copied,
                                             'rationale': 'Scripted, every ID miscopied.'}])
            return super().generate_structured(**kw)
    client = Miscopies()
    entries = registry_only(store, manifest, client)
    assert sorted(i for e in entries for i in e['member_candidate_ids']) == sorted(
        c['candidate_id'] for c in manifest['candidates'])
    assert all(r['status'] == 'completed' for r in manifest['registry_calls'])
    assert any(r.get('repair', {}).get('changes', {}).get('restored_ids') for r in manifest['registry_calls'])


def block_script(skip_initial=(), skip_correction=(), unknown_only=False, final=False):
    """Requests with several entries leave out the given ones (first answer, then correction).

    Relevance requests always skip; the final choice skips only with ``final``. A one-entry
    follow-up request is always answered.
    """
    calls = []
    def call(system, payload, output_model, max_tokens=8000):
        calls.append((system, deepcopy(payload)))
        entries = payload['entries']
        if payload.get('entry_encoding') == 'rows_in_entry_fields_order':
            entries = [dict(zip(payload['entry_fields'], row, strict=True)) for row in entries]
        ids = [e['entry_id'] for e in entries]
        correcting = system.endswith(registry.CORRECTION_SUFFIX)
        relevance = system.startswith(registry.RELEVANCE_PROMPT)
        skip = set(skip_correction if correcting else skip_initial) if len(ids) > 1 and (relevance or final) else set()
        if relevance:
            if unknown_only and len(ids) > 1:
                verdicts = [{'entry_id': 'unknown-' + str(n), 'relevant': True, 'reason': 'Wrong IDs.'} for n in range(2)]
            else:
                verdicts = [{'entry_id': i, 'relevant': True, 'reason': 'Scripted relevance.'} for i in ids if i not in skip]
            return output_model.model_validate({'verdicts': verdicts, 'kept_ids': []})
        ranked = sorted(entries, key=lambda e: (('documented', 'inferred', 'proposed').index(e['basis']), e['entry_id']))
        return output_model.model_validate({
            'verdicts': [{'entry_id': i, 'relevant': True, 'reason': 'Scripted choice.'} for i in ids if i not in skip],
            'kept_ids': [e['entry_id'] for e in ranked[:payload['max_roles']]]})
    return call, calls


def test_entries_a_block_and_its_correction_leave_out_get_a_follow_up_block(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 6)
    small_budget(monkeypatch, entries, manifest)
    ordered = sorted(e['entry_id'] for e in entries)
    first_block = next(registry.relevance_blocks(entries, [], manifest['max_roles'], manifest['candidates']))
    left = first_block[0]['entry_id']
    # Neither the first answer nor the correction judges ``left``: not an exact patch.
    call, calls = block_script(skip_initial={left, first_block[-1]['entry_id']}, skip_correction={left})
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    follow_ups = [p for s, p in calls if s == registry.RELEVANCE_PROMPT and [e['entry_id'] for e in p['entries']] == [left]]
    assert len(follow_ups) == 1
    scopes = [r['scope'] for r in manifest['selection_rounds']]
    assert 'relevance_follow_up' in scopes and scopes[-1] == 'relevant_entries'
    judged = [v['entry_id'] for r in manifest['selection_rounds'][:-1] for v in r['verdicts']]
    assert sorted(judged) == ordered  # every entry judged once, none guessed
    assert len(manifest['selected_roles']) == 4
    repaired = [r for r in manifest['panel_calls'] if r.get('repair')]
    assert len(repaired) == 1 and repaired[0]['repair']['changes']['left_for_follow_up'] == [left]
    assert not repaired[0].get('verdict_compositions')  # not an exact missing-ID patch
    count = len(calls)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == count


def test_block_with_no_usable_verdict_is_judged_in_the_final_choice(three_batches, monkeypatch):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 6)
    small_budget(monkeypatch, entries, manifest)
    call, calls = block_script(unknown_only=True)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    # Multi-entry blocks answered only with unknown IDs, twice: kept unfinished, not guessed.
    unusable = [r for r in manifest['panel_calls'] if r['status'] == 'running']
    assert unusable and all(r['correction']['status'] == 'invalid' and 'repair' not in r for r in unusable)
    final = [p for s, p in calls if s.startswith(registry.PANEL_PROMPT) and not s.endswith(registry.CORRECTION_SUFFIX)]
    assert len(final) == 1
    block_judged = {v['entry_id'] for r in manifest['selection_rounds'][:-1] for v in r['verdicts']}
    carried = {e['entry_id'] for e in entries} - block_judged
    assert carried and carried <= {e['entry_id'] for e in final[0]['entries']}
    assert len(manifest['selected_roles']) == 4
    assert all(r['filled_via'] == 'documented' for r in manifest['selected_roles'])
    count = len(calls)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == count


def test_final_choice_left_out_verdicts_get_a_follow_up_then_documented_first_fill(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 4 + ['inferred'])
    ordered = sorted(e['entry_id'] for e in entries)
    skipped = ordered[0]
    call, calls = block_script(skip_initial={skipped, ordered[1]}, skip_correction={skipped}, final=True)
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    follow_ups = [p for s, p in calls if s == registry.RELEVANCE_PROMPT]
    assert [[e['entry_id'] for e in p['entries']] for p in follow_ups] == [[skipped]]
    composition = manifest['panel_composition']
    assert composition['policy'] == registry.ACCOUNTING_REPAIR_POLICY
    assert composition['follow_up_verdict_ids'] == [skipped]
    assert all(r['filled_via'] == 'documented' for r in manifest['selected_roles'])
    assert len(manifest['selected_roles']) == 4
    assert len(manifest['omissions']) + len(manifest['selected_roles']) == len(entries)


def test_miscopied_kept_id_in_the_final_choice_is_restored(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented'] * 5)
    ordered = sorted(e['entry_id'] for e in entries)
    def call(system, payload, output_model, max_tokens=8000):
        kept = list(ordered[:4]); kept[0] = kept[0][:-1] + ('0' if kept[0][-1] != '0' else '1')
        return output_model.model_validate({'verdicts': [{'entry_id': i, 'relevant': True,
            'reason': 'Scripted.'} for i in ordered], 'kept_ids': kept})
    registry.choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert sorted(r['registry_entry_id'] for r in manifest['selected_roles']) == ordered[:4]
    record = manifest['panel_calls'][-1]
    assert record['repair']['changes']['restored_kept_ids'][0]['restored_id'] == ordered[0]


def test_failed_reselection_resumes_with_zero_calls_for_its_saved_registry_failure(corpus, monkeypatch):
    """Engine path of the Mobility incident: a derived re-selection fails at a registry merge
    under the old stop-after-one-correction rule, then resumes on this code."""
    import json
    from test_reselect_stakeholders import source_scan, derive
    from requirement_reuse_service.workflow import engine
    store, source = source_scan(corpus)
    trial = derive(store, source)

    class Miscopies(SelectorClient):
        def generate_structured(self, **kw):
            if kw['output_model'].__name__ == 'RoleRegistry':
                payload = json.loads(kw['user'])
                self.calls.append(('RoleRegistry', payload))
                ids = [c['candidate_id'] for c in payload['candidates']]
                copied = [ids[0][:-1] + ('0' if ids[0][-1] != '0' else '1'), *ids[1:]]
                return RoleRegistry(groups=[{'representative_id': copied[0], 'member_ids': copied,
                                             'rationale': 'Scripted, one ID miscopied in both answers.'}])
            return super().generate_structured(**kw)

    def old_rule(*args, **kwargs):
        raise ValueError('Stakeholder decision remained invalid after its single correction: '
                         'missing_candidate_ids, unknown_candidate_ids.')
    failing = Miscopies()
    with monkeypatch.context() as context:
        context.setattr(registry, 'repair_registry_accounting', old_rule)
        engine.execute_run(store, trial['run_id'], failing)
    failed = store.get('run', trial['run_id'])
    assert failed['status'] == 'failed' and failed['stages']['role_selection'] == 'failed'
    index = len(failed['role_manifest']['registry_calls']) - 1
    saved = failed['role_manifest']['registry_calls'][index]
    assert saved['status'] == 'running' and saved['correction']['status'] == 'invalid'
    client = SelectorClient()
    engine.execute_run(store, trial['run_id'], client)
    resumed = store.get('run', trial['run_id'])
    manifest = resumed['role_manifest']
    assert resumed['stages']['role_selection'] == 'completed', resumed['diagnostics']
    recovered = manifest['registry_calls'][index]
    assert recovered['recovery']['policy'] == registry.ACCOUNTING_REPAIR_POLICY
    assert recovered['recovery']['model_calls'] == 0
    assert recovered['repair']['changes']['restored_ids'][0]['edit_distance'] == 1
    assert recovered['original'] == saved['original'] and recovered['correction'] == saved['correction']
    # Only merges after the saved failure (e.g. the cross-source round) are new requests.
    later = manifest['registry_calls'][index + 1:]
    assert sum(name == 'RoleRegistry' for name, _ in client.calls) == len(later)
    assert all(r['status'] == 'completed' and 'correction' not in r for r in later)
    assert not any(name == 'RoleCandidates' for name, _ in client.calls)
    assert sorted(i for e in manifest['registry'] for i in e['member_candidate_ids']) == sorted(
        c['candidate_id'] for c in manifest['candidates'])
