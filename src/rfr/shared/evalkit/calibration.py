"""Private typed score-versus-correctness arithmetic, not empirical calibration authority."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

from pydantic import TypeAdapter

from .models import OpaqueId
from .statistics import Statistic


def _score(value: object) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("finite_strict_score_required")
    return float(value)


def _identifier(value: object) -> None:
    TypeAdapter(OpaqueId, config={"strict": True}).validate_python(value)
    if not value.strip():
        raise ValueError("explicit_signal_identifier_required")


@dataclass(frozen=True)
class BinaryCalibrationPoint:
    score: float
    correct: bool
    score_kind: str
    score_version: str

    def __post_init__(self):
        _score(self.score)
        if type(self.correct) is not bool:
            raise ValueError("strict_boolean_correctness_required")
        _identifier(self.score_kind)
        _identifier(self.score_version)


@dataclass(frozen=True)
class CalibrationSpec:
    score_kind: str
    score_version: str
    bin_edges: tuple[float, ...]
    version: str

    def __post_init__(self):
        for identifier in (self.score_kind, self.score_version, self.version):
            _identifier(identifier)
        if type(self.bin_edges) is not tuple or not 2 <= len(self.bin_edges) <= 101:
            raise ValueError("fixed_one_to_onehundred_bins_required")
        for edge in self.bin_edges:
            _score(edge)
        if (
            self.bin_edges[0] != 0
            or self.bin_edges[-1] != 1
            or any(
                left >= right
                for left, right in zip(self.bin_edges[:-1], self.bin_edges[1:], strict=True)
            )
        ):
            raise ValueError("strict_fixed_zero_to_one_edges_required")


@dataclass(frozen=True)
class ReliabilityBin:
    low: float
    high: float
    support: int
    mean_score: float | None
    accuracy: float | None
    absolute_gap: float | None


@dataclass(frozen=True)
class CalibrationResult:
    brier: Statistic
    ece: Statistic
    bins: tuple[ReliabilityBin, ...]
    spec: CalibrationSpec


def binary_calibration(
    points: tuple[BinaryCalibrationPoint, ...], spec: CalibrationSpec, *, max_points: int = 100000
) -> CalibrationResult:
    """Fixed bins [low,high), final bin includes1; missing scores are NOT point0.

    The caller owns actual eligible/answered/labelled/confidence-available populations and coverage.
    Never mix kinds/versions or treat this arithmetic as source/human/threshold authority.
    """
    if type(max_points) is not int or not 1 <= max_points <= 1000000:
        raise ValueError("bounded_positive_calibration_limit_required")
    if type(points) is not tuple or len(points) > max_points:
        raise ValueError("calibration_point_shape_or_limit")
    if type(spec) is not CalibrationSpec:
        raise ValueError("explicit_calibration_spec_required")
    spec = CalibrationSpec(spec.score_kind, spec.score_version, spec.bin_edges, spec.version)
    buckets = [[] for _ in spec.bin_edges[1:]]
    squared = []
    for point in points:
        if type(point) is not BinaryCalibrationPoint:
            raise ValueError("typed_calibration_point_required")
        checked = BinaryCalibrationPoint(
            point.score, point.correct, point.score_kind, point.score_version
        )
        if (checked.score_kind, checked.score_version) != (spec.score_kind, spec.score_version):
            raise ValueError("mixed_calibration_signal_or_version")
        score = _score(checked.score)
        index = min(bisect_right(spec.bin_edges, score) - 1, len(buckets) - 1)
        buckets[index].append((score, int(checked.correct)))
        squared.append((score - int(checked.correct)) ** 2)
    bins = []
    weighted_gaps = []
    for index, bucket in enumerate(buckets):
        n = len(bucket)
        mean = math.fsum(score for score, _ in bucket) / n if n else None
        accuracy = sum(correct for _, correct in bucket) / n if n else None
        gap = abs(mean - accuracy) if n else None
        bins.append(
            ReliabilityBin(
                float(spec.bin_edges[index]),
                float(spec.bin_edges[index + 1]),
                n,
                mean,
                accuracy,
                gap,
            )
        )
        if n:
            weighted_gaps.append(n * gap)
    n = len(points)
    brier = (
        Statistic(math.fsum(squared) / n, n)
        if n
        else Statistic(None, 0, "zero_calibration_support")
    )
    ece = (
        Statistic(math.fsum(weighted_gaps) / n, n)
        if n
        else Statistic(None, 0, "zero_calibration_support")
    )
    return CalibrationResult(brier, ece, tuple(bins), spec)
