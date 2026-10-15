"""Own literal receipt controls, no images, independent Gold, models or network."""

import base64
import importlib.util
import socket
from pathlib import Path

import pytest

from rfr.pipeline.models import ReceiptBundle
from rfr.pipeline.store import BatchStore
from rfr.receipt.b0 import extract_b0
from rfr.receipt.models import CurrencyPolicy

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "own_literal_receipt_controls", ROOT / "tests/receipt/test_b0_candidate_plugin.py"
)
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("receipt workflow controls forbid network")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def bundle_factory():
    def make(lines=None):
        doc, _, raw, digest = controls.literal_receipt(lines)
        receipt = extract_b0(doc, raw, digest, controls.context())
        return ReceiptBundle(
            document=doc,
            receipt=receipt,
            artifact_base64=base64.b64encode(raw).decode("ascii"),
        )

    return make


@pytest.fixture
def batch(tmp_path):
    return BatchStore.create(tmp_path, CurrencyPolicy())
