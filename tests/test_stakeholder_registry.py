"""Whole-corpus stakeholder selection; all generation is scripted and offline."""
from copy import deepcopy

import pytest

from test_role_selection import corpus, auto_run, SelectorClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.engine import freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.stakeholder_registry import build_registry, registry_entry, registry_view
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
            if kw['output_model'].__name__ == 'RolePanel':
                assert sum(name == 'RoleCandidates' for name, _ in self.calls) == 3
            return super().generate_structured(**kw)
    client = Client()
    manifest = selector.select_roles(store, run, client)
    assert manifest['status'] == 'completed'
    assert sum(name == 'RoleCandidates' for name, _ in client.calls) == 3
    assert sum(name == 'RolePanel' for name, _ in client.calls) == 1
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
    assert any(r.get('correction', {}).get('status') == 'valid' for r in manifest['registry_calls'])


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
