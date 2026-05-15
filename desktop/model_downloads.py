"""Auto-download recommended local models (embedding, STT, TTS) on first launch.

Each download is idempotent and skipped when the target file exists.
Failures are non-fatal — logged to ~/.open-notebook-plus/logs/downloads.log
and the launcher continues without that model.
"""
from __future__ import annotations

import logging
import shutil
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


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


def _download_one(url: str, dest: Path, label: str,
                  progress: Callable[[str], None] | None = None,
                  expected_size_mb: int = 0) -> bool:
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
    """
    progress = progress or (lambda msg: None)

    # Skip-if-already-present check uses the expected size as the source
    # of truth when we know it; 100 KB is the legacy fallback for entries
    # that don't yet declare an expected_size_mb (the small Piper config
    # JSONs, which are ~1 MB and have no partial-download risk).
    if dest.exists():
        existing_bytes = dest.stat().st_size
        min_bytes_ok = (
            int(expected_size_mb * 1024 * 1024 * 0.80)
            if expected_size_mb > 0
            else 100_000
        )
        if existing_bytes >= min_bytes_ok:
            return True
        # Below threshold — looks like a partial / corrupted download.
        # Don't trust it; delete and re-download.
        log.warning(
            "Existing %s is only %d bytes (expected >= %d) — re-downloading",
            dest.name, existing_bytes, min_bytes_ok,
        )
        try:
            dest.unlink()
        except OSError:
            pass  # if we can't delete it, the rename below will overwrite anyway

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        progress(f"Downloading {label} (~{dest.name})…")
        # 300s timeout for the FIRST byte; for large files we then stream
        # bytes which uses the same socket — no per-byte timeout, so a
        # genuinely slow connection still completes.
        with urllib.request.urlopen(url, timeout=300) as resp, tmp.open("wb") as f:
            shutil.copyfileobj(resp, f)
        tmp.rename(dest)
        progress(f"Downloaded {label}: {dest.stat().st_size // 1024 // 1024} MB")
        return True
    except Exception as exc:
        log.warning("Could not download %s: %s", label, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
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
    """Download Whisper.cpp base.en model into model_dir/STT/."""
    url, rel, label, size_mb = WHISPER_STT
    dest = model_dir / rel
    if _download_one(url, dest, label, progress, expected_size_mb=size_mb):
        return dest
    return None


def ensure_tts_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Amy medium voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, onnx_size = PIPER_VOICE_MODEL
    cfg_url, cfg_rel, cfg_label, cfg_size = PIPER_VOICE_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if (_download_one(onnx_url, onnx, onnx_label, progress, expected_size_mb=onnx_size)
            and _download_one(cfg_url, cfg, cfg_label, progress, expected_size_mb=cfg_size)):
        return (onnx, cfg)
    return None


def ensure_secondary_tts_voice(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Ryan high voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, onnx_size = PIPER_RYAN_MODEL
    cfg_url, cfg_rel, cfg_label, cfg_size = PIPER_RYAN_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if (_download_one(onnx_url, onnx, onnx_label, progress, expected_size_mb=onnx_size)
            and _download_one(cfg_url, cfg, cfg_label, progress, expected_size_mb=cfg_size)):
        return (onnx, cfg)
    return None
