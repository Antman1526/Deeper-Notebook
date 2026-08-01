"""Pure contracts for verified local-model readiness.

This module deliberately performs no filesystem or runtime I/O.  Discovery
supplies facts and callers can make routing decisions from the returned,
serializable assessment without treating a curated manifest as proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ModelRole = Literal[
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
]
Readiness = Literal[
    "ready_verified",
    "ready_unverified",
    "requires_runtime",
    "runtime_unavailable",
    "installed_unsupported",
    "incomplete",
    "planned",
    "removed",
]
ResourceTier = Literal["light", "standard", "heavyweight"]
ExecutionPolicy = Literal["strict_local", "local_preferred", "custom"]
ComputeProfile = Literal["efficient", "balanced", "maximum_quality"]
ManifestState = Literal["installed", "planned", "removed"]
SelectionSource = Literal["automatic", "role_override", "production_override"]
RouteOutcome = Literal["ready", "blocked", "approval_required"]

# The existing local sidecar probe applies a nine-second per-sidecar bound.
MAX_BOUNDED_HEALTH_LATENCY_MS = 9_000


@dataclass(frozen=True)
class ExternalModelRootTrust:
    """A durable approval for exactly one selected root and resolved target."""

    selected_root_fingerprint: str
    resolved_target_fingerprint: str


@dataclass(frozen=True)
class ModelReadinessEvidence:
    """All facts required to classify one local asset.

    Defaults fail closed.  In particular an inventory/manifest row has no
    health, accepted benchmark, or current-runtime identity proof by default.
    """

    file_complete: bool = False
    supported_runtime: bool = False
    runtime_configured: bool = True
    manifest_state: ManifestState = "installed"
    runtime_identity_matches: bool = False
    health_checked: bool = False
    health_healthy: bool = False
    health_latency_ms: int | None = None
    benchmark_accepted: bool = False
    symlink_trusted: bool = True


@dataclass(frozen=True)
class ModelReadinessAssessment:
    readiness: Readiness
    readiness_reason: str
    route_eligible: bool


@dataclass(frozen=True)
class LocalModelRouteCandidate:
    """Redacted facts a pure local planner needs about one model.

    Inventory and benchmark collection own discovery and measurement.  This
    contract deliberately contains neither a canonical path nor any provider
    configuration, prompt, source, or generated response.
    """

    model_id: str
    provider: str
    fingerprint: str
    modalities: tuple[Literal["text", "image", "audio"], ...]
    accepted_roles: tuple[ModelRole, ...]
    context_tokens: int
    supports_structured_output: bool
    readiness: Readiness
    health_healthy: bool
    accepted_quality: float
    benchmarked_at: float | None
    peak_memory_bytes: int
    latency_ms: int
    is_local: bool = True


@dataclass(frozen=True)
class RouteRequest:
    """A bounded, local-only request for a model route."""

    role: ModelRole
    required_context_tokens: int = 0
    modalities: tuple[Literal["text", "image", "audio"], ...] = ("text",)
    requires_structured_output: bool = False
    execution_policy: ExecutionPolicy = "strict_local"
    compute_profile: ComputeProfile = "balanced"
    role_override_model_id: str | None = None
    production_override_model_id: str | None = None
    memory_reservation_bytes: int = 0


@dataclass(frozen=True)
class ModelRoutePlan:
    """Explainable route result with only redacted selection facts."""

    role: ModelRole
    outcome: RouteOutcome
    selected_model_id: str | None
    selected_provider: str | None
    resource_tier: ResourceTier | None
    selection_source: SelectionSource | None
    route_reason: str
    escalation_model_ids: tuple[str, ...] = ()
    blocked_reason: str | None = None
    selected_fingerprint: str | None = None
    selected_measurements: tuple[tuple[str, int | float], ...] = ()

    def receipt(self) -> dict[str, object]:
        """Return the redacted, serializable route evidence for UI/audit use."""
        return {
            "role": self.role,
            "outcome": self.outcome,
            "selected_model_id": self.selected_model_id,
            "selected_provider": self.selected_provider,
            "resource_tier": self.resource_tier,
            "selection_source": self.selection_source,
            "route_reason": self.route_reason,
            "escalation_model_ids": list(self.escalation_model_ids),
            "blocked_reason": self.blocked_reason,
            "selected_fingerprint": self.selected_fingerprint,
            "selected_measurements": dict(self.selected_measurements),
        }


@dataclass(frozen=True)
class EscalationPlan:
    """A bounded higher-tier retry plan with a privacy-safe first-pass receipt."""

    allowed: bool
    model_ids: tuple[str, ...]
    reason: str
    receipt: dict[str, object]


def classify_model_readiness(
    evidence: ModelReadinessEvidence,
) -> ModelReadinessAssessment:
    """Classify a model from supplied facts, without probing or mutation.

    The ordering is intentional: unavailable inventory states are visible
    before runtime proof, while the only route-eligible state requires every
    independent physical, runtime, health, benchmark, and symlink gate.
    """
    if evidence.manifest_state == "planned":
        return _blocked("planned", "Model is planned and has not been installed.")
    if evidence.manifest_state == "removed":
        return _blocked("removed", "Model is marked removed and cannot be routed.")
    if not evidence.file_complete:
        return _blocked(
            "incomplete", "Model files are incomplete or missing required assets."
        )
    if not evidence.supported_runtime:
        return _blocked(
            "installed_unsupported",
            "Model is installed but no supported local runtime is configured.",
        )
    if not evidence.runtime_configured:
        return _blocked(
            "requires_runtime",
            "Model needs a configured supported local runtime.",
        )
    if not evidence.symlink_trusted:
        return _blocked(
            "ready_unverified",
            "External model symlink is not trusted for this selected root.",
        )
    if not evidence.runtime_identity_matches:
        return _blocked(
            "runtime_unavailable",
            "Current local runtime identity does not match this model.",
        )
    if not _has_bounded_healthy_probe(evidence):
        return _blocked(
            "ready_unverified",
            "Model has no bounded healthy local runtime probe.",
        )
    if not evidence.benchmark_accepted:
        return _blocked(
            "ready_unverified",
            "Model has no accepted local benchmark result.",
        )
    return ModelReadinessAssessment(
        readiness="ready_verified",
        readiness_reason="Complete files, matching local runtime, bounded health, and accepted benchmark verified.",
        route_eligible=True,
    )


def trust_record_matches(
    record: ExternalModelRootTrust,
    *,
    selected_root_fingerprint: str,
    resolved_target_fingerprint: str,
) -> bool:
    """Return true only for the exact selected-root and target identity pair."""
    return (
        bool(selected_root_fingerprint)
        and bool(resolved_target_fingerprint)
        and record.selected_root_fingerprint == selected_root_fingerprint
        and record.resolved_target_fingerprint == resolved_target_fingerprint
    )


def _has_bounded_healthy_probe(evidence: ModelReadinessEvidence) -> bool:
    return (
        evidence.health_checked
        and evidence.health_healthy
        and isinstance(evidence.health_latency_ms, int)
        and 0 <= evidence.health_latency_ms <= MAX_BOUNDED_HEALTH_LATENCY_MS
    )


def _blocked(readiness: Readiness, reason: str) -> ModelReadinessAssessment:
    return ModelReadinessAssessment(
        readiness=readiness,
        readiness_reason=reason,
        route_eligible=False,
    )
