"""v0.8.68 — offline gate for language-model provisioning.

Sits in provision_langchain_model's resolution path (the funnel every
LangGraph workflow uses). When the machine is offline (real probe or the
user's Offline-mode toggle) and the candidate model's provider is a cloud
provider, the gate substitutes the best registered LOCAL language model so
the turn answers instantly instead of hanging to the provider timeout.

Local providers (never gated): ollama and openai_compatible — in this
desktop app both point at machine-local sidecars (the llama.cpp chat
sidecar registers as openai_compatible; see desktop/auto_register/).
Everything else (openai, anthropic, google, groq, mistral, deepseek, xai,
openrouter, azure, vertex, ...) is treated as cloud.

Fail-open by design: any internal error (DB hiccup loading the Model
record, defaults fetch failure) returns the original candidate — the gate
must never be the thing that breaks a chat turn. The ONLY raise is
ConfigurationError when we are offline, the candidate is cloud, and no
local model exists: that turn was going to fail anyway, so fail fast with
an actionable message instead of a 300s hang.
"""
from __future__ import annotations

from loguru import logger

from open_notebook.exceptions import ConfigurationError
from open_notebook.health.network import get_network_state_with_settings

LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai_compatible"})


# --- thin indirections so tests can patch without touching domain models ---

async def _get_model_record(model_id: str):
    from open_notebook.ai.models import Model
    return await Model.get(model_id)


async def _get_defaults():
    from open_notebook.ai.models import model_manager
    return await model_manager.get_defaults()


async def _get_language_models(model_type: str):
    from open_notebook.ai.models import Model
    return await Model.get_models_by_type(model_type)


def _is_local(provider: str | None) -> bool:
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


async def find_local_language_model():
    """Best local fallback Model record, or None.

    Preference order (spec §3): the DefaultModels chat slot when it points
    at a local-provider model (the user's deliberate choice), else the
    first registered local-provider language model, name-sorted for
    determinism (mirrors the assigner's deterministic tie-breaks).
    """
    try:
        defaults = await _get_defaults()
        chat_id = getattr(defaults, "default_chat_model", None)
        if chat_id:
            rec = await _get_model_record(chat_id)
            if rec is not None and _is_local(getattr(rec, "provider", None)):
                return rec
    except Exception as exc:
        logger.debug(f"v0.8.68 offline-gate: defaults lookup failed ({exc!r})")

    try:
        candidates = [
            m for m in await _get_language_models("language")
            if _is_local(getattr(m, "provider", None))
        ]
        candidates.sort(key=lambda m: (getattr(m, "name", "") or "").lower())
        return candidates[0] if candidates else None
    except Exception as exc:
        logger.debug(f"v0.8.68 offline-gate: local-model query failed ({exc!r})")
        return None


async def gate_language_model_id(
    candidate_id: str | None,
    *,
    fallback_out: dict | None = None,
) -> str | None:
    """Return candidate_id, or a substituted local model id when offline.

    Ordering note: the Model record is loaded BEFORE the network state is
    consulted, so local-provider candidates never pay the probe cost —
    a fully-local setup runs zero probes.
    """
    if not candidate_id:
        return candidate_id

    try:
        record = await _get_model_record(candidate_id)
    except Exception as exc:
        logger.debug(
            f"v0.8.68 offline-gate: could not load {candidate_id} ({exc!r}) — "
            f"passing through (provisioning will surface the real error)"
        )
        return candidate_id
    if record is None:
        return candidate_id
    if getattr(record, "type", None) != "language":
        return candidate_id  # spec non-goal: embeddings/TTS/STT not gated
    if _is_local(getattr(record, "provider", None)):
        return candidate_id

    state = await get_network_state_with_settings()
    if state.status != "offline":  # online AND unknown both pass (spec §1)
        return candidate_id

    fallback = await find_local_language_model()
    if fallback is None:
        raise ConfigurationError(
            "You're offline and no local model is installed. Connect to the "
            "internet, or add a local model (Settings → Models) so chat can "
            "work offline."
        )
    reason = "forced-offline" if state.forced_offline else "offline"
    logger.info(
        f"v0.8.68 offline-gate: {candidate_id} → {fallback.id} ({reason})"
    )
    if fallback_out is not None:
        fallback_out.update({
            "offline_fallback": True,
            "from_model_id": candidate_id,
            "to_model_id": fallback.id,
            "to_model_name": getattr(fallback, "name", None),
            "reason": reason,
        })
    return fallback.id
