"""Receipt-local bounded job wires; no model, budget or shared-module schema replacement."""

from typing import Literal

from pydantic import Field, model_validator

from ..shared.docio.models import OpaqueId, Sha256, Wire


class JobSpec(Wire):
    method: Literal["B0", "J1", "V2"]
    source_revisions: dict[OpaqueId, Sha256] = Field(min_length=1, max_length=100)
    config_ref: Literal["receipt-local/1"] = "receipt-local/1"


class ItemProgress(Wire):
    status: Literal[
        "queued", "running", "ok", "error", "stale", "unavailable", "not_run", "unknown_interrupted"
    ]
    result_revision: Sha256 | None = None
    reason: OpaqueId | None = None

    @model_validator(mode="after")
    def branch(self):
        if (self.status == "ok") != (self.result_revision is not None):
            raise ValueError("only_actual_persisted_success_has_result")
        if (self.status in {"queued", "running", "ok"}) != (self.reason is None):
            raise ValueError("failure_or_unrun_needs_explicit_reason")
        return self


class JobRecord(Wire):
    job_id: Sha256
    request_id: OpaqueId
    spec: JobSpec
    execution_config_sha256: Sha256
    state: Literal["pending", "running", "complete", "partial", "failed", "interrupted"]
    items: dict[OpaqueId, ItemProgress] = Field(min_length=1, max_length=100)
    started_at: str | None = None
    ended_at: str | None = None
    execution_origin: Literal["local_rules", "not_run"]
    model_cost_usd: None = None
    model_cost_status: Literal["not_applicable", "not_run"]

    @model_validator(mode="after")
    def fixed_cohort(self):
        if set(self.items) != set(self.spec.source_revisions):
            raise ValueError("job_must_retain_every_requested_item")
        statuses = {item.status for item in self.items.values()}
        if (self.execution_origin == "local_rules") != (self.model_cost_status == "not_applicable"):
            raise ValueError("local_execution_and_nonmodel_cost_branch_mismatch")
        if self.spec.method != "B0" and ("ok" in statuses or self.execution_origin != "not_run"):
            raise ValueError("unconnected_model_arm_cannot_claim_local_success")
        if "ok" in statuses and self.execution_origin != "local_rules":
            raise ValueError("successful_items_require_actual_local_execution")
        if self.state == "pending" and statuses != {"queued"}:
            raise ValueError("pending_job_has_no_results")
        if self.state == "complete" and statuses != {"ok"}:
            raise ValueError("complete_job_requires_every_actual_success")
        if self.state in {"partial", "failed", "interrupted"} and statuses & {"queued", "running"}:
            raise ValueError("terminal_job_cannot_hide_pending_items")
        if self.state == "partial" and ("ok" not in statuses or statuses == {"ok"}):
            raise ValueError("partial_requires_actual_success_and_failure")
        if self.state == "failed" and "ok" in statuses:
            raise ValueError("failed_job_cannot_drop_actual_success")
        return self
