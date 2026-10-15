"""Initial application HTTP wires, independent of FastAPI and shared-module schema ownership."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ..pipeline.job_models import JobRecord, JobSpec
from ..pipeline.models import ReceiptBundle
from ..receipt.models import CheckResult, CurrencyPolicy, Receipt
from ..shared.docio.models import Document, OpaqueId, Sha256, Wire
from ..shared.fieldextract.models import FieldValue
from ..shared.rulings.models import RulingIntent, ScalarGeneration


class DecisionDraft(BaseModel):
    """Existing two-key CLI envelope, deliberately no added schema_version or key rewrite."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    expected_item_revision: str
    intent: RulingIntent


class DraftRequest(Wire):
    field_id: OpaqueId
    action: Literal["correct", "confirm", "waive_absent", "reopen"]
    value: str | None = Field(default=None, max_length=4096)
    expected_item_revision: Sha256
    expected_prior_event_id: OpaqueId | None
    actor: OpaqueId
    actor_kind: Literal["agent_provisional", "human_claimed"] = "agent_provisional"
    actor_ref: OpaqueId | None = None
    event_id: OpaqueId | None = None
    reason: str = Field(min_length=1, max_length=4096)
    waive_issues: tuple[OpaqueId, ...] = Field(default=(), max_length=1024)
    issue_reason: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def reasons(self):
        if not self.reason.strip() or len(self.reason.encode("utf-8")) > 4096:
            raise ValueError("bounded_explicit_reason_required")
        if len(set(self.waive_issues)) != len(self.waive_issues):
            raise ValueError("duplicate_issue_waiver")
        if self.waive_issues and (not self.issue_reason or not self.issue_reason.strip()):
            raise ValueError("explicit_issue_reason_required")
        if self.actor_kind == "human_claimed" and self.actor_ref is None:
            raise ValueError("claimed_human_reference_required")
        return self

    def command_arguments(self):
        return {
            "field": self.field_id,
            "action": self.action,
            "value": self.value,
            "expected_revision": self.expected_item_revision,
            "expected_prior": self.expected_prior_event_id,
            "actor": self.actor,
            "actor_kind": self.actor_kind,
            "actor_ref": self.actor_ref,
            "event_id": self.event_id,
            "reason": self.reason,
            "waive_issues": self.waive_issues,
            "issue_reason": self.issue_reason,
        }


class ReviewLabel(Wire):
    namespace: OpaqueId
    item_id: OpaqueId
    field_id: OpaqueId
    row_key: OpaqueId | None
    presence: Literal["present", "absent", "unlabelled"]
    value: JsonValue
    label_source: Literal["human", "agent_provisional", "unverified_human", "unlabelled"]
    label_provenance_ref: OpaqueId | None
    event_id: OpaqueId | None
    head_event_id: OpaqueId
    source_revision: OpaqueId | None
    evidence_revision: OpaqueId | None
    state: Literal["effective", "waived_absent", "needs_review"]


class ReviewField(Wire):
    machine: FieldValue
    effective_value: JsonValue
    corrected: bool
    decision_old_value: JsonValue
    review_state: Literal[
        "correct", "confirm", "waive_absent", "needs_review", "proposed", "absent"
    ]
    head_event_id: OpaqueId | None
    effective_event_id: OpaqueId | None
    conflict: OpaqueId | None
    label: ReviewLabel | None


class ItemReview(Wire):
    item_id: OpaqueId
    revision: Sha256
    generation: ScalarGeneration
    receipt: Receipt
    document: Document
    fields: dict[OpaqueId, ReviewField] = Field(max_length=827)
    checks: tuple[CheckResult, ...]
    issue_ids: tuple[OpaqueId, ...]
    unresolved_issues: tuple[OpaqueId, ...]
    unfinished_fields: tuple[OpaqueId, ...]
    clean: bool
    journal_status: OpaqueId
    label_authority: str = Field(max_length=512)

    @model_validator(mode="after")
    def complete_schema(self):
        if self.item_id != self.receipt.document_id or self.item_id != self.document.document_id:
            raise ValueError("item_document_binding_required")
        if self.generation.raw_source_revision != self.document.raw_source_revision:
            raise ValueError("review_generation_binding_required")
        actual = {field.field_id: field for field in self.receipt.all_fields()}
        if set(actual) != set(self.fields):
            raise ValueError("complete_scalar_line_adjustment_review_required")
        if any(self.fields[key].machine != field for key, field in actual.items()):
            raise ValueError("machine_review_metadata_cannot_change")
        if not set(self.unfinished_fields) <= set(self.fields):
            raise ValueError("unknown_unfinished_field")
        if not set(self.unresolved_issues) <= set(self.issue_ids) | {"journal_not_clean"}:
            raise ValueError("unknown_unresolved_issue")
        if self.clean and (self.unresolved_issues or self.unfinished_fields):
            raise ValueError("clean_cannot_hide_unresolved_items")
        return self


class ItemDetail(Wire):
    review: ItemReview
    image_available: bool = False


class CreateBatch(Wire):
    currency: CurrencyPolicy


class ItemSummary(Wire):
    item_id: OpaqueId
    revision: Sha256 | None
    deleted: bool
    clean: bool
    unfinished_fields: tuple[OpaqueId, ...]
    unresolved_issues: tuple[OpaqueId, ...]


class BatchSummary(Wire):
    batch_id: OpaqueId
    currency: Literal["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "KWD"]
    item_count: int = Field(ge=0, le=100)


class BatchView(BatchSummary):
    items: tuple[ItemSummary, ...] = Field(max_length=100)
    jobs: tuple[JobRecord, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def complete_items(self):
        if len(self.items) != self.item_count or len({item.item_id for item in self.items}) != len(
            self.items
        ):
            raise ValueError("batch_summary_must_retain_every_registered_item")
        return self


class Capabilities(Wire):
    recognized_import: bool
    image_upload: bool
    source_images: bool
    review_persistence: bool
    local_b0: bool
    jev: bool
    vision: bool


class ApiStatus(Wire):
    contract: Literal["receipt-api/1"] = "receipt-api/1"
    mode: Literal["local", "synthetic_demo"]
    stage: OpaqueId
    currencies: tuple[Literal["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "KWD"], ...]
    capabilities: Capabilities


class RecognizedImport(Wire):
    bundle: ReceiptBundle
    expected_revision: Sha256 | None = None


class StartJob(Wire):
    request_id: OpaqueId
    spec: JobSpec


API_MODELS = (
    DecisionDraft,
    DraftRequest,
    ReviewLabel,
    ReviewField,
    ItemReview,
    ItemDetail,
    CreateBatch,
    ItemSummary,
    BatchSummary,
    BatchView,
    Capabilities,
    ApiStatus,
    RecognizedImport,
    StartJob,
)
