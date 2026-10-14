"""Architecture gates with failure controls; no application schema is implemented."""

import ast
import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

from scaffold_checks import forbidden_shared_imports, publication_violations

ROOT = Path(__file__).resolve().parents[2]


class SharedModuleBoundaries(unittest.TestCase):
    def test_declared_dependency_and_injected_protocol_are_allowed(self):
        source = "from rfr.shared.docio.models import Page\nfrom typing import Protocol\n"
        self.assertEqual(forbidden_shared_imports("rfr.shared.fieldextract.selector", source), [])

    def test_module_local_relative_import_is_allowed(self):
        self.assertEqual(forbidden_shared_imports("rfr.shared.docio.ocr", "from .models import Page"), [])

    def test_app_import_control_is_detected(self):
        for statement in ("import rfr.pipeline", "from rfr import receipt", "from ... import api"):
            with self.subTest(statement=statement):
                self.assertTrue(forbidden_shared_imports("rfr.shared.docio.ocr", statement))

    def test_unapproved_shared_edge_control_is_detected(self):
        self.assertTrue(forbidden_shared_imports(
            "rfr.shared.rulings.store", "from rfr.shared.docio.models import Page"))

    def test_actual_python_sources_obey_boundaries_and_parse(self):
        sources = list((ROOT / "src").rglob("*.py"))
        self.assertTrue(sources, "A zero-source check cannot establish the scaffold exists")
        for path in sources:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            module = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
            self.assertEqual(forbidden_shared_imports(module, source), [], str(path))


class PublicationBoundaries(unittest.TestCase):
    def test_nonsecret_example_is_allowed(self):
        self.assertEqual(publication_violations(".env.example", "RFR_MODE=mock\n"), [])

    def test_private_paths_and_actual_env_controls_are_detected(self):
        for path in ("data/receipts.png", ".creds/key.txt", ".chatexports/chat.html",
                     ".thinking/lane/plan.md", ".agent-registry/ids/0001.json", ".env.local"):
            with self.subTest(path=path):
                self.assertTrue(publication_violations(path))

    def test_fake_credential_and_private_key_controls_are_detected(self):
        for sample in ("sk-" + "x" * 40, "ghp_" + "x" * 30,
                       "-----BEGIN " + "PRIVATE KEY-----"):
            with self.subTest(sample_kind=sample.split("-")[0]):
                self.assertIn("credential_pattern", publication_violations("src/example.py", sample))

    def test_path_escape_control_is_detected(self):
        for path in ("../outside.txt", "C:/outside.txt", "/outside.txt"):
            with self.subTest(path=path):
                self.assertIn("nonportable_path", publication_violations(path))

    def test_current_public_candidate_has_no_private_material(self):
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, check=True, capture_output=True,
        )
        names = sorted({name for name in result.stdout.decode("utf-8").split("\0") if name})
        self.assertTrue(names, "Zero candidate files is not a publication check")
        for name in names:
            path = ROOT / name
            self.assertFalse(path.is_symlink(), name)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(publication_violations(name, text), [], name)


class BootstrapScope(unittest.TestCase):
    def test_declared_runtime_matches_test_interpreter(self):
        self.assertEqual(sys.version_info[:2], (3, 12), "Run with the declared Python 3.12 interpreter")
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["requires-python"], ">=3.12,<3.13")

    def test_scaffold_does_not_claim_installed_product_dependencies(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(project["dependencies"], [])
        self.assertFalse(package.get("dependencies"))
        self.assertNotIn("build", package["scripts"])


if __name__ == "__main__":
    unittest.main()
