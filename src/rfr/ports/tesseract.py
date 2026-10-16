"""Installed, trusted local Tesseract adapter; no shell, provider or automatic installation."""

import hashlib
import importlib
import io
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from rfr.ingest.images import DecodedImage
from rfr.pipeline.files import BatchError, immutable, plain, read
from rfr.shared.docio.identity import artifact_bytes, canonical_bytes, grid_digest, raw_revision
from rfr.shared.docio.models import Bounds, OcrResult, PageInput, TransformPair
from rfr.shared.docio.tsv import TsvError, page_from_artifact, parse_tsv_artifact


class NativeOcrError(BatchError):
    """Closed local-engine diagnostics, safe to show without native stderr or paths."""


@dataclass(frozen=True)
class Capture:
    status: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    elapsed_s: float
    pid: int | None
    cleanup_complete: bool


def bounded_command(command, directory: Path, timeout_s: float, output_limit: int) -> Capture:
    """Capture bounded prefixes while draining a single trusted child; kill/wait on refusal."""
    if (
        type(timeout_s) not in (int, float)
        or not 0 < timeout_s <= 60
        or type(output_limit) is not int
        or not 0 < output_limit <= 4194304
        or type(command) is not list
        or not 0 < len(command) <= 32
        or any(type(part) is not str or "\0" in part for part in command)
        or sum(map(len, command)) > 4096
    ):
        raise NativeOcrError("native_command_bounds")
    plain(directory, directory=True)
    started = time.monotonic()
    # Native OCR needs no model credentials or inherited provider configuration.
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "PATH") if k in os.environ}
    env.update(OMP_THREAD_LIMIT="1", OMP_NUM_THREADS="1", TEMP=str(directory), TMP=str(directory))
    try:
        process = subprocess.Popen(
            command,
            cwd=directory,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return Capture("unavailable", None, b"", b"", time.monotonic() - started, None, True)
    output, errors = bytearray(), bytearray()
    exceeded, read_failed = threading.Event(), threading.Event()

    def drain(stream, target, maximum):
        try:
            while chunk := stream.read1(4096):
                remaining = maximum - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    exceeded.set()
        except (OSError, ValueError):
            read_failed.set()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, output, output_limit), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, errors, 16384), daemon=True),
    ]
    for reader in readers:
        reader.start()
    status = "ok"
    try:
        while process.poll() is None:
            if exceeded.is_set():
                status = "limit_exceeded"
                break
            if time.monotonic() - started >= timeout_s:
                status = "timeout"
                break
            time.sleep(0.01)
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                read_failed.set()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            status = "timeout"
        for reader in readers:
            reader.join(timeout=2)
        cleanup = process.poll() is not None and not any(r.is_alive() for r in readers)
        if cleanup:
            process.stdout.close()
            process.stderr.close()
    if exceeded.is_set():
        status = "limit_exceeded"
    elif read_failed.is_set() or not cleanup or status == "ok" and process.returncode != 0:
        status = "invalid" if cleanup else "timeout"
    return Capture(
        status,
        process.returncode,
        bytes(output),
        bytes(errors),
        time.monotonic() - started,
        process.pid,
        cleanup,
    )


def file_digest(path: Path, maximum=256 * 1024 * 1024) -> str:
    plain(path)
    if path.stat().st_size > maximum:
        raise NativeOcrError("native_engine_or_model_limit")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sibling_libraries(executable: Path) -> dict[str, str]:
    paths = sorted(executable.parent.glob("*.dll"))
    if len(paths) > 128 or sum(p.stat().st_size for p in paths) > 256 * 1024 * 1024:
        raise NativeOcrError("native_library_inventory_limit")
    return {path.name: file_digest(path) for path in paths}


def image_input(decoded: DecodedImage, execution_ref: str) -> PageInput:
    """The displayed RGBA8 grid is the OCR input; never reapply original EXIF transforms."""
    image_module = importlib.import_module("PIL.Image")
    with image_module.open(io.BytesIO(decoded.page_png)) as image, image.convert("RGBA") as rgba:
        grid = grid_digest(rgba.width, rgba.height, rgba.tobytes())
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    document_id = "receipt-image:" + decoded.manifest.original_sha256
    return PageInput(
        execution_ref=execution_ref,
        document_id=document_id,
        original_content_sha256=decoded.manifest.original_sha256,
        raw_source_revision=raw_revision(document_id, decoded.manifest.original_sha256),
        page_id="page:0",
        page_index=0,
        page_sha256=grid,
        width_px=decoded.manifest.page_width_px,
        height_px=decoded.manifest.page_height_px,
        grid_policy_id="rgba8-source-grid-v1",
        source_kind="image",
        transforms=TransformPair.model_validate(
            {
                "source_to_engine": {
                    "direction": "source_to_engine",
                    "algorithm": "identity/1",
                    "matrix": identity,
                },
                "engine_to_source": {
                    "direction": "engine_to_source",
                    "algorithm": "identity/1",
                    "matrix": identity,
                },
            }
        ),
    )


