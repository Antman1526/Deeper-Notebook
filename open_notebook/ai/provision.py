import os
import time

from esperanto import LanguageModel
from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from open_notebook.ai.models import model_manager
from open_notebook.exceptions import ConfigurationError
from open_notebook.utils import token_count

# v0.8.0 — TTL cache so smart routing doesn't add 5-10s per chat turn.
_HEALTH_CACHE_TTL_S = 30
_health_cache: "tuple[float, dict[str, bool]] | None" = None


def _truthy_env(name: str) -> bool:
    """Return True when env var is set to a truthy value (1/true/yes/on)."""
    return os.getenv(name, "").lower() in ("1", "true", "yes", "on")


def _local_chat_healthy_cached(model_name: str = "Local GGUF (llama.cpp)") -> bool:
    """v0.8.0 — TTL-cached health lookup for the chat sidecar.

    Reads the sidecar base URL from OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL (set by
    desktop/app.py _phase_auto_register at launch). If the env var is unset the
    probe has no target and returns False immediately — this is the safe
    "no local model configured" path.

    The TTL (30s) prevents calling probe_all_local_models on every chat turn;
    the probe itself has a 5s read-timeout so without caching it would add
    5-10s of blocking latency before every model invocation.
    """
    global _health_cache
    now = time.monotonic()
    if _health_cache is None or now - _health_cache[0] >= _HEALTH_CACHE_TTL_S:
        try:
            from open_notebook.health.local_models import probe_all_local_models

            # Desktop bootstrap writes this env var when the chat sidecar
            # registers its port (see desktop/app.py _phase_auto_register).
            base_url = os.getenv("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", "")
            creds: list[dict] = []
            if base_url:
                creds.append(
                    {
                        "name": model_name,
                        "kind": "openai_compatible",
                        "base_url": base_url,
                    }
                )
            results = probe_all_local_models(creds) if creds else []
            _health_cache = (
                now,
                {r["name"]: r["status"] == "healthy" for r in results},
            )
        except Exception:
            # v0.8.0 — probe failure is non-fatal; treat as unhealthy so the
            # router falls through to cloud and the user still gets a response.
            _health_cache = (now, {})
    return _health_cache[1].get(model_name, False)


async def provision_langchain_chat_model(
    content: str,
    *,
    selection_out: "dict | None" = None,
    **kwargs,
) -> BaseChatModel:
    """v0.8.0 — Smart-routed chat provisioning.

    Wraps provision_langchain_model with pick_provider when
    OPEN_NOTEBOOK_AUTO_ROUTE_CHAT is truthy (1/true/yes/on).
    Falls back to the plain default-chat path otherwise so the
    change is opt-in and backward-compatible.

    Env knobs (all optional):
      OPEN_NOTEBOOK_AUTO_ROUTE_CHAT      — enable smart routing (default: off)
      OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID  — SurrealDB model ID for local chat
      OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID  — SurrealDB model ID for cloud chat
                                           (falls back to DefaultModels.default_chat_model)
      OPEN_NOTEBOOK_LOCAL_N_CTX          — local model context window (default: 32768)
      OPEN_NOTEBOOK_CHAT_PROVIDER        — override: auto | local | cloud (default: auto)
      OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL  — sidecar base URL for health probe

    v0.8.1 — optional `selection_out` dict that, when smart routing is
    enabled, is populated with `selected_provider` ("local"/"cloud") and
    `selected_model_id` (the SurrealDB model ID actually used). The chat-
    graph node passes a dict here so the /chat/execute response can carry
    the routing decision back to clients (replaces the v0.8.0 "manual
    eyeball check" workaround in scripts/verify-chat-platform.sh).
    """
    if not _truthy_env("OPEN_NOTEBOOK_AUTO_ROUTE_CHAT"):
        # Default path — identical to calling provision_langchain_model directly
        # with no model_id so existing DefaultModels config drives selection.
        # No selection_out fields set: the default path has no local/cloud
        # distinction, so leaving the keys absent (caller reads as None) is
        # the truthful answer.
        return await provision_langchain_model(
            content=content,
            model_id=None,
            default_type="chat",
            **kwargs,
        )

    from open_notebook.ai.router import pick_provider

    content_tokens = token_count(content)
    local_model_id = os.getenv("OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID") or None
    cloud_model_id = os.getenv("OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID") or None
    if not cloud_model_id:
        # v0.8.1 — use the dedicated auto_route_cloud field, NOT
        # default_chat_model. The v0.8.0 code fell back to default_chat_model
        # which silently routed oversized prompts to a local model when the
        # operator's chat default was itself local and
        # OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID was unset. With auto_route_cloud
        # absent we leave cloud_model_id as None so pick_provider falls through
        # to its "no cloud configured" branch — transparent local-only
        # behavior — instead of masquerading a local model as cloud.
        defaults = await model_manager.get_defaults()
        cloud_model_id = getattr(defaults, "auto_route_cloud", None) or None

    # v0.8.5 — read EITHER env var so the router stays in sync with
    # the actual sidecar config. Pre-v0.8.5 this only read
    # OPEN_NOTEBOOK_LOCAL_N_CTX (default 32768), but the launcher's
    # _spawn_llamacpp_chat reads `ONP_CHAT_LLM_CTX` (also default
    # 32768). Same concept, different names. An operator running
    # `ONP_CHAT_LLM_CTX=8192` for low-RAM mode would get the sidecar
    # bound at 8k context while the router still thought it had 32k
    # headroom — long prompts got routed to local, llama.cpp returned
    # 400 context_length_exceeded.
    # Precedence: OPEN_NOTEBOOK_LOCAL_N_CTX wins (explicit router knob),
    # ONP_CHAT_LLM_CTX is the v0.8.5 fallback, 32768 is the final default.
    # Both share the same default so most operators see no change. A
    # follow-on (v0.8.6) should propagate the GGUF-auto-detected value
    # through env so even unset operators with high-capacity GGUFs
    # benefit from the full native context; deferred because that
    # requires a launcher refactor (n_ctx resolution happens after
    # session_env is built).
    try:
        local_n_ctx = int(
            os.getenv("OPEN_NOTEBOOK_LOCAL_N_CTX")
            or os.getenv("ONP_CHAT_LLM_CTX")
            or "32768"
        )
    except ValueError:
        # Malformed value — fall back to the safe default rather than
        # crash the chat turn over a bad env. Mirrors the launcher's
        # own _spawn_llamacpp_chat fallback semantics (v0.7.206).
        local_n_ctx = 32768
    default_provider = os.getenv("OPEN_NOTEBOOK_CHAT_PROVIDER", "auto")

    choice = pick_provider(
        content_tokens=content_tokens,
        local_chat_healthy=_local_chat_healthy_cached(),
        local_chat_n_ctx=local_n_ctx,
        cloud_model_id=cloud_model_id,
        local_model_id=local_model_id,
        default_provider=default_provider,
    )
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
        **kwargs,
    )


async def provision_langchain_model(
    content, model_id, default_type, **kwargs
) -> BaseChatModel:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type
    """
    tokens = token_count(content)
    model = None
    selection_reason = ""

    if tokens > 105_000:
        selection_reason = f"large_context (content has {tokens} tokens)"
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        model = await model_manager.get_default_model("large_context", **kwargs)
    elif model_id:
        selection_reason = f"explicit model_id={model_id}"
        model = await model_manager.get_model(model_id, **kwargs)
    else:
        selection_reason = f"default for type={default_type}"
        model = await model_manager.get_default_model(default_type, **kwargs)

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
