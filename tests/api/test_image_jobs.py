"""Authored PNG/fake native controls for HTTP image ownership; no listener or actual OCR."""

import asyncio
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from rfr.api.app import create_app
from rfr.api.body import BinaryBody
from rfr.api.image_jobs import ImageJobs
from rfr.api.models import ImageJobStart
from rfr.api.security import IMAGE_BODY_LIMIT, RequestGuard, RequestRefused
from rfr.pipeline.files import BatchError
from rfr.pipeline.image_worker import ImageWorker
from rfr.pipeline.job_models import ImageJobInput, ImageJobSpec
from rfr.pipeline.jobs import JobStore

spec = importlib.util.spec_from_file_location(
    "own_image_job_api_controls", Path(__file__).parents[1] / "pipeline/test_image_jobs.py"
)
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)
worker = controls.worker
inputs = controls.inputs
pixels = controls.pixels

ORIGIN = "http://127.0.0.1:24002"
TOKEN = "synthetic-test-capability-0000000000"
HEADERS = {"X-RFR-Token": TOKEN, "Origin": ORIGIN}
RAW = [
    (b"host", b"127.0.0.1:24002"),
    (b"x-rfr-token", TOKEN.encode()),
    (b"origin", ORIGIN.encode()),
    (b"content-type", b"application/octet-stream"),
]
PATH = "/api/batches/" + "a" * 32 + "/images/" + "b" * 64


def request_for(images, name="image-api-1"):
    return ImageJobStart(
        request_id=name, spec=ImageJobSpec(images=images, reference_date=date(2026, 10, 14))
    )


def test_binary_exception_exact_route_and_json_ceiling():
    guard = RequestGuard(ORIGIN, TOKEN, 100)
    guard.authorize("PUT", RAW + [(b"content-length", str(IMAGE_BODY_LIMIT).encode())], path=PATH)
    for method, path in [
        ("POST", PATH),
        ("PUT", PATH + "/"),
        ("PUT", PATH.upper()),
        ("PUT", "/api/batches"),
    ]:
        with pytest.raises(RequestRefused, match="json_content_type_required"):
            guard.authorize(method, RAW, path=path)
    with pytest.raises(ValueError, match="bounded_body_policy"):
        RequestGuard(ORIGIN, TOKEN, 25 * 1024 * 1024 + 1)
    with pytest.raises(RequestRefused, match="request_body_limit"):
        guard.authorize(
            "PUT", RAW + [(b"content-length", str(IMAGE_BODY_LIMIT + 1).encode())], path=PATH
        )


@pytest.mark.parametrize(
    "case", ["bytes", "messages", "length-short", "length-long", "disconnect", "wrong-type"]
)
def test_binary_actual_stream_limits_and_failed_terminal_state(case):
    headers = RAW + ([(b"content-length", b"3")] if case.startswith("length") else [])
    body = BinaryBody(RequestGuard(ORIGIN, TOKEN), "PUT", headers, path=PATH, max_messages=1)
    with pytest.raises(RequestRefused):
        if case == "bytes":
            body.feed({"type": "http.request", "body": b"x" * (IMAGE_BODY_LIMIT + 1)})
        elif case == "messages":
            body.feed({"type": "http.request", "body": b"x", "more_body": True})
            body.feed({"type": "http.request", "body": b"x"})
        elif case == "disconnect":
            body.feed({"type": "http.disconnect"})
        else:
            body.feed(
                {
                    "type": "http.request",
                    "body": b"xx"
                    if case == "length-short"
                    else b"xxxx"
                    if case == "length-long"
                    else "bad",
                }
            )
    assert body.failed and not body._body
    with pytest.raises(RequestRefused, match="body_already_refused"):
        body.value()


def test_upload_hash_refusal_precedes_decoder_and_exact_retry_avoids_decoder(batch, monkeypatch):
    host = ImageJobs(batch.data_root, enabled=True)
    host.open()
    try:
        raw = pixels(100)
        sha = hashlib.sha256(raw).hexdigest()
        token = host.begin_upload(batch.batch_id, sha)
        future = host.stage(token, batch.batch_id, sha, raw)
        staged, created = future.result(timeout=10)
        assert created and staged.original_sha256 == sha and staged.ocr_executed is False
        assert not batch._manifest().items
        monkeypatch.setattr(
            "rfr.api.image_jobs.decode_bytes",
            lambda *a: pytest.fail("decoder must not run on retry/hash refusal"),
        )
        token = host.begin_upload(batch.batch_id, sha)
        assert host.stage(token, batch.batch_id, sha, raw).result(timeout=10) == (staged, False)
        token = host.begin_upload(batch.batch_id, "d" * 64)
        with pytest.raises(RequestRefused, match="image_hash_mismatch"):
            host.stage(token, batch.batch_id, "d" * 64, raw).result(timeout=10)
        assert not (batch.root / "pages" / ("image-" + "d" * 64)).exists()
    finally:
        host.close()


