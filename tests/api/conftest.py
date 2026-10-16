"""Own public literal receipt controls; HTTP tests keep the socket-connect denial active."""

import importlib.util
import socket
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "own_api_pipeline_controls", ROOT / "tests/pipeline/conftest.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
batch = helpers.batch
bundle_factory = helpers.bundle_factory


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Deny application connections; allow only stdlib socketpair's Windows control pipe."""
    original_pair, original_connect = socket.socketpair, socket.socket.connect
    control = threading.local()

    def pair(*args, **kwargs):
        control.inside_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            control.inside_pair = False

    def connect(sock, address):
        if getattr(control, "inside_pair", False) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        raise AssertionError("receipt HTTP controls forbid application network")

    def denied(*args, **kwargs):
        raise AssertionError("receipt HTTP controls forbid application network")

    monkeypatch.setattr(socket, "socketpair", pair)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", denied)
