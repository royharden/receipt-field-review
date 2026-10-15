"""Trusted literal raw status binding; no private consumer schema, Gold or model effects."""

from dataclasses import replace

import pytest
from test_corpus import fixture
from test_reporting import spec
from test_runner import Adapter, H, Runner, lookup

from rfr.shared.evalkit.axis_status import (
    AxisStatus,
    AxisStatusBinding,
    prediction_digest,
    raw_machine_digest,
)
from rfr.shared.evalkit.corpus import FrozenCorpusError
from rfr.shared.evalkit.models import Outcome
from rfr.shared.evalkit.reporting import metric_row
from rfr.shared.evalkit.runner import MethodConfig, SourceView, compare
from rfr.shared.evalkit.statistics import accuracy, typed_equal

FIELDS = ("ok-field", "abstained-field", "error-field", "blocked-field")
STATUSES = ("ok", "abstained", "provider_error", "blocked")


class MultiRunner(Runner):
    def predict(self, public):
        prediction = super().predict(public)
        body = {
            "fields": {
                field: {
                    "status": status,
                    "value": public.public_payload["observed"] if status == "ok" else None,
                }
                for field, status in zip(FIELDS, STATUSES, strict=True)
            }
        }
        self.last = prediction.model_copy(update={"domain_payload": body, "machine_output": body})
        return self.last


class MultiAdapter(Adapter):
    def validate_prediction(self, prediction):
        assert prediction.domain_payload == prediction.machine_output
        assert set(prediction.machine_output) == {"fields"}
        assert set(prediction.machine_output["fields"]) == set(FIELDS)

    def to_outcomes(self, prediction, gold, policy):
        rows = []
        for field in FIELDS:
            raw = prediction.machine_output["fields"][field] if prediction.status == "ok" else None
            status = raw["status"] if raw else prediction.status
            value = raw["value"] if raw else None
            rows.append(
                Outcome(
                    item_id=gold.item_id,
                    group_id=gold.group_id,
                    dataset=gold.dataset,
                    split=gold.split,
                    method=prediction.method,
                    field=field,
                    **{"class": None},
                    eligibility="eligible",
                    status=status,
                    correct=typed_equal(value, gold.label_payload.payload["target"])
                    if status == "ok"
                    else None,
                    predicted=value,
                    expected=gold.label_payload.payload["target"],
                    human_touched_prediction=prediction.human_effective_output is not None,
                    evidence_origin=prediction.origin,
                    issues=(),
                    ledger_refs=prediction.ledger_refs,
                )
            )
        return tuple(rows)


class TrustedLiteralPort:
    """Expected4 axes are declared independently of response success keys; not a real S10 port."""

    def __init__(self):
        self.calls = 0

    def bind(self, prediction):
        self.calls += 1
        assert prediction.status == "ok" and prediction.domain_payload == prediction.machine_output
        fields = prediction.machine_output["fields"]
        assert set(fields) == set(FIELDS)
        return AxisStatusBinding(
            prediction_digest(prediction),
            raw_machine_digest(prediction),
            tuple(AxisStatus(field, None, fields[field]["status"]) for field in FIELDS),
        )


def run(tmp_path, *, port=None, runner=None, adapter=None, source=lookup):
    rows, manifest, _ = fixture(tmp_path)
    return compare(
        {"baseline": MethodConfig("fixture/1", H, "synthetic", runner or MultiRunner())},
        manifest,
        "dev",
        rows,
        adapter or MultiAdapter(),
        None,
        source,
        axis_status_port=port,
    )


