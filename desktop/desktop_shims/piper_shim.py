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

# v0.7.7 — Cap on input text length for one TTS request. 50,000 chars
# ≈ 10 minutes of synthesized audio at typical speech rates (~150 wpm,
# ~5 chars/word). Plenty for any legitimate single segment of a
# generated podcast. The cap protects against a buggy caller (or
# malicious local process) blowing the shim's memory by passing a
# huge text — Piper accumulates the entire WAV in BytesIO before
# returning, so input length directly drives RAM usage.
_MAX_INPUT_CHARS = 50_000


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

    app = FastAPI(title="Deeper Notebook — Piper TTS shim")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "voices": list(voices.keys())}

    # v0.7.207 — OpenAI-compatible `/v1/models` discovery endpoint
    # (same rationale as whisper_shim.py). Each voice surfaces as
    # an OpenAI-shaped model entry so the credential test in the
    # UI succeeds and the user sees which voices are available.
    @app.get("/v1/models")
    def list_models() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": name,
                    "object": "model",
                    "owned_by": "deeper-notebook",
                }
                for name in voices.keys()
            ],
        }

    @app.post("/v1/audio/speech")
    def speech(req: SpeechRequest) -> Response:
        # v0.7.7 — reject oversize input early. Piper synthesizes the
        # entire text into a single BytesIO before returning, so a
        # 10 MB input string would consume gigabytes of RAM and pin a
        # CPU core for minutes. Caller should split into segments.
        if len(req.input) > _MAX_INPUT_CHARS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Input text is {len(req.input)} chars; cap is "
                    f"{_MAX_INPUT_CHARS}. Split into smaller segments."
                ),
            )
        voice_name = req.voice or default_voice
        if voice_name not in voices:
            voice_name = default_voice
        v = voices[voice_name]
        buf = io.BytesIO()
        try:
            # piper >= 0.0.3 returns an iterable of AudioChunk objects;
            # convert the float32 arrays to int16 PCM and write one WAV.
            import numpy as np

            chunks = list(v.synthesize(req.input))
            if not chunks:
                raise HTTPException(status_code=500, detail="Piper returned no audio")
            c0 = chunks[0]
            sample_rate = c0.sample_rate
            sample_width = c0.sample_width  # bytes per sample (2 for int16)
            channels = c0.sample_channels
            # Concatenate all float arrays and convert to PCM int16.
            combined = np.concatenate([c.audio_float_array for c in chunks])
            pcm = np.clip(combined, -1.0, 1.0)
            pcm_int16 = (pcm * 32767).astype(np.int16)
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_int16.tobytes())
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(content=buf.getvalue(), media_type="audio/wav")

    return app


def _load_voice(model_path: Path) -> Any:
    """Lazy-load a Piper voice object from an .onnx path."""
    from piper.voice import PiperVoice

    return PiperVoice.load(str(model_path), config_path=str(model_path) + ".json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--voice",
        action="append",
        required=True,
        help="Voice in form NAME=PATH (e.g. alex=/path/to/amy.onnx). Repeatable.",
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
