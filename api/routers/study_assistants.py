"""Feature-gated API for one bounded foreground Study assistant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from api.schemas.study_assistants import (
    InvokeStudyAssistantRequest,
    StudyAssistantResponseBody,
)
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.assistant_service import (
    StudyAssistantCancelled,
    StudyAssistantError,
    StudyAssistantMalformedOutput,
    StudyAssistantNotFound,
    StudyAssistantPolicyError,
    StudyAssistantService,
    StudyAssistantTimeout,
    StudyAssistantUnavailable,
)
from deeper_notebook.study.assistants import StudyAssistantRole


def _require_study_workbench() -> None:
    if not study_workbench_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found"
        )


def _service() -> StudyAssistantService:
    return StudyAssistantService()


router = APIRouter(
    prefix="/study/plans",
    tags=["study-assistants"],
    dependencies=[Depends(_require_study_workbench)],
)


def _assistant_error(exc: StudyAssistantError) -> HTTPException:
    if isinstance(exc, StudyAssistantNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found"
        )
    if isinstance(exc, StudyAssistantPolicyError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.reason,
                "message": "Study assistant action is not allowed",
            },
        )
    if isinstance(exc, StudyAssistantMalformedOutput):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.reason,
                "message": "Study assistant response is invalid",
            },
        )
    if isinstance(exc, (StudyAssistantTimeout, StudyAssistantCancelled)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.reason,
                "message": "Study assistant invocation did not complete",
            },
        )
    if isinstance(exc, StudyAssistantUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.reason, "message": "Study assistants are unavailable"},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "assistant_unavailable",
            "message": "Study assistants are unavailable",
        },
    )


@router.post(
    "/{plan_id}/assistants/{role}:invoke",
    response_model=StudyAssistantResponseBody,
)
async def invoke_study_assistant(
    plan_id: str,
    role: StudyAssistantRole,
    payload: InvokeStudyAssistantRequest,
) -> StudyAssistantResponseBody:
    try:
        invocation = payload.to_invocation(plan_id, role)
    except (ValidationError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_assistant_request",
                "message": "Study assistant request is invalid",
            },
        ) from None
    try:
        response = await _service().invoke(plan_id, role, invocation)
    except StudyAssistantError as exc:
        raise _assistant_error(exc) from None
    return StudyAssistantResponseBody.model_validate(response.model_dump(mode="python"))


__all__ = ["router"]
