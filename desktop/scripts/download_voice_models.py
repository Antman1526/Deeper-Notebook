#!/usr/bin/env python3
"""Download Whisper.cpp + Piper voice models into the user's model dir.

Usage:
    python -m desktop.scripts.download_voice_models [--model-dir PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        default=str(Path.home() / "Desktop" / "AI_Models"),
        help="Where to put the downloaded models (default: ~/Desktop/AI_Models)",
    )
    args = parser.parse_args()
    model_dir = Path(args.model_dir).expanduser()
    model_dir.mkdir(parents=True, exist_ok=True)

    from desktop import model_downloads

    def progress(msg: str) -> None:
        print(msg)

    stt = model_downloads.ensure_stt_model(model_dir, progress=progress)
    tts = model_downloads.ensure_tts_model(model_dir, progress=progress)

    print()
    print("STT model:", stt if stt else "FAILED")
    print("TTS model:", tts if tts else "FAILED")
    return 0 if (stt and tts) else 1


if __name__ == "__main__":
    sys.exit(main())
