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

import asyncio
import os
import time
from pathlib import Path

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


async def _persist_route_receipt(receipt: dict[str, object]) -> None:
    from open_notebook.ai.models import persist_model_route_receipt

    await persist_model_route_receipt(receipt)


def _is_local(provider: str | None) -> bool:
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


async def find_local_language_model():
    """Best local fallback Model record, or None.

    Preference order (spec §3): the DefaultModels chat slot when it points
    at a local-provider model (the user's deliberate choice), else the
    first registered local-provider language model, name-sorted for
    determinism (mirrors the assigner's deterministic tie-breaks).
    """
    route, registered_models = await find_measured_local_language_route()
    if route is not None:
        selected = next(
            (
                model
                for model in registered_models
                if str(getattr(model, "id", "") or "") == route.selected_model_id
            ),
            None,
        )
        if selected is not None:
            return selected

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
            m
            for m in await _get_language_models("language")
            if _is_local(getattr(m, "provider", None))
        ]
        candidates.sort(key=lambda m: (getattr(m, "name", "") or "").lower())
        return candidates[0] if candidates else None
    except Exception as exc:
        logger.debug(f"v0.8.68 offline-gate: local-model query failed ({exc!r})")
        return None


async def find_measured_local_language_route(
    *,
    role: str = "chat",
    required_context_tokens: int = 0,
    requires_structured_output: bool = False,
    health_by_model_id: dict[str, bool] | None = None,
    explicit_model_id: str | None = None,
    forced_offline: bool = True,
):
    """Resolve a fresh, measured local route without probing a cloud provider.

    The persisted benchmark file has no per-row completion timestamp in older
    releases. Its modification time is therefore the conservative common age
    for those rows; unreadable or missing history is simply ineligible.
    """
    try:
        from open_notebook.local_models.benchmarks import (
            benchmark_history_path,
            load_benchmark_history,
        )
        from open_notebook.local_models.inventory import enumerate_models
        from open_notebook.local_models.role_routing import select_measured_model_route

        model_dir = _configured_local_model_dir()
        if model_dir is None:
            return None, []
        history_path = benchmark_history_path(model_dir)
        try:
            benchmarked_at = history_path.stat().st_mtime
        except OSError:
            return None, []
        registered_models = await _get_language_models("language")
        local_models = await asyncio.to_thread(enumerate_models, model_dir)
        route = select_measured_model_route(
            role,
            benchmark_results=load_benchmark_history(model_dir),
            registered_models=registered_models,
            local_models=local_models,
            health_by_model_id=health_by_model_id,
            required_context_tokens=required_context_tokens,
            requires_structured_output=requires_structured_output,
            benchmarked_at=benchmarked_at,
            now=time.time(),
            explicit_model_id=explicit_model_id,
            forced_offline=forced_offline,
        )
        return route, registered_models
    except Exception as exc:
        logger.debug(f"quality-aware local route unavailable ({exc!r})")
        return None, []


def _configured_local_model_dir() -> Path | None:
    raw = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(Path(home) / "Desktop" / "AI_Models") if home else ""
    if not raw:
        return None
    model_dir = Path(raw)
    return model_dir if model_dir.exists() and model_dir.is_dir() else None


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

    (
        measured_route,
        measured_registered_models,
    ) = await find_measured_local_language_route(
        forced_offline=state.forced_offline,
    )
    fallback = None
    if measured_route is not None:
        fallback = next(
            (
                model
                for model in measured_registered_models
                if str(getattr(model, "id", "") or "")
                == measured_route.selected_model_id
            ),
            None,
        )
    if fallback is None:
        fallback = await find_local_language_model()
    if fallback is None:
        raise ConfigurationError(
            "You're offline and no local model is installed. Connect to the "
            "internet, or add a local model (Settings → Models) so chat can "
            "work offline."
        )
    reason = "forced-offline" if state.forced_offline else "offline"
    logger.info(f"v0.8.68 offline-gate: {candidate_id} → {fallback.id} ({reason})")
    if fallback_out is not None:
        fallback_out.update(
            {
                "offline_fallback": True,
                "from_model_id": candidate_id,
                "to_model_id": fallback.id,
                "to_model_name": getattr(fallback, "name", None),
                "reason": reason,
            }
        )
    if measured_route is not None:
        try:
            receipt = measured_route.receipt()
            receipt["reason"] = f"{reason}; {receipt['reason']}"
            await _persist_route_receipt(receipt)
        except Exception as exc:
            # Route audit storage must not turn a working offline fallback
            # into a failed chat turn.
            logger.debug(f"Could not persist local route receipt ({exc!r})")
    return fallback.id