def test_simultaneous_field_statuses_preserve_posts_raw_outputs_and_distinct_axis_denominators(
    tmp_path,
):
    port = TrustedLiteralPort()
    result = run(tmp_path, port=port)
    method = result.methods["baseline"]
    assert result.frozen_item_ids == ("case:0", "case:1") and len(method.outcomes) == 8
    assert port.calls == 2 and len(method.actual_predictions) == 2 and method.calls_observed is None
    assert all(p.status == "ok" and p.origin == "synthetic" for p in method.actual_predictions)
    reports = {
        field: metric_row(
            tuple(o for o in method.outcomes if o.field == field),
            result.frozen_item_ids,
            spec(),
            accuracy,
            method="baseline",
            dataset_alias="synthetic",
            split="dev",
            config_ref="fixture/1",
            field=field,
        )
        for field in FIELDS
    }
    assert reports["ok-field"].answered_N == 2 and reports["ok-field"].value == 1.0
    assert (
        reports["abstained-field"].abstention_N == 2 and reports["abstained-field"].answered_N == 0
    )
    assert reports["error-field"].error_N == 2 and reports["error-field"].eligible_N == 2
    assert reports["blocked-field"].abstention_N == 2


def test_default_singlefield_status_guard_remains_without_optional_port(tmp_path):
    with pytest.raises(FrozenCorpusError, match="adapter_status_mismatch"):
        run(tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        "prediction-hash",
        "raw-hash",
        "missing",
        "extra",
        "duplicate",
        "not-run",
        "wrong-status",
        "wrong-class",
        "invalid-field",
    ],
)
def test_forged_or_incomplete_binding_refuses_before_scoring(tmp_path, change):
    class Forged(TrustedLiteralPort):
        def bind(self, prediction):
            binding = super().bind(prediction)
            if change == "prediction-hash":
                return replace(binding, prediction_sha256="b" * 64)
            if change == "raw-hash":
                return replace(binding, raw_machine_sha256="b" * 64)
            if change == "missing":
                return replace(binding, axes=binding.axes[:-1])
            if change == "extra":
                return replace(binding, axes=(*binding.axes, AxisStatus("foreign", None, "ok")))
            if change == "duplicate":
                return replace(binding, axes=(*binding.axes, binding.axes[0]))
            if change == "not-run":
                return replace(
                    binding, axes=(AxisStatus("ok-field", None, "not_run"), *binding.axes[1:])
                )
            if change == "wrong-status":
                return replace(
                    binding, axes=(AxisStatus("ok-field", None, "abstained"), *binding.axes[1:])
                )
            if change == "wrong-class":
                return replace(
                    binding, axes=(AxisStatus("ok-field", "foreign", "ok"), *binding.axes[1:])
                )
            return replace(binding, axes=(AxisStatus(1, None, "ok"), *binding.axes[1:]))

    with pytest.raises(FrozenCorpusError):
        run(tmp_path, port=Forged())


@pytest.mark.parametrize("branch", ["stale", "unavailable", "provider_error", "invalid", "not_run"])
def test_whole_failure_source_or_notrun_never_invokes_field_binding_or_promotes_success(
    tmp_path, branch
):
    class NoPort:
        def bind(self, prediction):
            raise AssertionError("binding called on whole failure")

    class Invalid(MultiAdapter):
        def validate_prediction(self, prediction):
            raise ValueError("invalid envelope")

    rows, manifest, _ = fixture(tmp_path)
    runner = (
        None
        if branch == "not_run"
        else MultiRunner("error" if branch == "provider_error" else "normal")
    )

    def source(gold):
        return SourceView(branch, None, {}) if branch in ("stale", "unavailable") else lookup(gold)

    result = compare(
        {"baseline": MethodConfig("fixture/1", H, "synthetic", runner)},
        manifest,
        "dev",
        rows,
        Invalid() if branch == "invalid" else MultiAdapter(),
        None,
        source,
        axis_status_port=NoPort(),
    )
    method = result.methods["baseline"]
    if branch == "not_run":
        assert method.status == "not_run" and method.actual_predictions == method.outcomes == ()
    else:
        assert len(method.outcomes) == 8 and all(o.status == branch for o in method.outcomes)


def test_binding_port_mutation_is_rejected_and_actual_raw_response_is_unchanged(tmp_path):
    class Mutator(TrustedLiteralPort):
        def bind(self, prediction):
            binding = super().bind(prediction)
            prediction.machine_output["fields"]["error-field"]["status"] = "ok"
            return binding

    runner = MultiRunner()
    with pytest.raises(FrozenCorpusError, match="invalid_axis_status_binding"):
        run(tmp_path, port=Mutator(), runner=runner)
    assert runner.last.machine_output["fields"]["error-field"]["status"] == "provider_error"


