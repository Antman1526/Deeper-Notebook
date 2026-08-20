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

from deeper_notebook.podcasts.profile_names import (
    equivalent_episode_profile_names,
)
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
        "name": "Deeper Notebook Local",
        "description": "Two-voice podcast using local Piper TTS",
        "num_segments": 5,
        "default_length_minutes": 5,
        # v0.7.149 — every preset MUST reference a speaker profile by name
        # (the backend's EpisodeProfileCreate schema requires speaker_config
        # as a required string field). The 4 candidates registered by
        # desktop/auto_register/speaker_profile.py are: Local Duo, Local
        # Solo, Local Debate, Local Interview. We map each episode preset
        # to the speaker profile that best fits its format.
        "speaker_profile": "Local Duo",
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
        "speaker_profile": "Local Duo",
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
        "speaker_profile": "Local Duo",
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
        # Local Debate's speakers have baked-in Pro/Skeptic personalities;
        # this is the natural fit.
        "speaker_profile": "Local Debate",
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
        "speaker_profile": "Local Duo",
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
        "speaker_profile": "Local Duo",
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
        "speaker_profile": "Local Duo",
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
        # Local Interview's speakers have baked-in Interviewer/Expert
        # backstories that match this format exactly.
        "speaker_profile": "Local Interview",
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
        "speaker_profile": "Local Duo",
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

    v0.7.149 — Payload rewritten to match the backend Pydantic schema
    (`api/routers/episode_profiles.py:EpisodeProfileCreate`). The
    previous payload sent `chat_model_id` + `speakers: [...]` which
    the schema doesn't accept; the missing `speaker_config` field made
    every POST return HTTP 422 and the whole preset library failed to
    register on every launch. Now we map each preset to a speaker
    profile by name (referenced via `speaker_config: str`) and route
    the chat model through `outline_llm` + `transcript_llm` (the schema's
    actual model-reference fields).
    """
    try:
        r = client.get("/api/episode-profiles")
        r.raise_for_status()
        existing = {p.get("name") for p in r.json() if p.get("name")}
    except Exception as exc:
        log.warning(
            "Could not list episode profiles: %s — skipping preset bootstrap",
            exc,
        )
        return

    # v0.7.149 — Cross-check: only register an episode preset if its
    # referenced speaker profile actually exists. The speaker bootstrap
    # runs BEFORE this module (see auto_register/__init__ ordering) so
    # in the happy path all four are present. If any is missing (e.g.
    # piper voices weren't registered → speaker bootstrap skipped), we
    # downgrade the corresponding episode preset to "Local Duo" or skip
    # it entirely rather than 422 every launch.
    try:
        r_sp = client.get("/api/speaker-profiles")
        r_sp.raise_for_status()
        existing_speakers = {p.get("name") for p in r_sp.json() if p.get("name")}
    except Exception as exc:
        log.warning(
            "Could not list speaker profiles: %s — skipping episode preset bootstrap",
            exc,
        )
        return
    if not existing_speakers:
        log.info(
            "Skipping episode profile registration: no speaker profiles exist "
            "(speaker bootstrap may have skipped — check piper voice registration)"
        )
        return

    # Resolve a chat model to use as outline_llm + transcript_llm. If no
    # eligible chat model is registered, we still register the presets
    # (these are optional fields) — the user can pick a model in the UI
    # when they generate an episode.
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
    if chat_id is None:
        log.info(
            "No chat model resolved for episode presets — outline_llm + "
            "transcript_llm will be left blank (user picks at generation time)"
        )

    created = 0
    skipped = 0
    # v0.7.156 — Migration-seeded speaker profiles (from migration
    # 7.surrealql) are all hardcoded to `tts_provider=openai` +
    # `tts_model=gpt-4o-mini-tts`. On a Piper-only install with no
    # OpenAI credential, any episode preset bound to one of those will
    # 500 at podcast-generation TTS time. v0.7.149's "alphabetically-first
    # fallback" path would silently pick `business_panel` (the
    # alphabetically-first migration-seeded speaker) on a fresh install
    # where Local Duo isn't yet registered — producing nine podcast
    # presets that all break at generation time.
    #
    # Filter out the known-broken migration seeds from the fallback
    # candidate pool. If the LOCAL-* profiles aren't yet registered,
    # we'd rather skip the preset entirely (recoverable: re-run
    # auto-register once Piper voices come online) than bind it to
    # something that's guaranteed to 500 later.
    _MIGRATION_SEEDED_SPEAKERS_REQUIRING_OPENAI = {
        "tech_experts",
        "solo_expert",
        "business_panel",
    }
    safe_fallback_speakers = (
        existing_speakers - _MIGRATION_SEEDED_SPEAKERS_REQUIRING_OPENAI
    )

    degraded = 0
    skipped_no_speaker = 0
    for preset in _PRESETS:
        equivalent_names = {
            *equivalent_episode_profile_names(preset["name"]),
        }
        if existing & equivalent_names:
            skipped += 1
            continue
        # v0.7.149 — Fall back to "Local Duo" if the preset's preferred
        # speaker profile isn't registered (e.g. piper voices missing →
        # only the migration-seeded `tech_experts` etc exist, none of
        # which we want as defaults). If even Local Duo is missing,
        # try any existing LOCAL-* profile as last-resort, then skip.
        #
        # v0.7.156 — Last-resort fallback now uses safe_fallback_speakers
        # (migration seeds filtered out) instead of all existing_speakers,
        # so a fresh install never silently binds a preset to an OpenAI-
        # only seeded speaker.
        speaker_config = preset["speaker_profile"]
        if speaker_config not in existing_speakers:
            if "Local Duo" in existing_speakers:
                speaker_config = "Local Duo"
                degraded += 1
            else:
                # Pick the first available LOCAL-* speaker profile
                # alphabetically for deterministic test behavior.
                # Migration-seeded openai-only speakers are filtered out.
                fallback = (
                    sorted(safe_fallback_speakers)[0]
                    if safe_fallback_speakers
                    else None
                )
                if fallback is None:
                    log.warning(
                        "Skipping preset %r: no LOCAL-* speaker profile "
                        "available (only migration-seeded openai speakers "
                        "exist — re-run auto-register once Piper voices "
                        "are registered)",
                        preset["name"],
                    )
                    skipped_no_speaker += 1
                    continue
                speaker_config = fallback
                degraded += 1

        payload: dict[str, Any] = {
            "name": preset["name"],
            "description": preset["description"],
            "speaker_config": speaker_config,
            "default_briefing": preset["default_briefing"],
            "num_segments": preset["num_segments"],
        }
        # outline_llm + transcript_llm are Optional[str] in the schema —
        # only include them when we actually resolved a chat model.
        if chat_id is not None:
            payload["outline_llm"] = chat_id
            payload["transcript_llm"] = chat_id

        try:
            r = client.post("/api/episode-profiles", json=payload)
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
            log.warning("Could not create episode profile %r: %s", preset["name"], exc)

    log.info(
        "Episode profile preset library: %d created, %d skipped (already "
        "existed), %d created with degraded speaker_profile fallback, "
        "%d skipped (no safe speaker_profile available)",
        created,
        skipped,
        degraded,
        skipped_no_speaker,
    )
