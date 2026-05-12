"""Post-startup registration of locally-available models against the upstream API.

Called by __main__.py after Supervisor.start_all() returns. Idempotent:
checks /api/credentials and /api/models first, only creates what's missing.

Endpoint summary (found in api/routers/credentials.py and api/routers/models.py):

  POST /credentials
    body: {name, provider, modalities: [...], base_url?}
    → 201 CredentialResponse {id, name, provider, ...}

  GET /credentials
    → list[CredentialResponse]

  GET /models
    → list[ModelResponse]

  POST /models
    body: {name, provider, type: "language"|"embedding"|..., credential?}
    → ModelResponse

  POST /models/auto-assign
    (no body) — assigns first available model of each type to default slots
    → AutoAssignResult {assigned, skipped, missing}

Public API (all preserved from the old flat module):
  auto_register(...)
  register_voice_models(...)
  register_default_episode_profile(...)
  _list_ollama_models(...)   — re-exported for test patching
  _list_local_ggufs(...)     — re-exported for test patching
"""
from __future__ import annotations

import logging

import httpx

from desktop.config import Config

# Re-export sub-module public symbols so existing imports/patches keep working.
from desktop.auto_register._http import (  # noqa: F401
    _ensure_credential,
    _ensure_model,
    _is_embedding_gguf,
    _list_local_ggufs,
    _list_ollama_models,
)
from desktop.auto_register.episode_profile import register_default_episode_profile  # noqa: F401
from desktop.auto_register.llamacpp import register_llamacpp_models
from desktop.auto_register.ollama import register_ollama_models
from desktop.auto_register.voice import register_voice_models  # noqa: F401

log = logging.getLogger(__name__)


def auto_register(
    api_base_url: str,
    cfg: Config,
    llamacpp_port: int | None = None,
    *,
    whisper_port: int | None = None,
    piper_port: int | None = None,
    embed_port: int | None = None,
    memory_port: int | None = None,
) -> None:
    """Register Ollama models + local GGUF models against the running API.

    api_base_url: e.g. http://127.0.0.1:55890 — the upstream FastAPI URL.
    cfg: loaded config (gives model_dir, provider preference).
    llamacpp_port: if set, a llama-cpp-python server is running on this port
                   and we should register an openai_compatible credential
                   pointing at http://127.0.0.1:<port>/v1.
    whisper_port: if set, register a Whisper STT credential on this port.
    piper_port: if set, register a Piper TTS credential on this port.
    embed_port: if set, register a local embedding credential on this port.
    memory_port: if set, register a Memory retriever credential on this port.

    Idempotent: safe to call on every startup.  Logs failures; does NOT raise
    (registration failures must not crash the launcher).
    """
    try:
        with httpx.Client(base_url=api_base_url, timeout=15.0) as client:
            _do_register(
                client, cfg, llamacpp_port,
                whisper_port=whisper_port,
                piper_port=piper_port,
                embed_port=embed_port,
                memory_port=memory_port,
            )
    except Exception as exc:
        log.warning("auto_register failed (non-fatal): %s", exc)


def _do_register(
    client: httpx.Client,
    cfg: Config,
    llamacpp_port: int | None,
    *,
    whisper_port: int | None = None,
    piper_port: int | None = None,
    embed_port: int | None = None,
    memory_port: int | None = None,
) -> None:
    """Main registration logic, runs inside an httpx.Client context."""
    # --- 1. Fetch existing credentials and models --------------------------
    existing_cred_names: set[str] = set()
    try:
        r = client.get("/api/credentials")
        r.raise_for_status()
        for cred in r.json():
            existing_cred_names.add(cred.get("name", "").lower())
    except Exception as exc:
        log.warning("Could not fetch existing credentials: %s — skipping auto-register", exc)
        return

    existing_model_keys: set[tuple[str, str]] = set()  # (name.lower, type.lower)
    try:
        r = client.get("/api/models")
        r.raise_for_status()
        for m in r.json():
            existing_model_keys.add((m.get("name", "").lower(), m.get("type", "").lower()))
    except Exception as exc:
        log.warning("Could not fetch existing models: %s — skipping auto-register", exc)
        return

    registered_any = False

    # --- 2. Ollama ----------------------------------------------------------
    # Discover models here so the call to _list_ollama_models is patchable at
    # the desktop.auto_register namespace (matching existing test patch paths).
    ollama_models = _list_ollama_models()
    if register_ollama_models(client, ollama_models, existing_cred_names, existing_model_keys):
        registered_any = True

    # --- 3 & 4. llama.cpp / openai_compatible (with or without live server) --
    # Discover GGUFs here so the call is patchable at desktop.auto_register.
    local_ggufs = _list_local_ggufs(cfg.model_dir)
    if register_llamacpp_models(
        client, existing_cred_names, existing_model_keys,
        model_dir=cfg.model_dir, llamacpp_port=llamacpp_port,
        local_ggufs=local_ggufs,
    ):
        registered_any = True

    # --- 5. Auto-assign defaults if we registered anything -----------------
    if registered_any:
        try:
            r = client.post("/api/models/auto-assign")
            if r.status_code < 300:
                result = r.json()
                log.info(
                    "auto-assign defaults: assigned=%s skipped=%s missing=%s",
                    list(result.get("assigned", {}).keys()),
                    result.get("skipped", []),
                    result.get("missing", []),
                )
            else:
                log.warning("auto-assign returned %s: %s", r.status_code, r.text[:200])
        except Exception as exc:
            log.warning("auto-assign failed (non-fatal): %s", exc)

    # --- 6. v0.3 — voice + embed registration + default episode profile -----
    if any(p is not None for p in (whisper_port, piper_port, embed_port)):
        register_voice_models(
            client,
            whisper_port=whisper_port,
            piper_port=piper_port,
            embed_port=embed_port,
            cfg=cfg,
        )
        register_default_episode_profile(client)

    # --- v0.4 memory layer --------------------------------------------------
    if memory_port is not None:
        from desktop.auto_register.memory import register_memory_credential
        register_memory_credential(client, memory_port=memory_port, cfg=cfg)
