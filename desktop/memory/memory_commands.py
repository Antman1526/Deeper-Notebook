"""surreal-commands handlers registered by Open Notebook Plus v0.4 memory layer.

This file is copied into the bundled upstream's commands/ directory at first
launch by desktop/app.py:_phase_register_memory_commands.

Discovery: surreal-commands imports any module passed via --import-modules.
Each @command-decorated function is registered as
    open_notebook.<function_name>
"""
from __future__ import annotations

import os

from surreal_commands import command


def _build_clients():
    """Lazily build the LLM + memory clients at command-invocation time.

    Avoids importing heavy deps at module load (worker discovery).

    Reads MEMORY_* env vars set by the Supervisor in `session_env` before
    spawning the worker. We use a private namespace (MEMORY_*) instead of
    OPENAI_COMPATIBLE_BASE_URL to avoid conflicting with the upstream
    esperanto/Ollama configuration the user picked for regular chat.
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
    import httpx

    class _LLM:
        def __init__(self, base_url, model):
            self.base_url = base_url
            self.model = model
        def complete(self, system, user):
            with httpx.Client(timeout=120) as client:
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
                return r.json()["choices"][0]["message"]["content"]
    llm = _LLM(llm_url, "Hermes-3-Llama-3.1-8B-Q4_K_M")
    return llm, mem_client


@command(name="memory_extract_turn")
def memory_extract_turn(chat_session_id: str, user_text: str,
                         assistant_text: str) -> dict:
    """Per-turn fact extractor. Best-effort; no exceptions propagate."""
    try:
        from desktop.memory.writer import extract_turn
        llm, mem_client = _build_clients()
        extract_turn(
            llm=llm, mem_client=mem_client,
            chat_session_id=chat_session_id,
            user_text=user_text, assistant_text=assistant_text,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@command(name="memory_summarize_session")
def memory_summarize_session(chat_session_id: str, transcript: str) -> dict:
    """Per-session episode summarizer."""
    try:
        from desktop.memory.writer import summarize_session
        llm, mem_client = _build_clients()
        summarize_session(
            llm=llm, mem_client=mem_client,
            chat_session_id=chat_session_id,
            transcript=transcript,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
