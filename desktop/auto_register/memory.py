"""Memory credential registration — sibling of voice.py.

Registers the Memory retriever shim as an openai_compatible-style credential
so the upstream API's credential store shows "Memory (local)" alongside the
other credentials. Whether upstream actually consumes this credential via
the chat path is decided at integration time (spec §3.2); for v0.4 we just
make it visible.
"""
from __future__ import annotations

import logging
from typing import Any

from desktop.auto_register._http import _ensure_credential

log = logging.getLogger(__name__)


def register_memory_credential(client: Any, *, memory_port: int, cfg) -> None:
    """Register the Memory retriever as an OpenAI-compatible-style credential."""
    cred = _ensure_credential(
        client=client,
        existing_names=set(),
        name="Memory (local)",
        provider="openai_compatible",
        modalities=["language"],
        base_url=f"http://127.0.0.1:{memory_port}",
    )
    if cred:
        log.info("Registered Memory credential id=%s", cred)
