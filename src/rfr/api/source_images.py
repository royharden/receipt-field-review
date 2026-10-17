"""Read an existing local normalized page only when its pixels match the current Docio grid."""

import importlib
import io
import re
import warnings
import zlib
from dataclasses import dataclass

from ..ingest.images import MAX_PIXELS, load_staged
from ..pipeline.files import BatchError, batch_mutex
from ..pipeline.store import BatchStore
from ..shared.docio.identity import grid_digest
from ..shared.rulings.store import PriorConflict
from .security import RequestRefused


@dataclass(frozen=True)
class SourcePage:
    png: bytes
    revision: str
    grid_sha256: str


def _normalized_chunks(raw: bytes) -> None:
    # The staging encoder emits only IHDR/IDAT/IEND. Refuse ancillary metadata and trailing
    # bytes even when a modified PNG still decodes to the same canonical pixel grid.
    offset, data_seen = 8, False
    while offset + 12 <= len(raw):
        size = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + size
        if (
            end > len(raw)
            or kind not in {b"IHDR", b"IDAT", b"IEND"}
            or (kind == b"IHDR") != (offset == 8)
            or zlib.crc32(memoryview(raw)[offset + 4 : end - 4])
            != int.from_bytes(raw[end - 4 : end], "big")
        ):
            raise BatchError("source_image_encoding_refused")
        if kind == b"IEND":
            if size != 0 or not data_seen or end != len(raw):
                raise BatchError("source_image_encoding_refused")
            return
        data_seen = data_seen or kind == b"IDAT"
        offset = end
    raise BatchError("source_image_encoding_refused")


def source_page(store: BatchStore, item_id: str, revision: str) -> SourcePage:
    if type(revision) is not str or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ValueError("exact_source_revision_required")
    # Hold the same mutex as register/delete until the response snapshot is fully validated.
    # An already issued response cannot revoke bytes; a new request rechecks the current head.
    with batch_mutex(store.root):
        bundle = store._bundle(store._manifest(), item_id)
        if bundle.revision != revision:
            raise PriorConflict("item_revision_conflict")
        document = bundle.document
        if document.source_kind != "image" or len(document.pages) != 1:
            raise RequestRefused(404, "source_image_unavailable")
        page = document.pages[0]
        if page.page_index != 0 or page.grid_policy_id != "rgba8-source-grid-v1":
            raise RequestRefused(404, "source_image_unavailable")
        staged = load_staged(store.root / "pages", document.original_content_sha256)
        _normalized_chunks(staged.page_png)
        if (page.width_px, page.height_px) != (
            staged.manifest.page_width_px,
            staged.manifest.page_height_px,
        ):
            raise BatchError("source_image_grid_conflict")
        try:
            image_module = importlib.import_module("PIL.Image")
        except ImportError:
            raise RequestRefused(503, "source_image_decoder_unavailable") from None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", image_module.DecompressionBombWarning)
                with image_module.open(io.BytesIO(staged.page_png), formats=["PNG"]) as image:
                    if (
                        image.size != (page.width_px, page.height_px)
                        or image.width * image.height > MAX_PIXELS
                        or image.mode != "RGB"
                        or getattr(image, "n_frames", 1) != 1
                    ):
                        raise BatchError("source_image_grid_conflict")
                    # Re-derive the canonical grid, rather than trusting a PNG-file hash or boxes.
                    with image.convert("RGBA") as rgba:
                        actual = grid_digest(rgba.width, rgba.height, rgba.tobytes())
        except (OSError, ValueError, image_module.DecompressionBombWarning):
            raise BatchError("source_image_decode_refused") from None
        if actual != page.page_sha256:
            raise BatchError("source_image_grid_conflict")
        return SourcePage(staged.page_png, revision, actual)
