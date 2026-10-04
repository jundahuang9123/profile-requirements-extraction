"""Tests must never consume a paid model API or resolve live source imports."""
import socket
import pytest

@pytest.fixture(autouse=True)
def block_network_in_tests(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError('Network calls are forbidden in the offline test suite.')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)
