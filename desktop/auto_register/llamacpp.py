"""llama.cpp / openai_compatible model registration."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from desktop.auto_register._http import (
    _ensure_credential,
    _ensure_model,
    _is_embedding_gguf,
)

log = logging.getLogger(__name__)


def register_llamacpp_models(
    client: httpx.Client,
    existing_cred_names: set[str],
    existing_model_keys: set[tuple[str, str]],
    model_dir: Path,
    llamacpp_port: int | None,
    local_ggufs: list[str],
) -> bool:
    """Register llama.cpp / local GGUF models.

    The caller is responsible for calling _list_local_ggufs() and passing the
    result in as ``local_ggufs``, which keeps the discovery call patchable at
    the __init__ level in tests.

    Returns True if any model was registered.
    """
    registered_any = False

    if llamacpp_port is not None:
        # A live llama-cpp-python server is running — register against it.
        base_url = f"http://127.0.0.1:{llamacpp_port}/v1"
        cred_id = _ensure_credential(
            client=client,
            existing_names=existing_cred_names,
            name="llama.cpp (local)",
            provider="openai_compatible",
            modalities=["language", "embedding"],
            base_url=base_url,
        )
        if cred_id:
            existing_cred_names.add("llama.cpp (local)")
            for gguf_rel in local_ggufs:
                model_name = Path(gguf_rel).stem
                model_type = "embedding" if _is_embedding_gguf(model_name) else "language"
                if _ensure_model(
                    client=client,
                    existing_keys=existing_model_keys,
                    name=model_name,
                    provider="openai_compatible",
                    model_type=model_type,
                    credential_id=cred_id,
                ):
                    existing_model_keys.add((model_name.lower(), model_type))
                    registered_any = True
    elif model_dir.exists():
        # No live server but GGUFs exist — register them so the picker shows them.
        if local_ggufs:
            cred_id = _ensure_credential(
                client=client,
                existing_names=existing_cred_names,
                name="Local GGUF (llama.cpp)",
                provider="openai_compatible",
                modalities=["language", "embedding"],
                base_url="http://127.0.0.1:8080/v1",
            )
            if cred_id:
                existing_cred_names.add("local gguf (llama.cpp)")
                for gguf_rel in local_ggufs:
                    model_name = Path(gguf_rel).stem
                    model_type = "embedding" if _is_embedding_gguf(model_name) else "language"
                    if _ensure_model(
                        client=client,
                        existing_keys=existing_model_keys,
                        name=model_name,
                        provider="openai_compatible",
                        model_type=model_type,
                        credential_id=cred_id,
                    ):
                        existing_model_keys.add((model_name.lower(), model_type))
                        registered_any = True

    return registered_any
