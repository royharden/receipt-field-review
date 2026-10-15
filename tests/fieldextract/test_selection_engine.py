"""Hand score/routing tables and adversarial injected-port controls, without real model results."""

from dataclasses import replace

import pytest

from rfr.shared.fieldextract.engine import (
    EvidenceAssessment,
    ExtractionError,
    JudgmentBindings,
    ThresholdPolicy,
    apply_domain_checks,
    extract_field,
    quality_multiplier,
)
from rfr.shared.fieldextract.models import (
    Candidate,
    CheckIssue,
    ExtensionEvidence,
    FieldSpec,
    JudgmentDistribution,
)


def spec(kind="boolean"):
    return FieldSpec(
        field_id="battery.present",
        kind=kind,
        required=True,
        definition="Nonreceipt synthetic battery-presence control",
        boundary_cases=("literal false",),
        generator="literal-control/1",
    )


def candidates(value=False):
    source = ExtensionEvidence(
        kind="extension",
        profile="synthetic-literal/1",
        evidence_id="public-hand-occurrence",
        payload={"literal": value},
    )
    return (
        Candidate(
            candidate_id="candidate:0",
            field_id="battery.present",
            raw=value,
            normalized=value,
            sources=(source,),
        ),
    )


def bindings(verifiers=False):
    return JudgmentBindings(
        "select:fixture",
        "none",
        {"hallucination": ("violation", "clear"), "off-target": ("violation", "clear")}
        if verifiers
        else {},
        "synthetic",
    )


def admitted(threshold=0.7, **changes):
    return replace(ThresholdPolicy("synthetic-routing-control/1", threshold, True, True), **changes)


class Evidence:
    def __init__(
        self, origin="measured_ocr", confidences=(0.9,), anchor=False, fail=False, foreign=False
    ):
        self.origin = origin
        self.confidences = confidences
        self.anchor = anchor
        self.fail = fail
        self.foreign = foreign
        self.calls = 0

    def assess(self, candidate):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private source CANARY")
        source = candidate.sources[0]
        if self.foreign:
            source = source.model_copy(update={"evidence_id": "foreign"})
        return EvidenceAssessment(
            source, self.origin, self.confidences, "synthetic-quality-control/1", self.anchor
        )


class Judge:
    def __init__(
        self, p=0.8, v=0.1, question="select:fixture", answers=None, origin="synthetic", error=False
    ):
        self.p = p
        self.v = v
        self.question = question
        self.answers = answers
        self.origin = origin
        self.error = error
        self.select_calls = self.verify_calls = 0

    def select(self, spec, options):
        self.select_calls += 1
        if self.error:
            raise RuntimeError("private provider CANARY")
        return JudgmentDistribution(
            question_id=self.question,
            origin=self.origin,
            probabilities=self.answers
            if self.answers is not None
            else {"candidate:0": self.p, "none": 1 - self.p},
        )

    def verify(self, spec, candidate):
        self.verify_calls += 1
        if self.error:
            raise RuntimeError("private provider CANARY")
        return JudgmentDistribution(
            question_id=self.question,
            origin=self.origin,
            probabilities={"violation": self.v, "clear": 1 - self.v},
        )


def test_exact_min_score_and_independent_binary_max_violation_not_exclusive_hazards():
    first = Judge(question="hallucination", v=0.1)
    second = Judge(question="off-target", v=0.8)
    result = extract_field(
        spec(),
        candidates(),
        Evidence(),
        bindings(True),
        mode="J1",
        policy=admitted(0.2),
        selector=Judge(),
        verifiers={"hallucination": first, "off-target": second},
    )
    assert result.confidence == pytest.approx(0.2)
    assert (
        result.components.selector_probability == 0.8
        and result.components.native_quality_multiplier == 0.9
    )
    assert result.components.verifier_probability == 0.8
    assert result.proposal is False and result.human_provenance_ref is None
    assert first.verify_calls == second.verify_calls == 1