def test_capacity_counts_partial_and_tombstones_before_body_admission(batch):
    from rfr.pipeline.files import atomic
    from rfr.shared.rulings.identity import canonical_bytes

    host = ImageJobs(batch.data_root, enabled=True)
    host.open()
    try:
        manifest = batch._manifest().model_copy(update={"items": {"deleted": None}})
        atomic(batch.root / "manifest.json", canonical_bytes(manifest.model_dump(mode="json")))
        for i in range(99):
            (batch.root / "pages" / ("image-" + f"{i:064x}")).mkdir()
        with pytest.raises(RequestRefused, match="batch_image_limit"):
            host.begin_upload(batch.batch_id, "f" * 64)
        with pytest.raises(RequestRefused, match="retained_image_conflict"):
            host.begin_upload(batch.batch_id, "0" * 64)
        assert host.upload_token is None
    finally:
        host.close()


def test_http_staging_start_status_retry_and_revision_conflict(batch, worker, monkeypatch):
    executed = Event()
    original = ImageWorker.execute

    def execute(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        executed.set()
        return result

    monkeypatch.setattr(ImageWorker, "execute", execute)
    app = create_app(
        batch.data_root, origin=ORIGIN, capability=TOKEN, enable_images=True, image_worker=worker
    )
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
        raw = pixels(100)
        sha = hashlib.sha256(raw).hexdigest()
        path = f"/api/batches/{batch.batch_id}/images/{sha}"
        response = client.put(
            path, content=raw, headers={"content-type": "application/octet-stream"}
        )
        assert response.status_code == 201, response.text
        view = response.json()
        assert view["ocr_executed"] is False and not batch._manifest().items
        assert (
            client.put(
                path, content=raw, headers={"content-type": "application/octet-stream"}
            ).status_code
            == 200
        )
        request = request_for({view["item_id"]: ImageJobInput(original_sha256=sha)})
        start = client.post(
            f"/api/batches/{batch.batch_id}/image-jobs", json=request.model_dump(mode="json")
        )
        assert start.status_code == 202, start.text
        job_id = start.json()["job_id"]
        assert executed.wait(10)
        # Drain actual owned work through lifespan, not a sleep/poll success assumption.
    jobs = JobStore(batch)
    complete = jobs.get(job_id)
    assert complete.state == "complete" and next(iter(complete.items.values())).status == "ok"
    before = {p: p.read_bytes() for p in jobs.folder.glob("*.json")}
    # New owner does not replay; exact retry works without a configured engine.
    with TestClient(
        create_app(batch.data_root, origin=ORIGIN, capability=TOKEN, enable_images=True),
        base_url=ORIGIN,
        headers=HEADERS,
    ) as client:
        status = client.get(f"/api/batches/{batch.batch_id}/image-jobs/{job_id}")
        assert status.status_code == 200 and status.json()["state"] == "complete"
        retry = client.post(
            f"/api/batches/{batch.batch_id}/image-jobs", json=request.model_dump(mode="json")
        )
        assert retry.status_code == 200 and retry.json() == complete.model_dump(mode="json")
        changed = request.model_dump(mode="json")
        changed["spec"]["reference_date"] = "2026-10-15"
        assert (
            client.post(f"/api/batches/{batch.batch_id}/image-jobs", json=changed).status_code
            == 409
        )
    assert before == {p: p.read_bytes() for p in jobs.folder.glob("*.json")}
    host = ImageJobs(batch.data_root, enabled=True, worker=worker)
    host.open()
    try:
        stale, created = host.start(
            batch.batch_id, request_for(request.spec.images, "explicit-stale-request")
        )
        assert created
        result = host.future.result(timeout=10)
        assert result.state == "failed" and {p.status for p in result.items.values()} == {"stale"}
        assert (
            batch.bundle(view["item_id"]).revision
            == next(iter(complete.items.values())).result_revision
        )
    finally:
        host.close()


def test_status_missing_is_read_only_and_startup_never_replays_pending(batch, inputs, worker):
    host = ImageJobs(batch.data_root, enabled=True, worker=worker)
    before = set(batch.root.rglob("*"))
    with pytest.raises(FileNotFoundError):
        host.status(batch.batch_id, "d" * 64)
    assert set(batch.root.rglob("*")) == before
    jobs = JobStore(batch)
    pending = jobs.start("explicit-pending", request_for(inputs).spec, image_worker=worker)
    before_bytes = {p: p.read_bytes() for p in jobs.folder.glob("*.json")}
    host.open()
    try:
        assert host.future is None and host.status(batch.batch_id, pending.job_id) == pending
        assert host.start(batch.batch_id, request_for(inputs, "explicit-pending")) == (
            pending,
            False,
        )
        with pytest.raises(RequestRefused, match="image_job_conflict"):
            host.start(batch.batch_id, request_for(inputs, "different-request"))
    finally:
        host.close()
    assert before_bytes == {p: p.read_bytes() for p in jobs.folder.glob("*.json")}


def test_one_upload_lease_refuses_parallel_upload_or_new_job_without_publication(
    batch, inputs, worker
):
    host = ImageJobs(batch.data_root, enabled=True, worker=worker)
    host.open()
    try:
        token = host.begin_upload(batch.batch_id, "d" * 64)
        with pytest.raises(RequestRefused, match="image_host_busy"):
            host.begin_upload(batch.batch_id, "e" * 64)
        with pytest.raises(RequestRefused, match="image_host_busy"):
            host.start(batch.batch_id, request_for(inputs))
        folder = batch.root / "runs/jobs"
        assert not list(folder.glob("*.json"))
        host.end_upload(token)
        token2 = host.begin_upload(batch.batch_id, "e" * 64)
        host.end_upload(token)  # A stale release cannot release a different admitted upload.
        assert host.upload_token is token2
        host.end_upload(token2)
    finally:
        host.close()


def test_owned_shutdown_waits_for_actual_item_keeps_lock_and_marks_remaining_not_run(
    batch, inputs, worker, monkeypatch
):
    entered, release = Event(), Event()
    original = ImageWorker.execute
    calls = []

    def execute(self, *args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(10)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ImageWorker, "execute", execute)
    host = ImageJobs(batch.data_root, enabled=True, worker=worker)
    host.open()
    record, created = host.start(batch.batch_id, request_for(inputs))
    assert created and entered.wait(10)
    closer = Thread(target=host.close)
    closer.start()
    try:
        assert host.stop.wait(2) and closer.is_alive()
        contender = ImageJobs(batch.data_root, enabled=True)
        with pytest.raises(BatchError, match="batch_lock_deadline"):
            contender.open()
        with pytest.raises(RequestRefused, match="image_host_unavailable"):
            host.begin_upload(batch.batch_id, "d" * 64)
    finally:
        release.set()
        closer.join(15)
    assert not closer.is_alive() and len(calls) == 1
    result = JobStore(batch).get(record.job_id)
    assert result.state == "interrupted"
    assert [p.status for p in result.items.values()] == ["ok", "not_run"]
    assert len(batch._manifest().items) == 1
    contender.open()
    contender.close()


@pytest.mark.parametrize(
    "refusal", ["auth", "origin", "oversize", "disabled", "missing", "partial"]
)
def test_http_upload_refused_before_any_body_read_or_decoder(batch, monkeypatch, refusal):
    app = create_app(
        batch.data_root, origin=ORIGIN, capability=TOKEN, enable_images=refusal != "disabled"
    )
    sha = "c" * 64
    path = f"/api/batches/{batch.batch_id}/images/{sha}"
    headers = list(RAW)
    expected = {
        "auth": 401,
        "origin": 403,
        "oversize": 413,
        "disabled": 503,
        "missing": 404,
        "partial": 409,
    }[refusal]
    if refusal == "auth":
        headers = [h for h in headers if h[0] != b"x-rfr-token"]
    if refusal == "origin":
        headers = [h for h in headers if h[0] != b"origin"]
    if refusal == "oversize":
        headers.append((b"content-length", str(IMAGE_BODY_LIMIT + 1).encode()))
    if refusal == "missing":
        path = f"/api/batches/{'d' * 32}/images/{sha}"
    if refusal == "partial":
        (batch.root / "pages" / ("image-" + sha)).mkdir()
    monkeypatch.setattr(
        "rfr.api.image_jobs.decode_bytes", lambda *a: pytest.fail("refusal must precede decoder")
    )

    async def exercise():
        async with app.router.lifespan_context(app):
            sent = []

            async def receive():
                pytest.fail("refusal must precede body read")

            async def send(message):
                sent.append(message)

            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "PUT",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "root_path": "",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 10),
                "server": ("127.0.0.1", 24002),
            }
            await app(scope, receive, send)
            assert sent[0]["status"] == expected
            assert "private" not in json.dumps(sent, default=str)

    asyncio.run(exercise())
