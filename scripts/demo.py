"""Run the synthetic recognized-bundle workflow locally; no image or model inference."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfr.pipeline.commands import draft_decision  # noqa: E402
from rfr.pipeline.files import BatchError, immutable, read  # noqa: E402
from rfr.pipeline.job_models import JobSpec  # noqa: E402
from rfr.pipeline.jobs import JobStore  # noqa: E402
from rfr.pipeline.models import ReceiptBundle  # noqa: E402
from rfr.pipeline.store import BatchStore  # noqa: E402
from rfr.shared.rulings.models import RulingIntent  # noqa: E402
from rfr.shared.rulings.store import JournalStore  # noqa: E402

FIXTURE = ROOT / "examples/provisional-recognized-receipt.json"
FIXTURE_SHA256 = "26212b137084dd27af57527b798c38ba9a6027ff7ced2e7af1bc855a149006fa"
CORRECTION = "SYNTHETIC REVIEWED SHOP"


def require(condition, code):
    if not condition:
        raise BatchError(code)


def cli(data, *arguments, expected=0):
    # A new process reads the durable files on every CLI call, including restart checks.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH"))))
    result = subprocess.run(
        [sys.executable, "-m", "rfr.cli", "--root", str(data), *arguments],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    require(result.returncode == expected, "demo_cli_unexpected_exit")
    return json.loads(result.stdout if result.stdout else result.stderr)


def apply(store, field, action, *, value=None, issues=()):
    draft = draft_decision(
        store,
        item="literal-doc",
        field=field,
        action=action,
        value=value,
        actor="synthetic demo controller",
        reason="Authored demonstration only; no human label or receipt accuracy claim",
        waive_issues=issues,
        issue_reason="Explicit synthetic conflict demonstration; not a verified receipt"
        if issues
        else None,
    )
    return store.decide(
        RulingIntent.model_validate_json(json.dumps(draft["intent"])),
        expected_item_revision=draft["expected_item_revision"],
    )


def run(output):
    fixture = read(FIXTURE, 1024 * 1024)
    require(hashlib.sha256(fixture).hexdigest() == FIXTURE_SHA256, "demo_fixture_hash_mismatch")
    bundle = ReceiptBundle.model_validate_json(fixture)
    # Validate existing ancestors before exclusive creation. Never reuse/clear any output.
    output = output.absolute()
    JournalStore(output.parent)
    require(not os.path.lexists(output), "demo_output_already_exists")
    output.mkdir(mode=0o700)
    data, exports = output / "batches", output / "exports"
    data.mkdir(mode=0o700)
    exports.mkdir(mode=0o700)
    batch_id = cli(data, "new", "--currency", "USD")["batch_id"]
    args = ["--batch", batch_id]
    imported = cli(data, "import-bundle", *args, "--bundle", str(FIXTURE))
    store = BatchStore(data, batch_id)
    initial = cli(data, "show", *args, "--item", "literal-doc")
    require(not initial["clean"] and initial["unresolved_issues"], "demo_must_begin_in_review")
    require(
        "subtotal_tax_adjustments_equal_total:arithmetic_mismatch" in initial["unresolved_issues"],
        "demo_must_exercise_arithmetic_conflict",
    )
    review = cli(data, "export", *args, "--out", str(exports))
    first = cli(data, "export", *args, "--mode", "clean", "--out", str(exports), expected=3)
    require(first["exported_N"] == 0, "demo_initial_clean_must_refuse")

    # Save the exact public CLI draft for durable retry, rather than regenerating its identity.
    draft = cli(
        data,
        "draft",
        *args,
        "--item",
        "literal-doc",
        "--field",
        "merchant_name",
        "--action",
        "correct",
        "--value",
        CORRECTION,
        "--actor",
        "synthetic demo controller",
        "--reason",
        "Authored correction; no human Gold claim",
    )
    draft_path = output / "merchant-decision.json"
    immutable(draft_path, json.dumps(draft, ensure_ascii=False).encode("utf-8"))
    cli(data, "apply", *args, "--draft", str(draft_path))
    retry = cli(data, "apply", *args, "--draft", str(draft_path))
    require(retry["outcome"] == "exact_retry", "demo_exact_retry_failed")
    corrected = cli(data, "show", *args, "--item", "literal-doc")
    require(
        corrected["fields"]["merchant_name"]["effective_value"] == CORRECTION,
        "demo_restart_lost_correction",
    )
    second = cli(data, "export", *args, "--mode", "clean", "--out", str(exports), expected=3)
    require(second["exported_N"] == 0, "demo_correction_cannot_silently_clean")

    for field in bundle.receipt.all_fields():
        current = store.detail("literal-doc")["fields"][field.field_id]
        if current["review_state"] == "needs_review":
            action = "waive_absent" if field.proposal is None else "confirm"
            apply(store, field.field_id, action)
    before_waivers = store.detail("literal-doc")
    require(
        not before_waivers["unfinished_fields"] and before_waivers["unresolved_issues"],
        "demo_confirmations_cannot_clear_conflicts",
    )
    waived = before_waivers["unresolved_issues"]
    apply(store, "merchant_name", "confirm", issues=waived)
    jobs = JobStore(store)
    pending = jobs.start(
        "synthetic-demo-rerun",
        JobSpec(method="B0", source_revisions={"literal-doc": imported["revision"]}),
    )
    rerun = jobs.run(pending.job_id)
    require(rerun.state == "complete", "demo_actual_local_rerun_failed")
    final = cli(data, "show", *args, "--item", "literal-doc")
    require(final["clean"], "demo_final_review_unresolved")
    require(
        final["fields"]["merchant_name"]["effective_value"] == CORRECTION,
        "demo_rerun_lost_correction",
    )
    for field in bundle.receipt.all_fields():
        actual = final["fields"][field.field_id]
        require(actual["machine"] == field.model_dump(mode="json"), "demo_machine_changed")
        require(actual["label"]["label_source"] == "agent_provisional", "demo_label_upgraded")
    clean = cli(data, "export", *args, "--mode", "clean", "--out", str(exports))
    require(clean["exported_N"] == 1, "demo_final_export_missing")
    summary = {
        "status": "synthetic_recognized_bundle_demo_complete",
        "fixture_sha256": FIXTURE_SHA256,
        "scope": "Authored recognized text/geometry/confidence; no source image or measured OCR",
        "batch_id": batch_id,
        "item_id": "literal-doc",
        "data_root": str(data),
        "review_export": review["output"],
        "clean_refusals": [first, second],
        "explicitly_waived_synthetic_issues": waived,
        "correction": CORRECTION,
        "exact_retry": retry["outcome"],
        "restart_and_rerun_preserved": True,
        "rerun": rerun.model_dump(mode="json"),
        "clean_export": clean["output"],
        "label_authority": "agent_provisional; not human Gold",
        "model_calls": 0,
        "model_cost_status": "not_applicable",
        "files": {},
    }
    for path in sorted(output.rglob("*")):
        if path.is_file():
            summary["files"][path.relative_to(output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    immutable(output / "DEMO.json", json.dumps(summary, indent=2).encode("utf-8") + b"\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock",), required=True)
    parser.add_argument("--out", type=Path, required=True, help="New private output directory")
    args = parser.parse_args(argv)
    try:
        summary = run(args.out)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        # Preserve partial output for diagnosis, with no success marker or private body echo.
        print(json.dumps({"error": "demo_refused_or_incomplete"}), file=sys.stderr)
        return 2
    print(json.dumps({key: summary[key] for key in ("status", "batch_id", "clean_export")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
