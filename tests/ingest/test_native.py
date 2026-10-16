"""Synthetic adapter faults; actual installed OCR is a separate explicitly selected test."""

import io
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image", reason="optional images extra is not installed")

from rfr.export.receipt import export_receipts, write_export  # noqa: E402
from rfr.ingest.images import decode_bytes  # noqa: E402
from rfr.ingest.native import import_image  # noqa: E402
from rfr.pipeline.commands import draft_decision  # noqa: E402
from rfr.pipeline.files import atomic  # noqa: E402
from rfr.pipeline.store import BatchStore  # noqa: E402
from rfr.ports.tesseract import Capture, NativeOcrError, TesseractOcr  # noqa: E402
from rfr.receipt.models import CurrencyPolicy  # noqa: E402
from rfr.shared.docio.identity import canonical_bytes  # noqa: E402
from rfr.shared.docio.models import Bounds  # noqa: E402
from rfr.shared.docio.tsv import HEADER  # noqa: E402
from rfr.shared.rulings.models import RulingIntent  # noqa: E402


def source_image():
    out = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(out, format="PNG")
    return out.getvalue()


def bounds():
    return Bounds(
        max_pages=1,
        max_encoded_bytes=20971520,
        max_decoded_pixels=25000000,
        max_words=2000,
        max_lines=2000,
        max_blocks=2000,
        max_output_bytes=4194304,
        deadline_s=30.0,
    )


def engine_files(tmp_path):
    data = tmp_path / "models"
    data.mkdir()
    (data / "eng.traineddata").write_bytes(b"authored model marker, not an OCR model")
    (data / "configs").mkdir()
    (data / "configs/tsv").write_text("tessedit_create_tsv 1", encoding="utf-8")
    return data


def test_adapter_page_binding_is_normalized_and_never_uses_original_exif_again(tmp_path):
    decoded = decode_bytes(source_image())
    directory = tmp_path / "run"
    directory.mkdir()
    port = TesseractOcr(decoded, directory, Path(sys.executable), tmp_path)
    page = port.page_input
    assert (page.width_px, page.height_px) == (100, 60)
    assert page.grid_policy_id == "rgba8-source-grid-v1"
    result = port.recognize(page.model_copy(update={"page_sha256": "f" * 64}), bounds())
    assert result.status == "invalid" and result.page is None
    assert result.issues == ("native_input_binding",) and not port.execution["ocr_started"]
    with pytest.raises(NativeOcrError, match="native_adapter_already_used"):
        port.recognize(page, bounds())


