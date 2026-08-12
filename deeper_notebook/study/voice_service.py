"""Bounded, local-only speech assistance for an approved Study plan."""

from __future__ import annotations

import asyncio
import inspect
import math
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from loguru import logger

from deeper_notebook.ai.offline_gate import LOCAL_PROVIDERS

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 16 * 1024
MAX_TTS_INPUT_BYTES = 8 * 1024
MAX_TTS_BYTES = 10 * 1024 * 1024
MAX_AUDIO_DURATION_SECONDS = 5 * 60
MAX_MODEL_SECONDS = 120
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_ALLOWED_AUDIO_TYPES = frozenset(
    {
        "audio/aac",
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-flac",
        "audio/x-wav",
    }
)
_SAFE_AUDIO_TYPES = frozenset(
    {
        "audio/aac",
        "audio/flac",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-flac",
        "audio/x-wav",
    }
)
_MIME_SUFFIX = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-flac": ".flac",
    "audio/x-wav": ".wav",
}
_AUTHORIZED_PLAN_STATES = frozenset({"approved", "generating", "active", "completed"})


class StudyVoiceError(RuntimeError):
    """Base class for bounded, safe voice errors."""

    code = "study_voice_unavailable"

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or self.code
        super().__init__(self.reason)


class StudyVoiceNotFound(StudyVoiceError):
    code = "study_plan_not_found"


class StudyVoiceValidationError(StudyVoiceError):
    code = "invalid_voice_request"


class StudyVoiceUnavailable(StudyVoiceError):
    code = "local_speech_unavailable"


class StudyVoiceTimeout(StudyVoiceError):
    code = "voice_timeout"


class StudyVoiceResultError(StudyVoiceError):
    code = "invalid_voice_result"


