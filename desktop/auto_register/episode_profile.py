"""Default episode profile registration."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


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
