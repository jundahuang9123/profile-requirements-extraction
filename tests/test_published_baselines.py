"""A published baseline copies the run's model calls, machine snapshot and earlier attempts, so on a long run
it is far larger than the run's current state. Publishing loads only the parts it copies and answers with a
summary; views, step downloads and command responses list baselines by ``baseline_summaries``. The baseline
itself is read at ``/baselines/{id}``, in the full view and in the export, under the same hash as before."""
import json
import sqlite3
from collections import Counter

import pytest

from test_workflow import assess, context, decision, setup_run  # noqa: F401 (fixture)
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow import fa_discussion as fd
from requirement_reuse_service.workflow.models import DeriveRequest
from requirement_reuse_service.workflow.storage import Store, canonical, digest


@pytest.fixture
def part_reads(monkeypatch):
    """The rows read from the store, per part, while ``reads['on']`` is set."""
    reads = {'on': False, 'rows': Counter()}
    collect = Store._collect_parts
    def counted(rows, **kwargs):
        rows = list(rows)
        if reads['on']:
            reads['rows'].update(name for name, _, _ in rows)
        return collect(rows, **kwargs)
    monkeypatch.setattr(Store, '_collect_parts', staticmethod(counted))
    return reads


def accepted_run(context):
    """A run whose requirement a reviewer accepted, with one earlier attempt in its history."""
    store, client = context
    run = setup_run(context)
    store.mutate(run['run_id'], None, 'earlier_attempt', lambda r: r['attempt_history'].append({'status': 'failed'}))
    run = store.get('run', run['run_id'])
    record = run['requirements'][0]
    accepted, _ = decision(client, assess(client, run, record), [record['revision_id']])
    assert accepted.status_code == 200, accepted.text
    return accepted.json()['run'], record


def publish(client, run, record, key='baseline', name='Validated profile requirements'):
    return client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json={
        'expected_version': run['version'], 'idempotency_key': key, 'revision_ids': [record['revision_id']], 'name': name})


def test_publishing_loads_no_earlier_baseline_and_answers_with_a_summary(context, part_reads):
    store, client = context
    run, record = accepted_run(context)
    first = publish(client, run, record, key='first', name='First')
    assert first.status_code == 200, first.text
    run = first.json()['run']
    part_reads['on'] = True
    second = publish(client, run, record, key='second', name='Second')
    assert second.status_code == 200, second.text
    summaries = [first.json()['result'], second.json()['result']]
    assert [s['name'] for s in summaries] == ['First', 'Second']
    assert second.json()['run']['baseline_summaries'] == summaries and 'baselines' not in second.json()['run']
    # Repeated under its key, the command returns its first response.
    assert publish(client, run, record, key='second', name='Second').json() == second.json()
    assert part_reads['rows']['baselines'] == 0
    part_reads['on'] = False
    # The event and the saved response hold the summary, not two more copies of the baseline.
    event = [e for e in store.events(run['run_id']) if e['event_type'] == 'baseline_published'][-1]
    assert event['data']['result'] == summaries[1]
    with sqlite3.connect(store.path) as db:
        saved_response = json.loads(db.execute("SELECT result FROM commands WHERE run_id=? AND key='second'",
                                               (run['run_id'],)).fetchone()[0])
    assert saved_response['result'] == summaries[1]
    # The baselines themselves are saved in full, under the hash of everything but their hash and id.
    saved = store.get('run', run['run_id'])['baselines']
    assert [engine.baseline_summary(b) for b in saved] == summaries
    for baseline in saved:
        assert baseline['provenance']['attempt_history'] == [{'status': 'failed'}]
        assert baseline['baseline_hash'] == digest({k: v for k, v in baseline.items() if k not in {'baseline_hash', 'baseline_id'}})


