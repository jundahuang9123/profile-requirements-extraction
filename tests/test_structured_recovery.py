"""Replay the live failure classes through real HTTP/validation code, offline."""
import json
import sys
import uuid
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.llm.client import OpenAICompatibleClient, OutputValidationError, OutputTokenLimitError, LLMError
from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.workflow.models import SpanElicitationResult
from requirement_reuse_service.workflow.role_selection import discovery_contract


class Reply(BaseModel):
    value: str


def client():
    return OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model='test',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1', api_key='test-secret'))


def response(payload, *, finish='stop', usage=None, status=200):
    return httpx.Response(status, json={
        'choices': [{'finish_reason': finish, 'message': {'content': payload if isinstance(payload, str) else json.dumps(payload)}}],
        'usage': usage}, request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))


def invoke(c, contract=Reply, repair=1):
    return c.generate_structured(system='Extract only supported needs.', user='Frozen source context.',
        output_model=contract, max_tokens=8000, schema_repair_attempts=repair)


def observation(links=1, value='literal'):
    return {'observation_id': 'o1', 'role_id': 'role', 'statement': 'A supported atomic need.',
        'intent': {'resource_type': 'Dataset', 'metadata_need': 'identifier', 'value_kind': value},
        'evidence_links': [{'source_span_id': f's{i}', 'component': 'statement'} for i in range(links)]}


@pytest.mark.parametrize('bad_kind', ['citations', 'enum', 'stakeholders', 'json'])
def test_live_failure_classes_receive_one_correction_without_relaxing_contract(monkeypatch, bad_kind):
    contract = SpanElicitationResult
    if bad_kind == 'citations':
        bad = {'observations': [observation(13)]}
        first, second = observation(12), observation()
        second['observation_id'] = 'o2'
        second['evidence_links'][0]['source_span_id'] = 's12'
        good = {'observations': [first, second]}
    elif bad_kind == 'enum':
        bad, good = {'observations': [observation(value='mixed')]}, {'observations': [observation(value='unknown')]}
    elif bad_kind == 'stakeholders':
        contract = discovery_contract(4)
        role = {'label': 'Publishers', 'stakeholders': [f'publisher-{i}' for i in range(7)],
            'basis': 'proposed', 'purpose': 'Examine publishing needs.', 'rationale': 'A suggested perspective.',
            'focus_questions': ['What do publishers need?']}
        bad, good = {'candidates': [role]}, {'candidates': [{**role, 'stakeholders': ['Data publishers']}]}
    else:
        contract, bad, good = Reply, '{"value":"unfinished', {'value': 'corrected'}
    with pytest.raises(OutputValidationError):
        from requirement_reuse_service.llm.client import validate_json_payload
        validate_json_payload(bad if isinstance(bad, str) else json.dumps(bad), contract)
    replies, sent = iter([response(bad), response(good)]), []
    def post(*args, **kwargs):
        sent.append(deepcopy(kwargs['json']))
        return next(replies)
    monkeypatch.setattr(httpx, 'post', post)
    c = client()
    result = invoke(c, contract)
    assert result == contract.model_validate(good)
    assert len(sent) == 2 and all(b['max_tokens'] == 8000 for b in sent)
    assert sent[1]['messages'][:2] == sent[0]['messages']
    assert sent[1]['messages'][2]['role'] == 'assistant'
    assert 'paths/types' in sent[1]['messages'][3]['content']
    audit = c.last_call_metadata()
    assert [a['validation'] for a in audit['generation_attempts']] == ['invalid', 'valid']
    assert audit['generation_attempts'][0]['validation_issue_count'] >= 1
    assert all(len(a['response_hash']) == 64 for a in audit['generation_attempts'])
    assert len(audit['http_attempts']) == 2
    assert 'test-secret' not in json.dumps(audit)
    assert 'Frozen source context.' not in json.dumps(audit)
    assert sent[1]['messages'][2]['content'] not in json.dumps(audit)
    if bad_kind == 'citations':
        # Recovery can split needs; the application itself never slices links.
        assert {link.source_span_id for item in result.observations for link in item.evidence_links} == {f's{i}' for i in range(13)}


def test_repeated_invalid_response_is_rejected_after_two_generations(monkeypatch):
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response({'observations': [observation(value='mixed')]})
    monkeypatch.setattr(httpx, 'post', post)
    c = client()
    with pytest.raises(OutputValidationError, match='literal_error.*finish_reason=stop'):
        invoke(c, SpanElicitationResult)
    assert len(sent) == 2
    assert all(a['validation'] == 'invalid' for a in c.last_call_metadata()['generation_attempts'])


@pytest.mark.parametrize('failure, expected', [('length', OutputTokenLimitError), ('auth', LLMError)])
def test_token_cutoff_and_authentication_do_not_trigger_schema_correction(monkeypatch, failure, expected):
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response({'value': 'valid'}, finish='length' if failure == 'length' else 'stop',
                        status=401 if failure == 'auth' else 200)
    monkeypatch.setattr(httpx, 'post', post)
    c = client()
    with pytest.raises(expected):
        invoke(c)
    assert len(sent) == 1
    assert len(c.last_call_metadata()['generation_attempts']) == 1


@pytest.mark.parametrize('missing', [False, True])
def test_usage_sums_both_generations_only_when_measured(monkeypatch, missing):
    replies = iter([
        response({'wrong': 'field'}, usage={'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30,
                                          'prompt_tokens_details': {'cached_tokens': 0}}),
        response({'value': 'ok'}, usage=None if missing else {'prompt_tokens': 40, 'completion_tokens': 50, 'total_tokens': 90})])
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: next(replies))
    c = client()
    assert invoke(c).value == 'ok'
    audit = c.last_call_metadata()
    assert audit['token_usage'] == (None if missing else {'prompt_tokens': 50, 'completion_tokens': 70, 'total_tokens': 120})
    assert audit['generation_attempts'][0]['token_usage']['total_tokens'] == 30


def test_schema_correction_is_opt_in_and_invalid_retry_count_fails_before_http(monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: pytest.fail('Must validate bounds before HTTP'))
    with pytest.raises(ValueError, match='zero or one'):
        invoke(client(), repair=2)
    sent = []
    def post(*args, **kwargs):
        sent.append(kwargs['json'])
        return response({'wrong': 'field'})
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(OutputValidationError):
        invoke(client(), repair=0)
    assert len(sent) == 1
