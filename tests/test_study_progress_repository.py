"""RED contracts for Task 14's adapter over the Task 10 progress authority."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeper_notebook.study import assistant_repository
from deeper_notebook.study.assistant_repository import (
    StudyAssistantConflictError,
    StudyAssistantRepository,
)
from deeper_notebook.study.progress import (
    StudyProgressAssessment,
    make_progress_receipt,
)
from deeper_notebook.study.progress_repository import StudyProgressRepository

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PLAN_ID = "study_plan:one"


def _receipt(request_id: str = "assessment-one", score: float = 0.5):
    return make_progress_receipt(
        plan_id=PLAN_ID,
        request_id=request_id,
        event="assessed",
        created_at=NOW,
        assessment=StudyProgressAssessment(
            concept_id="concept:one",
            score=score,
            correct=score >= 0.5,
        ),
    )


@pytest.mark.asyncio
async def test_append_progress_concurrent_create_race_re_reads_matching_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    winner = _receipt()
    winner_row = {
        "id": "study_progress:winner",
        "plan_id": PLAN_ID,
        "request_id": winner.request_id,
        "event": winner.event,
        "unit_id": winner.unit_id,
        "details": winner.details,
        "created_at": NOW,
    }

    async def query(sql: str, params: dict[str, object]):
        calls.append(sql)
        if sql.startswith("SELECT"):
            return (
                []
                if len([item for item in calls if item.startswith("SELECT")]) == 1
                else [winner_row]
            )
        raise RuntimeError("unique request winner")

    monkeypatch.setattr(assistant_repository, "repo_query", query)

    result = await StudyAssistantRepository().append_progress(_receipt())

    assert result.request_id == winner.request_id
    assert result.details == winner.details
    assert len([sql for sql in calls if sql.startswith("SELECT")]) >= 2


@pytest.mark.asyncio
async def test_append_progress_concurrent_create_race_rejects_mismatched_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(score=0.5)
    winner = _receipt(score=0.9)
    winner_row = {
        "id": "study_progress:winner",
        "plan_id": PLAN_ID,
        "request_id": winner.request_id,
        "event": winner.event,
        "unit_id": winner.unit_id,
        "details": winner.details,
        "created_at": NOW,
    }

    calls: list[str] = []

    async def query(sql: str, params: dict[str, object]):
        calls.append(sql)
        if sql.startswith("SELECT"):
            return (
                []
                if len([item for item in calls if item.startswith("SELECT")]) == 1
                else [winner_row]
            )
        raise RuntimeError("unique request winner")

    monkeypatch.setattr(assistant_repository, "repo_query", query)

    with pytest.raises(StudyAssistantConflictError):
        await StudyAssistantRepository().append_progress(receipt)


@pytest.mark.asyncio
async def test_progress_repository_caps_pages_before_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, object]] = []

    class FakeAssistantRepository:
        async def list_progress(self, plan_id: str, *, limit: int, offset: int):
            seen.append({"limit": limit, "offset": offset})
            return (_receipt(),)

        async def append_progress(self, receipt):
            return receipt

    repository = StudyProgressRepository(assistant=FakeAssistantRepository())
    rows = await repository.list_progress(PLAN_ID, limit=10**100, offset=0)

    assert len(rows) == 1
    assert seen == [{"limit": 50, "offset": 0}]


def test_progress_repository_uses_task10_migration_authority() -> None:
    migration = assistant_repository.MIGRATION_PATH.read_text()
    assert "DEFINE TABLE IF NOT EXISTS study_progress" in migration
    assert "DEFINE TABLE IF NOT EXISTS study_mastery" not in migration
    assert (
        "REMOVE TABLE IF EXISTS study_progress"
        in assistant_repository.MIGRATION_DOWN_PATH.read_text()
    )
