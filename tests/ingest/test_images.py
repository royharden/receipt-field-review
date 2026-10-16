"""Real optional codecs on authored pixels; no OCR, provider, browser or quality claims."""

import io
import json
import os
import struct
import subprocess
import sys
import zlib
from unittest.mock import patch

import pytest

Image = pytest.importorskip("PIL.Image", reason="optional images extra is not installed")
heif = pytest.importorskip("pillow_heif", reason="optional HEIC conformance extra is not installed")

from rfr.ingest.images import (  # noqa: E402
    MAX_ENCODED,
    MAX_PIXELS,
    ImageInputError,
    ImageLimits,
    decode_bytes,
    decode_file,
    digest,
    load_staged,
    stage_image,
)
from rfr.pipeline.files import BatchError  # noqa: E402


def encoded(image, format="PNG", **options):
    out = io.BytesIO()
    image.save(out, format=format, **options)
    return out.getvalue()


def quadrants():
    image = Image.new("RGB", (48, 32), "red")
    image.paste("green", (24, 0, 48, 16))
    image.paste("blue", (0, 16, 24, 32))
    image.paste("yellow", (24, 16, 48, 32))
    return image


def heic_bytes(image, second=None):
    container = heif.from_pillow(image)
    if second is not None:
        container.add_from_pillow(second)
    out = io.BytesIO()
    container.save(out, quality=-1)
    return out.getvalue()


def test_png_normalization_hashes_white_alpha_and_metadata():
    # Catches metadata leaks, an incorrect black alpha matte and binding original to derivative.
    im = Image.new("RGBA", (8, 6), (255, 0, 0, 0))
    im.putpixel((3, 2), (10, 20, 30, 255))
    exif = Image.Exif()
    exif[270] = "authored private metadata must not be copied"
    decoded = decode_bytes(encoded(im, exif=exif))
    assert decoded.manifest.original_sha256 == digest(decoded.original)
    assert decoded.manifest.page_sha256 == digest(decoded.page_png)
    assert decoded.manifest.ocr_executed is False
    with Image.open(io.BytesIO(decoded.page_png)) as page:
        assert page.size == (8, 6) and page.mode == "RGB"
        assert page.getpixel((0, 0)) == (255, 255, 255)
        assert page.getpixel((3, 2)) == (10, 20, 30)
        assert not page.getexif() and "icc_profile" not in page.info
        assert "xmp" not in page.info and "exif" not in page.info


@pytest.mark.parametrize(
    ("orientation", "corner_order"),
    [
        (1, "RGBY"),
        (2, "GRYB"),
        (3, "YBGR"),
        (4, "BYRG"),
        (5, "RBGY"),
        (6, "BRYG"),
        (7, "YGBR"),
        (8, "GYRB"),
    ],
)
def test_real_jpeg_all_exif_orientations_bind_pixels_and_boundary_matrix(
    orientation, corner_order, tmp_path
):
    # Independent labelled quadrant oracle catches mirrors and width-vs-width-1 boundary bugs.
    exif = Image.Exif()
    exif[274] = orientation
    decoded = decode_bytes(encoded(quadrants(), "JPEG", quality=100, subsampling=0, exif=exif))
    m = decoded.manifest
    expected = (48, 32) if orientation <= 4 else (32, 48)
    assert (m.page_width_px, m.page_height_px) == expected
    palette = {"R": (255, 0, 0), "G": (0, 128, 0), "B": (0, 0, 255), "Y": (255, 255, 0)}
    with Image.open(io.BytesIO(decoded.page_png)) as page:
        points = [
            (2, 2),
            (page.width - 3, 2),
            (2, page.height - 3),
            (page.width - 3, page.height - 3),
        ]
        for point, label in zip(points, corner_order, strict=True):
            assert (
                max(abs(a - b) for a, b in zip(page.getpixel(point), palette[label], strict=True))
                <= 3
            )
        assert not page.getexif()
    matrix, inverse = m.decoder_to_page, m.page_to_decoder
    mapped = []
    for x, y in [(0, 0), (48, 0), (0, 32), (48, 32)]:
        xx, yy = (sum(matrix[i][j] * (x, y, 1)[j] for j in range(3)) for i in range(2))
        mapped.append((xx, yy))
        assert tuple(sum(inverse[i][j] * (xx, yy, 1)[j] for j in range(3)) for i in range(2)) == (
            x,
            y,
        )
    assert set(mapped) == {(0, 0), (expected[0], 0), (0, expected[1]), expected}
    stage_image(tmp_path, decoded)
    assert load_staged(tmp_path, m.original_sha256) == decoded


