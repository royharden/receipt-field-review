"""Bounded native TSV parsing. The trusted caller owns actual engine execution/provenance."""

from __future__ import annotations

import hashlib
import math
import time

from pydantic import TypeAdapter

from .identity import artifact_bytes, canonical_bytes, engine_box_to_source
from .models import (
    Block,
    Bounds,
    EngineBox,
    Line,
    OpaqueId,
    Page,
    PageInput,
    ProcessingArtifact,
    Sha256,
    Word,
)

HEADER = (
    b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


class TsvError(ValueError):
    """Closed reason codes; never include source text or private execution paths."""

    def __init__(self, reason: str, status: str = "invalid"):
        super().__init__(reason)
        self.status = status


def _integer(value: str, *, positive: bool = False) -> int:
    if not value or len(value) > 12 or not value.isascii() or not value.isdecimal():
        raise TsvError("invalid_tsv_integer")
    parsed = int(value)
    if positive and parsed == 0:
        raise TsvError("invalid_tsv_integer")
    return parsed


def _contained(child: EngineBox, parent: EngineBox) -> None:
    if not (
        parent.x0 <= child.x0 < child.x1 <= parent.x1
        and parent.y0 <= child.y0 < child.y1 <= parent.y1
    ):
        raise TsvError("tsv_child_exceeds_parent")


def parse_tsv_artifact(
    retained_tsv: bytes,
    page_input: PageInput,
    bounds: Bounds,
    *,
    engine_width_px: int,
    engine_height_px: int,
    engine_version: str,
    config_sha256: str,
) -> ProcessingArtifact:
    """Parse one page's retained Tesseract TSV without running OCR or acquiring source bytes.

    Page numbers in this one-page engine output must be1; persisted page_index comes unchanged
    from PageInput. Structured row order is preserved. Words keep original Unicode/token spacing;
    docio-text/1 inserts one space between TSV words and newline between retained lines.
    Actual trusted execution is required before treating this parser's named engine as native proof.
    """
    started = time.monotonic()
    try:
        TypeAdapter(OpaqueId, config={"strict": True}).validate_python(engine_version)
        TypeAdapter(Sha256, config={"strict": True}).validate_python(config_sha256)
    except ValueError:
        raise TsvError("invalid_engine_metadata") from None
    if type(retained_tsv) is not bytes:
        raise TsvError("tsv_bytes_required")
    if len(retained_tsv) > bounds.max_output_bytes:
        raise TsvError("tsv_byte_limit", "limit_exceeded")
    for value in (engine_width_px, engine_height_px):
        if type(value) is not int or value <= 0:
            raise TsvError("invalid_engine_dimensions")
    if (
        engine_width_px * engine_height_px > bounds.max_decoded_pixels
        or page_input.width_px * page_input.height_px > bounds.max_decoded_pixels
    ):
        raise TsvError("decoded_pixel_limit", "limit_exceeded")
    try:
        rows = retained_tsv.decode("utf-8", errors="strict").splitlines()
    except UnicodeError:
        raise TsvError("invalid_tsv_utf8") from None
    if not rows or rows[0].encode("utf-8") != HEADER:
        raise TsvError("invalid_tsv_header")
    if len(rows) > 1 + 1 + bounds.max_blocks + bounds.max_lines * 2 + bounds.max_words:
        raise TsvError("tsv_row_limit", "limit_exceeded")
    preimage = {
        "algorithm": "docio-tsv/2",
        "input": page_input.model_dump(mode="json", exclude={"execution_ref"}),
        "retained_tsv_sha256": hashlib.sha256(retained_tsv).hexdigest(),
        "engine": "tesseract-tsv",
        "engine_version": engine_version,
        "engine_width_px": engine_width_px,
        "engine_height_px": engine_height_px,
        "config_sha256": config_sha256,
    }
    artifact_id = "tsv2:" + hashlib.sha256(canonical_bytes(preimage)).hexdigest()
    base = {
        "geometry_provenance": "measured_ocr",
        "source_engine": "tesseract-tsv",
        "source_engine_version": engine_version,
    }
    page_seen = False
    blocks, paragraphs, lines, word_ids = {}, {}, {}, set()
    current_block = current_paragraph = current_line = None
    words: list[Word] = []
    line_children: dict[tuple[int, int, int], list[str]] = {}
    for row in rows[1:]:
        if time.monotonic() - started > bounds.deadline_s:
            raise TsvError("tsv_deadline", "timeout")
        values = row.split("\t", 11)
        if len(values) != 12:
            raise TsvError("invalid_tsv_columns")
        level, page_number, block, paragraph, line, word = map(_integer, values[:6])
        if page_number != 1 or not 1 <= level <= 5:
            raise TsvError("invalid_tsv_page_or_level")
        left, top = map(_integer, values[6:8])
        width, height = (_integer(v, positive=True) for v in values[8:10])
        if len(values[10]) > 32:
            raise TsvError("invalid_tsv_confidence")
        try:
            confidence = float(values[10])
        except ValueError:
            raise TsvError("invalid_tsv_confidence") from None
        if not math.isfinite(confidence) or confidence != -1 and not 0 <= confidence <= 100:
            raise TsvError("invalid_tsv_confidence")
        box = EngineBox(
            x0=float(left), y0=float(top), x1=float(left + width), y1=float(top + height)
        )
        try:
            box.within(engine_width_px, engine_height_px)
        except ValueError:
            raise TsvError("tsv_box_exceeds_engine") from None
        if level != 5 and (values[11] or confidence != -1):
            raise TsvError("invalid_structural_tsv_row")
        if level == 1:
            if (
                page_seen
                or any((block, paragraph, line, word))
                or (left, top, width, height) != (0, 0, engine_width_px, engine_height_px)
            ):
                raise TsvError("invalid_tsv_page_row")
            page_seen = True
            continue
        if not page_seen:
            raise TsvError("missing_tsv_page_parent")
        if level == 2:
            if block == 0 or any((paragraph, line, word)) or block in blocks:
                raise TsvError("invalid_tsv_block_parent")
            blocks[block] = box
            current_block, current_paragraph, current_line = block, None, None
            if len(blocks) > bounds.max_blocks:
                raise TsvError("tsv_block_limit", "limit_exceeded")
        elif level == 3:
            key = (block, paragraph)
            if current_block != block or paragraph == 0 or any((line, word)) or key in paragraphs:
                raise TsvError("invalid_tsv_paragraph_parent")
            _contained(box, blocks[block])
            paragraphs[key] = box
            current_paragraph, current_line = key, None
        elif level == 4:
            key = (block, paragraph, line)
            if current_paragraph != (block, paragraph) or line == 0 or word or key in lines:
                raise TsvError("invalid_tsv_line_parent")
            _contained(box, paragraphs[current_paragraph])
            lines[key] = box
            line_children[key] = []
            current_line = key
            if len(lines) > bounds.max_lines:
                raise TsvError("tsv_line_limit", "limit_exceeded")
        else:
            key = (block, paragraph, line, word)
            if current_line != key[:3] or word == 0 or key in word_ids or not values[11].strip():
                raise TsvError("invalid_tsv_word_parent_or_text")
            _contained(box, lines[current_line])
            word_ids.add(key)
            stable_id = artifact_id + ":w:" + ":".join(map(str, key))
            try:
                mapped = engine_box_to_source(
                    box, page_input.transforms, page_input.width_px, page_input.height_px
                )
            except ValueError:
                raise TsvError("tsv_box_exceeds_source") from None
            words.append(
                Word(
                    stable_id=stable_id,
                    text=values[11],
                    bbox_px=mapped,
                    ocr_confidence=None if confidence == -1 else confidence / 100,
                    **base,
                )
            )
            line_children[current_line].append(stable_id)
            if len(words) > bounds.max_words:
                raise TsvError("tsv_word_limit", "limit_exceeded")
    if not page_seen:
        raise TsvError("missing_tsv_page_parent")
    word_map = {w.stable_id: w for w in words}
    output_lines = []
    for key, box in lines.items():
        children = tuple(line_children[key])
        if not children:
            continue
        try:
            mapped = engine_box_to_source(
                box, page_input.transforms, page_input.width_px, page_input.height_px
            )
        except ValueError:
            raise TsvError("tsv_line_exceeds_source") from None
        output_lines.append(
            Line(
                stable_id=artifact_id + ":l:" + ":".join(map(str, key)),
                text=" ".join(word_map[c].text for c in children),
                bbox_px=mapped,
                ocr_confidence=None,
                ordered_child_ids=children,
                **base,
            )
        )
    output_blocks = []
    for block, box in blocks.items():
        children = tuple(
            recognized_line.stable_id
            for recognized_line, key in zip(
                output_lines, (k for k in lines if line_children[k]), strict=True
            )
            if key[0] == block
        )
        if not children:
            continue
        selected = [
            recognized_line
            for recognized_line in output_lines
            if recognized_line.stable_id in children
        ]
        try:
            mapped = engine_box_to_source(
                box, page_input.transforms, page_input.width_px, page_input.height_px
            )
        except ValueError:
            raise TsvError("tsv_block_exceeds_source") from None
        output_blocks.append(
            Block(
                stable_id=artifact_id + ":b:" + str(block),
                text="\n".join(recognized_line.text for recognized_line in selected),
                bbox_px=mapped,
                ocr_confidence=None,
                ordered_child_ids=children,
                **base,
            )
        )
    identity = page_input.model_dump(
        include={
            "document_id",
            "raw_source_revision",
            "page_id",
            "page_index",
            "width_px",
            "height_px",
            "page_sha256",
            "grid_policy_id",
        }
    )
    artifact = ProcessingArtifact(
        **identity,
        artifact_id=artifact_id,
        engine="tesseract-tsv",
        engine_version=engine_version,
        config_digest=config_sha256,
        source_to_engine=page_input.transforms.source_to_engine,
        engine_to_source=page_input.transforms.engine_to_source,
        words=tuple(words),
        lines=tuple(output_lines),
        blocks=tuple(output_blocks),
    )
    if len(artifact_bytes(artifact)) > bounds.max_output_bytes:
        raise TsvError("artifact_byte_limit", "limit_exceeded")
    if time.monotonic() - started > bounds.deadline_s:
        raise TsvError("tsv_deadline", "timeout")
    return artifact


def page_from_artifact(artifact: ProcessingArtifact, page_input: PageInput) -> Page:
    """Assemble only an exactly bound recognized Page; caller retains exact artifact bytes."""
    for name in (
        "document_id",
        "raw_source_revision",
        "page_id",
        "page_index",
        "width_px",
        "height_px",
        "page_sha256",
        "grid_policy_id",
    ):
        if getattr(artifact, name) != getattr(page_input, name):
            raise TsvError("artifact_input_identity_mismatch")
    if (artifact.source_to_engine, artifact.engine_to_source) != (
        page_input.transforms.source_to_engine,
        page_input.transforms.engine_to_source,
    ):
        raise TsvError("artifact_input_transform_mismatch")
    value = artifact.model_dump(
        include={
            "document_id",
            "raw_source_revision",
            "page_id",
            "page_index",
            "width_px",
            "height_px",
            "page_sha256",
            "grid_policy_id",
            "words",
            "lines",
            "blocks",
        }
    )
    return Page.model_validate(
        value | {"source_kind": page_input.source_kind, "processing_ref": artifact.artifact_id}
    )
