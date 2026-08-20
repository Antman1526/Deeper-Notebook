from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deeper_notebook.study.assistant_repository import (
    StudyAssistantAuthorityConflictError,
    StudyAssistantConflictError,
)
from deeper_notebook.study.assistant_service import (
    ROLE_POLICIES,
    StudyAssistantMalformedOutput,
    StudyAssistantPolicyError,
    StudyAssistantService,
    StudyAssistantTimeout,
)
from deeper_notebook.study.assistants import (
    STUDY_ASSISTANT_ROLES,
    StudyAssistantInvocation,
    StudyAssistantResponse,
    StudyCitation,
    StudyProposedAction,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)


def invocation(**changes: object) -> StudyAssistantInvocation:
    values: dict[str, object] = {
        "invocation_id": "invoke-one",
        "request_id": "request-one",
        "plan_id": "study_plan:one",
        "unit_id": "unit-one",
        "role": "source_guide",
        "authority": "ask",
        "prompt": "Explain the selected source.",
        "selected_source_ids": ("source:allowed",),
        "created_at": NOW,
    }
    values.update(changes)
    return StudyAssistantInvocation.model_validate(values)


class FakePlanRepository:
    def __init__(self) -> None:
        self.version = 3
        self.state = "approved"

    async def get(self, plan_id: str):
        return SimpleNamespace(
            plan_id=plan_id,
            version=self.version,
            state=self.state,
            goal="Learn bounded systems",
            starting_level="beginner",
            source_links=(
                SimpleNamespace(source_id="source:allowed"),
                SimpleNamespace(source_id="source:other"),
            ),
            approved_syllabus_version=2,
            preferences=SimpleNamespace(
                model_route="cloud",
                network_allowed=True,
                approved_network_scope=(
                    "https://allowed.example.edu",
                    "https://models.example.edu",
                ),
            ),
        )

    async def get_syllabus(self, plan_id: str, version: int | None = None):
        return SimpleNamespace(
            plan_id=plan_id,
            version=version or 2,
            approved_at=NOW,
            source_manifest_sha256="a" * 64,
            units=(
                SimpleNamespace(
                    unit_id="unit-one",
                    title="Bounded systems",
                    objectives=("Understand bounds",),
                    source_ids=("source:allowed",),
                ),
            ),
        )


class FakeSourceLoader:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    async def __call__(self, source_id: str):
        self.loaded.append(source_id)
        return SimpleNamespace(
            id=source_id, title=source_id, full_text=f"TEXT {source_id}"
        )


class FakeAssistantRepository:
    def __init__(self) -> None:
        self.handoff_limit = 0
        self.updates: list[dict[str, object]] = []
        self.completions: list[tuple[object, object, dict[str, object]]] = []
        self.session = SimpleNamespace(
            session_id="study_assistant_session:one", revision=1, status="queued"
        )
        self.handoffs: tuple[object, ...] = ()
        self.handoff_by_request: object | None = None
        self.update_delay = 0.0
        self.reject_completion_authority = False

    async def list_handoffs(self, plan_id: str, *, limit: int, offset: int = 0):
        self.handoff_limit = limit
        return self.handoffs

    async def list_memory(
        self, plan_id: str, *, status: str | None = None, limit: int, offset: int = 0
    ):
        return (
            SimpleNamespace(
                memory_key="goal", value="Use examples", status="confirmed"
            ),
        )

    async def list_progress(self, plan_id: str, *, limit: int, offset: int = 0):
        return ()

    async def create_session(self, invocation, *, request_id=None):
        return self.session

    async def get_handoff_by_request(self, plan_id, request_id):
        return self.handoff_by_request

    async def update_session(self, session_id, **kwargs):
        if self.update_delay:
            await asyncio.sleep(self.update_delay)
        self.updates.append(dict(kwargs))
        return SimpleNamespace(
            session_id=session_id,
            revision=kwargs["expected_revision"] + 1,
            status=kwargs["status"],
        )

    async def append_handoff(self, handoff, *, request_id=None):
        return handoff

    async def complete_session(self, session_id, handoff, **kwargs):
        if self.reject_completion_authority:
            raise StudyAssistantAuthorityConflictError(
                "assistant completion authority changed"
            )
        self.completions.append((session_id, handoff, dict(kwargs)))
        return SimpleNamespace(
            session_id=session_id,
            revision=kwargs["expected_revision"] + 1,
            status="completed",
            response_id=kwargs["response_id"],
            completed_at=kwargs["completed_at"],
        ), handoff


