"""Pure, deterministic planning for the smallest capable local model route."""

from __future__ import annotations

import re
import time
from typing import Iterable

from deeper_notebook.local_models.contracts import (
    EscalationPlan,
    LocalModelRouteCandidate,
    ModelRoutePlan,
    ResourceTier,
    RouteRequest,
    SelectionSource,
)

BENCHMARK_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_GIB = 1024**3
_KNOWN_ROLES: frozenset[str] = frozenset(
    {
        "research_chat",
        "evidence_extraction",
        "claim_verification",
        "editorial_writing",
        "embedding_retrieval",
        "vision_analysis",
        "code_data_analysis",
        "podcast_outline",
        "podcast_script",
        "speech_to_text",
        "text_to_speech",
    }
)
_PROFILE_TIER_ORDER: dict[str, tuple[ResourceTier, ...]] = {
    # Balanced is deliberately smallest-capable: it never promotes a model
    # merely because it is larger. Quality breaks ties within a measured tier.
    "efficient": ("light", "standard", "heavyweight"),
    "balanced": ("light", "standard", "heavyweight"),
    "maximum_quality": ("heavyweight", "standard", "light"),
}
_ALLOWED_ESCALATION_REASONS = frozenset(
    {
        "schema_invalidity",
        "confidence_below_threshold",
        "insufficient_evidence_coverage",
        "contradiction_failure",
        "declared_task_complexity",
    }
)
_SAFE_BOUNDED_UNIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def classify_resource_tier(peak_memory_bytes: int, latency_ms: int) -> ResourceTier:
    """Classify from actual measurements, not model name or parameter guesses."""
    memory = max(0, int(peak_memory_bytes))
    latency = max(0, int(latency_ms))
    if memory <= 8 * _GIB and latency <= 2_500:
        return "light"
    if memory <= 16 * _GIB and latency <= 4_500:
        return "standard"
    return "heavyweight"


