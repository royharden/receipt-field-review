"""Stage one local image in an existing private directory; no OCR or receipt import."""

import argparse
import json
import sys
from pathlib import Path

from rfr.pipeline.files import BatchError

from .images import ImageInputError, decode_file, stage_image


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, required=True, help="Existing owner-private staging parent"
    )
    args = parser.parse_args(argv)
    try:
        decoded = decode_file(args.source)
        folder = stage_image(args.out, decoded)
    except (ImageInputError, BatchError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"error": "image_input_or_state_refused"}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"artifact_id": folder.name, "manifest": decoded.manifest.model_dump(mode="json")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
