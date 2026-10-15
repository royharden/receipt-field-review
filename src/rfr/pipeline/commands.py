"""One domain draft builder for CLI and the eventual HTTP interface; no automatic application."""

import uuid
from datetime import UTC, datetime

from ..shared.rulings.models import IssueDisposition, RulingIntent, ScalarPayload
from ..shared.rulings.store import PriorConflict
from .files import BatchError
from .review import NAMESPACE, normalized_value, subject

_UNOBSERVED = object()


def draft_decision(
    store,
    *,
    item,
    field,
    action,
    value=None,
    reason,
    actor,
    actor_kind="agent_provisional",
    actor_ref=None,
    event_id=None,
    waive_issues=(),
    issue_reason=None,
    expected_revision=None,
    expected_prior=_UNOBSERVED,
):
    view = store.detail(item)
    bundle = store.bundle(item)
    if bundle.revision != view["revision"]:
        raise BatchError("source_changed_during_draft")
    if expected_revision is not None and expected_revision != bundle.revision:
        raise PriorConflict("observed_item_revision_conflict")
    current = view["fields"].get(field)
    if current is None:
        raise BatchError("unknown_receipt_field")
    if expected_prior is not _UNOBSERVED and expected_prior != current["head_event_id"]:
        raise PriorConflict("observed_field_head_conflict")
    if action == "correct":
        new = normalized_value(field, value, bundle.receipt.context)
    elif action == "confirm":
        new = current["decision_old_value"]
        if new is None:
            raise BatchError("confirm_missing_requires_explicit_absence_waiver")
    elif action in {"waive_absent", "reopen"}:
        new = None
    else:
        raise BatchError("unknown_receipt_action")
    if waive_issues and not issue_reason:
        raise BatchError("explicit_issue_reason_required")
    if actor_kind not in {"human_claimed", "agent_provisional"}:
        raise BatchError("unknown_actor_claim")
    if actor_kind == "human_claimed" and not actor_ref:
        raise BatchError("claimed_human_provenance_reference_required")
    intent = RulingIntent(
        event_id=event_id or uuid.uuid4().hex,
        namespace=NAMESPACE,
        subject=subject(item, field),
        generation_identity=bundle.generation,
        event_kind="scalar_decision",
        payload=ScalarPayload(
            action=action,
            old_value=current["decision_old_value"],
            new_value=new,
            issue_dispositions=tuple(
                IssueDisposition(issue_id=issue, disposition="waived", reason=issue_reason)
                for issue in waive_issues
            ),
        ),
        expected_source_revision=bundle.document.raw_source_revision,
        expected_evidence_revision=bundle.generation.evidence_revision,
        expected_prior_event_id=current["head_event_id"],
        actor_label=actor,
        actor_provenance="human" if actor_kind == "human_claimed" else "agent_provisional",
        actor_provenance_ref=actor_ref,
        at_utc=datetime.now(UTC).isoformat(),
        reason=reason,
        context_refs=(),
    )
    return {"expected_item_revision": bundle.revision, "intent": intent.model_dump(mode="json")}
