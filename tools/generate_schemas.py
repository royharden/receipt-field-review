"""Generate/check module-owned models-only schemas from the installed package sources."""

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
MODULES = ("docio", "fieldextract", "rulings", "evalkit")


def schema_bytes(module: str) -> bytes:
    models = importlib.import_module(f"rfr.shared.{module}.models")
    bundle = {
        "schema_bundle_version": 1,
        "stage": "models-only",
        "module": module,
        "schemas": {model.__name__: model.model_json_schema() for model in models.WIRE_MODELS},
    }
    return (
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = []
    for module in MODULES:
        path = ROOT / "src/rfr/shared" / module / "schema.json"
        expected = schema_bytes(module)
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                failures.append(module)
        else:
            path.write_bytes(expected)
    print(json.dumps({"stage": "models-only", "module_count": 4, "mismatches": failures}))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
