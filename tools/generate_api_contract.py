"""Generate/check the app-local API schema without changing shared module schemas."""

import argparse
import json
from pathlib import Path

from rfr.api.models import API_MODELS
from rfr.pipeline.job_models import JobRecord, JobSpec


def contract_bytes():
    models = (*API_MODELS, JobRecord, JobSpec)
    return (
        json.dumps(
            {
                "contract_version": "receipt-api/1",
                "models": {
                    model.__name__: model.model_json_schema(by_alias=True) for model in models
                },
                "limits": {
                    "registered_items": 100,
                    "line_rows": 200,
                    "line_cells": 4,
                    "adjustments": 20,
                },
                "transport_status": "Not yet HTTP integration verified",
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "src/rfr/api/schema.json"
    expected = contract_bytes()
    if args.check:
        if not path.is_file() or path.read_bytes() != expected:
            raise SystemExit("Application API schema differs")
    else:
        path.write_bytes(expected)
    print(
        json.dumps(
            {"contract": "receipt-api/1", "model_count": len(API_MODELS) + 2, "check": args.check}
        )
    )


if __name__ == "__main__":
    main()
