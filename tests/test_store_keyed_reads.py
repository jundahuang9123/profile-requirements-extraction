"""Store reads that do not grow with the run (30 Oct scale check and the Health run's lock failure).

A need step looked up each saved answer by reading the run document and every part row, so each model call got
slower as the run grew (0.06 s to 0.3 s on Health). And the events of a run were read by scanning every run's
events: on the 1.8 GB store that held the read lock long enough for a live run's write to fail."""
import json
import sqlite3
import pytest
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_rq1_need_assessment import FullNeedsClient
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.storage import RUN_PARTS, Store


def chunk(n):
    return {'step': 'grouping', 'status': 'completed', 'n': n}


def test_a_keyed_entry_reads_as_the_whole_run_does(setup):
    store, run, _ = need_inputs(setup)
    rid = run['run_id']
    store.mutate(rid, None, 'test', lambda r: r['need_chunks'].update(a=chunk(1), b=chunk(2)))
    full = store.get_run(rid)['need_chunks']
    for key in ('a', 'b', 'missing'):
        assert store.get_run_part_entry(rid, 'need_chunks', key) == full.get(key)
    # Another run with an entry under the same key: each run reads its own.
    store.put('run', 'run-other', {**store.get_run(rid, parts=False), 'run_id': 'run-other'})
    assert store.get_run_part_entry('run-other', 'need_chunks', 'a') is None
    store.mutate('run-other', None, 'test', lambda r: r['need_chunks'].update(a=chunk(7)))
    assert store.get_run_part_entry('run-other', 'need_chunks', 'a') == chunk(7)
    assert store.get_run_part_entry(rid, 'need_chunks', 'a') == chunk(1)
    with pytest.raises(KeyError):
        store.get_run_part_entry('run-missing', 'need_chunks', 'a')
    for part in ('model_calls', 'machine_snapshot', 'not_a_part'):
        with pytest.raises(ValueError):
            store.get_run_part_entry(rid, part, 'a')


def test_an_entry_still_inline_in_an_earlier_document_is_found(setup):
    # An earlier layout kept parts inside the run document; get_run merges them, stored rows winning.
    store, run, _ = need_inputs(setup)
    rid = run['run_id']
    store.mutate(rid, None, 'test', lambda r: r['need_chunks'].update(a=chunk(1)))
    with sqlite3.connect(store.path) as db:
        body = json.loads(db.execute("SELECT body FROM objects WHERE kind='run' AND id=?", (rid,)).fetchone()[0])
        body['need_chunks'] = {'a': chunk(9), 'old': chunk(3)}
        db.execute("UPDATE objects SET body=? WHERE kind='run' AND id=?", (json.dumps(body), rid))
    full = store.get_run(rid)['need_chunks']
    assert full['a'] == chunk(1) and full['old'] == chunk(3)
    for key in ('a', 'old', 'missing'):
        assert store.get_run_part_entry(rid, 'need_chunks', key) == full.get(key)


def test_omitted_parts_are_not_read_and_the_rest_is_unchanged(setup):
    store, run, _ = need_inputs(setup)
    rid = run['run_id']
    store.mutate(rid, None, 'test', lambda r: r['need_chunks'].update(a=chunk(1)))
    full = store.get_run(rid)
    for omit in ((), ('model_calls',), tuple(p for p in RUN_PARTS if p != 'need_chunks'), tuple(RUN_PARTS)):
        assert store.get_run(rid, omit=omit) == {k: v for k, v in full.items() if k not in omit}


def test_the_events_of_a_run_are_read_through_an_index(setup):
    store, run, _ = need_inputs(setup)
    Store(str(store.path))
    with sqlite3.connect(store.path) as db:
        plan = ' '.join(str(row) for row in db.execute(
            'EXPLAIN QUERY PLAN SELECT sequence,event_type,body,created_at FROM events WHERE run_id=? ORDER BY sequence',
            (run['run_id'],)))
    assert 'events_by_run' in plan and 'SCAN events' not in plan
    assert store.events(run['run_id'])


@pytest.fixture
def no_full_lookup(monkeypatch):
    # The old lookup read the whole run with every part but need_chunks omitted.
    original = Store.get_run
    def guarded(self, run_id, *, parts=True, omit=()):
        assert set(omit) != set(RUN_PARTS) - {'need_chunks'}, 'saved answer looked up through the whole run'
        return original(self, run_id, parts=parts, omit=omit)
    monkeypatch.setattr(Store, 'get_run', guarded)


def test_saved_answers_are_looked_up_by_key(setup, no_full_lookup):
    store, run, records = need_inputs(setup)
    client = NeedsClient()
    written, events = needs.write_needs(store, run, [[records[0]], [records[1]]], client, None)
    calls = len(client.calls)
    again, replayed = needs.write_needs(store, run, [[records[0]], [records[1]]], client, None)
    assert len(client.calls) == calls and [n.revision_id for n in again] == [n.revision_id for n in written]
    needs.assess_needs(store, run, written, FullNeedsClient())