class FakeModel:
    def __init__(self, response: object | None = None, *, delay: bool = False) -> None:
        self.response = response or {
            "answer": "Selected evidence supports the explanation.",
            "citations": [
                {
                    "source_id": "source:allowed",
                    "locator": "p. 1",
                    "quote": "TEXT source:allowed",
                }
            ],
            "proposed_actions": [],
        }
        self.delay = delay
        self.last_prompt = ""
        self.call_count = 0

    async def ainvoke(self, prompt: str):
        self.call_count += 1
        self.last_prompt = prompt
        if self.delay:
            await asyncio.sleep(1)
        return self.response


def service(
    model: FakeModel | None = None, source_loader: FakeSourceLoader | None = None
):
    model = model or FakeModel()
    source_loader = source_loader or FakeSourceLoader()
    assistant_repository = FakeAssistantRepository()
    return (
        StudyAssistantService(
            plan_repository=FakePlanRepository(),
            assistant_repository=assistant_repository,
            source_loader=source_loader,
            model_resolver=lambda *_args, **_kwargs: model,
            url_validator=lambda url: SimpleNamespace(url=url),
        ),
        model,
        source_loader,
        assistant_repository,
    )


def test_all_twelve_roles_have_explicit_policies() -> None:
    assert set(ROLE_POLICIES) == set(STUDY_ASSISTANT_ROLES)
    assert len(ROLE_POLICIES) == 12
    assert {role: policy.model_role for role, policy in ROLE_POLICIES.items()} == {
        "study_director": "chat",
        "curriculum_architect": "source_synthesis",
        "socratic_tutor": "study_fast",
        "concept_explainer": "source_synthesis",
        "source_guide": "source_synthesis",
        "practice_coach": "study_fast",
        "exam_coach": "study_fast",
        "memory_coach": "study_fast",
        "research_scout": "coding_research",
        "project_mentor": "source_synthesis",
        "writing_coach": "source_synthesis",
        "progress_coach": "study_fast",
    }


def test_web_scope_uses_exact_host_port_and_path_boundaries() -> None:
    allowed = ("https://example.edu/course",)
    assert StudyAssistantService._url_in_scope("https://example.edu/course", allowed)
    assert StudyAssistantService._url_in_scope(
        "https://example.edu/course/one", allowed
    )
    assert not StudyAssistantService._url_in_scope(
        "https://example.edu/course-evil", allowed
    )
    assert not StudyAssistantService._url_in_scope(
        "https://example.edu.evil/course", allowed
    )
    assert not StudyAssistantService._url_in_scope(
        "https://example.edu:444/course", allowed
    )
    assert not StudyAssistantService._url_in_scope(
        "https://example.edu/course/../admin", allowed
    )
    assert not StudyAssistantService._url_in_scope(
        "https://example.edu/course/%2e%2e/admin", allowed
    )


@pytest.mark.asyncio
async def test_source_guide_retrieves_only_selected_plan_sources() -> None:
    subject, model, loader, repository = service()
    response = await subject.invoke("study_plan:one", "source_guide", invocation())
    assert set(response.retrieval_receipt.source_ids) == {"source:allowed"}
    assert loader.loaded == ["source:allowed"] * 3
    assert "source:other" not in model.last_prompt
    assert repository.handoff_limit == 20


