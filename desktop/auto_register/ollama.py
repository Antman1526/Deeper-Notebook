"""Ollama model registration."""

from __future__ import annotations

import logging
from typing import Iterable

import httpx

from desktop.auto_register._http import (
    _ensure_credential,
    _ensure_model,
    _is_embedding_gguf,
)

log = logging.getLogger(__name__)


def register_ollama_models(
    client: httpx.Client,
    ollama_model_names: list[str],
    existing_cred_names: set[str],
    existing_model_keys: set[tuple[str, str]],
) -> bool:
    """Register Ollama models from a pre-fetched list.

    The caller is responsible for calling _list_ollama_models() and passing
    the result in, which keeps the discovery call patchable at the __init__
    level in tests.

    Returns True if any model was registered.
    """
    if not ollama_model_names:
        return False

    registered_any = False
    cred_id = _ensure_credential(
        client=client,
        existing_names=existing_cred_names,
        name="Ollama (local)",
        provider="ollama",
        modalities=["language", "embedding"],
        base_url="http://127.0.0.1:11434",
    )
    if cred_id:
        existing_cred_names.add("ollama (local)")
        for model_name in ollama_model_names:
            model_type = "embedding" if _is_embedding_gguf(model_name) else "language"
            if _ensure_model(
                client=client,
                existing_keys=existing_model_keys,
                name=model_name,
                provider="ollama",
                model_type=model_type,
                credential_id=cred_id,
            ):
                existing_model_keys.add((model_name.lower(), model_type))
                registered_any = True
    return registered_any
