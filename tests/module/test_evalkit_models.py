"""Frozen populations, gold/input separation and privacy controls; no scoring engine."""

import copy

import pytest
from pydantic import ValidationError
from synthetic_wires import (
    H,
    gold_wire,
    manifest_wire,
    metric_wire,
    prediction_wire,
    projection_policy,
)

from rfr.shared.evalkit.identity import (
    ordered_ids_digest,
    validate_expected_predictions,
    validate_public_projection,
)
from rfr.shared.evalkit.models import (
    FieldLabel,
    GoldRecord,
    Manifest,
    MetricRow,
    Prediction,
    PublicMethodInput,
    PublicProjectionPolicy,
    ResamplingSpec,
)


@pytest.mark.parametrize("value", [False, True, "none", "multiple", "unknown", 0])
def test_present_target_class_is_not_absent_or_unlabelled(value):
    label = FieldLabel(presence="present", value=value)
    assert label.value == value and label.presence == "present"


@pytest.mark.parametrize(
    "presence,value", [("absent", False), ("unlabelled", "none"), ("present", None)]
)
def test_invalid_presence_value_crossovers_reject(presence, value):
    with pytest.raises(ValidationError):
        FieldLabel(presence=presence, value=value)


def test_human_corrected_reference_valid_and_machine_prediction_not_replaced():
    gold = GoldRecord.model_validate(gold_wire())
    prediction = Prediction.model_validate(prediction_wire())
    assert gold.label_source == "human_corrected"
    assert prediction.machine_output is False and prediction.human_effective_output is True
    with pytest.raises(ValidationError):
        GoldRecord.model_validate(gold_wire() | {"label_provenance_ref": None})
    assert (
        GoldRecord.model_validate(
            gold_wire() | {"label_source": "agent_provisional", "label_provenance_ref": None}
        ).label_source
        == "agent_provisional"
    )


def test_scorer_gold_cannot_be_public_method_input_and_no_hidden_top_level_config():
    with pytest.raises(ValidationError):
        PublicMethodInput.model_validate(gold_wire())
    public = {
        "item_id": "case:1",
        "public_payload": {"text": "synthetic text"},
        "input_sha256": H,
        "public_config_refs": ("public-schema/1",),
    }
    assert PublicMethodInput.model_validate(public).public_payload == {"text": "synthetic text"}
    with pytest.raises(ValidationError):
        PublicMethodInput.model_validate(public | {"gold": gold_wire()})
    with pytest.raises(ValidationError):
        PublicMethodInput.model_validate(
            public | {"public_payload": {"record": GoldRecord.model_validate(gold_wire())}}
        )


def test_manifest_preserves_null_published_seed_and_order_unicode():
    manifest = Manifest.model_validate(manifest_wire())
    assert manifest.split_seed is None
    assert ordered_ids_digest(("é", "e\u0301")) != ordered_ids_digest(("e\u0301", "é"))
    assert ordered_ids_digest(("a ",)) != ordered_ids_digest(("a",))


@pytest.mark.parametrize(
    "mutation",
    [
        "bool_seed",
        "bool_count",
        "wrong_count",
        "wrong_order",
        "duplicate_id",
        "cross_group",
        "wrong_split",
        "missing_group",
        "unpublished_null",
        "path_escape",
        "source_count",
        "unknown_field",
        "relabel_freeze",
    ],
)
def test_canonical_manifest_negative_controls(mutation):
    wire = copy.deepcopy(manifest_wire())
    if mutation == "bool_seed":
        wire["split_seed"] = True
    elif mutation == "bool_count":
        wire["splits"][0]["item_count"] = True
    elif mutation == "wrong_count":
        wire["splits"][0]["item_count"] = 3
    elif mutation == "wrong_order":
        wire["splits"][0]["ordered_item_ids"] = ("case:2", "case:1")
    elif mutation == "duplicate_id":
        wire["splits"][0]["ordered_item_ids"] = ("case:1", "case:1")
    elif mutation == "cross_group":
        wire["group_members"]["group:2"] = ("case:2", "asset:1")
    elif mutation == "wrong_split":
        wire["group_split_map"]["group:1"] = "heldout"
    elif mutation == "missing_group":
        del wire["group_split_map"]["group:1"]
    elif mutation == "unpublished_null":
        wire["partition_provenance"] = "seeded"
    elif mutation == "path_escape":
        wire["splits"][0]["items_file"] = "../private.jsonl"
    elif mutation == "source_count":
        wire["source_artifacts"][0]["count"] = 3
    elif mutation == "unknown_field":
        wire["schema"] = 1
    elif mutation == "relabel_freeze":
        wire["frozen_at"] = "2026-01-01T00:00:00-05:00"
    with pytest.raises(ValidationError):
        Manifest.model_validate(wire)


def test_error_rows_count_and_never_run_has_no_fake_outputs():
    error = Prediction.model_validate(
        prediction_wire()
        | {
            "status": "provider_error",
            "domain_payload": None,
            "machine_output": None,
            "human_effective_output": None,
            "human_provenance_ref": None,
            "issues": ("provider-error",),
            "ledger_refs": ("charged-attempt",),
        }
    )
    assert error.ledger_refs == ("charged-attempt",)
    validate_expected_predictions(("case:1", "case:2"), (error,))  # missing case remains expected
    for outputs in ((error, error), (error.model_copy(update={"item_id": "unrequested"}),)):
        with pytest.raises(ValueError):
            validate_expected_predictions(("case:1", "case:2"), outputs)
    wire = prediction_wire() | {
        "status": "not_run",
        "origin": "not_run",
        "model": None,
        "domain_payload": None,
        "machine_output": None,
        "human_effective_output": None,
        "human_provenance_ref": None,
    }
    assert Prediction.model_validate(wire).status == "not_run"
    with pytest.raises(ValidationError):
        Prediction.model_validate(wire | {"ledger_refs": ("fake-call",)})


