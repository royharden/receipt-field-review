"""Actual source-backed API DTOs and shared CLI draft semantics, not an HTTP acceptance claim."""

import json
from argparse import Namespace
from datetime import UTC, datetime

import pytest

from rfr.api.models import DecisionDraft, DraftRequest, ItemDetail, ItemReview
from rfr.cli import make_draft
from rfr.pipeline.commands import draft_decision
from rfr.shared.rulings.store import PriorConflict


def wire_view(batch, bundle_factory):
    bundle = bundle_factory()
    batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    return bundle, {key: value for key, value in view.items() if key != "retained_artifact_base64"}


def test_real_review_model_retains_all_scalar_line_adjustment_and_source_metadata(
    batch, bundle_factory
):
    bundle, view = wire_view(batch, bundle_factory)
    detail = ItemDetail.model_validate_json(json.dumps({"review": view}))
    actual = detail.review
    assert not detail.image_available
    assert len(actual.fields) == len(bundle.receipt.all_fields())
    assert set(actual.fields) == {field.field_id for field in bundle.receipt.all_fields()}
    assert actual.document == bundle.document and actual.receipt == bundle.receipt
    assert all(len(line.cells) == 4 for line in actual.receipt.line_items)
    assert "retained_artifact_base64" not in actual.model_dump(mode="json")
    assert not actual.clean and actual.unfinished_fields


@pytest.mark.parametrize(
    "mutation", ["omit_line", "change_machine", "fake_clean", "different_item", "raw_artifact"]
)
def test_closed_review_cannot_drop_line_metadata_change_scores_or_smuggle_artifact(
    batch, bundle_factory, mutation
):
    bundle, view = wire_view(batch, bundle_factory)
    if mutation == "omit_line":
        del view["fields"][bundle.receipt.line_items[0].cells["amount"].field_id]
    elif mutation == "change_machine":
        view["fields"]["merchant_name"]["machine"]["confidence"] = 1.0
    elif mutation == "fake_clean":
        view["clean"] = True
    elif mutation == "different_item":
        view["item_id"] = "different-source"
    else:
        view["retained_artifact_base64"] = bundle.artifact_base64
    with pytest.raises(ValueError):
        ItemReview.model_validate_json(json.dumps(view))


def request(view):
    return DraftRequest(
        field_id="total",
        action="correct",
        value="12.5",
        expected_item_revision=view["revision"],
        expected_prior_event_id=None,
        actor="literal-controller",
        reason="Explicit synthetic draft control",
        event_id="fixed-event",
    )


def test_cli_and_api_share_exact_two_key_draft_wire_and_domain_normalization(
    batch, bundle_factory, monkeypatch
):
    bundle, view = wire_view(batch, bundle_factory)
    import rfr.pipeline.commands as commands

    class Clock:
        @staticmethod
        def now(zone):
            assert zone is UTC
            return datetime(2026, 10, 15, tzinfo=UTC)

    monkeypatch.setattr(commands, "datetime", Clock)
    req = request(view)
    api = draft_decision(batch, item=bundle.document.document_id, **req.command_arguments())
    cli = make_draft(
        batch,
        Namespace(
            item=bundle.document.document_id,
            field=req.field_id,
            action=req.action,
            value=req.value,
            reason=req.reason,
            actor=req.actor,
            actor_kind=req.actor_kind,
            actor_ref=req.actor_ref,
            event_id=req.event_id,
            waive_issue=list(req.waive_issues),
            issue_reason=req.issue_reason,
        ),
    )
    assert cli == api and set(cli) == {"expected_item_revision", "intent"}
    draft = DecisionDraft.model_validate_json(json.dumps(api))
    assert draft.intent.payload.new_value == "12.50"
    assert set(draft.model_dump(mode="json")) == set(cli)


def test_observed_prior_and_source_revision_cannot_silently_draft_against_new_state(
    batch, bundle_factory
):
    bundle, view = wire_view(batch, bundle_factory)
    req = request(view)
    payload = draft_decision(batch, item=bundle.document.document_id, **req.command_arguments())
    parsed = DecisionDraft.model_validate_json(json.dumps(payload))
    batch.decide(parsed.intent, expected_item_revision=parsed.expected_item_revision)
    with pytest.raises(PriorConflict, match="observed_field_head"):
        draft_decision(batch, item=bundle.document.document_id, **req.command_arguments())
    args = req.command_arguments() | {"expected_revision": "f" * 64}
    with pytest.raises(PriorConflict, match="observed_item_revision"):
        draft_decision(batch, item=bundle.document.document_id, **args)


@pytest.mark.parametrize(
    "change",
    [
        {"reason": " "},
        {"reason": "é" * 3000},
        {"extra": True},
        {"actor_kind": "human_claimed"},
        {"waive_issues": ["issue"]},
        {"waive_issues": ["issue", "issue"], "issue_reason": "explicit"},
    ],
)
def test_initial_http_draft_input_is_closed_and_requires_explicit_claim_reasons(
    batch, bundle_factory, change
):
    _, view = wire_view(batch, bundle_factory)
    payload = json.loads(request(view).model_dump_json()) | change
    with pytest.raises(ValueError):
        DraftRequest.model_validate_json(json.dumps(payload))
