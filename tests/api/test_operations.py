"""Real file/journal operations behind the future transport, using authored receipt input."""

import json

import pytest

from rfr.api.models import CreateBatch, DraftRequest, RecognizedImport
from rfr.api.operations import ReviewOperations
from rfr.pipeline.files import BatchError
from rfr.receipt.models import CurrencyPolicy
from rfr.shared.rulings.store import PriorConflict


def setup(tmp_path, bundle_factory):
    operations = ReviewOperations(tmp_path)
    batch = operations.create(CreateBatch(currency=CurrencyPolicy()))
    bundle = bundle_factory()
    revision = operations.import_recognized(batch.batch_id, RecognizedImport(bundle=bundle))
    return operations, batch.batch_id, bundle, revision


def request(field, *, revision, prior=None, value="Facade Shop"):
    return DraftRequest(
        field_id=field,
        action="correct",
        value=value,
        expected_item_revision=revision,
        expected_prior_event_id=prior,
        actor="synthetic-operation-control",
        reason="Authored operation control, no human Gold claim",
    )


def test_typed_operations_preserve_corrections_and_machine_evidence_in_new_facade(
    tmp_path, bundle_factory
):
    operations, batch, bundle, revision = setup(tmp_path, bundle_factory)
    item = bundle.document.document_id
    before = operations.detail(batch, item)
    assert not before.image_available and not before.review.clean
    assert "retained_artifact_base64" not in before.model_dump(mode="json")["review"]
    assert operations.items(batch)[0].revision == revision
    draft = operations.draft(batch, item, request("merchant_name", revision=revision))
    assert operations.apply(batch, item, draft).outcome == "appended"
    assert operations.apply(batch, item, draft).outcome == "exact_retry"
    resumed = ReviewOperations(tmp_path)
    after = resumed.detail(batch, item)
    assert after.review.fields["merchant_name"].effective_value == "Facade Shop"
    assert (
        after.review.fields["merchant_name"].machine
        == before.review.fields["merchant_name"].machine
    )
    assert after.review.fields["merchant_name"].label.label_source == "agent_provisional"
    assert json.loads(resumed.export(batch, mode="clean")["omitted.json"])["exported_N"] == 0
    row = json.loads(resumed.export(batch)["receipts.jsonl"])
    assert row["fields"]["merchant_name"]["effective_value"] == "Facade Shop"
    assert row["retained_artifact_base64"] == bundle.artifact_base64


def test_route_item_mismatch_and_stale_field_head_do_not_append(tmp_path, bundle_factory):
    operations, batch, bundle, revision = setup(tmp_path, bundle_factory)
    item = bundle.document.document_id
    first = operations.draft(batch, item, request("merchant_name", revision=revision))
    with pytest.raises(BatchError, match="decision_route_item_conflict"):
        operations.apply(batch, "other-route-item", first)
    assert not (tmp_path / batch / "rulings.jsonl").exists()
    operations.apply(batch, item, first)
    with pytest.raises(PriorConflict, match="observed_field_head"):
        operations.draft(batch, item, request("merchant_name", revision=revision))


def test_tombstone_summary_and_unchanged_import_cannot_restore_item(tmp_path, bundle_factory):
    operations, batch, bundle, revision = setup(tmp_path, bundle_factory)
    item = bundle.document.document_id
    operations.delete(batch, item, expected_revision=revision)
    summary = operations.items(batch)[0]
    assert summary.deleted and not summary.clean and summary.revision is None
    with pytest.raises(BatchError, match="deleted_item_requires_new_identity"):
        operations.import_recognized(batch, RecognizedImport(bundle=bundle))
    assert json.loads(operations.export(batch)["receipts.jsonl"])["deleted"] is True


def test_untyped_and_mutated_requests_refuse_before_creating_storage(tmp_path):
    operations = ReviewOperations(tmp_path)
    with pytest.raises(BatchError, match="validated_api_request_required"):
        operations.create({"currency": "USD"})
    assert list(tmp_path.iterdir()) == []