class TesseractOcr:
    """One image/one execution implementing the canonical injected OcrAdapter contract."""

    def __init__(self, decoded: DecodedImage, directory: Path, executable: Path, tessdata: Path):
        self.decoded, self.directory = decoded, directory.absolute()
        self.executable, self.tessdata = executable.absolute(), tessdata.absolute()
        self.page_input = image_input(decoded, "native:" + directory.name)
        self.retained_artifact = None
        self.config = None
        self.execution = {"profile": "rfr-native-tesseract/1", "ocr_started": False, "commands": []}
        self._used = False

    def _capture(self, command, timeout_s, output_limit, name):
        result = bounded_command(command, self.directory, timeout_s, output_limit)
        immutable(self.directory / (name + ".stdout"), result.stdout)
        immutable(self.directory / (name + ".stderr"), result.stderr)
        self.execution["commands"].append(
            {
                "stage": name,
                "status": result.status,
                "exit_code": result.exit_code,
                "elapsed_s": result.elapsed_s,
                "pid": result.pid,
                "cleanup_complete": result.cleanup_complete,
                "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
            }
        )
        if name == "ocr":
            self.execution["ocr_started"] = result.pid is not None
        if result.status != "ok":
            raise NativeOcrError("native_" + name + "_" + result.status)
        return result.stdout

    def recognize(self, page: PageInput, bounds: Bounds) -> OcrResult:
        if self._used:
            raise NativeOcrError("native_adapter_already_used")
        self._used = True
        plain(self.directory, directory=True)
        started = time.monotonic()
        status, issue = "invalid", "native_input_refused"
        try:
            if page != self.page_input or not 0 < bounds.deadline_s <= 60:
                raise NativeOcrError("native_input_binding")
            if (
                bounds.max_pages != 1
                or bounds.max_words > 2000
                or bounds.max_output_bytes > 4194304
                or len(self.decoded.original) > bounds.max_encoded_bytes
                or page.width_px * page.height_px > min(bounds.max_decoded_pixels, 25000000)
            ):
                raise NativeOcrError("native_input_bounds")
            plain(self.tessdata, directory=True)
            binary_hash = file_digest(self.executable)
            model_hash = file_digest(self.tessdata / "eng.traineddata")
            immutable(self.directory / "input.png", self.decoded.page_png)
            immutable(self.directory / "input.json", canonical_bytes(page.model_dump(mode="json")))
            remaining = bounds.deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                raise NativeOcrError("native_version_timeout")
            version_raw = self._capture(
                [str(self.executable), "--version"], remaining, 8192, "version"
            )
            version_raw = version_raw or read(self.directory / "version.stderr", 16384)
            version = version_raw.decode("utf-8", errors="strict").splitlines()[0].strip()
            if not re.fullmatch(r"tesseract v?[0-9][A-Za-z0-9.+_-]{0,100}", version):
                raise NativeOcrError("native_version_refused")
            notice = self.executable.parent / "doc" / "LICENSE"
            self.config = {
                "profile": "rfr-tesseract-config/1",
                "engine_version": version,
                "executable_sha256": binary_hash,
                "eng_traineddata_sha256": model_hash,
                "sibling_dll_sha256": sibling_libraries(self.executable),
                "tsv_config_sha256": file_digest(self.tessdata / "configs" / "tsv", 16384),
                "language": "eng",
                "oem": 1,
                "psm": 6,
                "omp_thread_limit": 1,
                "installed_engine_notice_sha256": file_digest(notice, 1048576)
                if notice.is_file()
                else None,
                "model_license_provenance": (
                    "Installed model bytes pinned; separate model notice/source "
                    "not authenticated; no redistribution."
                ),
            }
            config_raw = canonical_bytes(self.config)
            immutable(self.directory / "engine.json", config_raw)
            remaining = bounds.deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                raise NativeOcrError("native_ocr_timeout")
            command = [
                str(self.executable),
                str(self.directory / "input.png"),
                "stdout",
                "--tessdata-dir",
                str(self.tessdata),
                "-l",
                "eng",
                "--oem",
                "1",
                "--psm",
                "6",
                "tsv",
            ]
            raw = self._capture(command, remaining, bounds.max_output_bytes, "ocr")
            if (
                file_digest(self.executable) != binary_hash
                or file_digest(self.tessdata / "eng.traineddata") != model_hash
                or sibling_libraries(self.executable) != self.config["sibling_dll_sha256"]
                or file_digest(self.tessdata / "configs" / "tsv", 16384)
                != self.config["tsv_config_sha256"]
            ):
                raise NativeOcrError("native_engine_changed_during_execution")
            remaining = bounds.deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                raise NativeOcrError("native_ocr_timeout")
            parse_bounds = Bounds.model_validate(bounds.model_dump() | {"deadline_s": remaining})
            artifact = parse_tsv_artifact(
                raw,
                page,
                parse_bounds,
                engine_width_px=page.width_px,
                engine_height_px=page.height_px,
                engine_version=version,
                config_sha256=hashlib.sha256(config_raw).hexdigest(),
            )
            recognized = page_from_artifact(artifact, page)
            self.retained_artifact = artifact_bytes(artifact)
            immutable(self.directory / "artifact.json", self.retained_artifact)
            self.execution.update(status="ok", issue=None)
            return OcrResult(
                status="ok",
                page=recognized,
                issues=(),
                capabilities=("installed-local-tesseract", "measured-word-boxes"),
                processing_artifact_ref=artifact.artifact_id,
            )
        except NativeOcrError as error:
            issue = str(error)
            status = (
                "timeout"
                if "timeout" in issue
                else "limit_exceeded"
                if "limit" in issue
                else "unavailable"
                if "unavailable" in issue
                else "invalid"
            )
        except FileNotFoundError:
            status, issue = "unavailable", "native_engine_or_eng_model_missing"
        except TsvError as error:
            status, issue = error.status, "native_tsv_" + str(error)
        except (OSError, ValueError, TypeError, IndexError):
            issue = "native_output_or_state_refused"
        finally:
            self.execution.setdefault("status", status)
            self.execution.setdefault("issue", issue)
            immutable(self.directory / "execution.json", canonical_bytes(self.execution))
        return OcrResult(
            status=status, page=None, issues=(issue,), capabilities=(), processing_artifact_ref=None
        )
