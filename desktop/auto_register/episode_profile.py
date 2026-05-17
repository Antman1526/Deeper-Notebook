"""Default episode profile registration.

v0.7.30 — expanded from one default preset to a library of eight
distinct podcast formats. Each preset has:

  - A short, marketable description (shown in the form picker)
  - A purpose-built `default_briefing` template (shapes the outline LLM)
  - A segment count tuned for the format's pacing
  - All share the local Piper TTS voices (amy=Alex, ryan=Sam)

The presets cover the most common podcast formats a researcher /
student / hobbyist actually uses:

  1. Deep Dive          — long-form exploration of a single topic
  2. Quick Brief        — sub-5-minute summary, headline-paced
  3. Debate             — two voices argue different sides
  4. Tutorial           — instructional, step-by-step walkthrough
  5. Story Mode         — narrative, scene-by-scene retelling
  6. News Roundup       — fast multi-topic recap
  7. Q&A Interview      — one host interviews the other
  8. Recap & Review     — book/paper/film-style critical review

Registration is idempotent: only presets whose `name` does not yet
exist in /api/episode-profiles are created. Existing user-customised
profiles are never overwritten.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from desktop.auto_register._http import _is_embedding_gguf

log = logging.getLogger(__name__)


# Names that should never be picked as the chat model. We match by prefix
# AND by the same heuristic _ensure_model uses (an embedding-y filename),
# so "nomic-embed-text-v1.5" is correctly excluded.
_NON_CHAT_PREFIXES = ("piper-", "whisper-", "nomic-", "Local Embeddings")


# v0.7.30 — preset library. Each entry is a self-contained episode
# profile definition. The chat_model_id + speaker IDs are filled in
# at registration time (they vary per install).
#
# Briefing prose is intentionally written as if the user wrote it
# themselves: clear voice, no LLM jargon, no "AI assistant" framing —
# the outline LLM reads this as a creative brief, not as instructions
# to itself.
_PRESETS: list[dict[str, Any]] = [
    {
        "name": "Open Notebook Plus Local",
        "description": "Two-voice podcast using local Piper TTS",
        "num_segments": 5,
        "default_length_minutes": 5,
        "default_briefing": (
            "A balanced two-host conversational podcast about the provided "
            "material. Hosts trade observations, ask each other questions, "
            "and surface the most interesting ideas. Aim for clarity over "
            "comprehensiveness."
        ),
    },
    {
        "name": "Deep Dive",
        "description": "Long-form exploration of one topic, 10-15 min",
        "num_segments": 7,
        "default_length_minutes": 12,
        "default_briefing": (
            "An in-depth two-host deep dive on a single topic. The hosts "
            "patiently unpack one core thesis, then explore consequences, "
            "counterarguments, surprising adjacencies, and what's still "
            "unresolved. Reward the patient listener: layer detail on "
            "detail. Pace is unhurried. End with a 'what we learned' "
            "synthesis, not a hard close."
        ),
    },
    {
        "name": "Quick Brief",
        "description": "Headline-paced summary in under 5 minutes",
        "num_segments": 3,
        "default_length_minutes": 4,
        "default_briefing": (
            "A tight, headline-paced summary of the material. Two hosts "
            "trade the three most-important takeaways and one open "
            "question. No throat-clearing, no recap of what they're about "
            "to say — just deliver it. Conversational but brisk. The "
            "listener has 4 minutes and wants the essentials."
        ),
    },
    {
        "name": "Debate",
        "description": "Two hosts argue opposing sides of the material",
        "num_segments": 5,
        "default_length_minutes": 10,
        "default_briefing": (
            "A structured debate. Alex argues in favour of (or the optimistic "
            "reading of) the material; Sam argues against (or the skeptical "
            "reading). They genuinely disagree — no false balance, no "
            "concession-after-every-point. Each segment introduces a fresh "
            "angle: factual claims, methodology, real-world implications, "
            "edge cases. End with a brief steel-manned synthesis where each "
            "host states what they conceded."
        ),
    },
    {
        "name": "Tutorial",
        "description": "Step-by-step instructional walkthrough",
        "num_segments": 5,
        "default_length_minutes": 8,
        "default_briefing": (
            "A teaching-format conversation. Sam plays the curious learner; "
            "Alex plays the patient practitioner. They walk through the "
            "material as a how-to: motivation → prerequisites → core "
            "procedure → common pitfalls → next steps. Sam asks the "
            "questions a beginner would actually ask. Alex answers in plain "
            "language, then refines with the precise term. No assumption "
            "of prior knowledge."
        ),
    },
    {
        "name": "Story Mode",
        "description": "Narrative retelling, scene by scene",
        "num_segments": 5,
        "default_length_minutes": 10,
        "default_briefing": (
            "A narrative-driven episode. The hosts retell the material as "
            "a story: characters (real or conceptual), stakes, turning "
            "points, resolution. Use scene-setting language. Alex sets up "
            "scenes; Sam reacts and asks what-happens-next. Quotes from "
            "the source are dramatised, not cited. The listener should "
            "want to know what happens in the next segment."
        ),
    },
    {
        "name": "News Roundup",
        "description": "Fast-paced multi-topic recap",
        "num_segments": 4,
        "default_length_minutes": 6,
        "default_briefing": (
            "A fast-paced recap of multiple items from the material. Each "
            "segment covers a distinct item or theme: headline, why-it-"
            "matters, one piece of supporting detail, and a one-line "
            "verdict. Hosts trade lead duties between segments. Energetic, "
            "informed, no editorialising. Closes with a one-sentence "
            "'one thing to watch' from each host."
        ),
    },
    {
        "name": "Q&A Interview",
        "description": "One host interviews the other in depth",
        "num_segments": 5,
        "default_length_minutes": 12,
        "default_briefing": (
            "An interview-style episode. Sam plays the curious interviewer; "
            "Alex plays the subject-matter expert who has internalised the "
            "material. Sam asks one substantial question per segment — "
            "starting from the obvious and progressing to the harder, more "
            "uncomfortable questions. Alex answers thoughtfully, sometimes "
            "concedes the limits of their certainty. End with Sam's "
            "best summary of what Alex said, and Alex's correction."
        ),
    },
    {
        "name": "Recap & Review",
        "description": "Book/paper-style critical review",
        "num_segments": 5,
        "default_length_minutes": 10,
        "default_briefing": (
            "A review-format episode treating the material as a single "
            "work to be critically assessed. Structure: setup (what is "
            "this and who's it for), what it gets right, what it gets "
            "wrong or oversimplifies, what's missing, and a final "
            "verdict. Hosts review with respect but without flattery. "
            "Both hosts must offer at least one specific criticism."
        ),
    },
]


def register_default_episode_profile(client: httpx.Client) -> None:
    """Idempotent: create the v0.7.30 preset library.

    Skips any preset whose `name` already exists in the database
    (whether user-created or from a prior install). Never overwrites.
    """
    try:
        r = client.get("/api/episode_profiles")
        r.raise_for_status()
        existing = {p.get("name") for p in r.json() if p.get("name")}
    except Exception as exc:
        log.warning(
            "Could not list episode profiles: %s — skipping preset bootstrap",
            exc,
        )
        return

    # Resolve the chat model ID + speaker voice IDs once; reused across
    # every preset. If any of these is missing, skip the entire library
    # — without them no preset can be useful anyway.
    try:
        models = client.get("/api/models").json()
    except Exception:
        return
    by_name = {m.get("name"): m.get("id") for m in models}
    chat_id = next(
        (
            mid
            for name, mid in by_name.items()
            if name
            and not name.startswith(_NON_CHAT_PREFIXES)
            and not _is_embedding_gguf(name)
        ),
        None,
    )
    amy_id = by_name.get("piper-amy-en")
    ryan_id = by_name.get("piper-ryan-en")
    if not (chat_id and amy_id and ryan_id):
        log.info(
            "Skipping episode profile registration: missing chat_id/amy_id/ryan_id"
        )
        return

    created = 0
    skipped = 0
    for preset in _PRESETS:
        if preset["name"] in existing:
            skipped += 1
            continue
        payload = {
            "name": preset["name"],
            "description": preset["description"],
            "chat_model_id": chat_id,
            "speakers": [
                {"name": "Alex", "role": "Host", "tts_model_id": amy_id},
                {"name": "Sam", "role": "Co-host", "tts_model_id": ryan_id},
            ],
            "default_length_minutes": preset["default_length_minutes"],
            "default_briefing": preset["default_briefing"],
            "num_segments": preset["num_segments"],
        }
        try:
            r = client.post("/api/episode_profiles", json=payload)
            if r.status_code in (200, 201):
                log.info("Created episode profile %r", preset["name"])
                created += 1
            else:
                log.warning(
                    "Could not create episode profile %r (HTTP %s): %s",
                    preset["name"],
                    r.status_code,
                    r.text[:200],
                )
        except Exception as exc:
            log.warning(
                "Could not create episode profile %r: %s", preset["name"], exc
            )

    log.info(
        "Episode profile preset library: %d created, %d skipped (already existed)",
        created,
        skipped,
    )
