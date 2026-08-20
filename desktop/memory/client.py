"""Factory for the mem0 memory client wired to our local SurrealDB +
local-LLM + local-embedder endpoints.

The `_register` import below has the side effect of installing `surreal` as
a mem0 vector-store provider; it MUST happen before `Memory.from_config()`
sees `provider: "surreal"`, or mem0 will reject the config as unknown.
"""

from __future__ import annotations

import os

import desktop.memory._register  # noqa: F401 — registers `surreal` provider
from deeper_notebook.environment import resolve_env

try:
    from mem0 import Memory
except ImportError:  # tests don't need mem0 installed at import time
    Memory = None  # type: ignore[assignment]


def build_memory_client(*, cfg, surreal_url: str, embed_url: str, llm_url: str):
    """Build a `mem0.Memory` instance backed by our SurrealDB store + local
    OpenAI-compatible LLM and embedder endpoints.

    v0.6.14 — model name no longer hardcoded to Hermes-3. The launcher's
    capability-aware spawner (v0.5.1+) picks the chat model dynamically
    based on available RAM, so on a 64 GB box it may load Qwen3.6-35B-A3B.
    Asking llama-cpp for a literal "Hermes-3-Llama-3.1-8B-Q4_K_M" then
    either silently returns the wrong model's output (when llama-cpp is
    lenient about model names) or 404s (when strict). Matches the same
    fix already applied in memory_commands.py.

    Override via DEEPER_NOTEBOOK_CHAT_MODEL_NAME env var; default "default" works
    against llama-cpp-python's permissive OpenAI-compatible server.
    """
    if Memory is None:
        raise RuntimeError("mem0 not installed — run bootstrap to provision the venv")
    chat_model_name = resolve_env("DEEPER_NOTEBOOK_CHAT_MODEL_NAME", "default")
    return Memory.from_config(
        {
            "vector_store": {
                "provider": "surreal",
                "config": {
                    "surreal_url": surreal_url,
                    "namespace": "open_notebook",
                    "database": "open_notebook",
                    "user": cfg.surreal_user,
                    "password": cfg.surreal_password,
                },
            },
            # v0.7.207 — mem0's BaseEmbedderConfig + BaseLlmConfig use
            # the field name `openai_base_url`, NOT `base_url`. Prior to
            # this fix the launcher passed `base_url` and mem0 rejected
            # with `TypeError: BaseEmbedderConfig.__init__() got an
            # unexpected keyword argument 'base_url'` at startup —
            # memory_shim crashed silently (production DEVNULL), the
            # Memory (local) credential test then reported "Cannot
            # connect to server", and every chat session lost the
            # mem0 writer that extracts facts + summarizes turns.
            # Visible in ~/.deeper-notebook/logs/memory.log.
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": "sk-no-key",
                    "openai_base_url": embed_url,
                    "model": "nomic-embed-text-v1.5",
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": "sk-no-key",
                    "openai_base_url": llm_url,
                    "model": chat_model_name,
                },
            },
        }
    )
