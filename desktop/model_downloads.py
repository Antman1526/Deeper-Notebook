"""Auto-download recommended local models (embedding, STT, TTS) on first launch.

Each download is idempotent and skipped when the target file exists.
Failures are non-fatal — logged to ~/.deeper-notebook/logs/downloads.log
and the launcher continues without that model.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import httpx

log = logging.getLogger(__name__)


# v0.7.188 — chunk size for streamed downloads. 1 MB balances syscall
# overhead vs. per-chunk progress granularity for multi-GB models.
_CHUNK_BYTES = 1 * 1024 * 1024

# Per-chunk idle timeout. urllib's single `timeout=` only bounds the
# initial connect; mid-stream stalls hang indefinitely. httpx's
# Timeout(read=N) applies per-chunk — N seconds of no bytes from
# the server is the failure threshold. 30s is generous for slow
# residential connections but short enough that a truly dead
# CDN connection is caught within half a minute.
_CHUNK_READ_TIMEOUT = 30.0

# Connect/handshake budget — fail fast on dead URLs / TLS issues.
_CONNECT_TIMEOUT = 10.0


# (url, dest_relative_path, friendly_name, expected_size_mb)
EMBEDDING_GGUF = (
    "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/"
    "nomic-embed-text-v1.5.f16.gguf?download=true",
    "GGUF/nomic-embed-text-v1.5.f16.gguf",
    "nomic-embed-text v1.5 (embedding)",
    273,
)

WHISPER_STT = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin?download=true",
    "STT/ggml-base.en.bin",
    "Whisper base.en (speech-to-text)",
    142,
)

# v0.8.67p — the whisper shim uses faster-whisper (CTranslate2 format), NOT
# whisper.cpp. The WHISPER_STT ggml .bin above was NEVER loaded by the shim
# (app.py passed the bare name "base.en", so faster-whisper re-downloaded its
# own CTranslate2 model from HuggingFace on first voice use — a slow, silent
# first-use stall). Pre-download the model the shim ACTUALLY loads, into
# STT/faster-whisper-base.en/, so the shim loads it locally with no HF fetch.
# Size floors (min_bytes) are deliberately loose — just enough to reject HTML
# error pages — so we don't depend on exact upstream file sizes.
_FW_BASE = "https://huggingface.co/Systran/faster-whisper-base.en/resolve/main"
FASTER_WHISPER_STT_DIR = "STT/faster-whisper-base.en"
FASTER_WHISPER_STT_FILES = (
    # (url, filename, min_bytes)
    (f"{_FW_BASE}/config.json?download=true", "config.json", 100),
    (f"{_FW_BASE}/model.bin?download=true", "model.bin", 20_000_000),
    (f"{_FW_BASE}/tokenizer.json?download=true", "tokenizer.json", 10_000),
    (f"{_FW_BASE}/vocabulary.txt?download=true", "vocabulary.txt", 10_000),
)
# Files that must all be present before the local model is preferred over the
# bare "base.en" HF-download fallback (an INCOMPLETE local dir would make
# faster-whisper fail to load — worse than falling back).
FASTER_WHISPER_STT_REQUIRED = tuple(f for _u, f, _m in FASTER_WHISPER_STT_FILES)

PIPER_VOICE_MODEL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/"
    "en_US-amy-medium.onnx?download=true",
    "TTS/en_US-amy-medium.onnx",
    "Piper Amy medium (text-to-speech voice)",
    30,
)
PIPER_VOICE_CONFIG = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/"
    "en_US-amy-medium.onnx.json?download=true",
    "TTS/en_US-amy-medium.onnx.json",
    "Piper Amy medium voice config",
    1,
)

PIPER_RYAN_MODEL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/"
    "en_US-ryan-high.onnx?download=true",
    "TTS/en_US-ryan-high.onnx",
    "Piper Ryan high (text-to-speech voice)",
    78,
)
PIPER_RYAN_CONFIG = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/"
    "en_US-ryan-high.onnx.json?download=true",
    "TTS/en_US-ryan-high.onnx.json",
    "Piper Ryan high voice config",
    1,
)


def _download_one(
    url: str,
    dest: Path,
    label: str,
    progress: Callable[[str], None] | None = None,
    expected_size_mb: int = 0,
    min_bytes: int = 0,
) -> bool:
    """Download url to dest atomically. Returns True if file is present after.

    v0.6.29 fixes:
      1. The previous "skip if file > 100 KB" check let PARTIAL downloads
         pass: a 280 MB embedding model interrupted at 120 MB has
         size_bytes > 100_000, so we skipped re-download — and llama-cpp
         then crashed loading the truncated GGUF header. Now we compare
         against expected_size_mb when provided, with a 20% lower-bound
         tolerance to absorb the size estimate being slightly off.
      2. urllib.request.urlopen previously had no timeout. A flaky CDN
         response could hang the whole launcher forever — the launcher
         spinner showed "Downloading..." and never progressed. Now we
         pass a generous 300s timeout.
      3. tmp.unlink uses missing_ok=True so a race during cleanup doesn't
         crash the worker.

    v0.7.150 — `min_bytes` keyword overrides the expected_size_mb-based
    calculation for files where the MB heuristic doesn't fit. Specifically:
    the Piper `.onnx.json` voice configs are ~5 KB JSON descriptors. The
    previous `expected_size_mb=1` declaration produced an 838 KB threshold
    (1 MB × 0.80) that the real 5 KB file couldn't meet, so every launch
    re-downloaded them — visible as the recurring "Existing X is only
    4882 bytes (expected >= 838860) — re-downloading" warnings in
    launcher.log. With `min_bytes=2048` the actual JSON is correctly
    detected as good (5000 ≥ 2048) and the partial-download protection
    still filters out obvious HTML error pages (typically < 1 KB).
    """
    progress = progress or (lambda msg: None)

    # Skip-if-already-present check. Threshold precedence:
    #   1. explicit min_bytes override (v0.7.150) — used for small files
    #      where the MB-based heuristic produces an unreachable threshold
    #   2. expected_size_mb × 0.80 — for normal-sized weight files
    #   3. legacy 100_000-byte floor — when neither is declared
    if dest.exists():
        existing_bytes = dest.stat().st_size
        if min_bytes > 0:
            min_bytes_ok = min_bytes
        elif expected_size_mb > 0:
            min_bytes_ok = int(expected_size_mb * 1024 * 1024 * 0.80)
        else:
            min_bytes_ok = 100_000
        if existing_bytes >= min_bytes_ok:
            return True
        # Below threshold — looks like a partial / corrupted download.
        # Don't trust it; delete and re-download.
        log.warning(
            "Existing %s is only %d bytes (expected >= %d) — re-downloading",
            dest.name,
            existing_bytes,
            min_bytes_ok,
        )
        try:
            dest.unlink()
        except OSError:
            pass  # if we can't delete it, the rename below will overwrite anyway

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    # v0.7.188 — Resumable streaming download.
    #
    # Pre-fix problems (audit finding #4):
    #   * urllib.urlopen had a single 300s `timeout` that only applied
    #     to the initial connect — once streaming began, an idle stalled
    #     socket could hang indefinitely. The launcher spinner would
    #     show "Downloading…" forever on a flaky CDN.
    #   * `shutil.copyfileobj` runs to completion or fails — no resume
    #     capability. A 5GB GGUF interrupted at 4.8GB simply restarted
    #     from byte 0 on next launch. Multiply by the 4-6 models we
    #     auto-download and a single dropped network event costs
    #     20-30 GB of redundant transfer.
    #
    # Post-fix:
    #   * `httpx.stream(...)` with per-chunk read timeout (_CHUNK_READ_TIMEOUT).
    #     A genuinely stalled connection raises ReadTimeout within 30s
    #     instead of hanging forever.
    #   * `.tmp` partial-download is KEPT between launches. On the next
    #     try we send `Range: bytes=<existing>-` and append. If the
    #     server doesn't support Range (200 vs 206), we fall back to
    #     a full restart — same shape as the pre-fix behaviour, no
    #     regression.
    #   * `start_at_byte` is captured BEFORE the request so any
    #     interrupt that drops mid-write still leaves the partial
    #     for the next launch to resume from.
    try:
        progress(f"Downloading {label} (~{dest.name})…")
        start_at_byte = tmp.stat().st_size if tmp.exists() else 0
        headers: dict[str, str] = {}
        if start_at_byte > 0:
            headers["Range"] = f"bytes={start_at_byte}-"
            log.info(
                "Resuming %s from byte %d (%.1f MB already on disk)",
                label,
                start_at_byte,
                start_at_byte / 1024 / 1024,
            )

        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_CHUNK_READ_TIMEOUT,
            write=_CHUNK_READ_TIMEOUT,
            pool=_CONNECT_TIMEOUT,
        )

        with httpx.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=timeout,
        ) as resp:
            # If we asked for a Range and the server replied with the
            # whole file (200 instead of 206), we have to start over.
            # Append-mode would corrupt by duplicating the prefix.
            if start_at_byte > 0 and resp.status_code == 200:
                log.warning(
                    "Server %s ignored Range header for %s — restarting "
                    "from byte 0 (will not corrupt; just lose %.1f MB of "
                    "redundant work)",
                    url,
                    label,
                    start_at_byte / 1024 / 1024,
                )
                start_at_byte = 0
            resp.raise_for_status()

            mode = "ab" if start_at_byte > 0 else "wb"
            written = start_at_byte
            last_progress_emit = time.monotonic()
            with tmp.open(mode) as f:
                for chunk in resp.iter_bytes(chunk_size=_CHUNK_BYTES):
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    # Throttle progress emissions to at most one per
                    # 2 seconds so we don't flood the launcher log
                    # with megabyte-level updates.
                    if time.monotonic() - last_progress_emit >= 2.0:
                        progress(f"Downloading {label}: {written // 1024 // 1024} MB")
                        last_progress_emit = time.monotonic()

        tmp.rename(dest)
        progress(f"Downloaded {label}: {dest.stat().st_size // 1024 // 1024} MB")
        return True
    except Exception as exc:
        log.warning("Could not download %s: %s", label, exc)
        # v0.7.188 — IMPORTANT: do NOT delete the .tmp on failure.
        # The whole point of the resume support is that next launch
        # picks up where this one left off. The partial-validity
        # check at the top of this function (min_bytes / 80%) handles
        # the case where the partial is in fact corrupted — only
        # dest.unlink() runs there, never tmp.unlink().
        return False


def ensure_embedding_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> Path | None:
    """Download nomic-embed-text into model_dir/GGUF/ if not present.

    Returns the path to the model on success, None on failure.
    """
    url, rel, label, size_mb = EMBEDDING_GGUF
    dest = model_dir / rel
    if _download_one(url, dest, label, progress, expected_size_mb=size_mb):
        return dest
    return None


def ensure_stt_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> Path | None:
    """v0.8.67p — Download the faster-whisper base.en CTranslate2 model into
    model_dir/STT/faster-whisper-base.en/ — the format the whisper shim actually
    loads. Returns the model directory if ALL files downloaded, else None (the
    launcher then falls back to the bare "base.en" name, which faster-whisper
    fetches from HuggingFace on first use).

    Pre-v0.8.67p this downloaded a whisper.cpp ggml .bin that the faster-whisper
    shim never loaded, so first voice use always blocked on a silent HF
    download. Fetching the real model here (in the gated download phase, with
    progress) removes that stall.
    """
    dest_dir = model_dir / FASTER_WHISPER_STT_DIR
    all_ok = True
    for url, fname, min_bytes in FASTER_WHISPER_STT_FILES:
        if not _download_one(
            url,
            dest_dir / fname,
            f"faster-whisper base.en / {fname}",
            progress,
            min_bytes=min_bytes,
        ):
            all_ok = False
    return dest_dir if all_ok else None


# v0.7.150 — Piper `.onnx.json` voice configs are ~5 KB JSON descriptors
# (a few hundred lines of phoneme→model-id mapping). The launcher's
# partial-download protection requires an explicit threshold for files
# this small: the expected_size_mb-based calculation can't produce a
# threshold below `expected_size_mb × 0.80 × 1 MB`, and the legacy
# 100_000-byte floor is also too high. 2048 bytes filters out obvious
# HTML error pages (typically <1 KB) while admitting the real ~5 KB JSON.
_PIPER_CONFIG_MIN_BYTES = 2048


def ensure_tts_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Amy medium voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, onnx_size = PIPER_VOICE_MODEL
    cfg_url, cfg_rel, cfg_label, _cfg_size = PIPER_VOICE_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if _download_one(
        onnx_url, onnx, onnx_label, progress, expected_size_mb=onnx_size
    ) and _download_one(
        cfg_url, cfg, cfg_label, progress, min_bytes=_PIPER_CONFIG_MIN_BYTES
    ):
        return (onnx, cfg)
    return None


def ensure_secondary_tts_voice(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Ryan high voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, onnx_size = PIPER_RYAN_MODEL
    cfg_url, cfg_rel, cfg_label, _cfg_size = PIPER_RYAN_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if _download_one(
        onnx_url, onnx, onnx_label, progress, expected_size_mb=onnx_size
    ) and _download_one(
        cfg_url, cfg, cfg_label, progress, min_bytes=_PIPER_CONFIG_MIN_BYTES
    ):
        return (onnx, cfg)
    return None
