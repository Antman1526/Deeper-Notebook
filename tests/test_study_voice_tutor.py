"""RED/GREEN coverage for the optional local-only Study voice tutor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_voice
from deeper_notebook.study.voice_service import (
    MAX_AUDIO_DURATION_SECONDS,
    MAX_UPLOAD_BYTES,
    MAX_TTS_BYTES,
    StudyVoiceService,
)


class FakePlanRepository:
    def __init__(self, *, state: str = "approved") -> None:
        self.plan = SimpleNamespace(
            plan_id="study_plan:one",
            state=state,
            approved_syllabus_version=1,
            preferences=SimpleNamespace(
                model_route="cloud",
                network_allowed=True,
                approved_network_scope=("https://example.edu/",),
            ),
        )
        self.syllabus = SimpleNamespace(
            plan_id="study_plan:one",
            version=1,
            approved_at=SimpleNamespace(),
        )

    async def get(self, plan_id: str):
        return self.plan if plan_id == self.plan.plan_id else None

    async def get_syllabus(self, plan_id: str, *, version: int | None = None):
        if plan_id != self.plan.plan_id or version != self.syllabus.version:
            return None
        return self.syllabus


class FakeSTT:
    provider = "ollama"

    def __init__(self, text: str = "What is spaced repetition?") -> None:
        self.text = text
        self.paths: list[Path] = []

    async def atranscribe(self, *, audio_file: Path):
        self.paths.append(audio_file)
        return SimpleNamespace(text=self.text, duration=None)


class FakeTTS:
    provider = "ollama"

    def __init__(self, data: bytes = b"RIFF-local-audio", content_type: str = "audio/wav") -> None:
        self.data = data
        self.content_type = content_type
        self.calls: list[str] = []

    async def agenerate_speech(self, text: str, voice: str = "default", output_file=None):
        self.calls.append(text)
        return SimpleNamespace(audio_data=self.data, content_type=self.content_type)


class FakeDefaults:
    default_speech_to_text_model = "model:stt"
    default_text_to_speech_model = "model:tts"


class FakeModelRecord:
    def __init__(self, model_type: str, provider: str) -> None:
        self.type = model_type
        self.provider = provider


def _client(monkeypatch, service: StudyVoiceService, *, enabled: bool = True) -> TestClient:
    monkeypatch.setattr(study_voice, "study_workbench_enabled", lambda: enabled)
    monkeypatch.setattr(study_voice, "_service", lambda: service)
    app = FastAPI()
    app.include_router(study_voice.router, prefix="/api")
    return TestClient(app)


def _service(
    *,
    stt=None,
    tts=None,
    state: str = "approved",
    stt_provider: str = "ollama",
    tts_provider: str = "ollama",
    max_upload_bytes: int | None = None,
    max_tts_bytes: int | None = None,
) -> StudyVoiceService:
    records = {
        "model:stt": FakeModelRecord("speech_to_text", stt_provider),
        "model:tts": FakeModelRecord("text_to_speech", tts_provider),
    }
    return StudyVoiceService(
        plan_repository=FakePlanRepository(state=state),
        speech_to_text_getter=AsyncMock(return_value=stt),
        text_to_speech_getter=AsyncMock(return_value=tts),
        defaults_getter=AsyncMock(return_value=FakeDefaults()),
        model_getter=AsyncMock(side_effect=lambda model_id: records.get(model_id)),
        max_upload_bytes=max_upload_bytes,
        max_tts_bytes=max_tts_bytes,
    )


def test_voice_tutor_fails_closed_when_local_speech_model_is_absent(monkeypatch) -> None:
    response = _client(monkeypatch, _service(stt=None)).post(
        "/api/study/plans/study_plan%3Aone/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"


def test_configured_remote_default_never_acquires_or_falls_back_to_cloud(monkeypatch) -> None:
    remote_getter = AsyncMock(return_value=FakeSTT())
    service = StudyVoiceService(
        plan_repository=FakePlanRepository(),
        speech_to_text_getter=remote_getter,
        defaults_getter=AsyncMock(return_value=FakeDefaults()),
        model_getter=AsyncMock(
            return_value=FakeModelRecord("speech_to_text", "openai")
        ),
    )
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    remote_getter.assert_not_awaited()


def test_openai_compatible_local_runtime_provider_is_normalized(monkeypatch) -> None:
    model = FakeSTT()
    model.provider = "openai-compatible"
    response = _client(
        monkeypatch,
        _service(stt=model, stt_provider="openai_compatible"),
    ).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 200


def test_feature_off_is_uniform_404_before_voice_validation(monkeypatch) -> None:
    response = _client(monkeypatch, _service(), enabled=False).post(
        "/api/study/plans/not-a-plan/voice:transcribe",
        files={"audio": ("question.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Study plan not found"}


def test_transcription_enforces_mime_duration_cap_and_cleans_task_file(monkeypatch) -> None:
    model = FakeSTT()
    api = _client(monkeypatch, _service(stt=model))

    bad_type = api.post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.txt", b"audio", "text/plain")},
    )
    assert bad_type.status_code == 422
    assert bad_type.json()["detail"]["code"] == "unsupported_audio_type"

    too_long = api.post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        data={"duration_seconds": str(MAX_AUDIO_DURATION_SECONDS + 1)},
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert too_long.status_code == 422
    assert too_long.json()["detail"]["code"] == "audio_duration_too_long"

    ok = api.post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert ok.status_code == 200
    assert ok.json()["transcript"] == "What is spaced repetition?"
    assert len(model.paths) == 1
    assert not model.paths[0].exists(), "task-owned upload must be deleted in finally"

    too_big = _client(monkeypatch, _service(stt=model, max_upload_bytes=4)).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"12345", "audio/webm")},
    )
    assert too_big.status_code == 413
    assert too_big.json()["detail"]["code"] == "audio_too_large"
    assert MAX_UPLOAD_BYTES > 4


def test_transcription_never_falls_back_to_cloud_and_rejects_empty_output(monkeypatch) -> None:
    cloud = FakeSTT()
    cloud.provider = "openai"
    api = _client(monkeypatch, _service(stt=cloud))
    response = api.post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    assert cloud.paths == []

    empty = _client(monkeypatch, _service(stt=FakeSTT(text="   "))).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "empty_transcription"

    oversized = _client(monkeypatch, _service(stt=FakeSTT(text="x" * (16 * 1024 + 1)))).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert oversized.status_code == 422
    assert oversized.json()["detail"]["code"] == "transcript_too_large"


def test_synthesis_bounds_text_output_and_projects_safe_audio(monkeypatch) -> None:
    tts = FakeTTS()
    api = _client(monkeypatch, _service(tts=tts))
    response = api.post(
        "/api/study/plans/study_plan:one/voice:synthesize",
        json={"text": "A local explanation."},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF-local-audio"
    assert tts.calls == ["A local explanation."]

    too_long = api.post(
        "/api/study/plans/study_plan:one/voice:synthesize",
        json={"text": "x" * (8 * 1024 + 1)},
    )
    assert too_long.status_code == 422
    assert too_long.json()["detail"]

    oversized = _client(monkeypatch, _service(tts=FakeTTS(data=b"12345"), max_tts_bytes=4)).post(
        "/api/study/plans/study_plan:one/voice:synthesize",
        json={"text": "bounded"},
    )
    assert oversized.status_code == 422
    assert oversized.json()["detail"]["code"] == "audio_output_too_large"

    unsafe = _client(monkeypatch, _service(tts=FakeTTS(content_type="application/octet-stream"))).post(
        "/api/study/plans/study_plan:one/voice:synthesize",
        json={"text": "bounded"},
    )
    assert unsafe.status_code == 422
    assert unsafe.json()["detail"]["code"] == "unsafe_audio_type"

    empty = _client(monkeypatch, _service(tts=FakeTTS(data=b""))).post(
        "/api/study/plans/study_plan:one/voice:synthesize",
        json={"text": "bounded"},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "empty_audio_output"
    assert MAX_TTS_BYTES > 4


@pytest.mark.asyncio
async def test_voice_requires_approved_plan_and_cancellation_cleans_upload(monkeypatch) -> None:
    not_approved = _client(monkeypatch, _service(stt=FakeSTT(), state="editing")).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert not_approved.status_code == 404

    class WaitingSTT(FakeSTT):
        async def atranscribe(self, *, audio_file: Path):
            self.paths.append(audio_file)
            await asyncio.Event().wait()

    model = WaitingSTT()
    service = _service(stt=model)
    task = asyncio.create_task(service.transcribe_upload("study_plan:one", _Upload(b"audio"), "audio/webm"))
    awaitable = task
    # The cancellation assertion is intentionally direct at the service seam,
    # where the task-owned temporary-file finally block is observable.
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await awaitable
    assert model.paths and not model.paths[0].exists()


class _Upload:
    filename = "question.webm"
    content_type = "audio/webm"
    size = None

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk
