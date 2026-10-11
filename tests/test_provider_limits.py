"""Exercise real client transport with fake HTTP responses, never provider calls."""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.llm import client as module
from requirement_reuse_service.llm.client import LLMError, OutputTokenLimitError, OpenAICompatibleClient, retry_after_seconds
from requirement_reuse_service.llm.config import LLMConfig


class Reply(BaseModel):
    value: str


@pytest.fixture
def config():
    # Unique fake endpoint prevents capacity settings from other tests interfering.
    import uuid
    return LLMConfig(provider='openai-compatible', model='test',
                     base_url=f'https://{uuid.uuid4().hex}.invalid/v1', api_key='test-secret')


def response(status, headers=None):
    return httpx.Response(status, headers=headers,
        json={'choices': [{'message': {'content': '{"value":"ok"}'}}]},
        request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))


def invoke(client):
    return client.generate_structured(system='s', user='u', output_model=Reply)


def test_429_retries_honor_retry_after_and_audit_without_credentials(config, monkeypatch):
    responses = iter([response(429, {'Retry-After': '3'}), response(429), response(200)])
    waits = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: next(responses))
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    client = OpenAICompatibleClient(config)
    assert invoke(client).value == 'ok'
    audit = client.last_call_metadata()
    assert waits == [3.0, 4.0]
    assert [a['status_code'] for a in audit['http_attempts']] == [429, 429, 200]
    assert audit['retry_wait_seconds'] == 7
    assert 'test-secret' not in json.dumps(audit)
    assert 'Authorization' not in json.dumps(audit)


def test_exhausted_rate_limit_is_bounded(config, monkeypatch):
    attempts, waits = [], []
    def post(*a, **kw):
        attempts.append(kw['json'])
        return response(429)
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='429'):
        invoke(client)
    # Default patience covers a one-minute rate window without a Retry-After header.
    assert len(attempts) == 6
    assert waits == [2.0, 4.0, 8.0, 16.0, 32.0]
    assert client.last_call_metadata()['http_attempts'][-1]['action'] == 'rate_limit_budget_exhausted'


def test_rate_limit_patience_is_configurable_and_never_exceeds_wait_budget(config, monkeypatch):
    waits = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: response(429))
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    config.rate_limit_retries, config.retry_wait_budget = 8, 10
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='429'):
        invoke(client)
    # 2 + 4 fit the 10-second budget; the next 8-second wait would exceed it.
    assert waits == [2.0, 4.0]
    assert client.last_call_metadata()['retry_wait_seconds'] == 6


def test_timeout_dropped_connection_and_gateway_errors_are_retried(config, monkeypatch):
    request = httpx.Request('POST', 'https://provider.invalid/v1/chat/completions')
    outcomes = iter([httpx.ReadTimeout('secret-bearing detail must not be audited', request=request),
                     response(503), response(200)])
    waits = []
    def post(*a, **kw):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    client = OpenAICompatibleClient(config)
    assert invoke(client).value == 'ok'
    audit = client.last_call_metadata()
    assert waits == [2.0, 4.0]
    assert [a.get('action') for a in audit['http_attempts']] == ['transient_retry', 'transient_retry', None]
    assert audit['http_attempts'][0]['error'] == 'ReadTimeout' and 'status_code' not in audit['http_attempts'][0]
    assert [a.get('status_code') for a in audit['http_attempts'][1:]] == [503, 200]
    assert audit['retry_wait_seconds'] == 6
    assert 'secret-bearing' not in json.dumps(audit)


@pytest.mark.parametrize('failure', ['timeout', 'connection', 'protocol', 500, 502, 503, 504])
def test_transient_retries_are_bounded_then_fail_visibly(config, monkeypatch, failure):
    request = httpx.Request('POST', 'https://provider.invalid/v1/chat/completions')
    errors = {'timeout': httpx.ConnectTimeout('slow', request=request),
              'connection': httpx.ConnectError('refused', request=request),
              'protocol': httpx.RemoteProtocolError('closed', request=request)}
    count, waits = [], []
    def post(*a, **kw):
        count.append(1)
        if failure in errors:
            raise errors[failure]
        return response(failure)
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match=str(failure) if isinstance(failure, int) else type(errors[failure]).__name__):
        invoke(client)
    assert len(count) == 3 and waits == [2.0, 4.0]
    last = client.last_call_metadata()['http_attempts'][-1]
    assert last['action'] == 'transient_retries_exhausted'


