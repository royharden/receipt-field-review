"""Durable local B0 reruns, explicit unavailability and no automatic recovery execution."""

import hashlib
import importlib.metadata
import platform
import re
from datetime import UTC, datetime
from pathlib import Path

from ..receipt.b0 import extract_b0
from ..shared.execution.callledger.models import decode_wire_json
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.store import GenerationConflict, JournalError, PriorConflict
from .files import BatchError, atomic, batch_mutex, plain, read
from .job_models import ImageJobSpec, ItemProgress, JobRecord, JobSpec
from .models import ReceiptBundle


def _now():
    return datetime.now(UTC).isoformat()


def local_execution_fingerprint():
    root = Path(__file__).resolve().parents[1]
    paths = (
        "pipeline/jobs.py",
        "pipeline/job_models.py",
        "pipeline/models.py",
        "receipt/b0.py",
        "receipt/candidates.py",
        "receipt/checks.py",
        "receipt/normalization.py",
        "receipt/models.py",
        "shared/docio/identity.py",
        "shared/docio/models.py",
        "shared/fieldextract/engine.py",
        "shared/fieldextract/models.py",
    )
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
    return hashlib.sha256(
        canonical_bytes(
            {
                "files": files,
                "python": platform.python_version(),
                "pydantic": importlib.metadata.version("pydantic"),
            }
        )
    ).hexdigest()


class LocalB0:
    """Actual deterministic extractor, with no model or human-effective input."""

    def execute(self, bundle: ReceiptBundle):
        receipt = extract_b0(
            bundle.document,
            bundle.artifact_bytes(),
            bundle.receipt.artifact_sha256,
            bundle.receipt.context,
        )
        return ReceiptBundle(
            document=bundle.document, receipt=receipt, artifact_base64=bundle.artifact_base64
        )


