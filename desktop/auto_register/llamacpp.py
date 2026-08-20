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

        # v0.7.194 — credential-name canonical-form resolution.
        #
        # Before v0.6.x this credential was named "Local GGUF (llama.cpp)"
        # — installs that went through the original Setup Wizard wrote
        # that name to SurrealDB along with the hardcoded port 8080.
        # Sometime around v0.6.x the canonical name shifted to
        # "llama.cpp (local)", but the rename wasn't propagated to
        # existing installs.
        #
        # End result: pre-v0.6.x users had `Local GGUF (llama.cpp)`
        # with port 8080 (broken since v0.5.9 stopped spawning that
        # port) and 10-20+ models LINKED to it. v0.7.193 auto-register
        # ran with the new name, found no match (case-sensitive name
        # lookup), and CREATED a fresh "llama.cpp (local)" with 0
        # models attached — orphaned. The user's chat still hit the
        # broken port 8080 because their existing models pointed at
        # the legacy credential.
        #
        # Fix: prefer the legacy name if it already exists. Auto-
        # register then refreshes its base_url to the current
        # chat_llm_port (via v0.7.193 _ensure_credential PUT) and the
        # 10-20+ already-linked models start working immediately. New
        # installs (no legacy credential) get the modern name.
        legacy_name = "Local GGUF (llama.cpp)"
        modern_name = "llama.cpp (local)"
        cred_name = (
            legacy_name if legacy_name.lower() in existing_cred_names else modern_name
        )
        cred_id = _ensure_credential(
            client=client,
            existing_names=existing_cred_names,
            name=cred_name,
            provider="openai_compatible",
            modalities=["language", "embedding"],
            base_url=base_url,
        )
        # v0.7.197 — When an embedding GGUF (nomic, bge-*, mxbai-*,
        # gte-*) is found in the model_dir, it MUST be linked to the
        # `Local Embeddings (llama.cpp)` credential (which points at
        # the dedicated --embedding=true llama-server on `embed_port`),
        # NOT the chat credential pointing at `chat_llm_port`.
        #
        # Before: every GGUF — chat OR embed — was linked to
        # `cred_id` (the chat credential). The chat llama-server
        # does not serve `/v1/embeddings` for the embed model file,
        # so any "use this embedding model" call from the API
        # crashed with a 404 / model-not-found at runtime.
        #
        # Look up the embed credential by name (it's created by
        # register_voice_models before this function runs). If it's
        # absent (no nomic file → no embed server), fall back to the
        # chat credential so non-embedding GGUFs still register and
        # any embedding GGUFs that slipped through still link
        # somewhere (and surface a known-bad URL the user can fix in
        # the UI) instead of being silently dropped.
        embed_cred_id: str | None = None
        embed_cred_name_lower = "local embeddings (llama.cpp)"
        if embed_cred_name_lower in existing_cred_names:
            try:
                resp = client.get("/api/credentials")
                resp.raise_for_status()
                for c in resp.json() or []:
                    if (c.get("name") or "").lower() == embed_cred_name_lower:
                        embed_cred_id = c.get("id")
                        break
            except Exception as exc:  # pragma: no cover — logged, not raised
                log.warning(
                    "v0.7.197 embed-credential lookup failed: %s (embedding "
                    "GGUFs will fall back to chat credential)",
                    exc,
                )

        if cred_id:
            existing_cred_names.add(cred_name.lower())
            for gguf_rel in local_ggufs:
                model_name = Path(gguf_rel).stem
                is_embedding = _is_embedding_gguf(model_name)
                model_type = "embedding" if is_embedding else "language"
                # Route embeddings to the embed credential when known.
                target_cred = (
                    embed_cred_id if (is_embedding and embed_cred_id) else cred_id
                )
                if _ensure_model(
                    client=client,
                    existing_keys=existing_model_keys,
                    name=model_name,
                    provider="openai_compatible",
                    model_type=model_type,
                    credential_id=target_cred,
                ):
                    existing_model_keys.add((model_name.lower(), model_type))
                    registered_any = True
    elif model_dir.exists():
        # v0.5.9 — the previous fallback registered an "openai_compatible"
        # credential with base_url=http://127.0.0.1:8080/v1 even when no
        # llama-cpp server was spawned. Result: dropdowns showed local
        # models that failed with connection errors when selected. Since
        # ONP always spawns its own llama-cpp server in the supervisor
        # process tree, this branch is dead in production. Logging here
        # so a future regression that strips the chat-server spawn shows
        # up in launcher.log instead of silently shipping broken creds.
        if local_ggufs:
            log.info(
                "skipping local-GGUF credential registration: no llama-cpp "
                "server port supplied (would have created broken creds)"
            )
        # v0.6.21 — the previous version kept ~30 lines of `if False:` legacy
        # fallback code below this point as documentation. Removed: comment
        # block above already captures the rationale, and the dead code was
        # never exercised (unreachable after the `return` two lines up).

    return registered_any
