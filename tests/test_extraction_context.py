"""Extraction input contracts, using scripted output and no provider requests."""
import json
from copy import deepcopy

import pytest

from test_workflow_span_extraction import corpus, payload
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest
from requirement_reuse_service.workflow.storage import digest


def extraction_run(corpus, output_form='needs'):
    store, initial = corpus
    run = engine.new_run(store, RunRequest(snapshot_id=initial['snapshot_id'], strategy='multi_agent',
        output_form=output_form, role_ids=['consumer_discovery'], base_profile_id='dcat-ap-2.0.1'))
    return store, run


def answer(data, output_form):
    result = payload(data)
    if output_form == 'needs':
        for row in result['observations']:
            row.pop('extension_kind')
            row.pop('base_property')
    return result


@pytest.mark.parametrize('output_form', ['needs', 'candidates'])
def test_extraction_uses_role_description_without_discovery_citations_or_history(corpus, output_form):
    store, run = extraction_run(corpus, output_form)
    description = dict(role_id='consumer_discovery', label='Consumers', stakeholders=['Consumers'],
        basis='documented', purpose='Discover data.', focus_questions=['Can users find data?'],
        rationale='Consumers discover datasets.', evidence_links=[{'evidence_id': 'eu-discovery-only'}],
        citations=['eu-other-discovery'], candidate_ids=['historic-candidate'],
        lineage_candidate_ids=['historic-lineage'], task_ids=['old-task'], future_audit='audit-only')
    run['role_manifest']['selected_roles'] = [description]
    run['role_manifest']['manifest_hash'] = digest({k: v for k, v in run['role_manifest'].items()
                                                  if k != 'manifest_hash'})
    frozen_manifest = deepcopy(run['role_manifest'])
    client = MockLLMClient(lambda system, user: answer(json.loads(user), output_form))
    observations, reports = engine.elicit(store, run, client)
    assert observations and reports[0]['status'] == 'completed'
    data = json.loads(client.calls[0]['user'])
    assert data['stakeholder_perspective'] == {key: description[key] for key in (
        'label', 'stakeholders', 'basis', 'purpose', 'focus_questions', 'rationale')}
    assert all(marker not in client.calls[0]['user'] for marker in (
        'eu-discovery-only', 'eu-other-discovery', 'historic-candidate', 'historic-lineage', 'audit-only'))
    assert run['role_manifest'] == frozen_manifest
    assert reports[0]['prompt_version'] == 'rq1-independent-elicitation-v3.3'


@pytest.mark.parametrize('output_form', ['needs', 'candidates'])
def test_only_candidate_extraction_receives_the_pinned_base_profile(corpus, output_form):
    store, run = extraction_run(corpus, output_form)
    client = MockLLMClient(lambda system, user: answer(json.loads(user), output_form))
    observations, reports = engine.elicit(store, run, client)
    assert observations and reports[0]['status'] == 'completed'
    data = json.loads(client.calls[0]['user'])
    if output_form == 'needs':
        assert 'base_profile' not in data
        assert run['base_profile_id'] == 'dcat-ap-2.0.1'
        assert run['base_profile_sha256']
    else:
        assert data['base_profile'] == engine.run_extraction_base_context(run)


def test_needs_preflight_does_not_reserve_an_unused_base_table(corpus, monkeypatch):
    store, initial = corpus
    units = [store.get('evidence', eid) for eid in initial['evidence_ids']]
    batch, _ = engine.elicitation_batch(units)
    monkeypatch.setattr(engine, 'EXTRACTION_UNIT_CHARS', len(engine.canonical({'evidence_units': batch})) + 5000)
    _, run = extraction_run(corpus)
    assert run['base_profile_id'] == 'dcat-ap-2.0.1'
    with pytest.raises(ValueError, match='reserved extraction input budget'):
        extraction_run(corpus, 'candidates')


def small_units(count=4, chars=1000):
    return [{'evidence_id': f'unit-{index}', 'content': 'x' * chars, 'kind': 'text_span'}
            for index in range(count)]


def test_four_small_passages_share_one_batch_despite_12k_fixed_context():
    units = small_units()
    context = {'role': {'description': 'x' * 12000}, 'user_tasks': []}
    batches = engine.extraction_batches(units, context)
    assert batches == [units]
    payload, _ = engine.elicitation_batch(units)
    assert len(engine.canonical({**context, 'evidence_units': payload})) > 16000
    assert len(engine.canonical(payload)) < 16000


def test_45k_complete_input_cap_still_splits_small_passages():
    units = small_units()
    context = {'role': {'description': 'x' * 42000}}
    batches = engine.extraction_batches(units, context)
    assert [len(batch) for batch in batches] == [2, 2]
    assert [unit for batch in batches for unit in batch] == units
    for batch in batches:
        payload, _ = engine.elicitation_batch(batch)
        assert len(engine.canonical({**context, 'evidence_units': payload})) <= 45000


def test_passage_target_and_four_passage_cap_still_apply():
    assert [len(batch) for batch in engine.extraction_batches(small_units(9), {})] == [4, 4, 1]
    assert [len(batch) for batch in engine.extraction_batches(small_units(4, 6000), {})] == [2, 2]


def test_single_large_passage_uses_only_the_hard_limit():
    units = small_units(1, 17000)
    assert engine.extraction_batches(units, {}) == [units]
    with pytest.raises(ValueError, match='extraction budget'):
        engine.extraction_batches(units, {'role': 'x' * 45000})