def test_real_heic_codec_delivered_grid_is_explicit_and_single_page(tmp_path):
    decoded = decode_bytes(heic_bytes(quadrants()))
    assert decoded.manifest.original_format == "HEIC"
    assert decoded.manifest.decoder_grid == "libheif-delivered"
    assert "pillow-heif/" in decoded.manifest.decoder
    assert (decoded.manifest.page_width_px, decoded.manifest.page_height_px) == (48, 32)
    with Image.open(io.BytesIO(decoded.page_png)) as page:
        assert not page.getexif() and page.mode == "RGB"
        assert page.getpixel((4, 4))[0] > 240 and page.getpixel((4, 4))[2] < 15
    stage_image(tmp_path, decoded)
    assert load_staged(tmp_path, decoded.manifest.original_sha256) == decoded


def test_multi_image_heic_and_animated_png_refuse_instead_of_dropping_frames():
    first, second = quadrants(), Image.new("RGB", (48, 32), "white")
    for raw in [heic_bytes(first, second), encoded(first, save_all=True, append_images=[second])]:
        with pytest.raises(ImageInputError, match="single_image_required"):
            decode_bytes(raw)


def test_real_heic_container_orientation_is_not_applied_twice(tmp_path):
    # The HEIF encoder records EXIF orientation as a container transform. libheif delivers
    # the rotated raster; calling a second EXIF transpose would restore the wrong dimensions.
    image = quadrants()
    exif = Image.Exif()
    exif[274] = 6
    # Use the Pillow writer directly: from_pillow pre-rotates its input, so pairing that
    # helper with an orientation-bearing save can apply orientation twice in the fixture.
    heif.register_heif_opener()
    # The plugin's orientation parser requires serialized EXIF bytes at this boundary.
    decoded = decode_bytes(encoded(image, "HEIF", quality=-1, exif=exif.tobytes()))
    assert (decoded.manifest.page_width_px, decoded.manifest.page_height_px) == (32, 48)
    assert decoded.manifest.exif_orientation == 1
    with Image.open(io.BytesIO(decoded.page_png)) as page:
        assert page.getpixel((3, 3))[2] > 240  # blue is top-left after clockwise rotation
        assert not page.getexif()
    stage_image(tmp_path, decoded)
    assert load_staged(tmp_path, decoded.manifest.original_sha256) == decoded


def test_signature_and_encoded_limit_run_before_optional_decoder_import():
    with patch(
        "rfr.ingest.images.importlib.import_module", side_effect=AssertionError("decoder called")
    ):
        with pytest.raises(ImageInputError, match="unsupported_image_signature"):
            decode_bytes(b"GIF89a" + bytes(20))
        with pytest.raises(ImageInputError, match="encoded_image_limit"):
            decode_bytes(b"\x89PNG\r\n\x1a\n" + bytes(20), ImageLimits(encoded=16))


def test_malformed_bytes_and_optional_dependency_diagnostics_do_not_echo_input():
    with pytest.raises(ImageInputError, match="^invalid_image$"):
        decode_bytes(b"\x89PNG\r\n\x1a\nprivate malformed contents")
    with patch(
        "rfr.ingest.images.importlib.import_module", side_effect=ImportError("private path")
    ):
        with pytest.raises(
            ImageInputError, match="^image_decoder_unavailable_install_images_extra$"
        ):
            decode_bytes(b"\x89PNG\r\n\x1a\n")
    original_import = __import__("importlib").import_module

    def no_heif(name):
        if name == "pillow_heif":
            raise ImportError("private path")
        return original_import(name)

    raw = heic_bytes(quadrants())
    with patch("rfr.ingest.images.importlib.import_module", side_effect=no_heif):
        with pytest.raises(ImageInputError, match="^heic_decoder_unavailable_install_heic_extra$"):
            decode_bytes(raw)