@pytest.mark.parametrize(
    "origin,confidences,q",
    [
        ("measured_ocr", (0.9, 0.4), 0.4),
        ("measured_ocr", (0.9, None), 0.0),
        ("measured_ocr", (), 0.0),
        ("native_text", (None,), 1.0),
        ("model_claimed", (), 0.0),
        ("none", (), 0.0),
    ],
    ids=[
        "minimum-word",
        "missing-word",
        "no-words",
        "native-policy",
        "asserted-box",
        "no-geometry",
    ],
)
def test_quality_policy_table_does_not_invent_ocr_confidence(origin, confidences, q):
    quality = Evidence(origin, confidences).assess(candidates()[0])
    assert quality_multiplier(quality) == q
    result = extract_field(
        spec(),
        candidates(),
        Evidence(origin, confidences),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=admitted(),
    )
    assert result.confidence == pytest.approx(0.9 * q)
    assert result.components.verifier_probability is None
    assert (result.status == "proposed") == (q == 1.0)
    if origin == "native_text":
        assert quality.word_confidences == (None,)


@pytest.mark.parametrize(
    "policy",
    [
        ThresholdPolicy(),
        admitted(calibrated=False),
        admitted(stratum_known=False),
        admitted(0.95),
    ],
    ids=["default", "uncalibrated", "unknown-stratum", "below-threshold"],
)
def test_high_diagnostic_score_never_overrides_review_gate(policy):
    result = extract_field(
        spec(),
        candidates(),
        Evidence("native_text", (None,)),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=policy,
    )
    assert result.confidence == 0.9 and result.value is None and result.proposal is False
    assert result.status == "needs_review" and result.human_provenance_ref is None


def test_false_proposal_remains_false_at_inclusive_threshold_and_hard_gate_clears_visible_value():
    result = extract_field(
        spec(),
        candidates(),
        Evidence("native_text", (None,)),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=admitted(0.9),
    )
    assert result.value is False and result.status == "proposed"
    hard = extract_field(
        spec(),
        candidates(),
        Evidence("native_text", (None,)),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=admitted(0.9),
        hard_flags=("source_conflict",),
    )
    assert hard.value is None and hard.proposal is False and hard.status == "needs_review"
    assert hard.confidence == 0.9


def test_none_answer_tie_or_empty_bank_abstains_and_never_asserts_printed_absence():
    for probability in (0.1, 0.5):
        result = extract_field(
            spec(),
            candidates(),
            Evidence(),
            bindings(),
            mode="J1",
            selector=Judge(p=probability),
            policy=admitted(),
        )
        assert result.status == "abstained" and result.value is result.proposal is None
        assert result.confidence is None
    judge = Judge()
    result = extract_field(spec(), (), Evidence(), bindings(), mode="J1", selector=judge)
    assert result.status == "abstained" and judge.select_calls == 0
    null = extract_field(
        spec(),
        candidates(None),
        Evidence("native_text", (None,)),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=admitted(),
    )
    assert null.status == "needs_review" and "printed_absence_requires_domain_proof" in null.issues


@pytest.mark.parametrize(
    "change",
    [
        {"question": "foreign-question"},
        {"origin": "native_model"},
        {"answers": {"foreign-candidate": 0.8, "none": 0.2}},
        {"answers": {"candidate:0": 1.0}},
    ],
    ids=["question", "origin", "foreign-option", "missing-none"],
)
def test_spoofed_response_binding_refuses_without_accepting_invented_values(change):
    with pytest.raises(ExtractionError):
        extract_field(
            spec(), candidates(), Evidence(), bindings(), mode="J1", selector=Judge(**change)
        )


def test_duplicate_foreign_reserved_or_overflow_candidates_rejected_before_any_port():
    original = candidates()[0]
    for bad in [
        (original, original),
        (original.model_copy(update={"field_id": "foreign"}),),
        (original.model_copy(update={"candidate_id": "none"}),),
        tuple(original.model_copy(update={"candidate_id": str(i)}) for i in range(64)),
    ]:
        judge = Judge()
        evidence = Evidence()
        with pytest.raises(ExtractionError):
            extract_field(spec(), bad, evidence, bindings(), mode="J1", selector=judge)
        assert judge.select_calls == evidence.calls == 0


def test_full_question_and_verifier_mapping_is_required_before_selection():
    judge = Judge()
    for ports in ({}, {"foreign": Judge()}):
        with pytest.raises(ExtractionError, match="verifier_binding_set_mismatch"):
            extract_field(
                spec(),
                candidates(),
                Evidence(),
                bindings(True),
                mode="J1",
                selector=judge,
                verifiers=ports,
            )
    assert judge.select_calls == 0


