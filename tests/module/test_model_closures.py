"""Moved module proof and schema parity, with planted forbidden-import controls."""

import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from synthetic_wires import document_fixture, gold_wire, manifest_wire, pair_intent, scalar_intent

ROOT = Path(__file__).resolve().parents[2]
MODULES = ("docio", "fieldextract", "rulings", "evalkit")


@pytest.mark.parametrize("module", MODULES)
def test_owned_schema_exact_regeneration_and_extra_fields_closed(module):
    spec = importlib.util.spec_from_file_location("schema_tool", ROOT / "tools/generate_schemas.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    expected = helper.schema_bytes(module)
    path = ROOT / "src/rfr/shared" / module / "schema.json"
    assert path.read_bytes() == expected
    models = importlib.import_module(f"rfr.shared.{module}.models")
    for model in models.WIRE_MODELS:
        assert model.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize("module", MODULES)
def test_moved_models_ports_and_identity_do_not_require_app_ocr_provider(module, tmp_path):
    detached = tmp_path / "detached"
    detached.mkdir()
    (detached / "__init__.py").write_text("", encoding="utf-8")
    closure = ("docio", "fieldextract") if module == "fieldextract" else (module,)
    for owned in closure:
        shutil.copytree(
            ROOT / "src/rfr/shared" / owned,
            detached / owned,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    document, _, _, ref = document_fixture()
    fixtures = {
        "Document": document.model_dump(mode="json"),
        "SourceEvidence": ref.model_dump(mode="json"),
        "RulingIntent": scalar_intent(),
        "GoldRecord": gold_wire(),
        "Manifest": manifest_wire(),
        "Candidate": {
            "candidate_id": "c1",
            "field_id": "f1",
            "raw": False,
            "normalized": False,
            "sources": (),
        },
    }
    fixture_path = tmp_path / "synthetic-fixtures.json"
    fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
    checks = {
        "docio": ("Document", "SourceEvidence"),
        "fieldextract": ("Candidate",),
        "rulings": ("RulingIntent",),
        "evalkit": ("GoldRecord", "Manifest"),
    }[module]
    script = f"""
import hashlib,importlib,importlib.abc,json,socket,sys
from pathlib import Path
sys.path.insert(0,{str(tmp_path)!r})
def denied(*args,**kwargs): raise RuntimeError("network denied")
socket.create_connection=denied
socket.socket.connect=denied
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".")[0] in {{"rfr","openai","PIL","pytesseract","fastapi","receipt"}}:
            raise RuntimeError("forbidden app/provider import")
sys.meta_path.insert(0,Guard())
models=importlib.import_module("detached.{module}.models")
importlib.import_module("detached.{module}.interfaces")
if {module!r} != "fieldextract": importlib.import_module("detached.{module}.identity")
fixtures=json.loads(Path({str(fixture_path)!r}).read_text(encoding="utf-8"))
for name in {checks!r}: getattr(models,name).model_validate_json(json.dumps(fixtures[name]))
assert Path(models.__file__).is_relative_to(Path({str(tmp_path)!r}))
try: importlib.import_module("rfr.pipeline")
except RuntimeError: pass
else: raise AssertionError("planted original-app import was not detected")
assert not any(name=="rfr" or name.startswith("rfr.") for name in sys.modules)
schemas={{model.__name__:model.model_json_schema() for model in models.WIRE_MODELS}}
print(json.dumps({{"module":{module!r},"schema_sha256":hashlib.sha256(json.dumps(schemas,sort_keys=True).encode()).hexdigest(),"forbidden_import_control":"detected"}}))
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    receipt = json.loads(result.stdout)
    original = importlib.import_module(f"rfr.shared.{module}.models")
    schemas = {model.__name__: model.model_json_schema() for model in original.WIRE_MODELS}
    assert (
        receipt["schema_sha256"]
        == hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest()
    )
    assert receipt["forbidden_import_control"] == "detected"


def test_pair_identity_module_moved_preserves_exact_intent():
    # Concrete pair wire tests, moved generic module above stays independent of S4 app/reducer.
    from rfr.shared.rulings.models import RulingIntent

    assert RulingIntent.model_validate(pair_intent()).subject.kind == "pair"
