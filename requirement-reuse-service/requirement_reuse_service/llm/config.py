from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_ANTHROPIC_MODEL = 'claude-opus-4-8'


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
      RRS_LLM_TIMEOUT    request timeout in seconds (default 240)
    """

    provider: str = 'disabled'
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int = 16000
    timeout: float = 240.0
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> 'LLMConfig':
        provider = os.environ.get('RRS_LLM_PROVIDER', '').strip().lower()
        if not provider:
            if os.environ.get('ANTHROPIC_API_KEY'):
                provider = 'anthropic'
            elif os.environ.get('RRS_LLM_BASE_URL'):
                provider = 'openai-compatible'
            else:
                provider = 'disabled'
        return cls(
            provider=provider,
            model=os.environ.get('RRS_LLM_MODEL') or None,
            base_url=os.environ.get('RRS_LLM_BASE_URL') or None,
            api_key=os.environ.get('RRS_LLM_API_KEY') or None,
            reasoning_effort=os.environ.get('RRS_LLM_REASONING_EFFORT') or None,
            max_tokens=int(os.environ.get('RRS_LLM_MAX_TOKENS', '16000')),
            timeout=float(os.environ.get('RRS_LLM_TIMEOUT', '240')),
        )

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
