"""Replay response exhaustion/invalid contracts through HTTP, without inference."""
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.llm.client import OpenAICompatibleClient
from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RequirementRecord, RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    return Store()


def new_run(store, text='Each dataset must publish its title.'):
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=text),
        source_role='stakeholder_need'))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    return engine.new_run(store, RunRequest(output_form='candidates', consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='rules'))


def client():
    return OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model='fixture-model',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1', api_key='test-secret'))


def response(payload=None, *, finish='stop', status=200, usage=None):
    return httpx.Response(status, json={'choices': [{'finish_reason': finish, 'message': {
        'content': json.dumps(payload) if payload is not None else None}}], 'usage': usage},
        request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))


def valid_assessment():
    return {'support': 'explicit', 'rationale': 'The source states this need.', 'findings': [],
            'assessor': 'model-supplied', 'revision_hash': 'model-supplied'}


@pytest.mark.parametrize('failure', ['length', 'schema'])
def test_assessment_recovers_on_same_context_and_keeps_measured_attempts(store, monkeypatch, failure):
    run = new_run(store)
    engine.execute_run(store, run['run_id'])
    record = RequirementRecord.model_validate(store.get('run', run['run_id'])['requirements'][0])
    assert len(record.evidence_links) > 1  # Statement and obligation use one passage.
    sent = []
    def post(*args, **kwargs):
        body = deepcopy(kwargs['json'])
        sent.append(body)
        if len(sent) == 1:
            return response({'support': 'invalid'} if failure == 'schema' else None,
                finish='stop' if failure == 'schema' else 'length', usage={
                    'prompt_tokens': 100, 'completion_tokens': 4000, 'total_tokens': 4100,
                    'completion_tokens_details': {'reasoning_tokens': 3997}})
        return response(valid_assessment(), usage={'prompt_tokens': 100, 'completion_tokens': 200, 'total_tokens': 300})
    monkeypatch.setattr(httpx, 'post', post)
    q = engine.assess(store, record, engine.TrackedClient(client(), store, run['run_id']))
    assert q.support == 'explicit' and q.revision_hash == record.content_hash
    assert q.assessor == 'rq1-support-quality-v2.2/fixture-model'
    assert [b['max_tokens'] for b in sent] == [4000, 8000]
    assert sent[0]['messages'][1] == sent[1]['messages'][1]
    context = json.loads(sent[0]['messages'][1]['content'])
    assert len(context['evidence']) == 1 and len(context['requirement']['evidence_links']) > 1
    calls = store.get('run', run['run_id'])['model_calls']
    assert [c['status'] for c in calls] == ['failed', 'completed']
    assert [c['output_tokens_reserved'] for c in calls] == [4000, 8000]
    assert all(c['schema_repair_attempts'] == 0 for c in calls)
    assert calls[0]['token_usage']['completion_tokens_details']['reasoning_tokens'] == 3997
    assert 'test-secret' not in json.dumps(calls)


@pytest.mark.parametrize('failure', ['length', 'schema'])
def test_exhausted_assessment_retains_draft_and_continues_other_records(store, monkeypatch, failure):
    run = new_run(store, 'Each dataset must publish its title.\nEach dataset must specify its language.')
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        if len(sent) <= 2:
            return response({'support': 'bad'} if failure == 'schema' else None,
                            finish='stop' if failure == 'schema' else 'length')
        assert store.get('run', run['run_id'])['status'] == 'verifying'
        return response(valid_assessment())
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_run(store, run['run_id'], client())
    result = store.get('run', run['run_id'])
    assert result['status'] == 'awaiting_human' and result['stages']['verification'] == 'completed'
    assert len(result['requirements']) == 2 and len(sent) == 3
    first, second = map(RequirementRecord.model_validate, result['requirements'])
    assert first.verification['status'] == second.verification['status'] == 'pass'
    assert first.qualification.support == 'uncertain' and second.qualification.support == 'explicit'
    assert any(f.criterion == 'assessment_unavailable' and f.severity == 'blocking' for f in first.qualification.findings)
    assert first.qualification.revision_hash == first.content_hash
    assert not result['decisions'] and result['worker_id'] is None
    with pytest.raises(ValueError, match='semantic'):
        engine.eligible(first)
    # An infrastructure/output failure is not a substantive debate trigger.
    routes, routing = engine.route_cases({**result, 'strategy': 'multi_agent'}, [first, second], [{
        'revision_ids': [first.revision_id, second.revision_id], 'kind': 'obligation'}])
    assert routes == []
    assert next(r for r in routing if r['revision_id'] == first.revision_id)['reasons'] == ['assessment_unavailable']
    assert all(r['route'] == 'human_review' for r in routing)


def test_authentication_failure_is_not_retried_or_mislabelled_as_assessment(store, monkeypatch):
    run = new_run(store)
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response(status=401)
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_run(store, run['run_id'], client())
    result = store.get('run', run['run_id'])
    assert result['status'] == 'failed' and len(sent) == 1
    assert result['requirements'][0]['qualification'] is None
    assert '401' in result['diagnostics'][0]


def test_failed_source_check_never_calls_assessor(store, monkeypatch):
    run = new_run(store)
    engine.execute_run(store, run['run_id'])
    record = RequirementRecord.model_validate(store.get('run', run['run_id'])['requirements'][0])
    record.verification['status'] = 'fail'
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: pytest.fail('No inference on bad evidence'))
    q = engine.assess(store, record, client())
    assert q.assessor == 'deterministic-gate-v2' and q.findings[0].criterion == 'grounding'


def discussion(store):
    run = new_run(store, 'Each dataset must publish its title.\nEach dataset should publish its title.')
    engine.execute_run(store, run['run_id'])
    return store.get('run', run['run_id'])