def test_the_workbench_lists_baselines_without_reading_them(context, part_reads):
    store, client = context
    run, record = accepted_run(context)
    published = publish(client, run, record)
    summary, run = published.json()['result'], published.json()['run']
    base = f'/api/rq1/v2/runs/{run["run_id"]}'
    evidence = store.get('evidence', run['evidence_ids'][0])
    addition = {'expected_version': run['version'], 'idempotency_key': 'human-add', 'rationale': 'A missed need.',
        'draft': {'statement': 'Describe the represented asset.', 'scope': 'Stakeholder datasets',
                  'evidence_links': [{'evidence_id': evidence['evidence_id'], 'quote': evidence['content']}],
                  'requirement_type': 'quality_provenance', 'intent': {'resource_type': 'Dataset', 'metadata_need': 'asset',
                                                                       'obligation_hint': 'unknown'}}}
    part_reads['on'] = True
    view = client.get(base + '?audit=false').json()
    assert view['baseline_summaries'] == [summary] and 'baselines' not in view
    step = client.get(base + '/stages/baseline').json()
    assert step['status'] == 'completed' and step['results'] == {'baseline_summaries': [summary]}
    for path in ('/evaluation', '/stages/adjudication'):
        assert client.get(base + path).status_code == 200, path
    added = client.post(base + '/requirements', json=addition)
    assert added.status_code == 200, added.text
    assert added.json()['run']['baseline_summaries'] == [summary] and 'baselines' not in added.json()['run']
    assert part_reads['rows']['baselines'] == 0
    part_reads['on'] = False
    # The baseline itself: its download, the full view and the export.
    baseline = client.get(f'{base}/baselines/{summary["baseline_id"]}').json()
    assert engine.baseline_summary(baseline) == summary and baseline['requirements'][0]['lifecycle_state'] == 'accepted'
    assert client.get(base).json()['baselines'] == [baseline]
    assert client.get(base + '/export').json()['run']['baselines'] == [baseline]


def test_a_baseline_too_large_for_one_record_is_refused_and_nothing_is_saved(context, monkeypatch):
    store, client = context
    run, record = accepted_run(context)
    monkeypatch.setattr(engine, 'MAX_VALUE_BYTES', 10_000)
    refused = publish(client, run, record)
    assert refused.status_code == 422 and 'more than the run store keeps in one record' in refused.text
    after = store.get('run', run['run_id'])
    assert after['version'] == run['version'] and after['baselines'] == [] and after['baseline_summaries'] == []


def test_a_run_published_before_it_kept_summaries_still_lists_its_baselines(context):
    store, client = context
    run, record = accepted_run(context)
    summary = publish(client, run, record, key='first', name='First').json()['result']
    with sqlite3.connect(store.path) as db:   # as saved before this version: no summaries in the document
        body = json.loads(db.execute("SELECT body FROM objects WHERE kind='run' AND id=?", (run['run_id'],)).fetchone()[0])
        del body['baseline_summaries']
        db.execute("UPDATE objects SET body=? WHERE kind='run' AND id=?", (canonical(body), run['run_id']))
    base = f'/api/rq1/v2/runs/{run["run_id"]}'
    view = client.get(base + '?audit=false').json()
    assert view['baseline_summaries'] == [summary]
    assert client.get(base + '/stages/baseline').json()['results'] == {'baseline_summaries': [summary]}
    # The run's next baseline keeps the earlier one in the list.
    second = publish(client, view, record, key='second', name='Second').json()
    assert second['run']['baseline_summaries'] == [summary, second['result']]


def test_a_trial_derived_from_a_published_run_reads_and_copies_no_baseline(context, part_reads):
    store, client = context
    run, record = accepted_run(context)
    source = publish(client, run, record).json()['run']
    part_reads['on'] = True
    child = engine.derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'],
                              rationale='A fresh trial of the same sources.'))
    assert part_reads['rows']['baselines'] == 0
    assert child['baselines'] == [] and child['baseline_summaries'] == [] and child['attempt_history'] == []


def test_a_discussion_of_a_published_run_cannot_be_continued():
    upstream = ('acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization', 'verification', 'consolidation')
    source = {'run_id': 'run-published', 'version': 3, 'status': 'failed', 'request': {'stakeholder_workflow': 'fa_mediated'},
              'stages': {s: 'completed' for s in upstream}, 'baseline_summaries': [{'baseline_id': 'baseline-b'}]}
    with pytest.raises(ValueError, match='published baselines'):
        fd.derive_discussion_run(None, source, DeriveRequest(start_from='deliberation', expected_version=3, rationale='Continue.'), 'fixture')
