import asyncio
import os
import time
from pathlib import Path

from esperanto import LanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from deeper_notebook.ai.models import model_manager
from deeper_notebook.ai.offline_gate import gate_language_model_id
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import ConfigurationError
from deeper_notebook.utils import token_count

# v0.8.0 — TTL cache so smart routing doesn't add 5-10s per chat turn.
_HEALTH_CACHE_TTL_S = 30
_health_cache: "tuple[float, dict[str, bool]] | None" = None
# v0.8.35 — single-flight lock for cache-miss probing. Without this,
# N concurrent chat requests hitting the same TTL-boundary all entered
# the probe branch independently and ran `await asyncio.to_thread(
# probe_all_local_models, ...)` in parallel — N × ~9s of duplicate work
# every cache window. Lazy-constructed in _get_health_cache_lock() so
# module import doesn't require a running event loop.
_health_cache_lock: "asyncio.Lock | None" = None


def _get_health_cache_lock() -> asyncio.Lock:
    """v0.8.35 — lazily construct the cache-miss lock the first time
    we need it. asyncio.Lock() in modern Python doesn't bind to a
    specific event loop at construct time, but lazy init keeps imports
    side-effect-free and mirrors the get_async_graph() pattern in
    deeper_notebook/graphs/chat.py for the same reason."""
    global _health_cache_lock
    if _health_cache_lock is None:
        _health_cache_lock = asyncio.Lock()
    return _health_cache_lock


def _truthy_env(name: str) -> bool:
    """Return True when env var is set to a truthy value (1/true/yes/on)."""
    return resolve_env(name, "").lower() in ("1", "true", "yes", "on")


async def _local_chat_healthy_cached(model_name: str = "Local GGUF (llama.cpp)") -> bool:
    """v0.8.0 — TTL-cached health lookup for the chat sidecar.

    Reads the sidecar base URL from DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL (set by
    desktop/app.py _phase_auto_register at launch). If the env var is unset the
    probe has no target and returns False immediately — this is the safe
    "no local model configured" path.

    The TTL (30s) prevents calling probe_all_local_models on every chat turn;
    the probe itself has a 5s read-timeout so without caching it would add
    5-10s of blocking latency before every model invocation.

    v0.8.20 CRITICAL — was sync, called from the async smart-router path
    in `provision_langchain_chat_model`. The inner `probe_all_local_models`
    drives `httpx.Client.get()` synchronously with up to a 9s structured
    timeout (connect=2.0, read=5.0, write=2.0, pool=2.0). Inside an
    async FastAPI request that blocks the WHOLE event loop — every other
    in-flight request (chat streams, SSE polls, the launcher's status
    poll, the frontend's 30s health badge poll) stalls for up to 9s
    every cache-miss tick. We now `await asyncio.to_thread(...)` so the
    blocking probe lands on the default executor and the event loop
    keeps serving everyone else. Sync callers (desktop/app.py launcher
    startup) keep using `probe_all_local_models` directly — they're not
    racing the event loop.
    """
    global _health_cache
    now = time.monotonic()
    # v0.8.35 — fast path: cache hit. Read outside the lock so cache
    # hits never serialize on the lock acquisition (every chat turn
    # would otherwise pay lock-acquire latency, killing the point of
    # the TTL cache).
    if _health_cache is not None and now - _health_cache[0] < _HEALTH_CACHE_TTL_S:
        return _health_cache[1].get(model_name, False)

    # v0.8.35 — slow path: single-flight cache-miss. Before the lock,
    # N concurrent callers at a TTL boundary each ran the probe
    # independently. Now the first acquirer probes; the others wait
    # and re-check the cache under the lock (the cache was just
    # populated by the leader → they return its value without
    # probing).
    async with _get_health_cache_lock():
        now = time.monotonic()
        if _health_cache is not None and now - _health_cache[0] < _HEALTH_CACHE_TTL_S:
            return _health_cache[1].get(model_name, False)

        try:
            from deeper_notebook.health.local_models import probe_all_local_models

            # Desktop bootstrap writes this env var when the chat sidecar
            # registers its port (see desktop/app.py _phase_auto_register).
            base_url = resolve_env("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", "")
            creds: list[dict] = []
            if base_url:
                creds.append(
                    {
                        "name": model_name,
                        "kind": "openai_compatible",
                        "base_url": base_url,
                    }
                )
            # v0.8.20 — push the sync httpx call onto a worker thread so
            # the FastAPI event loop stays responsive during the probe.
            results = (
                await asyncio.to_thread(probe_all_local_models, creds)
                if creds
                else []
            )
            _health_cache = (
                now,
                {r["name"]: r["status"] == "healthy" for r in results},
            )
        except Exception:
            # v0.8.0 — probe failure is non-fatal; treat as unhealthy so the
            # router falls through to cloud and the user still gets a response.
            _health_cache = (now, {})
    return _health_cache[1].get(model_name, False)


