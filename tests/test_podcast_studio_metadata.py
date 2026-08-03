"""Episode metadata must survive a retry without exposing source content."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.podcast_service import PodcastService
from api.routers.podcasts import (
    PodcastEpisodeResponse,
    _redacted_model_plan_receipts,
    _resolve_retry_selection,
    _retry_podcast_episode_locked,
    _selection_summary,
    cancel_podcast_episode,
    retry_podcast_episode,
)
from api.schemas.podcast_studio import (
    PodcastEditorialBrief,
    PodcastSelectionPreviewEntryResponse,
    PodcastSelectionPreviewResponse,
    PodcastStageModelPlanResponse,
)
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


def test_selection_summary_v2_keeps_validated_refs_and_normalized_settings_path_free() -> None:
    preview = PodcastSelectionPreviewResponse(
        selection_fingerprint="b" * 64,
        entries=[
            PodcastSelectionPreviewEntryResponse(
                stable_id="knowledge_engine_document:research",
                title="Private source title",
                authority_kind="external_read_only",
                relative_locator="Research/Private.md",
                revision_id="knowledge_engine_revision:one",
                fingerprint="c" * 64,
                state="included",
                reason="included",
                estimated_characters=42,
            )
        ],
        included_characters=42,
        requires_batch_engine=False,
        current_worker_eligible=True,
        blocked_reasons=[],
    )

    summary = _selection_summary(
        preview,
        selections=[
            {
                "kind": "knowledge_document",
                "document_id": "knowledge_engine_document:research",
                "expected_revision_id": "knowledge_engine_revision:one",
            }
        ],
        mode="critique",
        custom_prompt="  Keep the evidence bounded.  ",
        episode_length="long",
        review_outline=True,
    )

    assert summary["version"] == 2
    assert summary["included_items"] == [
        {
            "stable_id": "knowledge_engine_document:research",
            "authority_kind": "external_read_only",
            "revision_id": "knowledge_engine_revision:one",
            "fingerprint": "c" * 64,
        }
    ]
    assert summary["selections"] == [
        {
            "kind": "knowledge_document",
            "document_id": "knowledge_engine_document:research",
            "expected_revision_id": "knowledge_engine_revision:one",
        }
    ]
    assert summary["production_settings"] == {
        "mode": "critique",
        "episode_length": "long",
        "review_outline": True,
    }
    assert "custom_prompt" not in summary["production_settings"]
    serialized = str(summary)
    assert "Private source title" not in serialized
    assert "Research/Private.md" not in serialized
    assert "/Users/" not in serialized


def test_selection_summary_rejects_unsafe_included_receipt_ids() -> None:
    preview = PodcastSelectionPreviewResponse(
        selection_fingerprint="b" * 64,
        entries=[
            PodcastSelectionPreviewEntryResponse(
                stable_id="/Users/Antman/private.md",
                title="Unsafe",
                authority_kind="external_read_only",
                revision_id=None,
                fingerprint="c" * 64,
                state="included",
                reason="included",
                estimated_characters=1,
            )
        ],
        included_characters=1,
        requires_batch_engine=False,
        current_worker_eligible=True,
        blocked_reasons=[],
    )
    with pytest.raises(ValueError, match="path-free"):
        _selection_summary(
            preview,
            selections=[{"kind": "notebook", "notebook_id": "notebook:one"}],
        )


def test_redacted_receipts_preserve_prose_but_remove_embedded_paths() -> None:
    plans = [
        PodcastStageModelPlanResponse(
            role="podcast_outline",
            outcome="ready",
            model_id="/Users/Antman/models/secret.gguf",
            provider="openai_compatible",
            resource_tier="standard",
            selection_source="automatic",
            reason="pros/cons and HTTPS://example.test stay readable; /Users/Antman/models/secret.gguf is private",
            blocked_reason=None,
            override_choices=[],
        )
    ]
    receipt = _redacted_model_plan_receipts(plans)[0]
    assert "model_id" not in receipt
    assert "pros/cons" in receipt["reason"]
    assert "HTTPS://example.test" in receipt["reason"]
    assert "/Users/Antman/models/secret.gguf" not in receipt["reason"]


def test_episode_response_has_safe_legacy_metadata_defaults() -> None:
    response = PodcastEpisodeResponse(
        id="episode:legacy",
        name="Legacy",
        episode_profile={},
        speaker_profile={},
        briefing="brief",
    )
    assert response.selection_summary is None
    assert response.selection_fingerprint is None
    assert response.editorial_brief is None
    assert response.model_plan_receipts == []


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


@pytest.mark.asyncio
async def test_retry_submission_failure_preserves_old_episode_and_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    episode = _RetryEpisode()
    audio = tmp_path / "episodes" / "uuid" / "episode.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"old audio")
    episode.audio_file = str(audio)

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        raise RuntimeError("provider unavailable")

    import api.routers.podcasts as podcasts_router

    monkeypatch.setattr(podcasts_router, "_AUDIO_ROOT", tmp_path / "episodes")
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    with pytest.raises(Exception):
        await _retry_podcast_episode_locked("episode:failed")

    assert episode.deleted is False
    assert audio.exists()
    assert audio.read_bytes() == b"old audio"


@pytest.mark.asyncio
async def test_matching_retry_submits_before_deleting_the_old_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    events: list[str] = []

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        events.append(f"submit:deleted={episode.deleted}")
        return "command:retry"

    async def delete() -> None:
        events.append("delete")
        episode.deleted = True

    episode.delete = delete  # type: ignore[method-assign]

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    result = await _retry_podcast_episode_locked("episode:failed")

    assert result["job_id"] == "command:retry"
    assert events == ["submit:deleted=False", "delete"]


@pytest.mark.asyncio
async def test_route_retry_lock_prevents_duplicate_concurrent_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    episode_id = "episode:serialized"
    submit_started = asyncio.Event()
    release_submit = asyncio.Event()
    calls = 0

    async def get_episode(_: str) -> _RetryEpisode:
        if episode.deleted:
            raise HTTPException(status_code=404, detail="Episode not found")
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        nonlocal calls
        calls += 1
        submit_started.set()
        await release_submit.wait()
        return "command:serialized"

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    first = asyncio.create_task(retry_podcast_episode(object(), episode_id))
    await submit_started.wait()
    second = asyncio.create_task(retry_podcast_episode(object(), episode_id))
    release_submit.set()
    first_result, second_result = await asyncio.gather(
        first, second, return_exceptions=True
    )

    assert first_result == {
        "job_id": "command:serialized",
        "message": "Retry submitted successfully",
    }
    assert isinstance(second_result, HTTPException)
    assert second_result.status_code == 404
    assert calls == 1
    assert episode.deleted is True


@pytest.mark.asyncio
async def test_changed_selection_returns_preview_required_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.selection_summary = {
        "version": 2,
        "total_count": 1,
        "included_count": 1,
        "authority_counts": {"external_read_only": 1},
        "included_items": [
            {
                "stable_id": "knowledge_engine_document:research",
                "authority_kind": "external_read_only",
                "revision_id": "knowledge_engine_revision:one",
                "fingerprint": "a" * 64,
            }
        ],
        "selections": [
            {
                "kind": "knowledge_document",
                "document_id": "knowledge_engine_document:research",
                "expected_revision_id": "knowledge_engine_revision:one",
            }
        ],
        "production_settings": {
            "mode": "deep_dive",
            "custom_prompt": None,
            "episode_length": None,
            "review_outline": False,
        },
    }
    episode.selection_fingerprint = "a" * 64
    episode.deleted = False
    calls = {"submit": 0}

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        calls["submit"] += 1
        return "command:retry"

    async def changed_selection(*args, **kwargs):
        return {
            "status": "preview_required",
            "code": "podcast_selection_changed",
            "episode_id": "episode:failed",
            "message": "The selected source changed. Review it before retrying.",
            "selections": [
                {
                    "kind": "knowledge_document",
                    "document_id": "knowledge_engine_document:research",
                    "expected_revision_id": None,
                }
            ],
        }

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    monkeypatch.setattr(podcasts_router, "_resolve_retry_selection", changed_selection)

    result = await _retry_podcast_episode_locked("episode:failed")

    assert result["status"] == "preview_required"
    assert result["selections"][0]["expected_revision_id"] is None
    assert calls["submit"] == 0
    assert episode.deleted is False


def _v2_retry_summary(*, mode: str = "debate", episode_length: str = "long") -> dict[str, object]:
    return {
        "version": 2,
        "total_count": 1,
        "included_count": 1,
        "authority_counts": {"external_read_only": 1},
        "included_items": [{
            "stable_id": "knowledge_engine_document:research",
            "authority_kind": "external_read_only",
            "revision_id": "knowledge_engine_revision:one",
            "fingerprint": "a" * 64,
        }],
        "selections": [{
            "kind": "knowledge_document",
            "document_id": "knowledge_engine_document:research",
            "expected_revision_id": "knowledge_engine_revision:one",
        }],
        "production_settings": {
            "mode": mode,
            "episode_length": episode_length,
            "review_outline": True,
        },
    }


def _retry_preview(*, fingerprint: str, eligible: bool = True):
    from types import SimpleNamespace

    return SimpleNamespace(
        preview=PodcastSelectionPreviewResponse(
            selection_fingerprint=fingerprint,
            entries=[
                PodcastSelectionPreviewEntryResponse(
                    stable_id="knowledge_engine_document:research",
                    title="Current research",
                    authority_kind="external_read_only",
                    relative_locator="Research/Private.md",
                    revision_id="knowledge_engine_revision:two",
                    fingerprint="d" * 64,
                    state="included" if eligible else "changed",
                    reason="included" if eligible else "source_revision_changed",
                    estimated_characters=5,
                )
            ],
            included_characters=5,
            requires_batch_engine=False,
            current_worker_eligible=eligible,
            blocked_reasons=[] if eligible else ["podcast_selection_requires_refresh"],
        )
    )


@pytest.mark.asyncio
async def test_actual_v2_changed_fingerprint_returns_preview_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:changed-real"
    episode.selection_summary = _v2_retry_summary()
    episode.selection_fingerprint = "a" * 64

    async def preparation(*args, **kwargs):
        return _retry_preview(fingerprint="d" * 64, eligible=False)

    monkeypatch.setattr(
        podcasts_router,
        "_podcast_selection_preparation",
        preparation,
    )

    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_changed"
    assert result.selections[0].expected_revision_id is None
    assert episode.deleted is False


@pytest.mark.asyncio
async def test_tampered_v2_summary_count_mismatch_fails_closed() -> None:
    episode = _RetryEpisode()
    episode.id = "episode:tampered-counts"
    summary = _v2_retry_summary()
    summary["included_count"] = 0
    episode.selection_summary = summary

    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_tampered"
    assert result.selections == []


@pytest.mark.asyncio
async def test_actual_v2_matching_retry_replays_settings_and_submits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:matching-real"
    episode.selection_summary = _v2_retry_summary(mode="critique", episode_length="short")
    episode.selection_fingerprint = "d" * 64
    submitted: list[dict[str, object]] = []

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        submitted.append(kwargs)
        return "command:v2-retry"

    async def preparation(*args, **kwargs):
        return _retry_preview(fingerprint="d" * 64, eligible=True)

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    monkeypatch.setattr(podcasts_router, "_podcast_selection_preparation", preparation)

    result = await _retry_podcast_episode_locked("episode:matching-real", request=object())

    assert result["job_id"] == "command:v2-retry"
    assert len(submitted) == 1
    assert submitted[0]["mode"] == "critique"
    assert submitted[0]["episode_length"] == "short"
    assert submitted[0]["review_outline"] is True
    assert episode.deleted is True


@pytest.mark.asyncio
async def test_retry_selection_http_unavailability_is_typed_preview_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:unavailable"
    episode.selection_summary = _v2_retry_summary()

    async def unavailable(*args, **kwargs):
        raise HTTPException(status_code=503, detail={"code": "unavailable"})

    monkeypatch.setattr(podcasts_router, "_podcast_selection_preparation", unavailable)
    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_unavailable"
    assert result.selections[0].document_id == "knowledge_engine_document:research"


@pytest.mark.asyncio
async def test_cancellation_retains_all_episode_metadata_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    before = {
        "selection_summary": episode.selection_summary,
        "selection_fingerprint": episode.selection_fingerprint,
        "editorial_brief": episode.editorial_brief,
        "model_plan_receipts": episode.model_plan_receipts,
    }
    saved: list[dict[str, object]] = []

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def save() -> None:
        saved.append({key: getattr(episode, key) for key in before})

    async def detail() -> dict[str, str]:
        return {"status": "running", "error_message": ""}

    episode.get_job_detail = detail  # type: ignore[method-assign]
    episode.save = save  # type: ignore[method-assign]
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)

    result = await cancel_podcast_episode("episode:running")

    assert result["message"] == "Cancellation requested"
    assert saved == [{**before}]
    assert episode.cancel_requested is True