def _value(item: object, name: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


async def _maybe_await(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


def _safe_model_provider(model: object) -> str:
    return str(_value(model, "provider", "")).strip().lower().replace("-", "_")


def _validate_plan_id(plan_id: str) -> str:
    if (
        not isinstance(plan_id, str)
        or not plan_id.startswith("study_plan:")
        or len(plan_id) > 512
        or not plan_id[11:].strip()
        or any(char in plan_id for char in "\r\n\x00")
    ):
        raise StudyVoiceValidationError("invalid_plan_id")
    return plan_id


def _validate_mime(content_type: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in _ALLOWED_AUDIO_TYPES:
        raise StudyVoiceValidationError("unsupported_audio_type")
    return mime


def _validate_duration(duration_seconds: float | None) -> None:
    if duration_seconds is None:
        return
    if isinstance(duration_seconds, bool):
        raise StudyVoiceValidationError("invalid_audio_duration")
    try:
        duration = float(duration_seconds)
    except (TypeError, ValueError):
        raise StudyVoiceValidationError("invalid_audio_duration") from None
    if not math.isfinite(duration) or duration < 0:
        raise StudyVoiceValidationError("invalid_audio_duration")
    if duration > MAX_AUDIO_DURATION_SECONDS:
        raise StudyVoiceValidationError("audio_duration_too_long")


def _bounded_utf8(value: object, *, limit: int, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudyVoiceValidationError(reason)
    if len(value.encode("utf-8")) > limit:
        raise StudyVoiceValidationError(reason)
    return value.strip()


def _call_arguments(call: Callable[..., object], *, path: Path | None = None, text: str | None = None) -> tuple[tuple[object, ...], dict[str, object]]:
    """Adapt the common Esperanto and small local test-model signatures."""
    try:
        parameters = inspect.signature(call).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    if path is not None:
        for name in ("audio_file", "file", "audio", "path"):
            if name in parameters or accepts_kwargs:
                return (), {name: path}
        return (path,), {}
    if text is not None:
        kwargs: dict[str, object] = {"text": text} if "text" in parameters or accepts_kwargs else {}
        if "voice" in parameters:
            kwargs["voice"] = "default"
        return (() if kwargs else (text,)), kwargs
    return (), {}


async def _invoke_transcriber(model: object, path: Path) -> object:
    call = getattr(model, "atranscribe", None) or getattr(model, "transcribe", None)
    if not callable(call):
        raise StudyVoiceUnavailable("local_speech_unavailable")
    args, kwargs = _call_arguments(call, path=path)
    return await _maybe_await(call(*args, **kwargs))


async def _invoke_synthesizer(model: object, text: str) -> object:
    call = getattr(model, "agenerate_speech", None) or getattr(model, "generate_speech", None)
    if not callable(call):
        raise StudyVoiceUnavailable("local_speech_unavailable")
    args, kwargs = _call_arguments(call, text=text)
    return await _maybe_await(call(*args, **kwargs))


def _result_text(result: object) -> str:
    value = _value(result, "text", result)
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StudyVoiceResultError("invalid_transcription") from exc
    if not isinstance(value, str) or not value.strip():
        raise StudyVoiceResultError("empty_transcription")
    if len(value.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
        raise StudyVoiceResultError("transcript_too_large")
    return value.strip()


def _result_audio(result: object) -> tuple[bytes, str]:
    raw = _value(result, "audio_data", result)
    if isinstance(raw, Mapping):
        raw = raw.get("audio_data", raw.get("data", raw.get("content")))
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    elif isinstance(raw, bytearray):
        raw = bytes(raw)
    if not isinstance(raw, bytes) or not raw:
        raise StudyVoiceResultError("empty_audio_output")
    if len(raw) > MAX_TTS_BYTES:
        raise StudyVoiceResultError("audio_output_too_large")
    content_type = str(_value(result, "content_type", "audio/wav")).split(";", 1)[0].strip().lower()
    if content_type not in _SAFE_AUDIO_TYPES:
        raise StudyVoiceResultError("unsafe_audio_type")
    return raw, content_type


class StudyVoiceService:
    """Run speech work only after persisted Study authority and local routing checks."""

    def __init__(
        self,
        *,
        plan_repository: object | None = None,
        speech_to_text_getter: Callable[[], Awaitable[object | None]] | None = None,
        text_to_speech_getter: Callable[[], Awaitable[object | None]] | None = None,
        defaults_getter: Callable[[], Awaitable[object]] | None = None,
        model_getter: Callable[[str], Awaitable[object | None]] | None = None,
        max_upload_bytes: int | None = None,
        max_tts_bytes: int | None = None,
    ) -> None:
        if plan_repository is None:
            from .plan_repository import StudyPlanRepository

            plan_repository = StudyPlanRepository()
        if speech_to_text_getter is None or text_to_speech_getter is None or defaults_getter is None or model_getter is None:
            from deeper_notebook.ai.models import Model, model_manager

            speech_to_text_getter = speech_to_text_getter or model_manager.get_speech_to_text
            text_to_speech_getter = text_to_speech_getter or model_manager.get_text_to_speech
            defaults_getter = defaults_getter or model_manager.get_defaults
            model_getter = model_getter or Model.get
        self.plan_repository = plan_repository
        self._speech_to_text_getter = speech_to_text_getter
        self._text_to_speech_getter = text_to_speech_getter
        self._defaults_getter = defaults_getter
        self._model_getter = model_getter
        self.max_upload_bytes = max_upload_bytes if max_upload_bytes is not None else MAX_UPLOAD_BYTES
        self.max_tts_bytes = max_tts_bytes if max_tts_bytes is not None else MAX_TTS_BYTES

    async def _authorized_plan(self, plan_id: str) -> None:
        _validate_plan_id(plan_id)
        try:
            plan = await _maybe_await(self.plan_repository.get(plan_id))
            if plan is None or _value(plan, "state") not in _AUTHORIZED_PLAN_STATES or _value(plan, "approved_syllabus_version") is None:
                raise StudyVoiceNotFound("approved_plan_not_found")
            syllabus = await _maybe_await(
                self.plan_repository.get_syllabus(
                    plan_id, version=_value(plan, "approved_syllabus_version")
                )
            )
            if syllabus is None or _value(syllabus, "approved_at") is None:
                raise StudyVoiceNotFound("approved_syllabus_not_found")
        except StudyVoiceError:
            raise
        except Exception as exc:
            raise StudyVoiceUnavailable("study_voice_unavailable") from exc

    async def _local_model(self, kind: str) -> object:
        try:
            defaults = await _maybe_await(self._defaults_getter())
            field = "default_speech_to_text_model" if kind == "speech_to_text" else "default_text_to_speech_model"
            model_id = _value(defaults, field)
            if not isinstance(model_id, str) or not model_id.strip():
                raise StudyVoiceUnavailable("local_speech_unavailable")
            record = await _maybe_await(self._model_getter(model_id))
            provider = _safe_model_provider(record)
            if record is None or _value(record, "type") != kind or provider not in LOCAL_PROVIDERS:
                raise StudyVoiceUnavailable("local_speech_unavailable")
            getter = self._speech_to_text_getter if kind == "speech_to_text" else self._text_to_speech_getter
            model = await _maybe_await(getter())
            model_provider = _value(model, "provider")
            if model is None or (
                model_provider is not None
                and str(model_provider).strip().lower().replace("-", "_") not in LOCAL_PROVIDERS
            ):
                raise StudyVoiceUnavailable("local_speech_unavailable")
            return model
        except StudyVoiceError:
            raise
        except Exception as exc:
            logger.warning("Local Study speech capability was unavailable")
            raise StudyVoiceUnavailable("local_speech_unavailable") from exc

    async def _write_upload(self, upload: object, mime: str) -> Path:
        size = _value(upload, "size")
        if isinstance(size, int) and size > self.max_upload_bytes:
            raise StudyVoiceValidationError("audio_too_large")
        handle = tempfile.NamedTemporaryFile(
            mode="wb", prefix="study-voice-", suffix=_MIME_SUFFIX[mime], delete=False
        )
        path = Path(handle.name)
        written = 0
        try:
            with handle:
                while True:
                    chunk = await _maybe_await(upload.read(_UPLOAD_CHUNK_BYTES))
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise StudyVoiceValidationError("invalid_audio_upload")
                    if written + len(chunk) > self.max_upload_bytes:
                        raise StudyVoiceValidationError("audio_too_large")
                    handle.write(chunk)
                    written += len(chunk)
            if written == 0:
                raise StudyVoiceValidationError("empty_audio_upload")
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def transcribe_upload(
        self,
        plan_id: str,
        upload: object,
        content_type: str | None,
        *,
        duration_seconds: float | None = None,
    ) -> str:
        await self._authorized_plan(plan_id)
        mime = _validate_mime(content_type)
        _validate_duration(duration_seconds)
        model = await self._local_model("speech_to_text")
        path = await self._write_upload(upload, mime)
        try:
            try:
                async with asyncio.timeout(MAX_MODEL_SECONDS):
                    result = await _invoke_transcriber(model, path)
            except TimeoutError as exc:
                raise StudyVoiceTimeout("voice_timeout") from exc
            except asyncio.CancelledError:
                raise
            except StudyVoiceError:
                raise
            except Exception as exc:
                raise StudyVoiceUnavailable("local_speech_unavailable") from exc
            return _result_text(result)
        finally:
            path.unlink(missing_ok=True)

    async def synthesize_text(self, plan_id: str, text: str) -> tuple[bytes, str]:
        await self._authorized_plan(plan_id)
        bounded_text = _bounded_utf8(text, limit=MAX_TTS_INPUT_BYTES, reason="voice_text_too_large")
        model = await self._local_model("text_to_speech")
        try:
            try:
                async with asyncio.timeout(MAX_MODEL_SECONDS):
                    result = await _invoke_synthesizer(model, bounded_text)
            except TimeoutError as exc:
                raise StudyVoiceTimeout("voice_timeout") from exc
            except asyncio.CancelledError:
                raise
            except StudyVoiceError:
                raise
            except Exception as exc:
                raise StudyVoiceUnavailable("local_speech_unavailable") from exc
            data, content_type = _result_audio(result)
            if len(data) > self.max_tts_bytes:
                raise StudyVoiceResultError("audio_output_too_large")
            return data, content_type
        except StudyVoiceResultError:
            raise


__all__ = [
    "MAX_AUDIO_DURATION_SECONDS",
    "MAX_TRANSCRIPT_BYTES",
    "MAX_TTS_BYTES",
    "MAX_TTS_INPUT_BYTES",
    "MAX_UPLOAD_BYTES",
    "StudyVoiceError",
    "StudyVoiceNotFound",
    "StudyVoiceResultError",
    "StudyVoiceService",
    "StudyVoiceTimeout",
    "StudyVoiceUnavailable",
    "StudyVoiceValidationError",
]