@pytest.mark.parametrize("failure", ["missing", "timeout", "nonzero", "malformed"])
def test_native_failure_preserves_existing_batch_source_and_journal(failure, tmp_path, monkeypatch):
    data = engine_files(tmp_path)
    source = tmp_path / "PRIVATE_SOURCE.png"
    source.write_bytes(source_image())
    private = tmp_path / "private"
    private.mkdir()
    store = BatchStore.create(private, CurrencyPolicy())
    before = {
        p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*") if p.is_file()
    }

    def capture(command, directory, timeout_s, output_limit):
        if command[-1] == "--version":
            return Capture("ok", 0, b"tesseract v5.5-test\n", b"", 0.01, 1, True)
        if failure == "timeout":
            return Capture("timeout", -1, b"", b"PRIVATE_NATIVE_DETAIL", 0.3, 1, True)
        if failure == "nonzero":
            return Capture("invalid", 3, b"", b"PRIVATE_NATIVE_DETAIL", 0.01, 1, True)
        return Capture("ok", 0, b"PRIVATE_MALFORMED_TSV", b"", 0.01, 1, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    executable = tmp_path / "missing-engine" if failure == "missing" else Path(sys.executable)
    with pytest.raises(NativeOcrError) as refused:
        import_image(store, source, executable, data, date(2026, 10, 16))
    assert "PRIVATE" not in str(refused.value)
    assert {p: (store.root / p).read_bytes() for p in before} == before
    assert not store.list_items()
    run = next((store.root / "ocr").iterdir())
    result = json.loads((run / "execution.json").read_bytes())
    assert result["status"] != "ok" and not (run / "artifact.json").exists()
    assert source.read_bytes() == source_image()


def test_blank_tsv_is_genuine_empty_page_not_a_failed_stage(tmp_path, monkeypatch):
    data = engine_files(tmp_path)
    directory = tmp_path / "run"
    directory.mkdir()
    port = TesseractOcr(decode_bytes(source_image()), directory, Path(sys.executable), data)

    def capture(command, *args):
        raw = (
            b"tesseract v5.5-test\n"
            if command[-1] == "--version"
            else (HEADER + b"\n1\t1\t0\t0\t0\t0\t0\t0\t100\t60\t-1\t\n")
        )
        return Capture("ok", 0, raw, b"", 0.01, 1, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    result = port.recognize(port.page_input, bounds())
    assert result.status == "ok" and result.page.words == () and port.retained_artifact
    assert json.loads((directory / "execution.json").read_bytes())["ocr_started"] is True


def test_slow_startup_uses_overall_budget_without_resetting_ocr_deadline(tmp_path, monkeypatch):
    data = engine_files(tmp_path)
    directory = tmp_path / "run"
    directory.mkdir()
    port = TesseractOcr(decode_bytes(source_image()), directory, Path(sys.executable), data)
    clock, limits = [0.0], []
    monkeypatch.setattr("rfr.ports.tesseract.time.monotonic", lambda: clock[0])

    def capture(command, directory, timeout_s, output_limit):
        limits.append(timeout_s)
        if command[-1] == "--version":
            if timeout_s < 12:
                clock[0] += timeout_s
                return Capture("timeout", -1, b"", b"", timeout_s, 1, True)
            clock[0] += 12
            return Capture("ok", 0, b"tesseract v5.5-test\n", b"", 12, 1, True)
        clock[0] += 3
        raw = HEADER + b"\n1\t1\t0\t0\t0\t0\t0\t0\t100\t60\t-1\t\n"
        return Capture("ok", 0, raw, b"", 3, 1, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    result = port.recognize(port.page_input, bounds())
    assert result.status == "ok" and result.page is not None
    assert limits[0] <= 30 and limits[1] <= 18 and clock[0] == 15


def test_exhausted_total_budget_never_dispatches_ocr(tmp_path, monkeypatch):
    data = engine_files(tmp_path)
    directory = tmp_path / "run"
    directory.mkdir()
    port = TesseractOcr(decode_bytes(source_image()), directory, Path(sys.executable), data)
    clock, calls = [0.0], []
    monkeypatch.setattr("rfr.ports.tesseract.time.monotonic", lambda: clock[0])

    def capture(command, *args):
        calls.append(command)
        assert command[-1] == "--version"
        clock[0] = 30
        return Capture("ok", 0, b"tesseract v5.5-test\n", b"", 30, 1, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    result = port.recognize(port.page_input, bounds())
    assert result.status == "timeout" and result.page is None and len(calls) == 1
    assert result.issues == ("native_ocr_timeout",) and not port.execution["ocr_started"]


@pytest.mark.parametrize("state", ["full", "deleted", "stale", "journal"])
def test_known_batch_refusal_precedes_native_dispatch_and_retention(state, tmp_path, monkeypatch):
    data = engine_files(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(source_image())
    private = tmp_path / "private"
    private.mkdir()
    store = BatchStore.create(private, CurrencyPolicy())
    item = TesseractOcr(
        decode_bytes(source_image()), tmp_path, Path(sys.executable), data
    ).page_input.document_id
    manifest = store._manifest()
    if state == "full":
        manifest = manifest.model_copy(
            update={"items": {f"other:{i}": "a" * 64 for i in range(100)}}
        )
    elif state == "deleted":
        manifest = manifest.model_copy(update={"items": {item: None}})
    if state in {"full", "deleted"}:
        atomic(store.root / "manifest.json", canonical_bytes(manifest.model_dump(mode="json")))
    if state == "journal":
        (store.root / "rulings.jsonl").write_bytes(b"{damaged tail")
    before = {
        p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*") if p.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("native dispatch must not occur")

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", forbidden)
    with pytest.raises(NativeOcrError):
        import_image(
            store,
            source,
            Path(sys.executable),
            data,
            date(2026, 10, 16),
            expected_revision="b" * 64 if state == "stale" else None,
        )
    assert {p: (store.root / p).read_bytes() for p in before} == before
    assert not list((store.root / "pages").iterdir())
    assert not list((store.root / "ocr").iterdir())


@pytest.mark.native_ocr
def test_actual_installed_native_import_review_retry_rerun_and_reopen(tmp_path):
    executable = os.environ.get("RFR_TEST_TESSERACT")
    data = os.environ.get("RFR_TEST_TESSDATA")
    if not executable or not data:
        pytest.skip("explicit installed Tesseract and model paths are required")
    from PIL import ImageDraw, ImageFont

    image = Image.new("RGB", (1000, 800), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(os.environ["RFR_TEST_FONT"], 40)
    text = [
        "Merchant: SYNTHETIC SHOP",
        "DATE 2026-10-14",
        "CURRENCY USD",
        "Coffee 2 x 3.00 6.00",
        "Cake 4.00",
        "SUBTOTAL 10.00",
        "TAX 1.00",
        "TOTAL 11.00",
        "VISA",
    ]
    for index, line in enumerate(text):
        draw.text((35, 35 + index * 75), line, fill="black", font=font)
    source = tmp_path / "authored-native-receipt.png"
    image.save(source)
    private = tmp_path / "private"
    private.mkdir()
    store = BatchStore.create(private, CurrencyPolicy())
    command = [
        sys.executable,
        "-m",
        "rfr.cli",
        "--root",
        str(private),
        "import-image",
        "--batch",
        store.batch_id,
        "--source",
        str(source),
        "--tesseract",
        executable,
        "--tessdata",
        data,
        "--reference-date",
        "2026-10-16",
    ]

    def run():
        result = subprocess.run(command, capture_output=True, text=True, timeout=75)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    summary = run()
    item, revision = summary["item_id"], summary["revision"]
    bundle = store.bundle(item)
    assert bundle.receipt.fields["total"].proposal == "11.00"
    assert bundle.document.pages[0].words
    assert all(w.geometry_provenance == "measured_ocr" for w in bundle.document.pages[0].words)
    draft = draft_decision(
        store,
        item=item,
        field="merchant_name",
        action="correct",
        value="Reviewed native shop",
        reason="authored native functional control",
        actor="synthetic-controller",
        actor_kind="agent_provisional",
    )
    intent = RulingIntent.model_validate_json(json.dumps(draft["intent"]))
    first = store.decide(intent, expected_item_revision=draft["expected_item_revision"])
    retry = store.decide(intent, expected_item_revision=draft["expected_item_revision"])
    assert first.outcome == "appended" and retry.outcome == "exact_retry"
    again = run()
    assert again["revision"] == revision
    reopened = BatchStore(private, store.batch_id)
    assert (
        reopened.detail(item)["fields"]["merchant_name"]["effective_value"]
        == "Reviewed native shop"
    )
    assert reopened.bundle(item).document == bundle.document
    files = export_receipts(reopened, mode="review")
    target = write_export(tmp_path, files)
    exported = json.loads((target / "receipts.jsonl").read_bytes())
    assert exported["item_id"] == item
    assert b"Reviewed native shop" in files["receipts.jsonl"]
    assert json.loads(export_receipts(reopened, mode="clean")["omitted.json"])["exported_N"] == 0
