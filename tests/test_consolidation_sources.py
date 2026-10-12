"""Consolidation checks every merged candidate against its source but parses each source once."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine, evidence
from requirement_reuse_service.workflow.engine import execute_run, freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store

from test_resume_discussions import NEEDS, ROLES, ScriptedClient


def test_consolidation_parses_each_source_once_for_all_merged_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=NEEDS),
                                                  source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_ids=ROLES))
    parsed = []
    parse = evidence.decompose
    monkeypatch.setattr(evidence, 'decompose', lambda item: parsed.append(item.source_version_id) or parse(item))
    seen = {}
    merge = engine.consolidate

    def observed(*args, **kwargs):
        start = len(parsed)
        active, events, conflicts = merge(*args, **kwargs)
        seen.update(parsed=parsed[start:], merged=[e for e in events if e['action'] == 'equivalent_merge'])
        return active, events, conflicts
    monkeypatch.setattr(engine, 'consolidate', observed)

    execute_run(store, run['run_id'], ScriptedClient())
    saved = store.get('run', run['run_id'])
    merged = {e['outputs'][0] for e in seen['merged']}
    assert len(merged) == 3
    # Every merged candidate is still checked against the original source ...
    assert all(r['verification']['status'] == 'pass' for r in saved['requirements'] if r['revision_id'] in merged)
    # ... but the source is parsed once, not once per merged candidate.
    assert seen['parsed'] == [source['source_version_id']]
