"""Whole-corpus stakeholder selection; all generation is scripted and offline."""
from copy import deepcopy

import pytest

from test_role_selection import corpus, auto_run, SelectorClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.engine import freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.stakeholder_registry import (build_registry, registry_entry,
    registry_view, panel_payload, choose_panel)
from requirement_reuse_service.workflow.storage import canonical


@pytest.fixture
def three_batches(corpus, monkeypatch):
    store, _, _ = corpus
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='three.md', content=(
        'Data publishers provide datasets.\nCatalogue operators maintain metadata.\nData users find datasets.')),
        source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    monkeypatch.setattr(selector, 'pack_batches', lambda units: [[u] for u in units])
    run = new_run(store, RunRequest(output_form='candidates', snapshot_id=snapshot['snapshot_id'],
        strategy='multi_agent', role_selection='automatic', consolidation='exact'))
    return store, run


def test_discovery_finishes_before_any_panel_call(three_batches):
    store, run = three_batches
    class Client(SelectorClient):
        def generate_structured(self, **kw):
            if kw['output_model'].__name__ == 'StakeholderPanel':
                assert sum(name == 'RoleCandidates' for name, _ in self.calls) == 3
            return super().generate_structured(**kw)
    client = Client()
    manifest = selector.select_roles(store, run, client)
    assert manifest['status'] == 'completed'
    assert sum(name == 'RoleCandidates' for name, _ in client.calls) == 3
    assert sum(name == 'StakeholderPanel' for name, _ in client.calls) == 1
    assert len(manifest['batch_reports']) == 3
    assert len(manifest['selection_rounds']) == 1


@pytest.mark.parametrize('policy', ['v7', 'v8', 'v9', 'v10', 'v11'])
def test_old_incomplete_scan_refused_and_not_mutated(corpus, policy):
    run = auto_run(corpus)
    manifest = run['role_manifest']
    manifest.update(policy_version='rq1-stakeholder-selection-' + policy, status='failed')
    before = deepcopy(manifest)
    with pytest.raises(ValueError, match='policy has changed'):
        selector.ensure_selection_resumable(manifest)
    assert manifest == before


def registry_only(store, manifest, client):
    def call(system, payload, output_model, max_tokens=8000):
        assert len(canonical(payload)) <= selector.MAX_REQUEST_CHARS
        return client.generate_structured(system=system, user=canonical(payload), output_model=output_model,
                                          max_tokens=max_tokens)
    return build_registry(store, manifest, [], call, lambda event: None, {'model': 'scripted'})


def test_registry_is_independent_of_candidate_and_report_order(three_batches):
    store, run = three_batches
    completed = selector.select_roles(store, run, SelectorClient())
    first, second = deepcopy(completed), deepcopy(completed)
    for manifest in (first, second):
        for key in ('registry', 'registry_hash', 'registry_calls'):
            manifest.pop(key, None)
    second['candidates'].reverse(); second['batch_reports'].reverse()
    a, b = SelectorClient(), SelectorClient()
    assert registry_only(store, first, a) == registry_only(store, second, b)
    assert a.calls == b.calls
    assert [registry_view(e) for e in first['registry']] == [registry_view(e) for e in second['registry']]
    assert sorted(i for e in first['registry'] for i in e['member_candidate_ids']) == sorted(
        c['candidate_id'] for c in completed['candidates'])


