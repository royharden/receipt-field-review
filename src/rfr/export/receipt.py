"""Export every review item, or list every item omitted from the resolved-only export."""

import csv
import hashlib
import io
import json
import uuid
from pathlib import Path

from ..pipeline.files import immutable
from ..receipt.models import LINE_CELLS, SCALARS
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.store import JournalStore


def csv_text(value):
    if value is None:
        return ""
    text = value if type(value) is str else json.dumps(value, ensure_ascii=False)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + text
    return text


def _csv(headers, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: csv_text(value) for key, value in row.items()} for row in rows)
    return output.getvalue().encode("utf-8")


def _field(prefix, field):
    machine = field["machine"]
    return {
        prefix: field["effective_value"],
        prefix + "_confidence": machine["confidence"],
        prefix + "_method": machine["method"],
        prefix + "_status": machine["status"],
        prefix + "_review_state": field["review_state"],
        prefix + "_human_corrected": (
            field["corrected"]
            and field["label"] is not None
            and field["label"]["label_source"] == "unverified_human"
        ),
        prefix + "_audit_json": json.dumps(field, ensure_ascii=False, sort_keys=True),
    }


def export_receipts(store, *, mode="review"):
    if mode not in {"review", "clean"}:
        raise ValueError("explicit_review_or_clean_export_required")
    # One source/decision snapshot is held by list_items; never separately reread bundles.
    items = store.list_items()
    selected, omitted = [], []
    for item in items:
        if mode == "clean" and (item.get("deleted") or not item["clean"]):
            omitted.append(
                {
                    "item_id": item["item_id"],
                    "reasons": ["deleted"]
                    if item.get("deleted")
                    else [*item["unfinished_fields"], *item["unresolved_issues"]],
                }
            )
        else:
            selected.append(item)
    rows, lines = [], []
    scalar_headers = ["item_id", "deleted", "clean", "line_items_json", "adjustments_json"]
    suffixes = (
        "",
        "_confidence",
        "_method",
        "_status",
        "_review_state",
        "_human_corrected",
        "_audit_json",
    )
    scalar_headers.extend(field + suffix for field in SCALARS for suffix in suffixes)
    line_headers = ["item_id", "row_key"]
    line_headers.extend(field + suffix for field in LINE_CELLS for suffix in suffixes)
    for item in selected:
        row = {"item_id": item["item_id"], "deleted": item.get("deleted", False)}
        if not item.get("deleted"):
            row["clean"] = item["clean"]
            receipt = item["receipt"]
            for field in SCALARS:
                row.update(_field(field, item["fields"][field]))
            for line in receipt["line_items"]:
                line_row = {"item_id": item["item_id"], "row_key": line["row_key"]}
                for name in LINE_CELLS:
                    fid = line["cells"][name]["field_id"]
                    line_row.update(_field(name, item["fields"][fid]))
                lines.append(line_row)
            row["line_items_json"] = json.dumps(
                [line for line in lines if line["item_id"] == item["item_id"]],
                ensure_ascii=False,
            )
            row["adjustments_json"] = json.dumps(
                [
                    item["fields"][adjustment["amount"]["field_id"]]
                    for adjustment in receipt["adjustments"]
                ],
                ensure_ascii=False,
            )
        rows.append(row)
    return {
        "receipts.csv": _csv(scalar_headers, rows),
        "line_items.csv": _csv(line_headers, lines),
        "receipts.jsonl": b"".join(canonical_bytes(item) + b"\n" for item in selected),
        "omitted.json": canonical_bytes(
            {
                "mode": mode,
                "requested_N": len(items),
                "exported_N": len(selected),
                "omitted": omitted,
            }
        ),
    }


def write_export(parent: Path, files: dict[str, bytes]):
    if set(files) != {"receipts.csv", "line_items.csv", "receipts.jsonl", "omitted.json"}:
        raise ValueError("closed_receipt_export_file_set_required")
    parent = Path(parent).absolute()
    JournalStore(parent)  # Validate the explicit trusted local destination and ancestors.
    target = parent / ("receipt-export-" + uuid.uuid4().hex)
    target.mkdir(mode=0o700)
    digests = {}
    for name, data in files.items():
        if type(data) is not bytes:
            raise ValueError("export_bytes_required")
        immutable(target / name, data)
        digests[name] = hashlib.sha256(data).hexdigest()
    # This last immutable marker identifies a complete export set; interrupted sets stay incomplete.
    immutable(
        target / "EXPORT.json",
        canonical_bytes({"schema_version": 1, "files": digests, "public_label_authority": False}),
    )
    return target
