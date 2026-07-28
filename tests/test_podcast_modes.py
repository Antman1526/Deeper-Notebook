"""Contracts for the closed, durable Audio Overview formats."""

from __future__ import annotations

import pytest


def test_overview_modes_are_closed_and_legacy_episodes_default_to_deep_dive():
    from deeper_notebook.podcasts.models import (
        PodcastOverviewMode,
        normalize_podcast_mode,
    )

    assert [mode.value for mode in PodcastOverviewMode] == [
        "deep_dive",
        "brief",
        "critique",
        "debate",
    ]
    assert normalize_podcast_mode(None) is PodcastOverviewMode.DEEP_DIVE
    assert normalize_podcast_mode("deep_dive") is PodcastOverviewMode.DEEP_DIVE
    with pytest.raises(ValueError, match="Unsupported podcast overview mode"):
        normalize_podcast_mode("interview")


def test_every_mode_has_a_deterministic_generation_contract():
    from deeper_notebook.podcasts.models import (
        PodcastOverviewMode,
        get_podcast_mode_spec,
    )

    for mode in PodcastOverviewMode:
        spec = get_podcast_mode_spec(mode)
        assert spec.speaker_count in (1, 2)
        assert 1 <= spec.min_segments <= spec.max_segments <= 20
        assert spec.min_duration_minutes <= spec.max_duration_minutes
        assert spec.outline_schema
        assert spec.prompt_contract

    assert get_podcast_mode_spec("brief").speaker_count == 1
    assert get_podcast_mode_spec("debate").speaker_count == 2


def test_episode_persists_mode_custom_prompt_and_typed_transcript_segments():
    from deeper_notebook.podcasts.models import PodcastEpisode

    legacy = PodcastEpisode(
        name="Legacy", episode_profile={}, speaker_profile={}, briefing="b", content="c"
    )
    assert legacy.mode == "deep_dive"

    episode = PodcastEpisode(
        name="Debate",
        episode_profile={},
        speaker_profile={},
        briefing="b",
        content="c",
        mode="debate",
        custom_prompt="Give each position its strongest evidence.",
        transcript_segments=[
            {
                "start_seconds": 0,
                "end_seconds": 12.5,
                "speaker": "Host",
                "text": "Opening question",
                "citation_ids": ["source:one"],
            }
        ],
    )
    assert episode.mode == "debate"
    assert episode.custom_prompt == "Give each position its strongest evidence."
    assert episode.transcript_segments[0].citation_ids == ["source:one"]

    with pytest.raises(ValueError, match="end_seconds"):
        PodcastEpisode(
            name="Bad segment",
            episode_profile={},
            speaker_profile={},
            briefing="b",
            content="c",
            transcript_segments=[
                {
                    "start_seconds": 10,
                    "end_seconds": 2,
                    "speaker": "Host",
                    "text": "Impossible",
                }
            ],
        )


def test_generation_request_uses_closed_mode_and_keeps_legacy_suffix_compatible():
    from api.podcast_service import PodcastGenerationRequest

    request = PodcastGenerationRequest(
        episode_profile="episode",
        speaker_profile="speakers",
        episode_name="Brief",
        content="source text",
        mode="brief",
        custom_prompt="Prioritize decisions.",
    )
    assert request.mode.value == "brief"
    assert request.custom_prompt == "Prioritize decisions."

    legacy = PodcastGenerationRequest(
        episode_profile="episode",
        speaker_profile="speakers",
        episode_name="Legacy",
        content="source text",
        briefing_suffix="Keep it concise.",
    )
    assert legacy.mode.value == "deep_dive"
    assert legacy.resolved_custom_prompt == "Keep it concise."

    with pytest.raises(ValueError):
        PodcastGenerationRequest(
            episode_profile="episode",
            speaker_profile="speakers",
            episode_name="Bad",
            content="source text",
            mode="unknown",
        )


def test_submission_threads_mode_and_custom_prompt_to_the_durable_command(monkeypatch):
    import api.podcast_service as service_module
    from api.podcast_service import PodcastService

    async def local_resolver():
        return ("openai_compatible", "local", {})

    async def episode_profile(_name):
        return type(
            "EpisodeProfile",
            (),
            {
                "resolve_outline_config": local_resolver,
                "resolve_transcript_config": local_resolver,
            },
        )()

    async def speaker_profile(_name):
        return type(
            "SpeakerProfile",
            (),
            {"resolve_tts_config": local_resolver, "speakers": [{}, {}]},
        )()

    captured: dict[str, object] = {}

    def submit(_app, _command, arguments):
        captured.update(arguments)
        return "command:podcast"

    monkeypatch.setattr(service_module.EpisodeProfile, "get_by_name", episode_profile)
    monkeypatch.setattr(service_module.SpeakerProfile, "get_by_name", speaker_profile)
    monkeypatch.setattr(service_module, "submit_command", submit)

    import asyncio

    job_id = asyncio.run(
        PodcastService.submit_generation_job(
            episode_profile_name="episode",
            speaker_profile_name="speakers",
            episode_name="Debate",
            content="source text",
            mode="debate",
            custom_prompt="Use the strongest evidence on both sides.",
        )
    )
    assert job_id == "command:podcast"
    assert captured["mode"] == "debate"
    assert captured["custom_prompt"] == "Use the strongest evidence on both sides."


def test_transcript_metadata_normalizes_legacy_dialogue_without_inventing_citations():
    from deeper_notebook.podcasts.models import transcript_segments_from_payload

    segments = transcript_segments_from_payload(
        [
            {"speaker": "Host", "text": "First point."},
            {"speaker": "Guest", "content": "Response."},
        ],
        mode="critique",
    )

    assert [segment.speaker for segment in segments] == ["Host", "Guest"]
    assert segments[0].start_seconds == 0
    assert segments[0].end_seconds <= segments[1].start_seconds
    assert segments[0].citation_ids == []