@pytest.mark.asyncio
async def test_selected_source_evidence_survives_maximum_metadata_budget() -> None:
    subject, model, _loader, repository = service()

    async def maximum_memory(
        _plan_id: str, *, status: str | None = None, limit: int, offset: int = 0
    ):
        assert status == "confirmed"
        assert limit == 50
        assert offset == 0
        return tuple(
            SimpleNamespace(
                memory_key=f"memory-{index}",
                value="M" * 4_000,
                status="confirmed",
            )
            for index in range(50)
        )

    repository.list_memory = maximum_memory
    response = await subject.invoke("study_plan:one", "source_guide", invocation())

    assert response.status == "completed"
    assert "SOURCE source:allowed" in model.last_prompt
    assert "TEXT source:allowed" in model.last_prompt
    assert len(model.last_prompt) <= 64_000


@pytest.mark.asyncio
async def test_concurrent_identical_invocations_have_one_running_owner() -> None:
    subject, model, _loader, repository = service()
    claim_lock = asyncio.Lock()
    claimed = False

    async def one_winner_update(session_id: str, **kwargs):
        nonlocal claimed
        if kwargs["status"] != "running":
            return await FakeAssistantRepository.update_session(
                repository, session_id, **kwargs
            )
        async with claim_lock:
            if claimed:
                raise StudyAssistantConflictError(
                    "assistant session is already running"
                )
            claimed = True
        return SimpleNamespace(
            session_id=session_id,
            revision=kwargs["expected_revision"] + 1,
            status="running",
        )

    repository.update_session = one_winner_update
    results = await asyncio.gather(
        subject.invoke("study_plan:one", "source_guide", invocation()),
        subject.invoke("study_plan:one", "source_guide", invocation()),
        return_exceptions=True,
    )

    assert sum(isinstance(result, StudyAssistantResponse) for result in results) == 1
    assert (
        sum(
            isinstance(result, StudyAssistantPolicyError)
            and str(result) == "assistant_invocation_in_progress"
            for result in results
        )
        == 1
    )
    assert model.call_count == 1
    assert len(repository.completions) == 1


@pytest.mark.asyncio
async def test_research_scout_fails_closed_without_explicit_web_scope() -> None:
    subject, *_ = service()
    with pytest.raises(StudyAssistantPolicyError, match="network_not_approved"):
        await subject.invoke(
            "study_plan:one",
            "research_scout",
            invocation(role="research_scout", selected_source_ids=()),
        )


@pytest.mark.asyncio
async def test_explicit_cloud_route_uses_only_the_cloud_resolver() -> None:
    model = FakeModel()
    subject, local_model, *_ = service()
    calls: list[str] = []

    async def cloud(model_role: str, _invocation: StudyAssistantInvocation):
        calls.append(model_role)
        return model

    subject.cloud_model_resolver = cloud
    response = await subject.invoke(
        "study_plan:one",
        "concept_explainer",
        invocation(
            role="concept_explainer",
            model_route="cloud",
            network_allowed=True,
            approved_network_scope=("https://models.example.edu",),
        ),
    )
    assert response.status == "completed"
    assert calls == ["source_synthesis"]
    assert local_model.last_prompt == ""


@pytest.mark.asyncio
async def test_research_scout_filters_results_to_explicit_scope() -> None:
    model = FakeModel(
        {
            "answer": "The approved result supports the gap.",
            "citations": [
                {
                    "source_id": "https://allowed.example.edu/article",
                    "quote": "Evidence",
                }
            ],
            "proposed_actions": [],
        }
    )

    async def research(_query: str, _scope: tuple[str, ...]):
        return (
            SimpleNamespace(
                url="https://allowed.example.edu/article",
                title="Allowed",
                snippet="Evidence",
            ),
            SimpleNamespace(
                url="https://outside.example.net/article",
                title="Outside",
                snippet="Must not enter context",
            ),
        )

    subject, *_ = service(model)
    subject.web_researcher = research
    response = await subject.invoke(
        "study_plan:one",
        "research_scout",
        invocation(
            role="research_scout",
            selected_source_ids=(),
            network_allowed=True,
            approved_network_scope=("https://allowed.example.edu",),
        ),
    )
    assert response.citations[0].source_id == "https://allowed.example.edu/article"
    assert "outside.example.net" not in model.last_prompt


