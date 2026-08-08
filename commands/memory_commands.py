"""surreal-commands handlers registered by the Deeper Notebook memory layer.

This file is copied into the bundled upstream's commands/ directory at first
launch by desktop/app.py:_phase_register_memory_commands.

Discovery: surreal-commands imports any module passed via --import-modules.
Each @command-decorated function is registered as
    <persisted_app_identifier>.<function_name>
"""
from __future__ import annotations

import os

from surreal_commands import command

from deeper_notebook.environment import resolve_env


def _build_clients(model_override: str | None = None):
    """Lazily build the LLM + memory clients at command-invocation time.

    Avoids importing heavy deps at module load (worker discovery).

    Reads MEMORY_* env vars set by the Supervisor in `session_env` before
    spawning the worker. We use a private namespace (MEMORY_*) instead of
    OPENAI_COMPATIBLE_BASE_URL to avoid conflicting with the upstream
    esperanto/Ollama configuration the user picked for regular chat.

    v0.7.83 — optional `model_override` lets the caller (the command
    handlers below) pin the LLM to a specific model name when the user
    picked a per-session override in chat. Defaults to whatever
    DEEPER_NOTEBOOK_CHAT_MODEL_NAME / "default" resolves to so existing behavior is
    preserved when the caller doesn't pass an override.
    """
    from desktop.config import default_config_path, load_or_create
    from desktop.memory.client import build_memory_client

    cfg = load_or_create(default_config_path())
    surreal_url = os.environ.get("MEMORY_SURREAL_URL",
                                 os.environ.get("SURREAL_URL", ""))
    embed_url = os.environ.get("MEMORY_EMBED_URL", "")
    llm_url = os.environ.get("MEMORY_CHAT_LLM_URL", "")
    if not (surreal_url and embed_url and llm_url):
        raise RuntimeError(
            "memory_commands invoked without MEMORY_* URLs set — was the "
            "launcher Supervisor used to spawn this worker?"
        )
    mem_client = build_memory_client(
        cfg=cfg, surreal_url=surreal_url,
        embed_url=embed_url, llm_url=llm_url,
    )
    # Minimal LLM wrapper compatible with our writer's llm.complete()
    # v0.5.10 — fixes for production reliability:
    #   - Model name no longer hardcoded to Hermes-3. The launcher's
    #     capability-aware spawner (v0.5.1+) picks the model dynamically,
    #     so the writer must use whatever the chat server actually loaded.
    #     llama-cpp-python's OpenAI-compatible endpoint accepts model="default"
    #     or echoes the active model regardless of the name passed.
    #   - Timeout dropped from 120 s → 30 s default (writer is per-turn,
    #     blocking the worker that long stalls subsequent extracts).
    #     Overridable via DEEPER_NOTEBOOK_CHAT_TIMEOUT_S env var.
    #   - Reject the empty system+user case before the network round trip.
    #
    # v0.7.48 — removed redundant `import os` (was on line 55). The
    # module-level `import os` on line 12 was already in scope. Because
    # there was ALSO a local `import os` inside this function, Python
    # treated `os` as a function-local variable throughout the function
    # body — `os.environ.get(...)` calls at lines 31-34 hit
    # UnboundLocalError at runtime, BEFORE the local import line ran.
    # This bug was masked until v0.7.47 fixed memory-commands
    # registration; the writer code path never actually executed pre-
    # v0.7.47. Without this fix, the FIRST chat turn after v0.7.47
    # would have crashed the worker.
    import httpx

    chat_timeout_s = float(resolve_env("DEEPER_NOTEBOOK_CHAT_TIMEOUT_S", "30"))
    # v0.7.83 — caller-provided model_override takes precedence over
    # the env-var fallback. The local llama-cpp-python server echoes
    # whatever model name we send back as the active model regardless
    # of the value (it serves a single loaded GGUF), so this only
    # affects OpenAI-compatible third-party servers (LM Studio, vLLM)
    # that actually route by model name.
    chat_model_name = (
        model_override
        or resolve_env("DEEPER_NOTEBOOK_CHAT_MODEL_NAME")
        or "default"
    )

    class _LLM:
        def __init__(self, base_url, model):
            self.base_url = base_url
            self.model = model

        def complete(self, system, user):
            if not (system or user):
                return ""
            try:
                with httpx.Client(timeout=chat_timeout_s) as client:
                    r = client.post(
                        f"{self.base_url}/chat/completions",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "max_tokens": 800,
                            "temperature": 0.2,
                        },
                    )
                    r.raise_for_status()
                    # v0.7.5 — defensive .get() chain. Some
                    # OpenAI-compatible servers return HTTP 200 with
                    # `{"error": "..."}` (no "choices" key). The previous
                    # chained `[]` indexing would KeyError and crash
                    # the worker on those responses. Now we return "" and
                    # the writer silently produces zero facts for the
                    # turn — same outcome as the timeout path.
                    payload = r.json()
                    choices = payload.get("choices") or []
                    if not choices:
                        import logging
                        logging.getLogger(__name__).warning(
                            "chat LLM returned no choices (payload keys=%s) "
                            "— skipping fact extraction",
                            list(payload.keys()),
                        )
                        return ""
                    return (
                        choices[0].get("message", {}).get("content") or ""
                    )
            except httpx.TimeoutException:
                # Don't crash the worker — log and return empty so the writer
                # silently produces zero facts for this turn.
                import logging
                logging.getLogger(__name__).warning(
                    "chat LLM timed out after %ss — skipping fact extraction",
                    chat_timeout_s,
                )
                return ""
            except Exception as exc:
                # v0.7.5 — broaden to all Exception. Previously only
                # TimeoutException was caught; a connection-refused
                # (server restarting), HTTP 503 (model still loading on
                # local servers), HTTP 4xx (auth), or malformed-JSON
                # response would propagate out and crash the
                # surreal_commands worker. surreal_commands then retried
                # 5x per turn — log spam + no actual benefit since the
                # underlying server failure wasn't transient enough to
                # recover within retry windows. Now we degrade
                # gracefully: zero facts extracted for this turn, the
                # user's chat experience is unaffected, and one warning
                # in the log identifies the root cause.
                import logging
                logging.getLogger(__name__).warning(
                    "chat LLM failed (%s: %s) — skipping fact extraction",
                    type(exc).__name__, exc,
                )
                return ""

    llm = _LLM(llm_url, chat_model_name)
    return llm, mem_client


