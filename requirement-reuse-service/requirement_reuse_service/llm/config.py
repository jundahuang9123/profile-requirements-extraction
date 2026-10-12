from __future__ import annotations

import os
import math
import threading
from dataclasses import dataclass, field


DEFAULT_ANTHROPIC_MODEL = 'claude-opus-4-8'
_runtime_lock = threading.Lock()
_runtime_config: dict | None = None


def set_runtime_config(*, provider: str, model: str, base_url: str | None = None,
                       api_key: str | None = None, clear_api_key: bool = False,
                       preset: str | None = None) -> None:
    """Set process-local provider settings; credentials are never written to disk."""
    global _runtime_config
    provider = provider.strip().lower()
    if provider not in {'disabled', 'openai-compatible', 'anthropic'}:
        raise ValueError('Choose OpenAI-compatible, Anthropic, or disabled.')
    if provider != 'disabled' and not model.strip():
        raise ValueError('Choose or enter a model identifier.')
    with _runtime_lock:
        previous = _runtime_config or {}
        same_provider = (previous.get('provider') == provider and
                         (provider == 'anthropic' or previous.get('base_url') == (base_url or '').strip().rstrip('/')))
        environment = LLMConfig._environment_values() if not _runtime_config else {}
        same_environment = (environment.get('provider') == provider and
                            (provider == 'anthropic' or (environment.get('base_url') or '').rstrip('/') == (base_url or '').strip().rstrip('/')))
        key = None if clear_api_key else (api_key or (previous.get('api_key') if same_provider else None) or
                                          (environment.get('api_key') if same_environment else None))
        _runtime_config = {
            'provider': provider, 'model': model.strip() or None,
            'base_url': (base_url or '').strip().rstrip('/') or None,
            'api_key': key,
            'preset': preset or provider,
        }


def runtime_config_status() -> dict:
    """Safe status for the UI; this deliberately never returns credential data."""
    config = LLMConfig.from_env()
    return {'provider': config.provider, 'model': config.resolved_model() if config.provider != 'disabled' else 'disabled',
            'base_url': config.base_url, 'credential_configured': bool(config.api_key),
            'source': 'session' if _runtime_config is not None else 'environment',
            'preset': _runtime_config.get('preset') if _runtime_config is not None else config.provider}


