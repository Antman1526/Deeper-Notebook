"""OpenAI-compatible STT shim wrapping whisper-cpp-python.

Run as:
    python -m desktop_shims.whisper_shim --port 8765 --model /path/to/ggml-base.en.bin

Exposes:
    GET  /health                       → {"status": "ok"}
    POST /v1/audio/transcriptions      → multipart form (file), returns {"text": ...}
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


def build_app(model: Any) -> FastAPI:
    """Build the FastAPI app with the (already-loaded) whisper model injected.

    `model` only needs a `transcribe(audio_path_or_bytes) -> {"text": str}` method.
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
            # Write to a temp file because whisper-cpp-python wants a path
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            result = model.transcribe(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            return {"text": result.get("text", "")}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--model", required=True, help="Path to ggml-*.bin")
    args = parser.parse_args(argv)

    # Lazy import — only at runtime; tests inject a fake model.
    from whisper_cpp_python import Whisper

    model = Whisper(args.model)
    app = build_app(model=model)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
