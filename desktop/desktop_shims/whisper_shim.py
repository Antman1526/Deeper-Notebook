"""OpenAI-compatible STT shim wrapping faster-whisper.

Run as:
    python -m desktop_shims.whisper_shim --port 8765 --model base.en

Exposes:
    GET  /health                       → {"status": "ok"}
    POST /v1/audio/transcriptions      → multipart form (file), returns {"text": ...}

The --model argument accepts either a faster-whisper model size string
(e.g. "base.en", "small", "medium") or a path to a directory containing
a pre-converted CTranslate2 model.  On first run the model is downloaded
from HuggingFace (~150 MB for base.en) and cached in ~/.cache/huggingface.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


def build_app(model: Any) -> FastAPI:
    """Build the FastAPI app with the (already-loaded) faster-whisper model injected.

    `model` is a faster_whisper.WhisperModel instance.
    """
    app = FastAPI(title="Open Notebook Plus — Whisper STT shim")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/audio/transcriptions")
    async def transcribe(
        file: UploadFile = File(...),
        model_id: str = Form("whisper-base-en", alias="model"),
    ) -> dict:
        try:
            audio_bytes = await file.read()
            # Write to a temp file because faster-whisper wants a file path
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            segments, _info = model.transcribe(tmp_path)
            text = " ".join(seg.text for seg in segments).strip()
            Path(tmp_path).unlink(missing_ok=True)
            return {"text": text}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--model", required=True,
        help="faster-whisper model name ('base.en', 'small', etc.) or path to "
             "a CTranslate2 model directory",
    )
    args = parser.parse_args(argv)

    # Lazy import — only at runtime; tests inject a fake model.
    from faster_whisper import WhisperModel

    # cpu + int8 keeps RAM low on desktops; base.en ~150 MB on disk.
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    app = build_app(model=model)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
