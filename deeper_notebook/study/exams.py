"""v0.8.97 — ExamLab: timed exam attempts over Evidence Studio quiz artifacts.

Idea adopted from PageLM's ExamLab; implementation original (their license does
not permit code reuse).

Design invariants:

- **Snapshot at start.** An attempt copies its questions out of the quiz
  artifact when it begins, so regenerating or editing the artifact mid-attempt
  can never change what gets graded.
- **Deterministic after start.** Grading compares submitted option ids against
  the snapshotted ``correct_option_id`` — no model call, no network, instant,
  and identical offline. Explanations were generated when the quiz artifact
  was created and ride along in the snapshot.
- **Late is a fact, not a wall.** A submission after the deadline is graded
  normally and marked ``late=True``. Rejecting it would punish a single-user
  desktop app's owner for their own timer.
- **Idempotent seeding.** Missed questions can be pushed into the FSRS review
  deck once each; ``seeded_indices`` records which already were, so clicking
  the button twice cannot duplicate cards. Cards use the Anki-import precedent
  for evidence: a self-referential span over the card's own snapshot, because
  quiz citations are ``[S1]``-style markers, not offset spans.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.evaluation.schemas import EvidenceSpan, hash_source_text
from deeper_notebook.study.contracts import StudyCard

MAX_EXAM_QUESTIONS = 200
MIN_DURATION_SEC = 60
MAX_DURATION_SEC = 14_400  # 4 hours


class StudyExamError(RuntimeError):
    """Safe, typed exam failure suitable for the API boundary."""


class StudyExamNotFound(StudyExamError):
    pass


class StudyExamConflict(StudyExamError):
    pass


class ExamOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=2_000)


class ExamQuestion(BaseModel):
    """One snapshotted question. ``correct_option_id`` never leaves the server
    until the attempt is submitted — the API layer strips it."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    prompt: str = Field(min_length=1, max_length=8_000)
    options: list[ExamOption] = Field(min_length=2, max_length=12)
    correct_option_id: str = Field(min_length=1, max_length=64)
    explanation: str = Field(default="", max_length=8_000)
    citations: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def correct_must_be_an_option(self) -> "ExamQuestion":
        option_ids = {option.id for option in self.options}
        if len(option_ids) != len(self.options):
            raise ValueError("exam option ids must be unique")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must match an option id")
        return self


class ExamQuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    correct: bool
    answered: bool
    selected_option_id: str | None = None
    correct_option_id: str
    explanation: str = ""
    citations: list[str] = Field(default_factory=list)


class ExamAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    artifact_id: str
    notebook_id: str
    title: str
    questions: list[ExamQuestion] = Field(min_length=1, max_length=MAX_EXAM_QUESTIONS)
    question_count: int = Field(ge=1, le=MAX_EXAM_QUESTIONS)
    duration_sec: int = Field(ge=MIN_DURATION_SEC, le=MAX_DURATION_SEC)
    started_at: datetime
    deadline: datetime
    submitted_at: datetime | None = None
    late: bool | None = None
    answers: dict[str, str] | None = None
    results: list[ExamQuestionResult] | None = None
    correct_count: int | None = None
    score_percent: float | None = None
    seeded_indices: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def timezone_aware(self) -> "ExamAttempt":
        for name in ("started_at", "deadline", "submitted_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        return self


def build_attempt(
    *,
    artifact_id: str,
    notebook_id: str,
    title: str,
    quiz_questions: list[dict[str, Any]],
    duration_sec: int,
    now: datetime | None = None,
) -> ExamAttempt:
    """Snapshot a parsed QuizDocument's questions into a new attempt.

    ``quiz_questions`` is the ``model_dump()`` of ``QuizDocument.questions``.
    Raises StudyExamConflict when the quiz has no gradable questions.
    """
    started = now or datetime.now(UTC)
    snapshot: list[ExamQuestion] = []
    for index, raw in enumerate(quiz_questions[:MAX_EXAM_QUESTIONS]):
        options = [
            ExamOption(id=str(o.get("id", "")), text=str(o.get("text", "")))
            for o in raw.get("options", [])
        ]
        snapshot.append(
            ExamQuestion(
                index=index,
                prompt=str(raw.get("prompt", "")),
                options=options,
                correct_option_id=str(raw.get("correct_option_id", "")),
                explanation=str(raw.get("explanation", "") or ""),
                citations=[str(c) for c in raw.get("citations", [])],
            )
        )
    if not snapshot:
        raise StudyExamConflict("quiz artifact has no gradable questions")
    return ExamAttempt(
        artifact_id=artifact_id,
        notebook_id=notebook_id,
        title=title,
        questions=snapshot,
        question_count=len(snapshot),
        duration_sec=duration_sec,
        started_at=started,
        deadline=started + timedelta(seconds=duration_sec),
    )


def grade_attempt(
    attempt: ExamAttempt,
    answers: dict[str, str],
    *,
    now: datetime | None = None,
) -> ExamAttempt:
    """Pure, deterministic grading. Returns a new submitted attempt.

    Unanswered questions count as wrong (``answered=False``); unknown option
    ids count as wrong rather than raising — a malformed client must not be
    able to make an attempt ungradable.
    """
    if attempt.submitted_at is not None:
        raise StudyExamConflict("attempt is already submitted")
    submitted = now or datetime.now(UTC)
    results: list[ExamQuestionResult] = []
    correct_count = 0
    for question in attempt.questions:
        selected = answers.get(str(question.index))
        valid_ids = {option.id for option in question.options}
        answered = selected is not None and selected in valid_ids
        is_correct = answered and selected == question.correct_option_id
        if is_correct:
            correct_count += 1
        results.append(
            ExamQuestionResult(
                index=question.index,
                correct=is_correct,
                answered=answered,
                selected_option_id=selected if answered else None,
                correct_option_id=question.correct_option_id,
                explanation=question.explanation,
                citations=list(question.citations),
            )
        )
    graded = attempt.model_copy(
        update={
            "submitted_at": submitted,
            "late": submitted > attempt.deadline,
            "answers": {str(k): str(v) for k, v in answers.items()},
            "results": results,
            "correct_count": correct_count,
            "score_percent": round(100.0 * correct_count / attempt.question_count, 1),
        }
    )
    return graded


def missed_question_cards(attempt: ExamAttempt) -> list[tuple[int, StudyCard]]:
    """Build FSRS cards for missed questions not yet seeded.

    Evidence uses the Anki-import precedent (self-referential span over the
    card's own snapshot) because quiz citations are ``[S1]`` markers with no
    offsets. Returns ``(question_index, card)`` pairs so the caller can record
    ``seeded_indices`` atomically with the card writes.
    """
    if attempt.results is None or attempt.id is None:
        raise StudyExamConflict("attempt is not submitted")
    already = set(attempt.seeded_indices)
    by_index = {question.index: question for question in attempt.questions}
    pairs: list[tuple[int, StudyCard]] = []
    for result in attempt.results:
        if result.correct or result.index in already:
            continue
        question = by_index[result.index]
        correct_text = next(
            (o.text for o in question.options if o.id == question.correct_option_id),
            question.correct_option_id,
        )
        back = correct_text
        if question.explanation:
            back = f"{correct_text}\n\n{question.explanation}"
        snapshot = f"{question.prompt}\n{back}"[:1200]
        pairs.append(
            (
                result.index,
                StudyCard(
                    artifact_id=f"exam_attempt:{attempt.id}",
                    artifact_card_id=f"exam_question:{attempt.id}:{result.index}",
                    front=question.prompt,
                    back=back,
                    citations=[
                        EvidenceSpan(
                            source_id=f"exam_attempt:{attempt.id}",
                            source_content_sha256=hash_source_text(snapshot),
                            start=0,
                            end=len(snapshot),
                            quote=snapshot,
                        )
                    ],
                ),
            )
        )
    return pairs


class StudyExamRepository:
    """Persistence for exam attempts. Values are $-bound; ids via RecordID."""

    @staticmethod
    def _attempt_data(attempt: ExamAttempt) -> dict[str, Any]:
        # mode="python" keeps datetimes native for the driver — Surreal's
        # schema datetime fields reject ISO strings (StudyRepository._card_data
        # precedent).
        return attempt.model_dump(exclude={"id"}, mode="python")

    @staticmethod
    def _from_record(record: object) -> ExamAttempt:
        if not isinstance(record, dict):
            raise StudyExamError("invalid exam attempt record")
        data = dict(record)
        record_id = data.pop("id", None)
        data.pop("created", None)
        data.pop("updated", None)
        attempt = ExamAttempt.model_validate(data)
        return attempt.model_copy(update={"id": str(record_id) if record_id else None})

    async def create(self, attempt: ExamAttempt) -> ExamAttempt:
        token = hashlib.sha256(
            f"{attempt.artifact_id}|{attempt.started_at.isoformat()}".encode()
        ).hexdigest()[:20]
        record = RecordID("study_exam_attempt", f"exam_{token}")
        result = await repo_query(
            "CREATE $record CONTENT $data RETURN AFTER;",
            vars={"record": record, "data": self._attempt_data(attempt)},
        )
        rows = result if isinstance(result, list) else [result]
        if not rows:
            raise StudyExamError("exam attempt was not created")
        return self._from_record(rows[0])

    async def get(self, attempt_id: str) -> ExamAttempt:
        record = ensure_record_id(
            attempt_id
            if attempt_id.startswith("study_exam_attempt:")
            else f"study_exam_attempt:{attempt_id}"
        )
        result = await repo_query(
            "SELECT * FROM $record;", vars={"record": record}
        )
        rows = result if isinstance(result, list) else [result]
        if not rows or not rows[0]:
            raise StudyExamNotFound("exam attempt not found")
        return self._from_record(rows[0])

    async def save_submission(self, attempt: ExamAttempt) -> ExamAttempt:
        if attempt.id is None:
            raise StudyExamError("attempt has no id")
        record = ensure_record_id(attempt.id)
        result = await repo_query(
            "UPDATE $record MERGE $data RETURN AFTER;",
            vars={
                "record": record,
                "data": {
                    "submitted_at": attempt.submitted_at,
                    "late": attempt.late,
                    "answers": attempt.answers,
                    "results": [r.model_dump(mode="python") for r in attempt.results or []],
                    "correct_count": attempt.correct_count,
                    "score_percent": attempt.score_percent,
                },
            },
        )
        rows = result if isinstance(result, list) else [result]
        if not rows:
            raise StudyExamError("exam submission was not saved")
        return self._from_record(rows[0])

    async def mark_seeded(self, attempt_id: str, indices: list[int]) -> None:
        record = ensure_record_id(attempt_id)
        await repo_query(
            "UPDATE $record SET seeded_indices = array::distinct("
            "array::concat(seeded_indices, $indices)) RETURN NONE;",
            vars={"record": record, "indices": indices},
        )

    async def list_recent(
        self, *, notebook_id: str | None = None, limit: int = 20
    ) -> list[ExamAttempt]:
        bounded = max(1, min(int(limit), 100))
        vars: dict[str, Any] = {"limit": bounded}
        where = ""
        if notebook_id:
            where = "WHERE notebook_id = $notebook_id "
            vars["notebook_id"] = notebook_id
        # `where` is either "" or the literal three lines up — a local, not a
        # parameter — so this is safe by construction rather than by caller
        # discipline. That distinction is the whole point of
        # tests/test_v0_8_99_identifier_guards.py: the four sites that
        # interpolated a *function parameter* needed real guards, because a
        # comment asserting "callers only pass constants" is not a control.
        # Here there is no caller to trust. notebook_id and the [1,100]-clamped
        # limit both travel as $-bound vars.
        #
        # The B608 suppression below is bare on purpose. The house form
        # ("- constants/whitelisted identifiers; values bound"), which Bandit
        # parses as further test IDs and rejects one word at a time
        # ("Test in comment: constants is not a test name or id, ignoring").
        # Suppression still works, so the existing tags are noisy rather than
        # broken — but new ones need not add to it.
        result = await repo_query(
            "SELECT * FROM study_exam_attempt "  # nosec B608
            + where
            + "ORDER BY started_at DESC LIMIT $limit;",
            vars=vars,
        )
        rows = result if isinstance(result, list) else [result]
        return [self._from_record(row) for row in rows if row]
