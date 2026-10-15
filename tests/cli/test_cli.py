"""Exercise real subprocess entrypoints with provider imports/network denied, no fake human Gold."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "own_pipeline_bundle", ROOT / "tests/pipeline/conftest.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
bundle_factory = helpers.bundle_factory


@pytest.fixture
def command(tmp_path):
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text("""
import importlib.abc,socket,sys
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'openai','typesafe','PIL','fastapi','uvicorn'}:
   raise RuntimeError('CLI provider/native import forbidden')
sys.meta_path.insert(0,Guard())
def denied(*a,**k):raise RuntimeError('CLI network forbidden')
socket.create_connection=denied;socket.socket.connect=denied
""")
    data = tmp_path / "private-batches"
    data.mkdir()
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(guard), str(ROOT / "src")))}

    def run(*arguments, expected=0):
        result = subprocess.run(
            [sys.executable, "-m", "rfr.cli", "--root", str(data), *arguments],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return json.loads(result.stdout if result.stdout else result.stderr)

    return run, data, env


def test_actual_cli_import_draft_apply_restart_exactretry_rerun_and_exports(
    command, bundle_factory, tmp_path
):
    run, data, env = command
    control = subprocess.run(
        [sys.executable, "-c", "import socket;socket.create_connection(('invalid',1))"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert control.returncode != 0 and "CLI network forbidden" in control.stderr
    provider_control = subprocess.run(
        [sys.executable, "-c", "import openai"],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert provider_control.returncode != 0
    assert "CLI provider/native import forbidden" in provider_control.stderr
    bundle = bundle_factory()
    supplied = tmp_path / "provided-bundle.json"
    supplied.write_text(bundle.model_dump_json())
    batch = run("new")["batch_id"]
    common = ["--batch", batch]
    imported = run("import-bundle", *common, "--bundle", str(supplied))
    item, revision = imported["item_id"], imported["revision"]
    assert run("list", *common)[0]["clean"] is False
    draft = run(
        "draft",
        *common,
        "--item",
        item,
        "--field",
        "merchant_name",
        "--action",
        "correct",
        "--value",
        "CLI Shop",
        "--actor",
        "synthetic-controller",
        "--reason",
        "Literal CLI control",
    )
    assert draft["expected_item_revision"] == revision
    assert draft["intent"]["actor_provenance"] == "agent_provisional"
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(draft))
    first = run("apply", *common, "--draft", str(path))
    retry = run("apply", *common, "--draft", str(path))
    assert (
        first["outcome"] == "appended" and retry["outcome"] == "exact_retry" and retry["historical"]
    )
    run("import-bundle", *common, "--bundle", str(supplied), "--expected-revision", revision)
    shown = run("show", *common, "--item", item)
    assert shown["fields"]["merchant_name"]["effective_value"] == "CLI Shop"
    refused = run("export", *common, "--mode", "clean", "--out", str(tmp_path), expected=3)
    assert refused["status"] == "clean_export_empty" and refused["exported_N"] == 0
    exported = run("export", *common, "--out", str(tmp_path))
    assert exported["exported_N"] == exported["requested_N"] == 1
    assert json.loads((Path(exported["output"]) / "receipts.jsonl").read_bytes())["item_id"] == item
    assert (data / batch / "rulings.jsonl").is_file()


@pytest.mark.parametrize(
    "payload",
    [
        b"{bad",
        b'{"expected_item_revision":"x","intent":{},"intent":{}}',
        b'{"expected_item_revision":NaN,"intent":{}}',
        b"[]",
    ],
)
def test_private_malformed_duplicate_nonfinite_or_open_draft_has_closed_error(
    command, tmp_path, payload
):
    run, _, _ = command
    batch = run("new")["batch_id"]
    path = tmp_path / "PRIVATE_PATH_CANARY.json"
    path.write_bytes(payload)
    error = run("apply", "--batch", batch, "--draft", str(path), expected=2)
    assert "PRIVATE_PATH_CANARY" not in json.dumps(error) and len(error) == 1


def test_stale_and_missing_input_and_unverified_human_requirements(
    command, bundle_factory, tmp_path
):
    run, _, _ = command
    batch = run("new")["batch_id"]
    common = ["--batch", batch]
    missing = run(
        "import-bundle", *common, "--bundle", str(tmp_path / "private-missing.json"), expected=2
    )
    assert missing == {"error": "input_or_state_refused"}
    bundle = bundle_factory()
    path = tmp_path / "provided.json"
    path.write_text(bundle.model_dump_json())
    imported = run("import-bundle", *common, "--bundle", str(path))
    refused = run("import-bundle", *common, "--bundle", str(path), expected=2)
    assert refused == {"error": "item_revision_conflict"}
    refused = run(
        "draft",
        *common,
        "--item",
        imported["item_id"],
        "--field",
        "unknown",
        "--action",
        "confirm",
        "--actor",
        "control",
        "--reason",
        "control",
        expected=2,
    )
    assert refused == {"error": "unknown_receipt_field"}
    refused = run(
        "draft",
        *common,
        "--item",
        imported["item_id"],
        "--field",
        "merchant_name",
        "--action",
        "confirm",
        "--actor",
        "control",
        "--actor-kind",
        "human_claimed",
        "--reason",
        "control",
        expected=2,
    )
    assert refused == {"error": "claimed_human_provenance_reference_required"}