@dataclass
class LLMConfig:
    """Provider-agnostic LLM configuration resolved from environment variables.

    Providers:
      - ``disabled``           no LLM provider configured; LLM, hybrid, and
                               multi-agent requests report a rule fallback
      - ``anthropic``          native Anthropic Messages API (default when an
                               Anthropic key is available)
      - ``openai-compatible``  any endpoint speaking the OpenAI chat-completions
                               dialect: OpenAI, Ollama, vLLM, LM Studio,
                               OpenRouter, Together, Groq, Mistral, DeepSeek, ...
      - ``mock``               deterministic offline client for tests and demos

    Environment variables:
      RRS_LLM_PROVIDER   disabled | anthropic | openai-compatible | mock
      RRS_LLM_MODEL      model id (default for anthropic: claude-opus-4-8)
      RRS_LLM_BASE_URL   base URL for openai-compatible endpoints
                         (e.g. http://localhost:11434/v1 for Ollama)
      RRS_LLM_API_KEY    API key for openai-compatible endpoints
      RRS_LLM_REASONING_EFFORT optional OpenAI-compatible reasoning control.
                                For Ollama thinking models, use none to return
                                structured content without a long reasoning trace.
      ANTHROPIC_API_KEY  key for the anthropic provider (standard SDK variable)
      RRS_LLM_MAX_TOKENS response token cap (default 16000)
      RRS_LLM_TIMEOUT    request timeout in seconds per HTTP attempt (default 240)
      RRS_LLM_MAX_CONCURRENCY endpoint-wide in-process request limit (default 1)
      RRS_LLM_RATE_LIMIT_RETRIES extra attempts after HTTP 429 (default 5, 0-8)
      RRS_LLM_TRANSIENT_RETRIES extra attempts after a timeout, a dropped
                                connection or HTTP 500/502/503/504 (default 2, 0-3)
      RRS_LLM_RETRY_BACKOFF initial fallback delay in seconds (default 2)
      RRS_LLM_RETRY_WAIT_BUDGET total retry wait per request in seconds
                                (default 120, 0-600), shared by both retry kinds
    """

    provider: str = 'disabled'
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int = 16000
    timeout: float = 240.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    max_concurrency: int = 1
    rate_limit_retries: int = 5
    transient_retries: int = 2
    retry_backoff: float = 2.0
    retry_wait_budget: float = 120.0

    def __post_init__(self):
        if not 1 <= self.max_concurrency <= 4:
            raise ValueError('RRS_LLM_MAX_CONCURRENCY must be between 1 and 4.')
        if type(self.rate_limit_retries) is not int or not 0 <= self.rate_limit_retries <= 8:
            raise ValueError('RRS_LLM_RATE_LIMIT_RETRIES must be between 0 and 8.')
        # Each transient retry can last a full request timeout, so this stays small.
        if type(self.transient_retries) is not int or not 0 <= self.transient_retries <= 3:
            raise ValueError('RRS_LLM_TRANSIENT_RETRIES must be between 0 and 3.')
        if not math.isfinite(self.retry_backoff) or not 0 < self.retry_backoff <= 60:
            raise ValueError('RRS_LLM_RETRY_BACKOFF must be positive and at most 60 seconds.')
        if not math.isfinite(self.retry_wait_budget) or not 0 <= self.retry_wait_budget <= 600:
            raise ValueError('RRS_LLM_RETRY_WAIT_BUDGET must be between 0 and 600 seconds.')

    @classmethod
    def from_env(cls) -> 'LLMConfig':
        with _runtime_lock:
            runtime = dict(_runtime_config) if _runtime_config is not None else None
        if runtime is not None:
            env = cls._environment_values()
            return cls(provider=runtime['provider'], model=runtime['model'], base_url=runtime['base_url'],
                       api_key=runtime['api_key'], **env['options'])
        values = cls._environment_values()
        options = values.pop('options')
        return cls(**values, **options)

    @classmethod
    def _environment_values(cls) -> dict:
        provider = os.environ.get('RRS_LLM_PROVIDER', '').strip().lower()
        if not provider:
            if os.environ.get('ANTHROPIC_API_KEY'):
                provider = 'anthropic'
            elif os.environ.get('RRS_LLM_BASE_URL'):
                provider = 'openai-compatible'
            else:
                provider = 'disabled'
        return {
            'provider': provider,
            'model': os.environ.get('RRS_LLM_MODEL') or None,
            'base_url': os.environ.get('RRS_LLM_BASE_URL') or None,
            'api_key': (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('RRS_LLM_API_KEY')) if provider == 'anthropic' else os.environ.get('RRS_LLM_API_KEY') or None,
            'options': {
                'reasoning_effort': os.environ.get('RRS_LLM_REASONING_EFFORT') or None,
                'max_tokens': int(os.environ.get('RRS_LLM_MAX_TOKENS', '16000')),
                'timeout': float(os.environ.get('RRS_LLM_TIMEOUT', '240')),
                'max_concurrency': int(os.environ.get('RRS_LLM_MAX_CONCURRENCY', '1')),
                'rate_limit_retries': int(os.environ.get('RRS_LLM_RATE_LIMIT_RETRIES', '5')),
                'transient_retries': int(os.environ.get('RRS_LLM_TRANSIENT_RETRIES', '2')),
                'retry_backoff': float(os.environ.get('RRS_LLM_RETRY_BACKOFF', '2')),
                'retry_wait_budget': float(os.environ.get('RRS_LLM_RETRY_WAIT_BUDGET', '120')),
            },
        }

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == 'anthropic':
            return DEFAULT_ANTHROPIC_MODEL
        if self.provider == 'mock':
            return 'mock-model'
        if self.provider == 'disabled':
            return 'disabled'
        raise ValueError('RRS_LLM_MODEL must be set for openai-compatible providers')
