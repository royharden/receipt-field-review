"""Actual copied parser/model closure with all literal controls and original imports disabled."""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_complete_tsv_control_suite_after_actual_namespace_move(tmp_path):
    shutil.copytree(
        ROOT / "src/rfr/shared/docio",
        tmp_path / "portable_docio",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    content = (ROOT / "tests/docio/test_tsv_parser.py").read_text(encoding="utf-8")
    (tmp_path / "test_tsv_parser.py").write_text(
        content.replace("rfr.shared.docio", "portable_docio"), encoding="utf-8"
    )
    script = f"""
import importlib,importlib.abc,socket,sys
from pathlib import Path
sys.path.insert(0,{str(tmp_path)!r})
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {{'rfr','PIL','pytesseract','openai','typesafe','fastapi'}}:
            raise RuntimeError('original app/native/provider import forbidden')
sys.meta_path.insert(0,Guard())
def denied(*args,**kwargs):raise RuntimeError('network disabled')
socket.create_connection=denied;socket.socket.connect=denied
try:importlib.import_module('rfr.pipeline')
except RuntimeError:pass
else:raise AssertionError('forbidden import control failed')
import pytest
code=pytest.main([{str(tmp_path / "test_tsv_parser.py")!r},'-q','--tb=short',
    '--junitxml='+{str(tmp_path / "moved.xml")!r}])
for name,module in tuple(sys.modules.items()):
    if name=='portable_docio' or name.startswith('portable_docio.'):
        Path(module.__file__).resolve().relative_to(Path({str(tmp_path / "portable_docio")!r}))
assert not any(n=='rfr' or n.startswith('rfr.') for n in sys.modules)
raise SystemExit(code)
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    run = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    suites = list(ET.parse(tmp_path / "moved.xml").getroot().iter("testsuite"))
    assert sum(int(s.attrib["tests"]) for s in suites) == 22
    assert all(
        int(s.attrib.get(key, 0)) == 0 for s in suites for key in ["failures", "errors", "skipped"]
    )
