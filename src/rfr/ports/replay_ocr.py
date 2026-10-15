"""Strict caller-supplied OCR replay, never a live/native fallback or authenticity proof."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pydantic import TypeAdapter

from ..shared.docio.identity import canonical_bytes, validate_artifact_bytes
from ..shared.docio.models import Bounds, OcrResult, OpaqueId, PageInput, Sha256, Status
from ..shared.docio.tsv import page_from_artifact


@dataclass(frozen=True)
class ReplayRecord:
    input: PageInput
    origin: Literal["synthetic", "recorded_replay"]
    status: Status
    retained_artifact: bytes | None
    artifact_sha256: str | None
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class OcrReplayProfile:
    engine: str
    engine_version: str
    config_sha256: str

    def __post_init__(self):
        for value in (self.engine, self.engine_version):
            TypeAdapter(OpaqueId, config={"strict": True}).validate_python(value)
        TypeAdapter(Sha256, config={"strict": True}).validate_python(self.config_sha256)


def request_digest(page: PageInput, profile: OcrReplayProfile) -> str:
    stable = PageInput.model_validate_json(page.model_dump_json())
    preimage = {
        "algorithm": "rfr-ocr-replay/1",
        "input": stable.model_dump(mode="json", exclude={"execution_ref"}),
        "profile": {
            "engine": profile.engine,
            "engine_version": profile.engine_version,
            "config_sha256": profile.config_sha256,
        },
    }
    return hashlib.sha256(canonical_bytes(preimage)).hexdigest()


class ReplayOcr:
    """OcrAdapter over explicitly supplied immutable frames; no files, sockets or engine access.

    Retained input signatures are cache bindings, not authority to use source/capture/human data.
    Synthetic origin remains visible; it cannot establish genuine OCR quality or model execution.
    """

    def __init__(
        self,
        records: tuple[ReplayRecord, ...],
        *,
        profile: OcrReplayProfile,
        max_records: int = 100,
        max_record_bytes: int = 2 * 1024 * 1024,
        max_total_bytes: int = 128 * 1024 * 1024,
    ):
        if type(profile) is not OcrReplayProfile:
            raise ValueError("explicit_OCR_replay_profile_required")
        if any(
            type(n) is not int or n <= 0 for n in (max_records, max_record_bytes, max_total_bytes)
        ):
            raise ValueError("positive_replay_limits_required")
        if type(records) is not tuple or len(records) > max_records:
            raise ValueError("replay_record_limit")
        lookup = {}
        retained = {}
        total = 0
        for record in records:
            if not isinstance(record, ReplayRecord) or record.origin not in (
                "synthetic",
                "recorded_replay",
            ):
                raise ValueError("invalid_replay_record_or_origin")
            TypeAdapter(Status, config={"strict": True}).validate_python(record.status)
            if type(record.issues) is not tuple:
                raise ValueError("replay_issue_tuple_required")
            for issue in record.issues:
                TypeAdapter(OpaqueId, config={"strict": True}).validate_python(issue)
            inp = PageInput.model_validate_json(record.input.model_dump_json())
            key = request_digest(inp, profile)
            if key in lookup:
                raise ValueError("duplicate_replay_input")
            page = None
            ref = None
            if record.status == "ok":
                data = record.retained_artifact
                if (
                    type(data) is not bytes
                    or len(data) > max_record_bytes
                    or record.artifact_sha256 is None
                ):
                    raise ValueError("replay_artifact_bytes_required_or_limit")
                total += len(data)
                if total > max_total_bytes:
                    raise ValueError("replay_total_byte_limit")
                try:
                    artifact = validate_artifact_bytes(data, record.artifact_sha256)
                    if (artifact.engine, artifact.engine_version, artifact.config_digest) != (
                        profile.engine,
                        profile.engine_version,
                        profile.config_sha256,
                    ):
                        raise ValueError("replay_engine_profile_mismatch")
                    page = page_from_artifact(artifact, inp)
                except ValueError:
                    raise ValueError("invalid_or_unbound_replay_artifact") from None
                ref = "sha256:" + record.artifact_sha256
                if ref in retained and retained[ref] != data:
                    raise ValueError("replay_artifact_ref_collision")
                retained[ref] = data
            elif record.retained_artifact is not None or record.artifact_sha256 is not None:
                raise ValueError("failed_replay_cannot_claim_artifact")
            lookup[key] = (record.origin, record.status, page, ref, record.issues)
        self._lookup = MappingProxyType(lookup)
        self._retained = MappingProxyType(retained)
        self._profile = profile

    @staticmethod
    def _failure(status, reason):
        return OcrResult(
            status=status,
            page=None,
            issues=(reason,),
            capabilities=("strict_replay", "no_live_fallback"),
            processing_artifact_ref=None,
        )

    def recognize(self, page: PageInput, bounds: Bounds) -> OcrResult:
        began = time.monotonic()
        if page.width_px * page.height_px > bounds.max_decoded_pixels:
            return self._failure("limit_exceeded", "replay_pixel_limit")
        record = self._lookup.get(request_digest(page, self._profile))
        if record is None:
            if time.monotonic() - began > bounds.deadline_s:
                return self._failure("timeout", "replay_deadline")
            return self._failure("unavailable", "replay_miss")
        origin, status, recognized, ref, issues = record
        capabilities = ("strict_replay", origin, "no_live_fallback")
        if status != "ok":
            if time.monotonic() - began > bounds.deadline_s:
                return self._failure("timeout", "replay_deadline")
            return OcrResult(
                status=status,
                page=None,
                issues=(*issues, "captured_replay_failure"),
                capabilities=capabilities,
                processing_artifact_ref=None,
            )
        data = self._retained[ref]
        if (
            len(data) > bounds.max_output_bytes
            or len(recognized.words) > bounds.max_words
            or len(recognized.lines) > bounds.max_lines
            or len(recognized.blocks) > bounds.max_blocks
        ):
            return self._failure("limit_exceeded", "replay_output_limit")
        if time.monotonic() - began > bounds.deadline_s:
            return self._failure("timeout", "replay_deadline")
        # A fresh model prevents a consumer from mutating later results through nested data.
        result = OcrResult(
            status="ok",
            page=recognized,
            issues=(*issues, "replay_not_native_execution"),
            capabilities=capabilities,
            processing_artifact_ref=ref,
        )
        return OcrResult.model_validate_json(result.model_dump_json())

    def retained(self, processing_ref: str) -> bytes:
        """Only pre-registered retained frames; no filesystem/path/network fallback."""
        try:
            return self._retained[processing_ref]
        except KeyError:
            raise ValueError("unknown_replay_artifact_ref") from None
