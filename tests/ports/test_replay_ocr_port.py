"""Strict provided-frame controls, never real OCR/capture/data quality evidence."""

import hashlib
from dataclasses import replace
from datetime import date

import pytest

from rfr.ports.replay_ocr import OcrReplayProfile, ReplayOcr, ReplayRecord, request_digest
from rfr.receipt.b0 import extract_b0
from rfr.receipt.models import CurrencyPolicy, ReceiptContext
from rfr.shared.docio.identity import (
    artifact_bytes,
    grid_digest,
    raw_revision,
    validate_artifact_bytes,
)
from rfr.shared.docio.models import Bounds, Document, PageInput, ProcessingArtifact, Provenance

PROFILE = OcrReplayProfile("synthetic-native-structure", "fixture/1", "a" * 64)


def frame(blank=False):
    original = hashlib.sha256(b"ACME literal replay control").hexdigest()
    inp = PageInput.model_validate(
        {
            "execution_ref": "private-fixture-handle",
            "document_id": "control-doc",
            "original_content_sha256": original,
            "raw_source_revision": raw_revision("control-doc", original),
            "page_id": "page:0",
            "page_index": 0,
            "page_sha256": grid_digest(10, 10, b"\xff" * 400),
            "width_px": 10,
            "height_px": 10,
            "grid_policy_id": "rgba8-source-grid-v1",
            "source_kind": "native_text",
            "transforms": {
                "source_to_engine": {
                    "direction": "source_to_engine",
                    "algorithm": "identity/1",
                    "matrix": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                },
                "engine_to_source": {
                    "direction": "engine_to_source",
                    "algorithm": "identity/1",
                    "matrix": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                },
            },
        }
    )
    word = {
        "stable_id": "word:0",
        "text": "ACME",
        "bbox_px": {"x0": 1.0, "y0": 1.0, "x1": 9.0, "y1": 4.0},
        "ocr_confidence": None,
        "geometry_provenance": "native",
        "source_engine": PROFILE.engine,
        "source_engine_version": PROFILE.engine_version,
    }
    line = word | {"stable_id": "line:0", "ordered_child_ids": ("word:0",)}
    artifact = ProcessingArtifact(
        **inp.model_dump(
            include={
                "document_id",
                "raw_source_revision",
                "page_id",
                "page_index",
                "page_sha256",
                "width_px",
                "height_px",
                "grid_policy_id",
            }
        ),
        artifact_id="synthetic-frame",
        engine=PROFILE.engine,
        engine_version=PROFILE.engine_version,
        config_digest=PROFILE.config_sha256,
        source_to_engine=inp.transforms.source_to_engine,
        engine_to_source=inp.transforms.engine_to_source,
        words=() if blank else (word,),
        lines=() if blank else (line,),
        blocks=(),
    )
    data = artifact_bytes(artifact)
    record = ReplayRecord(inp, "synthetic", "ok", data, hashlib.sha256(data).hexdigest())
    return inp, record


def bounds(**changes):
    raw = {
        "max_pages": 1,
        "max_encoded_bytes": 1000,
        "max_decoded_pixels": 1000,
        "max_words": 10,
        "max_lines": 10,
        "max_blocks": 10,
        "max_output_bytes": 10000,
        "deadline_s": 1.0,
    }
    return Bounds.model_validate(raw | changes)


def test_exact_frame_and_transient_handle_reuse_keep_origin_refs_and_no_live_fallback():
    inp, record = frame()
    replay = ReplayOcr((record,), profile=PROFILE)
    result = replay.recognize(inp, bounds())
    assert result.status == "ok" and "synthetic" in result.capabilities
    assert "no_live_fallback" in result.capabilities and result.page.words[0].ocr_confidence is None
    another = inp.model_copy(update={"execution_ref": "changed-private-runtime-handle"})
    assert request_digest(inp, PROFILE) == request_digest(another, PROFILE)
    assert replay.recognize(another, bounds()) == result
    assert replay.retained(result.processing_artifact_ref) == record.retained_artifact
    with pytest.raises(ValueError, match="unknown_replay_artifact_ref"):
        replay.retained("../private")


def test_changed_grid_raw_profile_or_missing_frame_cannot_dispatch_or_silently_fallback():
    inp, record = frame()
    replay = ReplayOcr((record,), profile=PROFILE)
    different = inp.model_copy(update={"page_sha256": "c" * 64})
    miss = replay.recognize(different, bounds())
    assert miss.status == "unavailable" and miss.page is None and miss.issues == ("replay_miss",)
    with pytest.raises(ValueError, match="invalid_or_unbound_replay_artifact"):
        ReplayOcr((record,), profile=replace(PROFILE, config_sha256="c" * 64))
    assert request_digest(inp, PROFILE) != request_digest(
        inp, replace(PROFILE, config_sha256="c" * 64)
    )


