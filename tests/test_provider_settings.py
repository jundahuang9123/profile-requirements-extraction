from fastapi.testclient import TestClient

from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.main import app


def test_ui_provider_settings_are_runtime_only_and_never_return_key(monkeypatch):
    import requirement_reuse_service.llm.config as config_module

    monkeypatch.setattr(config_module, '_runtime_config', None)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    monkeypatch.delenv('RRS_LLM_API_KEY', raising=False)
    client = TestClient(app)
    response = client.post('/api/rq1/v2/provider-settings', json={
        'provider': 'kiconnect', 'model': 'inferenz-gpt-oss-120b',
        'api_key': 'test-secret-key',
    })
    assert response.status_code == 200
    body = response.json()
    assert body['preset'] == 'kiconnect'
    assert body['credential_configured'] is True
    assert 'test-secret-key' not in response.text
    config = LLMConfig.from_env()
    assert config.provider == 'openai-compatible'
    assert config.base_url == 'https://chat.kiconnect.nrw/api/v1'
    assert config.model == 'inferenz-gpt-oss-120b'
    assert config.api_key == 'test-secret-key'


def test_local_ollama_provider_needs_no_api_key(monkeypatch):
    import requirement_reuse_service.llm.config as config_module
    from requirement_reuse_service.workflow.api import ollama_default_url

    monkeypatch.setattr(config_module, '_runtime_config', None)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    monkeypatch.delenv('RRS_LLM_API_KEY', raising=False)
    response = TestClient(app).post('/api/rq1/v2/provider-settings', json={
        'provider': 'ollama', 'model': 'qwen-local:latest',
    })
    assert response.status_code == 200
    config = LLMConfig.from_env()
    assert config.base_url == ollama_default_url()
    assert config.api_key is None


def test_switching_endpoints_never_reuses_another_providers_key(monkeypatch):
    import requirement_reuse_service.llm.config as config_module
    monkeypatch.setattr(config_module, '_runtime_config', None)
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    client = TestClient(app)
    assert client.post('/api/rq1/v2/provider-settings', json={
        'provider': 'kiconnect', 'model': 'first', 'api_key': 'first-provider-secret'}).status_code == 200
    assert client.post('/api/rq1/v2/provider-settings', json={
        'provider': 'kiconnect', 'model': 'second'}).json()['credential_configured'] is True
    switched = client.post('/api/rq1/v2/provider-settings', json={
        'provider': 'openai', 'model': 'another-model'})
    assert switched.json()['credential_configured'] is False
    assert LLMConfig.from_env().api_key is None
