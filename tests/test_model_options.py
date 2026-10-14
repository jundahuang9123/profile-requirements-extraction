"""Only synthetic HTTP replies are used; no model generation is performed."""
import json
import uuid

import httpx
import pytest
from pydantic import BaseModel

from requirement_reuse_service.llm.client import OpenAICompatibleClient, OutputTokenLimitError, OutputValidationError
from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.llm.model_options import reasoning_effort_for


class Reply(BaseModel):
    value: str


def client(model, effort='low'):
    return OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=model,
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1', reasoning_effort=effort))


def respond(monkeypatch, content, *, reason='stop', reasoning=None, usage=None):
    bodies = []
    def post(url, **kwargs):
        bodies.append(kwargs['json'])
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'finish_reason': reason, 'message': {'content': content, 'reasoning_content': reasoning}}],
            'usage': usage})
    monkeypatch.setattr(httpx, 'post', post)
    return bodies


def generate(c):
    return c.generate_structured(system='Return one value.', user='Synthetic fixture.', output_model=Reply, max_tokens=100)


@pytest.mark.parametrize(('model', 'sent'), [
    ('inferenz-gpt-oss-120b', 'low'), ('inferenz-qwen3-8-27b', 'low'),
    ('inferenz-mistral-small-4-119b', None), ('qwen3:27b', None), ('gpt-4o', None), ('unknown', None),
])
def test_reasoning_effort_is_sent_only_for_supported_models(monkeypatch, model, sent):
    bodies = respond(monkeypatch, '{"value":"answer"}')
    c = client(model)
    assert generate(c).value == 'answer'
    assert bodies[0].get('reasoning_effort') == sent
    assert ('reasoning_effort' in bodies[0]) == (sent is not None)
    assert c.describe()['reasoning_effort'] == sent


def test_qwen_38_effort_levels_are_distinct_from_gpt_oss():
    assert reasoning_effort_for('inferenz-qwen3-8-27b', 'xhigh') == 'xhigh'
    with pytest.raises(ValueError, match='unsupported'):
        reasoning_effort_for('inferenz-qwen3-8-27b', 'high')
    with pytest.raises(ValueError, match='unsupported'):
        reasoning_effort_for('inferenz-gpt-oss-120b', 'xhigh')


@pytest.mark.parametrize('content', [
    '<think>Private reasoning with {"value":"wrong"}.</think>\n{"value":"answer"}',
    'Private reasoning with {"value":"wrong"}.</think>```json\n{"value":"answer"}\n```',
])
def test_qwen_thinking_is_not_parsed_or_saved(monkeypatch, content):
    bodies = respond(monkeypatch, content, reasoning='A separate private trace.')
    c = client('inferenz-qwen3-8-27b')
    assert generate(c).value == 'answer'
    audit = c.last_call_metadata()
    assert audit['thinking_removed'] is True
    assert audit['separate_reasoning_present'] is True
    assert 'Private reasoning' not in json.dumps(audit)
    assert 'private trace' not in json.dumps(audit)
    assert len(bodies) == 1


def test_json_with_literal_thinking_marker_is_unchanged(monkeypatch):
    respond(monkeypatch, json.dumps({'value': 'A literal </think> in a source excerpt.'}))
    assert generate(client('inferenz-qwen3-8-27b')).value == 'A literal </think> in a source excerpt.'


def test_unclosed_thinking_is_never_accepted_as_answer(monkeypatch):
    respond(monkeypatch, '<think>{"value":"a JSON-shaped thought"}')
    with pytest.raises(OutputValidationError, match='unclosed_thinking'):
        generate(client('inferenz-qwen3-8-27b'))


def test_length_reason_rejected_even_with_complete_json_and_thinking(monkeypatch):
    respond(monkeypatch, '<think>Thought.</think>{"value":"complete"}', reason='length',
        usage={'completion_tokens': 100, 'completion_tokens_details': {'reasoning_tokens': 90}})
    c = client('inferenz-qwen3-8-27b')
    with pytest.raises(OutputTokenLimitError): generate(c)
    assert c.last_call_metadata()['token_usage']['completion_tokens_details']['reasoning_tokens'] == 90


def test_separate_reasoning_never_substitutes_for_absent_answer(monkeypatch):
    from requirement_reuse_service.llm.client import LLMError
    respond(monkeypatch, '', reasoning='{"value":"not an answer"}')
    with pytest.raises(LLMError, match='no structured text'):
        generate(client('inferenz-qwen3-8-27b'))


def test_missing_reasoning_usage_remains_unknown(monkeypatch):
    respond(monkeypatch, '{"value":"answer"}', usage={'completion_tokens': 20})
    c = client('inferenz-qwen3-8-27b'); generate(c)
    assert 'completion_tokens_details' not in c.last_call_metadata()['token_usage']
