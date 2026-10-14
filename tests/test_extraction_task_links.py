"""Invalid task suggestions do not erase source-grounded extraction output."""
import json

import pytest

from test_workflow_span_extraction import corpus
from test_extraction_context import answer
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest


def task_run(corpus):
    store, initial = corpus
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(
        source_version_ids=store.get('snapshot', initial['snapshot_id'])['source_version_ids'],
        user_tasks=[{'id': identifier, 'statement': 'Users can discover data.'}
                    for identifier in ('CQ-bad', 'CQ-good', 'CQ-orphan')]))
    return store, engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'],
        strategy='multi_agent', output_form='needs', role_ids=['consumer_discovery']))


@pytest.mark.parametrize('bad_reason', [None, '', '   ', 'absent-field'])
def test_missing_reason_drops_only_its_link_and_preserves_raw_output_and_evidence(corpus, bad_reason):
    store, run = task_run(corpus)
    def respond(system, user):
        data = answer(json.loads(user), 'needs')
        row = data['observations'][0]
        row['supports_user_tasks'] = ['CQ-bad', 'CQ-good']
        row['task_justifications'] = [{'task_id': 'CQ-good', 'justification': 'Needed for discovery.'}]
        if bad_reason is not None:
            hint = {'task_id': 'CQ-bad'}
            if bad_reason != 'absent-field':
                hint['justification'] = bad_reason
            row['task_justifications'].append(hint)
        return data
    client = MockLLMClient(respond)
    observations, reports = engine.elicit(store, run, client)
    assert len(client.calls) == 1 and reports[0]['status'] == 'completed'
    observation = observations[0]
    assert observation.supports_user_tasks == ['CQ-good']
    assert [item.task_id for item in observation.task_justifications] == ['CQ-good']
    assert engine.verify(store, engine.record_from_observation(run['run_id'], observation),
                         run['evidence_ids'])['status'] == 'pass'
    audit = reports[0]['task_link_corrections']
    assert len(audit) == 1 and audit[0]['task_id'] == 'CQ-bad'
    assert audit[0]['reason'] == ('missing_justification' if bad_reason is None else 'blank_justification')
    assert audit[0]['raw_output_index'] == audit[0]['observation_index'] == 0
    raw = reports[0]['raw_outputs'][0]['observations'][0]
    assert raw['supports_user_tasks'] == ['CQ-bad', 'CQ-good']
    assert raw['evidence_links'] == [
        {'source_span_id': 's0', 'relation': 'supports', 'component': 'statement'},
        {'source_span_id': 's0', 'relation': 'supports', 'component': 'obligation'}]
    saved = store.get('run', run['run_id'])
    assert saved['role_runs'][0]['task_link_corrections'] == audit
    # Completed extraction and its correction audit can be read again without calls.
    again, resumed_reports = engine.elicit(store, saved, client)
    assert len(client.calls) == 1 and again == observations
    assert resumed_reports[0]['task_link_corrections'] == audit


def test_undeclared_duplicate_and_orphan_task_hints_are_each_audited(corpus):
    store, run = task_run(corpus)
    def respond(system, user):
        data = answer(json.loads(user), 'needs')
        row = data['observations'][0]
        row['supports_user_tasks'] = ['unknown', 'CQ-bad', 'CQ-good']
        row['task_justifications'] = [
            {'task_id': identifier, 'justification': 'A supplied reason.'}
            for identifier in ('unknown', 'CQ-bad', 'CQ-bad', 'CQ-good', 'CQ-orphan')]
        return data
    client = MockLLMClient(respond)
    observations, reports = engine.elicit(store, run, client)
    assert len(client.calls) == 1 and observations[0].supports_user_tasks == ['CQ-good']
    assert {(item['task_id'], item['reason']) for item in reports[0]['task_link_corrections']} == {
        ('unknown', 'undeclared_task_id'), ('CQ-bad', 'multiple_justifications'),
        ('CQ-orphan', 'justification_without_link')}
    assert reports[0]['invalid_task_ids'] == ['unknown']


def test_invalid_source_citation_still_rejects_the_answer_after_task_hint_cleanup(corpus):
    store, run = task_run(corpus)
    def respond(system, user):
        data = answer(json.loads(user), 'needs')
        row = data['observations'][0]
        row['supports_user_tasks'] = ['CQ-bad']
        row['evidence_links'][0]['source_span_id'] = 'outside-this-batch'
        return data
    client = MockLLMClient(respond)
    observations, reports = engine.elicit(store, run, client)
    assert observations == [] and reports[0]['status'] == 'failed' and len(client.calls) == 2
    assert 'outside this batch' in reports[0]['error']
    assert len(reports[0]['task_link_corrections']) == 2
    assert all(row['status'] == 'invalid' for row in reports[0]['citation_selections'])