class LocalModelPlanner:
    """Plan routes without filesystem, runtime, transport, or provider effects."""

    def __init__(
        self,
        candidates: Iterable[LocalModelRouteCandidate],
        *,
        available_memory_bytes: int | None = None,
        now: float | None = None,
    ) -> None:
        self._candidates = tuple(candidates)
        self._by_id = {candidate.model_id: candidate for candidate in self._candidates}
        self._available_memory_bytes = available_memory_bytes
        self._now = time.time() if now is None else now
        self._plan_requests: dict[int, RouteRequest] = {}

    def plan(self, request: RouteRequest) -> ModelRoutePlan:
        """Return one local route or a fail-closed explanation.

        An explicit override is a policy decision, not a preference hint: once
        supplied it is evaluated alone and a failed gate is returned unchanged.
        """
        source, override_id = self._override(request)
        if override_id is not None:
            candidate = self._by_id.get(override_id)
            if candidate is None:
                plan = self._blocked(
                    request,
                    source,
                    "Requested override is not an available local route candidate.",
                )
            else:
                failure = self._eligibility_failure(candidate, request)
                plan = (
                    self._blocked(request, source, failure)
                    if failure
                    else self._ready(candidate, request, source)
                )
            self._plan_requests[id(plan)] = request
            return plan

        eligible: list[LocalModelRouteCandidate] = []
        failures: list[str] = []
        for candidate in self._candidates:
            failure = self._eligibility_failure(candidate, request)
            if failure is None:
                eligible.append(candidate)
            else:
                failures.append(failure)
        if not eligible:
            plan = self._blocked(
                request,
                "automatic",
                _no_eligible_reason(failures),
            )
            self._plan_requests[id(plan)] = request
            return plan

        eligible.sort(
            key=lambda candidate: self._automatic_sort_key(candidate, request)
        )
        plan = self._ready(eligible[0], request, "automatic", eligible)
        self._plan_requests[id(plan)] = request
        return plan

    def escalation_plan(
        self,
        first_pass: ModelRoutePlan,
        *,
        reason: str,
        bounded_unit_id: str | None = None,
    ) -> EscalationPlan:
        """Return at most two higher-tier candidates for a declared quality failure."""
        request = self._plan_requests.get(id(first_pass))
        selected = self._by_id.get(first_pass.selected_model_id or "")
        safe_unit_id = _safe_bounded_unit_id(bounded_unit_id)
        receipt = {
            "first_pass_model_id": first_pass.selected_model_id,
            "first_pass_fingerprint": first_pass.selected_fingerprint,
            "first_pass_measurements": dict(first_pass.selected_measurements),
            "reason": reason,
            "bounded_unit_id": safe_unit_id,
        }
        if reason not in _ALLOWED_ESCALATION_REASONS:
            return EscalationPlan(
                allowed=False,
                model_ids=(),
                reason="Escalation reason is not permitted by local routing policy.",
                receipt=receipt,
            )
        if request is None or selected is None or first_pass.outcome != "ready":
            return EscalationPlan(
                allowed=False,
                model_ids=(),
                reason="A ready first-pass local route is required for escalation.",
                receipt=receipt,
            )

        current_rank = _tier_rank(
            classify_resource_tier(selected.peak_memory_bytes, selected.latency_ms)
        )
        higher = [
            candidate
            for candidate in self._candidates
            if _tier_rank(
                classify_resource_tier(
                    candidate.peak_memory_bytes, candidate.latency_ms
                )
            )
            > current_rank
            and self._eligibility_failure(candidate, request) is None
        ]
        higher.sort(
            key=lambda candidate: (
                _tier_rank(
                    classify_resource_tier(
                        candidate.peak_memory_bytes, candidate.latency_ms
                    )
                ),
                -candidate.accepted_quality,
                candidate.peak_memory_bytes,
                candidate.latency_ms,
                candidate.model_id,
            )
        )
        model_ids = tuple(candidate.model_id for candidate in higher[:2])
        if not model_ids:
            return EscalationPlan(
                allowed=False,
                model_ids=(),
                reason="No eligible higher-tier local model is available.",
                receipt=receipt,
            )
        return EscalationPlan(
            allowed=True,
            model_ids=model_ids,
            reason="Bounded higher-tier local escalation is permitted.",
            receipt=receipt,
        )

    def _ready(
        self,
        candidate: LocalModelRouteCandidate,
        request: RouteRequest,
        source: SelectionSource,
        eligible: Iterable[LocalModelRouteCandidate] | None = None,
    ) -> ModelRoutePlan:
        tier = classify_resource_tier(candidate.peak_memory_bytes, candidate.latency_ms)
        escalation = ()
        if eligible is not None:
            current_rank = _tier_rank(tier)
            escalation = tuple(
                other.model_id
                for other in eligible
                if _tier_rank(
                    classify_resource_tier(other.peak_memory_bytes, other.latency_ms)
                )
                > current_rank
            )[:2]
        return ModelRoutePlan(
            role=request.role,
            outcome="ready",
            selected_model_id=candidate.model_id,
            selected_provider=candidate.provider,
            resource_tier=tier,
            selection_source=source,
            route_reason=(
                f"{source.replace('_', ' ')} selected the {tier} verified local "
                "candidate after all route gates."
            ),
            escalation_model_ids=escalation,
            selected_fingerprint=candidate.fingerprint,
            selected_measurements=(
                ("accepted_quality", candidate.accepted_quality),
                ("peak_memory_bytes", candidate.peak_memory_bytes),
                ("latency_ms", candidate.latency_ms),
            ),
        )

    def _blocked(
        self, request: RouteRequest, source: SelectionSource, reason: str
    ) -> ModelRoutePlan:
        return ModelRoutePlan(
            role=request.role,
            outcome="blocked",
            selected_model_id=None,
            selected_provider=None,
            resource_tier=None,
            selection_source=source,
            route_reason="No eligible local route was selected.",
            blocked_reason=reason,
        )

    def _override(self, request: RouteRequest) -> tuple[SelectionSource, str | None]:
        if request.production_override_model_id:
            return "production_override", request.production_override_model_id
        if request.role_override_model_id:
            return "role_override", request.role_override_model_id
        return "automatic", None

    def _automatic_sort_key(
        self, candidate: LocalModelRouteCandidate, request: RouteRequest
    ) -> tuple[int, float, int, int, str]:
        order = _PROFILE_TIER_ORDER.get(
            request.compute_profile, _PROFILE_TIER_ORDER["balanced"]
        )
        tier = classify_resource_tier(candidate.peak_memory_bytes, candidate.latency_ms)
        return (
            order.index(tier),
            -candidate.accepted_quality,
            candidate.peak_memory_bytes,
            candidate.latency_ms,
            candidate.model_id,
        )

    def _eligibility_failure(
        self, candidate: LocalModelRouteCandidate, request: RouteRequest
    ) -> str | None:
        # Ordering is contractual; preserve it when adding any future gate.
        if candidate.readiness != "ready_verified":
            return f"Readiness gate failed: {candidate.readiness}."
        if not set(request.modalities).issubset(candidate.modalities):
            return "Modality gate failed."
        if (
            request.role not in _KNOWN_ROLES
            or request.role not in candidate.accepted_roles
        ):
            return "Role acceptance gate failed."
        if candidate.context_tokens < request.required_context_tokens:
            return "Context gate failed."
        if (
            request.requires_structured_output
            and not candidate.supports_structured_output
        ):
            return "Structured output gate failed."
        if not candidate.health_healthy:
            return "Health gate failed."
        if (
            self._available_memory_bytes is not None
            and candidate.peak_memory_bytes + max(0, request.memory_reservation_bytes)
            > self._available_memory_bytes
        ):
            return "Memory reservation gate failed."
        if not candidate.is_local:
            return f"Execution policy gate failed: {request.execution_policy} permits no cloud fallback."
        if candidate.benchmarked_at is None:
            return "Readiness gate failed: accepted benchmark is missing or stale."
        benchmark_age = self._now - candidate.benchmarked_at
        if not 0 <= benchmark_age <= BENCHMARK_MAX_AGE_SECONDS:
            return "Readiness gate failed: accepted benchmark is missing or stale."
        if candidate.accepted_quality <= 0:
            return "Readiness gate failed: accepted benchmark quality is missing."
        return None


def plan_model_route(
    candidates: Iterable[LocalModelRouteCandidate],
    request: RouteRequest,
    **kwargs: object,
) -> ModelRoutePlan:
    """Convenience function for callers that do not need escalation state."""
    return LocalModelPlanner(candidates, **kwargs).plan(request)


def _tier_rank(tier: ResourceTier) -> int:
    return {"light": 0, "standard": 1, "heavyweight": 2}[tier]


def _no_eligible_reason(failures: list[str]) -> str:
    if not failures:
        return "No local route candidates are available."
    return sorted(failures)[0]


def _safe_bounded_unit_id(value: object) -> str | None:
    """Keep only a short opaque identifier; never receipt arbitrary work text."""
    if not isinstance(value, str) or _SAFE_BOUNDED_UNIT_ID.fullmatch(value) is None:
        return None
    return value
