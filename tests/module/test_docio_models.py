"""Raw/grid/artifact/quote controls; all pages and transforms are synthetic."""

import hashlib
import json

import pytest
from pydantic import ValidationError
from synthetic_wires import G, H, document_fixture, transforms

from rfr.shared.docio.identity import (
    artifact_bytes,
    engine_box_to_source,
    grid_digest,
    grid_preimage,
    raw_revision,
    validate_artifact_bytes,
    validate_evidence,
)
from rfr.shared.docio.models import (
    AffineTransform,
    BoxPx,
    Document,
    EngineBox,
    OcrResult,
    Page,
    ProcessingArtifact,
    SourceEvidence,
    TransformPair,
    Word,
)


def test_exact_adopted_rgba_preimage_not_png_encoder_hash():
    pixels = bytes((255, 0, 0, 255, 0, 0, 255, 128))
    expected_header = (
        b'{"algorithm":"rgba8-source-grid-v1","channel_order":"RGBA",'
        b'"height_px":1,"mode":"RGBA8","row_order":"top-to-bottom","width_px":2}\n'
    )
    assert grid_preimage(2, 1, pixels) == expected_header + pixels
    assert (
        grid_digest(2, 1, pixels)
        == "525822da8c8afdfde283e5dcee4b25d9cad718efe04333943c7983100a92cd08"
    )
    assert grid_digest(2, 1, pixels) != grid_digest(1, 2, pixels)


@pytest.mark.parametrize(
    "w,h,p",
    [(True, 1, b"1234"), (0, 1, b""), (1, 1, b"123"), (1.0, 1, b"1234"), (1, 1, bytearray(4))],
)
def test_grid_controls_reject_boolean_dimensions_and_missing_retained_channels(w, h, p):
    with pytest.raises(ValueError):
        grid_preimage(w, h, p)


def test_raw_grid_and_derived_identity_are_independent():
    doc, artifact, retained, _ = document_fixture()
    changed = artifact.model_copy(
        update={"engine_version": "2", "words": (), "lines": (), "blocks": ()}
    )
    changed = ProcessingArtifact.model_validate_json(changed.model_dump_json())
    assert (
        hashlib.sha256(artifact_bytes(changed)).hexdigest() != hashlib.sha256(retained).hexdigest()
    )
    assert changed.raw_source_revision == doc.raw_source_revision
    assert changed.page_sha256 == doc.pages[0].page_sha256
    assert raw_revision("other-collection:document", H) != doc.raw_source_revision


@pytest.mark.parametrize(
    "matrix",
    [
        ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ((float("nan"), 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 1.0, 1.0)),
    ],
)
def test_singular_nonfinite_projective_transforms_reject(matrix):
    with pytest.raises(ValidationError):
        AffineTransform(direction="source_to_engine", algorithm="test", matrix=matrix)


def test_inverse_mismatch_rejects():
    value = transforms()
    value["engine_to_source"]["matrix"] = ((0.5, 0.0, 0.0), (0.0, 0.5, 0.0), (0.0, 0.0, 1.0))
    with pytest.raises(ValidationError):
        TransformPair.model_validate(value)


