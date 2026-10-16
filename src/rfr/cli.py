"""Private review CLI; explicit local image import, no provider, listener or live fallback."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .export.receipt import export_receipts, write_export
from .pipeline.commands import draft_decision
from .pipeline.files import BatchError, read
from .pipeline.models import ReceiptBundle
from .pipeline.store import BatchStore
from .receipt.models import MINOR_UNITS, CurrencyPolicy
from .shared.execution.callledger.models import decode_wire_json
from .shared.rulings.models import RulingIntent
from .shared.rulings.store import JournalError


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument(
        "--root", type=Path, required=True, help="Existing owner-private batch directory"
    )
    commands = root.add_subparsers(dest="command", required=True)
    create = commands.add_parser("new", help="Create a generated single-currency batch")
    create.add_argument("--currency", choices=tuple(MINOR_UNITS), default="USD")
    native = commands.add_parser("import-image", help="Stage and recognize one local receipt image")
    native.add_argument("--batch", required=True)
    native.add_argument("--source", type=Path, required=True)
    native.add_argument(
        "--tesseract", type=Path, required=True, help="Trusted installed executable"
    )
    native.add_argument(
        "--tessdata", type=Path, required=True, help="Installed English model directory"
    )
    native.add_argument("--reference-date", type=date.fromisoformat, required=True)
    native.add_argument("--expected-revision")
    for name in ("import-bundle", "list", "show", "draft", "apply", "export"):
        command = commands.add_parser(name)
        command.add_argument("--batch", required=True)
        if name == "import-bundle":
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument("--expected-revision")
        elif name in {"show", "draft"}:
            command.add_argument("--item", required=True)
        elif name == "apply":
            command.add_argument("--draft", type=Path, required=True)
        elif name == "export":
            command.add_argument("--mode", choices=("review", "clean"), default="review")
            command.add_argument("--out", type=Path, required=True, help="Existing private parent")
        if name == "draft":
            command.add_argument("--field", required=True)
            command.add_argument(
                "--action", choices=("correct", "confirm", "waive_absent", "reopen"), required=True
            )
            command.add_argument("--value")
            command.add_argument("--reason", required=True)
            command.add_argument("--actor", required=True)
            command.add_argument(
                "--actor-kind",
                choices=("agent_provisional", "human_claimed"),
                default="agent_provisional",
            )
            command.add_argument("--actor-ref")
            command.add_argument("--event-id")
            command.add_argument("--waive-issue", action="append", default=[])
            command.add_argument("--issue-reason")
    return root


def make_draft(store, args):
    return draft_decision(
        store,
        item=args.item,
        field=args.field,
        action=args.action,
        value=args.value,
        reason=args.reason,
        actor=args.actor,
        actor_kind=args.actor_kind,
        actor_ref=args.actor_ref,
        event_id=args.event_id,
        waive_issues=args.waive_issue,
        issue_reason=args.issue_reason,
    )


def execute(args):
    if args.command == "new":
        store = BatchStore.create(args.root, CurrencyPolicy(code=args.currency))
        return {"batch_id": store.batch_id, "currency": args.currency}, 0
    store = BatchStore(args.root, args.batch)
    if args.command == "import-image":
        # Ordinary provided-bundle/demo commands keep working without optional native codecs.
        from .ingest.images import ImageInputError
        from .ingest.native import import_image
        from .ports.tesseract import NativeOcrError

        try:
            result = import_image(
                store,
                args.source,
                args.tesseract,
                args.tessdata,
                args.reference_date,
                expected_revision=args.expected_revision,
            )
        except ImageInputError as error:
            raise NativeOcrError(str(error)) from None
        return result, 0
    if args.command == "import-bundle":
        supplied = decode_wire_json(
            read(args.bundle, 8 * 1024 * 1024).decode("utf-8"), max_bytes=8 * 1024 * 1024
        )
        bundle = ReceiptBundle.model_validate_json(json.dumps(supplied))
        revision = store.register(bundle, expected_revision=args.expected_revision)
        return {"item_id": bundle.document.document_id, "revision": revision}, 0
    if args.command == "list":
        return [
            {"item_id": item["item_id"], "deleted": True}
            if item.get("deleted")
            else {
                key: item[key]
                for key in (
                    "item_id",
                    "revision",
                    "clean",
                    "unfinished_fields",
                    "unresolved_issues",
                )
            }
            for item in store.list_items()
        ], 0
    if args.command == "show":
        return store.detail(args.item), 0
    if args.command == "draft":
        return make_draft(store, args), 0
    if args.command == "apply":
        draft = decode_wire_json(read(args.draft, 128 * 1024).decode("utf-8"), max_bytes=128 * 1024)
        if type(draft) is not dict or set(draft) != {"expected_item_revision", "intent"}:
            raise BatchError("closed_decision_draft_required")
        if type(draft["expected_item_revision"]) is not str:
            raise BatchError("explicit_expected_item_revision_required")
        intent = RulingIntent.model_validate_json(json.dumps(draft["intent"]))
        receipt = store.decide(intent, expected_item_revision=draft["expected_item_revision"])
        return receipt.model_dump(mode="json"), 0
    files = export_receipts(store, mode=args.mode)
    target = write_export(args.out, files)
    summary = json.loads(files["omitted.json"])
    summary["output"] = str(target)
    summary["status"] = (
        "clean_export_empty" if args.mode == "clean" and not summary["exported_N"] else "exported"
    )
    return summary, 3 if summary["status"] == "clean_export_empty" else 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result, status = execute(args)
    except (BatchError, JournalError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Never echo supplied bodies, paths or Pydantic's private-input diagnostics.
        print(json.dumps({"error": "input_or_state_refused"}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
