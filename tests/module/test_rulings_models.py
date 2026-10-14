"""Intent/identity shape tests, not append/CAS/crash/reducer execution evidence."""

import hashlib
import json

import pytest
from pydantic import ValidationError
from synthetic_wires import G, H, pair_intent, scalar_intent

from rfr.shared.rulings.identity import (
    canonical_bytes,
    canonical_pair,
    intent_bytes,
    pair_generation,
    pair_key,
)
from rfr.shared.rulings.models import (
    AppendReceipt,
    RecordIdentity,
    RulingEvent,
    RulingIntent,
    ScalarPayload,
)


def test_pair_stable_key_separates_raw_generation_and_opaque_namespace():
    refs = ({"dataset_id": "a", "record_id": "123"}, {"dataset_id": "b", "record_id": "123"})
    expected = {"algorithm_version": 1, "kind": "pair", "refs": [refs[0], refs[1]]}
    clear = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert pair_key(refs) == "pk1:" + hashlib.sha256(clear).hexdigest()
    assert pair_key(tuple(reversed(refs))) == pair_key(refs)
    assert pair_generation(pair_key(refs), (H, G)) != pair_generation(pair_key(refs), (G, H))
    assert canonical_bytes(refs) != canonical_bytes(
        (refs[0], {"dataset_id": "b ", "record_id": "123"})
    )


@pytest.mark.parametrize(
    "left,right",
    [
        (("a:b", "c"), ("a", "b:c")),
        (("é", "1"), ("e\u0301", "1")),
        (("ABC", "123"), ("abc", "123")),
        ((" a", "1"), ("a", "1")),
    ],
)
def test_identity_byte_distinctions_not_separator_or_unicode_normalization(left, right):
    a = {"dataset_id": left[0], "record_id": left[1]}
    b = {"dataset_id": right[0], "record_id": right[1]}
    assert canonical_bytes(a) != canonical_bytes(b)
    assert len(canonical_pair((a, b))) == 2


def test_record_content_hash_is_not_silently_added_to_stable_identity():
    with pytest.raises(ValidationError):
        RecordIdentity(dataset_id="a", record_id="123", content_hash=H)
    with pytest.raises(ValueError):
        canonical_pair(({"dataset_id": "a", "record_id": "123"},) * 2)


def test_scalar_opaque_id_survives_raw_change_and_typed_null_is_preserved():
    first = RulingIntent.model_validate(scalar_intent())
    value = scalar_intent()
    value["generation_identity"]["raw_source_revision"] = "raw-2"
    value["expected_source_revision"] = "raw-2"
    value["payload"] = {
        "action": "waive_absent",
        "old_value": None,
        "new_value": None,
        "issue_dispositions": (),
    }
    second = RulingIntent.model_validate(value)
    assert first.subject == second.subject
    assert second.payload.new_value is None
    assert intent_bytes(first) != intent_bytes(second)


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_label", "other"),
        ("at_utc", "2026-01-02T00:00:00Z"),
        ("reason", "different"),
        ("context_refs", ("different",)),
        ("expected_prior_event_id", "new-head"),
    ],
)
def test_complete_intent_distinguishes_changed_actor_time_reason_context_and_predecessor(
    field, value
):
    original = RulingIntent.model_validate(scalar_intent())
    changed = RulingIntent.model_validate(scalar_intent() | {field: value})
    assert intent_bytes(original) != intent_bytes(changed)


def test_store_sequence_excluded_but_historical_retry_never_asserts_current_authority():
    intent = RulingIntent.model_validate(scalar_intent())
    event = RulingEvent.model_validate(intent.model_dump() | {"sequence": 7})
    assert intent_bytes(intent) == intent_bytes(event)
    retry = AppendReceipt(
        event_id="event-1", sequence=7, intent_sha256=H, outcome="exact_retry", historical=True
    )
    assert retry.current_generation_authority is False
    with pytest.raises(ValidationError):
        AppendReceipt(
            event_id="event-1", sequence=7, intent_sha256=H, outcome="exact_retry", historical=False
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "reversed_refs",
        "wrong_key",
        "wrong_generation",
        "pair_scalar_payload",
        "scalar_pair_payload",
        "wrong_source",
        "wrong_evidence",
        "self_retract",
        "unknown_kind",
        "fake_human",
        "boolean_version",
    ],
)
def test_registered_branch_and_raw_generation_negative_controls(mutation):
    value = (
        pair_intent()
        if mutation not in ("scalar_pair_payload", "wrong_evidence")
        else scalar_intent()
    )
    if mutation == "reversed_refs":
        value["subject"]["refs"] = tuple(reversed(value["subject"]["refs"]))
    elif mutation == "wrong_key":
        value["subject"]["pair_key"] = "pk1:" + H
    elif mutation == "wrong_generation":
        value["generation_identity"]["pair_generation"] = "pg1:" + H
    elif mutation == "pair_scalar_payload":
        value["payload"] = scalar_intent()["payload"]
    elif mutation == "scalar_pair_payload":
        value["payload"] = {"action": "decide", "verdict": "positive"}
    elif mutation == "wrong_source":
        value["expected_source_revision"] = "old-generation"
    elif mutation == "wrong_evidence":
        value["expected_evidence_revision"] = "different"
    elif mutation == "self_retract":
        value["payload"] = {"action": "retract", "target_event_id": "event-1"}
    elif mutation == "unknown_kind":
        value["event_kind"] = "machine_approval"
    elif mutation == "fake_human":
        value["actor_provenance"] = "human"
    elif mutation == "boolean_version":
        value["schema_version"] = True
    with pytest.raises(ValidationError):
        RulingIntent.model_validate(value)


def test_pair_raw_profile_is_a_port_not_an_invented_row_hash_function():
    import rfr.shared.rulings.identity as module

    assert not hasattr(module, "raw_fingerprint")
    wire = RulingIntent.model_validate(pair_intent())
    assert wire.generation_identity.profile == "product-raw-fields-v1"
    for action in (
        {"action": "decide", "verdict": "positive"},
        {"action": "decide", "verdict": "negative"},
        {"action": "retract", "target_event_id": "other-event"},
    ):
        assert (
            RulingIntent.model_validate(pair_intent() | {"payload": action}).payload.action
            == action["action"]
        )
    # Payload shapes validate; effective-target/retraction reduction remains unimplemented.


def test_confirm_boolean_is_not_integer_and_reopen_cannot_reapprove():
    for wire in (
        {"action": "confirm", "old_value": False, "new_value": 0, "issue_dispositions": ()},
        {"action": "reopen", "old_value": True, "new_value": True, "issue_dispositions": ()},
    ):
        with pytest.raises(ValidationError):
            ScalarPayload.model_validate(wire)


def test_unknown_nested_fields_nonfinite_payload_and_non_utc_time_fail():
    for mutate in ("nested", "nonfinite", "time", "boolean_sequence"):
        value = scalar_intent()
        if mutate == "nested":
            value["subject"]["url"] = "https://example.invalid/private"
        elif mutate == "nonfinite":
            value["payload"]["new_value"] = float("nan")
        elif mutate == "time":
            value["at_utc"] = "2026-01-01T00:00:00"
        else:
            value["sequence"] = True
        with pytest.raises(ValidationError):
            (RulingEvent if mutate == "boolean_sequence" else RulingIntent).model_validate(value)