def test_dimensions_refuse_before_pixel_load_and_png_bomb_header_is_bounded():
    raw = encoded(Image.new("RGB", (5, 5)))
    with patch.object(Image.Image, "load", side_effect=AssertionError("pixel load called")):
        with pytest.raises(ImageInputError, match="decoded_pixel_limit"):
            decode_bytes(raw, ImageLimits(pixels=24))

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    bomb = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 6000, 5000, 8, 2, 0, 0, 0))
    bomb += chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")
    with pytest.raises(ImageInputError, match="decoded_pixel_limit"):
        decode_bytes(bomb)


def test_limits_cannot_weaken_policy_and_normalized_output_is_bounded():
    for kwargs in [{"encoded": MAX_ENCODED + 1}, {"pixels": MAX_PIXELS + 1}, {"pixels": True}]:
        with pytest.raises(ValueError, match="only_narrow"):
            ImageLimits(**kwargs)
    with pytest.raises(ImageInputError, match="normalized_image_limit"):
        decode_bytes(encoded(quadrants()), ImageLimits(normalized=40))


def test_staged_original_page_manifest_reopen_exact_retry_and_tamper_refusal(tmp_path):
    decoded = decode_bytes(encoded(quadrants()))
    folder = stage_image(tmp_path, decoded)
    original = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert load_staged(tmp_path, decoded.manifest.original_sha256) == decoded
    assert stage_image(tmp_path, decoded) == folder
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == original
    (folder / "page.png").write_bytes(b"tampered")
    with pytest.raises(ImageInputError, match="image_content_binding_mismatch"):
        stage_image(tmp_path, decoded)
    assert (folder / "page.png").read_bytes() == b"tampered"
    assert (folder / "original.bin").read_bytes() == decoded.original


def test_partial_stage_path_injection_and_hardlink_source_fail_closed(tmp_path):
    decoded = decode_bytes(encoded(quadrants()))
    partial = tmp_path / ("image-" + decoded.manifest.original_sha256)
    partial.mkdir()
    (partial / "original.bin").write_bytes(decoded.original)
    with pytest.raises(ImageInputError, match="incomplete_image_artifact"):
        stage_image(tmp_path, decoded)
    assert [p.name for p in partial.iterdir()] == ["original.bin"]
    with pytest.raises(ImageInputError, match="invalid_image_identity"):
        load_staged(tmp_path, "../escape")
    source = tmp_path / "source.png"
    source.write_bytes(decoded.original)
    os.link(source, tmp_path / "hardlink.png")
    with pytest.raises(BatchError, match="nonplain_private_path"):
        decode_file(source)


def test_real_local_command_persist_reopen_refusal_and_no_receipt_import(tmp_path):
    source = tmp_path / "authored.png"
    source.write_bytes(encoded(quadrants()))
    out = tmp_path / "private"
    out.mkdir()
    command = [sys.executable, "-m", "rfr.ingest", "--source", str(source), "--out", str(out)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    decoded = load_staged(out, result["manifest"]["original_sha256"])
    assert decoded.original == source.read_bytes()
    assert (
        subprocess.run(command, capture_output=True, text=True, timeout=10).stdout == first.stdout
    )
    assert not list(out.rglob("rulings.jsonl")) and not list(out.rglob("batch.json"))
    source.write_bytes(b"malformed authored input")
    refused = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert refused.returncode == 2
    assert json.loads(refused.stderr) == {"error": "unsupported_image_signature"}
    assert "authored" not in refused.stderr and not refused.stdout
    assert load_staged(out, result["manifest"]["original_sha256"]) == decoded
