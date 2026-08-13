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


def _invocation(**updates: object) -> StudyAssistantInvocation:
    values: dict[str, object] = {
        "plan_id": PLAN_ID,
        "role": "source_guide",
        "authority": "ask",
        "prompt": "Explain the selected source.",
        "created_at": NOW,
    }
    values.update(updates)
    return StudyAssistantInvocation(**values)


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


def test_invocation_idempotency_ignores_server_generated_created_at() -> None:
    later = NOW.replace(minute=NOW.minute + 1)
    assert assistant_repository._invocation_hash(
        _invocation(created_at=NOW), "request-one"
    ) == assistant_repository._invocation_hash(
        _invocation(created_at=later), "request-one"
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
                "idempotency_hash": assistant_repository._invocation_hash(
                    _invocation(), "request-one"
                ),
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
        "idempotency_hash": assistant_repository._handoff_hash(
            _handoff(), "handoff-one"
        ),
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
async def test_handoff_request_lookup_is_exact_projection_only(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    row = {
        "id": "study_assistant_handoff:one",
        "plan_id": PLAN_ID,
        "session_id": "study_assistant_session:one",
        "role": "source_guide",
        "request_id": "request-one:handoff",
        "observation": "Replay answer",
        "evidence": [],
        "proposed_action": None,
        "origin": "source_guide",
        "user_decision": "pending",
        "created_at": NOW,
        "idempotency_hash": "a" * 64,
        "provider_payload": {"secret": "must not project"},
    }

    async def query(sql, params):
        calls.append((sql, params))
        return [row]

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    result = await StudyAssistantRepository().get_handoff_by_request(
        PLAN_ID, "request-one:handoff"
    )
    assert result is not None
    assert result.observation == "Replay answer"
    assert "provider_payload" not in calls[0][0]
    assert calls[0][1]["request_id"] == "request-one:handoff"


@pytest.mark.asyncio
async def test_completion_persists_session_and_handoff_in_one_guarded_transaction(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    handoff = _handoff().model_copy(
        update={"request_id": "request-one:handoff"}
    )
    session_row = {
        "id": "study_assistant_session:one",
        "plan_id": PLAN_ID,
        "role": "source_guide",
        "authority": "ask",
        "status": "completed",
        "request_id": "request-one",
        "prompt_sha256": prompt_sha256("Explain the selected source."),
        "selected_source_ids": [],
        "response_id": "study_assistant_response:one",
        "revision": 3,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": NOW,
        "idempotency_hash": assistant_repository._invocation_hash(
            _invocation(), "request-one"
        ),
    }
    handoff_row = {
        "id": "study_assistant_handoff:one",
        **handoff.model_dump(mode="python", exclude={"handoff_id"}),
        "idempotency_hash": assistant_repository._handoff_hash(
            handoff, "request-one:handoff"
        ),
    }

    async def query(sql, params):
        calls.append((sql, params))
        if "BEGIN TRANSACTION" in sql:
            return None
        if "assistant_session" in params:
            return [session_row]
        if "assistant_handoff" in params:
            return [handoff_row]
        return []

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    session, stored_handoff = await StudyAssistantRepository().complete_session(
        "study_assistant_session:one",
        handoff,
        expected_revision=2,
        response_id="study_assistant_response:one",
        completed_at=NOW,
        authority_guard={
            "plan_revision": 3,
            "plan_state": "approved",
            "syllabus_version": 2,
            "source_ids": ("source:one",),
            "syllabus_approved_at": NOW,
            "source_manifest_sha256": "a" * 64,
            "model_route": "local",
            "network_allowed": False,
            "network_scope": (),
            "source_evidence": (),
        },
    )
    assert session.status == "completed"
    assert stored_handoff == assistant_repository._handoff_from(handoff_row)
    transaction, params = next(
        (sql, params) for sql, params in calls if "BEGIN TRANSACTION" in sql
    )
    assert "status = \"running\"" in transaction
    assert "revision = $expected_revision" in transaction
    assert "CREATE $assistant_handoff CONTENT $handoff_payload" in transaction
    assert "UPDATE $assistant_session MERGE $session_patch" in transaction
    assert "study_assistant_authority_guard_failed" in transaction
    assert "$study_plan" in transaction
    assert "$syllabus_approved_at" in transaction
    assert "time::floor(approved_at, 1us) = time::floor($syllabus_approved_at, 1us)" in transaction
    assert "crypto::sha256(full_text)" in transaction
    assert params["expected_revision"] == 2
    assert params["plan_revision"] == 3


@pytest.mark.parametrize("state", ["approved", "generating", "active", "completed"])
def test_completion_authority_guard_accepts_learning_lifecycle_states(state: str) -> None:
    assert state in assistant_repository._ASSISTANT_PLAN_STATES


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
        "idempotency_hash": assistant_repository._memory_hash(
            _memory(), expected_revision=1, request_id="memory-one"
        ),
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


@pytest.mark.asyncio
async def test_concurrent_mismatched_session_winner_is_a_typed_conflict(monkeypatch):
    """A uniqueness loser must not receive a winner's receipt."""
    loser = _invocation(role="concept_explainer")
    winner_row = {
        "id": "study_assistant_session:winner",
        "plan_id": PLAN_ID,
        "role": "source_guide",
        "authority": "ask",
        "status": "queued",
        "request_id": "same-request",
        "prompt_sha256": prompt_sha256(loser.prompt),
        "selected_source_ids": [],
        "created_at": NOW,
        "updated_at": NOW,
        "idempotency_hash": assistant_repository._invocation_hash(
            _invocation(), "same-request"
        ),
    }
    calls = {"initial": 0}

    async def query(sql, params):
        if sql.startswith("SELECT"):
            if calls["initial"] == 0:
                calls["initial"] += 1
                return []
            return [winner_row]
        raise RuntimeError("unique request winner")

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    with pytest.raises(StudyAssistantConflictError):
        await StudyAssistantRepository().create_session(loser, request_id="same-request")


@pytest.mark.asyncio
async def test_concurrent_mismatched_handoff_winner_is_a_typed_conflict(monkeypatch):
    handoff = _handoff()
    winner_row = {
        "id": "study_assistant_handoff:winner",
        "plan_id": PLAN_ID,
        "session_id": "study_assistant_session:one",
        "role": "source_guide",
        "request_id": "same-handoff",
        "observation": "Different observation won concurrently.",
        "evidence": [],
        "proposed_action": "Ask one question.",
        "origin": "source_guide",
        "user_decision": "pending",
        "created_at": NOW,
        "idempotency_hash": assistant_repository._handoff_hash(
            _handoff().model_copy(update={"observation": "Different observation won concurrently."}),
            "same-handoff",
        ),
    }
    calls = {"initial": 0}

    async def query(sql, params):
        if sql.startswith("SELECT"):
            if calls["initial"] == 0:
                calls["initial"] += 1
                return []
            return [winner_row]
        raise RuntimeError("unique request winner")

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    with pytest.raises(StudyAssistantConflictError):
        await StudyAssistantRepository().append_handoff(handoff, request_id="same-handoff")


@pytest.mark.asyncio
async def test_concurrent_mismatched_memory_winner_is_a_typed_conflict(monkeypatch):
    memory = _memory()
    winner_row = {
        "id": "study_plan_memory:winner",
        "plan_id": PLAN_ID,
        "memory_key": memory.memory_key,
        "value": "Different value won concurrently.",
        "provenance": "user_confirmed",
        "status": "confirmed",
        "confirmation_required": False,
        "confirmed_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "revision": 1,
        "idempotency_hash": assistant_repository._memory_hash(
            _memory().model_copy(update={"value": "Different value won concurrently."}),
            expected_revision=0,
            request_id="same-memory",
        ),
    }
    calls = {"initial": 0}

    async def query(sql, params):
        if sql.startswith("SELECT"):
            if calls["initial"] == 0:
                calls["initial"] += 1
                return []
            return [winner_row]
        raise RuntimeError("unique memory winner")

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    with pytest.raises(StudyAssistantConflictError):
        await StudyAssistantRepository().upsert_memory(
            memory, expected_revision=0, request_id="same-memory"
        )


@pytest.mark.asyncio
async def test_memory_and_progress_pages_cap_before_projection_materialization(monkeypatch):
    memory_row = {
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
    }
    progress_row = {
        "id": "study_progress:one",
        "plan_id": PLAN_ID,
        "request_id": "progress-one",
        "event": "started",
        "details": "Session started",
        "created_at": NOW,
    }
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(sql, params):
        calls.append((sql, params))
        if "study_plan_memory" in sql:
            return [dict(memory_row, memory_key=f"preference.answer_style.{i}") for i in range(500)]
        return [dict(progress_row, request_id=f"progress-{i}") for i in range(500)]

    monkeypatch.setattr(assistant_repository, "repo_query", query)
    repository = StudyAssistantRepository()
    memories = await repository.list_memory(PLAN_ID, limit=10**100)
    progress = await repository.list_progress(PLAN_ID, limit=10**100)
    assert len(memories) <= 50
    assert len(progress) <= 50
    assert [params["limit"] for _sql, params in calls] == [50, 50]


def test_page_size_rejects_infinite_input() -> None:
    with pytest.raises(StudyAssistantRepositoryError):
        assistant_repository._page(float("inf"), 0)


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
    assert migration.count("idempotency_hash") >= 3
    assert 'provenance != "assistant_inference"' in migration
    assert 'value = "inferred"' in migration
