"""Premise-specific excerpt selection preserves authentic text without asserting entailment."""
import base64
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.citations import elicitation_batch, materialize_observation
from requirement_reuse_service.workflow.engine import (TrackedClient, elicit, freeze_snapshot, new_run,
    record_from_observation, verify, ensure_elicitation_resumable)
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (RunRequest, SnapshotRequest, SourceRequest,
    SpanObservation, SpanElicitationResult)
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import pdfplumber
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    text = 'Each Na-\ntional Access Point must provide metadata.\nThe same actor. The same actor.'
    @contextmanager
    def fake_pdf(_):
        yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    monkeypatch.setattr(pdfplumber, 'open', fake_pdf)
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.pdf',
        content=base64.b64encode(b'%PDF-original-fixture-bytes').decode(), content_encoding='base64'),
        source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                   role_ids=['consumer_discovery']))
    return store, run


def payload(data, *, obligation=True, unknown=False, unsupported=False):
    spans = data['evidence_units'][0]['source_spans']
    links = [] if unsupported else [
        {'source_span_id': 'outside-this-batch' if unknown else spans[0]['span_id'], 'component': 'statement'},
        {'source_span_id': spans[1]['span_id'], 'component': 'statement'}]
    if obligation and not unsupported:
        links.append({'source_span_id': spans[1]['span_id'], 'component': 'obligation'})
    return {'observations': [{'observation_id': 'model-id', 'role_id': 'untrusted-role',
        'statement': 'Describe National Access Point metadata.', 'evidence_links': links,
        'requirement_type': 'descriptive_metadata',
        'intent': {'resource_type': 'DataService', 'metadata_need': 'metadata',
                   'obligation_hint': 'unknown' if unsupported else 'mandatory'},
        'support_level': 'unsupported' if unsupported else 'explicit'}]}


def test_multiline_pdf_citations_and_obligation_are_materialized_and_audited(corpus):
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user)))
    observations, reports = elicit(store, run, TrackedClient(client, store, run['run_id']))
    assert len(observations) == 1 and reports[0]['status'] == 'completed'
    observation = observations[0]
    assert [link.quote for link in observation.evidence_links] == [
        'Each Na-', 'tional Access Point must provide metadata.', 'tional Access Point must provide metadata.']
    assert observation.evidence_links[1].quote_start == len('Each Na-\n')
    assert observation.role_id == 'consumer_discovery'
    record = record_from_observation(run['run_id'], observation)
    assert verify(store, record, run['evidence_ids'])['status'] == 'pass'
    report = reports[0]
    assert report['citation_selections'][0]['status'] == 'materialized'
    assert report['raw_outputs'][0]['observations'][0]['evidence_links'][0] == {
        'source_span_id': 's0', 'relation': 'supports', 'component': 'statement'}
    saved_call = store.get('run', run['run_id'])['model_calls'][0]
    assert saved_call['output_contract'] == 'SpanElicitationResult'
    assert 'quote' not in saved_call['output']['observations'][0]['evidence_links'][0]


def test_missing_obligation_premise_is_still_blocked(corpus):
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user), obligation=False))
    observations, _ = elicit(store, run, client)
    verification = verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])
    assert verification['status'] == 'fail'
    assert verification['component_checks'] == {'statement_premise': True, 'obligation_premise': False}


def test_unknown_excerpt_stops_role_preserves_raw_response_and_cannot_fallback(corpus):
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user), unknown=True))
    observations, reports = elicit(store, run, client)
    assert observations == []
    assert reports[0]['status'] == 'failed'
    assert 'outside this batch' in reports[0]['error']
    assert reports[0]['raw_outputs'][0]['observations']
    assert reports[0]['citation_selections'][0]['status'] == 'invalid'


def test_unsupported_hypothesis_retains_empty_evidence_and_fails_gate(corpus):
    store, run = corpus
    observations, reports = elicit(store, run, MockLLMClient(
        lambda system, user: payload(json.loads(user), unsupported=True)))
    assert reports[0]['status'] == 'completed' and observations[0].support_level == 'unsupported'
    assert observations[0].evidence_links == []
    assert verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])['status'] == 'fail'


def test_generated_quote_is_not_accepted_by_new_provider_contract():
    with pytest.raises(ValueError):
        SpanElicitationResult.model_validate({'observations': [{'observation_id': 'x', 'role_id': 'x',
            'statement': 'A need.', 'evidence_links': [{'evidence_id': 'x', 'quote': 'A fabricated quotation.'}]}]})


def test_old_extraction_resume_rejected_before_provider_and_preserves_history(corpus, monkeypatch):
    from requirement_reuse_service.workflow import api
    store, run = corpus
    def legacy(r):
        r['status'] = 'failed'
        r['elicitation_policy_version'] = 'rq1-independent-elicitation-v2.4'
    store.mutate(run['run_id'], None, 'legacy_fixture', legacy)
    before = store.get('run', run['run_id'])
    monkeypatch.setattr(api, 'configured_client', lambda _: pytest.fail('No provider may be configured for this rejected resume'))
    result = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': before['version']})
    assert result.status_code == 422 and 'new run' in result.text
    assert store.get('run', run['run_id']) == before