def _configured_local_model_dir() -> Path | None:
    raw = (
        resolve_env("DEEPER_NOTEBOOK_MODEL_DIR")
        or resolve_env("DEEPER_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(Path(home) / "Desktop" / "AI_Models") if home else ""
    if not raw:
        return None
    model_dir = Path(raw)
    return model_dir if model_dir.exists() and model_dir.is_dir() else None


async def _measured_local_chat_model_id() -> str | None:
    """Best measured local chat model id, when benchmark history can prove one."""
    model_dir = _configured_local_model_dir()
    if model_dir is None:
        return None
    try:
        from deeper_notebook.local_models.benchmarks import resolve_measured_model_id

        return await resolve_measured_model_id(model_dir, "chat")
    except Exception as exc:
        logger.debug(f"Measured local chat model lookup skipped: {exc}")
        return None


async def provision_langchain_chat_model(
    content: str,
    *,
    selection_out: "dict | None" = None,
    privacy_gate_bypass: bool = False,
    fallback_out: "dict | None" = None,
    **kwargs,
) -> BaseChatModel:
    """v0.8.0 — Smart-routed chat provisioning.

    Wraps provision_langchain_model with pick_provider when
    DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT is truthy (1/true/yes/on).
    Falls back to the plain default-chat path otherwise so the
    change is opt-in and backward-compatible.

    Env knobs (all optional):
      DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT      — enable smart routing (default: off)
      DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID  — SurrealDB model ID for local chat
      DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID  — SurrealDB model ID for cloud chat
      DEEPER_NOTEBOOK_LOCAL_N_CTX          — local context window (default: 32768)
      DEEPER_NOTEBOOK_CHAT_PROVIDER        — auto | local | cloud (default: auto)
      DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL  — sidecar base URL for health probe

    Deprecated aliases accepted during migration:
      DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT, DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID,
      DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID, DEEPER_NOTEBOOK_LOCAL_N_CTX,
      DEEPER_NOTEBOOK_CHAT_PROVIDER, and DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL.
      The DEEPER_NOTEBOOK_* spellings for registered short settings, including
      DEEPER_NOTEBOOK_CHAT_LLM_CTX, are also deprecated aliases. Canonical
      DEEPER_NOTEBOOK_* variables always win.

    v0.8.1 — optional `selection_out` dict that, when smart routing is
    enabled, is populated with `selected_provider` ("local"/"cloud") and
    `selected_model_id` (the SurrealDB model ID actually used). The chat-
    graph node passes a dict here so the /chat/execute response can carry
    the routing decision back to clients (replaces the v0.8.0 "manual
    eyeball check" workaround in scripts/verify-chat-platform.sh).
    """
    # v0.8.37 — UI toggle takes effect when the env var is unset. Env var
    # precedence preserved for back-compat + ops overrides: if an operator
    # set DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT explicitly (even to "0"), respect it.
    # Otherwise consult DefaultModels.auto_route_enabled (the new Settings
    # toggle). Net effect: power-users keep their env-driven setup;
    # UI-driven users get a click-to-enable workflow.
    env_explicit = resolve_env("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT", "").strip()
    if env_explicit:
        smart_routing_on = _truthy_env("DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT")
    else:
        try:
            defaults_for_toggle = await model_manager.get_defaults()
            smart_routing_on = bool(getattr(defaults_for_toggle, "auto_route_enabled", False))
        except Exception:
            # Defaults fetch failure is non-fatal — fall back to OFF
            # (the v0.8.0 default) so we never accidentally route to a
            # half-configured local sidecar.
            smart_routing_on = False

    if not smart_routing_on:
        # Default path — identical to calling provision_langchain_model directly
        # with no model_id so existing DefaultModels config drives selection.
        # No selection_out fields set: the default path has no local/cloud
        # distinction, so leaving the keys absent (caller reads as None) is
        # the truthful answer.
        return await provision_langchain_model(
            content=content,
            model_id=None,
            default_type="chat",
            # v0.8.68 — thread the offline-fallback channel through so the
            # default (non-smart-routed) path reports substitutions too.
            fallback_out=fallback_out,
            **kwargs,
        )

    from deeper_notebook.ai.router import pick_provider

    content_tokens = token_count(content)
    local_model_id = resolve_env("DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID") or None
    if not local_model_id:
        local_model_id = await _measured_local_chat_model_id()
    cloud_model_id = resolve_env("DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID") or None
    if not cloud_model_id:
        # v0.8.1 — use the dedicated auto_route_cloud field, NOT
        # default_chat_model. The v0.8.0 code fell back to default_chat_model
        # which silently routed oversized prompts to a local model when the
        # operator's chat default was itself local and
        # DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID was unset. With auto_route_cloud
        # absent we leave cloud_model_id as None so pick_provider falls through
        # to its "no cloud configured" branch — transparent local-only
        # behavior — instead of masquerading a local model as cloud.
        defaults = await model_manager.get_defaults()
        cloud_model_id = getattr(defaults, "auto_route_cloud", None) or None

    # v0.8.100 — routing between zero candidates is not routing. When neither a
    # local nor a cloud candidate resolves, auto-route fell through to
    # pick_provider's step-5 ValueError ("No model available — neither local nor
    # cloud") and the turn died, even though a perfectly good default_chat_model
    # was configured and the SAME call with the toggle off would have answered.
    #
    # local_model_id comes from DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID or, failing
    # that, _measured_local_chat_model_id() — which only returns a model when
    # BENCHMARK HISTORY proves one. A fresh install has no benchmark history, so
    # a local-only operator who flipped the Settings toggle got a hard failure on
    # every chat turn, with an error message naming neither the toggle nor the
    # missing benchmark. That is the whole defect.
    #
    # Degrade to the default path rather than inventing a candidate. Assigning
    # default_chat_model to local_model_id is the tempting one-liner and it is
    # wrong: the privacy gate uses local_model_id as its "safe to keep on-device"
    # reroute target, so mislabeling a cloud default as local would let the gate
    # send secrets TO the cloud while reporting them kept on-device. Delegating
    # instead reproduces the toggle-off path exactly — the documented, tested
    # one. That path does not run the privacy gate; unchanged from today, and
    # with no candidates the gate has no reroute target regardless.
    if not local_model_id and not cloud_model_id:
        logger.info(
            "auto-route: no local or cloud candidate resolved — using the "
            "configured chat default. Benchmark a local model to give the "
            "router something to route between."
        )
        return await provision_langchain_model(
            content=content,
            model_id=None,
            default_type="chat",
            fallback_out=fallback_out,
            **kwargs,
        )

    # v0.8.5 — read EITHER env var so the router stays in sync with
    # the actual sidecar config. Pre-v0.8.5 this only read
    # DEEPER_NOTEBOOK_LOCAL_N_CTX (default 32768), but the launcher's
    # _spawn_llamacpp_chat reads DEEPER_NOTEBOOK_CHAT_LLM_CTX (also default
    # 32768). Same concept, different names. An operator running
    # DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192 for low-RAM mode would get the sidecar
    # bound at 8k context while the router still thought it had 32k
    # headroom — long prompts got routed to local, llama.cpp returned
    # 400 context_length_exceeded.
    # Precedence: DEEPER_NOTEBOOK_LOCAL_N_CTX wins (explicit router knob),
    # DEEPER_NOTEBOOK_CHAT_LLM_CTX is the v0.8.5 fallback, and 32768 is final.
    # Both share the same default so most operators see no change. A
    # follow-on (v0.8.6) should propagate the GGUF-auto-detected value
    # through env so even unset operators with high-capacity GGUFs
    # benefit from the full native context; deferred because that
    # requires a launcher refactor (n_ctx resolution happens after
    # session_env is built).
    try:
        local_n_ctx = int(
            resolve_env("DEEPER_NOTEBOOK_LOCAL_N_CTX")
            or resolve_env("DEEPER_NOTEBOOK_CHAT_LLM_CTX")
            or "32768"
        )
    except ValueError:
        # Malformed value — fall back to the safe default rather than
        # crash the chat turn over a bad env. Mirrors the launcher's
        # own _spawn_llamacpp_chat fallback semantics (v0.7.206).
        local_n_ctx = 32768
    # v0.8.37 — UI provider preference. Env var still wins for back-compat;
    # if unset, read `auto_route_provider_pref` from DefaultModels (new
    # Settings dropdown). Final fallback: "auto".
    default_provider = resolve_env("DEEPER_NOTEBOOK_CHAT_PROVIDER", "").strip()
    if not default_provider:
        try:
            defaults_for_pref = await model_manager.get_defaults()
            default_provider = (
                getattr(defaults_for_pref, "auto_route_provider_pref", None)
                or "auto"
            )
        except Exception:
            default_provider = "auto"
    if default_provider not in ("auto", "local", "cloud"):
        # Defensive: bad user-entered value (e.g. via raw SurrealQL).
        # Same fallback shape pick_provider would apply.
        default_provider = "auto"

    # v0.8.20 — was a sync call; the helper now awaits its inner
    # httpx probe on the default executor so the event loop stays
    # responsive even when a wedged local sidecar takes 9s to time
    # out. pick_provider itself stays sync — only the input changed.
    # v0.8.66 (audit A-6/A-7) — reserve headroom for the REPLY (chat callers use
    # max_tokens=8192) plus a margin for the system prompt + tool schemas that
    # `content_tokens` (content-only) doesn't count. Without this, a prompt just
    # under n_ctx routed local then overflowed when the reply was reserved →
    # llama.cpp 400. Env-tunable; default 8192 (reply) + 1024 (system/tools).
    try:
        _reply_headroom = int(
            resolve_env("DEEPER_NOTEBOOK_LOCAL_REPLY_HEADROOM_TOKENS") or "8192"
        )
        if _reply_headroom < 0:
            _reply_headroom = 8192
    except ValueError:
        _reply_headroom = 8192
    _reply_headroom += 1024  # system-prompt + tool-schema margin (A-7)

    choice = pick_provider(
        content_tokens=content_tokens,
        local_chat_healthy=await _local_chat_healthy_cached(),
        local_chat_n_ctx=local_n_ctx,
        cloud_model_id=cloud_model_id,
        local_model_id=local_model_id,
        default_provider=default_provider,
        reply_headroom_tokens=_reply_headroom,
    )
    # v0.8.51 — Phase 5.2a fail-closed privacy gate. When enabled
    # (DEEPER_NOTEBOOK_PRIVACY_GATE, default off) and the router picked CLOUD,
    # scan the
    # outbound content for structured secrets/PII; if found, keep the turn
    # on the local model (or block when no local model exists) so sensitive
    # data never leaves the machine. No-op when the gate is off — zero
    # change to default routing. Runs before the log + selected_provider
    # labeling so both reflect the gated decision.
    from deeper_notebook.ai.privacy_gate import (
        _privacy_gate_enabled,
        apply_privacy_gate,
    )

    # v0.8.57 — Phase 5.2b optional model-backed PII layer. Only worth the
    # extra local-LLM call when the gate is enabled AND this turn is actually
    # cloud-bound; otherwise skip it entirely (unconfigured → returns [] fast,
    # but we don't even await in the common case). The call is async so the
    # event loop stays free; results are UNIONed into the gate's regex floor.
    # v0.8.63 — explicit per-turn user consent ("Re-ask allowing cloud" in the
    # redaction-review sheet) skips the gate entirely for this turn. Logged so
    # the bypass is auditable. Default False → gate runs as normal.
    gate_findings: list[str] = []
    if privacy_gate_bypass:
        logger.info(
            "v0.8.63 privacy gate BYPASSED for this turn by explicit user "
            "consent (bypass_privacy_gate)"
        )
    else:
        extra_findings: list[str] = []
        if (
            _privacy_gate_enabled()
            and cloud_model_id
            and choice.model_id == cloud_model_id
        ):
            from deeper_notebook.ai.privacy_classifier import classify_via_model_async

            extra_findings = await classify_via_model_async(content)

        choice = apply_privacy_gate(
            choice,
            content=content,
            local_model_id=local_model_id,
            cloud_model_id=cloud_model_id,
            extra_findings=extra_findings,
            findings_out=gate_findings,
        )
    # v0.8.58 — when the gate acted (rerouted cloud→local), surface that it was
    # a PRIVACY decision (not ordinary size/health routing) + the category
    # labels, so the response / review UI can show "kept on-device". Only
    # category labels — never the matched secret values. (On a block the gate
    # raises before this, so this only fires for the reroute case.)
    if selection_out is not None and gate_findings:
        selection_out["privacy_gated"] = True
        selection_out["privacy_categories"] = sorted(set(gate_findings))
    logger.info(f"v0.8.0 chat router → {choice.model_id} ({choice.reason})")
    # v0.8.1 — surface the routing decision so callers (chat graph node)
    # can plumb it back into the HTTP response. Provider derivation: the
    # chosen model_id matches local_model_id ⇒ "local"; otherwise "cloud".
    # We compare by identity-of-choice rather than parsing choice.reason
    # so future router refactors that rephrase reasons don't silently
    # break this label.
    if selection_out is not None:
        if local_model_id and choice.model_id == local_model_id:
            selection_out["selected_provider"] = "local"
        elif cloud_model_id and choice.model_id == cloud_model_id:
            selection_out["selected_provider"] = "cloud"
        else:
            # Unexpected — router returned an ID neither of our inputs.
            # Don't lie; leave provider unset, but record the model_id.
            selection_out["selected_provider"] = None
        selection_out["selected_model_id"] = choice.model_id
    return await provision_langchain_model(
        content=content,
        model_id=choice.model_id,
        default_type="chat",
        # v0.8.68 — the smart router may pick cloud while the machine is
        # offline (e.g. stale health cache); the gate inside
        # provision_langchain_model corrects that and reports here.
        fallback_out=fallback_out,
        **kwargs,
    )


async def provision_langchain_model(
    content, model_id, default_type, fallback_out: "dict | None" = None, **kwargs
) -> BaseChatModel:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type

    v0.8.68 — resolution now happens in two phases (id, then instance) so
    the offline gate can substitute a LOCAL model id when the machine is
    offline (probe or Offline-mode toggle) and the candidate is a cloud
    provider. `fallback_out` (optional dict, NOT forwarded to the model
    constructor) is populated by the gate when a substitution happens —
    chat callers thread it into the response for the UI pill.
    """
    tokens = token_count(content)
    selection_reason = ""

    if tokens > 105_000:
        selection_reason = f"large_context (content has {tokens} tokens)"
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        candidate_id = await model_manager.get_default_model_id("large_context")
    elif model_id:
        selection_reason = f"explicit model_id={model_id}"
        candidate_id = model_id
    else:
        selection_reason = f"default for type={default_type}"
        candidate_id = await model_manager.get_default_model_id(default_type)

    # v0.8.68 — offline gate. No-op when online / candidate is local /
    # candidate is None. Raises ConfigurationError fast (instead of a
    # provider-timeout hang) when offline with no local model.
    candidate_id = await gate_language_model_id(candidate_id, fallback_out=fallback_out)

    model = None
    if candidate_id:
        if model_id and candidate_id == model_id:
            # Explicit-id path: keep get_model's typed errors verbatim
            # (pre-v0.8.68 behavior for explicit ids).
            model = await model_manager.get_model(candidate_id, **kwargs)
        else:
            # Default-resolution path (or a gate-substituted id): keep
            # get_default_model's historical log-and-return-None on a
            # load failure so the "no model configured" error below fires.
            try:
                model = await model_manager.get_model(candidate_id, **kwargs)
            except (ValueError, ConfigurationError) as e:
                logger.error(
                    f"Failed to load model for {selection_reason}: {e}. "
                    f"The configured model_id '{candidate_id}' may have been "
                    f"deleted or misconfigured. Please go to Settings → Models "
                    f"and reconfigure the default model."
                )
                model = None
    elif not candidate_id and default_type and not model_id and tokens <= 105_000:
        logger.warning(
            f"No default model configured for type '{default_type}'. "
            f"Please go to Settings → Models and set a default model."
        )

    logger.debug(f"Using model: {model}")

    if model is None:
        logger.error(
            f"Model provisioning failed: No model found. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}. "
            f"Please check Settings → Models and ensure a default model is configured for '{default_type}'."
        )
        raise ConfigurationError(
            f"No model configured for {selection_reason}. "
            f"Please go to Settings → Models and configure a default model for '{default_type}'."
        )

    if not isinstance(model, LanguageModel):
        logger.error(
            f"Model type mismatch: Expected LanguageModel but got {type(model).__name__}. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}."
        )
        raise ConfigurationError(
            f"Model is not a LanguageModel: {model}. "
            f"Please check that the model configured for '{default_type}' is a language model, not an embedding or speech model."
        )

    return model.to_langchain()