@pytest.mark.parametrize(
    "evidence",
    [
        Evidence(fail=True),
        Evidence(foreign=True),
        Evidence("native_text", (0.9,)),
        Evidence("measured_ocr", (float("nan"),)),
    ],
    ids=["source-refused", "foreign-source", "fabricated-native-confidence", "nonfinite-quality"],
)
def test_unverified_source_refuses_before_judgment_without_private_exception_text(evidence):
    judge = Judge()
    result = extract_field(spec(), candidates(), evidence, bindings(), mode="J1", selector=judge)
    assert judge.select_calls == 0 and result.status == "needs_review"
    assert result.value is None and result.confidence is None and result.source is None
    assert result.hard_flags == ("unverified_source",) and "CANARY" not in str(result)


def test_V2_fixed_prior_exists_only_after_independent_measured_OCR_anchor():
    for evidence in [
        Evidence(anchor=False),
        Evidence("model_claimed", (), anchor=True),
        Evidence("native_text", (None,), anchor=True),
    ]:
        result = extract_field(
            spec(),
            candidates(),
            evidence,
            bindings(),
            mode="V2",
            chosen_candidate_id="candidate:0",
            policy=admitted(0.1),
        )
        assert result.status == "needs_review" and result.components.selector_probability is None
        assert "unanchored_vision" in result.hard_flags
    result = extract_field(
        spec(),
        candidates(),
        Evidence(anchor=True),
        bindings(),
        mode="V2",
        chosen_candidate_id="candidate:0",
        policy=admitted(0.4),
    )
    assert result.components.selector_probability == 0.5 and result.confidence == 0.45


def test_port_exceptions_are_review_and_invalid_verifier_binding_is_refusal():
    failed = extract_field(
        spec(), candidates(), Evidence(), bindings(), mode="J1", selector=Judge(error=True)
    )
    assert failed.issues == ("selector_unavailable",) and failed.value is None
    ports = {
        "hallucination": Judge(question="hallucination", error=True),
        "off-target": Judge(question="off-target"),
    }
    failed = extract_field(
        spec(),
        candidates(),
        Evidence(),
        bindings(True),
        mode="J1",
        selector=Judge(),
        verifiers=ports,
    )
    assert failed.issues == ("verifier_unavailable",) and failed.value is None
    ports["hallucination"] = Judge(question="foreign")
    with pytest.raises(ExtractionError, match="judgment_question_or_origin_mismatch"):
        extract_field(
            spec(),
            candidates(),
            Evidence(),
            bindings(True),
            mode="J1",
            selector=Judge(),
            verifiers=ports,
        )


def test_port_cannot_mutate_bound_raw_candidate_into_invented_selected_value():
    class Mutator(Judge):
        def select(self, spec, options):
            options[0].normalized["answer"] = "forged"
            return super().select(spec, options)

    original = candidates({"answer": "original"})
    result = extract_field(
        spec("object"),
        original,
        Evidence("native_text", (None,)),
        bindings(),
        mode="J1",
        selector=Mutator(),
        policy=admitted(0.7),
    )
    assert result.value == result.proposal == {"answer": "original"}
    assert original[0].normalized == {"answer": "original"}


def test_domain_checks_preserve_proposal_enforce_hard_review_and_reject_foreign_or_human_fields():
    field = extract_field(
        spec(),
        candidates(),
        Evidence("native_text", (None,)),
        bindings(),
        mode="B0",
        chosen_candidate_id="candidate:0",
        b0_prior=0.9,
        policy=admitted(0.9),
    )

    class Checks:
        def check(self, fields):
            return (
                CheckIssue(
                    issue_id="format_violation",
                    severity="hard_failure",
                    field_ids=("battery.present",),
                ),
            )

    checked = apply_domain_checks((field,), Checks())[0]
    assert checked.status == "needs_review" and checked.value is None and checked.proposal is False
    assert checked.hard_flags == ("format_violation",)

    class Foreign:
        def check(self, fields):
            return (CheckIssue(issue_id="foreign", severity="review", field_ids=("foreign",)),)

    with pytest.raises(ExtractionError, match="foreign_check_field"):
        apply_domain_checks((field,), Foreign())
    human = field.model_copy(
        update={"status": "human_effective", "human_provenance_ref": "synthetic-only"}
    )
    with pytest.raises(ExtractionError, match="human_effective"):
        apply_domain_checks((human,), Checks())
