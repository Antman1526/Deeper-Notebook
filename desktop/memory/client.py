"""Factory for the mem0 memory client wired to our local SurrealDB +
local-LLM + local-embedder endpoints.

The `_register` import below has the side effect of installing `surreal` as
a mem0 vector-store provider; it MUST happen before `Memory.from_config()`
sees `provider: "surreal"`, or mem0 will reject the config as unknown.
"""
from __future__ import annotations

import desktop.memory._register  # noqa: F401 — registers `surreal` provider

try:
    from mem0 import Memory
except ImportError:  # tests don't need mem0 installed at import time
    Memory = None  # type: ignore[assignment]


def build_memory_client(*, cfg, surreal_url: str, embed_url: str, llm_url: str):
    """Build a `mem0.Memory` instance backed by our SurrealDB store + local
    OpenAI-compatible LLM and embedder endpoints."""
    if Memory is None:
        raise RuntimeError("mem0 not installed — run bootstrap to provision the venv")
    return Memory.from_config({
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
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": "sk-no-key",
                "base_url": embed_url,
                "model": "nomic-embed-text-v1.5",
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "api_key": "sk-no-key",
                "base_url": llm_url,
                "model": "Hermes-3-Llama-3.1-8B-Q4_K_M",
            },
        },
    })
