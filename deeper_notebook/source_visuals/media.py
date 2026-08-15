"""Strict, deterministic decoder and candidate-selection primitives.

The media boundary intentionally accepts bytes rather than filenames.  PDF,
video, and audio extractors may supply local bytes, but every candidate passes
through :func:`prepare_webp` before it can become a published derivative.
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping

from PIL import Image, ImageCms, ImageFile, ImageOps, ImageStat

from deeper_notebook.source_visuals.contracts import PreparedVisualAsset

MAX_WIDTH = 1_280
MAX_HEIGHT = 720
MAX_PIXELS = 40_000_000
MAX_OUTPUT_BYTES = 1_572_864
WEBP_QUALITIES = (86, 80, 74, 68, 60, 52)
NEUTRAL_LETTERBOX = (240, 240, 240)
ALLOWED_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
MIN_EMBEDDED_DIMENSION = 32
MIN_EMBEDDED_AREA = 4_096
MAX_EMBEDDED_ASPECT_RATIO = 8.0

# The global Pillow limit is part of the decoder contract.  The scoped warning
# filter below still turns a warning into a typed failure for every decode.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
ImageFile.LOAD_TRUNCATED_IMAGES = False


class SourceVisualMediaError(ValueError):
    """Bounded media failure whose public text never contains paths or bytes."""

    _CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,47}$")

    def __init__(self, code: str, _detail: object | None = None) -> None:
        normalized = str(code).upper()[:48]
        if self._CODE.fullmatch(normalized) is None:
            normalized = "MEDIA_FAILED"
        self.code = normalized
        super().__init__(normalized)


@dataclass(frozen=True, slots=True)
class VisualCandidate:
    """An extracted image candidate before final derivative preparation."""

    origin: str
    locator: Mapping[str, int | str]
    encoded_bytes: bytes
    score: float
    stable_key: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.encoded_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class _DecodedImage:
    image: Image.Image
    pixel_sha256: str
    width: int
    height: int


def _read_input(value: bytes | bytearray | memoryview | BinaryIO | Path | str) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, (Path, str)):
        try:
            return Path(value).read_bytes()
        except OSError as exc:
            raise SourceVisualMediaError("INPUT_READ_FAILED", exc) from None
    try:
        payload = value.read()
    except (AttributeError, OSError, ValueError) as exc:
        raise SourceVisualMediaError("INPUT_READ_FAILED", exc) from None
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise SourceVisualMediaError("INPUT_READ_FAILED")
    return bytes(payload)


def _sniff_svg(payload: bytes) -> bool:
    prefix = payload[:1_024].lstrip().lower()
    return prefix.startswith((b"<svg", b"<?xml")) or b"<svg" in prefix


def _container_format(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if payload.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "WEBP"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "GIF"
    return None


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 24 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")


def _reject_polyglot(payload: bytes, fmt: str) -> None:
    """Require the container's declared end to be the byte-string end."""

    if fmt == "PNG":
        offset = 8
        while offset + 12 <= len(payload):
            size = int.from_bytes(payload[offset : offset + 4], "big")
            end = offset + 12 + size
            if end > len(payload):
                raise SourceVisualMediaError("DECODE_FAILED")
            kind = payload[offset + 4 : offset + 8]
            offset = end
            if kind == b"IEND":
                if offset != len(payload):
                    raise SourceVisualMediaError("POLYGLOT")
                return
        raise SourceVisualMediaError("DECODE_FAILED")
    if fmt == "JPEG":
        _reject_jpeg_polyglot(payload)
        return
    if fmt == "WEBP":
        declared_size = int.from_bytes(payload[4:8], "little") + 8
        if declared_size != len(payload):
            raise SourceVisualMediaError("POLYGLOT")


def _reject_jpeg_polyglot(payload: bytes) -> None:
    """Parse JPEG markers through the first structural EOI and require EOF."""

    if len(payload) < 4 or payload[:2] != b"\xff\xd8":
        raise SourceVisualMediaError("DECODE_FAILED")
    offset = 2
    while True:
        marker, offset = _next_jpeg_marker(payload, offset)
        if marker == 0xD9:
            if offset != len(payload):
                raise SourceVisualMediaError("POLYGLOT")
            return
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7:
            raise SourceVisualMediaError("DECODE_FAILED")
        if marker == 0x01:
            continue
        if offset + 2 > len(payload):
            raise SourceVisualMediaError("DECODE_FAILED")
        segment_length = int.from_bytes(payload[offset : offset + 2], "big")
        if segment_length < 2:
            raise SourceVisualMediaError("DECODE_FAILED")
        segment_end = offset + segment_length
        if segment_end > len(payload):
            raise SourceVisualMediaError("DECODE_FAILED")
        offset = segment_end
        if marker == 0xDA:
            offset = _consume_jpeg_entropy(payload, offset)