def test_excerpt_batch_includes_all_units_without_silent_truncation():
    units = [{'evidence_id': f'unit-{i}', 'content': 'x' * 805 + '\nlast line',
              'kind': 'text_span'} for i in range(3)]
    payload_units, catalogue = elicitation_batch(units)
    assert len(payload_units) == 3
    for unit in units:
        spans = [s for s in catalogue if s['evidence_id'] == unit['evidence_id']]
        assert ''.join(s['quote'] for s in spans) == unit['content'].replace('\n', '')
        proposal = SpanObservation(observation_id='x', role_id='x', statement='Need.',
            evidence_links=[{'source_span_id': spans[-1]['span_id']}])
        link = materialize_observation(proposal, catalogue).evidence_links[0]
        assert link.evidence_id == unit['evidence_id'] and link.quote == 'last line'


def test_catalog_record_survives_extraction_and_materialization(corpus):
    """A valid DCAT class must not reject its batch or become Dataset."""
    from copy import deepcopy
    from requirement_reuse_service.models import NormalizedIntent as RecordIntent
    store, run = corpus
    def response(system, user):
        result = payload(json.loads(user))
        catalog = result['observations'][0]
        catalog['intent']['resource_type'] = 'CatalogRecord'
        dataset = deepcopy(catalog)
        dataset['observation_id'] = 'dataset-id'
        dataset['intent']['resource_type'] = 'Dataset'
        result['observations'].append(dataset)
        return result
    observations, reports = elicit(store, run, TrackedClient(MockLLMClient(response), store, run['run_id']))
    assert reports[0]['status'] == 'completed'
    assert [o.intent.resource_type for o in observations] == ['CatalogRecord', 'Dataset']
    for observation in observations:
        record = record_from_observation(run['run_id'], observation)
        assert record.normalized_intent.resource_type == observation.intent.resource_type
        assert RecordIntent(resource_type=observation.intent.resource_type).resource_type == observation.intent.resource_type
        assert record.evidence_links == observation.evidence_links
        assert verify(store, record, run['evidence_ids'])['status'] == 'pass'


def multiunit_run(corpus, count=5):
    store, _ = corpus
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='batch-needs.txt',
        content='\n'.join(f'Each dataset needs field {i}.' for i in range(count))), source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                  role_ids=['consumer_discovery']))
    assert len(run['evidence_ids']) == count
    return store, run


def unit_response(data):
    return {'observations': [{'observation_id': unit['evidence_id'], 'role_id': 'x',
        'statement': unit['source_spans'][0]['quote'], 'evidence_links': [
            {'source_span_id': unit['source_spans'][0]['span_id'], 'component': 'statement'}],
        'intent': {'resource_type': 'Dataset', 'metadata_need': 'field'},
        'support_level': 'explicit'} for unit in data['evidence_units']]}


