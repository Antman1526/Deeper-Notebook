"""v0.8.97 — ExamLab API schemas.

The taking-view/result-view split is the load-bearing decision here: while an
attempt is in progress the response carries questions WITHOUT
``correct_option_id`` or explanations, so the answer key never reaches the
taking screen. After submission the same endpoint returns full results.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from deeper_notebook.study.exams import (
    MAX_DURATION_SEC,
    MIN_DURATION_SEC,
    ExamAttempt,
)


class StartExamRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=512)
    duration_sec: int = Field(ge=MIN_DURATION_SEC, le=MAX_DURATION_SEC)


class SubmitExamRequest(BaseModel):
    # {"<question index>": "<selected option id>"} — sparse; unanswered
    # questions are simply absent and grade as wrong.
    answers: dict[str, str] = Field(default_factory=dict)


class ExamOptionResponse(BaseModel):
    id: str
    text: str


class ExamTakingQuestion(BaseModel):
    """A question as shown while the clock runs — no answer key."""

    index: int
    prompt: str
    options: list[ExamOptionResponse]


class ExamQuestionResultResponse(BaseModel):
    index: int
    prompt: str
    options: list[ExamOptionResponse]
    correct: bool
    answered: bool
    selected_option_id: str | None
    correct_option_id: str
    explanation: str
    citations: list[str]


class ExamAttemptResponse(BaseModel):
    id: str
    artifact_id: str
    notebook_id: str
    title: str
    question_count: int
    duration_sec: int
    started_at: datetime
    deadline: datetime
    submitted_at: datetime | None
    late: bool | None
    correct_count: int | None
    score_percent: float | None
    seeded_indices: list[int]
    # Exactly one of these is populated, keyed on submission state.
    questions: list[ExamTakingQuestion] | None
    results: list[ExamQuestionResultResponse] | None

    @classmethod
    def from_attempt(cls, attempt: ExamAttempt) -> "ExamAttemptResponse":
        submitted = attempt.submitted_at is not None
        by_index = {question.index: question for question in attempt.questions}
        questions = None
        results = None
        if submitted and attempt.results is not None:
            results = [
                ExamQuestionResultResponse(
                    index=result.index,
                    prompt=by_index[result.index].prompt,
                    options=[
                        ExamOptionResponse(id=o.id, text=o.text)
                        for o in by_index[result.index].options
                    ],
                    correct=result.correct,
                    answered=result.answered,
                    selected_option_id=result.selected_option_id,
                    correct_option_id=result.correct_option_id,
                    explanation=result.explanation,
                    citations=result.citations,
                )
                for result in attempt.results
            ]
        else:
            questions = [
                ExamTakingQuestion(
                    index=question.index,
                    prompt=question.prompt,
                    options=[
                        ExamOptionResponse(id=o.id, text=o.text)
                        for o in question.options
                    ],
                )
                for question in attempt.questions
            ]
        return cls(
            id=attempt.id or "",
            artifact_id=attempt.artifact_id,
            notebook_id=attempt.notebook_id,
            title=attempt.title,
            question_count=attempt.question_count,
            duration_sec=attempt.duration_sec,
            started_at=attempt.started_at,
            deadline=attempt.deadline,
            submitted_at=attempt.submitted_at,
            late=attempt.late,
            correct_count=attempt.correct_count,
            score_percent=attempt.score_percent,
            seeded_indices=list(attempt.seeded_indices),
            questions=questions,
            results=results,
        )


class ExamAttemptSummaryResponse(BaseModel):
    """List row — no question payload at all."""

    id: str
    artifact_id: str
    notebook_id: str
    title: str
    question_count: int
    duration_sec: int
    started_at: datetime
    submitted_at: datetime | None
    late: bool | None
    correct_count: int | None
    score_percent: float | None

    @classmethod
    def from_attempt(cls, attempt: ExamAttempt) -> "ExamAttemptSummaryResponse":
        return cls(
            id=attempt.id or "",
            artifact_id=attempt.artifact_id,
            notebook_id=attempt.notebook_id,
            title=attempt.title,
            question_count=attempt.question_count,
            duration_sec=attempt.duration_sec,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
            late=attempt.late,
            correct_count=attempt.correct_count,
            score_percent=attempt.score_percent,
        )


class SeedMissesResponse(BaseModel):
    created: int
    already_seeded: int
    seeded_indices: list[int]
