"""Consumer-supplied judgment, candidate and domain check ports."""

from typing import Protocol

from .models import Candidate, CheckIssue, FieldSpec, FieldValue, JudgmentDistribution


class CandidateGenerator(Protocol):
    def candidates(self, spec: FieldSpec, source_ref: str) -> tuple[Candidate, ...]: ...


class JudgmentPort(Protocol):
    def select(
        self, spec: FieldSpec, candidates: tuple[Candidate, ...]
    ) -> JudgmentDistribution: ...

    def verify(self, spec: FieldSpec, candidate: Candidate) -> JudgmentDistribution: ...


class EvidenceValidator(Protocol):
    def validate(self, profile: str, payload: object) -> None: ...


class DomainCheck(Protocol):
    def check(self, fields: tuple[FieldValue, ...]) -> tuple[CheckIssue, ...]: ...
