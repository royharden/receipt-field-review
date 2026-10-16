"""App-local image/OCR/B0 join; BatchStore and the existing journal stay authoritative."""

import base64
import hashlib
import uuid
from datetime import date
from pathlib import Path

from rfr.ingest.images import decode_file, manifest_bytes, stage_image
from rfr.pipeline.files import batch_mutex, immutable, plain
from rfr.pipeline.models import ReceiptBundle
from rfr.pipeline.store import BatchStore
from rfr.ports.tesseract import NativeOcrError, TesseractOcr
from rfr.receipt.b0 import extract_b0
from rfr.receipt.models import ReceiptContext
from rfr.shared.docio.identity import canonical_bytes
from rfr.shared.docio.models import Bounds, Document, Provenance


def import_image(
    store: BatchStore,
    source: Path,
    executable: Path,
    tessdata: Path,
    reference_date: date,
    *,
    expected_revision: str | None = None,
    deadline_s: float = 30.0,
):
    """Import one owner-local image; native failures never register a blank/successful item."""
    if (
        type(reference_date) is not date
        or type(deadline_s) not in (int, float)
        or not 0 < deadline_s <= 60
    ):
        raise NativeOcrError("explicit_reference_date_and_bounded_deadline_required")
    with batch_mutex(store.root):
        manifest = store._manifest()
    decoded = decode_file(source)
    parent = store.root / "ocr"
    plain(parent, directory=True)
    directory = parent / ("native-" + uuid.uuid4().hex)
    port = TesseractOcr(decoded, directory, executable, tessdata)
    # Early admission avoids dispatching OCR for a known full/deleted/stale/unclean batch.
    # register() remains authoritative and repeats its checks under its own lock.
    with batch_mutex(store.root):
        manifest = store._manifest()
        item = port.page_input.document_id
        if item in manifest.items and manifest.items[item] is None:
            raise NativeOcrError("deleted_item_requires_new_identity")
        if item not in manifest.items and len(manifest.items) >= 100:
            raise NativeOcrError("batch_item_limit")
        if expected_revision is not None and manifest.items.get(item) != expected_revision:
            raise NativeOcrError("item_revision_conflict")
        if not store.journal.replay().can_append:
            raise NativeOcrError("journal_not_clean")
    # Existing originals and partial artifacts retain the staging boundary's no-overwrite policy.
    stage_image(store.root / "pages", decoded)
    directory.mkdir(mode=0o700)
    immutable(directory / "image-manifest.json", manifest_bytes(decoded.manifest))
    bounds = Bounds(
        max_pages=1,
        max_encoded_bytes=20 * 1024 * 1024,
        max_decoded_pixels=25000000,
        max_words=2000,
        max_lines=2000,
        max_blocks=2000,
        max_output_bytes=4194304,
        deadline_s=float(deadline_s),
    )
    result = port.recognize(port.page_input, bounds)
    if result.status != "ok":
        raise NativeOcrError(result.issues[0])
    raw = port.retained_artifact
    artifact_hash = hashlib.sha256(raw).hexdigest()
    document = Document(
        document_id=port.page_input.document_id,
        original_content_sha256=decoded.manifest.original_sha256,
        raw_source_revision=port.page_input.raw_source_revision,
        source_kind="image",
        pages=(result.page,),
        provenance=Provenance(
            producer="rfr-installed-tesseract",
            version="rfr-native-tesseract/1",
            config_sha256=hashlib.sha256(canonical_bytes(port.config)).hexdigest(),
            source_grid_profile="rgba8-source-grid-v1",
            refs=("image:" + decoded.manifest.original_sha256,),
        ),
    )
    receipt = extract_b0(
        document,
        raw,
        artifact_hash,
        ReceiptContext(currency=manifest.currency, reference_date=reference_date),
    )
    bundle = ReceiptBundle(
        document=document, receipt=receipt, artifact_base64=base64.b64encode(raw).decode("ascii")
    )
    immutable(directory / "bundle.json", canonical_bytes(bundle.model_dump(mode="json")))
    try:
        # An identical machine rerun can replay without requiring the caller to fetch a revision.
        # Different evidence still needs explicit CAS; BatchStore rechecks under its own lock.
        if expected_revision is None:
            with batch_mutex(store.root):
                current = store._manifest().items.get(document.document_id)
            if current == bundle.revision:
                expected_revision = current
        revision = store.register(bundle, expected_revision=expected_revision)
    except Exception:
        immutable(
            directory / "import.json",
            canonical_bytes({"status": "registration_failed_or_unknown"}),
        )
        raise
    summary = {
        "item_id": document.document_id,
        "revision": revision,
        "native_execution": directory.name,
        "status": "imported_review_required",
    }
    immutable(directory / "import.json", canonical_bytes({"status": "registered", **summary}))
    return summary
