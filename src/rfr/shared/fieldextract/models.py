"""Proposals, typed values and neutral source extensions, without a selector engine."""

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, TypeAdapter, model_validator

from ..docio.models import OpaqueId, Probability, SourceEvidence, Wire


class DocumentEvidence(Wire):
    kind: Literal["document"]
    evidence: SourceEvidence


class ExtensionEvidence(Wire):
    """Payload must subsequently pass the named consumer-owned evidence validator."""

    kind: Literal["extension"]
    profile: OpaqueId
    evidence_id: OpaqueId
    payload: dict[str, JsonValue]


EvidenceSource = Annotated[DocumentEvidence | ExtensionEvidence, Field(discriminator="kind")]


class FieldSpec(Wire):
    field_id: OpaqueId
    kind: Literal["text", "number", "boolean", "date", "category", "set", "object"]
    required: bool
    definition: str
    boundary_cases: tuple[str, ...]
    generator: OpaqueId


class Candidate(Wire):
    candidate_id: OpaqueId
    field_id: OpaqueId
    raw: JsonValue
    normalized: JsonValue
    sources: tuple[EvidenceSource, ...]


class ScoreComponents(Wire):
    selector_probability: Probability | None
    verifier_probability: Probability | None
    native_quality_multiplier: Probability | None
    native_quality_policy: OpaqueId | None

    @model_validator(mode="after")
    def declared_policy(self) -> Self:
        if self.native_quality_multiplier is not None and self.native_quality_policy is None:
            raise ValueError("native quality is a declared policy, not invented OCR confidence")
        return self


class FieldValue(Wire):
    field_id: OpaqueId
    value: JsonValue
    confidence: Probability | None
    source: EvidenceSource | None
    method: OpaqueId
    status: Literal["proposed", "absent", "abstained", "needs_review", "human_effective"]
    proposal: JsonValue
    human_provenance_ref: OpaqueId | None
    hard_flags: tuple[OpaqueId, ...]
    issues: tuple[OpaqueId, ...]
    components: ScoreComponents
    score_version: OpaqueId
    threshold_version: OpaqueId

    @model_validator(mode="after")
    def review_branches(self) -> Self:
        if self.status in ("absent", "abstained") and self.value is not None:
            raise ValueError("absent/abstained cannot carry an effective value")
        if self.hard_flags and self.status not in ("needs_review", "human_effective"):
            raise ValueError("hard failures require review")
        if self.status == "human_effective" and self.human_provenance_ref is None:
            raise ValueError("human effective value needs actual provenance reference")
        if self.status != "human_effective" and self.human_provenance_ref is not None:
            raise ValueError("machine proposal cannot masquerade as human outcome")
        return self


class JudgmentDistribution(Wire):
    question_id: OpaqueId
    origin: Literal["native_model", "synthetic", "replay"]
    probabilities: dict[OpaqueId, Probability]

    @model_validator(mode="after")
    def full_distribution(self) -> Self:
        if not self.probabilities or abs(sum(self.probabilities.values()) - 1) > 1e-6:
            raise ValueError("native probabilities must form a complete distribution")
        return self


class CheckIssue(Wire):
    issue_id: OpaqueId
    severity: Literal["notice", "review", "hard_failure"]
    field_ids: tuple[OpaqueId, ...]


WIRE_MODELS = (FieldSpec, Candidate, FieldValue, JudgmentDistribution, CheckIssue)
EVIDENCE_ADAPTER = TypeAdapter(EvidenceSource)
