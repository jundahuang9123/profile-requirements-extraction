"""A typed label outside its values no longer costs an extraction unit.

Two StatDCAT development runs lost units because roles gave resource types the contract does
not list. Labels are suggestions, not evidence: such a label becomes unknown and is recorded
with the value given; everything else is judged as before.
"""
import json

import pytest

from test_workflow_span_extraction import corpus, multiunit_run, unit_response
from test_extraction_context import answer
from requirement_reuse_service.llm.client import MockLLMClient, validate_json_payload
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import NeedSpanElicitationResult, RunRequest
from requirement_reuse_service.workflow.output_recovery import LABEL_POLICY, reset_unknown_labels


class Answering(MockLLMClient):
    """Validates like the real client: a contract failure carries the parsed JSON."""

    def __init__(self, respond):
        super().__init__()
        self.respond = respond

    def generate_structured(self, **kwargs):
        self.calls.append({'system': kwargs['system'], 'user': kwargs['user']})
        return validate_json_payload(json.dumps(self.respond(json.loads(kwargs['user']))), kwargs['output_model'])


def needs_run(corpus):
    store, initial = corpus
    return store, engine.new_run(store, RunRequest(snapshot_id=initial['snapshot_id'], strategy='multi_agent',
                                                   output_form='needs', role_ids=['consumer_discovery']))


def slipped(data, **labels):
    result = answer(data, 'needs')
    row = result['observations'][0]
    for field, value in labels.items():
        (row if field == 'requirement_type' else row['intent'])[field] = value
    return result


def test_labels_outside_the_contract_become_unknown_and_the_unit_is_kept(corpus):
    store, run = needs_run(corpus)
    client = Answering(lambda data: slipped(data, resource_type='Observation', value_kind='mixed'))
    observations, reports = engine.elicit(store, run, engine.TrackedClient(client, store, run['run_id']))
    report = reports[0]
    assert len(client.calls) == 1 and report['status'] == 'completed'
    assert (report['processed_unit_count'], report['evidence_unit_count']) == (1, 1)
    observation = observations[0]
    assert (observation.intent.resource_type, observation.intent.value_kind) == ('Unknown', 'unknown')
    # Everything that is not a typed label stays as answered, the stated obligation included.
    expected = answer(json.loads(client.calls[0]['user']), 'needs')['observations'][0]
    assert observation.statement == expected['statement'] and observation.intent.obligation_hint == 'mandatory'
    assert [link.component for link in observation.evidence_links] == ['statement', 'obligation']
    record = engine.record_from_observation(run['run_id'], observation)
    assert engine.verify(store, record, run['evidence_ids'])['status'] == 'pass'
    assert sorted((r['field'], r['value'], r['replacement']) for r in report['label_resets']) == [
        ('intent.resource_type', 'Observation', 'Unknown'), ('intent.value_kind', 'mixed', 'unknown')]
    assert all((r['batch_index'], r['raw_output_index'], r['observation_index']) == ('0:0', 0, 0)
               for r in report['label_resets'])
    selection = report['citation_selections'][0]
    assert selection['status'] == 'materialized' and selection['label_recovery']['policy'] == LABEL_POLICY
    assert report['raw_outputs'][0]['observations'][0]['intent']['resource_type'] == 'Unknown'
    saved = store.get('run', run['run_id'])
    assert saved['model_calls'][0]['status'] == 'failed'  # the contract failure itself stays on record
    again, resumed = engine.elicit(store, saved, client)
    assert len(client.calls) == 1 and again == observations
    assert resumed[0]['label_resets'] == report['label_resets']


@pytest.mark.parametrize('other', ['relation', 'support_level', 'statement'])
def test_any_other_contract_issue_still_rejects_the_whole_answer(corpus, other):
    store, run = needs_run(corpus)

    def respond(data):
        result = slipped(data, resource_type='Observation')
        row = result['observations'][0]
        if other == 'relation':
            row['evidence_links'][0]['relation'] = 'proves'
        elif other == 'support_level':
            row['support_level'] = 'documented'
        else:
            row.pop('statement')
        return result
    observations, reports = engine.elicit(store, run, Answering(respond))
    assert observations == [] and reports[0]['status'] == 'failed'
    assert [f['kind'] for f in reports[0]['failed_batches']] == ['schema_invalid']
    assert 'label_resets' not in reports[0]


def test_a_label_slip_in_a_batch_does_not_split_it(corpus):
    store, run = multiunit_run(corpus)

    def respond(data):
        result = unit_response(data)
        if len(result['observations']) > 1:
            result['observations'][1]['intent']['resource_type'] = 'Slice'
        return result
    client = Answering(respond)
    observations, reports = engine.elicit(store, run, client)
    assert reports[0]['status'] == 'completed' and len(observations) == 5
    assert [len(json.loads(call['user'])['evidence_units']) for call in client.calls] == [4, 1]
    assert [(r['observation_index'], r['value']) for r in reports[0]['label_resets']] == [(1, 'Slice')]


def test_a_reset_never_guesses_a_value_or_adds_an_obligation():
    row = {'observation_id': 'o', 'role_id': 'r', 'statement': 'Users can find datasets by the area they cover.',
           'requirement_type': 'spatial', 'intent': {'resource_type': 'Dataset', 'obligation_hint': 'required'}}
    issues = [{'loc': ['observations', 0, 'requirement_type'], 'type': 'literal_error'},
              {'loc': ['observations', 0, 'intent', 'obligation_hint'], 'type': 'literal_error'}]
    result, resets = reset_unknown_labels(NeedSpanElicitationResult, issues, {'observations': [row]})
    assert (result.observations[0].requirement_type, result.observations[0].intent.obligation_hint) == ('unknown', 'unknown')
    assert [(r['field'], r['value']) for r in resets] == [('requirement_type', 'spatial'),
                                                          ('intent.obligation_hint', 'required')]
    assert row['requirement_type'] == 'spatial'  # the parsed answer itself is not changed
    # Other fields, other issue types and incomplete JSON are never reset.
    for issue in ({'loc': ['observations', 0, 'scope'], 'type': 'literal_error'},
                  {'loc': ['observations', 0, 'support_level'], 'type': 'literal_error'},
                  {'loc': ['observations', 0, 'intent', 'resource_type'], 'type': 'string_type'}):
        assert reset_unknown_labels(NeedSpanElicitationResult, [issue], {'observations': [row]}) == (None, [])
    assert reset_unknown_labels(NeedSpanElicitationResult, issues, None) == (None, [])