def test_transient_retries_can_be_disabled_and_honor_retry_after(config, monkeypatch):
    request = httpx.Request('POST', 'https://provider.invalid/v1/chat/completions')
    count = []
    def timeout(*a, **kw):
        count.append(1)
        raise httpx.ReadTimeout('slow', request=request)
    monkeypatch.setattr(httpx, 'post', timeout)
    monkeypatch.setattr(module.time, 'sleep', lambda _: pytest.fail('Disabled retries must not wait'))
    config.transient_retries = 0
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='ReadTimeout'):
        invoke(client)
    assert len(count) == 1
    assert client.last_call_metadata()['http_attempts'][0]['action'] == 'request_failed'
    # A gateway's own Retry-After is used instead of the fallback backoff, inside the budget.
    config.transient_retries = 2
    responses = iter([response(503, {'Retry-After': '7'}), response(200)])
    waits = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: next(responses))
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    assert invoke(OpenAICompatibleClient(config)).value == 'ok'
    assert waits == [7.0]


@pytest.mark.parametrize('status', [400, 403, 404, 422, 501])
def test_request_and_permission_errors_are_never_retried(config, monkeypatch, status):
    count = []
    def post(*a, **kw):
        count.append(kw['json'])
        return response(status)
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module.time, 'sleep', lambda _: pytest.fail('Must not wait for a non-transient failure'))
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match=str(status)):
        invoke(client)
    # HTTP 400 gets the existing single response_format fallback, nothing else repeats.
    assert len(count) == (2 if status == 400 else 1)
    assert client.last_call_metadata()['http_attempts'][-1]['action'] == 'request_failed'


def test_rate_limit_and_transient_retries_share_one_wait_budget(config, monkeypatch):
    responses = iter([response(429, {'Retry-After': '100'}), response(503, {'Retry-After': '30'})])
    waits = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: next(responses))
    monkeypatch.setattr(module.time, 'sleep', waits.append)
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='503'):
        invoke(client)
    # 100 seconds were already spent on the rate limit; 30 more would pass the 120-second budget.
    assert waits == [100.0]
    assert len(client.last_call_metadata()['http_attempts']) == 2


def test_long_retry_after_is_not_ignored_or_slept_past_budget(config, monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: response(429, {'Retry-After': '600'}))
    monkeypatch.setattr(module.time, 'sleep', lambda _: pytest.fail('Must not sleep past budget'))
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='429'):
        invoke(client)
    assert len(client.last_call_metadata()['http_attempts']) == 1


def test_auth_failure_is_not_retried(config, monkeypatch):
    count = []
    def post(*a, **kw):
        count.append(1)
        return response(401)
    monkeypatch.setattr(httpx, 'post', post)
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='401'):
        invoke(client)
    assert len(count) == 1


def test_response_format_fallback_and_429_share_a_bounded_audit(config, monkeypatch):
    responses = iter([response(400), response(429), response(200)])
    sent = []
    def post(*a, **kw):
        sent.append(kw['json'])
        return next(responses)
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    client = OpenAICompatibleClient(config)
    assert invoke(client).value == 'ok'
    assert 'response_format' in sent[0]
    assert all('response_format' not in body for body in sent[1:])
    assert len(client.last_call_metadata()['http_attempts']) == 3


def test_clients_share_endpoint_slots_and_record_own_attempts(config, monkeypatch):
    clients = [OpenAICompatibleClient(config) for _ in range(3)]
    active = maximum = 0
    guard = threading.Lock()
    def post(*a, **kw):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return response(200)
    monkeypatch.setattr(httpx, 'post', post)
    def work(client):
        invoke(client)
        return client.last_call_metadata()
    with ThreadPoolExecutor(max_workers=3) as pool:
        audits = list(pool.map(work, clients))
    assert maximum == 1
    assert all(len(a['http_attempts']) == 1 for a in audits)
    assert sum(a['queue_seconds'] for a in audits) > 0
    # A differently configured client does not create a second pool in this process.
    config.max_concurrency = 4
    assert OpenAICompatibleClient(config).describe()['max_concurrency'] == 1


