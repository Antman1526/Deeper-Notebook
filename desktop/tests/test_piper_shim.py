from __future__ import annotations

import sys
import wave
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.piper_shim import build_app
from fastapi.testclient import TestClient


@dataclass
class _FakeAudioChunk:
    """Minimal stand-in for piper.voice.AudioChunk."""

    sample_rate: int = 22050
    sample_width: int = 2
    sample_channels: int = 1
    audio_float_array: np.ndarray = field(
        default_factory=lambda: np.zeros(100, dtype=np.float32)
    )
    phonemes: list[str] = field(default_factory=list)
    phoneme_ids: list[int] = field(default_factory=list)


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


def test_models_use_canonical_owner_identity():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        body = c.get("/v1/models").json()

    assert {model["owned_by"] for model in body["data"]} == {"deeper-notebook"}


def test_speech_returns_wav():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/speech",
            json={
                "input": "Hello world",
                "voice": "alex",
                "model": "piper-amy-en",
            },
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/wav"
        # Body is a valid WAV
        wav = wave.open(BytesIO(r.content))
        assert wav.getnchannels() == 1


def test_speech_unknown_voice_falls_back_to_first():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/speech",
            json={
                "input": "Hello",
                "voice": "nobody",
                "model": "x",
            },
        )
        assert r.status_code == 200  # falls back, doesn't error


def test_speech_missing_input_400():
    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        r = c.post("/v1/audio/speech", json={"voice": "alex", "model": "x"})
        assert r.status_code == 422


def test_speech_rejects_input_over_max_chars():
    """v0.7.7 regression: speech() must reject input strings over
    _MAX_INPUT_CHARS with HTTP 413. Without this cap, a buggy caller
    passing a 10 MB text string would consume gigabytes of RAM as
    Piper synthesizes the whole thing into BytesIO."""
    from desktop_shims.piper_shim import _MAX_INPUT_CHARS

    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        # _MAX_INPUT_CHARS + 1 char → must reject
        oversize = "x" * (_MAX_INPUT_CHARS + 1)
        r = c.post("/v1/audio/speech", json={"input": oversize})
    assert r.status_code == 413
    body = r.json()
    assert "cap is" in body["detail"]
    assert str(_MAX_INPUT_CHARS) in body["detail"]


def test_speech_accepts_input_at_max_chars():
    """Boundary case: input EQUAL to the cap is allowed (the check is
    strict greater-than). Catches off-by-one regressions."""
    from desktop_shims.piper_shim import _MAX_INPUT_CHARS

    app = build_app(voices=_fake_piper_voices())
    with TestClient(app) as c:
        at_cap = "x" * _MAX_INPUT_CHARS
        r = c.post("/v1/audio/speech", json={"input": at_cap})
    # Synthesizer is mocked so it returns immediately with fake chunks;
    # we don't care about the audio bytes, only that the cap didn't
    # reject this boundary case.
    assert r.status_code == 200


def test_speech_max_chars_is_local_friendly():
    """The cap should be generous enough for legitimate podcast
    segments (typically 100-300 words = ~500-2000 chars per segment)
    but tight enough to protect against runaway input. Pin to a
    reasonable range so an over-zealous refactor can't degrade UX
    OR safety."""
    from desktop_shims.piper_shim import _MAX_INPUT_CHARS

    assert 10_000 <= _MAX_INPUT_CHARS <= 200_000, (
        f"_MAX_INPUT_CHARS={_MAX_INPUT_CHARS} is outside the safe range for local TTS"
    )
