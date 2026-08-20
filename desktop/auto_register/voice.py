"""Whisper / Piper / embedding voice-model registration."""

from __future__ import annotations

import logging

import httpx

from desktop.auto_register._http import _ensure_credential, _ensure_model
from desktop.config import Config

log = logging.getLogger(__name__)


def register_voice_models(
    client: httpx.Client,
    *,
    whisper_port: int | None,
    piper_port: int | None,
    embed_port: int | None,
    cfg: Config,
    existing_cred_names: set[str] | None = None,
    existing_model_keys: set[tuple[str, str]] | None = None,
) -> None:
    """Register Whisper/Piper/embed credentials + models if ports are set.

    v0.6.21 — accept the caller's already-fetched name/key sets so we don't
    re-create duplicate credentials on every launch. The previous version
    passed `existing_names=set()` and `existing_keys=set()` to every
    _ensure_credential / _ensure_model call, which meant the idempotency
    check (`name.lower() in existing_names`) was ALWAYS False and the
    function fell through to POST. Each relaunch therefore created another
    "Whisper (local)" / "Piper (local)" / "Local Embeddings (llama.cpp)"
    duplicate, polluting the credentials dropdown.

    Defaults preserve old test call sites that didn't pass these sets.
    """
    existing_cred_names = (
        existing_cred_names if existing_cred_names is not None else set()
    )
    existing_model_keys = (
        existing_model_keys if existing_model_keys is not None else set()
    )

    # Whisper
    if whisper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=existing_cred_names,
            name="Whisper (local)",
            provider="openai_compatible",
            modalities=["speech_to_text"],
            base_url=f"http://127.0.0.1:{whisper_port}/v1",
        )
        if cred:
            existing_cred_names.add("whisper (local)")
            if _ensure_model(
                client=client,
                existing_keys=existing_model_keys,
                name="whisper-base-en",
                provider="openai_compatible",
                model_type="speech_to_text",
                credential_id=cred,
            ):
                existing_model_keys.add(("whisper-base-en", "speech_to_text"))

    # Piper
    if piper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=existing_cred_names,
            name="Piper (local)",
            provider="openai_compatible",
            modalities=["text_to_speech"],
            base_url=f"http://127.0.0.1:{piper_port}/v1",
        )
        if cred:
            existing_cred_names.add("piper (local)")
            for voice_id in ("piper-amy-en", "piper-ryan-en"):
                if _ensure_model(
                    client=client,
                    existing_keys=existing_model_keys,
                    name=voice_id,
                    provider="openai_compatible",
                    model_type="text_to_speech",
                    credential_id=cred,
                ):
                    existing_model_keys.add((voice_id, "text_to_speech"))

    # Embedding (llama.cpp server with --embedding flag)
    if embed_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=existing_cred_names,
            name="Local Embeddings (llama.cpp)",
            provider="openai_compatible",
            modalities=["embedding"],
            base_url=f"http://127.0.0.1:{embed_port}/v1",
        )
        if cred:
            existing_cred_names.add("local embeddings (llama.cpp)")
            if _ensure_model(
                client=client,
                existing_keys=existing_model_keys,
                name="nomic-embed-text-v1.5",
                provider="openai_compatible",
                model_type="embedding",
                credential_id=cred,
            ):
                existing_model_keys.add(("nomic-embed-text-v1.5", "embedding"))
