"""Check the actual built wheel retains runtime schemas and vendored license notices."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path


def check(directory):
    wheels = list(Path(directory).glob("receipt_field_review-*.whl"))
    if len(wheels) != 1:
        raise ValueError("exactly_one_product_wheel_required")
    wheel = wheels[0]
    required = (
        ["rfr/api/schema.json"]
        + [
            f"rfr/shared/{name}/schema.json"
            for name in ("docio", "fieldextract", "rulings", "evalkit")
        ]
        + ["rfr/shared/execution/LICENSE.S3", "rfr/shared/execution/LICENSE.S6"]
    )
    with zipfile.ZipFile(wheel) as archive:
        for name in required:
            if not archive.read(name).strip():
                raise ValueError("empty_required_wheel_asset")
        for name in required[:5]:
            if not isinstance(json.loads(archive.read(name)), dict):
                raise ValueError("invalid_wheel_schema")
    return {
        "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "required_assets": required,
    }


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1])))
