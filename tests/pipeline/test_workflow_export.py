"""Actual file/journal workflow and private exports over literal source-backed controls."""

import csv
import io
import json

import pytest
from test_review_store import decision

from rfr.export.receipt import export_receipts, write_export
from rfr.shared.rulings.models import IssueDisposition
from rfr.shared.rulings.store import GenerationConflict, PathRefused


def test_clean_refusals_then_explicit_all_field_and_issue_resolution(
    batch, bundle_factory, tmp_path
):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    item = bundle.document.document_id
    first = export_receipts(batch, mode="clean")
    assert first["receipts.jsonl"] == b""
    omitted = json.loads(first["omitted.json"])
    assert omitted["requested_N"] == 1 and omitted["exported_N"] == 0
    view = batch.detail(item)
    batch.decide(decision(bundle, view, new="=2+2"), expected_item_revision=revision)
    assert json.loads(export_receipts(batch, mode="clean")["omitted.json"])["exported_N"] == 0
    for n, field in enumerate(bundle.receipt.all_fields(), 1):
        view = batch.detail(item)
        if view["fields"][field.field_id]["review_state"] != "needs_review":
            continue
        value = field.proposal
        action = "waive_absent" if value is None else "confirm"
        batch.decide(
            decision(bundle, view, field.field_id, event=f"field-{n}", action=action, new=value),
            expected_item_revision=revision,
        )
    view = batch.detail(item)
    assert view["unfinished_fields"] == []
    assert view["unresolved_issues"]  # Confirming numbers alone does not waive code/hard issues.
    dispositions = tuple(
        IssueDisposition(
            issue_id=issue, disposition="waived", reason="Explicit literal control waiver"
        )
        for issue in view["unresolved_issues"]
    )
    batch.decide(
        decision(
            bundle, view, event="explicit-issues", action="confirm", new="=2+2", issues=dispositions
        ),
        expected_item_revision=revision,
    )
    view = batch.detail(item)
    assert view["clean"] and all(f["machine"]["confidence"] != 1 for f in view["fields"].values())
    files = export_receipts(batch, mode="clean")
    audit = json.loads(files["receipts.jsonl"])
    assert audit["fields"]["merchant_name"]["effective_value"] == "=2+2"
    assert audit["fields"]["merchant_name"]["label"]["label_source"] == "agent_provisional"
    assert audit["document"]["raw_source_revision"] == bundle.document.raw_source_revision
    assert audit["retained_artifact_base64"] == bundle.artifact_base64
    scalar = list(csv.DictReader(io.StringIO(files["receipts.csv"].decode())))[0]
    assert scalar["merchant_name"] == "'=2+2"
    assert scalar["merchant_name_method"] == bundle.receipt.fields["merchant_name"].method
    assert scalar["merchant_name_human_corrected"] == "false"
    lines = list(csv.DictReader(io.StringIO(files["line_items.csv"].decode())))
    assert len(lines) == len(bundle.receipt.line_items)
    assert all("quantity_audit_json" in line and "amount_confidence" in line for line in lines)
    destination = write_export(tmp_path, files)
    assert (destination / "receipts.jsonl").read_bytes() == files["receipts.jsonl"]
    assert len(json.loads((destination / "EXPORT.json").read_bytes())["files"]) == 4
    assert write_export(tmp_path, files) != destination


def test_unknown_issue_and_invalid_money_do_not_write(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    intent = decision(bundle, view, "total", new="garbage")
    with pytest.raises(GenerationConflict):
        batch.decide(intent, expected_item_revision=revision)
    assert not batch.journal.path.exists()
    issue = IssueDisposition(issue_id="unknown-hard-issue", disposition="waived", reason="control")
    with pytest.raises(GenerationConflict):
        batch.decide(decision(bundle, view, issues=(issue,)), expected_item_revision=revision)
    assert not batch.journal.path.exists()
    assert not batch.detail(bundle.document.document_id)["clean"]
    with pytest.raises((FileNotFoundError, PathRefused)):
        write_export(batch.root / "does-not-exist", export_receipts(batch))


def test_review_export_keeps_unresolved_and_deleted_items(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    files = export_receipts(batch)
    assert json.loads(files["receipts.jsonl"])["clean"] is False
    batch.delete(bundle.document.document_id, expected_revision=revision)
    assert json.loads(export_receipts(batch)["receipts.jsonl"])["deleted"] is True
    omitted = json.loads(export_receipts(batch, mode="clean")["omitted.json"])
    assert omitted["omitted"][0]["reasons"] == ["deleted"]


def test_claimed_human_stays_unverified_and_confirmation_retains_corrected_audit(
    batch, bundle_factory
):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    item = bundle.document.document_id
    intent = decision(bundle, batch.detail(item)).model_copy(
        update={
            "actor_provenance": "human",
            "actor_provenance_ref": "synthetic-unverified-claim-only",
        }
    )
    batch.decide(intent, expected_item_revision=revision)
    view = batch.detail(item)
    confirm = decision(bundle, view, event="confirm-later", action="confirm", new="Corrected Shop")
    confirm = confirm.model_copy(
        update={
            "actor_provenance": "human",
            "actor_provenance_ref": "synthetic-unverified-claim-only",
        }
    )
    batch.decide(confirm, expected_item_revision=revision)
    exported = export_receipts(batch)
    row = list(csv.DictReader(io.StringIO(exported["receipts.csv"].decode())))[0]
    assert row["merchant_name_human_corrected"] == "true"
    audit = json.loads(exported["receipts.jsonl"])
    assert audit["fields"]["merchant_name"]["label"]["label_source"] == "unverified_human"
