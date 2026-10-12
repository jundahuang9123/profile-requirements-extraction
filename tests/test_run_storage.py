"""Run parts are stored as rows: updates rewrite only the run document, readers see full runs."""
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import api, engine
from requirement_reuse_service.workflow.engine import TrackedClient, execute_run, freeze_snapshot, new_run
from requirement_reuse_service.workflow.evaluation import workflow_metrics
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import RUN_PARTS, ConflictError, PartNotLoaded, Store, canonical, digest

from test_resume_discussions import NEEDS, ROLES, ScriptedClient


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=NEEDS),
                                                  source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    client = ScriptedClient()
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    run = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_ids=ROLES))
    return store, run, client


def document(store, run_id):
    with sqlite3.connect(store.path) as db:
        return json.loads(db.execute('SELECT body FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone()[0])


def part_rows(store, run_id):
    with sqlite3.connect(store.path) as db:
        return dict(db.execute('SELECT part, count(*) FROM run_parts WHERE run_id=? GROUP BY part', (run_id,)).fetchall())


def test_parts_live_outside_the_run_document_but_readers_see_the_full_run(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    stored = document(store, run['run_id'])
    assert not set(RUN_PARTS) & stored.keys()
    rows = part_rows(store, run['run_id'])
    assert rows['model_calls'] == len(saved['model_calls']) == len(client.calls)
    assert rows['stage_results'] == len(saved['stage_results']) and 'consolidation' in saved['stage_results']
    assert rows['machine_snapshot'] == 1 and saved['machine_snapshot']['requirements']
    assert [c['output_contract'] for c in saved['model_calls']] == [name for name, _ in client.calls]
    # The API, the export and the evaluation see the same complete run.
    http = TestClient(app)
    assert http.get(f'/api/rq1/v2/runs/{run["run_id"]}').json() == saved
    assert http.get(f'/api/rq1/v2/runs/{run["run_id"]}/export').json()['run'] == saved
    assert workflow_metrics(saved)['model_calls']['count'] == len(client.calls)
    core = store.get_run(run['run_id'], parts=False)
    assert core == {key: value for key, value in saved.items() if key not in RUN_PARTS}


def test_model_calls_do_not_rewrite_the_run_document(setup):
    store, run, _ = setup
    before = store.get_run(run['run_id'], parts=False)
    tracked = TrackedClient(ScriptedClient(), store, run['run_id'])
    events = len(store.events(run['run_id']))
    for _ in range(3):
        with pytest.raises(AssertionError):     # the scripted client knows no such contract
            tracked.generate_structured(system='s', user='{}', output_model=type('Unknown', (), {}))
    after = store.get_run(run['run_id'], parts=False)
    assert after['version'] == before['version'] and after['job_lease_until'] > time.time() + 800
    assert {k: v for k, v in after.items() if k != 'job_lease_until'} == {k: v for k, v in before.items() if k != 'job_lease_until'}
    assert len(store.get('run', run['run_id'])['model_calls']) == 3
    assert [e['event_type'] for e in store.events(run['run_id'])[events:]] == ['model_call_recorded'] * 3


def test_a_cancelled_run_refuses_model_calls_and_the_lease_blocks_resume(setup):
    store, run, _ = setup
    store.touch_run(run['run_id'], time.time() + 900)
    store.mutate(run['run_id'], None, 'worker', lambda r: r.update(status='failed', worker_id='other-worker'))
    assert store.get_run(run['run_id'], parts=False)['job_lease_until'] > time.time()
    saved = store.get('run', run['run_id'])
    response = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': saved['version']})
    assert response.status_code == 409 and 'lease' in response.text
    store.mutate(run['run_id'], None, 'cancel', lambda r: r.update(status='cancelled'))
    with pytest.raises(ConflictError, match='cancelled'):
        store.touch_run(run['run_id'], time.time() + 900)


def test_change_functions_cannot_read_unloaded_parts_but_can_write_them(setup):
    store, run, _ = setup
    with pytest.raises(PartNotLoaded):
        store.mutate(run['run_id'], None, 'read', lambda r: len(r['model_calls']))
    with pytest.raises(TypeError):
        store.mutate(run['run_id'], None, 'serialize', lambda r: canonical(r))
    def edit_snapshot(r):
        r['machine_snapshot']['x'] = 1
    with pytest.raises(TypeError):        # the snapshot is replaced as a whole, never edited in place
        store.mutate(run['run_id'], None, 'edit', edit_snapshot)

    def write(r):
        r.setdefault('model_calls', []).append({'call_id': 'a'})
        r['stage_results']['normalization'] = {'requirements': [1]}
        r['stage_results'].update(verification={'requirements': [2]})
        r['machine_snapshot'] = {'requirements': [3]}
        r.setdefault('attempt_history', []).append({'status': 'failed'})
    store.mutate(run['run_id'], None, 'write', write)
    store.mutate(run['run_id'], None, 'write', lambda r: (r['model_calls'].append({'call_id': 'b'}),
                                                          r['stage_results'].pop('normalization', None)))
    saved = store.get('run', run['run_id'])
    assert saved['model_calls'] == [{'call_id': 'a'}, {'call_id': 'b'}]
    assert saved['stage_results'] == {'verification': {'requirements': [2]}}
    assert saved['machine_snapshot'] == {'requirements': [3]} and saved['attempt_history'] == [{'status': 'failed'}]
    store.mutate(run['run_id'], None, 'clear', lambda r: r.update(machine_snapshot={}))
    assert store.get('run', run['run_id'])['machine_snapshot'] == {}
    assert part_rows(store, run['run_id']).get('machine_snapshot') is None


def test_loaded_parts_save_appends_edits_and_removals(setup):
    store, run, _ = setup
    store.mutate(run['run_id'], None, 'seed', lambda r: (r['model_calls'].extend([{'n': 1}, {'n': 2}]),
                                                         r['stage_results'].update(a={'x': 1}, b={'x': 2})))
    rows_before = part_rows(store, run['run_id'])

    def change(r):
        assert [c['n'] for c in r['model_calls']] == [1, 2]
        r['model_calls'].append({'n': 3})
        r['stage_results']['a']['x'] = 10          # edited in place
        del r['stage_results']['b']
        r['baselines'].append({'baseline_id': 'b1'})
        return len(r['model_calls'])
    assert store.mutate(run['run_id'], None, 'loaded', change, parts=True)['result'] == 3
    saved = store.get('run', run['run_id'])
    assert [c['n'] for c in saved['model_calls']] == [1, 2, 3]
    assert saved['stage_results'] == {'a': {'x': 10}} and saved['baselines'] == [{'baseline_id': 'b1'}]
    assert part_rows(store, run['run_id'])['model_calls'] == rows_before['model_calls'] + 1
    # An edited list item rewrites the list rather than being lost.
    store.mutate(run['run_id'], None, 'edit', lambda r: r['model_calls'][0].update(n=100), parts=True)
    assert [c['n'] for c in store.get('run', run['run_id'])['model_calls']] == [100, 2, 3]


def test_runs_saved_by_earlier_versions_are_read_and_moved_on_their_next_update(setup):
    store, run, _ = setup
    legacy = {**store.get('run', run['run_id']), 'model_calls': [{'call_id': 'old-1'}, {'call_id': 'old-2'}],
              'stage_results': {'normalization': {'requirements': ['old']}}, 'machine_snapshot': {'requirements': ['old']},
              'attempt_history': [{'status': 'failed'}], 'baselines': []}
    with sqlite3.connect(store.path) as db:      # the layout an earlier version wrote
        db.execute('UPDATE objects SET body=? WHERE kind="run" AND id=?', (canonical(legacy), run['run_id']))
        db.execute('DELETE FROM run_parts WHERE run_id=?', (run['run_id'],))
        db.execute('DELETE FROM run_state WHERE run_id=?', (run['run_id'],))
        db.execute('INSERT INTO commands VALUES(?,?,?,?)', (run['run_id'], 'old-command', digest(None),
                                                            canonical({'run': legacy, 'result': {'ok': True}})))
    assert store.get('run', run['run_id']) == legacy
    # A model call recorded before the first update is appended after the inline calls.
    store.append_run_part(run['run_id'], 'model_calls', {'call_id': 'new-1'})
    store.touch_run(run['run_id'], time.time() + 900)
    assert [c['call_id'] for c in store.get('run', run['run_id'])['model_calls']] == ['old-1', 'old-2', 'new-1']
    store.mutate(run['run_id'], None, 'first_update', lambda r: r['model_calls'].append({'call_id': 'new-2'}))
    assert not set(RUN_PARTS) & document(store, run['run_id']).keys()
    migrated = store.get('run', run['run_id'])
    assert [c['call_id'] for c in migrated['model_calls']] == ['old-1', 'old-2', 'new-1', 'new-2']
    assert migrated['stage_results'] == legacy['stage_results'] and migrated['machine_snapshot'] == legacy['machine_snapshot']
    assert migrated['attempt_history'] == legacy['attempt_history']
    # An idempotent replay of a command saved by an earlier version shows the parts once.
    replay = store.mutate(run['run_id'], None, 'replayed', lambda r: None, key='old-command', payload=None, hydrate=True)
    assert replay['result'] == {'ok': True}
    assert [c['call_id'] for c in replay['run']['model_calls']] == ['old-1', 'old-2', 'new-1', 'new-2']


def test_api_responses_include_the_parts(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    record = next(r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids'])
    opened = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/deliberations', json={
        'expected_version': saved['version'], 'revision_ids': [record['revision_id']], 'question': 'Why?'})
    assert opened.status_code == 200, opened.text
    returned = opened.json()['run']
    assert returned['stage_results'].keys() == saved['stage_results'].keys()
    assert len(returned['model_calls']) == len(saved['model_calls'])


def test_each_excerpt_catalogue_is_stored_once_and_referenced_by_hash(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    selections = [s for report in saved['role_runs'] for s in report['citation_selections']]
    assert selections and all('catalogue' not in s for s in selections)
    hashes = {s['catalogue_hash'] for s in selections}
    # Both roles read the same batch: one stored catalogue serves both.
    assert len(selections) == len(ROLES) and len(hashes) == 1
    assert saved['catalogues'].keys() == hashes
    [catalogue] = saved['catalogues'].values()
    assert digest(catalogue) == next(iter(hashes)) and {span['quote'] for span in catalogue} == set(NEEDS.split('\n'))
    assert part_rows(store, run['run_id'])['catalogues'] == 1
    step = TestClient(app).get(f'/api/rq1/v2/runs/{run["run_id"]}/stages/elicitation').json()
    assert step['results']['catalogues'] == saved['catalogues']


def test_source_check_reports_keep_the_outcome_without_copying_the_passage(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    for record in saved['requirements']:
        assert record['verification']['status'] == 'pass'
        for link in record['verification']['links']:
            assert 'content' not in link
            assert link['status'] == 'pass' and link['source_hash'] and link['parser_version'] and 'quote_end' in link


def test_workbench_view_leaves_out_audit_parts_only(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    http = TestClient(app)
    full = http.get(f'/api/rq1/v2/runs/{run["run_id"]}').json()
    view = http.get(f'/api/rq1/v2/runs/{run["run_id"]}?audit=false').json()
    assert full['model_calls'] and full['machine_snapshot'] and full['catalogues']
    assert view == {key: value for key, value in full.items() if key not in api.AUDIT_PARTS}
    assert view['stage_results'] and 'attempt_history' in view and 'baselines' in view
