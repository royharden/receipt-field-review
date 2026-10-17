"""Authored pixels through local staging/Docio and ASGI; native OCR is explicitly injected."""

import io
import json
import os
import struct
import sys
import zlib
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

Image = pytest.importorskip("PIL.Image", reason="optional image decoder is not installed")

from rfr.api.app import create_app  # noqa: E402
from rfr.api.operations import ReviewOperations  # noqa: E402
from rfr.ingest.images import digest, load_staged  # noqa: E402
from rfr.ingest.native import import_image  # noqa: E402
from rfr.pipeline.store import BatchStore  # noqa: E402
from rfr.ports.tesseract import Capture  # noqa: E402
from rfr.receipt.models import CurrencyPolicy  # noqa: E402
from rfr.shared.docio.tsv import HEADER  # noqa: E402

ORIGIN = "http://127.0.0.1:24002"
TOKEN = "synthetic-image-test-capability-00000"


def client(root):
    return TestClient(
        create_app(root, origin=ORIGIN, capability=TOKEN),
        base_url=ORIGIN,
        headers={"X-RFR-Token": TOKEN, "Origin": ORIGIN},
    )


@pytest.fixture
def native_item(tmp_path, monkeypatch):
    # Real decoding/staging and canonical bundle registration; no native subprocess/model.
    original = io.BytesIO()
    exif = Image.Exif()
    exif[270] = "PRIVATE_ORIGINAL_METADATA"
    Image.new("RGBA", (12, 8), (240, 10, 20, 128)).save(original, format="PNG", exif=exif)
    source = tmp_path / "source.png"
    source.write_bytes(original.getvalue())
    data = tmp_path / "models"
    (data / "configs").mkdir(parents=True)
    (data / "eng.traineddata").write_bytes(b"synthetic model marker")
    (data / "configs/tsv").write_bytes(b"synthetic config marker")

    def capture(command, *args):
        raw = (
            b"tesseract v5.5-test\n"
            if command[-1] == "--version"
            else HEADER + b"\n1\t1\t0\t0\t0\t0\t0\t0\t12\t8\t-1\t\n"
        )
        return Capture("ok", 0, raw, b"", 0.01, 1, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    private = tmp_path / "private"
    private.mkdir()
    store = BatchStore.create(private, CurrencyPolicy())
    summary = import_image(
        store, source, Path(sys.executable).resolve(strict=True), data, date(2026, 10, 16)
    )
    bundle = store.bundle(summary["item_id"])
    staged = load_staged(store.root / "pages", bundle.document.original_content_sha256)
    url = (
        f"/api/batches/{store.batch_id}/items/{summary['item_id']}/page"
        f"?revision={summary['revision']}"
    )
    return private, store, bundle, staged, url


def snapshot(store):
    return {p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*") if p.is_file()}


def test_source_page_http_returns_only_bound_normalized_pixels_and_reopens(native_item):
    private, store, bundle, staged, url = native_item
    before = snapshot(store)
    for _ in range(2):
        with client(private) as c:
            response = c.get(url)
            assert response.status_code == 200, response.text
            assert response.content == staged.page_png
            assert b"PRIVATE_ORIGINAL_METADATA" not in response.content
            assert response.headers["content-type"] == "image/png"
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-rfr-item-revision"] == bundle.revision
            assert response.headers["x-rfr-page-sha256"] == bundle.document.pages[0].page_sha256
            detail = c.get(url.split("/page?")[0]).json()
            assert detail["image_available"] is True
            with Image.open(io.BytesIO(response.content)) as image:
                assert image.size == (12, 8) and image.mode == "RGB" and not image.getexif()
    assert snapshot(store) == before


@pytest.mark.parametrize("fault", ["missing-token", "foreign-host", "foreign-origin"])
def test_source_page_admission_precedes_private_reads(tmp_path, monkeypatch, fault):
    # No registered image/batch is needed: admission must refuse before storage is touched.
    url = f"/api/batches/{'a' * 32}/items/private-item/page?revision={'b' * 64}"

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized source read")

    monkeypatch.setattr(ReviewOperations, "source_page", forbidden)
    with client(tmp_path) as c:
        headers = {
            "missing-token": {"X-RFR-Token": ""},
            "foreign-host": {"Host": "attacker.invalid"},
            "foreign-origin": {"Origin": "https://attacker.invalid"},
        }[fault]
        response = c.get(url, headers=headers)
        assert response.status_code == (401 if fault == "missing-token" else 403)
        assert response.headers["cache-control"] == "no-store"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "stale",
        "missing",
        "deleted",
        "corrupt-png",
        "grid",
        "link",
        "metadata",
        "trailing",
        "header-only",
        "oversize",
        "bad-revision",
        "no-revision",
    ],
)
def test_source_page_refusals_preserve_all_private_bytes(native_item, fault):
    private, store, bundle, staged, url = native_item
    folder = store.root / "pages" / ("image-" + staged.manifest.original_sha256)
    if fault == "stale":
        url = url.replace(bundle.revision, "f" * 64)
    elif fault == "bad-revision":
        url = url.replace(bundle.revision, "invalid")
    elif fault == "no-revision":
        url = url.split("?")[0]
    elif fault == "deleted":
        store.delete(bundle.document.document_id, expected_revision=bundle.revision)
    elif fault == "missing":
        (folder / "page.png").unlink()
    elif fault == "corrupt-png":
        (folder / "page.png").write_bytes(b"PRIVATE_TAMPERED_IMAGE")
    elif fault == "link":
        os.link(folder / "page.png", private / "linked.png")
    elif fault == "oversize":
        manifest = json.loads((folder / "manifest.json").read_bytes())
        manifest["page_bytes"] = 80 * 1024 * 1024 + 1
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        # A complete, hash-consistent replacement image must still match Docio's pixel grid.
        output = io.BytesIO()
        Image.new("RGB", (12, 8), "blue").save(output, format="PNG")
        raw = output.getvalue()
        if fault == "metadata":
            data = b"Comment\0PRIVATE_ANCILLARY_METADATA"
            chunk = b"tEXt" + data
            raw = staged.page_png[:33] + struct.pack(">I", len(data)) + chunk
            raw += struct.pack(">I", zlib.crc32(chunk)) + staged.page_png[33:]
        elif fault == "trailing":
            raw = staged.page_png + b"PRIVATE_TRAILING_DATA"
        elif fault == "header-only":
            raw = staged.page_png[:33]
        (folder / "page.png").write_bytes(raw)
        manifest = json.loads((folder / "manifest.json").read_bytes())
        manifest.update(page_sha256=digest(raw), page_bytes=len(raw))
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = snapshot(store)
    with client(private) as c:
        response = c.get(url)
        assert response.status_code in ({409} if fault == "stale" else {400, 404})
        assert "PRIVATE" not in response.text and str(private) not in response.text
        assert response.headers["cache-control"] == "no-store"
        if fault not in {"stale", "deleted", "bad-revision", "no-revision"}:
            detail = c.get(url.split("/page?")[0])
            assert detail.status_code == 200
            assert detail.json()["image_available"] is False
    assert snapshot(store) == before


def test_source_decoder_missing_refuses_page_but_keeps_text_review(native_item, monkeypatch):
    import rfr.api.source_images as sources

    private, store, _, _, url = native_item
    before = snapshot(store)
    original_import = sources.importlib.import_module

    def missing(name, *args, **kwargs):
        if name == "PIL.Image":
            raise ImportError("PRIVATE_DECODER_PATH")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(sources.importlib, "import_module", missing)
    with client(private) as c:
        response = c.get(url)
        assert response.status_code == 503
        assert response.json() == {"error": "source_image_decoder_unavailable"}
        detail = c.get(url.split("/page?")[0])
        assert detail.status_code == 200 and detail.json()["image_available"] is False
    assert snapshot(store) == before


def test_supplied_recognized_bundle_without_local_pixels_has_no_source_image(
    tmp_path, bundle_factory
):
    bundle = bundle_factory()
    store = BatchStore.create(tmp_path, CurrencyPolicy())
    revision = store.register(bundle, expected_revision=None)
    with client(tmp_path) as c:
        response = c.get(
            f"/api/batches/{store.batch_id}/items/{bundle.document.document_id}/page",
            params={"revision": revision},
        )
        assert response.status_code == 404
