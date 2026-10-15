"""Run every supplied public offline control against one actually moved canonical closure."""

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_published_execution_controls_without_owner_apps_or_network(tmp_path, record_property):
    source = ROOT / "src/rfr/shared/execution"
    target = tmp_path / "portable_execution"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    notice = json.loads((ROOT / "docs/vendor/execution/SOURCE.json").read_text())
    adaptations = []
    tests = []
    for entry in notice["files"]:
        path = entry["target"]
        original = (ROOT / path).read_bytes()
        assert hashlib.sha256(original).hexdigest() == entry["sha256"]
        if not path.startswith("tests/consumers/"):
            continue
        relative = path.split("/assets/", 1)[1]
        if relative.endswith(".py.txt"):
            relative = relative[:-4]
            text = original.decode("utf-8")
            adapted = text.replace("llm_router_eval.shared", "portable_execution")
            adapted = adapted.replace("issue_triage.shared", "portable_execution")
            adapted = adapted.replace("src/issue_triage/shared", "portable_execution")
            adapted = adapted.replace(
                "contracts/consumers/s3/owner/tests/providers/conftest.py",
                "providers/conftest.py",
            )
            adapted = adapted.replace(
                'helper.replace("from issue_triage.", "from detached.")',
                'helper.replace("from portable_execution.", "from detached.shared.")',
            )
            if relative == "tests/prices/test_pricing.py":
                adapted = adapted.replace(
                    '"PYTHONPATH": str(tmp_path),',
                    '"PYTHONPATH": os.pathsep.join((str(tmp_path), str(repo))),',
                )
            content = adapted.encode("utf-8")
            adaptations.append(
                {
                    "path": relative,
                    "original_sha256": entry["sha256"],
                    "adapted_sha256": hashlib.sha256(content).hexdigest(),
                    "diff": "".join(
                        difflib.unified_diff(
                            text.splitlines(keepends=True),
                            adapted.splitlines(keepends=True),
                            fromfile="original/" + relative,
                            tofile="moved/" + relative,
                        )
                    ),
                }
            )
            if Path(relative).name.startswith("test_"):
                tests.append(relative)
        else:
            content = original
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    assert len(tests) == 21  # All original S3 controls, purpose-fix additions and S6 controls.
    (tmp_path / "adaptations.json").write_text(json.dumps(adaptations, indent=2))
    # Also guard ordinary child processes used by crash/schema/price-copy controls.
    guard = """
import importlib.abc,socket,sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {'rfr','llm_router_eval','issue_triage',
                                  'openai','typesafe','PIL','fastapi'}:
            raise RuntimeError('original app or SDK import forbidden')
sys.meta_path.insert(0,Guard())
def denied(*a,**k):raise RuntimeError('execution controls network forbidden')
socket.create_connection=denied
socket.socket.connect=denied
"""
    (tmp_path / "sitecustomize.py").write_text(guard)
    script = f"""
import json,pathlib,sys
sys.path.insert(0,{str(tmp_path)!r})
exec({guard!r})
for name in ['rfr','llm_router_eval','issue_triage','openai','typesafe']:
    try: __import__(name)
    except RuntimeError: pass
    else: raise AssertionError('import canary failed')
import socket
try: socket.create_connection(('example.invalid',443))
except RuntimeError: pass
else: raise AssertionError('network canary failed')
from portable_execution.providers import controller,models
from portable_execution.screen import s3_adapter
assert s3_adapter.Provider is controller.Provider
assert s3_adapter.TypedJudgmentRequest is models.TypedJudgmentRequest
import pytest
result=pytest.main(['tests','-q','--tb=short','--junitxml=moved.xml'])
for name,module in tuple(sys.modules.items()):
    if name=='portable_execution' or name.startswith('portable_execution.'):
        pathlib.Path(module.__file__).resolve().relative_to(pathlib.Path({str(target)!r}))
assert not any(n.split('.')[0] in {{'rfr','llm_router_eval','issue_triage','openai','typesafe'}}
               for n in sys.modules)
print(json.dumps({{'pytest_exit':result,'class_identity':'same','canaries':'detected'}}))
raise SystemExit(result)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["OPENAI_API_KEY"] = env["TYPESAFE_API_KEY"] = ""
    run = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    (tmp_path / "moved.stdout.txt").write_text(run.stdout)
    (tmp_path / "moved.stderr.txt").write_text(run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    proof = json.loads(run.stdout.strip().splitlines()[-1])
    assert proof["pytest_exit"] == 0 and proof["class_identity"] == "same"
    suites = list(ET.parse(tmp_path / "moved.xml").getroot().iter("testsuite"))
    actual = sum(int(s.attrib["tests"]) for s in suites)
    record_property("actual_moved_controls", actual)
    record_property("moved_junit_path", str(tmp_path / "moved.xml"))
    record_property("adaptations_path", str(tmp_path / "adaptations.json"))
    assert actual == 325
    assert all(
        int(s.attrib.get(k, 0)) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
