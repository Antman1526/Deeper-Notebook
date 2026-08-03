"""Episode metadata must survive a retry without exposing source content."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.podcast_service import PodcastService
from api.routers.podcasts import _retry_podcast_episode_locked
from api.schemas.podcast_studio import PodcastEditorialBrief
from deeper_notebook.podcasts.models import EpisodeProfile, SpeakerProfile


class _RetryEpisode:
    name = "Research synthesis"
    episode_profile = {"name": "Local Episode"}
    speaker_profile = {"name": "Local Voice"}
    content = "The source body remains available only to the worker."
    audio_file = None
    briefing_suffix = "Keep this concise"
    mode = "deep_dive"
    custom_prompt = "Lead with the result"
    selection_summary = {
        "version": 1,
        "total_count": 2,
        "included_count": 2,
        "authority_counts": {"external_read_only": 2},
    }
    selection_fingerprint = "a" * 64
    editorial_brief = {
        "central_question": "What should change?",
        "audience": "expert",
        "purpose": "analyze",
        "format": "deep_dive",
        "target_minutes": 30,
        "required_takeaway": "Change the review threshold.",
        "include_unanswered_questions": True,
        "evidence_policy": "strict",
        "episode_profile_name": "Local Episode",
        "speaker_profile_name": "Local Voice",
        "outline": ["Context", "Decision"],
    }
    model_plan_receipts = [
        {
            "version": 1,
            "role": "podcast_outline",
            "outcome": "ready",
            "reason": "automatic selected the standard verified local candidate after all route gates.",
        }
    ]

    def __init__(self) -> None:
        self.deleted = False

    async def get_job_detail(self) -> dict[str, str]:
        return {"status": "failed", "error_message": "transient provider issue"}

    async def delete(self) -> None:
        self.deleted = True


def test_editorial_brief_rejects_an_absolute_path() -> None:
    with pytest.raises(ValidationError, match="filesystem path"):
        PodcastEditorialBrief(
            central_question="/Users/Antman/2nd Brains/Private.md",
            audience="Research team",
            outline=["Context"],
        )


@pytest.mark.asyncio
async def test_retry_replays_studio_metadata_on_the_new_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    calls: list[dict[str, object]] = []

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        calls.append(kwargs)
        return "command:retry"

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    result = await _retry_podcast_episode_locked("episode:failed")

    assert result == {"job_id": "command:retry", "message": "Retry submitted successfully"}
    assert episode.deleted is True
    assert len(calls) == 1
    assert calls[0]["selection_summary"] == episode.selection_summary
    assert calls[0]["selection_fingerprint"] == episode.selection_fingerprint
    assert calls[0]["editorial_brief"] == episode.editorial_brief
    assert calls[0]["model_plan_receipts"] == episode.model_plan_receipts
    assert calls[0]["content"] == episode.content
