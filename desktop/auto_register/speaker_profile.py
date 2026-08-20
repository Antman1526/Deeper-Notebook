"""Default speaker profile registration.

v0.7.32 — auto-create local speaker profiles wired to the piper voices.

Background: migration 7.surrealql seeded three speaker_profile presets
(`tech_experts`, `solo_expert`, `business_panel`) — every one hardcoded
to `tts_provider=openai` + `tts_model=gpt-4o-mini-tts`. On a local
Piper-only install, none of them resolves to a working TTS model. The
desktop bundle ships `piper-amy-en` and `piper-ryan-en` voice records
but no speaker_profile referencing them — the GeneratePodcastDialog
dropdown only shows the broken cloud presets, and any generation
attempt 404s because no OpenAI credential exists.

This module registers four LOCAL-FIRST presets, all using piper voices:

  1. Local Duo            — Alex (amy) + Sam (ryan) — the default
                            balanced two-host pair. Matches what
                            episode_profile.py registers as the
                            per-speaker tts_model_id fallback.
  2. Local Solo           — Alex alone — narrator/explainer format
                            (best with the episode_profile "Tutorial"
                            preset).
  3. Local Debate         — Pro (amy) + Skeptic (ryan) — pairs with
                            the "Debate" episode preset; distinct
                            personalities baked into backstory.
  4. Local Interview      — Interviewer (amy) + Expert (ryan) —
                            pairs with the "Q&A Interview" episode
                            preset.

Idempotent: only creates presets whose `name` doesn't already exist.
Skips silently if neither piper voice is registered (catches Piper
disabled or first-run mid-flight states).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

log = logging.getLogger(__name__)


# Each speaker entry conforms to api/routers/speaker_profiles.py's
# SpeakerProfileCreate.speakers payload. `voice_id` per speaker is the
# Piper voice short-code (matches what piper_shim exposes); the actual
# TTS Model registry id is passed via per-speaker `voice_model` so
# different speakers in the same profile can override the profile's
# default voice_model.
def _build_presets(amy_model_id: str, ryan_model_id: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "Local Duo",
            "description": "Two-host conversational pair (local Piper voices)",
            "voice_model": amy_model_id,  # profile-level default
            "speakers": [
                {
                    "name": "Alex",
                    "voice_id": "amy",
                    "backstory": (
                        "Curious generalist who reads broadly and connects "
                        "ideas across fields. Asks the questions a thoughtful "
                        "listener would ask."
                    ),
                    "personality": (
                        "Warm, energetic, and quick to follow up. Comfortable "
                        "admitting when something is new to them."
                    ),
                    "voice_model": amy_model_id,
                },
                {
                    "name": "Sam",
                    "voice_id": "ryan",
                    "backstory": (
                        "Practitioner with deep experience in the material's "
                        "domain. Has seen ideas play out in the real world."
                    ),
                    "personality": (
                        "Measured, precise, occasionally dry. Pushes back "
                        "when claims feel too tidy."
                    ),
                    "voice_model": ryan_model_id,
                },
            ],
        },
        {
            "name": "Local Solo",
            "description": "Single-narrator format (local Piper voice)",
            "voice_model": amy_model_id,
            "speakers": [
                {
                    "name": "Alex",
                    "voice_id": "amy",
                    "backstory": (
                        "Patient explainer who treats the listener as a "
                        "smart friend new to the topic."
                    ),
                    "personality": (
                        "Calm, structured, lightly conversational. Builds "
                        "ideas step by step without losing the listener."
                    ),
                    "voice_model": amy_model_id,
                },
            ],
        },
        {
            "name": "Local Debate",
            "description": "Two hosts argue opposing sides (local Piper voices)",
            "voice_model": amy_model_id,
            "speakers": [
                {
                    "name": "Alex",
                    "voice_id": "amy",
                    "backstory": (
                        "Optimistic about the material — gives it the most "
                        "charitable reading and defends its strongest claims."
                    ),
                    "personality": (
                        "Enthusiastic and engaged. Argues with conviction "
                        "but listens carefully to counter-points."
                    ),
                    "voice_model": amy_model_id,
                },
                {
                    "name": "Sam",
                    "voice_id": "ryan",
                    "backstory": (
                        "Skeptical of the material — finds the weak spots, "
                        "the unaddressed edge cases, the over-claimed bits."
                    ),
                    "personality": (
                        "Sharp, slightly contrarian, dry. Pushes hard but "
                        "concedes a good point when one lands."
                    ),
                    "voice_model": ryan_model_id,
                },
            ],
        },
        {
            "name": "Local Interview",
            "description": "Interviewer + Expert format (local Piper voices)",
            "voice_model": amy_model_id,
            "speakers": [
                {
                    "name": "Alex",
                    "voice_id": "amy",
                    "backstory": (
                        "Journalist with a knack for asking the question the "
                        "audience wishes they could ask themselves."
                    ),
                    "personality": (
                        "Inquisitive, persistent without being aggressive. "
                        "Follows up on vague answers, summarises crisply."
                    ),
                    "voice_model": amy_model_id,
                },
                {
                    "name": "Sam",
                    "voice_id": "ryan",
                    "backstory": (
                        "Subject-matter expert who has internalised the "
                        "material and is comfortable admitting the limits "
                        "of their certainty."
                    ),
                    "personality": (
                        "Thoughtful, careful with claims. Occasionally "
                        "concedes 'I don't know' or 'that's a fair point'."
                    ),
                    "voice_model": ryan_model_id,
                },
            ],
        },
    ]


def register_default_speaker_profile(client: httpx.Client) -> None:
    """Idempotent: create the v0.7.32 local-Piper speaker profile library.

    Skips presets whose `name` already exists (whether user-created,
    migrated, or from a prior install). Never overwrites.
    """
    # 1. List existing speaker profiles. We MUST match on name so we
    #    don't create dupes (the table has a UNIQUE index on name).
    try:
        r = client.get("/api/speaker-profiles")
        r.raise_for_status()
        existing = {p.get("name") for p in r.json() if p.get("name")}
    except Exception as exc:
        log.warning(
            "Could not list speaker profiles: %s — skipping speaker preset bootstrap",
            exc,
        )
        return

    # 2. Look up the Piper voice model IDs registered by voice.py.
    try:
        models = client.get("/api/models").json()
    except Exception:
        return
    by_name = {m.get("name"): m.get("id") for m in models}
    amy_id = by_name.get("piper-amy-en")
    ryan_id = by_name.get("piper-ryan-en")
    if not (amy_id and ryan_id):
        log.info(
            "Skipping speaker profile registration: "
            "piper-amy-en / piper-ryan-en not yet registered"
        )
        return

    # 3. Create missing presets.
    created = 0
    skipped = 0
    for preset in _build_presets(amy_id, ryan_id):
        if preset["name"] in existing:
            skipped += 1
            continue
        try:
            r = client.post("/api/speaker-profiles", json=preset)
            if r.status_code in (200, 201):
                log.info("Created speaker profile %r", preset["name"])
                created += 1
            else:
                log.warning(
                    "Could not create speaker profile %r (HTTP %s): %s",
                    preset["name"],
                    r.status_code,
                    r.text[:200],
                )
        except Exception as exc:
            log.warning("Could not create speaker profile %r: %s", preset["name"], exc)

    log.info(
        "Speaker profile preset library: %d created, %d skipped (already existed)",
        created,
        skipped,
    )
