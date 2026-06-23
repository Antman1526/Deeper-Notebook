"""Native MLX OpenAI-compatible model registration."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from desktop.auto_register._http import _ensure_credential, _ensure_model

log = logging.getLogger(__name__)


def _mlx_model_display_name(model_ref: str) -> str:
    name = Path(model_ref).name.strip()
    return name.replace("__", "/", 1) or model_ref


def register_mlx_models(
    client: httpx.Client,
    existing_cred_names: set[str],
    existing_model_keys: set[tuple[str, str]],
    *,
    base_url: str | None,
    model_ref: str | None,
) -> bool:
    """Register the native MLX server started by the desktop launcher."""
    if not base_url or not model_ref:
        return False

    cred_name = "MLX (local)"
    cred_id = _ensure_credential(
        client=client,
        existing_names=existing_cred_names,
        name=cred_name,
        provider="openai_compatible",
        modalities=["language"],
        base_url=base_url,
    )
    if cred_id is None:
        return False

    existing_cred_names.add(cred_name.lower())
    model_name = _mlx_model_display_name(model_ref)
    registered = _ensure_model(
        client=client,
        existing_keys=existing_model_keys,
        name=model_name,
        provider="openai_compatible",
        model_type="language",
        credential_id=cred_id,
    )
    if registered:
        existing_model_keys.add((model_name.lower(), "language"))
        log.info("Registered MLX model %r against %s", model_name, base_url)
    return registered