def test_output_cutoff_splits_without_losing_units_or_accepting_partial_json(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = multiunit_run(corpus)
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            assert len(data['evidence_units']) <= 4
            if len(data['evidence_units']) > 1:
                raise OutputTokenLimitError('simulated provider length cutoff')
            return kwargs['output_model'].model_validate(unit_response(data))
    observations, reports = elicit(store, run, TrackedClient(Cutoff(), store, run['run_id']))
    assert reports[0]['status'] == 'completed'
    assert len(observations) == 5
    assert {o.evidence_links[0].evidence_id for o in observations} == set(run['evidence_ids'])
    selections = reports[0]['citation_selections']
    assert any(s.get('recovery') == 'split_into_smaller_batches' for s in selections)
    assert sum(s.get('observation_count', 0) for s in selections) == 5
    calls = store.get('run', run['run_id'])['model_calls']
    assert len(calls) == 8  # Seven nodes for four units, plus one final singleton.
    assert sum(c['status'] == 'failed' for c in calls) == 3


def test_single_unit_output_cutoff_has_one_bounded_larger_retry(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = corpus
    budgets = []
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            budgets.append(kwargs['max_tokens'])
            raise OutputTokenLimitError('simulated length cutoff')
    observations, reports = elicit(store, run, Cutoff())
    assert budgets == [8000, 12000]
    assert observations == [] and reports[0]['status'] == 'failed'
    assert reports[0]['citation_selections'][-1]['recovery'] == 'exhausted'


def test_schema_failure_does_not_trigger_token_recovery(corpus):
    from requirement_reuse_service.llm.client import LLMError
    store, run = corpus
    budgets = []
    class Invalid(MockLLMClient):
        def generate_structured(self, **kwargs):
            budgets.append(kwargs['max_tokens'])
            raise LLMError('normal stop but invalid schema')
    observations, reports = elicit(store, run, Invalid())
    assert budgets == [8000]
    assert observations == [] and reports[0]['status'] == 'failed'


def test_recovery_retains_completed_split_when_later_leaf_fails(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = multiunit_run(corpus, count=2)
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            if len(data['evidence_units']) > 1 or data['evidence_units'][0]['evidence_id'] == run['evidence_ids'][1]:
                raise OutputTokenLimitError('simulated length cutoff')
            return kwargs['output_model'].model_validate(unit_response(data))
    observations, reports = elicit(store, run, Cutoff())
    assert reports[0]['status'] == 'failed'
    assert len(observations) == 1 and observations[0].evidence_links[0].evidence_id == run['evidence_ids'][0]
    assert reports[0]['observation_ids'] == [observations[0].observation_id]


def test_restart_only_calls_unfinished_evidence_batches(corpus):
    from requirement_reuse_service.llm.client import LLMError
    store, run = multiunit_run(corpus)
    seen = []
    class InterruptSecondBatch(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            seen.append([unit['evidence_id'] for unit in data['evidence_units']])
            if len(seen) == 2:
                raise LLMError('Simulated process/provider interruption')
            return kwargs['output_model'].model_validate(unit_response(data))
    client = InterruptSecondBatch()
    partial, reports = elicit(store, run, client)
    assert len(partial) == 4 and reports[0]['status'] == 'failed'
    # Restore directly from the checkpoint without relying on the caller saving its return value.
    restored = Store(store.path).get('run', run['run_id'])
    assert len(restored['observations']) == 4
    completed, reports = elicit(store, restored, client)
    assert reports[0]['status'] == 'completed' and len(completed) == 5
    assert len(seen) == 3 and seen[2] == seen[1]
    assert set(seen[0]).isdisjoint(seen[2])
    assert {o.observation_id for o in partial} <= {o.observation_id for o in completed}


def test_schema_exhaustion_splits_and_continues_then_resumes_only_failed_units(corpus):
    from requirement_reuse_service.llm.client import OutputValidationError
    store, run = multiunit_run(corpus)
    seen = []
    failed_id = run['evidence_ids'][0]
    class InvalidBatch(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            assert kwargs['schema_repair_attempts'] == 1
            ids = [unit['evidence_id'] for unit in data['evidence_units']]
            seen.append(ids)
            if len(ids) > 1 or failed_id in ids:
                raise OutputValidationError('SpanElicitationResult', [{'loc': ['observations', 0], 'type': 'too_long'}])
            return kwargs['output_model'].model_validate(unit_response(data))
    partial, reports = elicit(store, run, TrackedClient(InvalidBatch(), store, run['run_id']))
    assert len(seen) == 8  # Four-unit binary split tree, plus the last source.
    assert len(partial) == 4 and reports[0]['status'] == 'failed'
    assert reports[0]['failed_batches'][0]['evidence_ids'] == [failed_id]
    assert {o.evidence_links[0].evidence_id for o in partial} == set(run['evidence_ids']) - {failed_id}
    restored = Store(store.path).get('run', run['run_id'])
    assert restored['role_runs'][0]['status'] == 'failed'
    assert len(restored['observations']) == 4
    replayed = []
    def recover(system, user):
        data = json.loads(user)
        replayed.extend(unit['evidence_id'] for unit in data['evidence_units'])
        return unit_response(data)
    completed, reports = elicit(store, restored, MockLLMClient(recover))
    assert reports[0]['status'] == 'completed' and len(completed) == 5
    assert replayed == [failed_id]
    assert {o.observation_id for o in partial} <= {o.observation_id for o in completed}


@pytest.mark.parametrize('invented_span', [False, True])
def test_real_client_correction_is_audited_and_still_passes_source_gate(corpus, monkeypatch, invented_span):
    import httpx
    import uuid
    from requirement_reuse_service.llm.client import OpenAICompatibleClient
    from requirement_reuse_service.llm.config import LLMConfig
    from requirement_reuse_service.workflow.evaluation import workflow_metrics
    store, run = corpus
    sent = []
    def post(*args, **kwargs):
        body = kwargs['json']
        sent.append(body)
        data = json.loads(body['messages'][1]['content'])
        proposal = payload(data, unknown=invented_span and len(sent) == 2)
        proposal['observations'][0]['intent']['value_kind'] = 'mixed' if len(sent) == 1 else 'unknown'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}},
            request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))
    monkeypatch.setattr(httpx, 'post', post)
    client = OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model='test',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1'))
    observations, reports = elicit(store, run, TrackedClient(client, store, run['run_id']))
    assert len(sent) == 2
    assert reports[0]['status'] == ('failed' if invented_span else 'completed')
    if invented_span:
        assert observations == []
        assert 'outside this batch' in reports[0]['error']
    else:
        assert len(observations) == 1
        record = record_from_observation(run['run_id'], observations[0])
        assert verify(store, record, run['evidence_ids'])['status'] == 'pass'
    saved = store.get('run', run['run_id'])
    call = saved['model_calls'][0]
    assert call['status'] == 'completed'  # JSON success is distinct from evidence validity.
    assert call['token_usage']['total_tokens'] == 60
    assert call['output_tokens_reserved'] == 16000
    metrics = workflow_metrics(saved)['model_calls']
    assert metrics['count'] == 1 and metrics['http_attempts'] == 2
    assert metrics['schema_correction_generations'] == 1
    assert metrics['actual_token_usage']['total_tokens'] == 60
    assert metrics['max_output_tokens_reserved_sum'] == 16000