def test_retry_after_http_date_and_bad_values():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=20), usegmt=True)
    assert 18 <= retry_after_seconds(date) <= 20
    assert retry_after_seconds('bogus') is None
    assert retry_after_seconds('NaN') is None
    assert retry_after_seconds('0') == 0


def test_invalid_limits_fail_before_network():
    with pytest.raises(ValueError, match='CONCURRENCY'):
        LLMConfig(max_concurrency=0)
    with pytest.raises(ValueError, match='RATE_LIMIT_RETRIES'):
        LLMConfig(rate_limit_retries=100)
    with pytest.raises(ValueError, match='TRANSIENT_RETRIES'):
        LLMConfig(transient_retries=4)
    with pytest.raises(ValueError, match='WAIT_BUDGET'):
        LLMConfig(retry_wait_budget=601)
    assert LLMConfig(rate_limit_retries=8, transient_retries=3, retry_wait_budget=600).retry_wait_budget == 600


def test_environment_sets_retry_bounds_and_provenance_records_reasoning_effort(monkeypatch):
    for name, value in {'RRS_LLM_PROVIDER': 'openai-compatible', 'RRS_LLM_MODEL': 'test',
                        'RRS_LLM_BASE_URL': 'https://env-bounds.invalid/v1', 'RRS_LLM_REASONING_EFFORT': 'low',
                        'RRS_LLM_RATE_LIMIT_RETRIES': '7', 'RRS_LLM_TRANSIENT_RETRIES': '1',
                        'RRS_LLM_RETRY_WAIT_BUDGET': '300'}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr('requirement_reuse_service.llm.config._runtime_config', None)
    description = OpenAICompatibleClient(LLMConfig.from_env()).describe()
    assert description['reasoning_effort'] == 'low'
    assert (description['rate_limit_retries'], description['transient_retries'],
            description['retry_wait_budget_seconds'], description['timeout_seconds']) == (7, 1, 300.0, 240.0)
    monkeypatch.delenv('RRS_LLM_REASONING_EFFORT')
    monkeypatch.setenv('RRS_LLM_BASE_URL', 'https://env-default.invalid/v1')
    assert OpenAICompatibleClient(LLMConfig.from_env()).describe()['reasoning_effort'] is None


@pytest.mark.parametrize('content', ['{"value":"unfinished', '{"value":"valid but cutoff"}'])
def test_output_limit_rejects_partial_response_and_keeps_usage(config, monkeypatch, content):
    measured = {'prompt_tokens': 100, 'completion_tokens': 5000, 'total_tokens': 5100,
                'completion_tokens_details': {'reasoning_tokens': 4700, 'reasoning_text': 'never retain this'},
                'unexpected_text': 'never retain this'}
    result = httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': content}}],
                                     'usage': measured},
                            request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: result)
    client = OpenAICompatibleClient(config)
    with pytest.raises(OutputTokenLimitError, match='output token limit'):
        invoke(client)
    audit = client.last_call_metadata()
    assert audit['finish_reason'] == 'length'
    assert audit['response_chars'] == len(content)
    assert audit['token_usage']['completion_tokens_details'] == {'reasoning_tokens': 4700}
    assert audit['token_usage']['total_tokens'] == 5100
    assert len(audit['http_attempts']) == 1
    assert 'never retain this' not in json.dumps(audit)
    assert content not in json.dumps(audit)


def test_invalid_json_after_normal_stop_is_distinct_from_token_limit(config, monkeypatch):
    result = httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"value":"broken'}}]},
                            request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: result)
    client = OpenAICompatibleClient(config)
    with pytest.raises(LLMError, match='finish_reason=stop'):
        invoke(client)
    assert client.last_call_metadata()['token_usage'] is None


def test_missing_finish_reason_and_usage_remain_unknown(config, monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: response(200))
    client = OpenAICompatibleClient(config)
    assert invoke(client).value == 'ok'
    assert client.last_call_metadata()['finish_reason'] is None
    assert client.last_call_metadata()['token_usage'] is None