@command(name="memory_extract_turn", app="open_notebook")
def memory_extract_turn(chat_session_id: str, user_text: str,
                         assistant_text: str,
                         model_override: str | None = None) -> dict:
    """Per-turn fact extractor. Best-effort; no exceptions propagate.

    v0.7.83 — accepts optional `model_override` (defaults to None for
    backward compatibility with any in-flight rows queued by older API
    versions). When set, the writer's LLM client uses that model name
    instead of the bundled DEEPER_NOTEBOOK_CHAT_MODEL_NAME / "default".
    """
    try:
        from desktop.memory.writer import extract_turn
        llm, mem_client = _build_clients(model_override=model_override)
        extract_turn(
            llm=llm, mem_client=mem_client,
            chat_session_id=chat_session_id,
            user_text=user_text, assistant_text=assistant_text,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@command(name="memory_summarize_session", app="open_notebook")
def memory_summarize_session(chat_session_id: str, transcript: str,
                              model_override: str | None = None) -> dict:
    """Per-session episode summarizer.

    v0.7.83 — see memory_extract_turn for the model_override contract.
    """
    try:
        from desktop.memory.writer import summarize_session
        llm, mem_client = _build_clients(model_override=model_override)
        summarize_session(
            llm=llm, mem_client=mem_client,
            chat_session_id=chat_session_id,
            transcript=transcript,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
