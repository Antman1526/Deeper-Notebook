"""Phase 3 Task 11 — pure provider-router.

Decides whether a chat turn goes to the local llama-cpp sidecar
or the cloud provider, based on content size, local-sidecar
health, n_ctx headroom, and user preference. Pure function so it's
trivially testable and re-callable from any callsite (chat node,
ask node, future tools).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    """Immutable decision: which model to use and why."""

    model_id: str
    reason: str


def pick_provider(
    *,
    content_tokens: int,
    local_chat_healthy: bool,
    local_chat_n_ctx: int,
    cloud_model_id: str | None,
    local_model_id: str | None,
    default_provider: str = "auto",
    reply_headroom_tokens: int = 1000,
) -> ModelChoice:
    """Route a chat turn to local or cloud based on health, size, and user preference.

    Pure function — no I/O, no state. All inputs come in as kwargs.

    Args:
        content_tokens: Estimated token count of the prompt + context.
        local_chat_healthy: Whether the local llama-cpp sidecar is responding.
        local_chat_n_ctx: Context window size of the local model.
        cloud_model_id: Cloud provider model ID (e.g., "model:gpt-4o") or None.
        local_model_id: Local model ID (e.g., "model:hermes-3") or None.
        default_provider: User preference — "auto", "local", or "cloud".

    Returns:
        ModelChoice(model_id, reason) — the selected model and routing justification.

    Raises:
        ValueError: If no model is available (both local and cloud are None/unconfigured).

    Routing logic (in order):
        1. If user explicitly forces cloud/local, honor it (and fall back gracefully
           if the forced model isn't available).
        2. Auto mode: Prefer local if healthy AND content_tokens + 1k headroom < n_ctx.
        3. Fall back to cloud if auto-route can't use local.
        4. Fall back to local if cloud isn't configured and auto-route oversized.
        5. Raise if both are unavailable.
    """
    # Step 1: Explicit user override wins over auto-routing.
    if default_provider == "cloud":
        if cloud_model_id:
            return ModelChoice(cloud_model_id, "user-forced cloud")
        # Cloud forced but not available — fall through to step 3+ to auto-choose
    if default_provider == "local":
        if local_model_id:
            return ModelChoice(local_model_id, "user-forced local")
        # Local forced but not available — raise (user's explicit choice can't be honored)
        if not cloud_model_id:
            raise ValueError("No model available — neither local nor cloud")
        # If cloud is available, cloud is not really "forced", so we don't hit this.
        # But for clarity: if local is forced and unavailable and we have cloud,
        # we still raise (user explicitly said local).
        raise ValueError("No model available — neither local nor cloud")

    # Step 2: Auto mode — prefer local when healthy AND content fits with enough
    # headroom for the reply + system prompt + tool schemas.
    # v0.8.66 (audit A-6/A-7) — `reply_headroom_tokens` now reflects the ACTUAL
    # reply reservation (callers pass max_tokens, default 8192) plus a margin for
    # the system prompt + tool schemas that `content_tokens` (content-only)
    # omits. Pre-v0.8.66 this was a flat 1000, so a ~(n_ctx-1k) prompt routed
    # local then overflowed once the 8192-token reply was reserved → llama.cpp
    # 400 context_length_exceeded. The default stays 1024 for direct/legacy
    # callers; the chat caller passes the real reservation.
    if (
        local_chat_healthy
        and local_model_id
        and content_tokens <= local_chat_n_ctx - reply_headroom_tokens
    ):
        return ModelChoice(local_model_id, "local: healthy + fits in n_ctx")

    # Step 3: Cloud fallback — either oversized content or local unhealthy.
    if cloud_model_id:
        if local_chat_healthy:
            reason = (
                f"cloud: content {content_tokens}t exceeds n_ctx {local_chat_n_ctx}t"
            )
        else:
            reason = "cloud: local unavailable"
        return ModelChoice(cloud_model_id, reason)

    # Step 4: Best-effort local even when too big — the llama-cpp server
    # returns its own 400 on truly oversized prompts so the user gets
    # a specific error rather than this router opaquely choosing.
    if local_model_id:
        return ModelChoice(
            local_model_id,
            "local fallback (no cloud configured)",
        )

    # Step 5: No model available — impossible state.
    raise ValueError("No model available — neither local nor cloud")
