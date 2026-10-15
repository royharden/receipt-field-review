"""Literal native-format controls; they do not establish a real OCR engine or image accuracy."""

import hashlib
import json

import pytest

from rfr.shared.docio.identity import artifact_bytes, raw_revision, validate_artifact_bytes
from rfr.shared.docio.models import Bounds, PageInput
from rfr.shared.docio.tsv import HEADER, TsvError, page_from_artifact, parse_tsv_artifact

H = "a" * 64


def page():
    return PageInput.model_validate(
        {
            "execution_ref": "synthetic-private-page",
            "document_id": "synthetic-doc",
            "original_content_sha256": H,
            "raw_source_revision": raw_revision("synthetic-doc", H),
            "page_id": "synthetic-page",
            "page_index": 0,
            "page_sha256": "b" * 64,
            "width_px": 80,
            "height_px": 40,
            "grid_policy_id": "rgba8-source-grid-v1",
            "source_kind": "image",
            "transforms": {
                "source_to_engine": {
                    "direction": "source_to_engine",
                    "algorithm": "synthetic-scale/1",
                    "matrix": ((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0)),
                },
                "engine_to_source": {
                    "direction": "engine_to_source",
                    "algorithm": "synthetic-scale/1",
                    "matrix": ((0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 1.0)),
                },
            },
        }
    )


def bounds(**changes):
    return Bounds(
        max_pages=1,
        max_encoded_bytes=1024 * 1024,
        max_decoded_pixels=20000,
        max_words=10,
        max_lines=10,
        max_blocks=10,
        max_output_bytes=1024 * 1024,
        deadline_s=2.0,
        **changes,
    )


def rows():
    return [
        "1\t1\t0\t0\t0\t0\t0\t0\t160\t80\t-1\t",
        "2\t1\t1\t0\t0\t0\t10\t8\t100\t20\t-1\t",
        "3\t1\t1\t1\t0\t0\t10\t8\t100\t20\t-1\t",
        "4\t1\t1\t1\t1\t0\t10\t8\t100\t20\t-1\t",
        "5\t1\t1\t1\t1\t1\t20\t10\t30\t12\t93.5\t商  店",
        "5\t1\t1\t1\t1\t2\t60\t10\t30\t12\t-1\t£2.00",
    ]


def payload(lines=None):
    return HEADER + b"\n" + ("\n".join(rows() if lines is None else lines) + "\n").encode("utf-8")


def parse(data=None, inp=None, limits=None):
    return parse_tsv_artifact(
        payload() if data is None else data,
        inp or page(),
        limits or bounds(),
        engine_width_px=160,
        engine_height_px=80,
        engine_version="synthetic-tsv/1",
        config_sha256=H,
    )


def test_hierarchy_unicode_confidence_once_mapped_boxes_stable_ids_and_exact_bytes():
    first = parse()
    second = parse()
    assert artifact_bytes(first) == artifact_bytes(second)
    assert first.words[0].text == "商  店" and first.words[1].text == "£2.00"
    assert first.words[0].ocr_confidence == 0.935 and first.words[1].ocr_confidence is None
    assert first.lines[0].ocr_confidence is None and first.blocks[0].ocr_confidence is None
    box = first.words[0].bbox_px
    assert (box.x0, box.y0, box.x1, box.y1) == (10, 5, 25, 11)
    assert first.lines[0].text == "商  店 £2.00"
    assert first.lines[0].ordered_child_ids == tuple(w.stable_id for w in first.words)
    assert first.blocks[0].ordered_child_ids == (first.lines[0].stable_id,)
    data = artifact_bytes(first)
    assert validate_artifact_bytes(data, hashlib.sha256(data).hexdigest()) == first
    recognized = page_from_artifact(first, page())
    assert recognized.processing_ref == first.artifact_id and recognized.words == first.words
    changed = rows()
    changed[-1] = changed[-1].replace("£2.00", "£2.01")
    assert parse(payload(changed)).artifact_id != first.artifact_id


def test_genuine_blank_page_has_no_words_but_missing_page_row_is_invalid():
    blank = parse(payload(rows()[:1]))
    assert blank.words == blank.lines == blank.blocks == ()
    assert page_from_artifact(blank, page()).words == ()
    with pytest.raises(TsvError, match="missing_tsv_page_parent"):
        parse(HEADER + b"\n")


