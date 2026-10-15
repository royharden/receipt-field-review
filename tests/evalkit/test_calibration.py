"""Tiny arithmetic controls only, not data fitting, threshold admission or model quality."""

import pytest

from rfr.shared.evalkit.calibration import (
    BinaryCalibrationPoint,
    CalibrationSpec,
    binary_calibration,
)


def spec(edges=None, **changes):
    return CalibrationSpec(
        **(
            {
                "score_kind": "native_probability",
                "score_version": "literal/1",
                "bin_edges": tuple(i / 10 for i in range(11)) if edges is None else edges,
                "version": "fixed-bins/1",
            }
            | changes
        )
    )


def point(score, correct, **changes):
    return BinaryCalibrationPoint(
        **(
            {
                "score": score,
                "correct": correct,
                "score_kind": "native_probability",
                "score_version": "literal/1",
            }
            | changes
        )
    )


def test_supplied_two_point_hand_brier_ece_and_private_signal_metadata():
    result = binary_calibration((point(0.8, True), point(0.4, False)), spec())
    assert result.brier.value == pytest.approx(0.1) and result.ece.value == pytest.approx(0.3)
    assert result.brier.support == result.ece.support == 2
    assert sum(bin.support for bin in result.bins) == 2
    assert result.spec.score_kind == "native_probability"


def test_exact_edges_enter_right_bin_and_final_one_is_inclusive():
    result = binary_calibration(
        (point(0, False), point(0.5, True), point(1, True)), spec((0.0, 0.5, 1.0))
    )
    assert tuple(bin.support for bin in result.bins) == (1, 2)
    assert result.bins[0].mean_score == result.bins[0].accuracy == 0
    assert result.bins[1].mean_score == 0.75 and result.bins[1].accuracy == 1
    assert result.ece.value == pytest.approx(1 / 6)


def test_same_bin_means_and_bin_support_weights_are_not_unweighted_average():
    points = (point(0.1, False), point(0.2, True), point(0.3, True), point(0.9, False))
    result = binary_calibration(points, spec((0.0, 0.5, 1.0)))
    assert result.bins[0].support == 3 and result.bins[0].accuracy == pytest.approx(2 / 3)
    assert result.bins[0].mean_score == pytest.approx(0.2)
    assert result.ece.value == pytest.approx((3 * abs(0.2 - 2 / 3) + 0.9) / 4)


def test_empty_support_and_empty_bins_are_explicit_null_not_perfect_or_zero():
    result = binary_calibration((), spec())
    assert result.brier.value is result.ece.value is None
    assert result.brier.support == 0 and result.brier.null_reason == "zero_calibration_support"
    assert all(
        bin.support == 0 and bin.mean_score is bin.accuracy is bin.absolute_gap is None
        for bin in result.bins
    )
    partial = binary_calibration((point(0.8, True),), spec())
    assert sum(bin.support == 0 for bin in partial.bins) == 9


@pytest.mark.parametrize("score", [True, "0.8", float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_or_coerced_score_refuses_instead_of_clipping(score):
    with pytest.raises(ValueError):
        point(score, True)


@pytest.mark.parametrize("correct", [0, 1, None, "true"])
def test_correctness_is_strict_bool_not_arbitrary_class_label(correct):
    with pytest.raises(ValueError):
        point(0.8, correct)


@pytest.mark.parametrize(
    "edges",
    [
        (),
        (0.0, 0.5, 0.5, 1.0),
        (0.0, 0.7, 0.5, 1.0),
        (0.1, 1.0),
        (0.0, 0.9),
        (0.0, float("nan"), 1.0),
        (False, 1.0),
        tuple(i / 101 for i in range(102)),
    ],
    ids=[
        "empty",
        "duplicate",
        "nonmonotone",
        "missing-zero",
        "missing-one",
        "nan",
        "bool",
        "over100bins",
    ],
)
def test_invalid_frozen_edges_refuse_without_adaptive_repair(edges):
    with pytest.raises(ValueError):
        spec(edges)


@pytest.mark.parametrize(
    "change", [{"score_kind": "self_reported_confidence"}, {"score_version": "another/2"}]
)
def test_mixed_signal_or_version_requires_separate_report_not_silent_pooling(change):
    with pytest.raises(ValueError, match="mixed_calibration"):
        binary_calibration((point(0.8, True), point(0.4, False, **change)), spec())


def test_typed_bounded_input_and_frozen_spec_do_not_impute_missing_points():
    with pytest.raises(ValueError):
        binary_calibration([point(0.8, True)], spec())
    with pytest.raises(ValueError):
        binary_calibration((point(0.8, True), point(0.4, False)), spec(), max_points=1)
    with pytest.raises(ValueError):
        binary_calibration((), spec(), max_points=True)
    with pytest.raises(ValueError):
        binary_calibration((None,), spec())
    assert binary_calibration((point(0.8, True),), spec()).brier.support == 1
