from __future__ import annotations

import hashlib
import io
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures" / "source_visuals"
PNG_FIXTURE = FIXTURES / "fixture.png"


def _image_bytes(
    *,
    fmt: str = "PNG",
    size: tuple[int, int] = (320, 180),
    color: tuple[int, int, int] = (25, 80, 140),
    transparent: bool = False,
) -> bytes:
    mode = "RGBA" if transparent else "RGB"
    image = Image.new(mode, size, color + ((0,) if transparent else ()))
    output = io.BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def _oversized_png_header(width: int = 10_001, height: int = 4_000) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, value: bytes) -> bytes:
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)
        )

    # One short scanline is enough: the decoder must reject the pixel bound
    # before trying to inflate a full 40MP image.
    return (
        signature
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\0" + b"\0" * width * 3))
        + chunk(b"IEND", b"")
    )


def _candidate_image_bytes() -> bytes:
    return _image_bytes(size=(640, 360), color=(35, 120, 90))


def test_prepare_webp_accepts_png_jpeg_and_webp_through_one_decoder() -> None:
    from deeper_notebook.source_visuals.media import prepare_webp

    source = Image.open(io.BytesIO(_candidate_image_bytes())).convert("RGB")
    encoded: dict[str, bytes] = {}
    for fmt in ("PNG", "JPEG", "WEBP"):
        output = io.BytesIO()
        source.save(output, format=fmt)
        encoded[fmt] = output.getvalue()

    prepared = [prepare_webp(value) for value in encoded.values()]
    assert {asset.mime_type for asset in prepared} == {"image/webp"}
    assert all(asset.width <= 1280 and asset.height <= 720 for asset in prepared)
    assert all(len(asset.encoded_bytes) <= 1_572_864 for asset in prepared)
    assert all(len(asset.asset_sha256) == 64 for asset in prepared)


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "SVG_UNSUPPORTED"),
        (_image_bytes(fmt="GIF"), "FORMAT_UNSUPPORTED"),
        (b"not an image", "DECODE_FAILED"),
        (_candidate_image_bytes()[:-12], "DECODE_FAILED"),
    ],
)
def test_prepare_webp_rejects_unsupported_malformed_and_truncated_inputs(
    payload: bytes, error_code: str
) -> None:
    from deeper_notebook.source_visuals.media import (
        SourceVisualMediaError,
        prepare_webp,
    )

    with pytest.raises(SourceVisualMediaError) as caught:
        prepare_webp(payload)
    assert caught.value.code == error_code
    assert str(caught.value) == error_code


def test_prepare_webp_rejects_animated_gif_and_webp() -> None:
    from deeper_notebook.source_visuals.media import (
        SourceVisualMediaError,
        prepare_webp,
    )

    frames = [
        Image.new("RGB", (120, 80), color) for color in ((10, 20, 30), (30, 20, 10))
    ]
    for fmt in ("GIF", "WEBP"):
        output = io.BytesIO()
        frames[0].save(
            output,
            format=fmt,
            save_all=True,
            append_images=frames[1:],
            duration=20,
            loop=0,
        )
        with pytest.raises(SourceVisualMediaError, match="ANIMATED_UNSUPPORTED"):
            prepare_webp(output.getvalue())


def test_prepare_webp_rejects_alpha_only_images() -> None:
    from deeper_notebook.source_visuals.media import (
        SourceVisualMediaError,
        prepare_webp,
    )

    with pytest.raises(SourceVisualMediaError, match="ALPHA_ONLY"):
        prepare_webp(_image_bytes(transparent=True))


def test_prepare_webp_rejects_over_40mp_and_decoder_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.media as media

    with pytest.raises(media.SourceVisualMediaError, match="PIXEL_LIMIT"):
        media.prepare_webp(_oversized_png_header())

    monkeypatch.setattr(media.Image, "MAX_IMAGE_PIXELS", 1)
    with pytest.raises(media.SourceVisualMediaError, match="DECOMPRESSION_BOMB"):
        media.prepare_webp(_candidate_image_bytes())


