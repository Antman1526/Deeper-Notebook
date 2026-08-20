"""Smallest-capable, local-only model-route planning contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from deeper_notebook.local_models.contracts import (
    LocalModelRouteCandidate,
    RouteRequest,
)
from deeper_notebook.local_models.planner import (
    BENCHMARK_MAX_AGE_SECONDS,
    LocalModelPlanner,
    classify_resource_tier,
)


def _candidate(model_id: str, *, tier_memory: int, latency_ms: int, **changes):
    candidate = LocalModelRouteCandidate(
        model_id=model_id,
        provider="loopback",
        fingerprint=f"fp-{model_id}",
        modalities=("text",),
        accepted_roles=("research_chat",),
        context_tokens=32_768,
        supports_structured_output=True,
        readiness="ready_verified",
        health_healthy=True,
        accepted_quality=90.0,
        benchmarked_at=1_000.0,
        peak_memory_bytes=tier_memory,
        latency_ms=latency_ms,
        is_local=True,
    )
    return replace(candidate, **changes)


@pytest.mark.parametrize(
    ("role", "modality"),
    [
        ("research_chat", "text"),
        ("evidence_extraction", "text"),
        ("claim_verification", "text"),
        ("editorial_writing", "text"),
        ("embedding_retrieval", "text"),
        ("vision_analysis", "image"),
        ("code_data_analysis", "text"),
        ("podcast_outline", "text"),
        ("podcast_script", "text"),
        ("speech_to_text", "audio"),
        ("text_to_speech", "audio"),
    ],
)
def test_planner_selects_a_verified_local_candidate_for_every_approved_role(
    role, modality
):
    candidate = _candidate(
        "model-a",
        tier_memory=4 * 1024**3,
        latency_ms=120,
        modalities=(modality,),
        accepted_roles=(role,),
    )

    plan = LocalModelPlanner([candidate], now=1_100.0).plan(
        RouteRequest(role=role, modalities=(modality,))
    )

    assert plan.outcome == "ready"
    assert plan.selected_model_id == "model-a"
    assert plan.route_reason
    assert set(plan.receipt()).isdisjoint({"path", "source", "output", "prompt"})


@pytest.mark.parametrize(
    ("peak_memory_bytes", "latency_ms", "expected"),
    [
        (4 * 1024**3, 300, "light"),
        (10 * 1024**3, 1_000, "standard"),
        (24 * 1024**3, 1_000, "heavyweight"),
        (4 * 1024**3, 4_000, "standard"),
    ],
)
def test_resource_tier_uses_measured_memory_and_latency(
    peak_memory_bytes, latency_ms, expected
):
    assert classify_resource_tier(peak_memory_bytes, latency_ms) == expected


def test_automatic_selection_uses_profile_then_quality_memory_latency_and_id():
    light_slower = _candidate("model-b", tier_memory=4 * 1024**3, latency_ms=300)
    light_faster = _candidate("model-a", tier_memory=4 * 1024**3, latency_ms=200)
    heavyweight = _candidate("model-z", tier_memory=24 * 1024**3, latency_ms=100)
    planner = LocalModelPlanner([heavyweight, light_slower, light_faster], now=1_100.0)

    balanced = planner.plan(RouteRequest(role="research_chat", modalities=("text",)))
    maximum = planner.plan(
        RouteRequest(
            role="research_chat",
            modalities=("text",),
            compute_profile="maximum_quality",
        )
    )

    assert balanced.selected_model_id == "model-a"
    assert maximum.selected_model_id == "model-z"


def test_override_precedence_blocks_ineligible_override_instead_of_falling_back():
    eligible = _candidate("automatic", tier_memory=4 * 1024**3, latency_ms=100)
    bad_production = _candidate(
        "production", tier_memory=4 * 1024**3, latency_ms=100, readiness="planned"
    )
    planner = LocalModelPlanner([eligible, bad_production], now=1_100.0)

    plan = planner.plan(
        RouteRequest(
            role="research_chat",
            modalities=("text",),
            role_override_model_id="automatic",
            production_override_model_id="production",
        )
    )

    assert plan.outcome == "blocked"
    assert plan.selection_source == "production_override"
    assert plan.selected_model_id is None
    assert "readiness" in (plan.blocked_reason or "").lower()


def test_stale_benchmark_and_no_eligible_route_fail_closed():
    stale = _candidate(
        "stale",
        tier_memory=4 * 1024**3,
        latency_ms=100,
        benchmarked_at=0.0,
    )
    plan = LocalModelPlanner([stale], now=31 * 24 * 60 * 60).plan(
        RouteRequest(role="research_chat", modalities=("text",))
    )

    assert plan.outcome == "blocked"
    assert plan.selected_model_id is None
    assert "benchmark" in (plan.blocked_reason or "").lower()


def test_eligibility_reports_modality_before_a_stale_benchmark():
    wrong_modality_and_stale = _candidate(
        "wrong-modality",
        tier_memory=4 * 1024**3,
        latency_ms=100,
        modalities=("image",),
        benchmarked_at=0.0,
    )

    plan = LocalModelPlanner(
        [wrong_modality_and_stale], now=BENCHMARK_MAX_AGE_SECONDS + 1
    ).plan(RouteRequest(role="research_chat", modalities=("text",)))

    assert plan.outcome == "blocked"
    assert "modality" in (plan.blocked_reason or "").lower()


def test_future_dated_benchmark_fails_closed():
    future_dated = _candidate(
        "future", tier_memory=4 * 1024**3, latency_ms=100, benchmarked_at=2_000.0
    )

    plan = LocalModelPlanner([future_dated], now=1_000.0).plan(
        RouteRequest(role="research_chat")
    )

    assert plan.outcome == "blocked"
    assert "benchmark" in (plan.blocked_reason or "").lower()


def test_escalation_receipt_is_redacted_bounded_and_only_allows_declared_failures():
    first = _candidate("first", tier_memory=4 * 1024**3, latency_ms=100)
    second = _candidate("second", tier_memory=10 * 1024**3, latency_ms=100)
    third = _candidate("third", tier_memory=24 * 1024**3, latency_ms=100)
    planner = LocalModelPlanner([first, second, third], now=1_100.0)
    plan = planner.plan(RouteRequest(role="research_chat", modalities=("text",)))

    escalation = planner.escalation_plan(
        plan,
        reason="confidence_below_threshold",
        bounded_unit_id="unit-7",
    )

    assert escalation.allowed is True
    assert escalation.model_ids == ("second", "third")
    assert escalation.receipt["first_pass_model_id"] == "first"
    assert escalation.receipt["bounded_unit_id"] == "unit-7"
    assert set(escalation.receipt).isdisjoint({"source", "output", "prompt", "path"})

    assert planner.escalation_plan(plan, reason="provider_error").allowed is False


@pytest.mark.parametrize(
    "unsafe_unit_id", ["x" * 129, "raw source\noutput", "../../raw-output"]
)
def test_escalation_omits_unsafe_bounded_unit_ids(unsafe_unit_id):
    first = _candidate("first", tier_memory=4 * 1024**3, latency_ms=100)
    second = _candidate("second", tier_memory=10 * 1024**3, latency_ms=100)
    planner = LocalModelPlanner([first, second], now=1_100.0)
    plan = planner.plan(RouteRequest(role="research_chat"))

    escalation = planner.escalation_plan(
        plan,
        reason="confidence_below_threshold",
        bounded_unit_id=unsafe_unit_id,
    )

    assert escalation.allowed is True
    assert escalation.receipt["bounded_unit_id"] is None
    assert unsafe_unit_id not in repr(escalation.receipt)


def test_escalation_receipt_redacts_an_invalid_reason():
    malicious_reason = "raw source:\nprivate output payload"
    first = _candidate("first", tier_memory=4 * 1024**3, latency_ms=100)
    second = _candidate("second", tier_memory=10 * 1024**3, latency_ms=100)
    planner = LocalModelPlanner([first, second], now=1_100.0)
    plan = planner.plan(RouteRequest(role="research_chat"))

    escalation = planner.escalation_plan(plan, reason=malicious_reason)

    assert escalation.allowed is False
    assert escalation.receipt["reason"] == "rejected_unrecognized_reason"
    assert malicious_reason not in repr(escalation.receipt)
