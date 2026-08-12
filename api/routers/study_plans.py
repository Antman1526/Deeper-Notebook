"""Feature-gated, projection-only HTTP endpoints for Study Workbench plans."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.study_plans import (
    ApproveSyllabusRequest,
    CreateStudyPlanRequest,
    PatchStudyPlanRequest,
    RemoveSourceLinkRequest,
    RemoveSourceLinkResponse,
    SaveSyllabusRequest,
    SourceLinkRequest,
    StudyPlanResponse,
    StudyPlanSourceLinkResponse,
    StudySyllabusResponse,
)
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.plan_repository import (
    StudyPlanRepository,
    StudyPlanRepositoryError,
)

router = APIRouter(prefix="/study/plans", tags=["study-plans"])


def _repository() -> StudyPlanRepository:
    return StudyPlanRepository()


def _require_study_workbench() -> None:
    if not study_workbench_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found")


def _not_found(detail: str = "Study plan not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _repository_error(exc: StudyPlanRepositoryError) -> HTTPException:
    """Project only safe, action-relevant persistence failures to HTTP."""
    message = str(exc)
    if message in {"study plan not found", "invalid study plan ID"}:
        return _not_found()
    if message in {
        "study plan revision conflict",
        "study plan revision conflict or syllabus version not found",
        "study syllabus version already exists or is unavailable",
        "Study source link already exists or plan is unavailable",
    }:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Study plan changed")
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Study plans are unavailable")


async def _existing_plan(plan_id: str) -> StudyPlanResponse:
    try:
        plan = await _repository().get(plan_id)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if plan is None:
        raise _not_found()
    return StudyPlanResponse.from_plan(plan)


@router.post("", response_model=StudyPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_study_plan(payload: CreateStudyPlanRequest) -> StudyPlanResponse:
    _require_study_workbench()
    try:
        return StudyPlanResponse.from_plan(await _repository().create(payload.to_plan()))
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None


@router.get("", response_model=list[StudyPlanResponse])
async def list_study_plans(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> list[StudyPlanResponse]:
    _require_study_workbench()
    try:
        plans = await _repository().list(limit=limit, offset=offset)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return [StudyPlanResponse.from_plan(plan) for plan in plans]


@router.get("/{plan_id}", response_model=StudyPlanResponse)
async def get_study_plan(plan_id: str) -> StudyPlanResponse:
    _require_study_workbench()
    return await _existing_plan(plan_id)


@router.patch("/{plan_id}", response_model=StudyPlanResponse)
async def patch_study_plan(plan_id: str, payload: PatchStudyPlanRequest) -> StudyPlanResponse:
    _require_study_workbench()
    try:
        plan = await _repository().update(
            plan_id,
            payload.changes(),
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanResponse.from_plan(plan)


@router.post(
    "/{plan_id}/sources",
    response_model=StudyPlanSourceLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_study_plan_source(
    plan_id: str, payload: SourceLinkRequest
) -> StudyPlanSourceLinkResponse:
    _require_study_workbench()
    try:
        link = await _repository().add_source(
            plan_id,
            payload.source_id,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanSourceLinkResponse.from_link(link)


@router.delete("/{plan_id}/sources/{source_id}", response_model=RemoveSourceLinkResponse)
async def remove_study_plan_source(
    plan_id: str,
    source_id: str,
    payload: RemoveSourceLinkRequest,
) -> RemoveSourceLinkResponse:
    _require_study_workbench()
    try:
        removed = await _repository().remove_source(
            plan_id,
            source_id,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return RemoveSourceLinkResponse(removed=removed)


@router.get("/{plan_id}/syllabus", response_model=StudySyllabusResponse)
async def get_study_syllabus(
    plan_id: str,
    version: int | None = Query(default=None, ge=1),
) -> StudySyllabusResponse:
    _require_study_workbench()
    try:
        syllabus = await _repository().get_syllabus(plan_id, version=version)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if syllabus is None:
        raise _not_found("Study syllabus not found")
    return StudySyllabusResponse.from_syllabus(syllabus)


@router.put("/{plan_id}/syllabus", response_model=StudySyllabusResponse)
async def save_study_syllabus(
    plan_id: str,
    payload: SaveSyllabusRequest,
) -> StudySyllabusResponse:
    _require_study_workbench()
    try:
        syllabus = await _repository().save_syllabus(
            payload.to_syllabus(plan_id),
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudySyllabusResponse.from_syllabus(syllabus)


@router.post("/{plan_id}/syllabus:approve", response_model=StudyPlanResponse)
async def approve_study_syllabus(
    plan_id: str,
    payload: ApproveSyllabusRequest,
) -> StudyPlanResponse:
    _require_study_workbench()
    current = await _existing_plan(plan_id)
    if current.state != "editing":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Study plan cannot approve syllabus")
    try:
        plan = await _repository().approve_syllabus(
            plan_id,
            syllabus_version=payload.syllabus_version,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanResponse.from_plan(plan)
