"""Projection and optimistic persistence tests for Study assistant records."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deeper_notebook.study import assistant_repository
from deeper_notebook.study.assistant_repository import (
    StudyAssistantConflictError,
    StudyAssistantNotFoundError,
    StudyAssistantRepository,
    StudyAssistantRepositoryError,
)
from deeper_notebook.study.assistants import (
    StudyAssistantHandoff,
    StudyAssistantInvocation,
    StudyPlanMemory,
    prompt_sha256,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
PLAN_ID = "study_plan:one"


def _invocation() -> StudyAssistantInvocation:
    return StudyAssistantInvocation(
        plan_id=PLAN_ID,
        role="source_guide",
        authority="ask",
        prompt="Explain the selected source.",
        created_at=NOW,
    )


def _handoff() -> StudyAssistantHandoff:
    return StudyAssistantHandoff(
        plan_id=PLAN_ID,
        session_id="study_assistant_session:one",
        role="source_guide",
        observation="The learner needs a smaller example.",
        evidence=({"source_id": "source:one", "locator": "page:1"},),
        proposed_action="Ask one question.",
        origin="source_guide",
        user_decision="pending",
        created_at=NOW,
    )


def _memory() -> StudyPlanMemory:
    return StudyPlanMemory(
        plan_id=PLAN_ID,
        memory_key="preference.answer_style",
        value="Prefer concise examples",
        provenance="user_confirmed",
        status="confirmed",
        confirmation_required=False,
        confirmed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_create_session_uses_parameterized_record_id_and_projects_safe_fields(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        return [
            {
                "id": "study_assistant_session:one",
                "plan_id": PLAN_ID,
                "role": "source_guide",
                "authority": "ask",
                "status": "completed",
                "request_id": "request-one",
                "prompt_sha256": prompt_sha256("Explain the selected source."),
                "selected_source_ids": [],
                "created_at": NOW,
                "updated_at": NOW,
                "provider_payload": {"secret": "must not project"},
                "chain_of_thought": "must not project",
            }
        ]

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    result = await StudyAssistantRepository().create_session(_invocation(), request_id="request-one")
    assert result.session_id == "study_assistant_session:one"
    assert result.role == "source_guide"
    assert not hasattr(result, "provider_payload")
    assert "$plan_id" in calls[0][0]
    assert calls[0][1]["plan_id"] == PLAN_ID


@pytest.mark.asyncio
async def test_handoff_append_is_idempotent_and_page_is_capped(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    row = {
        "id": "study_assistant_handoff:one",
        "plan_id": PLAN_ID,
        "session_id": "study_assistant_session:one",
        "role": "source_guide",
        "observation": "The learner needs a smaller example.",
        "evidence": [{"source_id": "source:one", "locator": "page:1"}],
        "proposed_action": "Ask one question.",
        "origin": "source_guide",
        "user_decision": "pending",
        "created_at": NOW,
    }

    async def query(sql, params):
        calls.append((sql, params))
        return [row]

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    repository = StudyAssistantRepository()
    first = await repository.append_handoff(_handoff(), request_id="handoff-one")
    retry = await repository.append_handoff(_handoff(), request_id="handoff-one")
    page = await repository.list_handoffs(PLAN_ID, limit=10_000)
    assert first == retry
    assert page == (first,)
    assert any(params.get("limit") == 50 for _sql, params in calls)
    assert all("provider_payload" not in sql for sql, _params in calls)


@pytest.mark.asyncio
async def test_memory_upsert_requires_expected_revision_and_is_idempotent(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    row = {
        "id": "study_plan_memory:one",
        "plan_id": PLAN_ID,
        "memory_key": "preference.answer_style",
        "value": "Prefer concise examples",
        "provenance": "user_confirmed",
        "status": "confirmed",
        "confirmation_required": False,
        "confirmed_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "revision": 1,
        "raw_provider_payload": {"secret": "must not project"},
    }

    async def query(sql, params):
        calls.append((sql, params))
        if sql.startswith("SELECT"):
            return [row]
        return [{**row, "revision": 2}]

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    result = await StudyAssistantRepository().upsert_memory(
        _memory(), expected_revision=1, request_id="memory-one"
    )
    assert result.memory_key == "preference.answer_style"
    assert result.revision == 2
    assert not hasattr(result, "raw_provider_payload")
    assert any("revision = $expected_revision" in sql for sql, _params in calls)
    assert any(params.get("expected_revision") == 1 for _sql, params in calls)
    update_calls = [(sql, params) for sql, params in calls if sql.startswith("UPDATE")]
    assert len(update_calls) == 1
    update_sql, update_params = update_calls[0]
    assert "MERGE $payload" in update_sql
    assert " SET " not in update_sql
    assert update_params["payload"]["revision"] == 2


def test_migration_uses_bounded_assertions_and_down_is_symmetric() -> None:
    root = assistant_repository.__file__
    assert root is not None
    migration = assistant_repository.MIGRATION_PATH.read_text()
    down = assistant_repository.MIGRATION_DOWN_PATH.read_text()
    for table in (
        "study_assistant_session",
        "study_assistant_handoff",
        "study_plan_memory",
        "study_progress",
    ):
        assert f"DEFINE TABLE IF NOT EXISTS {table}" in migration
        assert f"REMOVE TABLE IF EXISTS {table}" in down
    assert "array::every" in migration
    assert "string::trim" in migration