class JobStore:
    def __init__(self, batch, *, create=True):
        self.batch = batch
        self.folder = batch.root / "runs" / "jobs"
        if not create:
            return
        with batch_mutex(batch.root):
            plain(self.folder.parent, directory=True)
            self.folder.mkdir(exist_ok=True)
            plain(self.folder, directory=True)

    def _path(self, job_id):
        if type(job_id) is not str or not re.fullmatch(r"[0-9a-f]{64}", job_id):
            raise BatchError("invalid_job_id")
        plain(self.folder, directory=True)
        return self.folder / (job_id + ".json")

    def _load(self, job_id):
        try:
            raw = read(self._path(job_id), 512 * 1024)
            decode_wire_json(raw.decode("utf-8"), max_bytes=512 * 1024)
            record = JobRecord.model_validate_json(raw)
        except ValueError:
            raise BatchError("invalid_job_state") from None
        expected = hashlib.sha256(record.request_id.encode("utf-8")).hexdigest()
        if record.job_id != job_id or job_id != expected:
            raise BatchError("job_identity_conflict")
        return record

    def _save(self, record):
        # Revalidate mutable nested mappings and closed terminal branches before atomic handoff.
        raw = canonical_bytes(record.model_dump(mode="json"))
        record = JobRecord.model_validate_json(raw)
        atomic(self._path(record.job_id), raw)

    def get(self, job_id):
        with batch_mutex(self.batch.root):
            return self._load(job_id)

    def lookup_request(self, request_id, spec):
        """Read-only historical retry before server busy/config admission; never resubmit."""
        request_id, spec, job_id = self._intent(request_id, spec)
        with batch_mutex(self.batch.root):
            if not self._path(job_id).exists():
                return None
            record = self._load(job_id)
            if record.request_id != request_id or record.spec != spec:
                raise BatchError("job_request_intent_conflict")
            return record

    @staticmethod
    def _intent(request_id, spec):
        if type(request_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
            raise BatchError("invalid_job_request_id")
        if type(spec) not in (JobSpec, ImageJobSpec):
            raise BatchError("closed_job_spec_required")
        spec = type(spec).model_validate_json(canonical_bytes(spec.model_dump(mode="json")))
        job_id = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        return request_id, spec, job_id

    def start(self, request_id: str, spec: JobSpec | ImageJobSpec, *, image_worker=None):
        request_id, spec, job_id = self._intent(request_id, spec)
        with batch_mutex(self.batch.root):
            path = self._path(job_id)
            if path.exists():
                prior = self._load(job_id)
                if prior.spec != spec or prior.request_id != request_id:
                    raise BatchError("job_request_intent_conflict")
                return prior  # No new execution, even when an earlier run failed/interrupted.
            active_path = self.folder / "active.json"
            if active_path.exists():
                try:
                    active = decode_wire_json(read(active_path, 512).decode("utf-8"), max_bytes=512)
                    if type(active) is not dict or set(active) != {"job_id"}:
                        raise ValueError("invalid_active_job")
                    prior = self._load(active["job_id"])
                except (ValueError, KeyError):
                    raise BatchError("invalid_active_job_state") from None
                if prior.state in {"pending", "running"}:
                    raise BatchError("batch_job_already_active")
            image_job = isinstance(spec, ImageJobSpec)
            if image_job:
                if image_worker is None:
                    raise BatchError("trusted_image_worker_required")
                from ..ingest.images import load_staged

                # Validate the entire fixed cohort before publishing a job or starting OCR.
                for image in spec.images.values():
                    load_staged(self.batch.root / "pages", image.original_sha256)
            fingerprint = self._fingerprint(spec, image_worker)
            record = JobRecord(
                job_id=job_id,
                request_id=request_id,
                spec=spec,
                execution_config_sha256=fingerprint,
                state="pending",
                items={
                    item: ItemProgress(status="queued")
                    for item in (spec.images if image_job else spec.source_revisions)
                },
                execution_origin="not_run",
                model_cost_status="not_run",
            )
            self._save(record)
            atomic(active_path, canonical_bytes({"job_id": job_id}))
            return record

    def _fingerprint(self, spec, image_worker, *, engine_sha256=None):
        local = local_execution_fingerprint()
        if isinstance(spec, ImageJobSpec):
            if image_worker is None:
                raise BatchError("trusted_image_worker_required")
            return hashlib.sha256(
                canonical_bytes(
                    {"local": local, "image": image_worker.fingerprint(engine_sha256=engine_sha256)}
                )
            ).hexdigest()
        return local

    def _progress(self, job_id, item_id, progress, *, execution_started=False):
        with batch_mutex(self.batch.root):
            record = self._load(job_id)
            if record.state != "running":
                raise BatchError("job_no_longer_running")
            items = dict(record.items)
            items[item_id] = progress
            update = {"items": items}
            if execution_started:
                update.update(
                    execution_origin="local_image_pipeline"
                    if isinstance(record.spec, ImageJobSpec)
                    else "local_rules",
                    model_cost_status="not_applicable",
                )
            self._save(record.model_copy(update=update))

    def run(self, job_id, *, local_b0=None, image_worker=None, should_stop=None):
        with batch_mutex(self.batch.root):
            record = self._load(job_id)
            if record.state != "pending":
                return record
            record = record.model_copy(update={"state": "running", "started_at": _now()})
            self._save(record)  # Claim is durable before any executor is called.
        executor = local_b0 if local_b0 is not None else LocalB0()
        if isinstance(record.spec, ImageJobSpec):
            return self._run_images(record, image_worker, should_stop=should_stop)
        config_matches = record.execution_config_sha256 == local_execution_fingerprint()
        for item_id, expected in record.spec.source_revisions.items():
            if not config_matches:
                self._progress(
                    job_id,
                    item_id,
                    ItemProgress(status="unavailable", reason="frozen_execution_config_changed"),
                )
                continue
            if record.spec.method != "B0":
                self._progress(
                    job_id,
                    item_id,
                    ItemProgress(
                        status="unavailable", reason="canonical_method_adapter_unavailable"
                    ),
                )
                continue
            self._progress(job_id, item_id, ItemProgress(status="running"))
            try:
                bundle = self.batch.bundle(item_id)
                if bundle.revision != expected:
                    raise GenerationConflict("requested_source_revision_changed")
                self._progress(
                    job_id, item_id, ItemProgress(status="running"), execution_started=True
                )
                result = executor.execute(bundle)
                if (
                    type(result) is not ReceiptBundle
                    or result.document != bundle.document
                    or result.artifact_base64 != bundle.artifact_base64
                    or result.receipt.context != bundle.receipt.context
                ):
                    raise BatchError("method_changed_frozen_source")
                revision = self.batch.register(result, expected_revision=expected)
                progress = ItemProgress(status="ok", result_revision=revision)
            except (GenerationConflict, PriorConflict):
                progress = ItemProgress(status="stale", reason="source_revision_conflict")
            except BatchError:
                progress = ItemProgress(status="unavailable", reason="source_or_result_unavailable")
            except JournalError:
                progress = ItemProgress(status="error", reason="decision_journal_refused")
            except Exception:
                progress = ItemProgress(status="error", reason="method_error")
            self._progress(job_id, item_id, progress)
        return self._finish(job_id)

    def _run_images(self, record, worker, *, should_stop=None):
        from ..ingest.images import load_staged

        for item_id, image in record.spec.images.items():
            if should_stop is not None and should_stop():
                return self._stop_images(record.job_id)
            try:
                if worker is None:
                    raise BatchError("trusted_image_worker_required")
                # Use this same snapshot for both the queued-config comparison and importer.
                # A fresh independent snapshot in either boundary would reopen the drift gap.
                engine_sha256 = worker.engine_sha256()
                if (
                    self._fingerprint(record.spec, worker, engine_sha256=engine_sha256)
                    != record.execution_config_sha256
                ):
                    raise BatchError("frozen_execution_config_changed")
                load_staged(self.batch.root / "pages", image.original_sha256)
                with batch_mutex(self.batch.root):
                    manifest = self.batch._manifest()
                    if (
                        manifest.items.get(item_id) != image.expected_revision
                        or item_id in manifest.items
                        and manifest.items[item_id] is None
                    ):
                        raise GenerationConflict("requested_source_revision_changed")
                    if item_id not in manifest.items and len(manifest.items) >= 100:
                        raise BatchError("batch_item_limit")
                    if not self.batch.journal.replay().can_append:
                        raise BatchError("journal_not_clean")
                self._progress(
                    record.job_id, item_id, ItemProgress(status="running"), execution_started=True
                )
                result = worker.execute(
                    self.batch,
                    image,
                    record.spec.reference_date,
                    expected_engine_sha256=engine_sha256,
                )
                bundle = self.batch.bundle(item_id)
                if (
                    type(result) is not dict
                    or result.get("item_id") != item_id
                    or result.get("revision") != bundle.revision
                    or bundle.document.original_content_sha256 != image.original_sha256
                    or bundle.receipt.context.reference_date != record.spec.reference_date
                ):
                    raise BatchError("image_result_identity_conflict")
                progress = ItemProgress(status="ok", result_revision=bundle.revision)
            except (GenerationConflict, PriorConflict):
                progress = ItemProgress(status="stale", reason="source_revision_conflict")
            except (BatchError, ValueError, OSError):
                progress = ItemProgress(
                    status="unavailable", reason="image_source_or_worker_refused"
                )
            except JournalError:
                progress = ItemProgress(status="error", reason="decision_journal_refused")
            except Exception:
                progress = ItemProgress(status="error", reason="image_method_error")
            self._progress(record.job_id, item_id, progress)
        return self._finish(record.job_id)

    def _stop_images(self, job_id):
        """The owning loop calls this only between items, after actual in-flight progress."""
        with batch_mutex(self.batch.root):
            record = self._load(job_id)
            if record.state != "running":
                return record
            items = {
                item: ItemProgress(status="not_run", reason="server_shutdown")
                if progress.status == "queued"
                else progress
                for item, progress in record.items.items()
            }
            if any(progress.status == "running" for progress in items.values()):
                raise BatchError("cannot_stop_live_image_item")
            record = record.model_copy(
                update={"items": items, "state": "interrupted", "ended_at": _now()}
            )
            self._save(record)
            return record

    def _finish(self, job_id):
        with batch_mutex(self.batch.root):
            record = self._load(job_id)
            if record.state != "running":
                return record
            count = sum(item.status == "ok" for item in record.items.values())
            state = "complete" if count == len(record.items) else "partial" if count else "failed"
            record = record.model_copy(update={"state": state, "ended_at": _now()})
            self._save(record)
            return record

    def recover_interrupted(self, job_id):
        """Call only after the owner has established the previous worker is gone; never auto-run."""
        with batch_mutex(self.batch.root):
            record = self._load(job_id)
            if record.state not in {"pending", "running"}:
                return record
            items = {
                item: ItemProgress(
                    status="unknown_interrupted", reason="worker_result_not_acknowledged"
                )
                if progress.status == "running"
                else ItemProgress(status="not_run", reason="prior_worker_interrupted")
                if progress.status == "queued"
                else progress
                for item, progress in record.items.items()
            }
            record = record.model_copy(
                update={"state": "interrupted", "items": items, "ended_at": _now()}
            )
            self._save(record)
            return record