def test_registry_support_is_derived_and_documented_representative_required(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    for key in ('registry', 'registry_hash', 'registry_calls'):
        manifest.pop(key, None)
    original = manifest['candidates'][0]
    inferred = {**deepcopy(original), 'candidate_id': 'inferred-fixture', 'basis': 'inferred'}
    manifest['candidates'].append(inferred)
    manifest['batch_reports'][0]['candidate_ids'].append(inferred['candidate_id'])
    class Client(SelectorClient):
        def generate_structured(self, **kw):
            import json
            data = json.loads(kw['user'])
            if kw['output_model'].__name__ == 'RoleRegistry' and 'invalid_answer' not in data:
                self.calls.append(('RoleRegistry', data))
                inferred_entry = next((c for c in data['candidates'] if c['basis'] == 'inferred'), None)
                if inferred_entry:
                    return kw['output_model'].model_validate({'groups': [{
                        'representative_id': inferred_entry['candidate_id'],
                        'member_ids': [c['candidate_id'] for c in data['candidates']], 'rationale': 'Scripted invalid choice.'}]})
            return super().generate_structured(**kw)
    entries = registry_only(store, manifest, Client())
    assert entries[0]['basis'] == 'documented'
    assert entries[0]['sources'][0]['name'] == 'three.md'
    assert entries[0]['batch_count'] == 3
    representative = next(c for c in manifest['candidates'] if c['candidate_id'] == entries[0]['representative_id'])
    assert all(entries[0][k] == representative[k] for k in ('label', 'purpose', 'focus_questions', 'basis'))
    assert any(r.get('representative_normalizations') for r in manifest['registry_calls'])
    assert not any(r.get('correction') for r in manifest['registry_calls'])


def test_registry_collapses_only_identical_member_dispositions(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    for key in ('registry', 'registry_hash', 'registry_calls'):
        manifest.pop(key, None)
    class Duplicate(SelectorClient):
        def generate_structured(self, **kw):
            answer = super().generate_structured(**kw)
            if kw['output_model'].__name__ == 'RoleRegistry':
                answer.groups[0].member_ids.append(answer.groups[0].member_ids[0])
            return answer
    entries = registry_only(store, manifest, Duplicate())
    assert len(entries[0]['member_candidate_ids']) == 3
    assert all(r.get('duplicate_collapses') for r in manifest['registry_calls'])


def test_registry_tampered_support_is_refused(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    manifest['registry'][0]['batch_count'] = 999
    from requirement_reuse_service.workflow.storage import digest
    manifest['registry_hash'] = digest(manifest['registry'])
    with pytest.raises(ValueError, match='support does not match'):
        registry_only(store, manifest, SelectorClient())


def panel_fixture(three_batches, bases):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    original = manifest['candidates'][0]
    manifest['candidates'] = [{**deepcopy(original), 'candidate_id': 'candidate-' + str(i),
        'basis': basis, 'label': f'Perspective {i}'} for i, basis in enumerate(bases)]
    manifest['batch_reports'] = [{'batch_index': 0, 'candidate_ids': [c['candidate_id'] for c in manifest['candidates']]}]
    manifest.pop('panel_calls', None); manifest['selection_rounds'] = []; manifest['selected_roles'] = []
    return manifest, [registry_entry(store, manifest, [c['candidate_id']], c['candidate_id'])
                      for c in manifest['candidates']]


def panel_call_log(invalid_first=False, always_invalid=False):
    calls = []
    def call(system, payload, output_model, max_tokens=8000):
        calls.append(deepcopy(payload))
        entries = sorted(payload['entries'], key=lambda e: (
            ('documented', 'inferred', 'proposed').index(e['basis']), e['entry_id']))
        kept = [e['entry_id'] for e in entries[:payload['max_roles']]]
        if always_invalid or (invalid_first and len(calls) == 1):
            kept[0] = entries[-1]['entry_id']
        return output_model.model_validate({'verdicts': [{'entry_id': e['entry_id'], 'relevant': True,
            'reason': 'Addresses a documented activity.'} for e in payload['entries']], 'kept_ids': kept})
    return call, calls


@pytest.mark.parametrize('bases, expected', [
    (['documented']*2 + ['inferred']*3, {'documented': 2, 'fallback_inferred': 2}),
    (['inferred']*2 + ['proposed']*3, {'fallback_inferred': 2, 'fallback_proposed': 2}),
    (['proposed']*3, {'fallback_proposed': 3}),
])
def test_panel_fills_documented_then_inferred_then_proposed(three_batches, bases, expected):
    from collections import Counter
    manifest, entries = panel_fixture(three_batches, bases)
    call, calls = panel_call_log()
    choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == 1
    assert Counter(r['filled_via'] for r in manifest['selected_roles']) == expected
    assert len(calls[0]['entries']) == len(entries)
    assert all(r['source_support'] for r in manifest['selected_roles'])
    assert len(manifest['selection_rounds']) == 1


def test_documented_priority_is_corrected_only_once(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented']*4 + ['inferred'])
    call, calls = panel_call_log(invalid_first=True)
    choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == 2
    assert manifest['panel_calls'][0]['correction']['status'] == 'valid'
    assert all(r['filled_via'] == 'documented' for r in manifest['selected_roles'])


def test_failed_panel_correction_is_completed_by_the_documented_first_rule_not_repeated(three_batches):
    from requirement_reuse_service.workflow.stakeholder_registry import ACCOUNTING_REPAIR_POLICY
    manifest, entries = panel_fixture(three_batches, ['documented']*4 + ['inferred'])
    call, calls = panel_call_log(always_invalid=True)
    choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == 2
    record = manifest['panel_calls'][0]
    assert record['correction']['status'] == 'invalid'
    assert record['repair']['policy'] == ACCOUNTING_REPAIR_POLICY and record['repair']['model_calls'] == 0
    # The model kept the inferred entry in a documented place; the program fill restores the rule.
    assert all(r['filled_via'] == 'documented' for r in manifest['selected_roles'])
    assert len(manifest['selected_roles']) == 4
    assert manifest['panel_composition']['policy'] == ACCOUNTING_REPAIR_POLICY
    inferred = next(e['entry_id'] for e in entries if e['basis'] == 'inferred')
    assert inferred in manifest['panel_composition']['model_kept_ids']
    assert inferred not in manifest['panel_composition']['kept_ids']
    before = deepcopy(manifest)
    choose_panel(manifest, entries, [], call, lambda event: None, {'model': 'scripted'})
    assert len(calls) == 2 and manifest == before


def test_empty_discovery_alone_uses_explicit_default_roles(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient(empty=True))
    assert {r['filled_via'] for r in manifest['selected_roles']} == {'default'}
    assert all(r['basis'] == 'proposed' and not r['evidence_links'] for r in manifest['selected_roles'])
    assert not manifest.get('panel_calls')


def test_panel_prompt_is_order_independent(three_batches):
    manifest, entries = panel_fixture(three_batches, ['documented', 'inferred', 'proposed'])
    assert panel_payload(entries, [], 4, manifest['candidates']) == panel_payload(
        list(reversed(entries)), [], 4, list(reversed(manifest['candidates'])))


def test_scripted_48_batch_scan_counts_every_call(corpus, monkeypatch):
    from collections import Counter
    store, _, _ = corpus
    sources = [register_source(store, SourceRequest(source_role='stakeholder_need', artifact=ArtifactPayload(
        name=f'synthetic-source-{i:02}.md', content='\n'.join(
            f'Catalogue operators maintain metadata for fixture {i}-{j}.' for j in range(4 if i < 9 else 3)))))
        for i in range(13)]
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[s['source_version_id'] for s in sources]))
    monkeypatch.setattr(selector, 'pack_batches', lambda units: [[u] for u in units])
    run = new_run(store, RunRequest(output_form='candidates', snapshot_id=snapshot['snapshot_id'],
        strategy='multi_agent', role_selection='automatic', consolidation='exact'))
    client = SelectorClient()
    manifest = selector.select_roles(store, run, client)
    assert Counter(name for name, _ in client.calls) == {
        'RoleCandidates': 48, 'RoleRegistry': 14, 'StakeholderPanel': 1}
    assert len(manifest['candidates']) == 48
    assert sum(len(e['member_candidate_ids']) for e in manifest['registry']) == 48
    assert len(manifest['registry'][0]['sources']) == 13


def test_batch_support_counts_only_batches_with_member_citations(three_batches):
    store, run = three_batches
    manifest = selector.select_roles(store, run, SelectorClient())
    candidate = manifest['candidates'][0]
    manifest['batch_reports'].append({'batch_index': 999, 'candidate_ids': [candidate['candidate_id']],
                                      'evidence_ids': ['not-a-cited-unit']})
    entry = registry_entry(store, manifest, [candidate['candidate_id']], candidate['candidate_id'])
    assert entry['batch_count'] == 1
    candidate.update(basis='proposed', evidence_links=[], task_ids=[])
    uncited = registry_entry(store, manifest, [candidate['candidate_id']], candidate['candidate_id'])
    assert uncited['sources'] == [] and uncited['batch_count'] == 0