def test_prepare_webp_rejects_polyglot_and_oversized_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.media as media

    with pytest.raises(media.SourceVisualMediaError, match="POLYGLOT"):
        media.prepare_webp(_candidate_image_bytes() + b"PK\x03\x04")

    monkeypatch.setattr(
        media, "_encode_webp", lambda *_args, **_kwargs: b"x" * (1_572_865)
    )
    with pytest.raises(media.SourceVisualMediaError, match="OUTPUT_TOO_LARGE"):
        media.prepare_webp(_candidate_image_bytes())


def test_prepare_webp_letterboxes_and_applies_exif_orientation() -> None:
    from deeper_notebook.source_visuals.media import prepare_webp

    image = Image.new("RGB", (180, 320), (200, 30, 50))
    exif = image.getexif()
    exif[274] = 6
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif.tobytes())
    prepared = prepare_webp(output.getvalue())
    decoded = Image.open(io.BytesIO(prepared.encoded_bytes))
    assert (prepared.width, prepared.height) == (1280, 720)
    assert decoded.getpixel((0, 0)) == (240, 240, 240)


def test_prepare_webp_accepts_baseline_and_progressive_jpeg_but_rejects_structural_trailing_data() -> (
    None
):
    from deeper_notebook.source_visuals.media import (
        SourceVisualMediaError,
        prepare_webp,
    )

    image = Image.new("RGB", (320, 180), (35, 120, 90))
    baseline = io.BytesIO()
    progressive = io.BytesIO()
    image.save(baseline, format="JPEG")
    image.save(progressive, format="JPEG", progressive=True)

    assert prepare_webp(baseline.getvalue()).mime_type == "image/webp"
    assert prepare_webp(progressive.getvalue()).mime_type == "image/webp"

    malformed_length = bytearray(baseline.getvalue())
    malformed_length[4:6] = b"\xff\xff"
    hostile = (
        baseline.getvalue() + b"PK\x03\x04archive-bytes" + b"\xff\xd9",
        baseline.getvalue() + progressive.getvalue(),
        bytes(malformed_length),
    )
    for payload in hostile:
        with pytest.raises(SourceVisualMediaError):
            prepare_webp(payload)


def test_select_candidate_is_deterministic_and_scores_without_randomness() -> None:
    from deeper_notebook.source_visuals.media import VisualCandidate, select_candidate

    payload = _candidate_image_bytes()
    candidates = [
        VisualCandidate("embedded", {"page": 2, "resource_id": "9"}, payload, 0.5, "b"),
        VisualCandidate("embedded", {"page": 1, "resource_id": "4"}, payload, 0.5, "a"),
        VisualCandidate("video_frame", {"timestamp_ms": 1000}, payload, 0.8, "c"),
    ]
    chosen = select_candidate(reversed(candidates))
    assert chosen is not None
    assert chosen.stable_key == "c"
    assert select_candidate(candidates).stable_key == chosen.stable_key


def test_select_candidate_ties_use_locator_before_origin() -> None:
    from deeper_notebook.source_visuals.media import VisualCandidate, select_candidate

    payload = _candidate_image_bytes()
    candidates = [
        VisualCandidate("video_frame", {"timestamp_ms": 1}, payload, 0.5, "video"),
        VisualCandidate("audio_artwork", {"resource_id": "a"}, payload, 0.5, "audio"),
    ]

    chosen = select_candidate(candidates)
    assert chosen is not None
    assert chosen.stable_key == "audio"


def test_candidate_alt_text_is_bounded_neutral_and_locator_based() -> None:
    from deeper_notebook.source_visuals.media import VisualCandidate, build_alt_text

    candidate = VisualCandidate(
        "embedded", {"page": 4, "resource_id": "12"}, b"x", 1.0, "k"
    )
    text = build_alt_text("A bounded source title", "PDF", candidate)
    assert text == "A bounded source title, PDF, Embedded image, page 4"
    assert len(text) <= 300


def test_error_codes_never_include_paths_or_unbounded_details() -> None:
    from deeper_notebook.source_visuals.media import SourceVisualMediaError

    error = SourceVisualMediaError("DECODE_FAILED", "/private/source.txt with secret")
    assert error.code == "DECODE_FAILED"
    assert "/private" not in str(error)
    assert len(str(error)) <= 64
