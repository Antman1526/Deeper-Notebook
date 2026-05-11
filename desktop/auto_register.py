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
) -> None:
    """Register Ollama models + local GGUF models against the running API.

    api_base_url: e.g. http://127.0.0.1:55890 — the upstream FastAPI URL.
    cfg: loaded config (gives model_dir, provider preference).
    llamacpp_port: if set, a llama-cpp-python server is running on this port
                   and we should register an openai_compatible credential
                   pointing at http://127.0.0.1:<port>/v1.

    Idempotent: safe to call on every startup.  Logs failures; does NOT raise
    (registration failures must not crash the launcher).
    """
    try:
        with httpx.Client(base_url=api_base_url, timeout=15.0) as client:
            _do_register(client, cfg, llamacpp_port)
    except Exception as exc:
        log.warning("auto_register failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _do_register(
    client: httpx.Client,
    cfg: Config,
    llamacpp_port: int | None,
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
