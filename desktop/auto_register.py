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
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import httpx

from desktop.config import Config

log = logging.getLogger(__name__)

# GGUF filenames that strongly suggest a dedicated embedding model.
# These are registered as "embedding" type; everything else is "language".
_EMBEDDING_HINTS = ("nomic", "bge", "e5", "gte", "minilm", "embed", "snowflake")


def _is_embedding_gguf(filename: str) -> bool:
    lower = filename.lower()
    return any(hint in lower for hint in _EMBEDDING_HINTS)


def auto_register(
    api_base_url: str,
    cfg: Config,
    llamacpp_port: int | None = None,
    *,
    whisper_port: int | None = None,
    piper_port: int | None = None,
    embed_port: int | None = None,
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
            )
    except Exception as exc:
        log.warning("auto_register failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _do_register(
    client: httpx.Client,
    cfg: Config,
    llamacpp_port: int | None,
    *,
    whisper_port: int | None = None,
    piper_port: int | None = None,
    embed_port: int | None = None,
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
    ollama_models = _list_ollama_models()
    if ollama_models:
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
            for model_name in ollama_models:
                # Ollama tag names include ":<tag>"; use the full name as-is.
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

    # --- 3. llama.cpp / openai_compatible -----------------------------------
    if llamacpp_port is not None:
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
            # Register any GGUFs from model_dir.
            for gguf_rel in _list_local_ggufs(cfg.model_dir):
                model_name = Path(gguf_rel).stem  # strip .gguf
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

    # --- 4. Scan model_dir even without llamacpp ----------------------------
    # If no llamacpp server but there are GGUFs, still register them so the
    # picker shows them.  We use provider="openai_compatible" with no live
    # server — the user can point the server at them later.
    elif cfg.model_dir.exists():
        ggufs = _list_local_ggufs(cfg.model_dir)
        if ggufs:
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
                for gguf_rel in ggufs:
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


def register_default_episode_profile(client: httpx.Client) -> None:
    """Idempotent: create 'Open Notebook Plus Local' episode profile if missing."""
    PROFILE_NAME = "Open Notebook Plus Local"
    try:
        r = client.get("/api/episode_profiles")
        r.raise_for_status()
        for p in r.json():
            if p.get("name") == PROFILE_NAME:
                return  # already exists
    except Exception as exc:
        log.warning("Could not list episode profiles: %s — skipping profile bootstrap", exc)
        return

    # Look up the IDs we just registered for chat model + piper voices
    try:
        models = client.get("/api/models").json()
    except Exception:
        return
    by_name = {m.get("name"): m.get("id") for m in models}
    chat_id = (by_name.get("Hermes-3-Llama-3.1-8B-Q4_K_M")
               or by_name.get("Mistral-7B-Instruct-v0.3-Q4_K_M")
               or next((mid for name, mid in by_name.items()
                        if not name.startswith(("piper-", "whisper-", "nomic-"))),
                       None))
    amy_id = by_name.get("piper-amy-en")
    ryan_id = by_name.get("piper-ryan-en")
    if not (chat_id and amy_id and ryan_id):
        log.info("Skipping episode profile creation: missing chat_id/amy_id/ryan_id")
        return

    payload = {
        "name": PROFILE_NAME,
        "description": "Two-voice podcast using local Piper TTS",
        "chat_model_id": chat_id,
        "speakers": [
            {"name": "Alex", "role": "Host", "tts_model_id": amy_id},
            {"name": "Sam", "role": "Co-host", "tts_model_id": ryan_id},
        ],
        "default_length_minutes": 5,
    }
    try:
        r = client.post("/api/episode_profiles", json=payload)
        if r.status_code in (200, 201):
            log.info("Created default episode profile %r", PROFILE_NAME)
    except Exception as exc:
        log.warning("Could not create episode profile %r: %s", PROFILE_NAME, exc)


def _ensure_credential(
    *,
    client: httpx.Client,
    existing_names: set[str],
    name: str,
    provider: str,
    modalities: list[str],
    base_url: str | None = None,
) -> str | None:
    """Return the ID of the named credential, creating it if missing.

    Returns None on error.
    """
    if name.lower() in existing_names:
        # Already exists — fetch its ID.
        try:
            r = client.get("/api/credentials")
            r.raise_for_status()
            for cred in r.json():
                if cred.get("name", "").lower() == name.lower():
                    return cred.get("id")
        except Exception as exc:
            log.warning("Could not fetch credential id for %r: %s", name, exc)
            return None

    payload: dict = {"name": name, "provider": provider, "modalities": modalities}
    if base_url:
        payload["base_url"] = base_url
    try:
        r = client.post("/api/credentials", json=payload)
        if r.status_code == 201:
            data = r.json()
            log.info("Created credential %r (provider=%s id=%s)", name, provider, data.get("id"))
            return data.get("id")
        else:
            log.warning(
                "POST /credentials %r → %s: %s", name, r.status_code, r.text[:200]
            )
            return None
    except Exception as exc:
        log.warning("Could not create credential %r: %s", name, exc)
        return None


def _ensure_model(
    *,
    client: httpx.Client,
    existing_keys: set[tuple[str, str]],
    name: str,
    provider: str,
    model_type: str,
    credential_id: str | None,
) -> bool:
    """POST /models if (name, type) not already registered.  Returns True if created."""
    if (name.lower(), model_type.lower()) in existing_keys:
        return False

    payload: dict = {"name": name, "provider": provider, "type": model_type}
    if credential_id:
        payload["credential"] = credential_id
    try:
        r = client.post("/api/models", json=payload)
        if r.status_code in (200, 201):
            log.info("Registered model %r (provider=%s type=%s)", name, provider, model_type)
            return True
        elif r.status_code == 400 and "already exists" in (r.text or "").lower():
            return False  # duplicate — treat as no-op
        else:
            log.warning(
                "POST /models %r → %s: %s", name, r.status_code, r.text[:200]
            )
            return False
    except Exception as exc:
        log.warning("Could not register model %r: %s", name, exc)
        return False


# ---------------------------------------------------------------------------
# Discovery helpers (public for testability)
# ---------------------------------------------------------------------------

def _list_ollama_models(base_url: str = "http://127.0.0.1:11434") -> list[str]:
    """Return Ollama model names if the daemon is reachable, else []."""
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=1.0)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", []) if "name" in m]
    except Exception:
        pass
    return []


def _list_local_ggufs(model_dir: Path, min_bytes: int = 1 * 1024 * 1024) -> list[str]:
    """Return relative paths of GGUF files >= min_bytes in model_dir."""
    if not model_dir.exists():
        return []
    return sorted(
        str(p.relative_to(model_dir))
        for p in model_dir.rglob("*.gguf")
        if p.is_file() and p.stat().st_size >= min_bytes
    )
