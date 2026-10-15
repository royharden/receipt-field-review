"""Receipt-local file storage wires, separate from reusable module schemas."""

import base64
import hashlib

from pydantic import Field, model_validator

from ..receipt.models import CurrencyPolicy, Receipt
from ..shared.docio.identity import validate_artifact_bytes, validate_evidence
from ..shared.docio.models import Document, OpaqueId, Sha256, TransformPair, Wire
from ..shared.fieldextract.models import DocumentEvidence
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.models import ScalarGeneration


class ReceiptBundle(Wire):
    document: Document
    receipt: Receipt
    artifact_base64: str = Field(max_length=4 * 1024 * 1024)

    @model_validator(mode="after")
    def bindings(self):
        raw = self.artifact_bytes()
        artifact = validate_artifact_bytes(raw, self.receipt.artifact_sha256)
        doc, receipt = self.document, self.receipt
        if (
            len(doc.pages) != 1
            or receipt.document_id != doc.document_id
            or receipt.raw_source_revision != doc.raw_source_revision
        ):
            raise ValueError("single_receipt_document_binding_required")
        page = doc.pages[0]
        if page.processing_ref != artifact.artifact_id or page.model_dump(
            exclude={"source_kind", "processing_ref"}
        ) != artifact.model_dump(
            include=set(type(page).model_fields) - {"source_kind", "processing_ref"}
        ):
            raise ValueError("retained_page_artifact_binding_required")
        if any(f.status == "human_effective" for f in receipt.all_fields()):
            raise ValueError("machine_bundle_cannot_contain_human_projection")
        transforms = {
            "transform:" + artifact.artifact_id: TransformPair(
                source_to_engine=artifact.source_to_engine,
                engine_to_source=artifact.engine_to_source,
            )
        }
        for field in receipt.all_fields():
            if field.source is not None:
                if type(field.source) is not DocumentEvidence:
                    raise ValueError("receipt_source_must_be_document_evidence")
                validate_evidence(
                    field.source.evidence,
                    doc,
                    raw,
                    require_measured_spatial=True,
                    resolved_transforms=transforms,
                )
        return self

    def artifact_bytes(self):
        try:
            return base64.b64decode(self.artifact_base64, validate=True)
        except ValueError:
            raise ValueError("invalid_retained_artifact_encoding") from None

    @property
    def revision(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()

    @property
    def generation(self):
        evidence = hashlib.sha256(
            canonical_bytes(
                {
                    "artifact": self.receipt.artifact_sha256,
                    "context": self.receipt.context.model_dump(mode="json"),
                }
            )
        ).hexdigest()
        return ScalarGeneration(
            kind="scalar",
            profile="receipt-review/1",
            source_sha256=self.document.original_content_sha256,
            raw_source_revision=self.document.raw_source_revision,
            evidence_revision=evidence,
        )


class BatchManifest(Wire):
    batch_id: OpaqueId
    currency: CurrencyPolicy
    items: dict[OpaqueId, Sha256 | None] = Field(max_length=100)
