"""OpenAI-compatible TTS shim wrapping piper-tts.

Run as:
    python -m desktop_shims.piper_shim --port 8766 \\
        --voice alex=/path/to/en_US-amy-medium.onnx \\
        --voice sam=/path/to/en_US-ryan-high.onnx

Exposes:
    GET  /health                  → {"status": "ok", "voices": [...]}
    POST /v1/audio/speech         → JSON {input, voice?, model?} → audio/wav
"""
from __future__ import annotations

import argparse
import io
import sys
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


class SpeechRequest(BaseModel):
    input: str
    voice: str | None = None
    model: str | None = None


def build_app(voices: dict[str, Any]) -> FastAPI:
    """Build the FastAPI app with pre-loaded Piper voices injected.

    `voices` maps user-facing name → piper_voice_obj where the object has
    .synthesize(text: str, wav_file: BinaryIO) -> None.
    """
    if not voices:
        raise ValueError("piper_shim.build_app needs at least one voice")
    default_voice = next(iter(voices))

    app = FastAPI(title="Open Notebook Plus — Piper TTS shim")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "voices": list(voices.keys())}

    @app.post("/v1/audio/speech")
    def speech(req: SpeechRequest) -> Response:
        voice_name = req.voice or default_voice
        if voice_name not in voices:
            voice_name = default_voice
        v = voices[voice_name]
        buf = io.BytesIO()
        try:
            v.synthesize(req.input, buf)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(content=buf.getvalue(), media_type="audio/wav")

    return app


def _load_voice(model_path: Path) -> Any:
    """Lazy-load a Piper voice object from an .onnx path."""
    from piper.voice import PiperVoice
    return PiperVoice.load(str(model_path),
                           config_path=str(model_path) + ".json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--voice", action="append", required=True,
        help='Voice in form NAME=PATH (e.g. alex=/path/to/amy.onnx). Repeatable.',
    )
    args = parser.parse_args(argv)

    voices = {}
    for spec in args.voice:
        name, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--voice expects NAME=PATH, got {spec!r}")
        voices[name] = _load_voice(Path(path))

    app = build_app(voices=voices)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
