from __future__ import annotations

import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.piper_shim import build_app


def _fake_piper_voices():
    """Build a {voice_name: piper_voice_obj} dict. piper_voice_obj.synthesize
    writes WAV bytes to the given file-like object.
    """
    def make(text_per_call: str):
        v = MagicMock()
        def synth(text, wav_file, **kw):
            # Minimal valid WAV
            with wave.open(wav_file, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(b"\x00\x00" * 100)
        v.synthesize.side_effect = synth
        return v
    return {"alex": make("alex"), "sam": make("sam")}


def test_health_returns_200():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_speech_returns_wav():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post("/v1/audio/speech", json={
            "input": "Hello world",
            "voice": "alex",
            "model": "piper-amy-en",
        })
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/wav"
        # Body is a valid WAV
        wav = wave.open(BytesIO(r.content))
        assert wav.getnchannels() == 1


def test_speech_unknown_voice_falls_back_to_first():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post("/v1/audio/speech", json={
            "input": "Hello", "voice": "nobody", "model": "x",
        })
        assert r.status_code == 200  # falls back, doesn't error


def test_speech_missing_input_400():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post("/v1/audio/speech", json={"voice": "alex", "model": "x"})
        assert r.status_code == 422
