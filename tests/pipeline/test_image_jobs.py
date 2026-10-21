"""Authored pixels and injected native responses, never actual OCR or receipt accuracy."""

import hashlib
import json
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event

import pytest

from rfr.ingest.images import decode_bytes, stage_image
from rfr.pipeline.files import BatchError
from rfr.pipeline.image_worker import ImageWorker
from rfr.pipeline.job_models import ImageJobInput, ImageJobSpec, JobRecord, JobSpec
from rfr.pipeline.jobs import JobStore
from rfr.ports.tesseract import Capture
from rfr.shared.docio.tsv import HEADER

DAY = date(2026, 10, 14)


def pixels(color):
    def chunk(tag, raw):
        return struct.pack(">I", len(raw)) + tag + raw + struct.pack(">I", zlib.crc32(tag + raw))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 100, 60, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + bytes([color]) * 300) * 60))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def inputs(batch):
    pytest.importorskip("PIL.Image", reason="image job decoding needs optional images extra")
    result = {}
    for color in (100, 200):
        decoded = decode_bytes(pixels(color))
        stage_image(batch.root / "pages", decoded)
        digest = decoded.manifest.original_sha256
        result["receipt-image:" + digest] = ImageJobInput(original_sha256=digest)
    return result


@pytest.fixture
def worker(tmp_path, monkeypatch):
    engine = tmp_path / "trusted-engine.exe"
    engine.write_bytes(b"authored engine marker, not executable code")
    (tmp_path / "trusted.dll").write_bytes(b"authored library marker")
    data = tmp_path / "tessdata"
    data.mkdir()
    (data / "eng.traineddata").write_bytes(b"authored model marker")
    (data / "configs").mkdir()
    (data / "configs" / "tsv").write_bytes(b"tessedit_create_tsv 1")
    result = ImageWorker(engine, data)

    def capture(command, *args):
        raw = (
            b"tesseract v5.5-test\n"
            if command[-1] == "--version"
            else HEADER + b"\n1\t1\t0\t0\t0\t0\t0\t0\t100\t60\t-1\t\n"
        )
        return Capture("ok", 0, raw, b"", 0.01, 123, True)

    monkeypatch.setattr("rfr.ports.tesseract.bounded_command", capture)
    monkeypatch.setattr(
        "subprocess.Popen", lambda *a, **kw: pytest.fail("no native process in image-job controls")
    )
    return result


def queued(batch, inputs, worker, request="images-1"):
    jobs = JobStore(batch)
    spec = ImageJobSpec(images=inputs, reference_date=DAY)
    return jobs, jobs.start(request, spec, image_worker=worker)


def test_sequential_image_join_persists_every_item_and_exact_retry_never_reexecutes(
    batch, inputs, worker, monkeypatch
):
    jobs, record = queued(batch, inputs, worker)
    calls = []
    original = ImageWorker.execute

    def execute(self, store, image, day, *, expected_engine_sha256):
        calls.append(image.original_sha256)
        # Each preceding result has already been durably published before the next call.
        current = jobs.get(record.job_id)
        assert sum(p.status == "ok" for p in current.items.values()) == len(calls) - 1
        return original(self, store, image, day, expected_engine_sha256=expected_engine_sha256)

    monkeypatch.setattr(ImageWorker, "execute", execute)
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "complete" and len(calls) == 2
    assert result.execution_origin == "local_image_pipeline" and result.model_cost_usd is None
    assert result.model_cost_status == "not_applicable"
    for item, progress in result.items.items():
        assert progress.result_revision == batch.bundle(item).revision
        assert batch.bundle(item).document.original_content_sha256 == inputs[item].original_sha256
    assert jobs.start(record.request_id, record.spec) == result
    assert jobs.run(record.job_id, image_worker=worker) == result and len(calls) == 2
    with pytest.raises(BatchError, match="intent_conflict"):
        jobs.start(
            record.request_id,
            ImageJobSpec(images=inputs, reference_date=date(2026, 10, 15)),
            image_worker=worker,
        )


def test_image_and_recognized_jobs_share_one_active_worker(batch, inputs, worker):
    jobs, record = queued(batch, inputs, worker)
    with pytest.raises(BatchError, match="already_active"):
        jobs.start("recognized", JobSpec(method="B0", source_revisions={"other": "a" * 64}))
    result = jobs.recover_interrupted(record.job_id)
    assert {p.status for p in result.items.values()} == {"not_run"}
    # An interrupted image job does not poison the shared active marker for old job specs.
    assert jobs.start("recognized", JobSpec(method="B0", source_revisions={"other": "a" * 64}))