@pytest.mark.asyncio
async def test_research_scout_keeps_every_citable_web_excerpt_in_prompt() -> None:
    final_url = "https://allowed.example.edu/article-7"
    final_quote = "LAST WEB EVIDENCE"
    model = FakeModel(
        {
            "answer": "The final approved result supports the answer.",
            "citations": [{"source_id": final_url, "quote": final_quote}],
            "proposed_actions": [],
        }
    )
    subject, _model, _loader, repository = service(model)

    async def maximum_memory(
        _plan_id: str, *, status: str | None = None, limit: int, offset: int = 0
    ):
        return tuple(
            SimpleNamespace(
                memory_key=f"memory-{index}",
                value="M" * 4_000,
                status="confirmed",
            )
            for index in range(50)
        )

    repository.list_memory = maximum_memory
    subject.web_researcher = lambda *_args: tuple(
        SimpleNamespace(
            url=f"https://allowed.example.edu/article-{index}",
            title=f"Approved result {index}",
            snippet=(final_quote if index == 7 else f"WEB EVIDENCE {index}")
            + " W" * 2_000,
        )
        for index in range(8)
    )

    response = await subject.invoke(
        "study_plan:one",
        "research_scout",
        invocation(
            role="research_scout",
            selected_source_ids=(),
            network_allowed=True,
            approved_network_scope=("https://allowed.example.edu",),
        ),
    )

    assert response.status == "completed"
    assert final_url in model.last_prompt
    assert final_quote in model.last_prompt
    assert len(model.last_prompt) <= 64_000


def test_research_prompt_allows_only_evidence_ids_present_in_context() -> None:
    prompt = StudyAssistantService._prompt(
        "research_scout",
        invocation(
            role="research_scout",
            selected_source_ids=(),
            network_allowed=True,
            approved_network_scope=("https://allowed.example.edu",),
        ),
        ROLE_POLICIES["research_scout"],
        "SOURCE https://allowed.example.edu/article\nApproved evidence",
    )

    assert "only selected source IDs" not in prompt
    assert "evidence IDs explicitly present" in prompt


@pytest.mark.asyncio
async def test_default_web_discovery_preserves_approved_path_scope(monkeypatch) -> None:
    from deeper_notebook.tools import web_search

    calls: list[tuple[str, int]] = []

    async def search(query: str, *, max_results: int):
        calls.append((query, max_results))
        return ()

    monkeypatch.setattr(web_search, "run_web_search_with_evidence", search)
    await StudyAssistantService._default_web_research(
        "private topic", ("https://example.edu/approved/course",)
    )
    assert calls == [("(site:example.edu/approved/course) private topic", 8)]


@pytest.mark.asyncio
async def test_web_evidence_is_bounded_before_materialization() -> None:
    model = FakeModel(
        {
            "answer": "The bounded results support the gap.",
            "citations": [
                {
                    "source_id": "https://allowed.example.edu/0",
                    "quote": "Evidence",
                }
            ],
            "proposed_actions": [],
        }
    )
    examined = 0

    def evidence():
        nonlocal examined
        index = 0
        while True:
            examined += 1
            yield SimpleNamespace(
                url=f"https://allowed.example.edu/{index}",
                title=f"Result {index}",
                snippet="Evidence",
            )
            index += 1

    subject, *_ = service(model)
    subject.web_researcher = lambda *_args: evidence()
    await subject.invoke(
        "study_plan:one",
        "research_scout",
        invocation(
            role="research_scout",
            selected_source_ids=(),
            network_allowed=True,
            approved_network_scope=("https://allowed.example.edu",),
        ),
    )
    assert examined == 8


