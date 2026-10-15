"""Receipt B0 adapter over actual retained Docio evidence and the unchanged generic engine."""

import hashlib

from ..shared.docio.identity import validate_artifact_bytes, validate_evidence
from ..shared.docio.models import Document, TransformPair
from ..shared.fieldextract.engine import (
    UNCALIBRATED_POLICY,
    EvidenceAssessment,
    JudgmentBindings,
    apply_domain_checks,
    extract_field,
)
from ..shared.fieldextract.models import DocumentEvidence
from .candidates import Entry, build_bank
from .checks import check_issues, check_receipt
from .models import PrintedAdjustment, Receipt, ReceiptContext, ReceiptLine


def extract_b0(
    document: Document,
    retained_artifact: bytes,
    expected_artifact_sha256: str,
    context: ReceiptContext,
) -> Receipt:
    artifact = validate_artifact_bytes(retained_artifact, expected_artifact_sha256)
    bank = build_bank(document, artifact, expected_artifact_sha256, context)
    transforms = {
        "transform:" + artifact.artifact_id: TransformPair(
            source_to_engine=artifact.source_to_engine, engine_to_source=artifact.engine_to_source
        )
    }
    words = {word.stable_id: word for word in artifact.words}
    lines = {line.stable_id: line for line in artifact.lines}

    class ReceiptEvidenceAuthority:
        def assess(self, candidate):
            if len(candidate.sources) != 1 or not isinstance(
                candidate.sources[0], DocumentEvidence
            ):
                raise ValueError("receipt_document_source_required")
            source = candidate.sources[0]
            excerpt = validate_evidence(
                source.evidence,
                document,
                retained_artifact,
                require_measured_spatial=True,
                resolved_transforms=transforms,
            )
            if type(candidate.raw) is not str or excerpt is None or candidate.raw not in excerpt:
                raise ValueError("receipt_raw_occurrence_mismatch")
            ref = source.evidence
            ids = (
                ref.word_ids
                if ref.word_ids
                else tuple(
                    word_id
                    for line_id in ref.line_ids
                    for word_id in lines[line_id].ordered_child_ids
                )
            )
            matched = tuple(words[word_id] for word_id in ids)
            origins = {word.geometry_provenance for word in matched}
            if origins == {"native"} and document.source_kind in ("pdf", "native_text"):
                origin = "native_text"
                policy = "receipt-native-structural/1"
            elif origins == {"measured_ocr"}:
                origin = "measured_ocr"
                policy = "receipt-measured-word-min/1"
            else:
                origin = "none"
                policy = "receipt-unsupported-geometry/1"
            return EvidenceAssessment(
                source, origin, tuple(w.ocr_confidence for w in matched), policy
            )

    authority = ReceiptEvidenceAuthority()

    def extract(entry: Entry):
        return extract_field(
            entry.spec,
            entry.candidates,
            authority,
            JudgmentBindings("receipt-select:" + entry.spec.field_id, "none", {}, "synthetic"),
            mode="B0",
            policy=UNCALIBRATED_POLICY,
            chosen_candidate_id=entry.chosen_id,
            b0_prior=entry.prior,
            hard_flags=entry.hard_flags,
        )

    fields = {key: extract(value) for key, value in bank.fields.items()}
    rows = tuple(
        ReceiptLine(
            row_key=row.row_key, cells={key: extract(value) for key, value in row.fields.items()}
        )
        for row in bank.rows
    )
    adjustments = tuple(
        PrintedAdjustment(
            adjustment_id=item.adjustment_id,
            kind=item.kind,
            stage=item.stage,
            amount=extract(item.field),
        )
        for item in bank.adjustments
    )
    receipt = Receipt(
        receipt_id="receipt1:" + hashlib.sha256(document.raw_source_revision.encode()).hexdigest(),
        document_id=document.document_id,
        raw_source_revision=document.raw_source_revision,
        artifact_sha256=expected_artifact_sha256,
        context=context,
        fields=fields,
        line_items=rows,
        adjustments=adjustments,
    )
    checks = check_receipt(receipt)

    class Checks:
        def check(self, fields):
            return check_issues(checks)

    checked = {
        field.field_id: field for field in apply_domain_checks(receipt.all_fields(), Checks())
    }
    return Receipt(
        receipt_id=receipt.receipt_id,
        document_id=receipt.document_id,
        raw_source_revision=receipt.raw_source_revision,
        artifact_sha256=receipt.artifact_sha256,
        context=context,
        fields={key: checked[value.field_id] for key, value in fields.items()},
        line_items=tuple(
            ReceiptLine(
                row_key=row.row_key,
                cells={key: checked[value.field_id] for key, value in row.cells.items()},
            )
            for row in rows
        ),
        adjustments=tuple(
            PrintedAdjustment(
                adjustment_id=item.adjustment_id,
                kind=item.kind,
                stage=item.stage,
                amount=checked[item.amount.field_id],
            )
            for item in adjustments
        ),
        checks=checks,
    )
