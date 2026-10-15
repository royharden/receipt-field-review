"""Generic candidate-bound extraction through trusted injected ports. No provider implementation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import TypeAdapter

from ..docio.models import OpaqueId
from .interfaces import DomainCheck, JudgmentPort
from .models import (
    Candidate,
    CheckIssue,
    EvidenceSource,
    FieldSpec,
    FieldValue,
    JudgmentDistribution,
    ScoreComponents,
)


class ExtractionError(ValueError):
    """Closed refusal codes, without candidate text, private paths or provider exception strings."""


@dataclass(frozen=True)
class EvidenceAssessment:
    """Result from an actual trusted consumer resolver, not evidence authenticated by this shape."""

    source: EvidenceSource | None
    origin: Literal["measured_ocr", "native_text", "model_claimed", "none"]
    word_confidences: tuple[float | None, ...]
    policy_id: str
    independently_anchored: bool = False


class EvidenceAuthority(Protocol):
    def assess(self, candidate: Candidate) -> EvidenceAssessment: ...


@dataclass(frozen=True)
class ThresholdPolicy:
    version: str = "uncalibrated/1"
    threshold: float | None = None
    calibrated: bool = False
    stratum_known: bool = False


UNCALIBRATED_POLICY = ThresholdPolicy()


@dataclass(frozen=True)
class JudgmentBindings:
    selection_question_id: str
    none_answer_id: str
    verifier_answers: Mapping[str, tuple[str, str]]
    expected_origin: Literal["native_model", "synthetic", "replay"]


def _id(value: object) -> None:
    try:
        TypeAdapter(OpaqueId, config={"strict": True}).validate_python(value)
    except ValueError:
        raise ExtractionError("invalid_binding_id") from None


def _probability(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ExtractionError("invalid_probability")
    return float(value)


def quality_multiplier(assessment: EvidenceAssessment) -> float:
    """Native text uses a named structural policy, never manufactured OCR confidence."""
    if not isinstance(assessment, EvidenceAssessment):
        raise ExtractionError("evidence_assessment_required")
    _id(assessment.policy_id)
    if type(assessment.independently_anchored) is not bool:
        raise ExtractionError("invalid_anchor_flag")
    if type(assessment.word_confidences) is not tuple:
        raise ExtractionError("explicit_word_confidences_required")
    for confidence in assessment.word_confidences:
        if confidence is not None:
            _probability(confidence)
    if assessment.origin == "measured_ocr":
        return (
            min(assessment.word_confidences)
            if assessment.word_confidences
            and all(c is not None for c in assessment.word_confidences)
            else 0.0
        )
    if assessment.origin == "native_text":
        if any(c is not None for c in assessment.word_confidences):
            raise ExtractionError("native_text_cannot_invent_ocr_confidence")
        return 1.0
    if assessment.origin in ("model_claimed", "none"):
        return 0.0
    raise ExtractionError("unsupported_quality_origin")


def _distribution(
    value: object, question: str, answers: set[str], origin: str
) -> JudgmentDistribution:
    if not isinstance(value, JudgmentDistribution):
        raise ExtractionError("invalid_judgment_distribution")
    try:
        value = JudgmentDistribution.model_validate_json(value.model_dump_json())
    except ValueError:
        raise ExtractionError("invalid_judgment_distribution") from None
    if value.question_id != question or value.origin != origin:
        raise ExtractionError("judgment_question_or_origin_mismatch")
    if set(value.probabilities) != answers:
        raise ExtractionError("judgment_answer_set_mismatch")
    return value


def _value(
    spec: FieldSpec,
    method: str,
    policy: ThresholdPolicy,
    *,
    proposal=None,
    source=None,
    confidence=None,
    selector=None,
    verifier=None,
    quality=None,
    quality_policy=None,
    status="needs_review",
    hard_flags=(),
    issues=(),
) -> FieldValue:
    return FieldValue(
        field_id=spec.field_id,
        value=proposal if status == "proposed" else None,
        confidence=confidence,
        source=source,
        method=method,
        status=status,
        proposal=proposal,
        human_provenance_ref=None,
        hard_flags=hard_flags,
        issues=issues,
        components=ScoreComponents(
            selector_probability=selector,
            verifier_probability=verifier,
            native_quality_multiplier=quality,
            native_quality_policy=quality_policy,
        ),
        score_version="min-selector-quality-verifier/1",
        threshold_version=policy.version,
    )


def extract_field(
    spec: FieldSpec,
    candidates: tuple[Candidate, ...],
    evidence_authority: EvidenceAuthority,
    bindings: JudgmentBindings,
    *,
    mode: Literal["B0", "J1", "V2"],
    policy: ThresholdPolicy = UNCALIBRATED_POLICY,
    selector: JudgmentPort | None = None,
    verifiers: Mapping[str, JudgmentPort] | None = None,
    chosen_candidate_id: str | None = None,
    b0_prior: float | None = None,
    hard_flags: tuple[str, ...] = (),
) -> FieldValue:
    """Preflight bindings before judgment. Caller owns funded full-fanout transport and provenance.

    A binary verifier port is preconfigured per expected question, so independent hazards are not
    forced into one exclusive distribution. This engine installs/calls no SDK and supplies no budget
    authority, source resolver, calibration proof or screen. Injected ports enforce those gates.
    """
    if mode not in ("B0", "J1", "V2") or not isinstance(spec, FieldSpec):
        raise ExtractionError("invalid_extraction_mode_or_spec")
    if (
        not isinstance(policy, ThresholdPolicy)
        or type(policy.calibrated) is not bool
        or type(policy.stratum_known) is not bool
    ):
        raise ExtractionError("invalid_threshold_policy")
    _id(policy.version)
    if policy.threshold is not None:
        _probability(policy.threshold)
    if policy.calibrated and policy.threshold is None:
        raise ExtractionError("calibrated_threshold_missing")
    if type(candidates) is not tuple or len(candidates) > 63:
        raise ExtractionError("candidate_limit_or_shape")
    if not isinstance(bindings, JudgmentBindings) or bindings.expected_origin not in (
        "native_model",
        "synthetic",
        "replay",
    ):
        raise ExtractionError("invalid_judgment_bindings")
    _id(bindings.selection_question_id)
    _id(bindings.none_answer_id)
    verifier_ports = {} if verifiers is None else dict(verifiers)
    answer_bindings = dict(bindings.verifier_answers)
    if set(verifier_ports) != set(answer_bindings) or len(answer_bindings) > 8:
        raise ExtractionError("verifier_binding_set_mismatch")
    for question, answers in answer_bindings.items():
        _id(question)
        if type(answers) is not tuple or len(answers) != 2 or answers[0] == answers[1]:
            raise ExtractionError("binary_verifier_answers_required")
        for answer in answers:
            _id(answer)
    if bindings.selection_question_id in answer_bindings:
        raise ExtractionError("duplicate_question_binding")
    if type(hard_flags) is not tuple or len(set(hard_flags)) != len(hard_flags):
        raise ExtractionError("invalid_hard_flags")
    for flag in hard_flags:
        _id(flag)
    by_id = {}
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ExtractionError("candidate_required")
        candidate = Candidate.model_validate_json(candidate.model_dump_json())
        if (
            candidate.field_id != spec.field_id
            or candidate.candidate_id in by_id
            or candidate.candidate_id == bindings.none_answer_id
        ):
            raise ExtractionError("duplicate_or_foreign_candidate")
        by_id[candidate.candidate_id] = candidate
    if not by_id:
        return _value(
            spec,
            mode,
            policy,
            status="needs_review" if hard_flags else "abstained",
            hard_flags=hard_flags,
            issues=("no_candidates",),
        )
    assessments = {}
    for candidate_id, candidate in by_id.items():
        try:
            supplied = Candidate.model_validate_json(candidate.model_dump_json())
            assessment = evidence_authority.assess(supplied)
            quality = quality_multiplier(assessment)
            if assessment.source is None or assessment.source not in candidate.sources:
                raise ExtractionError("evidence_source_not_candidate_bound")
            assessments[candidate_id] = (assessment, quality)
        except Exception:
            return _value(
                spec,
                mode,
                policy,
                hard_flags=tuple(dict.fromkeys((*hard_flags, "unverified_source"))),
                issues=("evidence_unavailable",),
            )
    selection_probability = None
    if mode == "J1":
        if selector is None or chosen_candidate_id is not None or b0_prior is not None:
            raise ExtractionError("J1_selector_required_without_prior_override")
        try:
            raw = selector.select(
                FieldSpec.model_validate_json(spec.model_dump_json()),
                tuple(Candidate.model_validate_json(c.model_dump_json()) for c in by_id.values()),
            )
        except Exception:
            return _value(
                spec, mode, policy, hard_flags=hard_flags, issues=("selector_unavailable",)
            )
        result = _distribution(
            raw,
            bindings.selection_question_id,
            set(by_id) | {bindings.none_answer_id},
            bindings.expected_origin,
        )
        maximum = max(result.probabilities.values())
        winners = [key for key, p in result.probabilities.items() if p == maximum]
        if len(winners) != 1 or winners[0] == bindings.none_answer_id:
            return _value(
                spec,
                mode,
                policy,
                status="needs_review" if hard_flags else "abstained",
                selector=maximum,
                hard_flags=hard_flags,
                issues=("selection_abstained",),
            )
        chosen_candidate_id = winners[0]
        selection_probability = maximum
    else:
        if selector is not None:
            raise ExtractionError("unexpected_selector_for_fixed_prior_mode")
        if chosen_candidate_id is None:
            return _value(
                spec,
                mode,
                policy,
                status="needs_review" if hard_flags else "abstained",
                hard_flags=hard_flags,
                issues=("selection_abstained",),
            )
        if mode == "B0":
            if type(b0_prior) not in (float, int) or b0_prior not in (0.0, 0.3, 0.6, 0.9):
                raise ExtractionError("undeclared_B0_prior")
            selection_probability = float(b0_prior)
        elif b0_prior is not None:
            raise ExtractionError("V2_prior_is_not_caller_calibrated")
    if chosen_candidate_id not in by_id:
        raise ExtractionError("unrequested_candidate_reply")
    candidate = by_id[chosen_candidate_id]
    assessment, quality = assessments[chosen_candidate_id]
    if mode == "V2":
        if not assessment.independently_anchored or assessment.origin != "measured_ocr":
            return _value(
                spec,
                mode,
                policy,
                proposal=candidate.normalized,
                source=assessment.source,
                quality=quality,
                quality_policy=assessment.policy_id,
                hard_flags=tuple(dict.fromkeys((*hard_flags, "unanchored_vision"))),
                issues=("V2_requires_independent_OCR_anchor",),
            )
        selection_probability = 0.5
    violations = []
    for question, answers in answer_bindings.items():
        try:
            raw = verifier_ports[question].verify(
                FieldSpec.model_validate_json(spec.model_dump_json()),
                Candidate.model_validate_json(candidate.model_dump_json()),
            )
        except Exception:
            return _value(
                spec,
                mode,
                policy,
                proposal=candidate.normalized,
                source=assessment.source,
                selector=selection_probability,
                quality=quality,
                quality_policy=assessment.policy_id,
                hard_flags=hard_flags,
                issues=("verifier_unavailable",),
            )
        distribution = _distribution(raw, question, set(answers), bindings.expected_origin)
        violations.append(distribution.probabilities[answers[0]])
    violation = max(violations) if violations else 0.0
    score = min(selection_probability * quality, 1.0 - violation)
    issues = []
    if not violations:
        issues.append("verifier_not_run")
    if not policy.calibrated:
        issues.append("uncalibrated")
    if not policy.stratum_known:
        issues.append("unknown_stratum")
    if candidate.normalized is None:
        issues.append("printed_absence_requires_domain_proof")
    accepted = (
        not hard_flags
        and policy.calibrated
        and policy.stratum_known
        and score >= policy.threshold
        and quality > 0
        and candidate.normalized is not None
    )
    if not accepted and policy.threshold is not None and score < policy.threshold:
        issues.append("below_threshold")
    return _value(
        spec,
        mode,
        policy,
        proposal=candidate.normalized,
        source=assessment.source,
        confidence=score,
        selector=selection_probability,
        verifier=violation if violations else None,
        quality=quality,
        quality_policy=assessment.policy_id,
        status="proposed" if accepted else "needs_review",
        hard_flags=hard_flags,
        issues=tuple(issues),
    )


def apply_domain_checks(
    fields: tuple[FieldValue, ...], checker: DomainCheck
) -> tuple[FieldValue, ...]:
    """Machine proposal checks only. Human-effective projections require their own ruling policy."""
    ids = tuple(f.field_id for f in fields)
    if len(set(ids)) != len(ids) or any(f.status == "human_effective" for f in fields):
        raise ExtractionError("duplicate_or_human_effective_machine_fields")
    try:
        issues = checker.check(
            tuple(FieldValue.model_validate_json(f.model_dump_json()) for f in fields)
        )
    except Exception:
        issues = (
            CheckIssue(issue_id="domain_check_unavailable", severity="review", field_ids=ids),
        )
    if type(issues) is not tuple:
        raise ExtractionError("domain_check_tuple_required")
    validated = []
    for issue in issues:
        if not isinstance(issue, CheckIssue):
            raise ExtractionError("check_issue_required")
        issue = CheckIssue.model_validate_json(issue.model_dump_json())
        if not set(issue.field_ids) <= set(ids):
            raise ExtractionError("foreign_check_field")
        validated.append(issue)
    result = []
    for field in fields:
        relevant = [i for i in validated if not i.field_ids or field.field_id in i.field_ids]
        review = any(i.severity in ("review", "hard_failure") for i in relevant)
        updates = {
            "issues": tuple(dict.fromkeys((*field.issues, *(i.issue_id for i in relevant)))),
            "hard_flags": tuple(
                dict.fromkeys(
                    (
                        *field.hard_flags,
                        *(i.issue_id for i in relevant if i.severity == "hard_failure"),
                    )
                )
            ),
        }
        if review:
            updates |= {"status": "needs_review", "value": None}
        result.append(FieldValue.model_validate(field.model_dump() | updates))
    return tuple(result)