@pytest.mark.asyncio
async def test_web_results_must_pass_the_outbound_url_policy() -> None:
    model = FakeModel(
        {
            "answer": "The safe result supports the gap.",
            "citations": [
                {
                    "source_id": "https://allowed.example.edu/safe",
                    "quote": "The safe result supports the gap.",
                }
            ],
            "proposed_actions": [],
        }
    )
    validated: list[str] = []

    async def validate(url: str) -> object:
        validated.append(url)
        if url.endswith("unsafe"):
            raise ValueError("blocked")
        return SimpleNamespace(url=url)

    subject, *_ = service(model)
    subject.url_validator = validate
    subject.web_researcher = lambda *_args: (
        SimpleNamespace(
            url="https://allowed.example.edu/unsafe",
            title="Unsafe",
            snippet="Must not enter context",
        ),
        SimpleNamespace(
            url="https://allowed.example.edu/safe",
            title="Safe",
            snippet="The safe result supports the gap.",
        ),
    )
    response = await subject.invoke(
        "study_plan:one",
        "research_scout",
        invocation(
            role="research_scout",
            selected_source_ids=(),
            network_allowed=True,
            approved_network_scope=("https://allowed.example.edu",),
        ),
    )
    assert validated == [
        "https://allowed.example.edu/unsafe",
        "https://allowed.example.edu/safe",
    ]
    assert response.citations[0].source_id.endswith("/safe")
    assert "Must not enter context" not in model.last_prompt


@pytest.mark.asyncio
async def test_selected_source_role_rejects_uncited_model_output() -> None:
    subject, *_ = service(
        FakeModel({"answer": "No evidence", "citations": [], "proposed_actions": []})
    )
    with pytest.raises(StudyAssistantPolicyError, match="citations_required"):
        await subject.invoke("study_plan:one", "source_guide", invocation())


@pytest.mark.asyncio
async def test_citation_requires_a_quote_grounded_in_selected_evidence() -> None:
    subject, *_ = service(
        FakeModel(
            {
                "answer": "Claim",
                "citations": [{"source_id": "source:allowed", "locator": "p. 1"}],
                "proposed_actions": [],
            }
        )
    )
    with pytest.raises(StudyAssistantPolicyError, match="citation_quote_required"):
        await subject.invoke("study_plan:one", "source_guide", invocation())


@pytest.mark.asyncio
async def test_citations_and_actions_are_grounded_and_authority_bounded() -> None:
    ungrounded, *_ = service(
        FakeModel(
            {
                "answer": "Claim",
                "citations": [
                    {"source_id": "source:allowed", "quote": "invented quotation"}
                ],
                "proposed_actions": [],
            }
        )
    )
    with pytest.raises(StudyAssistantPolicyError, match="citation_quote_not_grounded"):
        await ungrounded.invoke("study_plan:one", "source_guide", invocation())

    destructive, *_ = service(
        FakeModel(
            {
                "answer": "Claim",
                "citations": [
                    {
                        "source_id": "source:allowed",
                        "quote": "TEXT source:allowed",
                    }
                ],
                "proposed_actions": [
                    {"action": "source.delete", "label": "Delete source"}
                ],
            }
        )
    )
    with pytest.raises(StudyAssistantPolicyError, match="proposed_action_not_allowed"):
        await destructive.invoke("study_plan:one", "source_guide", invocation())

    disguised, *_ = service(
        FakeModel(
            {
                "answer": "Claim",
                "citations": [
                    {
                        "source_id": "source:allowed",
                        "quote": "TEXT source:allowed",
                    }
                ],
                "proposed_actions": [
                    {
                        "action": "navigate.delete_learning_data",
                        "label": "Delete learning data",
                    }
                ],
            }
        )
    )
    with pytest.raises(StudyAssistantPolicyError, match="proposed_action_not_allowed"):
        await disguised.invoke("study_plan:one", "source_guide", invocation())


