"""Bounded optional PNG/JPEG/HEIC decoding into an explicit normalized source grid."""

import hashlib
import importlib
import io
import json
import warnings
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from rfr.pipeline.files import batch_mutex, immutable, plain, read
from rfr.shared.docio.models import (
    AffineTransform,
    Matrix,
    PositiveInt,
    Sha256,
    TransformPair,
    Wire,
)

MAX_ENCODED = 20 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_NORMALIZED = 80 * 1024 * 1024


class ImageInputError(ValueError):
    """Closed diagnostic codes; decoder errors never echo paths or input metadata."""


@dataclass(frozen=True)
class ImageLimits:
    encoded: int = MAX_ENCODED
    pixels: int = MAX_PIXELS
    normalized: int = MAX_NORMALIZED

    def __post_init__(self):
        for value, ceiling in zip(
            (self.encoded, self.pixels, self.normalized),
            (MAX_ENCODED, MAX_PIXELS, MAX_NORMALIZED),
            strict=True,
        ):
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("image_limits_may_only_narrow_hard_bounds")


DEFAULT_LIMITS = ImageLimits()


class ImageManifest(Wire):
    profile: Literal["rfr-image/1"] = "rfr-image/1"
    original_sha256: Sha256
    original_bytes: PositiveInt
    original_format: Literal["PNG", "JPEG", "HEIC"]
    page_sha256: Sha256
    page_bytes: PositiveInt
    page_width_px: PositiveInt
    page_height_px: PositiveInt
    decoder_width_px: PositiveInt
    decoder_height_px: PositiveInt
    exif_orientation: int
    decoder: str
    grid_policy: Literal["rfr-normalized-rgb-png/1"] = "rfr-normalized-rgb-png/1"
    decoder_grid: Literal["Pillow-before-EXIF", "libheif-delivered"]
    decoder_to_page: Matrix
    page_to_decoder: Matrix
    container_orientation: int | None = None
    ocr_executed: Literal[False] = False

    @model_validator(mode="after")
    def bounded(self):
        if (
            self.original_bytes > MAX_ENCODED
            or self.page_bytes > MAX_NORMALIZED
            or self.page_width_px * self.page_height_px > MAX_PIXELS
            or self.decoder_width_px * self.decoder_height_px > MAX_PIXELS
            or not 1 <= self.exif_orientation <= 8
        ):
            raise ValueError("image_manifest_bounds")
        heic = self.original_format == "HEIC"
        if (
            self.decoder_grid != ("libheif-delivered" if heic else "Pillow-before-EXIF")
            or (heic and self.exif_orientation != 1)
            or (not heic and self.container_orientation is not None)
        ):
            raise ValueError("image_manifest_grid")
        size = (self.decoder_width_px, self.decoder_height_px)
        expected_size = size if self.exif_orientation <= 4 else size[::-1]
        forward, inverse = orientation_matrices(self.exif_orientation, *size)
        if (
            (self.page_width_px, self.page_height_px) != expected_size
            or self.decoder_to_page != forward
            or self.page_to_decoder != inverse
        ):
            raise ValueError("image_manifest_geometry")
        TransformPair(
            source_to_engine=AffineTransform(
                direction="source_to_engine",
                algorithm="exif-boundary/1",
                matrix=self.decoder_to_page,
            ),
            engine_to_source=AffineTransform(
                direction="engine_to_source",
                algorithm="exif-boundary/1",
                matrix=self.page_to_decoder,
            ),
        )
        return self


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DecodedImage:
    original: bytes
    page_png: bytes
    manifest: ImageManifest

    def __post_init__(self):
        m = self.manifest
        if (
            len(self.original) != m.original_bytes
            or len(self.page_png) != m.page_bytes
            or digest(self.original) != m.original_sha256
            or digest(self.page_png) != m.page_sha256
        ):
            raise ImageInputError("image_content_binding_mismatch")
        if signature(self.original) != m.original_format:
            raise ImageInputError("image_original_format_mismatch")
        # Check the fixed PNG IHDR without loading optional native codecs again.
        # This binds the declared grid/profile, not authenticity or full PNG validity.
        raw = self.page_png
        if (
            len(raw) < 33
            or raw[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            or raw[24:29] != b"\x08\x02\x00\x00\x00"
            or int.from_bytes(raw[16:20], "big") != m.page_width_px
            or int.from_bytes(raw[20:24], "big") != m.page_height_px
            or zlib.crc32(raw[12:29]) != int.from_bytes(raw[29:33], "big")
        ):
            raise ImageInputError("image_page_header_mismatch")


def signature(raw: bytes) -> Literal["PNG", "JPEG", "HEIC"]:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if raw.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(raw) >= 16 and raw[4:8] == b"ftyp":
        size = int.from_bytes(raw[:4], "big")
        if 16 <= size <= min(len(raw), 512) and size % 4 == 0:
            brands = [raw[8:12], *(raw[i : i + 4] for i in range(16, size, 4))]
            if any(b in {b"heic", b"heix", b"hevc", b"hevx"} for b in brands):
                return "HEIC"
    raise ImageInputError("unsupported_image_signature")


def orientation_matrices(orientation: int, width: int, height: int) -> tuple[Matrix, Matrix]:
    # Pixel-boundary coordinates: [0,width] x [0,height], not pixel-center indices.
    w, h = float(width), float(height)
    a, b, c, d, e, f = {
        1: (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        2: (-1.0, 0.0, w, 0.0, 1.0, 0.0),
        3: (-1.0, 0.0, w, 0.0, -1.0, h),
        4: (1.0, 0.0, 0.0, 0.0, -1.0, h),
        5: (0.0, 1.0, 0.0, 1.0, 0.0, 0.0),
        6: (0.0, -1.0, h, 1.0, 0.0, 0.0),
        7: (0.0, -1.0, h, -1.0, 0.0, w),
        8: (0.0, 1.0, 0.0, -1.0, 0.0, w),
    }[orientation]
    det = a * e - b * d
    return (
        ((a, b, c), (d, e, f), (0.0, 0.0, 1.0)),
        (
            (e / det, -b / det, (b * f - e * c) / det),
            (-d / det, a / det, (d * c - a * f) / det),
            (0.0, 0.0, 1.0),
        ),
    )


class BoundedOutput(io.BytesIO):
    def __init__(self, maximum: int):
        super().__init__()
        self.maximum = maximum

    def write(self, data):
        if self.tell() + len(data) > self.maximum:
            raise ImageInputError("normalized_image_limit")
        return super().write(data)


def decode_bytes(raw: bytes, limits: ImageLimits = DEFAULT_LIMITS) -> DecodedImage:
    if type(raw) is not bytes or not raw:
        raise ImageInputError("nonempty_image_bytes_required")
    if len(raw) > limits.encoded:
        raise ImageInputError("encoded_image_limit")
    kind = signature(raw)
    try:
        image_module = importlib.import_module("PIL.Image")
        image_ops = importlib.import_module("PIL.ImageOps")
        pillow = importlib.import_module("PIL")
    except ImportError:
        raise ImageInputError("image_decoder_unavailable_install_images_extra") from None
    decoder = "Pillow/" + pillow.__version__
    if kind == "HEIC":
        try:
            heif = importlib.import_module("pillow_heif")
        except ImportError:
            raise ImageInputError("heic_decoder_unavailable_install_heic_extra") from None
        heif.register_heif_opener()
        decoder += ";pillow-heif/" + heif.__version__
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", image_module.DecompressionBombWarning)
            with image_module.open(
                io.BytesIO(raw), formats=["HEIF" if kind == "HEIC" else kind]
            ) as im:
                width, height = im.size
                if width <= 0 or height <= 0 or width * height > limits.pixels:
                    raise ImageInputError("decoded_pixel_limit")
                if getattr(im, "n_frames", 1) != 1:
                    raise ImageInputError("single_image_required")
                # libheif has already applied container transforms and normalized EXIF.
                # Its delivered raster is the declared starting grid, not raw encoded pixels.
                container_orientation = (
                    im.info.get("original_orientation") if kind == "HEIC" else None
                )
                orientation = 1 if kind == "HEIC" else im.getexif().get(274, 1)
                if type(orientation) is not int or not 1 <= orientation <= 8:
                    raise ImageInputError("invalid_exif_orientation")
                im.load()
                # Some native decoders refine dimensions during load. Bind the delivered raster,
                # and refuse a changed size beyond the limit before normalization/output.
                width, height = im.size
                if width <= 0 or height <= 0 or width * height > limits.pixels:
                    raise ImageInputError("decoded_pixel_limit")
                oriented = image_ops.exif_transpose(im) if kind != "HEIC" else im.copy()
                with oriented:
                    with oriented.convert("RGBA") as rgba:
                        with image_module.new("RGB", rgba.size, "white") as page:
                            page.paste(rgba, mask=rgba.getchannel("A"))
                            output = BoundedOutput(limits.normalized)
                            # Fresh image has no source EXIF/XMP/ICC/filename metadata.
                            page.save(output, format="PNG", optimize=False)
                            png = output.getvalue()
                            page_width, page_height = page.size
                forward, inverse = orientation_matrices(orientation, width, height)
    except (image_module.DecompressionBombWarning, image_module.DecompressionBombError):
        raise ImageInputError("decoded_pixel_limit") from None
    except ImageInputError:
        raise
    except (OSError, ValueError, SyntaxError, EOFError, RuntimeError):
        raise ImageInputError("invalid_image") from None
    return DecodedImage(
        raw,
        png,
        ImageManifest(
            original_sha256=digest(raw),
            original_bytes=len(raw),
            original_format=kind,
            page_sha256=digest(png),
            page_bytes=len(png),
            page_width_px=page_width,
            page_height_px=page_height,
            decoder_width_px=width,
            decoder_height_px=height,
            exif_orientation=orientation,
            decoder=decoder,
            decoder_grid="libheif-delivered" if kind == "HEIC" else "Pillow-before-EXIF",
            decoder_to_page=forward,
            page_to_decoder=inverse,
            container_orientation=container_orientation
            if type(container_orientation) is int
            else None,
        ),
    )


def decode_file(path: Path, limits: ImageLimits = DEFAULT_LIMITS) -> DecodedImage:
    plain(path.parent, directory=True)
    return decode_bytes(read(path, limits.encoded), limits)


def manifest_bytes(manifest: ImageManifest) -> bytes:
    return (json.dumps(manifest.model_dump(mode="json"), sort_keys=True) + "\n").encode("utf-8")


def load_staged(parent: Path, original_sha256: str) -> DecodedImage:
    # Validate before using the supplied identity in any path.
    if len(original_sha256) != 64 or any(c not in "0123456789abcdef" for c in original_sha256):
        raise ImageInputError("invalid_image_identity")
    plain(parent, directory=True)
    folder = parent / ("image-" + original_sha256)
    plain(folder, directory=True)
    if set(p.name for p in folder.iterdir()) != {"original.bin", "page.png", "manifest.json"}:
        raise ImageInputError("incomplete_image_artifact")
    manifest = ImageManifest.model_validate_json(read(folder / "manifest.json", 16384))
    if manifest.original_sha256 != original_sha256:
        raise ImageInputError("image_identity_mismatch")
    return DecodedImage(
        read(folder / "original.bin", MAX_ENCODED),
        read(folder / "page.png", MAX_NORMALIZED),
        manifest,
    )


def stage_image(parent: Path, decoded: DecodedImage) -> Path:
    """Original + derivative + commit marker; partial/modified artifacts fail closed on retry."""
    plain(parent, directory=True)
    folder = parent / ("image-" + decoded.manifest.original_sha256)
    with batch_mutex(parent):
        if folder.exists() or folder.is_symlink():
            if load_staged(parent, decoded.manifest.original_sha256) != decoded:
                raise ImageInputError("immutable_image_conflict")
            return folder
        folder.mkdir(mode=0o700)
        immutable(folder / "original.bin", decoded.original)
        immutable(folder / "page.png", decoded.page_png)
        immutable(folder / "manifest.json", manifest_bytes(decoded.manifest))
    return folder
