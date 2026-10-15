"""Synthetic judgment ports only; no providers or source acquisition."""

import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network disabled in fieldextract controls")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
