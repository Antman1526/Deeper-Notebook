"""v0.8.68 — staged podcast generation runner.

podcast-creator's `create_podcast()` is a black box: one awaited call, no
progress, no cancellation. But the library EXPORTS its compiled LangGraph
(`podcast_graph`) with four named nodes (generate_outline →
generate_transcript → generate_all_audio → combine_audio), so this module
re-implements only the thin setup layer around it and streams the graph
instead of invoking it. That unlocks, with zero forking:

  - per-stage progress (episode.generation_stage updated as nodes finish),
  - cooperative cancellation (a watcher polls episode.cancel_requested and
    cancels the in-flight graph task),
  - stage-aware timeouts (the error names the stage that hung),
  - outline-review-before-TTS (run the outline node alone, then resume from
    the transcript node with a user-edited outline via `resume_graph`).

Upgrade guard: tests/test_v0_8_68_podcast_staged.py pins the node names —
if a podcast-creator upgrade renames them, the suite fails loudly instead
of stages silently going dark.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from loguru import logger
from podcast_creator import (
    PodcastState,
    load_episode_config,
    load_speaker_config,
    podcast_graph,
    resolve_language_name,
)
from podcast_creator.core import Outline
from podcast_creator.nodes import (
    combine_audio_node,
    generate_all_audio_node,
    generate_outline_node,
    generate_transcript_node,
    route_audio_generation,
)

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.podcasts.models import (
    STAGE_AUDIO,
    STAGE_COMBINE,
    STAGE_OUTLINE,
    STAGE_TRANSCRIPT,
    PodcastOverviewMode,
    get_podcast_mode_spec,
    normalize_podcast_mode,
)

# Stage transition map: when node X completes, the run is now in stage Y.
# (combine_audio completing means the run is done — stage cleared by caller.)
NODE_DONE_NEXT_STAGE: dict[str, Optional[str]] = {
    "generate_outline": STAGE_TRANSCRIPT,
    "generate_transcript": STAGE_AUDIO,
    "generate_all_audio": STAGE_COMBINE,
    "combine_audio": None,
}


class CancelledByUser(Exception):
    """The user hit Cancel — distinct from timeouts and provider errors."""


_resume_graph = None


def get_full_graph():
    return podcast_graph


def get_resume_graph():
    """Compiled graph that starts at the TRANSCRIPT node — used to resume a
    generation after the user reviewed/edited the outline. Reuses the
    library's own node functions and conditional routing, so behavior is
    identical to the tail of the full graph."""
    global _resume_graph
    if _resume_graph is None:
        wf = StateGraph(PodcastState)
        wf.add_node("generate_transcript", generate_transcript_node)
        wf.add_node("generate_all_audio", generate_all_audio_node)
        wf.add_node("combine_audio", combine_audio_node)
        wf.add_edge(START, "generate_transcript")
        wf.add_conditional_edges(
            "generate_transcript", route_audio_generation, ["generate_all_audio"]
        )
        wf.add_edge("generate_all_audio", "combine_audio")
        wf.add_edge("combine_audio", END)
        _resume_graph = wf.compile()
    return _resume_graph


# v0.8.86 — per-episode length control (improvement roadmap, Batch 3). Maps a
# short/medium/long choice to a segment count, overriding the profile's
# num_segments for this one episode (values stay within the profile validator's
# 3-20 range). Unknown/None → no override (use the profile default).
_LENGTH_TO_SEGMENTS = {"short": 3, "medium": 5, "long": 8}


def segments_for_length(episode_length: Optional[str]) -> Optional[int]:
    if not episode_length:
        return None
    return _LENGTH_TO_SEGMENTS.get(episode_length.strip().lower())


def segments_for_overview_mode(
    mode: PodcastOverviewMode | str | None,
    episode_length: Optional[str],
    profile_segments: int,
) -> int:
    """Apply a requested short/medium/long value inside a mode's bounds.

    The profile remains the user-owned default. A mode never produces an
    outline outside its own schema contract, even when an older profile was
    configured with a broader segment count.
    """
    spec = get_podcast_mode_spec(mode)
    requested = segments_for_length(episode_length) or profile_segments
    return max(spec.min_segments, min(spec.max_segments, requested))


def speaker_profile_for_overview_mode(
    speaker_profile: Any,
    mode: PodcastOverviewMode | str | None,
) -> Any:
    """Use the exact number of voices promised by the selected format."""
    spec = get_podcast_mode_spec(mode)
    speakers = list(getattr(speaker_profile, "speakers", []))
    if len(speakers) < spec.speaker_count:
        raise ValueError(
            f"Audio Overview format '{normalize_podcast_mode(mode).value}' requires "
            f"{spec.speaker_count} speakers, but the selected profile has {len(speakers)}."
        )
    if len(speakers) == spec.speaker_count:
        return speaker_profile
    return speaker_profile.model_copy(
        update={"speakers": speakers[: spec.speaker_count]}
    )


def build_state_and_config(
    *,
    content: str,
    briefing: str,
    episode_profile_name: str,
    speaker_profile_name: str,
    language: Optional[str],
    output_dir: str,
    episode_name: str,
    outline: Optional[dict] = None,
    episode_length: Optional[str] = None,
    mode: PodcastOverviewMode | str | None = None,
    custom_prompt: Optional[str] = None,
) -> tuple[dict, dict]:
    """Mirror of create_podcast()'s setup for OUR call shape (explicit
    briefing + episode_profile, which the upstream function treats as
    'briefing overrides everything'). Requires configure('episode_config'/
    'speakers_config', ...) to have been called first — same precondition
    the create_podcast path had."""
    episode_config = load_episode_config(episode_profile_name)
    speaker_profile = load_speaker_config(
        speaker_profile_name or episode_config.speaker_config
    )
    resolved_language = resolve_language_name(language) if language else None
    normalized_mode = normalize_podcast_mode(mode)
    speaker_profile = speaker_profile_for_overview_mode(
        speaker_profile, normalized_mode
    )
    # The overview mode owns the allowable outline range; the familiar
    # short/medium/long control remains a bounded preference inside it.
    num_segments = segments_for_overview_mode(
        normalized_mode, episode_length, episode_config.num_segments
    )

    state: PodcastState = {
        "content": content,
        "briefing": briefing,
        "num_segments": num_segments,
        "language": resolved_language,
        "outline": (
            Outline.model_validate(outline) if isinstance(outline, dict) else outline
        ),
        "transcript": [],
        "audio_clips": [],
        "final_output_file_path": None,
        "output_dir": Path(output_dir),
        "episode_name": episode_name,
        "speaker_profile": speaker_profile,
        # podcast-creator safely ignores unknown state keys. Keeping this
        # metadata beside the graph state makes a resumed job auditable and
        # preserves the exact format request for custom nodes/providers.
        "overview_mode": normalized_mode.value,
        "custom_prompt": custom_prompt,
    }
    config = {
        "configurable": {
            "outline_provider": episode_config.outline_provider,
            "outline_model": episode_config.outline_model,
            "transcript_provider": episode_config.transcript_provider,
            "transcript_model": episode_config.transcript_model,
            "outline_config": episode_config.outline_config,
            "transcript_config": episode_config.transcript_config,
        }
    }
    return state, config


async def generate_outline_only(state: dict, config: dict) -> dict:
    """Phase 1 of the review workflow: run just the outline node."""
    return await generate_outline_node(state, config)


async def _cancel_requested(episode_id: Any) -> bool:
    """Poll the episode's cancel flag. Fail-open (False) on any DB hiccup —
    a flaky read must never abort a 20-minute generation."""
    try:
        rows = await repo_query(
            "SELECT cancel_requested FROM ONLY $id",
            {"id": ensure_record_id(str(episode_id))},
        )
        if isinstance(rows, list):
            rows = rows[0] if rows else {}
        return bool(rows.get("cancel_requested")) if isinstance(rows, dict) else False
    except Exception as exc:
        logger.debug(f"cancel-flag poll failed (non-fatal): {exc}")
        return False


async def run_graph_with_stages(
    graph_obj: Any,
    state: dict,
    config: dict,
    *,
    episode: Any,
    deadline: float,
    poll_interval: float = 5.0,
) -> dict:
    """Stream the graph, updating episode.generation_stage as nodes finish,
    while watching the cancel flag and the wall-clock deadline.

    Returns the merged node outputs (final_output_file_path, transcript,
    outline, ...) — the same keys create_podcast()'s final state carried.

    Raises CancelledByUser on a user cancel and asyncio.TimeoutError past
    the deadline; both cancel the in-flight graph task first.
    """
    merged: dict = {}

    async def _consume() -> None:
        async for update in graph_obj.astream(
            state, config=config, stream_mode="updates"
        ):
            for node_name, node_out in update.items():
                if isinstance(node_out, dict):
                    merged.update(node_out)
                next_stage = NODE_DONE_NEXT_STAGE.get(node_name)
                # The audio node fires once per dialogue line (Send fan-out);
                # only write the stage transition once.
                if next_stage and episode.generation_stage != next_stage:
                    episode.generation_stage = next_stage
                    try:
                        await episode.save()
                    except Exception as exc:
                        logger.warning(f"stage update save failed (non-fatal): {exc}")

    task = asyncio.create_task(_consume())
    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=poll_interval)
            if task in done:
                task.result()  # surface any generation exception
                break
            if time.monotonic() > deadline:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise asyncio.TimeoutError()
            if await _cancel_requested(episode.id):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise CancelledByUser()
    finally:
        if not task.done():
            task.cancel()
    return merged
