"""Rebuild operational review without overwriting machine metadata or certifying human Gold."""

import hashlib
from dataclasses import asdict

from ..receipt.checks import check_receipt
from ..receipt.models import Receipt, ReceiptLine
from ..receipt.normalization import normalize_date, normalize_money, normalize_quantity
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.models import ScalarPayload, ScalarSubject
from ..shared.rulings.projection import export_labels, project
from ..shared.rulings.store import subject_key
from .files import BatchError

NAMESPACE = "receipt-review/1"


def subject(item_id, field_id):
    return ScalarSubject(kind="field", item_id=item_id, field_id=field_id)


def normalized_value(field_id, value, context):
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 4096:
        raise BatchError("explicit_bounded_review_value_required")
    if field_id == "date":
        result = normalize_date(value, context.reference_date)
        if result.value is None:
            raise BatchError("invalid_review_date")
        # A valid printed future date remains reviewable; the code check still fails visibly.
        # Human review must explicitly disposition that failure before a clean export.
        return result.value
    elif field_id.endswith(":quantity"):
        result = normalize_quantity(value, context.currency)
    elif (
        field_id in {"subtotal", "tax", "total"}
        or field_id.endswith((":unit_price", ":amount"))
        or field_id.startswith("adjustment:")
    ):
        result = normalize_money(value, context.currency)
    elif field_id == "currency":
        if value != context.currency.code:
            raise BatchError("review_currency_differs_from_batch")
        return value
    else:
        return value.strip()
    if result.value is None or result.issues:
        raise BatchError("invalid_review_value")
    return result.value


def review_item(bundle, snapshot):
    receipt = bundle.receipt
    generations = {
        subject_key(NAMESPACE, subject(receipt.document_id, f.field_id)): bundle.generation
        for f in receipt.all_fields()
    }
    views = project(snapshot, generations)
    labels = {
        label.field_id: label
        for label in export_labels(snapshot, generations)
        if label.namespace == NAMESPACE and label.item_id == receipt.document_id
    }
    by_id = {event.event_id: event for event in snapshot.events}
    fields, projected, dispositions = {}, {}, {}
    for field in receipt.all_fields():
        key = subject_key(NAMESPACE, subject(receipt.document_id, field.field_id))
        view = views.get(key)
        event = by_id.get(view.effective_event_id) if view else None
        active = event is not None and isinstance(event.payload, ScalarPayload)
        value = view.value if active else field.value
        state = event.payload.action if active else "needs_review"
        if not active and field.status in ("proposed", "absent") and not field.hard_flags:
            state = field.status
        if active:
            for issue in event.payload.issue_dispositions:
                dispositions[issue.issue_id] = issue.disposition
        projected[field.field_id] = field.model_copy(update={"value": value})
        fields[field.field_id] = {
            "machine": field.model_dump(mode="json"),
            "effective_value": value,
            "corrected": active and canonical_bytes(value) != canonical_bytes(field.proposal),
            "decision_old_value": value
            if active or state in {"proposed", "absent"}
            else field.proposal,
            "review_state": state,
            "head_event_id": view.head_event_id if view else None,
            "effective_event_id": view.effective_event_id if view else None,
            "conflict": view.reason_code if view and not active else None,
            "label": asdict(labels[field.field_id]) if field.field_id in labels else None,
        }
    effective = Receipt(
        receipt_id=receipt.receipt_id,
        document_id=receipt.document_id,
        raw_source_revision=receipt.raw_source_revision,
        artifact_sha256=receipt.artifact_sha256,
        context=receipt.context,
        fields={k: projected[f.field_id] for k, f in receipt.fields.items()},
        line_items=tuple(
            ReceiptLine(
                row_key=row.row_key, cells={k: projected[f.field_id] for k, f in row.cells.items()}
            )
            for row in receipt.line_items
        ),
        adjustments=tuple(
            adjustment.model_copy(update={"amount": projected[adjustment.amount.field_id]})
            for adjustment in receipt.adjustments
        ),
    )
    checks = check_receipt(effective, effective=True)
    issues = {issue for f in receipt.all_fields() for issue in (*f.hard_flags, *f.issues)}
    for check in checks:
        if check.status != "pass":
            values = {fid: projected[fid].value for fid in check.field_ids}
            binding = hashlib.sha256(canonical_bytes(values)).hexdigest()
            issues.add("check:" + check.check_id + ":" + binding)
    unresolved = sorted(
        issue for issue in issues if dispositions.get(issue) not in {"resolved", "waived"}
    )
    unfinished = sorted(fid for fid, f in fields.items() if f["review_state"] == "needs_review")
    if not snapshot.can_append:
        unresolved.append("journal_not_clean")
    return {
        "item_id": receipt.document_id,
        "revision": bundle.revision,
        "generation": bundle.generation.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "document": bundle.document.model_dump(mode="json"),
        "retained_artifact_base64": bundle.artifact_base64,
        "fields": fields,
        "checks": [check.model_dump(mode="json") for check in checks],
        "issue_ids": sorted(issues),
        "unresolved_issues": unresolved,
        "unfinished_fields": unfinished,
        "clean": not unresolved and not unfinished,
        "journal_status": snapshot.status,
        "label_authority": "Local operational decisions; human attribution remains unverified",
    }
