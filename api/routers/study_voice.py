"""Feature-gated, local-only Study voice endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api.schemas.study_assistants import (
    StudyVoiceCapabilityResponse,
    StudyVoiceTranscriptionResponse,
    SynthesizeStudyVoiceRequest,
)
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.voice_service import (
    StudyVoiceError,
    StudyVoiceNotFound,
    StudyVoiceResultError,
    StudyVoiceService,
    StudyVoiceTimeout,
    StudyVoiceUnavailable,
    StudyVoiceValidationError,
)


def _require_study_workbench() -> None:
    if not study_workbench_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found"
        )


def _service() -> StudyVoiceService:
    return StudyVoiceService()


router = APIRouter(
    prefix="/study/plans",
    tags=["study-voice"],
    dependencies=[Depends(_require_study_workbench)],
)


def _voice_error(exc: StudyVoiceError) -> HTTPException:
    if isinstance(exc, StudyVoiceNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found"
        )
    if isinstance(exc, StudyVoiceValidationError):
        if exc.reason == "audio_too_large":
            return HTTPException(
                status_code=413,
                detail={
                    "code": exc.reason,
                    "message": "Audio upload exceeds the local limit",
                },
            )
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.reason, "message": "Invalid Study voice request"},
        )
    if isinstance(exc, StudyVoiceResultError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.reason, "message": "Local speech output was invalid"},
        )
    if isinstance(exc, StudyVoiceTimeout):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.reason, "message": "Local speech did not complete"},
        )
    if isinstance(exc, StudyVoiceUnavailable):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "local_speech_unavailable",
                "message": "Local speech is unavailable",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "study_voice_unavailable",
            "message": "Study voice is unavailable",
        },
    )


@router.post(
    "/{plan_id}/voice:transcribe",
    response_model=StudyVoiceTranscriptionResponse,
)
async def transcribe_study_voice(
    plan_id: str,
    audio: UploadFile = File(...),
    duration_seconds: float | None = Form(default=None),
) -> StudyVoiceTranscriptionResponse:
    try:
        transcript = await _service().transcribe_upload(
            plan_id,
            audio,
            audio.content_type,
            duration_seconds=duration_seconds,
        )
    except StudyVoiceError as exc:
        raise _voice_error(exc) from None
    finally:
        await audio.close()
    return StudyVoiceTranscriptionResponse(transcript=transcript)


@router.get(
    "/{plan_id}/voice:capability",
    response_model=StudyVoiceCapabilityResponse,
)
async def study_voice_capability(plan_id: str) -> StudyVoiceCapabilityResponse:
    try:
        capability = await _service().capability(plan_id)
    except StudyVoiceError as exc:
        raise _voice_error(exc) from None
    return StudyVoiceCapabilityResponse(**capability)


@router.post("/{plan_id}/voice:synthesize")
async def synthesize_study_voice(
    plan_id: str,
    payload: SynthesizeStudyVoiceRequest,
) -> StreamingResponse:
    try:
        audio, content_type = await _service().synthesize_text(plan_id, payload.text)
    except StudyVoiceError as exc:
        raise _voice_error(exc) from None
    return StreamingResponse(iter((audio,)), media_type=content_type)


__all__ = ["router"]
