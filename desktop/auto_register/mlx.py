"""Native MLX OpenAI-compatible model registration."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from desktop.auto_register._http import _ensure_credential, _ensure_model

log = logging.getLogger(__name__)


def _mlx_model_display_name(model_ref: str) -> str:
    """Human-readable repo label, e.g. ``mlx-community/North-Mini-Code-1.0-6bit``.

    Kept for logging only. It must NOT be what gets registered — see
    ``register_mlx_models``.
    """
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
    # v0.8.97 — register the LAUNCH REFERENCE, not the prettified display name.
    # A model row's `name` is used verbatim as the OpenAI `model` field
    # (deeper_notebook/ai/models.py builds every language model with
    # `model_name=model.name`), and mlx_lm.server keys its single loaded model
    # on the exact `--model` string it was started with. Anything else is
    # treated as a Hugging Face repo id and 404s — so the old display name
    # ("PocketAiHub/Qwen3.8-27B-MLX-6bit") produced a model row that registered
    # cleanly, showed up in the picker, and could never answer a single turn.
    # mlx_lm.server has no --model-name/alias option, so the wire id has to be
    # the path. See test_registered_mlx_model_name_is_the_string_the_server_accepts.
    model_name = model_ref
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
        log.info(
            "Registered MLX model %r (%s) against %s",
            _mlx_model_display_name(model_ref),
            model_name,
            base_url,
        )
    return registered
