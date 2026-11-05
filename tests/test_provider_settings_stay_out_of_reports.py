"""The provider key never reaches a repr, a traceback or a test's environment."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.llm.config import LLMConfig  # noqa: E402


def test_the_config_repr_has_no_credentials():
    config = LLMConfig(provider='openai-compatible', base_url='https://gateway.invalid/v1', api_key='sk-synthetic-secret',
                       extra_headers={'X-Api-Key': 'synthetic-header-secret'})
    text = repr(config)
    assert 'sk-synthetic-secret' not in text and 'synthetic-header-secret' not in text
    assert "provider='openai-compatible'" in text
    assert config.api_key == 'sk-synthetic-secret' and config.extra_headers == {'X-Api-Key': 'synthetic-header-secret'}


def test_no_test_sees_the_shells_provider_settings():
    assert not any(name.startswith('RRS_LLM_') for name in os.environ)
    assert 'ANTHROPIC_API_KEY' not in os.environ and 'OPENAI_API_KEY' not in os.environ