def test_validator_and_mapper_only_receive_copies_of_retained_actual_prediction(tmp_path):
    class Mutating(MultiAdapter):
        def validate_prediction(self, prediction):
            super().validate_prediction(prediction)
            prediction.machine_output["fields"]["ok-field"]["value"] = "private-mutator"

        def to_outcomes(self, prediction, gold, policy):
            rows = super().to_outcomes(prediction, gold, policy)
            prediction.machine_output["fields"]["ok-field"]["value"] = "private-mutator"
            return rows

    result = run(tmp_path, port=TrustedLiteralPort(), adapter=Mutating())
    assert [
        p.machine_output["fields"]["ok-field"]["value"]
        for p in result.methods["baseline"].actual_predictions
    ] == [False, True]


@pytest.mark.parametrize(
    "change",
    [{"evidence_origin": "live"}, {"human_touched_prediction": True}],
    ids=["origin-promotion", "human-promotion"],
)
def test_optional_status_port_does_not_weaken_original_provenance_guards(tmp_path, change):
    class Relabel(MultiAdapter):
        def to_outcomes(self, prediction, gold, policy):
            return tuple(
                row.model_copy(update=change)
                for row in super().to_outcomes(prediction, gold, policy)
            )

    with pytest.raises(FrozenCorpusError, match="adapter_provenance_mismatch"):
        run(tmp_path, port=TrustedLiteralPort(), adapter=Relabel())


@pytest.mark.parametrize(
    "change",
    [{"config_sha256": "b" * 64}, {"item_id": "foreign-post"}],
    ids=["config", "post-identity"],
)
def test_actual_response_identity_refuses_before_axis_binding(tmp_path, change):
    class Wrong(MultiRunner):
        def predict(self, public):
            return super().predict(public).model_copy(update=change)

    port = TrustedLiteralPort()
    with pytest.raises(FrozenCorpusError, match="prediction_identity_changed"):
        run(tmp_path, port=port, runner=Wrong())
    assert port.calls == 0


def test_complete_valid_domain_packet_preserves_actual_partial_controller_and_child_statuses(
    tmp_path,
):
    class PartialRunner(MultiRunner):
        def predict(self, public):
            response = super().predict(public)
            body = response.machine_output | {
                "original_controller_status": "partial",
                "operation_status": "partial",
            }
            return response.model_copy(
                update={
                    "machine_output": body,
                    "domain_payload": body,
                    "issues": ("partial_operation",),
                }
            )

    class PartialAdapter(MultiAdapter):
        def validate_prediction(self, prediction):
            assert set(prediction.machine_output) == {
                "fields",
                "original_controller_status",
                "operation_status",
            }
            assert prediction.machine_output == prediction.domain_payload
            assert set(prediction.machine_output["fields"]) == set(FIELDS)
            assert prediction.machine_output["original_controller_status"] == "partial"

    result = run(
        tmp_path, port=TrustedLiteralPort(), runner=PartialRunner(), adapter=PartialAdapter()
    )
    method = result.methods["baseline"]
    assert method.status == "executed"  # Dispatch metadata, not complete-success status.
    assert len(method.outcomes) == 8 and sum(o.status == "ok" for o in method.outcomes) == 2
    assert all(
        p.status == "ok"
        and p.domain_payload["original_controller_status"] == "partial"
        and p.machine_output["operation_status"] == "partial"
        and p.issues == ("partial_operation",)
        and p.ledger_refs == ("measured-attempt",)
        for p in method.actual_predictions
    )
    # Whole-method report derives actual operation state, not the canonical envelope's ok tag.
    reported_operation_statuses = tuple(
        p.domain_payload["operation_status"] for p in method.actual_predictions
    )
    assert reported_operation_statuses == ("partial", "partial")