@pytest.mark.parametrize(
    "index,old,new,reason",
    [
        (0, "160\t80", "159\t80", "invalid_tsv_page_row"),
        (4, "5\t1\t1\t1\t1\t1", "5\t2\t1\t1\t1\t1", "invalid_tsv_page_or_level"),
        (4, "20\t10\t30", "150\t10\t30", "tsv_box_exceeds_engine"),
        (4, "20\t10\t30", "-1\t10\t30", "invalid_tsv_integer"),
        (4, "20\t10\t30", "20\t10\t0", "invalid_tsv_integer"),
        (4, "93.5", "NaN", "invalid_tsv_confidence"),
        (4, "93.5", "101", "invalid_tsv_confidence"),
        (4, "93.5", "-2", "invalid_tsv_confidence"),
        (4, "5\t1\t1\t1\t1\t1", "5\t1\t1\t1\t2\t1", "invalid_tsv_word_parent_or_text"),
        (4, "商  店", "   ", "invalid_tsv_word_parent_or_text"),
        (3, "-1\t", "0\t", "invalid_structural_tsv_row"),
    ],
    ids=[
        "page-size",
        "foreign-page",
        "engine-bound",
        "negative-coord",
        "zero-box",
        "nan",
        "over-confidence",
        "negative-confidence",
        "orphan-line",
        "blank-word",
        "structural-confidence",
    ],
)
def test_invalid_rows_refuse_with_closed_reason_no_source_text(index, old, new, reason):
    data = rows()
    assert old in data[index]
    data[index] = data[index].replace(old, new)
    with pytest.raises(TsvError, match=reason) as error:
        parse(payload(data))
    assert "商" not in str(error.value)


def test_duplicate_rows_wrong_header_invalid_utf8_and_orphan_hierarchy_refuse():
    for bad in [
        payload(rows() + [rows()[-1]]),
        payload(rows()[1:]),
        HEADER + b"\n\xff",
        b"wrong header\n",
        payload(rows()[:3] + rows()[4:]),
    ]:
        with pytest.raises(TsvError):
            parse(bad)


def test_explicit_count_byte_pixel_output_and_deadline_caps(monkeypatch):
    for change in [
        {"max_words": 1},
        {"max_lines": 1, "max_blocks": 1, "max_words": 1},
        {"max_output_bytes": 50},
        {"max_decoded_pixels": 100},
    ]:
        raw = bounds().model_dump() | change
        with pytest.raises(TsvError) as error:
            parse(limits=Bounds.model_validate(raw))
        assert error.value.status == "limit_exceeded"
    times = iter([0.0, 3.0])
    monkeypatch.setattr("rfr.shared.docio.tsv.time.monotonic", lambda: next(times))
    with pytest.raises(TsvError, match="tsv_deadline"):
        parse()


def test_assembly_rejects_changed_input_grid_or_transform():
    artifact = parse()
    for field, value in [("page_sha256", "c" * 64), ("page_index", 1)]:
        raw = page().model_dump() | {field: value}
        with pytest.raises(TsvError, match="artifact_input_identity_mismatch"):
            page_from_artifact(artifact, PageInput.model_validate(raw))
    data = json.loads(page().model_dump_json())
    data["transforms"]["source_to_engine"]["matrix"][0][2] = 2.0
    data["transforms"]["engine_to_source"]["matrix"][0][2] = -1.0
    other = PageInput.model_validate_json(json.dumps(data))
    with pytest.raises(TsvError, match="artifact_input_transform_mismatch"):
        page_from_artifact(artifact, other)


def test_word_line_paragraph_must_remain_inside_actual_parent_box():
    for index in (2, 3, 4):
        data = rows()
        if index == 4:
            data[index] = data[index].replace("20\t10\t30", "100\t10\t30")
        else:
            data[index] = data[index].replace("10\t8\t100", "0\t8\t100")
        with pytest.raises(TsvError, match="tsv_child_exceeds_parent"):
            parse(payload(data))


def test_engine_metadata_is_closed_and_not_authenticated_by_valid_shape():
    for version, digest in [("", H), ("synthetic/1", "wrong-digest")]:
        with pytest.raises(TsvError, match="invalid_engine_metadata"):
            parse_tsv_artifact(
                payload(),
                page(),
                bounds(),
                engine_width_px=160,
                engine_height_px=80,
                engine_version=version,
                config_sha256=digest,
            )


def test_transient_execution_handle_does_not_change_retained_content_or_child_identity():
    first = parse()
    another = page().model_copy(update={"execution_ref": "different-transient-execution-handle"})
    second = parse(inp=another)
    assert artifact_bytes(first) == artifact_bytes(second)
    assert first.artifact_id.startswith("tsv2:")
    assert first.words == second.words and first.lines == second.lines


@pytest.mark.parametrize(
    "change",
    [
        {"page_sha256": "c" * 64},
        {"page_id": "different-page"},
        {
            "original_content_sha256": "c" * 64,
            "raw_source_revision": raw_revision("synthetic-doc", "c" * 64),
        },
    ],
    ids=["retained-grid", "page-id", "original-raw"],
)
def test_actual_immutable_input_changes_still_change_derived_identity(change):
    original = parse()
    different = parse(inp=PageInput.model_validate(page().model_dump() | change))
    assert original.artifact_id != different.artifact_id
    changed_config = parse_tsv_artifact(
        payload(),
        page(),
        bounds(),
        engine_width_px=160,
        engine_height_px=80,
        engine_version="synthetic-tsv/1",
        config_sha256="c" * 64,
    )
    assert original.artifact_id != changed_config.artifact_id
