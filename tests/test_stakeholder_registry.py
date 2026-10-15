"""Whole-corpus stakeholder selection; all generation is scripted and offline."""
from copy import deepcopy

import pytest

from test_role_selection import corpus, auto_run, SelectorClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.engine import freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest


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
