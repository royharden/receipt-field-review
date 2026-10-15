"""A fake native PDF PageSource passes the same generic engine; no PDF decoder is installed."""

import hashlib

from test_selection_engine import admitted, bindings, spec

from rfr.shared.docio.identity import artifact_bytes, grid_digest, raw_revision, validate_evidence
from rfr.shared.docio.models import (
    Bounds,
    Document,
    PageInput,
    PageSourceResult,
    ProcessingArtifact,
    Provenance,
    SourceEvidence,
)
from rfr.shared.docio.tsv import page_from_artifact
from rfr.shared.fieldextract.engine import EvidenceAssessment, extract_field
from rfr.shared.fieldextract.models import Candidate, DocumentEvidence


def test_fake_native_pdf_pages_nullable_confidence_and_real_retained_evidence_validation():
    original = hashlib.sha256(b"synthetic fake PDF source control").hexdigest()
    revision = raw_revision("fake-native-doc", original)
    image_sha = grid_digest(40, 20, b"\xff\xff\xff\xff" * 800)
    transform = {
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
    }
    inp = PageInput.model_validate(
        {
            "execution_ref": "private-fake-native-handle",
            "document_id": "fake-native-doc",
            "original_content_sha256": original,
            "raw_source_revision": revision,
            "page_id": "page:0",
            "page_index": 0,
            "page_sha256": image_sha,
            "width_px": 40,
            "height_px": 20,
            "grid_policy_id": "rgba8-source-grid-v1",
            "source_kind": "pdf",
            "transforms": transform,
        }
    )
    provenance = Provenance(
        producer="fake-native-source",
        version="synthetic/1",
        config_sha256="a" * 64,
        source_grid_profile="rgba8-source-grid-v1",
    )

    class FakeNativeSource:
        def pages(self, trusted_input, bounds):
            assert trusted_input == "private-fake-native-handle" and bounds.max_pages == 1
            return PageSourceResult(
                status="ok",
                pages=(inp,),
                issues=(),
                capabilities=("synthetic-native-source-control",),
                provenance=provenance,
            )

    limits = Bounds(
        max_pages=1,
        max_encoded_bytes=1000,
        max_decoded_pixels=1000,
        max_words=10,
        max_lines=10,
        max_blocks=10,
        max_output_bytes=10000,
        deadline_s=1.0,
    )
    source = FakeNativeSource().pages("private-fake-native-handle", limits)
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
        artifact_id="fake-native-artifact",
        engine="fake-native-text",
        engine_version="synthetic/1",
        config_digest="a" * 64,
        source_to_engine=inp.transforms.source_to_engine,
        engine_to_source=inp.transforms.engine_to_source,
        lines=(),
        blocks=(),
        words=(
            {
                "stable_id": "native-word",
                "text": "battery absent",
                "bbox_px": {"x0": 1.0, "y0": 1.0, "x1": 30.0, "y1": 8.0},
                "ocr_confidence": None,
                "geometry_provenance": "native",
                "source_engine": "fake-native-text",
                "source_engine_version": "synthetic/1",
            },
        ),
    )
    retained = artifact_bytes(artifact)
    recognized = page_from_artifact(artifact, source.pages[0])
    document = Document(
        document_id=inp.document_id,
        original_content_sha256=original,
        raw_source_revision=revision,
        source_kind="pdf",
        pages=(recognized,),
        provenance=provenance,
    )
    ref = SourceEvidence(
        **inp.model_dump(
            include={
                "document_id",
                "original_content_sha256",
                "raw_source_revision",
                "page_id",
                "page_index",
                "page_sha256",
                "width_px",
                "height_px",
                "grid_policy_id",
            }
        ),
        evidence_artifact_sha256=hashlib.sha256(retained).hexdigest(),
        bbox_px=None,
        word_ids=("native-word",),
        line_ids=None,
        excerpt_sha256=hashlib.sha256(b"battery absent").hexdigest(),
        transform_ref=None,
    )
    candidate = Candidate(
        candidate_id="native-candidate",
        field_id="battery.present",
        raw="battery absent",
        normalized=False,
        sources=(DocumentEvidence(kind="document", evidence=ref),),
    )

    class NativeAuthority:
        def assess(self, candidate):
            actual = candidate.sources[0]
            assert (
                validate_evidence(
                    actual.evidence, document, retained, require_measured_spatial=True
                )
                == "battery absent"
            )
            return EvidenceAssessment(
                actual, "native_text", (None,), "synthetic-native-structural/1"
            )

    result = extract_field(
        spec(),
        (candidate,),
        NativeAuthority(),
        bindings(),
        mode="B0",
        chosen_candidate_id="native-candidate",
        b0_prior=0.9,
        policy=admitted(0.9),
    )
    assert result.value is False and result.components.native_quality_multiplier == 1.0
    assert document.pages[0].words[0].ocr_confidence is None
