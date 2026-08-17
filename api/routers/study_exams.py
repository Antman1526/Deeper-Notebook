"""v0.8.97 — ExamLab endpoints: timed exam attempts over quiz artifacts."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.study_exams import (
    ExamAttemptResponse,
    ExamAttemptSummaryResponse,
    SeedMissesResponse,
    StartExamRequest,
    SubmitExamRequest,
)
from deeper_notebook.domain.notebook import StudioArtifact
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.studio.payloads import parse_payload_document
from deeper_notebook.study.exams import (
    StudyExamConflict,
    StudyExamError,
    StudyExamNotFound,
    StudyExamRepository,
    build_attempt,
    grade_attempt,
    missed_question_cards,
)
from deeper_notebook.study.repository import StudyRepository, StudyRepositoryError

router = APIRouter(prefix="/study/exams", tags=["study-exams"])


def _repository() -> StudyExamRepository:
    return StudyExamRepository()


@router.post(
    "/attempts",
    response_model=ExamAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_exam_attempt(payload: StartExamRequest) -> ExamAttemptResponse:
    try:
        artifact = await StudioArtifact.get(payload.artifact_id)
    except (NotFoundError, InvalidInputError):
        raise HTTPException(status_code=404, detail="Quiz artifact not found") from None
    if artifact.artifact_type != "quiz":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ExamLab attempts require a quiz artifact",
        )
    try:
        document = parse_payload_document("quiz", artifact.output_payload)
    except InvalidInputError:
        document = None
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This quiz predates structured documents and cannot be graded. "
                "Regenerate it in Evidence Studio first."
            ),
        )
    try:
        attempt = build_attempt(
            artifact_id=payload.artifact_id,
            notebook_id=str(artifact.notebook_id),
            title=artifact.title,
            quiz_questions=[q.model_dump() for q in document.questions],
            duration_sec=payload.duration_sec,
        )
        created = await _repository().create(attempt)
    except StudyExamConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except StudyExamError:
        raise HTTPException(status_code=503, detail="ExamLab is unavailable") from None
    return ExamAttemptResponse.from_attempt(created)


@router.get("/attempts", response_model=list[ExamAttemptSummaryResponse])
async def list_exam_attempts(
    notebook_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ExamAttemptSummaryResponse]:
    try:
        attempts = await _repository().list_recent(notebook_id=notebook_id, limit=limit)
    except StudyExamError:
        raise HTTPException(status_code=503, detail="ExamLab is unavailable") from None
    return [ExamAttemptSummaryResponse.from_attempt(a) for a in attempts]


@router.get("/attempts/{attempt_id}", response_model=ExamAttemptResponse)
async def get_exam_attempt(attempt_id: str) -> ExamAttemptResponse:
    try:
        attempt = await _repository().get(attempt_id)
    except StudyExamNotFound:
        raise HTTPException(status_code=404, detail="Exam attempt not found") from None
    except StudyExamError:
        raise HTTPException(status_code=503, detail="ExamLab is unavailable") from None
    return ExamAttemptResponse.from_attempt(attempt)


@router.post("/attempts/{attempt_id}/submit", response_model=ExamAttemptResponse)
async def submit_exam_attempt(
    attempt_id: str, payload: SubmitExamRequest
) -> ExamAttemptResponse:
    repository = _repository()
    try:
        attempt = await repository.get(attempt_id)
        graded = grade_attempt(attempt, payload.answers)
        saved = await repository.save_submission(graded)
    except StudyExamNotFound:
        raise HTTPException(status_code=404, detail="Exam attempt not found") from None
    except StudyExamConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except StudyExamError:
        raise HTTPException(status_code=503, detail="ExamLab is unavailable") from None
    return ExamAttemptResponse.from_attempt(saved)


@router.post("/attempts/{attempt_id}/seed-misses", response_model=SeedMissesResponse)
async def seed_missed_questions(attempt_id: str) -> SeedMissesResponse:
    """Push not-yet-seeded missed questions into the FSRS review deck."""
    exam_repository = _repository()
    try:
        attempt = await exam_repository.get(attempt_id)
        pairs = missed_question_cards(attempt)
    except StudyExamNotFound:
        raise HTTPException(status_code=404, detail="Exam attempt not found") from None
    except StudyExamConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    already = len(attempt.seeded_indices)
    if not pairs:
        return SeedMissesResponse(
            created=0, already_seeded=already, seeded_indices=list(attempt.seeded_indices)
        )
    study_repository = StudyRepository()
    seeded: list[int] = []
    try:
        for index, card in pairs:
            await study_repository.create_card_version(card)
            seeded.append(index)
        await exam_repository.mark_seeded(str(attempt.id), seeded)
    except (StudyRepositoryError, StudyExamError):
        if seeded:
            # Cards that DID land stay usable; record them so a retry can't
            # duplicate. Best-effort — a failure here surfaces as 503 anyway.
            try:
                await exam_repository.mark_seeded(str(attempt.id), seeded)
            except StudyExamError:
                pass
        raise HTTPException(
            status_code=503, detail="Review deck is unavailable"
        ) from None
    return SeedMissesResponse(
        created=len(seeded),
        already_seeded=already,
        seeded_indices=sorted(set(attempt.seeded_indices) | set(seeded)),
    )
