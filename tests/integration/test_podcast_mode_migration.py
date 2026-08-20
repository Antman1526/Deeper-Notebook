"""Real-SurrealDB durability check for Audio Overview mode fields.

Run with SURREAL_INTEGRATION=1. The shared integration fixture creates a
throwaway namespace, applies all migrations, and removes it on teardown.
"""

from __future__ import annotations

import pytest

from deeper_notebook.podcasts.models import PodcastEpisode

pytestmark = pytest.mark.integration_surreal


@pytest.mark.asyncio
async def test_mode_prompt_and_transcript_segments_survive_outline_retry_and_reload(
    clean_namespace,
):
    episode = PodcastEpisode(
        name="Durable debate",
        episode_profile={"name": "profile"},
        speaker_profile={"name": "speakers"},
        briefing="debate briefing",
        content="source text",
        mode="debate",
        custom_prompt="Represent both positions fairly.",
        transcript_segments=[
            {
                "start_seconds": 0,
                "end_seconds": 8,
                "speaker": "Host A",
                "text": "Case for the proposal.",
                "citation_ids": ["source:a"],
            }
        ],
    )
    await episode.save()

    reloaded = await PodcastEpisode.get(str(episode.id))
    assert reloaded is not None
    assert reloaded.mode == "debate"
    assert reloaded.custom_prompt == "Represent both positions fairly."
    assert reloaded.transcript_segments[0].citation_ids == ["source:a"]

    # Outline approval/resume mutates the same durable record. This is the
    # data path used after the process restarts between outline review and TTS.
    reloaded.generation_stage = "awaiting_review"
    reloaded.outline = {
        "segments": [{"name": "Question", "description": "Frame it", "size": "short"}]
    }
    await reloaded.save()
    after_outline_review = await PodcastEpisode.get(str(episode.id))
    assert after_outline_review.mode == "debate"
    assert after_outline_review.custom_prompt == "Represent both positions fairly."

    # Retry creates a fresh command record while replaying the exact durable
    # fields. Reloading it is the same repository path used after app restart.
    retry = PodcastEpisode(
        name=after_outline_review.name,
        episode_profile=after_outline_review.episode_profile,
        speaker_profile=after_outline_review.speaker_profile,
        briefing=after_outline_review.briefing,
        content=after_outline_review.content,
        mode=after_outline_review.mode,
        custom_prompt=after_outline_review.custom_prompt,
        transcript_segments=after_outline_review.transcript_segments,
    )
    await retry.save()
    reloaded_retry = await PodcastEpisode.get(str(retry.id))
    assert reloaded_retry.mode == "debate"
    assert reloaded_retry.custom_prompt == "Represent both positions fairly."
