"""Test-only stdio bridge to real local services, not an HTTP/native-browser substitute."""

import hashlib
import json
import sys
from pathlib import Path

from rfr.api.models import CreateBatch, DecisionDraft, DraftRequest, RecognizedImport
from rfr.api.operations import ReviewOperations
from rfr.pipeline.models import ReceiptBundle
from rfr.receipt.models import CurrencyPolicy
from rfr.shared.rulings.store import GenerationConflict, PriorConflict


def main():
    root = Path(sys.argv[1])
    operations = ReviewOperations(root)
    batch = operations.create(CreateBatch(currency=CurrencyPolicy())).batch_id
    bundle = ReceiptBundle.model_validate_json(
        (
            Path(__file__).resolve().parents[2] / "examples/provisional-recognized-receipt.json"
        ).read_bytes()
    )
    operations.import_recognized(batch, RecognizedImport(bundle=bundle))
    item = bundle.document.document_id
    for line in sys.stdin:
        request = json.loads(line)
        try:
            command = request["operation"]
            if command == "init":
                value = {"batch": batch, "item": item, "detail": operations.detail(batch, item)}
            elif command == "item":
                value = operations.detail(batch, item)
            elif command == "draft":
                value = operations.draft(
                    batch, item, DraftRequest.model_validate_json(json.dumps(request["input"]))
                )
            elif command == "apply":
                value = operations.apply(
                    batch, item, DecisionDraft.model_validate_json(json.dumps(request["input"]))
                )
            elif command == "audit":
                path = root / batch / "rulings.jsonl"
                raw = path.read_bytes() if path.exists() else b""
                value = {"sha256": hashlib.sha256(raw).hexdigest(), "events": len(raw.splitlines())}
            else:
                raise ValueError("unknown_test_operation")
            # Models cross the same closed JSON wires used by the product facade.
            encoded = json.dumps(
                {"id": request["id"], "ok": True, "value": value},
                default=lambda model: model.model_dump(mode="json"),
            )
        except (GenerationConflict, PriorConflict):
            # Explicit test-port mapping matches the public code, not internal exception text.
            encoded = json.dumps(
                {"id": request["id"], "ok": False, "status": 409, "error": "revision_conflict"}
            )
        print(encoded, flush=True)


if __name__ == "__main__":
    main()
