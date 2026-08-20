"""Strict contracts for the bounded Study assistant boundary.

These tests deliberately exercise the public contract before any repository or
orchestration code exists.  A future assistant service may add behavior, but it
must not widen these immutable, plan-local records.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deeper_notebook.study.assistants import (
    STUDY_ASSISTANT_ROLES,
    STUDY_AUTHORITIES,
    StudyAssistantHandoff,
    StudyAssistantInvocation,
    StudyAssistantResponse,
    StudyPlanMemory,
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


def test_all_twelve_roles_and_four_authorities_are_exact() -> None:
    assert STUDY_ASSISTANT_ROLES == (
        "study_director",
        "curriculum_architect",
        "socratic_tutor",
        "concept_explainer",
        "source_guide",
        "practice_coach",
        "exam_coach",
        "memory_coach",
        "research_scout",
        "project_mentor",
        "writing_coach",
        "progress_coach",
    )
    assert STUDY_AUTHORITIES == ("ask", "coach", "plan", "create")
    assert set(
        StudyAssistantInvocation.model_fields["role"].annotation.__args__
    ) == set(  # type: ignore[attr-defined]
        STUDY_ASSISTANT_ROLES
    )


def test_invocation_is_deeply_immutable_and_bounded() -> None:
    invocation = _invocation(
        selected_source_ids=("source:one",),
        citations=({"source_id": "source:one", "locator": "page:1", "quote": "A"},),
        proposed_actions=({"action": "review_source", "label": "Review source"},),
    )
    with pytest.raises(ValidationError):
        _invocation(prompt="x" * 16_385)
    with pytest.raises(ValidationError):
        _invocation(citations=tuple({"source_id": f"source:{i}"} for i in range(33)))
    with pytest.raises(ValidationError):
        _invocation(
            proposed_actions=tuple(
                {"action": "review_source", "label": str(i)} for i in range(21)
            )
        )
    with pytest.raises((ValidationError, TypeError)):
        invocation.citations[0]["quote"] = "mutate"  # type: ignore[index]
    with pytest.raises(ValidationError):
        invocation.prompt = "changed"  # type: ignore[misc]


def test_create_authority_cannot_enable_network_or_mutate_syllabus() -> None:
    with pytest.raises(ValidationError):
        _invocation(
            role="research_scout",
            authority="create",
            network_allowed=True,
            approved_network_scope=None,
        )
    with pytest.raises(ValidationError):
        _invocation(
            authority="create",
            syllabus_mutation="approve",
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"authority": "plan", "syllabus_mutation": "edit"},
        {"authority": "plan", "mutates_syllabus": True, "syllabus_mutation": "propose"},
        {"authority": "plan", "mutates_sources": True},
        {"authority": "plan", "publishes_cards": True},
        {"authority": "plan", "changes_schedule": True},
    ],
)
def test_plan_authority_only_proposes_bounded_actions(
    updates: dict[str, object],
) -> None:
    """Plan mode can describe a proposal, never perform a protected mutation."""
    with pytest.raises(ValidationError):
        _invocation(**updates)


def test_plan_authority_accepts_only_a_proposal_without_protected_mutation() -> None:
    invocation = _invocation(
        authority="plan",
        syllabus_mutation="propose",
        proposed_actions=(
            {"action": "revise_syllabus", "label": "Review proposed prerequisite"},
        ),
    )
    assert invocation.syllabus_mutation == "propose"
    assert invocation.mutates_syllabus is False


def test_network_requires_explicit_approved_bounded_scope() -> None:
    with pytest.raises(ValidationError):
        _invocation(network_allowed=True)
    with pytest.raises(ValidationError):
        _invocation(
            role="research_scout",
            network_allowed=True,
            approved_network_scope=(),
        )
    allowed = _invocation(
        role="research_scout",
        network_allowed=True,
        approved_network_scope=("https://example.edu/research",),
    )
    assert allowed.network_allowed is True


def test_response_exposes_citations_and_actions_but_no_raw_provider_or_reasoning() -> (
    None
):
    response = StudyAssistantResponse(
        plan_id=PLAN_ID,
        role="source_guide",
        authority="ask",
        answer="The selected source describes the core idea.",
        citations=({"source_id": "source:one", "locator": "page:1", "quote": "A"},),
        proposed_actions=(),
        created_at=NOW,
    )
    assert response.answer
    assert "chain_of_thought" not in StudyAssistantResponse.model_fields
    assert "raw_provider_payload" not in StudyAssistantResponse.model_fields
    with pytest.raises(ValidationError):
        StudyAssistantResponse(
            plan_id=PLAN_ID,
            role="source_guide",
            authority="ask",
            answer="Answer",
            citations=(),
            proposed_actions=(),
            created_at=NOW,
            raw_provider_payload={"secret": "never"},
        )


def test_handoff_is_bounded_and_requires_plan_local_origin() -> None:
    handoff = StudyAssistantHandoff(
        plan_id=PLAN_ID,
        session_id="study_assistant_session:one",
        role="source_guide",
        observation="The learner is uncertain about velocity.",
        evidence=({"source_id": "source:one", "locator": "page:2"},),
        proposed_action="Ask one Socratic question.",
        origin="source_guide",
        user_decision="pending",
        created_at=NOW,
    )
    assert handoff.session_id == "study_assistant_session:one"
    with pytest.raises(ValidationError):
        StudyAssistantHandoff(
            plan_id=PLAN_ID,
            session_id="study_assistant_session:one",
            role="source_guide",
            observation="x" * 16_385,
            evidence=(),
            proposed_action=None,
            origin="source_guide",
            user_decision="pending",
            created_at=NOW,
        )
    with pytest.raises(ValidationError):
        handoff.user_decision = "accepted"  # type: ignore[misc]


def test_memory_provenance_status_and_inferred_confirmation_are_explicit() -> None:
    with pytest.raises(ValidationError):
        StudyPlanMemory(
            plan_id=PLAN_ID,
            memory_key="misconception.velocity",
            value="Confuses speed and velocity",
            provenance="assistant_inference",
            status="inferred",
            confirmation_required=False,
            created_at=NOW,
            updated_at=NOW,
        )
    inferred = StudyPlanMemory(
        plan_id=PLAN_ID,
        memory_key="misconception.velocity",
        value="Confuses speed and velocity",
        provenance="assistant_inference",
        status="inferred",
        confirmation_required=True,
        created_at=NOW,
        updated_at=NOW,
    )
    assert inferred.confirmed_at is None
    confirmed = inferred.confirm(now=NOW)
    assert confirmed.status == "confirmed"
    assert confirmed.confirmation_required is False
    assert confirmed.confirmed_at == NOW


@pytest.mark.parametrize("status", ["active", "confirmed"])
def test_assistant_inference_cannot_become_durable_without_user_decision(
    status: str,
) -> None:
    with pytest.raises(ValidationError):
        StudyPlanMemory(
            plan_id=PLAN_ID,
            memory_key="misconception.velocity",
            value="Confuses speed and velocity",
            provenance="assistant_inference",
            status=status,
            confirmation_required=False,
            confirmed_at=NOW if status == "confirmed" else None,
            created_at=NOW,
            updated_at=NOW,
        )
