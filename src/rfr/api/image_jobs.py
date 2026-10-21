"""One lifespan-owned image executor; files remain the only job/source truth.

Shutdown drains actual work. A synchronous codec can hang: this is not hard process isolation.
"""

import hashlib
import importlib.util
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from ..ingest.images import ImageInputError, decode_bytes, load_staged, stage_image
from ..pipeline.files import BatchError, batch_mutex, plain
from ..pipeline.jobs import JobStore
from ..pipeline.store import BatchStore
from .models import ImageJobStart, StagedImage
from .operations import _request
from .security import RequestRefused


class ImageJobs:
    def __init__(self, data_root, *, enabled=False, worker=None):
        if type(enabled) is not bool or (worker is not None and not enabled):
            raise ValueError("explicit_image_host_enable_required")
        self.root, self.enabled, self.worker = data_root, enabled, worker
        self.gate = threading.Lock()
        self.stop = threading.Event()
        self.upload_idle = threading.Event()
        self.upload_idle.set()
        self.upload_token = None
        self.future = None
        self.executor = None
        self.owner = None
        self.running = False

    def open(self):
        if not self.enabled:
            return
        with self.gate:
            if self.running:
                raise RuntimeError("image_host_already_started")
            owner = batch_mutex(self.root, deadline_s=0.1)
            owner.__enter__()  # OS-owned root lock, not timestamp/age ownership.
            try:
                self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rfr-image")
                self.owner = owner
                self.stop.clear()
                self.running = True
            except BaseException:
                owner.__exit__(None, None, None)
                raise

    def close(self):
        with self.gate:
            if not self.running:
                return
            self.running = False
            self.stop.set()
            executor, owner = self.executor, self.owner
        # No timeout/daemon escape: lock stays held until upload and worker have actually ended.
        self.upload_idle.wait()
        executor.shutdown(wait=True, cancel_futures=False)
        owner.__exit__(None, None, None)
        self.executor = self.owner = None

    def capabilities(self):
        staging = self.enabled and self.running and importlib.util.find_spec("PIL") is not None
        runnable = False
        if staging and self.worker is not None:
            try:
                # Bounded file-only configuration check, no process probe.
                self.worker.engine_sha256()
                runnable = True
            except (ValueError, OSError, BatchError):
                pass
        return staging, runnable

    def _admit(self):
        if not self.enabled or not self.running or self.stop.is_set():
            raise RequestRefused(503, "image_host_unavailable")

    def _busy(self):
        return self.upload_token is not None or self.future is not None and not self.future.done()

    def _batch(self, batch_id):
        if type(batch_id) is not str or re.fullmatch(r"[0-9a-f]{32}", batch_id) is None:
            raise RequestRefused(400, "invalid_batch_id")
        # Refuse missing batch before JournalStore can create any subdirectory.
        plain(self.root / batch_id, directory=True)
        batch = BatchStore(self.root, batch_id)
        batch._manifest()
        return batch

    def _capacity(self, batch, original_sha256=None, *, item_id=None):
        pages = batch.root / "pages"
        plain(pages, directory=True)
        ids = set(batch._manifest().items)
        for path in pages.iterdir():
            if path.name.startswith("image-"):
                suffix = path.name[6:]
                if re.fullmatch(r"[0-9a-f]{64}", suffix) is None:
                    raise RequestRefused(409, "invalid_retained_image_identity")
                plain(path, directory=True)
                ids.add("receipt-image:" + suffix)
        item = item_id if item_id is not None else "receipt-image:" + original_sha256
        if len(ids) > 100 or item not in ids and len(ids) >= 100:
            raise RequestRefused(409, "batch_image_limit")
        if original_sha256 is not None and (pages / ("image-" + original_sha256)).exists():
            try:
                load_staged(pages, original_sha256)
            except (ValueError, OSError, BatchError):
                raise RequestRefused(409, "retained_image_conflict") from None

    def import_recognized(self, operations, batch_id, request):
        # Preserve the same identity-union ceiling when both HTTP import paths are enabled.
        if not self.enabled:
            return operations.import_recognized(batch_id, request)
        with self.gate:
            self._admit()
            if self._busy():
                raise RequestRefused(409, "image_host_busy")
            batch = self._batch(batch_id)
            with batch_mutex(batch.root):
                self._capacity(batch, item_id=request.bundle.document.document_id)
            return operations.import_recognized(batch_id, request)

    def begin_upload(self, batch_id, original_sha256):
        if (
            type(original_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", original_sha256) is None
        ):
            raise RequestRefused(400, "invalid_image_identity")
        with self.gate:
            self._admit()
            if self._busy():
                raise RequestRefused(409, "image_host_busy")
            if importlib.util.find_spec("PIL") is None:
                raise RequestRefused(503, "image_decoder_unavailable")
            batch = self._batch(batch_id)
            with batch_mutex(batch.root):
                self._capacity(batch, original_sha256)
            token = object()
            self.upload_token = token
            self.upload_idle.clear()
            return token

    def end_upload(self, token):
        with self.gate:
            if self.upload_token is token:
                self.upload_token = None
                self.upload_idle.set()

    def stage(self, token, batch_id, original_sha256, raw):
        with self.gate:
            self._admit()
            if self.upload_token is not token:
                raise RequestRefused(409, "upload_admission_required")
            self.future = self.executor.submit(self._stage, batch_id, original_sha256, raw)
            # Future now owns this work even if its HTTP caller disconnects/cancels.
            self.upload_token = None
            self.upload_idle.set()
            return self.future

    def _stage(self, batch_id, original_sha256, raw):
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != original_sha256:
            raise RequestRefused(400, "image_hash_mismatch")
        batch = self._batch(batch_id)
        with batch_mutex(batch.root):
            self._capacity(batch, original_sha256)
            if (batch.root / "pages" / ("image-" + original_sha256)).exists():
                decoded = load_staged(batch.root / "pages", original_sha256)
                if decoded.original != raw:
                    raise RequestRefused(409, "retained_image_conflict")
                return self._view(decoded), False
        try:
            decoded = decode_bytes(raw)
        except ImageInputError as error:
            if "unavailable" in str(error):
                raise RequestRefused(503, "image_decoder_unavailable") from None
            raise RequestRefused(400, "invalid_image") from None
        with batch_mutex(batch.root):
            self._capacity(batch, original_sha256)
            created = not (batch.root / "pages" / ("image-" + original_sha256)).exists()
            stage_image(batch.root / "pages", decoded)
        return self._view(decoded), created

    @staticmethod
    def _view(decoded):
        m = decoded.manifest
        return StagedImage(
            item_id="receipt-image:" + m.original_sha256,
            original_sha256=m.original_sha256,
            original_bytes=m.original_bytes,
            original_format=m.original_format,
            normalized_png_sha256=m.page_sha256,
            width=m.page_width_px,
            height=m.page_height_px,
        )

    def start(self, batch_id, request):
        request = _request(ImageJobStart, request)
        with self.gate:
            self._admit()
            batch = self._batch(batch_id)
            jobs = JobStore(batch)
            try:
                prior = jobs.lookup_request(request.request_id, request.spec)
                if prior is not None:
                    return prior, False
                if self._busy():
                    raise RequestRefused(409, "image_host_busy")
                if self.worker is None or not self.capabilities()[1]:
                    raise RequestRefused(503, "image_worker_unavailable")
                record = jobs.start(request.request_id, request.spec, image_worker=self.worker)
            except BatchError as error:
                if str(error) in {"job_request_intent_conflict", "batch_job_already_active"}:
                    raise RequestRefused(409, "image_job_conflict") from None
                raise
            # If submission fails the pending record stays durable, never automatically rerun.
            self.future = self.executor.submit(
                jobs.run, record.job_id, image_worker=self.worker, should_stop=self.stop.is_set
            )
            return record, True

    def status(self, batch_id, job_id):
        # No executor/recovery/startup dependency and no JobStore directory creation.
        batch = self._batch(batch_id)
        plain(batch.root / "runs" / "jobs", directory=True)
        return JobStore(batch, create=False).get(job_id)
