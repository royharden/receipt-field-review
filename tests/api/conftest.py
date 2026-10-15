"""Reuse only own public literal receipt controls, with no HTTP/provider/native runtime."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "own_api_pipeline_controls", ROOT / "tests/pipeline/conftest.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
batch = helpers.batch
bundle_factory = helpers.bundle_factory
no_network = helpers.no_network
