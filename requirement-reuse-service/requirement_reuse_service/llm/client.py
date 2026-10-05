from __future__ import annotations

import json
import re
from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from .config import LLMConfig

T = TypeVar('T', bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when an LLM provider call fails or returns unusable output."""


@runtime_checkable
class LLMClient(Protocol):
    """Minimal provider-agnostic interface for structured JSON generation.

    Implementations must return an instance of ``output_model`` validated
    against its schema. Provider, model id, and any sampling configuration are
    implementation details recorded via ``describe()`` for provenance.
    """

    def generate_structured(self, *, system: str, user: str, output_model: type[T], max_tokens: int | None = None) -> T:
        ...

    def describe(self) -> dict[str, str]:
        ...


class AnthropicClient:
    """Native Anthropic Messages API client using structured outputs."""

    def __init__(self, config: LLMConfig):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("The 'anthropic' package is required for the anthropic provider (pip install anthropic).") from exc
        kwargs: dict[str, Any] = {'timeout': config.timeout}
        if config.api_key:
            kwargs['api_key'] = config.api_key
        self._client = anthropic.Anthropic(**kwargs)
        self.model_id = config.resolved_model()
        self.max_tokens = config.max_tokens

    def generate_structured(self, *, system: str, user: str, output_model: type[T], max_tokens: int | None = None) -> T:
        try:
            response = self._client.messages.parse(
                model=self.model_id,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                thinking={'type': 'adaptive'},
                messages=[{'role': 'user', 'content': user}],
                output_format=output_model,
            )
        except Exception as exc:
            raise LLMError(f'Anthropic request failed: {exc}') from exc
        parsed = getattr(response, 'parsed_output', None)
        if parsed is None:
            raise LLMError(f'Anthropic returned no parseable structured output (stop_reason={getattr(response, "stop_reason", "?")}).')
        return parsed

    def describe(self) -> dict[str, str]:
        return {'provider': 'anthropic', 'model': self.model_id}


class OpenAICompatibleClient:
    """Client for any OpenAI chat-completions-compatible endpoint.

    Covers OpenAI, Ollama (http://localhost:11434/v1), vLLM, LM Studio,
    OpenRouter, Together, Groq, Mistral, DeepSeek, and similar servers. The
    JSON schema is embedded in the prompt and the response is validated with
    Pydantic, because native json-schema response formats are not uniformly
    supported across these servers.
    """

    def __init__(self, config: LLMConfig):
        try:
            import httpx
        except ImportError as exc:
            raise LLMError("The 'httpx' package is required for openai-compatible providers.") from exc
        if not config.base_url:
            raise LLMError('RRS_LLM_BASE_URL must be set for openai-compatible providers.')
        self._httpx = httpx
        self.base_url = config.base_url.rstrip('/')
        self.api_key = config.api_key
        self.model_id = config.resolved_model()
        self.max_tokens = config.max_tokens
        self.reasoning_effort = config.reasoning_effort
        self.timeout = config.timeout
        self.extra_headers = dict(config.extra_headers)

    def generate_structured(self, *, system: str, user: str, output_model: type[T], max_tokens: int | None = None) -> T:
        schema = json.dumps(output_model.model_json_schema(), indent=2)
        system_with_schema = (
            f'{system}\n\n'
            'Respond with a single JSON object only - no prose, no markdown fences. '
            f'The JSON object must conform to this JSON Schema:\n{schema}'
        )
        headers = {'Content-Type': 'application/json', **self.extra_headers}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        body: dict[str, Any] = {
            'model': self.model_id,
            'max_tokens': max_tokens or self.max_tokens,
            'messages': [
                {'role': 'system', 'content': system_with_schema},
                {'role': 'user', 'content': user},
            ],
            'response_format': {'type': 'json_object'},
        }
        if self.reasoning_effort:
            body['reasoning_effort'] = self.reasoning_effort
        text = self._post_chat(body, headers)
        return validate_json_payload(text, output_model)

    def _post_chat(self, body: dict[str, Any], headers: dict[str, str]) -> str:
        url = f'{self.base_url}/chat/completions'
        try:
            response = self._httpx.post(url, json=body, headers=headers, timeout=self.timeout)
            if response.status_code == 400 and 'response_format' in body:
                # Some local servers reject response_format; retry without it.
                retry_body = {key: value for key, value in body.items() if key != 'response_format'}
                response = self._httpx.post(url, json=retry_body, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except self._httpx.HTTPError as exc:
            raise LLMError(f'OpenAI-compatible request to {url} failed: {exc}') from exc
        payload = response.json()
        try:
            return payload['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f'Unexpected chat-completions response shape: {json.dumps(payload)[:400]}') from exc

    def describe(self) -> dict[str, str]:
        return {'provider': 'openai-compatible', 'model': self.model_id, 'base_url': self.base_url}


class MockLLMClient:
    """Deterministic offline client for tests, demos, and CI.

    Returns the configured payload (a dict, or a callable producing one)
    validated against the requested output model.
    """

    def __init__(self, payload: dict[str, Any] | Callable[[str, str], dict[str, Any]] | None = None):
        self.payload = payload if payload is not None else {'requirements': []}
        self.model_id = 'mock-model'
        self.calls: list[dict[str, str]] = []

    def generate_structured(self, *, system: str, user: str, output_model: type[T], max_tokens: int | None = None) -> T:
        self.calls.append({'system': system, 'user': user})
        data = self.payload(system, user) if callable(self.payload) else self.payload
        try:
            return output_model.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f'Mock payload does not match {output_model.__name__}: {exc}') from exc

    def describe(self) -> dict[str, str]:
        return {'provider': 'mock', 'model': self.model_id}


def validate_json_payload(text: str, output_model: type[T]) -> T:
    """Parse model output into ``output_model``, tolerating markdown fences."""
    candidate = extract_json_object(text)
    try:
        return output_model.model_validate_json(candidate)
    except ValidationError as exc:
        raise LLMError(f'LLM output failed schema validation for {output_model.__name__}: {exc}') from exc


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    fence = re.search(r'```(?:json)?\s*(\{.*\})\s*```', stripped, flags=re.DOTALL)
    if fence:
        return fence.group(1)
    start = stripped.find('{')
    end = stripped.rfind('}')
    if start >= 0 and end > start:
        return stripped[start:end + 1]
    raise LLMError(f'No JSON object found in LLM output: {stripped[:200]}')


def create_client(config: LLMConfig | None = None) -> LLMClient:
    config = config or LLMConfig.from_env()
    provider = config.provider.lower()
    if provider == 'disabled':
        raise LLMError('LLM provider is disabled; set RRS_LLM_PROVIDER and credentials/base URL to enable LLM extraction.')
    if provider == 'anthropic':
        return AnthropicClient(config)
    if provider in {'openai-compatible', 'openai', 'ollama'}:
        return OpenAICompatibleClient(config)
    if provider == 'mock':
        return MockLLMClient()
    raise LLMError(f"Unknown LLM provider '{config.provider}'. Use disabled, anthropic, openai-compatible, or mock.")
