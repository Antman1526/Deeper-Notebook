"""RED/GREEN coverage for the optional local-only Study voice tutor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from esperanto.providers.stt.openai_compatible import OpenAICompatibleSpeechToTextModel
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_voice
from deeper_notebook.study import voice_service as voice_service_module
from deeper_notebook.study.voice_service import (
    MAX_AUDIO_DURATION_SECONDS,
    MAX_TTS_BYTES,
    MAX_UPLOAD_BYTES,
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

    def __init__(self, text: str = "What is spaced repetition?", duration: object = None) -> None:
        self.text = text
        self.duration = duration
        self.paths: list[Path] = []

    async def atranscribe(self, *, audio_file: Path | str):
        self.paths.append(Path(audio_file))
        return SimpleNamespace(text=self.text, duration=self.duration)


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
    def __init__(
        self,
        model_type: str,
        provider: str,
        *,
        credential: str | None = "credential:local",
    ) -> None:
        self.type = model_type
        self.provider = provider
        self.credential = credential


class FakeCredentialRecord:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str | None = None,
        endpoint_stt: str | None = None,
        endpoint_tts: str | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url
        self.endpoint = None
        self.endpoint_stt = endpoint_stt
        self.endpoint_tts = endpoint_tts


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
    credential_base_url: str | None = "http://127.0.0.1:11434",
    credential_provider: str | None = None,
    credential_id: str | None = "credential:local",
    credential_getter=None,
) -> StudyVoiceService:
    records = {
        "model:stt": FakeModelRecord("speech_to_text", stt_provider, credential=credential_id),
        "model:tts": FakeModelRecord("text_to_speech", tts_provider, credential=credential_id),
    }
    provider = credential_provider or stt_provider
    credentials = (
        {
            credential_id: FakeCredentialRecord(
                provider=provider,
                base_url=credential_base_url,
            )
        }
        if credential_id
        else {}
    )
    return StudyVoiceService(
        plan_repository=FakePlanRepository(state=state),
        speech_to_text_getter=AsyncMock(return_value=stt),
        text_to_speech_getter=AsyncMock(return_value=tts),
        defaults_getter=AsyncMock(return_value=FakeDefaults()),
        model_getter=AsyncMock(side_effect=lambda model_id: records.get(model_id)),
        credential_getter=credential_getter or AsyncMock(side_effect=lambda credential_id: credentials.get(credential_id)),
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
            return_value=FakeModelRecord("speech_to_text", "openai", credential=None)
        ),
    )
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    remote_getter.assert_not_awaited()


@pytest.mark.parametrize(
    "provider,base_url",
    [
        ("openai_compatible", "https://api.example.com/v1"),
        ("ollama", "http://192.168.1.25:11434"),
    ],
)
def test_public_or_remote_local_provider_never_acquires_speech_getter(
    monkeypatch,
    provider: str,
    base_url: str,
) -> None:
    getter = AsyncMock(return_value=FakeSTT())
    service = _service(
        stt=FakeSTT(),
        stt_provider=provider,
        credential_provider=provider,
        credential_base_url=base_url,
    )
    service._speech_to_text_getter = getter
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    getter.assert_not_awaited()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost.evil:11434",
        "http://127.0.0.1.evil:11434",
        "http://user:secret@localhost:11434",
        "http://169.254.1.1:11434",
    ],
)
def test_local_endpoint_host_spoofs_fail_closed_before_getter(monkeypatch, base_url: str) -> None:
    getter = AsyncMock(return_value=FakeSTT())
    service = _service(credential_base_url=base_url)
    service._speech_to_text_getter = getter
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    getter.assert_not_awaited()


@pytest.mark.parametrize(
    "base_url",
    ["http://localhost:11434/v1", "http://127.42.0.7:8080/v1", "http://[::1]:9000/v1"],
)
def test_loopback_local_endpoints_are_accepted(monkeypatch, base_url: str) -> None:
    model = FakeSTT()
    response = _client(
        monkeypatch,
        _service(stt=model, stt_provider="openai_compatible", credential_provider="openai_compatible", credential_base_url=base_url),
    ).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 200
    assert model.paths


def test_missing_or_unreadable_credential_fails_closed_without_getter(monkeypatch) -> None:
    getter = AsyncMock(return_value=FakeSTT())
    service = _service(
        credential_getter=AsyncMock(side_effect=RuntimeError("credential unavailable")),
    )
    service._speech_to_text_getter = getter
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    getter.assert_not_awaited()


def test_credential_missing_provider_fails_closed_without_getter(monkeypatch) -> None:
    getter = AsyncMock(return_value=FakeSTT())
    service = _service(
        credential_getter=AsyncMock(
            return_value=FakeCredentialRecord(provider="", base_url="http://127.0.0.1:11434")
        ),
    )
    service._speech_to_text_getter = getter
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    getter.assert_not_awaited()


def test_runtime_public_endpoint_is_rejected_before_transcription(monkeypatch) -> None:
    model = FakeSTT()
    model.base_url = "https://api.example.com/v1"
    response = _client(monkeypatch, _service(stt=model)).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    assert model.paths == []


def test_env_fallback_local_provider_is_not_voice_authority(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    getter = AsyncMock(return_value=FakeSTT())
    service = _service(
        stt_provider="ollama",
        credential_provider="ollama",
        credential_id=None,
        credential_getter=AsyncMock(return_value=None),
    )
    service._speech_to_text_getter = getter
    response = _client(monkeypatch, service).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
    getter.assert_not_awaited()


def test_capability_receipt_acquires_and_validates_runtime_models(monkeypatch) -> None:
    service = _service(stt=FakeSTT(), tts=FakeTTS())
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "ready", "tts": "ready"}
    service._speech_to_text_getter.assert_awaited_once()
    service._text_to_speech_getter.assert_awaited_once()


def test_capability_receipt_fails_closed_for_public_endpoint(monkeypatch) -> None:
    service = _service(
        stt=FakeSTT(),
        tts=FakeTTS(),
        credential_base_url="https://api.example.com/v1",
        credential_provider="openai_compatible",
    )
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "unavailable", "tts": "unavailable"}
    service._speech_to_text_getter.assert_not_awaited()
    service._text_to_speech_getter.assert_not_awaited()


def test_capability_receipt_fails_closed_when_ollama_factory_is_unavailable(monkeypatch) -> None:
    service = _service(stt=None, tts=None)
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "unavailable", "tts": "unavailable"}
    service._speech_to_text_getter.assert_awaited_once()
    service._text_to_speech_getter.assert_awaited_once()


def test_capability_receipt_fails_closed_on_getter_error_without_leaking(monkeypatch) -> None:
    service = _service(stt=FakeSTT(), tts=FakeTTS())
    service._speech_to_text_getter = AsyncMock(side_effect=RuntimeError("factory detail must stay private"))
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "unavailable", "tts": "ready"}
    assert "factory detail" not in response.text


def test_capability_receipt_rejects_public_runtime_endpoint(monkeypatch) -> None:
    runtime = FakeSTT()
    runtime.base_url = "https://api.example.com/v1"
    service = _service(stt=runtime)
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "unavailable", "tts": "unavailable"}


def test_capability_receipt_accepts_a_valid_openai_compatible_runtime(monkeypatch) -> None:
    stt = FakeSTT()
    stt.provider = "openai-compatible"
    tts = FakeTTS()
    tts.provider = "openai-compatible"
    service = _service(
        stt=stt,
        tts=tts,
        stt_provider="openai_compatible",
        tts_provider="openai_compatible",
        credential_provider="openai_compatible",
    )
    response = _client(monkeypatch, service).get(
        "/api/study/plans/study_plan:one/voice:capability",
    )
    assert response.status_code == 200
    assert response.json() == {"stt": "ready", "tts": "ready"}


@pytest.mark.asyncio
async def test_capability_getter_probe_is_bounded() -> None:
    service = _service(stt=FakeSTT(), tts=FakeTTS())
    async def never_finishes():
        await asyncio.Event().wait()

    service._speech_to_text_getter = never_finishes
    service.capability_timeout_seconds = 0.01
    capability = await asyncio.wait_for(service.capability("study_plan:one"), timeout=0.2)
    assert capability == {"stt": "unavailable", "tts": "ready"}


@pytest.mark.asyncio
async def test_concrete_esperanto_transcriber_receives_a_supported_string_path(tmp_path) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "A concrete local transcript."})

    model = OpenAICompatibleSpeechToTextModel(
        model_name="whisper-local",
        api_key="not-required",
        base_url="http://127.0.0.1:8000/v1",
    )
    await model.async_client.aclose()
    model.async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    path = tmp_path / "question.webm"
    path.write_bytes(b"audio")
    try:
        result = await voice_service_module._invoke_transcriber(model, path)
    finally:
        await model.async_client.aclose()
    assert result.text == "A concrete local transcript."
    assert requests and requests[0].url.path.endswith("/audio/transcriptions")


def test_feature_off_capability_is_uniform_404_before_plan_validation(monkeypatch) -> None:
    response = _client(monkeypatch, _service(), enabled=False).get(
        "/api/study/plans/not-a-plan/voice:capability",
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Study plan not found"}


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


def test_model_returned_duration_is_authoritative_and_bounded(monkeypatch) -> None:
    response = _client(
        monkeypatch,
        _service(stt=FakeSTT(duration=MAX_AUDIO_DURATION_SECONDS + 1)),
    ).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        data={"duration_seconds": "1"},
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "audio_duration_too_long"


def test_invalid_model_returned_duration_fails_safe(monkeypatch) -> None:
    response = _client(
        monkeypatch,
        _service(stt=FakeSTT(duration=-1)),
    ).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_audio_duration"


def test_non_numeric_model_returned_duration_fails_safe(monkeypatch) -> None:
    response = _client(
        monkeypatch,
        _service(stt=FakeSTT(duration="301")),
    ).post(
        "/api/study/plans/study_plan:one/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_audio_duration"


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
        async def atranscribe(self, *, audio_file: Path | str):
            self.paths.append(Path(audio_file))
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


@pytest.mark.asyncio
async def test_default_credential_metadata_loader_projects_endpoint_without_secrets(monkeypatch) -> None:
    query = AsyncMock(
        return_value=[
            {
                "id": "credential:local",
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434",
            }
        ]
    )
    monkeypatch.setattr(voice_service_module, "repo_query", query)

    metadata = await voice_service_module._load_credential_metadata("credential:local")

    assert metadata["provider"] == "ollama"
    assert metadata["base_url"] == "http://127.0.0.1:11434"
    query.assert_awaited_once()
    statement = query.await_args.args[0]
    assert "SELECT id, provider, base_url, endpoint, endpoint_stt, endpoint_tts" in statement
    assert "api_key" not in statement
    assert "config" not in statement


@pytest.mark.asyncio
async def test_default_credential_metadata_loader_rejects_cross_table_link(monkeypatch) -> None:
    query = AsyncMock()
    monkeypatch.setattr(voice_service_module, "repo_query", query)

    metadata = await voice_service_module._load_credential_metadata("note:local")

    assert metadata is None
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_credential_metadata_loader_accepts_projected_mapping(monkeypatch) -> None:
    monkeypatch.setattr(
        voice_service_module,
        "repo_query",
        AsyncMock(return_value={"provider": "ollama", "base_url": "http://localhost:11434"}),
    )

    metadata = await voice_service_module._load_credential_metadata("credential:local")

    assert metadata == {"provider": "ollama", "base_url": "http://localhost:11434"}
