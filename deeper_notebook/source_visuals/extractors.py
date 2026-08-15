"""Bounded local PDF, video-frame, and audio-artwork extractors."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from pathlib import Path
from typing import Iterable

import fitz
import imageio_ffmpeg

from deeper_notebook.source_visuals.media import (
    SourceVisualMediaError,
    VisualCandidate,
    _decode_image,
    build_alt_text,
    image_quality_score,
    prepare_webp,
)

MAX_PDF_PAGES = 24
MAX_PDF_CANDIDATES = 64
MAX_SUBPROCESS_OUTPUT = 8 * 1024 * 1024
VIDEO_FRAME_TIMEOUT_SECONDS = 15.0
VIDEO_JOB_TIMEOUT_SECONDS = 60.0
_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d{2})(?:,|\s|$)")


def _bounded_path(value: str | Path) -> Path:
    path = Path(value)
    if not path:
        raise SourceVisualMediaError("INPUT_READ_FAILED")
    return path


def _candidate_from_bytes(
    *,
    origin: str,
    locator: dict[str, int | str],
    encoded_bytes: bytes,
    stable_key: str,
) -> VisualCandidate | None:
    try:
        decoded = _decode_image(encoded_bytes)
        width, height = decoded.width, decoded.height
        if (
            min(width, height) < 32
            or width * height < 4_096
            or max(width / max(1, height), height / max(1, width)) > 8.0
        ):
            decoded.image.close()
            return None
        score = image_quality_score(encoded_bytes)
        decoded.image.close()
    except SourceVisualMediaError:
        return None
    return VisualCandidate(origin, locator, bytes(encoded_bytes), score, stable_key)


def extract_pdf_candidates(
    source: str | Path | bytes,
    *,
    max_pages: int = MAX_PDF_PAGES,
    max_candidates: int = MAX_PDF_CANDIDATES,
) -> list[VisualCandidate]:
    """Extract at most 64 eligible embedded images from the first 24 pages."""

    if max_pages < 1 or max_candidates < 1:
        return []
    try:
        if isinstance(source, bytes):
            document = fitz.open(stream=source, filetype="pdf")
        else:
            document = fitz.open(_bounded_path(source))
    except (OSError, RuntimeError, ValueError):
        raise SourceVisualMediaError("PDF_DECODE_FAILED") from None

    candidates: list[VisualCandidate] = []
    seen_bytes: set[str] = set()
    seen_pixels: set[str] = set()
    inspected = 0
    inspect_limit = min(MAX_PDF_CANDIDATES, max_candidates)
    try:
        page_limit = min(MAX_PDF_PAGES, max_pages, len(document))
        for page_number in range(page_limit):
            if inspected >= inspect_limit:
                break
            try:
                images = document[page_number].get_images(full=True)
            except (RuntimeError, ValueError):
                continue
            for image_info in images:
                if inspected >= inspect_limit:
                    break
                inspected += 1
                try:
                    xref = int(image_info[0])
                    extracted = document.extract_image(xref)
                    encoded = bytes(extracted.get("image", b""))
                    resource_id = str(xref)
                except (KeyError, IndexError, RuntimeError, TypeError, ValueError):
                    continue
                if not encoded:
                    continue
                encoded_hash = hashlib.sha256(encoded).hexdigest()
                if encoded_hash in seen_bytes:
                    continue
                try:
                    decoded = _decode_image(encoded)
                    pixel_hash = decoded.pixel_sha256
                    decoded.image.close()
                except SourceVisualMediaError:
                    continue
                if pixel_hash in seen_pixels:
                    continue
                seen_bytes.add(encoded_hash)
                seen_pixels.add(pixel_hash)
                candidate = _candidate_from_bytes(
                    origin="embedded",
                    locator={"page": page_number + 1, "resource_id": resource_id},
                    encoded_bytes=encoded,
                    stable_key=f"pdf:{page_number + 1:04d}:{resource_id}:{encoded_hash}",
                )
                if candidate is not None:
                    candidates.append(candidate)
    finally:
        document.close()
    return candidates


def _duration_ms_from_text(stderr: bytes | str) -> int:
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else str(stderr)
    match = _DURATION_RE.search(text)
    if match is None:
        raise SourceVisualMediaError("VIDEO_DURATION_INVALID")
    hours, minutes, seconds = int(match.group(1)), int(match.group(2)), float(match.group(3))
    if minutes >= 60 or seconds >= 60 or hours >= 100:
        raise SourceVisualMediaError("VIDEO_DURATION_INVALID")
    duration_ms = int(round((hours * 3_600 + minutes * 60 + seconds) * 1_000))
    if duration_ms <= 0:
        raise SourceVisualMediaError("VIDEO_DURATION_INVALID")
    return duration_ms


def video_timestamps_ms(duration_ms: int) -> tuple[int, ...]:
    """Return exact, deduplicated 25%, 50%, and 75% timestamps."""

    if duration_ms <= 0:
        return ()
    timestamps: list[int] = []
    for numerator in (25, 50, 75):
        value = int(duration_ms * numerator // 100)
        if value not in timestamps:
            timestamps.append(value)
    return tuple(timestamps[:3])


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(min(64 * 1024, limit - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise SourceVisualMediaError("FFMPEG_OUTPUT_LIMIT")
    return b"".join(chunks)


async def _stop_process(process: object) -> None:
    terminate = getattr(process, "terminate", None)
    if callable(terminate):
        terminate()
    try:
        await asyncio.wait_for(getattr(process, "wait")(), timeout=1.0)
        return
    except (asyncio.TimeoutError, ProcessLookupError):
        pass
    kill = getattr(process, "kill", None)
    if callable(kill):
        kill()
    try:
        await getattr(process, "wait")()
    except (asyncio.CancelledError, ProcessLookupError):
        pass


async def _run_ffmpeg(*args: str, timeout: float) -> tuple[bytes, bytes]:
    """Run the package ffmpeg binary with bounded pipes and no shell."""

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError):
        raise SourceVisualMediaError("FFMPEG_UNAVAILABLE") from None
    assert process.stdout is not None and process.stderr is not None
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.gather(
                _read_capped(process.stdout, MAX_SUBPROCESS_OUTPUT),
                _read_capped(process.stderr, MAX_SUBPROCESS_OUTPUT),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        await _stop_process(process)
        raise SourceVisualMediaError("TIMEOUT") from None
    except SourceVisualMediaError:
        await _stop_process(process)
        raise
    except asyncio.CancelledError:
        await _stop_process(process)
        raise
    returncode = await process.wait()
    if returncode != 0:
        raise SourceVisualMediaError("FFMPEG_FAILED")
    return stdout, stderr


async def _probe_video_duration(source: Path) -> int:
    _stdout, stderr = await _run_ffmpeg(
        "-nostdin",
        "-i",
        str(source),
        "-f",
        "null",
        "-",
        timeout=VIDEO_FRAME_TIMEOUT_SECONDS,
    )
    return _duration_ms_from_text(stderr)


async def _extract_video_frame(source: Path, timestamp_ms: int) -> bytes:
    seconds = timestamp_ms / 1_000
    timestamp = f"{seconds:.3f}"
    stdout, _stderr = await _run_ffmpeg(
        "-nostdin",
        "-ss",
        timestamp,
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
        timeout=VIDEO_FRAME_TIMEOUT_SECONDS,
    )
    if not stdout:
        raise SourceVisualMediaError("VIDEO_FRAME_EMPTY")
    return stdout


async def extract_video_candidates(source: str | Path) -> list[VisualCandidate]:
    """Probe duration and extract three deterministic representative frames."""

    path = _bounded_path(source)
    started = time.monotonic()
    try:
        duration_ms = await asyncio.wait_for(
            _probe_video_duration(path), timeout=VIDEO_JOB_TIMEOUT_SECONDS
        )
        candidates: list[VisualCandidate] = []
        for timestamp_ms in video_timestamps_ms(duration_ms):
            elapsed = time.monotonic() - started
            remaining = VIDEO_JOB_TIMEOUT_SECONDS - elapsed
            if remaining <= 0:
                raise SourceVisualMediaError("TIMEOUT")
            try:
                frame = await asyncio.wait_for(
                    _extract_video_frame(path, timestamp_ms),
                    timeout=min(VIDEO_FRAME_TIMEOUT_SECONDS, remaining),
                )
            except asyncio.TimeoutError:
                raise SourceVisualMediaError("TIMEOUT") from None
            candidate = _candidate_from_bytes(
                origin="video_frame",
                locator={"timestamp_ms": timestamp_ms},
                encoded_bytes=frame,
                stable_key=f"video:{timestamp_ms:016d}:{hashlib.sha256(frame).hexdigest()}",
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates
    except asyncio.TimeoutError:
        raise SourceVisualMediaError("TIMEOUT") from None
    except SourceVisualMediaError:
        raise
    except (OSError, ValueError):
        raise SourceVisualMediaError("VIDEO_FAILED") from None


async def extract_audio_artwork(source: str | Path) -> VisualCandidate | None:
    """Extract one attached picture and never decode the audio stream."""

    path = _bounded_path(source)
    try:
        stdout, stderr = await _run_ffmpeg(
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:v:0?",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
            timeout=VIDEO_FRAME_TIMEOUT_SECONDS,
        )
    except SourceVisualMediaError as exc:
        if exc.code == "FFMPEG_FAILED":
            return None
        raise
    stream_info = stderr.decode("utf-8", "replace").lower()
    if "attached pic" not in stream_info or not stdout:
        return None
    candidate = _candidate_from_bytes(
        origin="audio_artwork",
        locator={"resource_id": "attached-picture-0"},
        encoded_bytes=stdout,
        stable_key=f"audio:attached-picture-0:{hashlib.sha256(stdout).hexdigest()}",
    )
    return candidate


def candidates_alt_text(title: str, source_kind: str, candidates: Iterable[VisualCandidate]) -> dict[str, str]:
    """Return stable alt text keyed by each candidate's stable key."""

    return {
        candidate.stable_key: build_alt_text(title, source_kind, candidate)
        for candidate in candidates
    }


__all__ = [
    "MAX_PDF_CANDIDATES",
    "MAX_PDF_PAGES",
    "MAX_SUBPROCESS_OUTPUT",
    "VIDEO_FRAME_TIMEOUT_SECONDS",
    "VIDEO_JOB_TIMEOUT_SECONDS",
    "SourceVisualMediaError",
    "VisualCandidate",
    "candidates_alt_text",
    "extract_audio_artwork",
    "extract_pdf_candidates",
    "extract_video_candidates",
    "video_timestamps_ms",
]
