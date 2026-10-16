"""Actual local child lifecycle controls; Python workers are not OCR evidence."""

import os
import sys

import pytest

from rfr.ports.tesseract import NativeOcrError, bounded_command


def test_actual_child_capture_and_nonzero_have_bounded_private_outputs(tmp_path):
    result = bounded_command(
        [sys.executable, "-c", "import sys;print('value');sys.stderr.write('PRIVATE');sys.exit(3)"],
        tmp_path,
        10.0,
        100,
    )
    assert result.status == "invalid" and result.exit_code == 3
    assert result.stdout.strip() == b"value" and result.stderr == b"PRIVATE"
    assert result.pid is not None and result.cleanup_complete


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_actual_output_flood_is_bounded_and_child_reaped(stream, tmp_path):
    result = bounded_command(
        [sys.executable, "-c", f"import sys;sys.{stream}.buffer.write(b'x'*1000000)"],
        tmp_path,
        10.0,
        128,
    )
    assert result.status == "limit_exceeded" and result.cleanup_complete
    assert len(result.stdout) <= 128 and len(result.stderr) <= 16384


def test_actual_hung_child_hits_deadline_and_is_reaped(tmp_path):
    result = bounded_command(
        [sys.executable, "-c", "import time;time.sleep(30)"],
        tmp_path,
        0.3,
        100,
    )
    assert result.status == "timeout" and result.cleanup_complete
    assert result.exit_code is not None and result.elapsed_s < 10


def test_missing_executable_and_environment_containment(tmp_path, monkeypatch):
    result = bounded_command([str(tmp_path / "PRIVATE_missing_engine")], tmp_path, 1.0, 100)
    assert result.status == "unavailable" and result.pid is None
    assert not result.stdout and not result.stderr and result.cleanup_complete
    monkeypatch.setenv("OPENAI_API_KEY", "AUTHORED_CANARY")
    result = bounded_command(
        [
            sys.executable,
            "-c",
            "import os;print('OPENAI_API_KEY' in os.environ);print(os.environ['OMP_THREAD_LIMIT'])",
        ],
        tmp_path,
        10.0,
        100,
    )
    assert result.status == "ok" and result.stdout.splitlines() == [b"False", b"1"]
    assert os.environ["OPENAI_API_KEY"] == "AUTHORED_CANARY"


@pytest.mark.parametrize("timeout,limit", [(True, 10), (float("inf"), 10), (1, True), (1, 4194305)])
def test_command_bounds_cannot_be_widened(timeout, limit, tmp_path):
    with pytest.raises(NativeOcrError, match="native_command_bounds"):
        bounded_command([sys.executable], tmp_path, timeout, limit)


def test_cli_missing_image_extra_keeps_actionable_closed_diagnostic(tmp_path, monkeypatch, capsys):
    import importlib
    import json

    from rfr.cli import main
    from rfr.pipeline.store import BatchStore
    from rfr.receipt.models import CurrencyPolicy

    private = tmp_path / "private"
    private.mkdir()
    store = BatchStore.create(private, CurrencyPolicy())
    source = tmp_path / "PRIVATE_SOURCE.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    original_import = importlib.import_module

    def missing_decoder(name, *args, **kwargs):
        if name.startswith("PIL"):
            raise ImportError("PRIVATE_ENV_DETAIL")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("rfr.ingest.images.importlib.import_module", missing_decoder)
    status = main(
        [
            "--root",
            str(private),
            "import-image",
            "--batch",
            store.batch_id,
            "--source",
            str(source),
            "--tesseract",
            "unused",
            "--tessdata",
            "unused",
            "--reference-date",
            "2026-10-16",
        ]
    )
    captured = capsys.readouterr()
    assert status == 2 and not captured.out
    assert json.loads(captured.err) == {"error": "image_decoder_unavailable_install_images_extra"}
    assert not store.list_items()
