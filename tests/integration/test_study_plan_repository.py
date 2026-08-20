"""Real-SurrealDB persistence contracts for Study Workbench plans."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import StudioArtifact
from deeper_notebook.study.artifact_service import (
    StudyArtifactConflict,
    StudyArtifactService,
    _artifact_identity,
)
from deeper_notebook.study.assistant_repository import (
    StudyAssistantAuthorityConflictError,
    StudyAssistantConflictError,
    StudyAssistantRepository,
)
from deeper_notebook.study.assistants import (
    StudyAssistantHandoff,
    StudyAssistantInvocation,
    StudyPlanMemory,
    StudyProgressReceipt,
)
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudySyllabus,
    StudySyllabusUnit,
)
from deeper_notebook.study.source_service import (
    StudySourceReadiness,
    StudySourceReadinessItem,
)
from deeper_notebook.study.syllabus_service import source_manifest

pytestmark = pytest.mark.integration_surreal


def _plan() -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:integration",
        goal="Verify persisted syllabus versions",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
        source_manifest_sha256="a" * 64,
    )


def _syllabus(version: int) -> StudySyllabus:
    return StudySyllabus(
        plan_id="study_plan:integration",
        version=version,
        source_manifest_sha256="a" * 64,
        units=[
            StudySyllabusUnit(
                unit_id=f"foundations-{version}",
                title=f"Foundations {version}",
                objectives=["Explain the core idea"],
                estimated_minutes=60,
                source_ids=["source:read-only"],
            )
        ],
    )


def _manifestless_plan() -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:lifecycle",
        goal="Verify atomic syllabus lifecycle",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
    )


def _manifest_syllabus(version: int, manifest: str) -> StudySyllabus:
    return StudySyllabus(
        plan_id="study_plan:lifecycle",
        version=version,
        source_manifest_sha256=manifest,
        units=[
            StudySyllabusUnit(
                unit_id=f"lifecycle-{version}",
                title=f"Lifecycle {version}",
                objectives=["Verify lifecycle binding"],
                estimated_minutes=30,
                source_ids=["source:lifecycle"],
            )
        ],
    )


async def test_plan_create_list_link_version_and_optimistic_approval(clean_namespace):
    repository = StudyPlanRepository()

    created = await repository.create(_plan())
    assert created.plan_id == "study_plan:integration"
    assert created.version == 1

    linked = await repository.add_source(created.plan_id, "source:read-only")
    assert linked.source_id == "source:read-only"

    loaded = await repository.get(created.plan_id)
    assert loaded is not None
    assert [link.source_id for link in loaded.source_links] == ["source:read-only"]
    assert loaded.version == 2

    listed = await repository.list(limit=10)
    assert [plan.plan_id for plan in listed] == ["study_plan:integration"]

    proposed = await repository.save_syllabus(
        _syllabus(1), expected_revision=2, lifecycle_action="propose"
    )
    assert proposed.version == 1
    proposed_plan = await repository.get(created.plan_id)
    assert proposed_plan is not None
    assert proposed_plan.state == "syllabus_proposed"
    assert proposed_plan.version == 3

    await repository.save_syllabus(
        _syllabus(2), expected_revision=3, lifecycle_action="edit"
    )
    editing_plan = await repository.get(created.plan_id)
    assert editing_plan is not None
    assert editing_plan.state == "editing"
    assert editing_plan.version == 4
    syllabus_rows = await repo_query(
        "SELECT plan_id, version FROM study_syllabus WHERE plan_id = $plan_id "
        "ORDER BY version ASC",
        {"plan_id": "study_plan:integration"},
    )
    assert [row["version"] for row in syllabus_rows] == [1, 2]

    approved = await repository.approve_syllabus(
        created.plan_id,
        syllabus_version=2,
        expected_revision=4,
    )
    assert approved.state == "approved"
    assert approved.approved_syllabus_version == 2
    assert approved.version == 5

    current = await repository.get(created.plan_id)
    assert current is not None
    assert current.state == "approved"
    assert current.approved_syllabus_version == 2
    assert current.source_manifest_sha256 == "a" * 64


async def test_real_surreal_plan_timestamp_precision_boundary_is_ordered(
    clean_namespace,
):
    """One clock sample remains ordered through Surreal nanosecond storage."""
    boundary = datetime(2026, 8, 12, 12, 0, 0, 123456, tzinfo=UTC)
    plan = StudyPlan(
        plan_id="study_plan:timestamp-boundary",
        goal="Verify timestamp ordering at precision boundary",
        starting_level="beginner",
        created_at=boundary,
    )
    assert plan.updated_at == boundary
    created = await StudyPlanRepository().create(plan)
    loaded = await StudyPlanRepository().get(created.plan_id)
    assert loaded is not None
    assert loaded.updated_at >= loaded.created_at
    assert loaded.updated_at == loaded.created_at


async def test_assistant_session_handoff_memory_and_progress_are_durable(
    clean_namespace,
):
    repository = StudyPlanRepository()
    assistant = StudyAssistantRepository()
    plan_id = "study_plan:assistant-integration"
    created = await repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify assistant receipts",
            starting_level="beginner",
        )
    )
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    invocation = StudyAssistantInvocation(
        plan_id=plan_id,
        role="source_guide",
        authority="ask",
        prompt="Explain the selected source.",
        created_at=now,
    )
    session = await assistant.create_session(invocation, request_id="assistant-request")
    assert session.plan_id == plan_id
    assert session.prompt_sha256
    assert session.status == "queued"
    updated = await assistant.update_session(
        session.session_id,
        status="completed",
        expected_revision=session.revision,
        response_id="study_assistant_response:one",
        completed_at=now,
    )
    assert updated.status == "completed"
    assert (
        await assistant.update_session(
            session.session_id,
            status="completed",
            expected_revision=session.revision,
            response_id="study_assistant_response:one",
            completed_at=now,
        )
        == updated
    )

    handoff = StudyAssistantHandoff(
        plan_id=plan_id,
        session_id=session.session_id,
        role="source_guide",
        observation="The learner needs a smaller example.",
        evidence=({"source_id": "source:integration", "locator": "page:1"},),
        proposed_action="Ask one question.",
        origin="source_guide",
        user_decision="pending",
        created_at=now,
    )
    first_handoff = await assistant.append_handoff(
        handoff, request_id="handoff-request"
    )
    retry_handoff = await assistant.append_handoff(
        handoff, request_id="handoff-request"
    )
    assert first_handoff == retry_handoff
    assert await assistant.list_handoffs(plan_id, limit=999) == (first_handoff,)

    memory = StudyPlanMemory(
        plan_id=plan_id,
        memory_key="preference.answer_style",
        value="Prefer concise examples",
        provenance="user_confirmed",
        status="confirmed",
        confirmation_required=False,
        confirmed_at=now,
        created_at=now,
        updated_at=now,
    )
    persisted_memory = await assistant.upsert_memory(
        memory, expected_revision=0, request_id="memory-request"
    )
    assert persisted_memory.memory_key == memory.memory_key
    assert (
        await assistant.upsert_memory(
            memory, expected_revision=0, request_id="memory-request"
        )
        == persisted_memory
    )
    assert await assistant.get_memory(plan_id, memory.memory_key) == persisted_memory

    for index, invalid in enumerate(
        (
            {
                "status": "inferred",
                "confirmation_required": False,
                "confirmed_at": None,
            },
            {"status": "active", "confirmation_required": True, "confirmed_at": None},
            {
                "status": "confirmed",
                "confirmation_required": False,
                "confirmed_at": now,
            },
        )
    ):
        with pytest.raises(Exception):
            await repo_query(
                "CREATE $invalid_memory CONTENT $payload RETURN AFTER;",
                {
                    "invalid_memory": ensure_record_id(
                        f"study_plan_memory:invalid-inferred-{index}"
                    ),
                    "payload": {
                        "plan_id": plan_id,
                        "memory_key": f"inferred.invalid.{index}",
                        "value": "Needs confirmation",
                        "provenance": "assistant_inference",
                        **invalid,
                        "idempotency_hash": "b" * 64,
                        "created_at": now,
                        "updated_at": now,
                        "revision": 1,
                    },
                },
            )

    progress = StudyProgressReceipt(
        plan_id=plan_id,
        request_id="progress-request",
        unit_id="foundations",
        event="started",
        details="Session started",
        created_at=now,
    )
    first_progress = await assistant.append_progress(progress)
    retry_progress = await assistant.append_progress(progress)
    assert first_progress == retry_progress
    assert await assistant.list_progress(plan_id, limit=999) == (first_progress,)


async def test_assistant_completion_publishes_one_atomic_replay_receipt(
    clean_namespace,
):
    repository = StudyPlanRepository()
    assistant = StudyAssistantRepository()
    plan_id = "study_plan:assistant-completion"
    await repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify atomic assistant completion",
            starting_level="beginner",
        )
    )
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    # Surreal stores datetimes with nanosecond precision while the Python
    # driver decodes them to microseconds. The completion guard must compare
    # canonical microsecond values without weakening any other authority field.
    approved_at = datetime(2026, 8, 12, 12, 0, 0, 123456, tzinfo=UTC)
    evidence_text = "Atomic assistant evidence"
    evidence_sha256 = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
    evidence_id = "source:assistant-evidence"
    await repo_query(
        "CREATE $source CONTENT $payload RETURN AFTER;",
        {
            "source": ensure_record_id(evidence_id),
            "payload": {
                "title": "Assistant evidence",
                "source_type": "text",
                "full_text": evidence_text,
            },
        },
    )
    await repo_query(
        'UPDATE $study_plan MERGE { state: "active", active_syllabus_version: 1, '
        "source_manifest_sha256: $manifest, source_links: [$source_id] } RETURN AFTER;",
        {
            "study_plan": ensure_record_id(plan_id),
            "manifest": "a" * 64,
            "source_id": evidence_id,
        },
    )
    await repo_query(
        "CREATE $study_syllabus CONTENT { schema_version: 1, plan_id: $plan_id, "
        "version: 1, source_manifest_sha256: $manifest, "
        'approved_at: d"2026-08-12T12:00:00.123456789Z", created_at: $created_at } RETURN AFTER;',
        {
            "study_syllabus": ensure_record_id(
                "study_syllabus:assistant-completion-v1"
            ),
            "plan_id": plan_id,
            "manifest": "a" * 64,
            "created_at": now,
        },
    )
    invocation = StudyAssistantInvocation(
        plan_id=plan_id,
        role="source_guide",
        authority="ask",
        prompt="Explain the selected source.",
        created_at=now,
    )
    queued = await assistant.create_session(
        invocation, request_id="assistant-completion"
    )
    running = await assistant.update_session(
        queued.session_id,
        status="running",
        expected_revision=queued.revision,
    )
    handoff = StudyAssistantHandoff(
        request_id="assistant-completion:handoff",
        plan_id=plan_id,
        session_id=running.session_id,
        role="source_guide",
        observation="The selected source supports the explanation.",
        evidence=({"source_id": evidence_id, "locator": "page:1"},),
        proposed_action='[{"action":"navigate.unit","label":"Open unit","unit_id":null,"expected_revision":null}]',
        origin="source_guide",
        created_at=now,
    )
    completed, persisted_handoff = await assistant.complete_session(
        running.session_id,
        handoff,
        expected_revision=running.revision,
        response_id="study_assistant_response:completion",
        completed_at=now,
        authority_guard={
            "plan_revision": 1,
            "plan_state": "active",
            "syllabus_version": 1,
            "source_ids": (evidence_id,),
            "syllabus_approved_at": approved_at,
            "source_manifest_sha256": "a" * 64,
            "model_route": "local",
            "network_allowed": False,
            "network_scope": (),
            "source_evidence": (
                {
                    "source_id": evidence_id,
                    "full_text_sha256": evidence_sha256,
                },
            ),
        },
    )
    assert completed.status == "completed"
    assert completed.response_id == "study_assistant_response:completion"
    assert persisted_handoff.observation == handoff.observation
    assert await assistant.get_session(running.session_id) == completed
    assert await assistant.complete_session(
        running.session_id,
        handoff,
        expected_revision=running.revision,
        response_id="study_assistant_response:completion",
        completed_at=now,
        authority_guard={
            "plan_revision": 1,
            "plan_state": "active",
            "syllabus_version": 1,
            "source_ids": (evidence_id,),
            "syllabus_approved_at": approved_at,
            "source_manifest_sha256": "a" * 64,
            "model_route": "local",
            "network_allowed": False,
            "network_scope": (),
            "source_evidence": (
                {
                    "source_id": evidence_id,
                    "full_text_sha256": evidence_sha256,
                },
            ),
        },
    ) == (completed, persisted_handoff)

    drift_invocation = invocation.model_copy(
        update={
            "invocation_id": "assistant-authority-drift",
            "request_id": "assistant-authority-drift",
        }
    )
    drift_queued = await assistant.create_session(
        drift_invocation, request_id="assistant-authority-drift"
    )
    drift_running = await assistant.update_session(
        drift_queued.session_id,
        status="running",
        expected_revision=drift_queued.revision,
    )
    drift_handoff = handoff.model_copy(
        update={
            "request_id": "assistant-authority-drift:handoff",
            "session_id": drift_running.session_id,
        }
    )
    await repo_query(
        "UPDATE $source SET full_text = $changed RETURN AFTER;",
        {
            "source": ensure_record_id(evidence_id),
            "changed": "Changed after the assistant evidence check",
        },
    )
    with pytest.raises(
        StudyAssistantAuthorityConflictError,
        match="assistant completion authority changed",
    ):
        await assistant.complete_session(
            drift_running.session_id,
            drift_handoff,
            expected_revision=drift_running.revision,
            response_id="study_assistant_response:drift",
            completed_at=now,
            authority_guard={
                "plan_revision": 1,
                "plan_state": "active",
                "syllabus_version": 1,
                "source_ids": (evidence_id,),
                "syllabus_approved_at": approved_at,
                "source_manifest_sha256": "a" * 64,
                "model_route": "local",
                "network_allowed": False,
                "network_scope": (),
                "source_evidence": (
                    {
                        "source_id": evidence_id,
                        "full_text_sha256": evidence_sha256,
                    },
                ),
            },
        )
    persisted_drift = await assistant.get_session(drift_running.session_id)
    assert persisted_drift is not None
    assert persisted_drift.status == "running"
    assert (
        await assistant.get_handoff_by_request(
            plan_id, "assistant-authority-drift:handoff"
        )
        is None
    )


async def test_assistant_concurrent_mismatched_idempotency_winners_fail_closed(
    clean_namespace,
):
    """Real Surreal uniqueness races return one receipt and typed conflicts."""
    repository = StudyPlanRepository()
    assistant = StudyAssistantRepository()
    plan_id = "study_plan:assistant-concurrency"
    await repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify concurrent receipts",
            starting_level="beginner",
        )
    )
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    session_results = await asyncio.gather(
        assistant.create_session(
            StudyAssistantInvocation(
                plan_id=plan_id,
                role="source_guide",
                authority="ask",
                prompt="Same prompt",
                created_at=now,
            ),
            request_id="concurrent-session",
        ),
        assistant.create_session(
            StudyAssistantInvocation(
                plan_id=plan_id,
                role="concept_explainer",
                authority="ask",
                prompt="Same prompt",
                created_at=now,
            ),
            request_id="concurrent-session",
        ),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, StudyAssistantConflictError)
            for result in session_results
        )
        == 1
    )
    assert sum(not isinstance(result, BaseException) for result in session_results) == 1
    winning_session = next(
        result for result in session_results if not isinstance(result, BaseException)
    )
    assert (
        await assistant.create_session(
            StudyAssistantInvocation(
                plan_id=plan_id,
                role=winning_session.role,
                authority=winning_session.authority,
                prompt="Same prompt",
                created_at=now,
            ),
            request_id="concurrent-session",
        )
        == winning_session
    )

    running_results = await asyncio.gather(
        assistant.update_session(
            winning_session.session_id,
            status="running",
            expected_revision=winning_session.revision,
        ),
        assistant.update_session(
            winning_session.session_id,
            status="running",
            expected_revision=winning_session.revision,
        ),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, StudyAssistantConflictError)
            for result in running_results
        )
        == 1
    )
    assert sum(not isinstance(result, BaseException) for result in running_results) == 1

    session_id = winning_session.session_id
    handoff_results = await asyncio.gather(
        assistant.append_handoff(
            StudyAssistantHandoff(
                plan_id=plan_id,
                session_id=session_id,
                role="source_guide",
                observation="Winner A",
                origin="source_guide",
                created_at=now,
            ),
            request_id="concurrent-handoff",
        ),
        assistant.append_handoff(
            StudyAssistantHandoff(
                plan_id=plan_id,
                session_id=session_id,
                role="source_guide",
                observation="Winner B",
                origin="source_guide",
                created_at=now,
            ),
            request_id="concurrent-handoff",
        ),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, StudyAssistantConflictError)
            for result in handoff_results
        )
        == 1
    )
    assert sum(not isinstance(result, BaseException) for result in handoff_results) == 1
    winning_handoff = next(
        result for result in handoff_results if not isinstance(result, BaseException)
    )
    assert (
        await assistant.append_handoff(
            StudyAssistantHandoff(
                plan_id=plan_id,
                session_id=session_id,
                role="source_guide",
                observation=winning_handoff.observation,
                origin="source_guide",
                created_at=now,
            ),
            request_id="concurrent-handoff",
        )
        == winning_handoff
    )

    memory_results = await asyncio.gather(
        assistant.upsert_memory(
            StudyPlanMemory(
                plan_id=plan_id,
                memory_key="concurrent.memory",
                value="Winner A",
                provenance="user_confirmed",
                status="confirmed",
                confirmation_required=False,
                confirmed_at=now,
                created_at=now,
                updated_at=now,
            ),
            expected_revision=0,
            request_id="concurrent-memory",
        ),
        assistant.upsert_memory(
            StudyPlanMemory(
                plan_id=plan_id,
                memory_key="concurrent.memory",
                value="Winner B",
                provenance="user_confirmed",
                status="confirmed",
                confirmation_required=False,
                confirmed_at=now,
                created_at=now,
                updated_at=now,
            ),
            expected_revision=0,
            request_id="concurrent-memory",
        ),
        return_exceptions=True,
    )
    assert (
        sum(
            isinstance(result, StudyAssistantConflictError) for result in memory_results
        )
        == 1
    )
    assert sum(not isinstance(result, BaseException) for result in memory_results) == 1


async def test_plan_artifact_link_is_atomic_and_retry_idempotent(clean_namespace):
    repository = StudyPlanRepository()
    await repository.create(_plan())

    first = await repository.link_artifact(
        "study_plan:integration",
        "studio_artifact:quiz-one",
        artifact_kind="quiz",
        metadata={"unit_id": "foundations", "syllabus_version": 1},
    )
    retry = await repository.link_artifact(
        "study_plan:integration",
        "studio_artifact:quiz-one",
        artifact_kind="quiz",
        metadata={"unit_id": "foundations", "syllabus_version": 1},
    )
    found = await repository.find_artifact_link(
        "study_plan:integration",
        unit_id="foundations",
        artifact_kind="quiz",
        syllabus_version=1,
    )
    rows = await repo_query(
        "SELECT plan_id, artifact_id, artifact_kind, metadata "
        "FROM study_plan_artifact WHERE plan_id = $plan_id",
        {"plan_id": "study_plan:integration"},
    )

    assert first == retry
    assert found == first
    assert rows == [
        {
            "plan_id": "study_plan:integration",
            "artifact_id": "studio_artifact:quiz-one",
            "artifact_kind": "quiz",
            "metadata": {"unit_id": "foundations", "syllabus_version": 1},
        }
    ]


async def test_study_artifact_provisional_record_accepts_plan_owner_token(
    clean_namespace,
):
    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {
            "source": ensure_record_id("source:artifact-owner"),
            "data": {"title": "Artifact evidence", "full_text": "Evidence"},
        },
    )
    artifact = StudioArtifact(
        notebook_id="notebook:study_integration",
        artifact_type="quiz",
        title="Foundations quiz",
        source_ids=["source:artifact-owner"],
    )
    await artifact.save()

    assert artifact.id is not None
    loaded = await StudioArtifact.get(artifact.id)
    assert loaded.notebook_id == "notebook:study_integration"
    assert loaded.source_ids == ["source:⟨artifact-owner⟩"]


async def test_real_studio_claim_serializes_independent_services(
    clean_namespace, monkeypatch
):
    repository = StudyPlanRepository()
    plan_id = "study_plan:artifactconcurrency"
    source = SimpleNamespace(
        id="source:artifactconcurrency",
        title="Concurrency evidence",
        full_text="Persistent evidence for one generated artifact.",
        provenance={},
        command=None,
    )
    manifest = source_manifest([source])
    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {
            "source": ensure_record_id(source.id),
            "data": {"title": source.title, "full_text": source.full_text},
        },
    )
    created = await repository.create(
        StudyPlan(
            plan_id=plan_id,
            goal="Verify persistent artifact claims",
            starting_level="beginner",
        )
    )
    await repository.add_source(plan_id, source.id, expected_revision=created.version)
    linked_plan = await repository.get(plan_id)
    assert linked_plan is not None
    syllabus_one = StudySyllabus(
        plan_id=plan_id,
        version=1,
        source_manifest_sha256=manifest,
        units=[
            StudySyllabusUnit(
                unit_id="foundations",
                title="Foundations",
                objectives=["Keep one persistent claim"],
                estimated_minutes=30,
                source_ids=[source.id],
            )
        ],
    )
    await repository.save_syllabus(
        syllabus_one,
        expected_revision=linked_plan.version,
        lifecycle_action="propose",
    )
    syllabus_two = syllabus_one.model_copy(update={"version": 2})
    await repository.save_syllabus(
        syllabus_two,
        expected_revision=linked_plan.version + 1,
        lifecycle_action="edit",
    )
    approved = await repository.approve_syllabus(
        plan_id,
        syllabus_version=2,
        expected_revision=linked_plan.version + 2,
    )
    stored_syllabus = await repository.get_syllabus(plan_id, version=2)
    assert stored_syllabus is not None

    class ReadySourceService:
        async def readiness(self, _plan):
            return StudySourceReadiness(
                ready=True,
                items=(
                    StudySourceReadinessItem(
                        source_id=source.id,
                        title=source.title,
                        kind="text",
                        ready=True,
                        command_id=None,
                        fingerprint_status="available",
                        reason="ready",
                    ),
                ),
            )

    started = asyncio.Event()
    release_old = asyncio.Event()
    generation_calls = 0
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    current_time = [now]

    async def generate(request):
        nonlocal generation_calls
        generation_calls += 1
        artifact = await StudioArtifact.get(request.artifact_id)
        if generation_calls == 1:
            started.set()
            await release_old.wait()
            artifact.output_payload = {"markdown": "old owner"}
        else:
            artifact.output_payload = {"markdown": "fresh owner"}
        artifact.status = "completed"
        before = getattr(request, "before_persist", None)
        if before is not None:
            await before(artifact)
        persist = getattr(request, "persist_artifact", None)
        if persist is None:
            await artifact.save()
        else:
            result = persist(artifact)
            if hasattr(result, "__await__"):
                await result
        return await StudioArtifact.get(request.artifact_id)

    monkeypatch.setattr(
        "deeper_notebook.study.artifact_service.generate_artifact", generate
    )
    first_service = StudyArtifactService(
        repository=repository,
        source_service=ReadySourceService(),
        source_loader=lambda _source_id: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "old-owner",
        lock_store={},
    )
    second_service = StudyArtifactService(
        repository=repository,
        source_service=ReadySourceService(),
        source_loader=lambda _source_id: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "fresh-owner",
        lock_store={},
    )
    first = asyncio.create_task(
        first_service.generate_unit(plan_id, "foundations", ["quiz"], approved.version)
    )
    await started.wait()
    current_time[0] = now + timedelta(seconds=241)
    second = asyncio.create_task(
        second_service.generate_unit(plan_id, "foundations", ["quiz"], approved.version)
    )
    await asyncio.sleep(0)
    release_old.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    operation_id = _artifact_identity(plan_id, 2, manifest, "foundations", "quiz")
    artifact_rows = await repo_query(
        "SELECT id, status FROM studio_artifact WHERE id = $artifact_id;",
        {"artifact_id": ensure_record_id(operation_id)},
    )
    link_rows = await repo_query(
        "SELECT artifact_id FROM study_plan_artifact WHERE plan_id = $plan_id;",
        {"plan_id": plan_id},
    )
    assert generation_calls == 2
    assert len(artifact_rows) == 1
    assert artifact_rows[0]["status"] == "completed"
    assert link_rows == [{"artifact_id": operation_id}]
    assert sum(isinstance(result, StudyArtifactConflict) for result in results) == 1
    assert sum(isinstance(result, list) for result in results) == 1
    payload_rows = await repo_query(
        "SELECT status, output_payload, generation_claim_owner FROM $artifact;",
        {"artifact": ensure_record_id(operation_id)},
    )
    assert payload_rows == [
        {
            "status": "completed",
            "output_payload": {"markdown": "fresh owner"},
            "generation_claim_owner": None,
        }
    ]
    reused = await second_service.generate_unit(
        plan_id, "foundations", ["quiz"], approved.version
    )
    assert reused == next(result for result in results if isinstance(result, list))
    assert generation_calls == 2


async def test_real_studio_stale_claim_takeover_is_atomic_and_owner_fenced(
    clean_namespace,
):
    operation_id = _artifact_identity(
        "study_plan:stale-claim", 1, "a" * 64, "foundations", "quiz"
    )
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    stale_started = now - timedelta(seconds=300)
    # Equality is the durable lease boundary: the old owner is expired and
    # concurrent contenders must be able to converge on one fresh claim.
    stale_until = now
    await repo_query(
        "CREATE $artifact CONTENT $data RETURN AFTER;",
        {
            "artifact": ensure_record_id(operation_id),
            "data": {
                "notebook_id": ensure_record_id("notebook:study_integration"),
                "artifact_type": "quiz",
                "title": "Stale claim",
                "status": "running",
                "source_ids": [],
                "generation_claim_owner": "dead-worker",
                "generation_claim_started_at": stale_started,
                "generation_claim_lease_until": stale_until,
            },
        },
    )
    stale_snapshot = await StudioArtifact.get(operation_id)
    first_service = StudyArtifactService(
        repository=object(),
        source_service=object(),
        clock=lambda: now,
        owner_token_factory=lambda: "worker-one",
    )
    second_service = StudyArtifactService(
        repository=object(),
        source_service=object(),
        clock=lambda: now,
        owner_token_factory=lambda: "worker-two",
    )

    async def claim(service: StudyArtifactService):
        current = await StudioArtifact.get(operation_id)
        return await service._claim_provisional(current, operation_id, "quiz", ())

    results = await asyncio.gather(
        claim(first_service), claim(second_service), return_exceptions=True
    )

    assert sum(isinstance(result, StudyArtifactConflict) for result in results) == 1
    assert sum(isinstance(result, tuple) for result in results) == 1
    rows = await repo_query(
        "SELECT status, generation_claim_owner, generation_claim_started_at, "
        "generation_claim_lease_until FROM $artifact;",
        {"artifact": ensure_record_id(operation_id)},
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["generation_claim_owner"] in {"worker-one", "worker-two"}
    assert rows[0]["generation_claim_started_at"] == now
    assert rows[0]["generation_claim_lease_until"] == now + timedelta(seconds=240)

    # A stale owner that wakes after takeover cannot mark the new owner's row
    # failed; the conditional mutation returns no row and remains non-authorizing.
    await first_service._mark(stale_snapshot, "failed", owner_token="dead-worker")
    after_fenced_mark = await repo_query(
        "SELECT status, generation_claim_owner FROM $artifact;",
        {"artifact": ensure_record_id(operation_id)},
    )
    assert after_fenced_mark == [
        {
            "status": "running",
            "generation_claim_owner": rows[0]["generation_claim_owner"],
        }
    ]


async def test_manifestless_plan_lifecycle_binds_exact_syllabus_manifest_atomically(
    clean_namespace,
):
    repository = StudyPlanRepository()
    created = await repository.create(_manifestless_plan())
    assert created.source_manifest_sha256 is None

    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {
            "source": ensure_record_id("source:lifecycle"),
            "data": {"title": "Lifecycle source", "full_text": "Initial evidence"},
        },
    )
    await repository.add_source(
        created.plan_id, "source:lifecycle", expected_revision=1
    )
    analyzing = await repository.get(created.plan_id)
    assert analyzing is not None
    assert analyzing.state == "analyzing_sources"
    assert analyzing.version == 2

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.save_syllabus(
            _manifest_syllabus(99, "d" * 64),
            expected_revision=2,
            lifecycle_action="edit",
        )
    assert (
        await repo_query(
            "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
            {"plan_id": created.plan_id},
        )
        == []
    )

    await repository.save_syllabus(
        _manifest_syllabus(1, "b" * 64),
        expected_revision=2,
        lifecycle_action="propose",
    )
    proposed = await repository.get(created.plan_id)
    assert proposed is not None
    assert proposed.state == "syllabus_proposed"
    assert proposed.version == 3

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=1, expected_revision=3
        )
    still_proposed = await repository.get(created.plan_id)
    assert still_proposed == proposed
    assert (
        await repo_query(
            "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 1",
            {"plan_id": created.plan_id},
        )
    )[0].get("approved_at") is None

    await repository.save_syllabus(
        _manifest_syllabus(2, "c" * 64),
        expected_revision=3,
        lifecycle_action="edit",
    )
    editing = await repository.get(created.plan_id)
    assert editing is not None
    assert editing.state == "editing"
    assert editing.version == 4

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=2, expected_revision=3
        )
    stale = await repository.get(created.plan_id)
    assert stale == editing
    assert (
        await repo_query(
            "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 2",
            {"plan_id": created.plan_id},
        )
    )[0].get("approved_at") is None

    approved = await repository.approve_syllabus(
        created.plan_id, syllabus_version=2, expected_revision=4
    )
    assert approved.state == "approved"
    assert approved.version == 5
    assert approved.approved_syllabus_version == 2
    assert approved.source_manifest_sha256 == "c" * 64


async def test_syllabus_read_projects_exact_or_latest_ordered_immutable_version(
    clean_namespace,
):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    await repository.save_syllabus(_syllabus(1), expected_revision=created.version)
    await repository.save_syllabus(_syllabus(2), expected_revision=created.version)
    persisted_units = await repo_query(
        "SELECT plan_id, syllabus_version, unit_id, position FROM study_unit "
        "ORDER BY syllabus_version ASC, position ASC"
    )
    assert persisted_units == [
        {
            "plan_id": created.plan_id,
            "syllabus_version": 1,
            "unit_id": "foundations-1",
            "position": 0,
        },
        {
            "plan_id": created.plan_id,
            "syllabus_version": 2,
            "unit_id": "foundations-2",
            "position": 0,
        },
    ]
    exact_rows = await repo_query(
        "SELECT plan_id, syllabus_version, unit_id, position FROM study_unit "
        "WHERE type::string(plan_id) = $plan_id AND syllabus_version = $version "
        "ORDER BY position ASC LIMIT 64",
        {"plan_id": created.plan_id, "version": 1},
    )
    assert exact_rows == [persisted_units[0]]

    exact = await repository.get_syllabus(created.plan_id, version=1)
    latest = await repository.get_syllabus(created.plan_id)

    assert exact is not None
    assert exact.version == 1
    assert [unit.unit_id for unit in exact.units] == ["foundations-1"]
    assert latest is not None
    assert latest.version == 2
    assert [unit.unit_id for unit in latest.units] == ["foundations-2"]
    assert await repository.get_syllabus("study_plan:missing") is None


async def test_plan_source_removal_does_not_delete_source_record(clean_namespace):
    repository = StudyPlanRepository()
    await repository.create(_plan())
    source_id = ensure_record_id("source:owned-elsewhere")
    source_data = {
        "title": "Task-owned source",
        "full_text": "Immutable source body",
    }
    await repo_query(
        "CREATE $source CONTENT $data RETURN AFTER;",
        {"source": source_id, "data": source_data},
    )
    before = await repo_query(
        "SELECT id, title, full_text FROM source WHERE id = $source_id",
        {"source_id": source_id},
    )
    await repository.add_source(
        "study_plan:integration", "source:owned-elsewhere", expected_revision=1
    )

    removed = await repository.remove_source(
        "study_plan:integration", "source:owned-elsewhere", expected_revision=2
    )
    assert removed is True

    source_rows = await repo_query(
        "SELECT id, title, full_text FROM source WHERE id = $source_id",
        {"source_id": source_id},
    )
    assert source_rows == before
    loaded = await repository.get("study_plan:integration")
    assert loaded is not None
    assert loaded.source_links == ()


async def test_guarded_approval_missing_or_stale_is_atomic(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    before = await repository.get(created.plan_id)
    assert before is not None

    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=99, expected_revision=1
        )
    after_missing = await repository.get(created.plan_id)
    assert after_missing == before
    assert (
        await repo_query(
            "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
            {"plan_id": created.plan_id},
        )
        == []
    )

    await repository.add_source(created.plan_id, "source:guard", expected_revision=1)
    await repository.save_syllabus(
        _syllabus(1), expected_revision=2, lifecycle_action="propose"
    )
    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=1, expected_revision=99
        )
    still_pending = await repository.get(created.plan_id)
    assert still_pending is not None
    assert still_pending.version == 3
    assert still_pending.state == "syllabus_proposed"
    assert (
        await repo_query(
            "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 1",
            {"plan_id": created.plan_id},
        )
    )[0].get("approved_at") is None

    await repository.save_syllabus(
        _syllabus(2), expected_revision=3, lifecycle_action="edit"
    )
    approved = await repository.approve_syllabus(
        created.plan_id, syllabus_version=1, expected_revision=4
    )
    assert approved.approved_syllabus_version == 1
    with pytest.raises(Exception, match="study syllabus|revision"):
        await repository.approve_syllabus(
            created.plan_id, syllabus_version=2, expected_revision=3
        )
    unchanged = await repository.get(created.plan_id)
    assert unchanged is not None
    assert unchanged.approved_syllabus_version == 1
    assert unchanged.version == 5
    assert (
        await repo_query(
            "SELECT approved_at FROM study_syllabus WHERE plan_id = $plan_id AND version = 2",
            {"plan_id": created.plan_id},
        )
    )[0].get("approved_at") is None


async def test_guarded_link_and_syllabus_mutations_roll_back(clean_namespace):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())

    with pytest.raises(Exception, match="study source|plan"):
        await repository.add_source(
            created.plan_id, "source:stale", expected_revision=99
        )
    assert (
        await repo_query(
            "SELECT id FROM study_plan_source WHERE plan_id = $plan_id",
            {"plan_id": created.plan_id},
        )
        == []
    )

    with pytest.raises(Exception, match="study source|plan"):
        await repository.remove_source(
            created.plan_id, "source:stale", expected_revision=99
        )
    assert await repository.get(created.plan_id) == created

    with pytest.raises(Exception, match="study syllabus|plan"):
        await repository.save_syllabus(_syllabus(1), expected_revision=99)
    assert (
        await repo_query(
            "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
            {"plan_id": created.plan_id},
        )
        == []
    )

    with pytest.raises(Exception, match="study source|plan"):
        await repository.add_source(
            "study_plan:missing", "source:missing", expected_revision=1
        )
    assert (
        await repo_query(
            "SELECT id FROM study_plan_source WHERE source_id = 'source:missing'",
        )
        == []
    )

    await repository.add_source(created.plan_id, "source:existing", expected_revision=1)
    with pytest.raises(Exception, match="study plan|source"):
        await repository.remove_source(
            "study_plan:missing", "source:existing", expected_revision=1
        )
    linked = await repository.get(created.plan_id)
    assert linked is not None
    assert [item.source_id for item in linked.source_links] == ["source:existing"]

    with pytest.raises(Exception, match="study syllabus|plan"):
        await repository.save_syllabus(
            _syllabus(2).model_copy(update={"plan_id": "study_plan:missing"}),
            expected_revision=1,
        )
    assert (
        await repo_query(
            "SELECT id FROM study_syllabus WHERE plan_id = $plan_id",
            {"plan_id": "study_plan:missing"},
        )
        == []
    )


async def test_mapping_update_rejects_invalid_contract_without_db_change(
    clean_namespace,
):
    repository = StudyPlanRepository()
    created = await repository.create(_plan())
    for changes in (
        {"goal": " "},
        {"starting_level": ""},
        {"preferences": {"weekly_minutes": "bad", "session_minutes": 30}},
        {"target_date": "2026-99-99"},
    ):
        with pytest.raises(Exception, match="invalid study plan update"):
            await repository.update(created.plan_id, changes, expected_revision=1)
        assert await repository.get(created.plan_id) == created
