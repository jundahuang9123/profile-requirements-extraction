"""Cross-source merge rounds place same-role entries in one block, so duplicates can meet.

The functional Mobility registry kept 'Data Owner', 'Data Provider', 'Data Custodian',
'Member States' and 'Metadata Point of Contact' twice each: blocks formed in entry-ID
(hash) order rarely put them side by side. All generation here is scripted and offline.
"""
import json

from test_role_selection import corpus, SelectorClient  # noqa: F401 (fixture dependency)
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow import stakeholder_registry as registry
from requirement_reuse_service.workflow.engine import freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RoleRegistry, RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import canonical

LABELS = ['Data Owner', 'Catalogue Operator', 'Data User', 'Funding Agency',
          'Publisher', 'Research Group', 'Standards Committee', 'Data Owners']


def test_role_noun_is_the_singular_head_of_the_label():
    assert registry.role_noun('Data Owners') == registry.role_noun('Owner') == 'owner'
    assert registry.role_noun('Public Authorities') == 'authority'
    assert registry.role_noun('Business & SME Re‑users') == 'user'
    assert registry.role_noun('Data Provider (Commission/JRC)') == 'provider'
    assert registry.role_noun('Data Access') == 'access'


def test_cross_source_rounds_put_same_role_entries_from_different_sources_in_one_block(corpus, monkeypatch):
    store, _, _ = corpus
    sources = [register_source(store, SourceRequest(source_role='stakeholder_need', artifact=ArtifactPayload(
        name=f'order-source-{i}.md', content=f'Catalogue operators maintain metadata for order fixture {i}.')))
        for i in range(len(LABELS))]
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[s['source_version_id'] for s in sources]))
    monkeypatch.setattr(selector, 'pack_batches', lambda units: [[u] for u in units])
    run = new_run(store, RunRequest(output_form='candidates', snapshot_id=snapshot['snapshot_id'],
        strategy='multi_agent', role_selection='automatic', consolidation='exact'))
    manifest = selector.select_roles(store, run, SelectorClient())
    assert len(manifest['candidates']) == len(LABELS)
    for candidate, label in zip(sorted(manifest['candidates'], key=lambda c: c['candidate_id']), LABELS):
        candidate['label'] = label
    for key in ('registry', 'registry_hash', 'registry_calls'):
        manifest.pop(key, None)
    entries = [registry.registry_entry(store, manifest, [c['candidate_id']], c['candidate_id'])
               for c in manifest['candidates']]
    # Room for two entries per merge request.
    pair = max(len(canonical({'candidates': [registry.registry_view(a), registry.registry_view(b)]}))
               for a in entries for b in entries if a is not b)
    monkeypatch.setattr(registry, 'MERGE_CHARS', pair + 10)
    offered = []
    def call(system, payload, output_model, max_tokens=8000):
        """Merge exactly the entries whose labels name the same role; keep others apart."""
        offered.append([c['label'] for c in payload['candidates']])
        groups = {}
        for c in payload['candidates']:
            groups.setdefault(registry.role_noun(c['label']), []).append(c['candidate_id'])
        return RoleRegistry(groups=[{'representative_id': ids[0], 'member_ids': ids,
                                     'rationale': 'Scripted: same role.'} for ids in groups.values()])
    result = registry.build_registry(store, manifest, [], call, lambda event: None, {'model': 'scripted'})
    owners = [e for e in result if registry.role_noun(e['label']) == 'owner']
    assert len(owners) == 1 and len(owners[0]['member_candidate_ids']) == 2
    assert len(result) == len(LABELS) - 1
    assert sorted(i for e in result for i in e['member_candidate_ids']) == sorted(
        c['candidate_id'] for c in manifest['candidates'])
    # Every request still lists its entries in ID order.
    for record in manifest['registry_calls']:
        assert record['status'] == 'completed'
    assert any(sorted(map(registry.role_noun, labels)) == ['owner', 'owner'] for labels in offered)
