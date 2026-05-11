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


def _download_one(url: str, dest: Path, label: str,
                  progress: Callable[[str], None] | None = None) -> bool:
    """Download url to dest atomically. Returns True if file is present after."""
    progress = progress or (lambda msg: None)
    if dest.exists() and dest.stat().st_size > 100_000:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        progress(f"Downloading {label} (~{dest.name})…")
        with urllib.request.urlopen(url) as resp, tmp.open("wb") as f:
            shutil.copyfileobj(resp, f)
        tmp.rename(dest)
        progress(f"Downloaded {label}: {dest.stat().st_size // 1024 // 1024} MB")
        return True
    except Exception as exc:
        log.warning("Could not download %s: %s", label, exc)
        if tmp.exists():
            tmp.unlink()
        return False


def ensure_embedding_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> Path | None:
    """Download nomic-embed-text into model_dir/GGUF/ if not present.

    Returns the path to the model on success, None on failure.
    """
    url, rel, label, _ = EMBEDDING_GGUF
    dest = model_dir / rel
    if _download_one(url, dest, label, progress):
        return dest
    return None


def ensure_stt_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> Path | None:
    """Download Whisper.cpp base.en model into model_dir/STT/."""
    url, rel, label, _ = WHISPER_STT
    dest = model_dir / rel
    if _download_one(url, dest, label, progress):
        return dest
    return None


def ensure_tts_model(
    model_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path] | None:
    """Download Piper Amy medium voice (.onnx + .json) into model_dir/TTS/."""
    onnx_url, onnx_rel, onnx_label, _ = PIPER_VOICE_MODEL
    cfg_url, cfg_rel, cfg_label, _ = PIPER_VOICE_CONFIG
    onnx = model_dir / onnx_rel
    cfg = model_dir / cfg_rel
    if (_download_one(onnx_url, onnx, onnx_label, progress)
            and _download_one(cfg_url, cfg, cfg_label, progress)):
        return (onnx, cfg)
    return None
