from __future__ import annotations

import wave
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.piper_shim import build_app


@dataclass
class _FakeAudioChunk:
    """Minimal stand-in for piper.voice.AudioChunk."""
    sample_rate: int = 22050
    sample_width: int = 2
    sample_channels: int = 1
    audio_float_array: np.ndarray = field(
        default_factory=lambda: np.zeros(100, dtype=np.float32)
    )
    phonemes: List[str] = field(default_factory=list)
    phoneme_ids: List[int] = field(default_factory=list)


def _fake_piper_voices():
    """Build a {voice_name: piper_voice_obj} dict. piper_voice_obj.synthesize
    returns an iterable of AudioChunk-like objects (new piper >= 0.0.3 API).
    """
    def make():
        v = MagicMock()
        v.synthesize.return_value = [_FakeAudioChunk()]
        return v
    return {"alex": make(), "sam": make()}


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