@pytest.mark.parametrize("damage", ["oversize", "hash", "hardlink", "missing"])
def test_staged_image_refusal_precedes_job_publication(batch, inputs, worker, damage):
    digest = next(iter(inputs.values())).original_sha256
    folder = batch.root / "pages" / ("image-" + digest)
    source = folder / "original.bin"
    if damage == "oversize":
        with source.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
    elif damage == "hash":
        source.write_bytes(pixels(50))
    elif damage == "hardlink":
        # A second link is forbidden even if every retained byte still matches.
        (batch.root / "linked-original").hardlink_to(source)
    else:
        source.unlink()
    jobs = JobStore(batch)
    with pytest.raises((ValueError, BatchError, OSError)):
        jobs.start(
            "bad-image", ImageJobSpec(images=inputs, reference_date=DAY), image_worker=worker
        )
    assert not (jobs.folder / "active.json").exists()
    assert not (jobs.folder / (hashlib.sha256(b"bad-image").hexdigest() + ".json")).exists()


def test_changed_staged_bytes_and_engine_fail_closed_before_dispatch(batch, inputs, worker):
    jobs, record = queued(batch, inputs, worker)
    worker.executable.write_bytes(b"changed engine")
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "failed" and result.execution_origin == "not_run"
    assert {p.status for p in result.items.values()} == {"unavailable"}
    assert not batch._manifest().items


def test_changed_staged_bytes_after_queue_remain_failure_without_native_dispatch(
    batch, inputs, worker, monkeypatch
):
    jobs, record = queued(batch, inputs, worker)
    for image in inputs.values():
        source = batch.root / "pages" / ("image-" + image.original_sha256) / "original.bin"
        source.write_bytes(pixels(50))
    monkeypatch.setattr(
        ImageWorker,
        "execute",
        lambda *a, **kw: pytest.fail("changed retained bytes cannot dispatch"),
    )
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "failed" and result.execution_origin == "not_run"
    assert {p.status for p in result.items.values()} == {"unavailable"}


def test_missing_worker_never_marks_image_execution_started(batch, inputs, worker):
    jobs, record = queued(batch, inputs, worker)
    result = jobs.run(record.job_id)
    assert result.state == "failed" and result.execution_origin == "not_run"
    assert {p.status for p in result.items.values()} == {"unavailable"}


@pytest.mark.parametrize("component", ["executable", "model", "dll", "tsv-config"])
def test_engine_replacement_after_job_preflight_before_native_snapshot_refuses_persistence(
    batch, inputs, worker, monkeypatch, component
):
    """S2-IMG-001: a stable replacement during decode must not register under queued A."""
    import rfr.ingest.native as native_import

    item = next(iter(inputs))
    jobs, record = queued(batch, {item: inputs[item]}, worker)
    manifest_before = batch._manifest()
    original_decode = native_import.decode_file
    replacements = {
        "executable": worker.executable,
        "model": worker.tessdata / "eng.traineddata",
        "dll": worker.executable.parent / "trusted.dll",
        "tsv-config": worker.tessdata / "configs" / "tsv",
    }
    decoded = []

    def replace_during_decode(source):
        # Reaching this boundary proves the job's per-item fingerprint already matched A.
        assert jobs.get(record.job_id).items[item].status == "running"
        result = original_decode(source)
        replacements[component].write_bytes(b"stable replacement B after job preflight")
        decoded.append(source)
        return result

    monkeypatch.setattr(native_import, "decode_file", replace_during_decode)
    monkeypatch.setattr(
        "rfr.ports.tesseract.bounded_command",
        lambda *a, **kw: pytest.fail("queued engine drift must precede native dispatch"),
    )
    result = jobs.run(record.job_id, image_worker=worker)
    assert len(decoded) == 1 and result.state == "failed"
    assert result.execution_config_sha256 == record.execution_config_sha256
    assert result.items[item].status == "unavailable"
    assert result.items[item].result_revision is None
    assert batch._manifest() == manifest_before
    run = next((batch.root / "ocr").iterdir())
    execution = json.loads((run / "execution.json").read_bytes())
    assert execution["issue"] == "native_queued_engine_identity_changed"
    assert not execution["ocr_started"] and execution["commands"] == []
    assert not (run / "artifact.json").exists()
    assert not (run / "bundle.json").exists() and not (run / "import.json").exists()
    # The failed exact retry stays terminal and never decodes/executes again.
    assert jobs.start(record.request_id, record.spec) == result
    assert jobs.run(record.job_id, image_worker=worker) == result and len(decoded) == 1


