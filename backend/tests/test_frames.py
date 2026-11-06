from __future__ import annotations

import struct

from PIL import Image, ImageDraw

from app.frames.service import _window, dhash, parse_bif, validate_image


def _jpeg_bytes() -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", (320, 180), (120, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_parse_bif_returns_embedded_images() -> None:
    images = [_jpeg_bytes(), _jpeg_bytes()]
    header_size = 8 + 4 + 4 + 4
    index_size = 16 * len(images)
    offset = header_size + index_size
    entries = []
    payload = b""
    for index, image in enumerate(images):
        entries.append((index * 10_000, offset + len(payload), len(image)))
        payload += image

    data = bytearray()
    data += b"\x89BIF\r\n\x1a\n"
    data += struct.pack("<III", 1, len(images), 10_000)
    for timestamp, image_offset, length in entries:
        data += struct.pack("<QII", timestamp, image_offset, length)
    data += payload

    parsed = parse_bif(bytes(data))
    assert len(parsed) == 2
    assert parsed[0].startswith(b"\xff\xd8")


def test_parse_bif_rejects_invalid_header() -> None:
    assert parse_bif(b"not a bif") == []


def test_window_avoids_intro_and_credits() -> None:
    snapshot = {
        "runtime_ticks": 2 * 60 * 60 * 10_000_000,
        "chapters": [
            {"start_ticks": 0, "marker_type": None},
            {"start_ticks": 5 * 60 * 10_000_000, "marker_type": "IntroEnd"},
            {"start_ticks": 100 * 60 * 10_000_000, "marker_type": "CreditsStart"},
        ],
    }
    start, end = _window(snapshot)
    assert start >= 5 * 60 + 15
    assert end <= 100 * 60 - 15
    assert start < end


def test_validate_image_rejects_black_frame(tmp_path) -> None:
    path = tmp_path / "black.jpg"
    Image.new("RGB", (320, 180), (0, 0, 0)).save(path)
    try:
        validate_image(path)
    except ValueError:
        pass
    else:
        raise AssertionError("A black frame must be rejected")


def test_validate_image_accepts_detailed_frame(tmp_path) -> None:
    path = tmp_path / "frame.jpg"
    image = Image.new("RGB", (640, 360), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    for x in range(0, 640, 16):
        draw.rectangle([x, 0, x + 8, 360], fill=(x % 255, (x * 2) % 255, 120))
    image.save(path, quality=90)
    width, height, phash = validate_image(path)
    assert width == 640
    assert height == 360
    assert len(phash) == 16


def test_dhash_is_stable(tmp_path) -> None:
    path = tmp_path / "frame.jpg"
    image = Image.new("RGB", (320, 180), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 300, 160], fill=(220, 180, 90))
    image.save(path)
    assert dhash(path) == dhash(path)
