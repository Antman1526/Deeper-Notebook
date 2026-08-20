from __future__ import annotations

# Allow importing the shim package by adding desktop to sys.path
import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.whisper_shim import build_app


def _fake_segment(text: str) -> MagicMock:
    seg = MagicMock()
    seg.text = text
    return seg


def _fake_whisper_model(transcript: str = "hello world"):
    """Return a mock that behaves like a faster-whisper WhisperModel.

    faster-whisper API:
        segments, info = model.transcribe(path)
        text = " ".join(seg.text for seg in segments)
    """
    fake = MagicMock()
    fake_seg = _fake_segment(transcript)
    fake.transcribe.return_value = ([fake_seg], MagicMock())
    return fake


def test_health_returns_200():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_models_use_canonical_owner_identity():
    app = build_app(model=_fake_whisper_model())
    with TestClient(app) as c:
        body = c.get("/v1/models").json()

    assert {model["owned_by"] for model in body["data"]} == {"deeper-notebook"}


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


def test_transcribe_cleans_up_temp_file_on_success(tmp_path, monkeypatch):
    """v0.6.13: the .wav temp file must be deleted whether transcribe succeeds
    OR raises. Previously only the happy path cleaned up."""
    import tempfile

    # Capture every NamedTemporaryFile path created so we can verify it's gone.
    created_paths: list[str] = []
    original_ntf = tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        ntf = original_ntf(*args, **kwargs)
        created_paths.append(ntf.name)
        return ntf

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", tracking_ntf)

    app = build_app(model=_fake_whisper_model("hi"))
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/transcriptions",
            files={"file": ("a.wav", b"fake-wav-bytes", "audio/wav")},
        )
    assert r.status_code == 200
    assert r.json()["text"] == "hi"
    assert created_paths, "expected NamedTemporaryFile to have been called"
    for p in created_paths:
        assert not Path(p).exists(), f"temp file leaked: {p}"


def test_transcribe_cleans_up_temp_file_on_exception(tmp_path, monkeypatch):
    """The regression test for the actual bug: transcribe() raises, we still
    delete the temp file."""
    import tempfile

    created_paths: list[str] = []
    original_ntf = tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        ntf = original_ntf(*args, **kwargs)
        created_paths.append(ntf.name)
        return ntf

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", tracking_ntf)

    # Mock that raises (simulating malformed audio / GPU OOM / etc.)
    bad_model = MagicMock()
    bad_model.transcribe.side_effect = RuntimeError("simulated model crash")

    app = build_app(model=bad_model)
    with TestClient(app) as c:
        r = c.post(
            "/v1/audio/transcriptions",
            files={"file": ("a.wav", b"fake", "audio/wav")},
        )
    assert r.status_code == 500
    assert created_paths, "expected NamedTemporaryFile to have been called"
    for p in created_paths:
        assert not Path(p).exists(), f"temp file leaked on exception: {p}"
