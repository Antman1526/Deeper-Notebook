"""Default episode profile registration."""
from __future__ import annotations

import logging

import httpx

from desktop.auto_register._http import _is_embedding_gguf

log = logging.getLogger(__name__)


# Names that should never be picked as the chat model. We match by prefix
# AND by the same heuristic _ensure_model uses (an embedding-y filename),
# so "nomic-embed-text-v1.5" is correctly excluded.
_NON_CHAT_PREFIXES = ("piper-", "whisper-", "nomic-", "Local Embeddings")


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

    # Look up the IDs we just registered for chat model + piper voices.
    # v0.6.22 — dropped hardcoded "Hermes-3 / Mistral" fallback gates.
    # After v0.6.11's RAM-probe fix, a 64 GB box auto-registers a chat
    # model named e.g. "Qwen3.6-35B-A3B-Q4_K_M". The hardcoded .get()
    # calls returned None on those installs and we silently fell through
    # to the "any non-voice/embed model" path anyway. Now that path is
    # the primary — and also filters out embedding-y names that the old
    # version let slip through (a name not matching the prefix tuple
    # but matching the embedding heuristic, like "bge-large-en-v1.5").
    try:
        models = client.get("/api/models").json()
    except Exception:
        return
    by_name = {m.get("name"): m.get("id") for m in models}
    chat_id = next(
        (mid for name, mid in by_name.items()
         if name
         and not name.startswith(_NON_CHAT_PREFIXES)
         and not _is_embedding_gguf(name)),
        None,
    )
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
