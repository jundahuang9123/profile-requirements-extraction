"""Tests must never consume a paid model API or resolve live source imports."""
import os
import socket
import pytest

# Provider settings a developer shell may export. Tests set what they need themselves.
PROVIDER_VARIABLES = ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY')


@pytest.fixture(autouse=True)
def no_provider_settings_from_the_shell(monkeypatch):
    """A test never sees the shell's provider key or endpoint, so no report can print them."""
    for name in list(os.environ):
        if name.startswith('RRS_LLM_') or name in PROVIDER_VARIABLES:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def block_network_in_tests(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError('Network calls are forbidden in the offline test suite.')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
