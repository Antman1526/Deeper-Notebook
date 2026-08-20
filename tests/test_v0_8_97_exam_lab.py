"""v0.8.97 — ExamLab: snapshot, deterministic grading, and FSRS seeding.

Grading and card-building are pure functions, so they get direct unit
coverage. Persistence and router wiring follow the house pattern of
source-shape guards (the live-DB path is the integration suite's job).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deeper_notebook.study.exams import (
    ExamAttempt,
    StudyExamConflict,
    build_attempt,
    grade_attempt,
    missed_question_cards,
)

_ROOT = Path(__file__).resolve().parents[1]

_QUIZ_QUESTIONS = [
    {
        "prompt": "What color is the sky on a clear day?",
        "options": [{"id": "a", "text": "Blue"}, {"id": "b", "text": "Green"}],
        "correct_option_id": "a",
        "explanation": "Rayleigh scattering favors shorter wavelengths.",
        "citations": ["[S1]"],
    },
    {
        "prompt": "2 + 2 = ?",
        "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
        "correct_option_id": "b",
        "explanation": "",
        "citations": [],
    },
    {
        "prompt": "Water boils at sea level at…",
        "options": [
            {"id": "a", "text": "90°C"},
            {"id": "b", "text": "100°C"},
            {"id": "c", "text": "110°C"},
        ],
        "correct_option_id": "b",
        "explanation": "At 1 atm, 100°C.",
        "citations": ["[S2]"],
    },
]


def _attempt(**overrides) -> ExamAttempt:
    attempt = build_attempt(
        artifact_id="studio_artifact:quiz1",
        notebook_id="notebook:n1",
        title="Sample quiz",
        quiz_questions=_QUIZ_QUESTIONS,
        duration_sec=600,
        now=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )
    return attempt.model_copy(update={"id": "study_exam_attempt:t1", **overrides})


# --- snapshot -----------------------------------------------------------------


def test_build_attempt_snapshots_all_questions_with_deadline():
    attempt = _attempt()
    assert attempt.question_count == 3
    assert attempt.deadline - attempt.started_at == timedelta(seconds=600)
    assert [q.index for q in attempt.questions] == [0, 1, 2]
    # The snapshot carries the answer key and explanations for grading time.
    assert attempt.questions[0].correct_option_id == "a"
    assert attempt.questions[2].explanation == "At 1 atm, 100°C."


def test_build_attempt_rejects_an_empty_quiz():
    with pytest.raises(StudyExamConflict):
        build_attempt(
            artifact_id="studio_artifact:q",
            notebook_id="notebook:n",
            title="Empty",
            quiz_questions=[],
            duration_sec=600,
        )


# --- grading ------------------------------------------------------------------


def test_grading_is_deterministic_and_counts_unanswered_as_wrong():
    graded = grade_attempt(
        _attempt(),
        {"0": "a", "2": "a"},  # Q0 right, Q1 unanswered, Q2 wrong
        now=datetime(2026, 8, 17, 12, 5, tzinfo=UTC),
    )
    assert graded.correct_count == 1
    assert graded.score_percent == 33.3
    assert graded.late is False
    by_index = {r.index: r for r in graded.results or []}
    assert by_index[0].correct and by_index[0].answered
    assert not by_index[1].correct and not by_index[1].answered
    assert not by_index[2].correct and by_index[2].answered
    assert by_index[2].selected_option_id == "a"
    assert by_index[2].correct_option_id == "b"


def test_unknown_option_id_grades_as_unanswered_not_an_error():
    """A malformed client must not be able to make an attempt ungradable."""
    graded = grade_attempt(_attempt(), {"0": "zzz"})
    by_index = {r.index: r for r in graded.results or []}
    assert not by_index[0].correct
    assert not by_index[0].answered
    assert by_index[0].selected_option_id is None


def test_late_submission_is_graded_and_flagged_not_rejected():
    graded = grade_attempt(
        _attempt(),
        {"0": "a", "1": "b", "2": "b"},
        now=datetime(2026, 8, 17, 13, 0, tzinfo=UTC),  # 50 min past a 10-min exam
    )
    assert graded.late is True
    assert graded.score_percent == 100.0


def test_double_submission_conflicts():
    graded = grade_attempt(_attempt(), {})
    with pytest.raises(StudyExamConflict):
        grade_attempt(graded, {"0": "a"})


# --- FSRS seeding -------------------------------------------------------------


def test_missed_question_cards_cover_only_unseeded_misses():
    graded = grade_attempt(_attempt(), {"0": "a", "2": "a"})  # misses: 1, 2
    graded = graded.model_copy(update={"seeded_indices": [1]})
    pairs = missed_question_cards(graded)
    assert [index for index, _ in pairs] == [2]
    card = pairs[0][1]
    assert card.front == "Water boils at sea level at…"
    assert card.back.startswith("100°C")
    assert "At 1 atm" in card.back
    # Anki-import evidence precedent: self-referential span over the snapshot.
    assert card.citations[0].source_id == "exam_attempt:study_exam_attempt:t1"
    assert card.citations[0].quote.startswith("Water boils")


def test_seeding_an_unsubmitted_attempt_conflicts():
    with pytest.raises(StudyExamConflict):
        missed_question_cards(_attempt())


def test_perfect_score_seeds_nothing():
    graded = grade_attempt(_attempt(), {"0": "a", "1": "b", "2": "b"})
    assert missed_question_cards(graded) == []


# --- wiring guards ------------------------------------------------------------


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_router_registered_in_main():
    src = _src("api/main.py")
    assert (
        'app.include_router(study_exams.router, prefix="/api", tags=["study-exams"])'
        in src
    )


def test_taking_view_never_carries_the_answer_key():
    """While unsubmitted, the response builder must emit ExamTakingQuestion
    (no correct_option_id / explanation)."""
    from api.schemas.study_exams import ExamAttemptResponse

    response = ExamAttemptResponse.from_attempt(_attempt())
    assert response.results is None
    assert response.questions is not None
    dumped = response.model_dump()
    assert "correct_option_id" not in str(dumped["questions"])
    assert response.questions[0].options[0].text == "Blue"


def test_submitted_view_carries_full_results():
    from api.schemas.study_exams import ExamAttemptResponse

    graded = grade_attempt(_attempt(), {"0": "a"})
    response = ExamAttemptResponse.from_attempt(graded)
    assert response.questions is None
    assert response.results is not None
    assert response.results[0].correct_option_id == "a"
    assert response.results[0].explanation.startswith("Rayleigh")


def test_migration_48_defines_the_attempt_table_with_down():
    up = _src("deeper_notebook/database/migrations/48.surrealql")
    down = _src("deeper_notebook/database/migrations/48_down.surrealql")
    assert "DEFINE TABLE IF NOT EXISTS study_exam_attempt SCHEMAFULL" in up
    for field in (
        "questions",
        "duration_sec",
        "deadline",
        "seeded_indices",
        "score_percent",
    ):
        assert f"DEFINE FIELD IF NOT EXISTS {field} " in up, f"missing {field}"
    assert "REMOVE TABLE IF EXISTS study_exam_attempt;" in down