@pytest.mark.asyncio
async def test_whole_invocation_timeout_covers_context_loading() -> None:
    async def slow_source(_source_id: str):
        await asyncio.sleep(1)
        return None

    subject, *_ = service()
    subject.source_loader = slow_source
    with pytest.raises(StudyAssistantTimeout, match="assistant_timeout"):
        await subject.invoke(
            "study_plan:one",
            "source_guide",
            invocation(timeout_seconds=1),
            timeout_seconds=0.001,
        )


@pytest.mark.asyncio
async def test_running_retry_does_not_load_context_or_mutate_the_winner() -> None:
    subject, model, loader, repository = service()
    repository.session = SimpleNamespace(
        session_id="study_assistant_session:one", revision=2, status="running"
    )
    with pytest.raises(
        StudyAssistantPolicyError, match="assistant_invocation_in_progress"
    ):
        await subject.invoke("study_plan:one", "source_guide", invocation())
    assert loader.loaded == []
    assert model.last_prompt == ""
    assert repository.updates == []


@pytest.mark.asyncio
async def test_completed_retry_replays_full_receipt_without_model_or_context() -> None:
    subject, model, loader, repository = service()
    action = StudyProposedAction(
        action="navigate.unit", label="Open unit", unit_id="unit-one"
    )
    repository.session = SimpleNamespace(
        session_id="study_assistant_session:one",
        revision=3,
        status="completed",
        response_id="study_assistant_response:one",
        created_at=NOW,
        completed_at=NOW,
    )
    repository.handoffs = (
        SimpleNamespace(
            session_id="study_assistant_session:one",
            observation="Full replay answer",
            evidence=(
                StudyCitation(source_id="source:allowed", quote="TEXT source:allowed"),
            ),
            proposed_action='[{"action":"navigate.unit","label":"Open unit","unit_id":"unit-one","expected_revision":null}]',
            created_at=NOW,
        ),
    )
    repository.handoff_by_request = repository.handoffs[0]
    response = await subject.invoke(
        "study_plan:one",
        "source_guide",
        invocation(created_at=NOW.replace(minute=1)),
    )
    assert response.answer == "Full replay answer"
    assert response.proposed_actions == (action,)
    assert response.created_at == NOW
    assert loader.loaded == []
    assert model.last_prompt == ""


@pytest.mark.asyncio
async def test_completed_retry_uses_exact_request_receipt_not_recent_page() -> None:
    subject, model, loader, repository = service()
    repository.session = SimpleNamespace(
        session_id="study_assistant_session:one",
        revision=3,
        status="completed",
        response_id="study_assistant_response:one",
        completed_at=NOW,
    )
    repository.handoffs = tuple(
        SimpleNamespace(
            session_id=f"study_assistant_session:other-{index}",
            observation="Other",
            evidence=(),
            proposed_action=None,
            created_at=NOW,
        )
        for index in range(20)
    )
    repository.handoff_by_request = SimpleNamespace(
        session_id="study_assistant_session:one",
        observation="Exact replay",
        evidence=(StudyCitation(source_id="source:allowed"),),
        proposed_action=None,
        created_at=NOW,
    )
    response = await subject.invoke("study_plan:one", "source_guide", invocation())
    assert response.answer == "Exact replay"
    assert loader.loaded == []
    assert model.last_prompt == ""