def test_importer_refuses_mismatched_success_provenance_before_bundle_publication(
    batch, inputs, worker, monkeypatch
):
    """S2-IMG-001: success alone cannot bypass the importer's queued identity check."""
    from rfr.ports.tesseract import TesseractOcr

    item = next(iter(inputs))
    jobs, record = queued(batch, {item: inputs[item]}, worker)
    manifest_before = batch._manifest()
    recognize = TesseractOcr.recognize

    def mismatched_provenance(self, page, bounds):
        result = recognize(self, page, bounds)
        assert result.status == "ok"
        self.config["executable_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(TesseractOcr, "recognize", mismatched_provenance)
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "failed" and result.items[item].status == "unavailable"
    assert batch._manifest() == manifest_before
    run = next((batch.root / "ocr").iterdir())
    assert (run / "artifact.json").exists()  # Injected native output is retained, not imported.
    assert not (run / "bundle.json").exists() and not (run / "import.json").exists()


def test_engine_drift_between_items_refuses_remaining_dispatch(batch, inputs, worker, monkeypatch):
    jobs, record = queued(batch, inputs, worker)
    original = ImageWorker.execute
    calls = []

    def execute(self, store, image, day, *, expected_engine_sha256):
        calls.append(image.original_sha256)
        result = original(self, store, image, day, expected_engine_sha256=expected_engine_sha256)
        self.executable.write_bytes(b"changed after first completed item")
        return result

    monkeypatch.setattr(ImageWorker, "execute", execute)
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "partial" and len(calls) == 1
    assert sorted(p.status for p in result.items.values()) == ["ok", "unavailable"]


def test_source_revision_cas_refuses_new_image_rerun_without_current_revision(
    batch, inputs, worker, monkeypatch
):
    jobs, first = queued(batch, inputs, worker)
    assert jobs.run(first.job_id, image_worker=worker).state == "complete"
    before = batch._manifest()
    next_job = jobs.start("second-image-intent", first.spec, image_worker=worker)
    monkeypatch.setattr(
        ImageWorker,
        "execute",
        lambda *a, **kw: pytest.fail("existing source requires explicit CAS"),
    )
    result = jobs.run(next_job.job_id, image_worker=worker)
    assert {p.status for p in result.items.values()} == {"stale"}
    assert result.execution_origin == "not_run" and batch._manifest() == before


def test_per_item_failure_keeps_fixed_cohort_and_continues_sequentially(
    batch, inputs, worker, monkeypatch
):
    jobs, record = queued(batch, inputs, worker)
    original = ImageWorker.execute
    first_item = sorted(inputs)[0]
    first = inputs[first_item].original_sha256

    def execute(self, store, image, day, *, expected_engine_sha256):
        if image.original_sha256 == first:
            raise RuntimeError("private decoder details must not enter job state")
        return original(self, store, image, day, expected_engine_sha256=expected_engine_sha256)

    monkeypatch.setattr(ImageWorker, "execute", execute)
    result = jobs.run(record.job_id, image_worker=worker)
    assert result.state == "partial" and set(result.items) == set(inputs)
    assert result.items[first_item].status == "error"
    assert sorted(p.status for p in result.items.values()) == ["error", "ok"]
    assert "private decoder" not in result.model_dump_json()


def test_interruption_and_duplicate_claim_never_auto_repeat_image_execution(
    batch, inputs, worker, monkeypatch
):
    jobs, record = queued(batch, inputs, worker)
    entered, release = Event(), Event()
    calls = []

    def execute(self, store, image, day, *, expected_engine_sha256):
        calls.append(image.original_sha256)
        entered.set()
        assert release.wait(5)
        raise KeyboardInterrupt("synthetic interrupted native result")

    monkeypatch.setattr(ImageWorker, "execute", execute)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(jobs.run, record.job_id, image_worker=worker)
        assert entered.wait(5)
        assert JobStore(batch).run(record.job_id, image_worker=worker).state == "running"
        release.set()
        with pytest.raises(KeyboardInterrupt):
            future.result(timeout=10)
    result = JobStore(batch).recover_interrupted(record.job_id)
    assert {p.status for p in result.items.values()} == {"unknown_interrupted", "not_run"}
    assert jobs.run(record.job_id, image_worker=worker) == result and len(calls) == 1


def test_image_intent_wire_refuses_paths_duplicate_identities_and_oversized_cohort():
    image = ImageJobInput(original_sha256="a" * 64)
    with pytest.raises(ValueError):
        ImageJobSpec(images={"../client-path": image}, reference_date=DAY)
    with pytest.raises(ValueError):
        ImageJobInput(original_sha256="a" * 64, executable="client.exe")
    with pytest.raises(ValueError):
        ImageJobSpec(
            images={
                "receipt-image:" + f"{i:064x}": ImageJobInput(original_sha256=f"{i:064x}")
                for i in range(101)
            },
            reference_date=DAY,
        )
    with pytest.raises(ValueError):
        ImageWorker(Path("relative.exe"), Path("relative-models"))


def test_stored_image_wire_cannot_claim_rules_origin_or_lose_cohort(batch, inputs, worker):
    _, record = queued(batch, inputs, worker)
    payload = record.model_dump(mode="json")
    payload.update(execution_origin="local_rules", model_cost_status="not_applicable")
    with pytest.raises(ValueError):
        JobRecord.model_validate_json(json.dumps(payload))
