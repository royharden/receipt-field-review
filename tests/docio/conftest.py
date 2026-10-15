"""TSV controls are tiny authored implementation vectors, never an OCR-quality dataset."""

import socket

import pytest


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network disabled in docio parser controls")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