@pytest.mark.asyncio
async def test_completion_uses_one_atomic_repository_boundary() -> None:
    subject, *_rest, repository = service()
    response = await subject.invoke("study_plan:one", "source_guide", invocation())
    assert response.status == "completed"
    assert len(repository.completions) == 1
    assert repository.updates == [{"status": "running", "expected_revision": 1}]
    assert repository.completions[0][2]["authority_guard"] == {
        "plan_revision": 3,
        "plan_state": "approved",
        "syllabus_version": 2,
        "source_ids": ("source:allowed", "source:other"),
        "syllabus_approved_at": NOW,
        "source_manifest_sha256": "a" * 64,
        "model_route": "cloud",
        "network_allowed": True,
        "network_scope": (
            "https://allowed.example.edu",
            "https://models.example.edu",
        ),
        "source_evidence": (
            {
                "source_id": "source:allowed",
                "full_text_sha256": "db8803a4f900b900d5293fbdb4bbd09d85c393f7a4be2137bcd98f42bc9a8d20",
            },
        ),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["approved", "generating", "active", "completed"])
async def test_tutors_remain_available_through_learning_lifecycle(state: str) -> None:
    subject, *_rest, repository = service()
    subject.plan_repository.state = state
    await subject.invoke("study_plan:one", "source_guide", invocation())
    assert repository.completions[0][2]["authority_guard"]["plan_state"] == state


@pytest.mark.asyncio
async def test_changed_body_request_id_is_a_stable_conflict() -> None:
    subject, *_rest, repository = service()

    async def conflict(*_args, **_kwargs):
        raise StudyAssistantConflictError("assistant request ID was already used")

    repository.create_session = conflict
    with pytest.raises(StudyAssistantPolicyError, match="assistant_request_conflict"):
        await subject.invoke("study_plan:one", "source_guide", invocation())


@pytest.mark.asyncio
async def test_plan_authority_drift_after_model_is_rejected() -> None:
    subject, *_ = service()
    plan_repository = subject.plan_repository
    model = subject.model_resolver("source_synthesis", invocation())
    original = model.ainvoke

    async def mutate_after_generation(prompt: str):
        result = await original(prompt)
        plan_repository.version += 1
        return result

    model.ainvoke = mutate_after_generation
    with pytest.raises(StudyAssistantPolicyError, match="study_authority_changed"):
        await subject.invoke("study_plan:one", "source_guide", invocation())


@pytest.mark.asyncio
async def test_final_atomic_publication_rejects_authority_drift() -> None:
    subject, *_rest, repository = service()
    repository.reject_completion_authority = True
    with pytest.raises(StudyAssistantPolicyError, match="study_authority_changed"):
        await subject.invoke("study_plan:one", "source_guide", invocation())
    assert repository.completions == []


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_safe() -> None:
    subject, *_ = service(FakeModel(delay=True))
    with pytest.raises(StudyAssistantTimeout, match="assistant_timeout"):
        await subject.invoke(
            "study_plan:one",
            "source_guide",
            invocation(timeout_seconds=1),
            timeout_seconds=0.001,
        )


@pytest.mark.asyncio
async def test_timeout_cleanup_cannot_extend_the_foreground_deadline() -> None:
    subject, *_rest, repository = service(FakeModel(delay=True))
    repository.update_delay = 0.2
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(StudyAssistantTimeout, match="assistant_timeout"):
        await subject.invoke(
            "study_plan:one",
            "source_guide",
            invocation(timeout_seconds=1),
            timeout_seconds=0.001,
        )
    assert loop.time() - started < 0.05


@pytest.mark.asyncio
async def test_cancellation_is_propagated_and_receipted() -> None:
    subject, *_rest, repository = service(FakeModel(delay=True))
    task = asyncio.create_task(
        subject.invoke("study_plan:one", "source_guide", invocation())
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repository.updates[-1]["status"] == "cancelled"
    assert repository.updates[-1]["error_code"] == "assistant_cancelled"


@pytest.mark.asyncio
async def test_completed_response_never_contains_provider_payload() -> None:
    subject, *_ = service()
    response = await subject.invoke("study_plan:one", "source_guide", invocation())
    assert isinstance(response, StudyAssistantResponse)
    assert response.status == "completed"
    assert response.citations == (
        StudyCitation(
            source_id="source:allowed",
            locator="p. 1",
            quote="TEXT source:allowed",
        ),
    )
    assert "provider" not in response.model_dump()
