from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Allow importing the shim package by adding desktop to sys.path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.whisper_shim import build_app


def _fake_whisper_model(transcript: str = "hello world"):
    fake = MagicMock()
    # whisper-cpp-python style: model(audio_bytes).transcribe() → result dict
    fake.transcribe.return_value = {"text": transcript}
    return fake


def test_health_returns_200():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_transcribe_returns_text():
    app = build_app(model=_fake_whisper_model("the quick brown fox"))
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/transcriptions",
            files={"file": ("clip.wav", b"FAKEWAV", "audio/wav")},
            data={"model": "whisper-base-en"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["text"] == "the quick brown fox"


def test_transcribe_rejects_missing_file():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        r = c.post("/v1/audio/transcriptions", data={"model": "whisper-base-en"})
        assert r.status_code == 422  # FastAPI: missing required form file
