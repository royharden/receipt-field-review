"""Catch a cosmetic demo, lost corrections, silent clean exports and live/native fallback."""

import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_changed_fixture_is_refused_before_any_output(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("receipt_demo_control", ROOT / "scripts/demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    changed = tmp_path / "changed-bundle.json"
    changed.write_bytes((ROOT / "examples/provisional-recognized-receipt.json").read_bytes() + b" ")
    monkeypatch.setattr(module, "FIXTURE", changed)
    output = tmp_path / "must-not-exist"
    with pytest.raises(module.BatchError, match="demo_fixture_hash_mismatch"):
        module.run(output)
    assert not output.exists()


@pytest.fixture
def command(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        """
import importlib.abc,socket,sys
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'openai','typesafe','PIL','fastapi','uvicorn'}:
   raise RuntimeError('demo SDK/native import forbidden')
sys.meta_path.insert(0,Guard())
def denied(*a,**k):raise RuntimeError('demo network forbidden')
socket.create_connection=denied;socket.socket.connect=denied;socket.socket.bind=denied
""",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(guard), str(ROOT / "src")))}

    def run(*args, expected=0):
        result = subprocess.run(
            [sys.executable, *map(str, args)],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return result

    return run


def test_actual_demo_with_network_sdk_canaries_and_durable_restart_exports(command, tmp_path):
    for body, message in [
        ("import openai", "demo SDK/native import forbidden"),
        ("import socket;socket.create_connection(('invalid',1))", "demo network forbidden"),
    ]:
        assert message in command("-c", body, expected=1).stderr
    output = tmp_path / "demo"
    detached = tmp_path / "detached-product"
    for name in ("scripts", "examples", "src"):
        shutil.copytree(
            ROOT / name, detached / name, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info")
        )
    result = command(detached / "scripts/demo.py", "--mode", "mock", "--out", output)
    assert json.loads(result.stdout)["status"] == "synthetic_recognized_bundle_demo_complete"
    report = json.loads((output / "DEMO.json").read_bytes())
    fixture = ROOT / "examples/provisional-recognized-receipt.json"
    assert b"\r" not in fixture.read_bytes(), (
        "The byte-pinned fixture must survive Git LF normalization"
    )
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == report["fixture_sha256"]
    assert report["model_calls"] == 0 and report["model_cost_status"] == "not_applicable"
    assert [x["exported_N"] for x in report["clean_refusals"]] == [0, 0]
    assert all(x["status"] == "clean_export_empty" for x in report["clean_refusals"])
    assert report["exact_retry"] == "exact_retry" and report["restart_and_rerun_preserved"]
    assert report["explicitly_waived_synthetic_issues"]
    assert report["rerun"]["execution_origin"] == "local_rules"
    assert report["rerun"]["state"] == "complete"
    for relative, digest in report["files"].items():
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest
    review = json.loads((Path(report["review_export"]) / "receipts.jsonl").read_bytes())
    clean_dir = Path(report["clean_export"])
    clean = json.loads((clean_dir / "receipts.jsonl").read_bytes())
    assert review["clean"] is False and review["unresolved_issues"]
    assert "subtotal_tax_adjustments_equal_total:arithmetic_mismatch" in review["unresolved_issues"]
    assert all(field["effective_value"] is None for field in review["fields"].values())
    assert clean["clean"] and not clean["unfinished_fields"] and not clean["unresolved_issues"]
    for field_id, field in clean["fields"].items():
        assert field["machine"] == review["fields"][field_id]["machine"]
        assert field["label"]["label_source"] == "agent_provisional"
    row = next(csv.DictReader(io.StringIO((clean_dir / "receipts.csv").read_text())))
    assert row["merchant_name"] == report["correction"]
    assert row["merchant_name_human_corrected"] == "false"
    assert list(csv.DictReader(io.StringIO((clean_dir / "line_items.csv").read_text())))
    # Another process after demo exit must replay, not recover from in-memory state.
    show = command(
        "-m",
        "rfr.cli",
        "--root",
        report["data_root"],
        "show",
        "--batch",
        report["batch_id"],
        "--item",
        "literal-doc",
    )
    assert (
        json.loads(show.stdout)["fields"]["merchant_name"]["effective_value"]
        == row["merchant_name"]
    )
    # A malformed update cannot overwrite accepted local corrections or source state.
    bad = tmp_path / "PRIVATE_BUNDLE_BODY.json"
    bad.write_bytes(b'{"document": "PRIVATE_BODY_CANARY"}')
    refused = command(
        "-m",
        "rfr.cli",
        "--root",
        report["data_root"],
        "import-bundle",
        "--batch",
        report["batch_id"],
        "--bundle",
        bad,
        expected=2,
    )
    assert json.loads(refused.stderr) == {"error": "input_or_state_refused"}
    assert "PRIVATE_" not in refused.stderr
    after = command(
        "-m",
        "rfr.cli",
        "--root",
        report["data_root"],
        "show",
        "--batch",
        report["batch_id"],
        "--item",
        "literal-doc",
    )
    assert json.loads(after.stdout) == json.loads(show.stdout)


@pytest.mark.parametrize("kind", ["directory", "file", "parent-file", "unknown-mode"])
def test_refusals_preserve_existing_output_and_never_mark_success(command, tmp_path, kind):
    output = tmp_path / "out"
    mode = "mock"
    if kind == "directory":
        output.mkdir()
        (output / "keep.txt").write_bytes(b"preserve")
    elif kind == "file":
        output.write_bytes(b"preserve")
    elif kind == "parent-file":
        output.write_bytes(b"preserve")
        output = output / "child"
    else:
        mode = "live"
    command(ROOT / "scripts/demo.py", "--mode", mode, "--out", output, expected=2)
    assert not (output / "DEMO.json").exists()
    if kind == "directory":
        assert list(output.iterdir()) == [output / "keep.txt"]
        assert (output / "keep.txt").read_bytes() == b"preserve"
    elif kind == "file":
        assert output.read_bytes() == b"preserve"
    elif kind == "parent-file":
        assert output.parent.read_bytes() == b"preserve"
    else:
        assert not output.exists()