def test_real_blank_success_is_distinct_from_captured_failure_and_missing_cache():
    inp, record = frame(True)
    blank = ReplayOcr((record,), profile=PROFILE).recognize(inp, bounds())
    assert blank.status == "ok" and blank.page.words == blank.page.lines == ()
    failed = ReplayRecord(inp, "recorded_replay", "timeout", None, None, ("captured_timeout",))
    result = ReplayOcr((failed,), profile=PROFILE).recognize(inp, bounds())
    assert (
        result.status == "timeout"
        and result.page is None
        and result.processing_artifact_ref is None
    )
    assert "recorded_replay" in result.capabilities
    assert ReplayOcr((), profile=PROFILE).recognize(inp, bounds()).status == "unavailable"


def test_duplicate_wrong_hash_foreign_frame_or_fake_failure_artifact_refuses_registration():
    inp, record = frame()
    for records in [
        (record, record),
        (replace(record, artifact_sha256="b" * 64),),
        (replace(record, input=inp.model_copy(update={"page_id": "foreign"})),),
        (replace(record, status="invalid"),),
        (replace(record, origin="live"),),
    ]:
        with pytest.raises(ValueError):
            ReplayOcr(records, profile=PROFILE)
    with pytest.raises(ValueError, match="replay_record_limit"):
        ReplayOcr((record, record), profile=PROFILE, max_records=1)


def test_count_storedbyte_pixel_output_and_deadline_limits_are_explicit(monkeypatch):
    inp, record = frame()
    for limits in [{"max_record_bytes": 1}, {"max_total_bytes": 1}, {"max_records": True}]:
        with pytest.raises(ValueError):
            ReplayOcr((record,), profile=PROFILE, **limits)
    replay = ReplayOcr((record,), profile=PROFILE)
    for limits in [{"max_decoded_pixels": 50}, {"max_output_bytes": 1}]:
        result = replay.recognize(inp, bounds(**limits))
        assert result.status == "limit_exceeded" and result.page is None
    times = iter([0.0, 2.0])
    monkeypatch.setattr("rfr.ports.replay_ocr.time.monotonic", lambda: next(times))
    assert replay.recognize(inp, bounds()).status == "timeout"


def test_same_OcrAdapter_protocol_feeds_retained_source_bound_receipt_B0_with_review_default():
    inp, record = frame()
    replay = ReplayOcr((record,), profile=PROFILE)
    result = replay.recognize(inp, bounds())
    document = Document(
        document_id=inp.document_id,
        original_content_sha256=inp.original_content_sha256,
        raw_source_revision=inp.raw_source_revision,
        source_kind="native_text",
        pages=(result.page,),
        provenance=Provenance(
            producer="synthetic-replay-control",
            version="fixture/1",
            config_sha256=PROFILE.config_sha256,
            source_grid_profile=inp.grid_policy_id,
        ),
    )
    receipt = extract_b0(
        document,
        replay.retained(result.processing_artifact_ref),
        record.artifact_sha256,
        ReceiptContext(currency=CurrencyPolicy(), reference_date=date(2026, 10, 14)),
    )
    assert receipt.fields["merchant_name"].proposal == "ACME"
    assert (
        receipt.fields["merchant_name"].value is None
        and receipt.fields["merchant_name"].status == "needs_review"
    )
    assert receipt.fields["total"].proposal is None and receipt.fields["tax"].proposal is None


def test_actual_word_line_block_counts_respect_caller_caps_without_clipping():
    inp, record = frame()
    original = validate_artifact_bytes(record.retained_artifact, record.artifact_sha256)
    word = original.words[0]
    line = original.lines[0]
    second_word = word.model_copy(update={"stable_id": "word:1"})
    second_line = line.model_copy(update={"stable_id": "line:1", "ordered_child_ids": ("word:1",)})
    from rfr.shared.docio.models import Block

    blocks = tuple(
        Block(
            **line.model_dump(exclude={"stable_id", "ordered_child_ids"}),
            stable_id="block:" + str(index),
            ordered_child_ids=(item.stable_id,),
        )
        for index, item in enumerate((line, second_line))
    )
    artifact = ProcessingArtifact.model_validate(
        original.model_dump()
        | {"words": (word, second_word), "lines": (line, second_line), "blocks": blocks}
    )
    data = artifact_bytes(artifact)
    record = replace(
        record, retained_artifact=data, artifact_sha256=hashlib.sha256(data).hexdigest()
    )
    replay = ReplayOcr((record,), profile=PROFILE)
    for limits in ({"max_words": 1}, {"max_lines": 1}, {"max_blocks": 1}):
        result = replay.recognize(inp, bounds(**limits))
        assert result.status == "limit_exceeded" and result.page is None
    assert len(replay.recognize(inp, bounds()).page.words) == 2


@pytest.mark.parametrize("captured", ["miss", "unavailable"])
def test_deadline_also_bounds_miss_and_recorded_failure(captured, monkeypatch):
    inp, _ = frame()
    records = (
        ()
        if captured == "miss"
        else (ReplayRecord(inp, "recorded_replay", "unavailable", None, None),)
    )
    replay = ReplayOcr(records, profile=PROFILE)
    times = iter([0.0, 2.0])
    monkeypatch.setattr("rfr.ports.replay_ocr.time.monotonic", lambda: next(times))
    result = replay.recognize(inp, bounds())
    assert result.status == "timeout" and result.page is None