@pytest.mark.parametrize('failure', ['length', 'schema'])
def test_discussion_retry_counts_every_generation_and_validates_citations(store, monkeypatch, failure):
    run = discussion(store)
    case = run['deliberations'][0]
    sent = []
    def post(*args, **kwargs):
        sent.append(deepcopy(kwargs['json']))
        if len(sent) == 1:
            return response({'body': 'Bad citation', 'evidence_ids': ['outside-corpus']} if failure == 'schema' else None,
                            finish='stop' if failure == 'schema' else 'length')
        context = json.loads(sent[-1]['messages'][1]['content'])
        return response({'body': 'Unresolved scope needs human review.', 'finished': True,
                         'evidence_ids': context['allowed_evidence_ids'][:1]})
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_case(store, run['run_id'], case['case_id'], client())
    result = store.get('run', run['run_id'])
    completed = next(c for c in result['deliberations'] if c['case_id'] == case['case_id'])
    assert completed['status'] == 'unresolved'
    assert completed['model_attempts'] == len(case['participants']) + 1 == len(sent)
    assert completed['output_tokens_reserved'] == 4000 * len(case['participants']) + 8000
    assert len(completed['messages']) == len(case['participants'])
    assert [b['max_tokens'] for b in sent[:2]] == [4000, 8000]
    assert sent[0]['messages'][1] == sent[1]['messages'][1]
    assert all('outside-corpus' not in m['evidence_ids'] for m in completed['messages'])
    assert len(result['model_calls']) == len(sent) and not result['decisions']


@pytest.mark.parametrize('limit,reason', [('max_calls', 'call_limit'), ('total_output_budget', 'output_token_budget'),
                                        ('time', 'time_budget'), ('cancel', 'cancelled')])
def test_discussion_cannot_spend_retry_past_any_budget(store, monkeypatch, limit, reason):
    run = discussion(store)
    case = run['deliberations'][0]
    clock = [0.0]
    monkeypatch.setattr(engine.time, 'monotonic', lambda: clock[0])
    if limit in {'max_calls', 'total_output_budget'}:
        store.mutate(run['run_id'], None, 'fixture_budget', lambda r: next(
            c for c in r['deliberations'] if c['case_id'] == case['case_id']).update(
                **{limit: 1 if limit == 'max_calls' else 4000}))
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        if limit == 'time':
            clock[0] = 301.0
        if limit == 'cancel':
            store.mutate(run['run_id'], None, 'fixture_cancel', lambda r: r.update(status='cancelled'))
        return response(finish='length')
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_case(store, run['run_id'], case['case_id'], client())
    completed = next(c for c in store.get('run', run['run_id'])['deliberations'] if c['case_id'] == case['case_id'])
    assert completed['status'] == ('cancelled' if limit == 'cancel' else 'budget_exhausted')
    assert completed['stop_reason'] == reason and len(sent) == completed['model_attempts'] == 1
    assert completed['output_tokens_reserved'] == 4000 and not completed['messages']


def test_historical_case_does_not_gain_new_retry_budget(store, monkeypatch):
    run = discussion(store)
    case = run['deliberations'][0]
    def old_case(r):
        c = next(c for c in r['deliberations'] if c['case_id'] == case['case_id'])
        c.update(policy_version='rq1-selective-v4')
        c.pop('max_retry_output_tokens')
        c.pop('model_attempts')
    store.mutate(run['run_id'], None, 'fixture_historical', old_case)
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response(finish='length')
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_case(store, run['run_id'], case['case_id'], client())
    completed = next(c for c in store.get('run', run['run_id'])['deliberations'] if c['case_id'] == case['case_id'])
    assert completed['status'] == 'failed' and len(sent) == 1
    assert completed['output_tokens_reserved'] == 4000


def test_cancel_during_successful_inflight_turn_does_not_append_or_override_case(store, monkeypatch):
    run = discussion(store)
    case = run['deliberations'][0]
    def post(*args, **kwargs):
        store.mutate(run['run_id'], None, 'fixture_case_cancel', lambda r: next(
            c for c in r['deliberations'] if c['case_id'] == case['case_id']).update(status='cancelled'))
        return response({'body': 'Late result', 'finished': True})
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_case(store, run['run_id'], case['case_id'], client())
    result = store.get('run', run['run_id'])
    completed = next(c for c in result['deliberations'] if c['case_id'] == case['case_id'])
    assert completed['status'] == completed['stop_reason'] == 'cancelled'
    assert not completed['messages']
    assert result['model_calls'][0]['status'] == 'completed'  # Transport result remains auditable.


@pytest.mark.parametrize('failure,expected_calls', [('length', 2), ('schema', 2), ('auth', 1)])
def test_discussion_repeated_failure_is_bounded_and_never_becomes_consensus(store, monkeypatch, failure, expected_calls):
    run = discussion(store)
    case = run['deliberations'][0]
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response({'body': 'Invalid evidence', 'evidence_ids': ['outside']} if failure == 'schema' else None,
                        finish='length' if failure == 'length' else 'stop', status=401 if failure == 'auth' else 200)
    monkeypatch.setattr(httpx, 'post', post)
    engine.execute_case(store, run['run_id'], case['case_id'], client())
    result = store.get('run', run['run_id'])
    completed = next(c for c in result['deliberations'] if c['case_id'] == case['case_id'])
    assert completed['status'] == 'failed' and not completed['messages']
    assert len(sent) == completed['model_attempts'] == expected_calls
    assert completed['output_tokens_reserved'] == (4000 if expected_calls == 1 else 12000)
    assert not result['decisions']
