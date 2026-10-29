"""Trusted owner-local OCR configuration; queue intents contain no filesystem paths."""

import hashlib
import importlib.metadata
from dataclasses import dataclass
from pathlib import Path

from ..shared.rulings.identity import canonical_bytes


@dataclass(frozen=True)
class ImageWorker:
    executable: Path
    tessdata: Path
    deadline_s: float = 30.0

    def __post_init__(self):
        if (
            not isinstance(self.executable, Path)
            or not isinstance(self.tessdata, Path)
            or not self.executable.is_absolute()
            or not self.tessdata.is_absolute()
            or type(self.deadline_s) not in (int, float)
            or not 0 < self.deadline_s <= 60
        ):
            raise ValueError("trusted_absolute_engine_paths_and_bounded_deadline_required")

    def engine_sha256(self):
        from ..ports.tesseract import engine_identity, engine_identity_digest

        return engine_identity_digest(engine_identity(self.executable, self.tessdata))

    def fingerprint(self, *, engine_sha256=None):
        # File-only admission. No engine process or capability probe runs here.
        root = Path(__file__).resolve().parents[1]
        files = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "pipeline/image_worker.py",
                "pipeline/store.py",
                "pipeline/files.py",
                "ingest/native.py",
                "ingest/images.py",
                "ports/tesseract.py",
                "shared/docio/tsv.py",
            )
        }
        versions = {}
        for package in ("pillow", "pillow-heif"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        return hashlib.sha256(
            canonical_bytes(
                {
                    "files": files,
                    "versions": versions,
                    "executable": str(self.executable),
                    "tessdata": str(self.tessdata),
                    "engine_sha256": self.engine_sha256()
                    if engine_sha256 is None
                    else engine_sha256,
                    "deadline_s": self.deadline_s,
                }
            )
        ).hexdigest()

    def execute(self, batch, image, reference_date, *, expected_engine_sha256):
        from ..ingest.native import import_image

        # The caller has verified this immutable staged identity, including its derivative.
        source = batch.root / "pages" / ("image-" + image.original_sha256) / "original.bin"
        return import_image(
            batch,
            source,
            self.executable,
            self.tessdata,
            reference_date,
            expected_revision=image.expected_revision,
            deadline_s=self.deadline_s,
            expected_engine_sha256=expected_engine_sha256,
        )
