"""Generic proposal controls without field selection/verifier/domain check engines."""

import pytest
from pydantic import ValidationError

from rfr.shared.fieldextract.models import (
    Candidate,
    FieldValue,
    JudgmentDistribution,
    ScoreComponents,
)


def field_wire():
    return {
        "field_id": "supported",
        "value": False,
        "confidence": None,
        "source": None,
        "method": "native-fixture",
        "status": "needs_review",
        "proposal": False,
        "human_provenance_ref": None,
        "hard_flags": ("ungrounded",),
        "issues": (),
        "components": {
            "selector_probability": None,
            "verifier_probability": None,
            "native_quality_multiplier": None,
            "native_quality_policy": None,
        },
        "score_version": "fixture/1",
        "threshold_version": "review-only/1",
    }


def test_null_native_confidence_and_false_proposal_remain_honest():
    value = FieldValue.model_validate(field_wire())
    assert value.proposal is False and value.value is False and value.confidence is None
    for bad in (
        {"status": "proposed"},
        {"confidence": float("nan")},
        {"status": "human_effective"},
        {"unexpected": True},
    ):
        with pytest.raises(ValidationError):
            FieldValue.model_validate(field_wire() | bad)


def test_consumer_extension_requires_tagged_profile_not_unknown_pointer_union():
    value = {
        "candidate_id": "candidate-1",
        "field_id": "supported",
        "raw": False,
        "normalized": False,
        "sources": (
            {
                "kind": "extension",
                "profile": "fixture-evidence/1",
                "evidence_id": "field-1",
                "payload": {"raw": False},
            },
        ),
    }
    assert Candidate.model_validate(value).raw is False
    with pytest.raises(ValidationError):
        Candidate.model_validate(value | {"sources": ({"kind": "unknown"},)})


def test_distribution_keeps_native_probabilities_without_renormalization():
    distribution = {
        "question_id": "select",
        "origin": "synthetic",
        "probabilities": {"a": 0.2, "b": 0.8},
    }
    assert JudgmentDistribution.model_validate(distribution).probabilities["a"] == 0.2
    for bad in ({"a": 0.2, "b": 0.7}, {"a": float("inf")}, {"a": True}, {"a": 1.1}):
        with pytest.raises(ValidationError):
            JudgmentDistribution.model_validate(distribution | {"probabilities": bad})
    with pytest.raises(ValidationError):
        ScoreComponents(
            selector_probability=None,
            verifier_probability=None,
            native_quality_multiplier=0.9,
            native_quality_policy=None,
        )