def test_metric_populations_keep_frozen_eligible_answered_error_and_na_distinct():
    metric = MetricRow.model_validate(metric_wire())
    assert (metric.corpus_N, metric.eligible_N, metric.answered_N, metric.error_N) == (7, 6, 5, 1)
    undefined = metric_wire() | {
        "denominator": 0.0,
        "numerator": 0.0,
        "value": None,
        "null_reason": "zero-support",
    }
    assert MetricRow.model_validate(undefined).value is None
    for bad in (
        {"eligible_N": 8},
        {"answered_N": 7},
        {"denominator": 0.0},
        {"value": None},
        {"value": float("inf")},
        {"corpus_N": True},
    ):
        with pytest.raises(ValidationError):
            MetricRow.model_validate(metric_wire() | bad)
    never = metric_wire() | {
        "measurement_status": "not_measured",
        "evidence_origin": "not_run",
        "numerator": None,
        "denominator": None,
        "value": None,
        "null_reason": "not-run",
        "answered_N": 0,
    }
    assert MetricRow.model_validate(never).eligible_N == 6
    with pytest.raises(ValidationError):
        MetricRow.model_validate(never | {"numerator": 0.0})


def test_whole_group_resampling_policy_shape_without_fake_draw_execution():
    spec = {
        "version": "paired-group/1",
        "unit": "group_id",
        "seed": 37,
        "draws": 2000,
        "level": 0.95,
        "method": "percentile",
        "group_order": ("g1", "g2"),
        "stratum_map": {"g1": "mixed", "g2": "month2"},
        "min_support": 2,
        "min_valid_draws": 1900,
        "statistic_version": "fixture/1",
        "rng_version": "Python3.12/random",
    }
    assert ResamplingSpec.model_validate(spec).unit == "group_id"
    for bad in (
        {"unit": "skill_cell"},
        {"seed": True},
        {"draws": 100},
        {"min_valid_draws": 2001},
        {"stratum_map": {"g1": "month1"}},
        {"group_order": ("g1", "g1")},
    ):
        with pytest.raises(ValidationError):
            ResamplingSpec.model_validate(spec | bad)


def test_public_projection_safe_aggregate_and_private_canary_positive_controls():
    policy = PublicProjectionPolicy.model_validate(projection_policy())
    validate_public_projection(
        {"method": "baseline", "dataset_alias": "synthetic", "value": 0.5, "eligible_N": 6}, policy
    )
    controls = [
        {"item_id": "canary-private"},
        {"metadata": {"url": "https://example.invalid/private"}},
        {"method": "secret-organization"},
        {"dataset_alias": "private-source-id"},
        {"value": float("nan")},
        {"eligible_N": True},
        {"rawtext": "CANARY private text"},
    ]
    for row in controls:
        with pytest.raises(ValueError):
            validate_public_projection(row, policy)
    with pytest.raises(ValidationError):
        PublicProjectionPolicy.model_validate(
            projection_policy() | {"allowed_dimensions": ("item_id",)}
        )


def test_s1_minimal_view_stays_partial_until_actual_owner_enrichment():
    from rfr.shared.evalkit.models import ManifestEnrichmentResult, S1MinimalManifest

    wire = {
        "schema": 1,
        "split": "dev",
        "seed": None,
        "frozen_at": "2026-01-01T00:00:00Z",
        "items_file": "gold/dev.jsonl",
        "item_count": 2,
    }
    partial = S1MinimalManifest.model_validate(wire)
    assert partial.model_dump() == wire
    result = ManifestEnrichmentResult(
        status="needs_owner_metadata",
        canonical_manifest=None,
        missing_metadata=("actual-rows", "scorer", "groups", "checksums"),
    )
    assert result.canonical_manifest is None
    with pytest.raises(ValidationError):
        Manifest.model_validate(wire)
    for bad in (
        {"schema": True},
        {"seed": True},
        {"item_count": True},
        {"items_file": "../escape"},
    ):
        with pytest.raises(ValidationError):
            S1MinimalManifest.model_validate(wire | bad)
    with pytest.raises(ValidationError):
        ManifestEnrichmentResult(status="ready", canonical_manifest=None, missing_metadata=())


def test_not_run_human_effective_fiction_and_public_fractional_counts_reject():
    never = prediction_wire() | {
        "status": "not_run",
        "origin": "not_run",
        "domain_payload": None,
        "machine_output": None,
    }
    with pytest.raises(ValidationError):
        Prediction.model_validate(never)
    policy = PublicProjectionPolicy.model_validate(projection_policy())
    for value in (-1, 0.5, None):
        with pytest.raises(ValueError):
            validate_public_projection({"eligible_N": value}, policy)


def test_adopted_class_wire_alias_retains_private_python_attribute_and_rejects_old_key():
    metric = MetricRow.model_validate(metric_wire() | {"class": "false"})
    assert metric.class_name == "false" and metric.model_dump()["class"] == "false"
    assert "class_name" not in metric.model_dump()
    bad = metric_wire()
    bad["class_name"] = bad.pop("class")
    with pytest.raises(ValidationError):
        MetricRow.model_validate(bad)