def _next_jpeg_marker(payload: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(payload) or payload[offset] != 0xFF:
        raise SourceVisualMediaError("DECODE_FAILED")
    while offset < len(payload) and payload[offset] == 0xFF:
        offset += 1
    if offset >= len(payload) or payload[offset] == 0x00:
        raise SourceVisualMediaError("DECODE_FAILED")
    return payload[offset], offset + 1


def _consume_jpeg_entropy(payload: bytes, offset: int) -> int:
    while offset < len(payload):
        if payload[offset] != 0xFF:
            offset += 1
            continue
        marker_offset = offset
        offset += 1
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            raise SourceVisualMediaError("DECODE_FAILED")
        marker = payload[offset]
        if marker == 0x00 or 0xD0 <= marker <= 0xD7:
            offset += 1
            continue
        return marker_offset
    raise SourceVisualMediaError("DECODE_FAILED")


def _srgb_rgb(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    profile = image.info.get("icc_profile")
    if profile:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            target = ImageCms.createProfile("sRGB")
            rgb = ImageCms.profileToProfile(rgb, source, target, outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            # A malformed optional ICC profile must not make the pixel decoder
            # accept an unbounded or ambiguous image.  RGB conversion remains
            # deterministic and Pillow has already validated the container.
            rgb = image.convert("RGB")
    rgb.info.pop("icc_profile", None)
    return rgb


def _decode_image(value: bytes | bytearray | memoryview | BinaryIO | Path | str) -> _DecodedImage:
    payload = _read_input(value)
    if not payload:
        raise SourceVisualMediaError("DECODE_FAILED")
    if _sniff_svg(payload):
        raise SourceVisualMediaError("SVG_UNSUPPORTED")
    expected_format = _container_format(payload)
    if expected_format is None:
        raise SourceVisualMediaError("DECODE_FAILED")
    if expected_format not in ALLOWED_FORMATS:
        if expected_format == "GIF":
            try:
                with Image.open(io.BytesIO(payload)) as gif:
                    if bool(getattr(gif, "is_animated", False)) or int(getattr(gif, "n_frames", 1)) != 1:
                        raise SourceVisualMediaError("ANIMATED_UNSUPPORTED")
            except SourceVisualMediaError:
                raise
            except (OSError, ValueError, SyntaxError):
                raise SourceVisualMediaError("DECODE_FAILED") from None
        raise SourceVisualMediaError("FORMAT_UNSUPPORTED")
    dimensions = _png_dimensions(payload)
    if dimensions and dimensions[0] * dimensions[1] > MAX_PIXELS:
        raise SourceVisualMediaError("PIXEL_LIMIT")
    _reject_polyglot(payload, expected_format)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as opened:
                if opened.format != expected_format:
                    raise SourceVisualMediaError("FORMAT_MISMATCH")
                if bool(getattr(opened, "is_animated", False)) or int(getattr(opened, "n_frames", 1)) != 1:
                    raise SourceVisualMediaError("ANIMATED_UNSUPPORTED")
                opened.verify()
            with Image.open(io.BytesIO(payload)) as opened:
                if opened.format != expected_format:
                    raise SourceVisualMediaError("FORMAT_MISMATCH")
                if bool(getattr(opened, "is_animated", False)) or int(getattr(opened, "n_frames", 1)) != 1:
                    raise SourceVisualMediaError("ANIMATED_UNSUPPORTED")
                oriented = ImageOps.exif_transpose(opened)
                oriented.load()
                if oriented.width * oriented.height > MAX_PIXELS:
                    raise SourceVisualMediaError("PIXEL_LIMIT")
                if "A" in oriented.getbands():
                    alpha = oriented.getchannel("A")
                    if alpha.getextrema()[1] == 0:
                        raise SourceVisualMediaError("ALPHA_ONLY")
                rgb = _srgb_rgb(oriented)
                rgb.load()
    except SourceVisualMediaError:
        raise
    except Image.DecompressionBombError:
        raise SourceVisualMediaError("DECOMPRESSION_BOMB") from None
    except Image.DecompressionBombWarning:
        raise SourceVisualMediaError("DECOMPRESSION_BOMB") from None
    except (ValueError, OSError, SyntaxError):
        raise SourceVisualMediaError("DECODE_FAILED") from None

    if rgb.width <= 0 or rgb.height <= 0:
        raise SourceVisualMediaError("INVALID_DIMENSIONS")
    pixels = rgb.tobytes()
    return _DecodedImage(
        image=rgb,
        pixel_sha256=hashlib.sha256(pixels).hexdigest(),
        width=rgb.width,
        height=rgb.height,
    )


def _encode_webp(image: Image.Image, quality: int) -> bytes:
    output = io.BytesIO()
    image.save(
        output,
        format="WEBP",
        quality=quality,
        method=6,
        lossless=False,
        exact=True,
    )
    return output.getvalue()


def _letterbox(image: Image.Image) -> Image.Image:
    contained = image.copy()
    contained.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (MAX_WIDTH, MAX_HEIGHT), NEUTRAL_LETTERBOX)
    left = (MAX_WIDTH - contained.width) // 2
    top = (MAX_HEIGHT - contained.height) // 2
    canvas.paste(contained, (left, top))
    contained.close()
    return canvas


def prepare_webp(value: bytes | bytearray | memoryview | BinaryIO | Path | str) -> PreparedVisualAsset:
    """Decode one static image and return a bounded deterministic WebP."""

    decoded = _decode_image(value)
    try:
        contained = _letterbox(decoded.image)
        encoded = None
        for quality in WEBP_QUALITIES:
            candidate = _encode_webp(contained, quality)
            if len(candidate) <= MAX_OUTPUT_BYTES:
                encoded = candidate
                break
        if encoded is None:
            raise SourceVisualMediaError("OUTPUT_TOO_LARGE")
        return PreparedVisualAsset(
            encoded_bytes=encoded,
            asset_sha256=hashlib.sha256(encoded).hexdigest(),
            width=MAX_WIDTH,
            height=MAX_HEIGHT,
        )
    except SourceVisualMediaError:
        raise
    except (OSError, ValueError) as exc:
        raise SourceVisualMediaError("ENCODE_FAILED", exc) from None
    finally:
        decoded.image.close()
        if "contained" in locals():
            contained.close()


def image_quality_score(value: bytes | bytearray | memoryview | BinaryIO | Path | str) -> float:
    """Return a stable score based only on decoded pixels."""

    decoded = _decode_image(value)
    image = decoded.image
    try:
        sample = image.copy()
        sample.thumbnail((256, 256), Image.Resampling.BILINEAR)
        gray = sample.convert("L")
        stat = ImageStat.Stat(gray)
        mean = stat.mean[0] / 255.0
        variance = min(1.0, stat.var[0] / (255.0 * 255.0 / 12.0))
        # Neighbor differences provide an inexpensive deterministic sharpness
        # signal without introducing a numerical dependency into this module.
        raw = list(gray.getdata())
        width, height = gray.size
        if width > 1 and height > 1:
            differences = [
                abs(raw[index] - raw[index + 1]) + abs(raw[index] - raw[index + width])
                for index in range((width - 1) * (height - 1))
            ]
            edge_variance = min(1.0, (sum(differences) / max(1, len(differences))) / 255.0)
        else:
            edge_variance = 0.0
        resolution = min(1.0, (decoded.width * decoded.height) / (MAX_WIDTH * MAX_HEIGHT))
        exposure = max(0.0, 1.0 - abs(mean - 0.5) * 2.0)
        return round(0.35 * resolution + 0.30 * edge_variance + 0.20 * exposure + 0.15 * variance, 8)
    finally:
        image.close()


def _locator_key(locator: Mapping[str, int | str]) -> tuple[str, str]:
    if "page" in locator:
        return ("page", f"{int(locator['page']):08d}")
    if "timestamp_ms" in locator:
        return ("timestamp_ms", f"{int(locator['timestamp_ms']):016d}")
    return ("resource_id", str(locator.get("resource_id", ""))[:128])


def select_candidate(candidates: Iterable[VisualCandidate]) -> VisualCandidate | None:
    """Select the best candidate with fixed score and stable tie-breakers."""

    values = list(candidates)
    if not values:
        return None
    return min(
        values,
        key=lambda candidate: (
            -round(float(candidate.score), 8),
            _locator_key(candidate.locator),
            str(candidate.locator.get("resource_id", ""))[:128],
            candidate.sha256,
            candidate.stable_key[:128],
        ),
    )


def build_alt_text(title: str, source_kind: str, candidate: VisualCandidate) -> str:
    """Build neutral, bounded alt text from title, kind, origin, and locator."""

    safe_title = " ".join(str(title).split())[:160] or "Source"
    kind = " ".join(str(source_kind).split())[:64] or "source"
    origin_label = {
        "embedded": "Embedded image",
        "video_frame": "Video frame",
        "audio_artwork": "Embedded artwork",
    }.get(candidate.origin, "Source visual")
    if "page" in candidate.locator:
        location = f"page {int(candidate.locator['page'])}"
    elif "timestamp_ms" in candidate.locator:
        location = f"at {int(candidate.locator['timestamp_ms'])} milliseconds"
    else:
        location = "embedded resource"
    return f"{safe_title}, {kind}, {origin_label}, {location}"[:300]


__all__ = [
    "ALLOWED_FORMATS",
    "MAX_HEIGHT",
    "MAX_OUTPUT_BYTES",
    "MAX_PIXELS",
    "MAX_WIDTH",
    "NEUTRAL_LETTERBOX",
    "SourceVisualMediaError",
    "VisualCandidate",
    "WEBP_QUALITIES",
    "build_alt_text",
    "image_quality_score",
    "prepare_webp",
    "select_candidate",
]
