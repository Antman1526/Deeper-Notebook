"""Feature-gated, projection-only HTTP endpoints for Study Workbench plans."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

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
    StudySourceReadinessResponse,
    StudySyllabusResponse,
)
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.plan_repository import (
    StudyPlanConflictError,
    StudyPlanNotFoundError,
    StudyPlanRepository,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.plans import StudyPlan
from deeper_notebook.study.source_service import (
    StudySourceNotFoundError,
    StudySourceService,
    StudySourceUnavailableError,
)


def _repository() -> StudyPlanRepository:
    return StudyPlanRepository()


def _require_study_workbench() -> None:
    if not study_workbench_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found")


router = APIRouter(
    prefix="/study/plans",
    tags=["study-plans"],
    dependencies=[Depends(_require_study_workbench)],
)


def _not_found(detail: str = "Study plan not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _repository_error(exc: StudyPlanRepositoryError) -> HTTPException:
    """Project only safe, action-relevant persistence failures to HTTP."""
    if isinstance(exc, StudyPlanNotFoundError):
        return _not_found()
    if isinstance(exc, StudyPlanConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Study plan changed")
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Study plans are unavailable")


async def _existing_plan(plan_id: str) -> StudyPlanResponse:
    plan = await _load_plan(plan_id)
    return StudyPlanResponse.from_plan(plan)


async def _load_plan(plan_id: str) -> StudyPlan:
    try:
        plan = await _repository().get(plan_id)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if plan is None:
        raise _not_found()
    return plan


def _source_error(exc: StudySourceNotFoundError | StudySourceUnavailableError) -> HTTPException:
    if isinstance(exc, StudySourceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Sources are unavailable",
    )


@router.post("", response_model=StudyPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_study_plan(payload: CreateStudyPlanRequest) -> StudyPlanResponse:
    try:
        return StudyPlanResponse.from_plan(await _repository().create(payload.to_plan()))
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None


@router.get("", response_model=list[StudyPlanResponse])
async def list_study_plans(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> list[StudyPlanResponse]:
    try:
        plans = await _repository().list(limit=limit, offset=offset)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return [StudyPlanResponse.from_plan(plan) for plan in plans]


@router.get("/{plan_id}", response_model=StudyPlanResponse)
async def get_study_plan(plan_id: str) -> StudyPlanResponse:
    return await _existing_plan(plan_id)


@router.patch("/{plan_id}", response_model=StudyPlanResponse)
async def patch_study_plan(plan_id: str, payload: PatchStudyPlanRequest) -> StudyPlanResponse:
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
    repository = _repository()
    try:
        current = await repository.get(plan_id)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if current is None:
        raise _not_found()
    source_id = payload.source_id.strip()
    if source_id in {link.source_id.strip() for link in current.source_links}:
        # A retry of an already-persisted link is idempotent even when the
        # caller retained a stale revision.  Do this before source authority
        # access or revision checks so retries remain mutation-free.
        return StudyPlanSourceLinkResponse(source_id=source_id)

    if current.version != payload.expected_revision:
        raise _repository_error(StudyPlanConflictError("study plan revision conflict"))

    try:
        await StudySourceService().validate_source(source_id)
    except (StudySourceNotFoundError, StudySourceUnavailableError) as exc:
        raise _source_error(exc) from None

    try:
        link = await repository.add_source(
            plan_id,
            source_id,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanSourceLinkResponse.from_link(link)


@router.get(
    "/{plan_id}/sources/readiness",
    response_model=StudySourceReadinessResponse,
)
async def get_study_plan_source_readiness(plan_id: str) -> StudySourceReadinessResponse:
    plan = await _load_plan(plan_id)
    readiness = await StudySourceService().readiness(plan)
    return StudySourceReadinessResponse.from_readiness(readiness)


@router.delete("/{plan_id}/sources/{source_id}", response_model=RemoveSourceLinkResponse)
async def remove_study_plan_source(
    plan_id: str,
    source_id: str,
    payload: RemoveSourceLinkRequest,
) -> RemoveSourceLinkResponse:
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
