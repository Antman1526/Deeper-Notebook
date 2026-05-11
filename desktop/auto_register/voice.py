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
) -> None:
    """Register Whisper/Piper/embed credentials + models if ports are set."""
    # Whisper
    if whisper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Whisper (local)",
            provider="openai_compatible",
            modalities=["speech_to_text"],
            base_url=f"http://127.0.0.1:{whisper_port}/v1",
        )
        if cred:
            _ensure_model(
                client=client, existing_keys=set(),
                name="whisper-base-en",
                provider="openai_compatible",
                model_type="speech_to_text",
                credential_id=cred,
            )

    # Piper
    if piper_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Piper (local)",
            provider="openai_compatible",
            modalities=["text_to_speech"],
            base_url=f"http://127.0.0.1:{piper_port}/v1",
        )
        if cred:
            for voice_id in ("piper-amy-en", "piper-ryan-en"):
                _ensure_model(
                    client=client, existing_keys=set(),
                    name=voice_id,
                    provider="openai_compatible",
                    model_type="text_to_speech",
                    credential_id=cred,
                )

    # Embedding (llama.cpp server with --embedding flag)
    if embed_port is not None:
        cred = _ensure_credential(
            client=client,
            existing_names=set(),
            name="Local Embeddings (llama.cpp)",
            provider="openai_compatible",
            modalities=["embedding"],
            base_url=f"http://127.0.0.1:{embed_port}/v1",
        )
        if cred:
            _ensure_model(
                client=client, existing_keys=set(),
                name="nomic-embed-text-v1.5",
                provider="openai_compatible",
                model_type="embedding",
                credential_id=cred,
            )