@pytest.mark.parametrize(
    "forward,inverse",
    [
        (
            ((0.0, -1.0, 80.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            ((0.0, 1.0, 0.0), (-1.0, 0.0, 80.0), (0.0, 0.0, 1.0)),
        ),
        (
            ((-1.0, 0.0, 100.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            ((-1.0, 0.0, 100.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        (
            ((2.0, 0.0, 4.0), (0.0, 2.0, 6.0), (0.0, 0.0, 1.0)),
            ((0.5, 0.0, -2.0), (0.0, 0.5, -3.0), (0.0, 0.0, 1.0)),
        ),
    ],
)
def test_synthetic_rotate_mirror_scale_roundtrip_once_within_one_source_pixel(forward, inverse):
    pair = TransformPair.model_validate(
        {
            "source_to_engine": {
                "direction": "source_to_engine",
                "algorithm": "synthetic/1",
                "matrix": forward,
            },
            "engine_to_source": {
                "direction": "engine_to_source",
                "algorithm": "synthetic/1",
                "matrix": inverse,
            },
        }
    )
    source = (2.0, 3.0, 20.0, 13.0)
    points = [
        (
            forward[0][0] * x + forward[0][1] * y + forward[0][2],
            forward[1][0] * x + forward[1][1] * y + forward[1][2],
        )
        for x in (source[0], source[2])
        for y in (source[1], source[3])
    ]
    engine = EngineBox(
        x0=min(x for x, y in points),
        y0=min(y for x, y in points),
        x1=max(x for x, y in points),
        y1=max(y for x, y in points),
    )
    result = engine_box_to_source(engine, pair, 100, 80)
    assert (
        max(
            abs(a - b)
            for a, b in zip((result.x0, result.y0, result.x1, result.y1), source, strict=True)
        )
        <= 1
    )
    with pytest.raises(ValueError):
        engine_box_to_source(result, pair, 100, 80)


def test_line_only_native_excerpt_and_null_confidence():
    document, artifact, retained, ref = document_fixture()
    assert artifact.words[0].ocr_confidence is None
    assert validate_evidence(ref, document, retained, require_measured_spatial=True) == "café  Ω"
    assert validate_artifact_bytes(retained, ref.evidence_artifact_sha256) == artifact


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_content_sha256", G),
        ("page_sha256", H),
        ("document_id", "other-collection:document"),
        ("page_index", 1),
        ("word_ids", ("current-engine-reused-ID",)),
        ("excerpt_sha256", H),
        ("bbox_px", {"x0": 40.0, "y0": 40.0, "x1": 60.0, "y1": 60.0}),
    ],
)
def test_wrong_raw_grid_collection_ids_excerpt_and_contradictory_box_fail(field, value):
    document, _, retained, ref = document_fixture()
    candidate = ref.model_dump()
    candidate[field] = value
    with pytest.raises(ValueError):
        validate_evidence(SourceEvidence.model_validate(candidate), document, retained)


def test_asserted_geometry_never_upgrades_to_measured():
    document, _, retained, ref = document_fixture(geometry="model_claimed")
    assert validate_evidence(ref, document, retained) == "café  Ω"
    with pytest.raises(ValueError):
        validate_evidence(ref, document, retained, require_measured_spatial=True)
    value = document.pages[0].words[0].model_dump()
    value["ocr_confidence"] = 0.99
    with pytest.raises(ValidationError):
        Word.model_validate(value)


def test_exact_retained_artifact_not_reencoded_or_rerun():
    _, _, retained, ref = document_fixture()
    pretty = json.dumps(json.loads(retained), ensure_ascii=False, indent=2).encode()
    with pytest.raises(ValueError):
        validate_artifact_bytes(pretty, ref.evidence_artifact_sha256)
    with pytest.raises(ValueError):
        validate_artifact_bytes(pretty, hashlib.sha256(pretty).hexdigest())


def test_genuine_blank_ok_differs_from_unavailable_ocr():
    document, _, _, _ = document_fixture()
    blank = Page.model_validate(
        document.pages[0].model_dump() | {"words": (), "lines": (), "blocks": ()}
    )
    result = OcrResult(
        status="ok",
        page=blank,
        issues=(),
        capabilities=("native",),
        processing_artifact_ref="blank-artifact",
    )
    assert result.page is not None and result.page.words == ()
    assert (
        OcrResult(
            status="unavailable",
            page=None,
            issues=("not-installed",),
            capabilities=(),
            processing_artifact_ref=None,
        ).page
        is None
    )
    for status, page, ref in (("ok", None, None), ("unavailable", blank, "blank-artifact")):
        with pytest.raises(ValidationError):
            OcrResult(
                status=status, page=page, issues=(), capabilities=(), processing_artifact_ref=ref
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("width_px", True),
        ("page_index", -1),
        ("page_index", 0.0),
        ("unexpected", 1),
    ],
)
def test_page_closed_integer_and_zero_base_controls(field, value):
    document, _, _, _ = document_fixture()
    candidate = document.pages[0].model_dump() | {field: value}
    with pytest.raises(ValidationError):
        Page.model_validate(candidate)


def test_document_rejects_changed_raw_revision_instead_of_upgrading_old_evidence():
    document, _, _, _ = document_fixture()
    with pytest.raises(ValidationError):
        Document.model_validate(document.model_dump() | {"raw_source_revision": "current-ocr"})
    with pytest.raises(ValidationError):
        BoxPx(x0=0.0, y0=0.0, x1=float("inf"), y1=1.0)


def test_engine_frame_cannot_be_persisted_as_source_and_artifact_cannot_be_retargeted():
    document, _, retained, ref = document_fixture()
    engine = EngineBox(x0=2.0, y0=3.0, x1=20.0, y1=13.0)
    with pytest.raises(ValidationError):
        Word.model_validate(document.pages[0].words[0].model_dump() | {"bbox_px": engine})
    with pytest.raises(ValidationError):
        SourceEvidence.model_validate(ref.model_dump() | {"bbox_px": engine})
    changed = document.pages[0].model_dump()
    changed["words"][0]["text"] = "current OCR reused ID"
    changed_doc = Document.model_validate(document.model_dump() | {"pages": (changed,)})
    with pytest.raises(ValueError):
        validate_evidence(ref, changed_doc, retained)


def test_text_only_line_resolution_and_original_internal_whitespace_survive():
    document, artifact, _, ref = document_fixture()
    changed = artifact.model_dump()
    for kind in ("words", "lines", "blocks"):
        changed[kind][0]["bbox_px"] = None
        changed[kind][0]["geometry_provenance"] = "none"
    # Line's stored spacing is independent of word join; retain that exact observed text.
    changed["lines"][0]["text"] = "café   Ω"
    changed["blocks"][0]["text"] = "café   Ω"
    new_artifact = ProcessingArtifact.model_validate(changed)
    retained = artifact_bytes(new_artifact)
    page = document.pages[0].model_dump() | {
        key: changed[key] for key in ("words", "lines", "blocks")
    }
    document = Document.model_validate(document.model_dump() | {"pages": (page,)})
    value = ref.model_dump() | {
        "bbox_px": None,
        "evidence_artifact_sha256": hashlib.sha256(retained).hexdigest(),
        "excerpt_sha256": hashlib.sha256("café   Ω".encode()).hexdigest(),
    }
    ref = SourceEvidence.model_validate(value)
    assert validate_evidence(ref, document, retained) == "café   Ω"
    with pytest.raises(ValueError):
        validate_evidence(ref, document, retained, require_measured_spatial=True)


def test_transform_reference_requires_explicit_retained_binding_not_current_config():
    document, artifact, retained, ref = document_fixture()
    ref = SourceEvidence.model_validate(ref.model_dump() | {"transform_ref": "transform:1"})
    with pytest.raises(ValueError):
        validate_evidence(ref, document, retained)
    pair = TransformPair(
        source_to_engine=artifact.source_to_engine, engine_to_source=artifact.engine_to_source
    )
    assert (
        validate_evidence(ref, document, retained, resolved_transforms={"transform:1": pair})
        == "café  Ω"
    )


def test_hierarchy_rejects_duplicate_foreign_and_reordered_child_ids():
    _, artifact, _, _ = document_fixture()
    for ids in (("word-1", "word-1"), ("unknown-word",)):
        value = artifact.model_dump()
        value["lines"][0]["ordered_child_ids"] = ids
        with pytest.raises(ValidationError):
            ProcessingArtifact.model_validate(value)
