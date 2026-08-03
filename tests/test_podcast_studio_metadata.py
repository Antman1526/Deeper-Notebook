"""Episode metadata must survive a retry without exposing source content."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.podcast_service import (
    PodcastService,
    PodcastSubmissionNotCreatedError,
    PodcastSubmissionUncertainError,
)
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
    id = "episode:failed"
    name = "Research synthesis"
    episode_profile = {"name": "Local Episode"}
    speaker_profile = {"name": "Local Voice"}
    content = "The source body remains available only to the worker."
    audio_file = None
    briefing_suffix = "Keep this concise"
    mode = "deep_dive"
    custom_prompt = "Lead with the result"
    command = "command:old"
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
            "resource_tier": "standard",
            "selection_source": "automatic",
            "reason": "route_ready",
        }
    ]
    retry_submitted = None

    def __init__(self) -> None:
        self.deleted = False
        self.saved = False

    async def get_job_detail(self) -> dict[str, str]:
        return {"status": "failed", "error_message": "transient provider issue"}

    async def delete(self) -> None:
        self.deleted = True

    async def save(self) -> None:
        self.saved = True


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
    assert set(receipt) == {
        "version",
        "role",
        "outcome",
        "resource_tier",
        "selection_source",
        "reason",
    }
    assert receipt == {
        "version": 1,
        "role": "podcast_outline",
        "outcome": "ready",
        "resource_tier": "standard",
        "selection_source": "automatic",
        "reason": "route_ready",
    }


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
    attempts = 0

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PodcastSubmissionNotCreatedError(RuntimeError("provider unavailable"))
        return "command:recovered"

    import api.routers.podcasts as podcasts_router

    monkeypatch.setattr(podcasts_router, "_AUDIO_ROOT", tmp_path / "episodes")
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    with pytest.raises(Exception):
        await _retry_podcast_episode_locked("episode:failed")

    assert episode.deleted is False
    assert episode.retry_submitted is None
    assert audio.exists()
    assert audio.read_bytes() == b"old audio"

    result = await _retry_podcast_episode_locked("episode:failed")

    assert result["job_id"] == "command:recovered"
    assert attempts == 2
    assert episode.deleted is True


@pytest.mark.asyncio
async def test_retry_exact_legacy_submitted_marker_reuses_job_without_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    episode.retry_submitted = {"job_id": "command:legacy", "generation": 3}
    submissions = 0

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def submit_generation_job(**kwargs) -> str:
        nonlocal submissions
        submissions += 1
        return "command:unexpected"

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    result = await _retry_podcast_episode_locked("episode:legacy")

    assert result == {
        "job_id": "command:legacy",
        "message": "Retry already submitted successfully",
    }
    assert submissions == 0


@pytest.mark.asyncio
async def test_retry_rejects_legacy_marker_with_extra_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    episode.retry_submitted = {
        "job_id": "command:legacy",
        "generation": 3,
        "token": "must-not-be-accepted",
    }

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)

    with pytest.raises(HTTPException, match="Failed to retry episode"):
        await _retry_podcast_episode_locked("episode:legacy")


@pytest.mark.asyncio
async def test_retry_uncertain_submit_keeps_reservation_across_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: dict[str, object] = {"retry_submitted": None}
    submissions = 0

    class ReloadedEpisode(_RetryEpisode):
        def __init__(self) -> None:
            super().__init__()
            self.retry_submitted = persisted["retry_submitted"]

        async def save(self) -> None:
            marker = self.retry_submitted
            persisted["retry_submitted"] = (
                marker.model_dump(mode="json") if marker is not None else None
            )

    async def get_episode(_: str) -> _RetryEpisode:
        return ReloadedEpisode()

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        nonlocal submissions
        submissions += 1
        raise PodcastSubmissionUncertainError(TimeoutError("submit timed out"))

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    with pytest.raises(HTTPException, match="state is uncertain"):
        await _retry_podcast_episode_locked("episode:uncertain")
    with pytest.raises(HTTPException, match="state is uncertain"):
        await _retry_podcast_episode_locked("episode:uncertain")

    assert submissions == 1


@pytest.mark.asyncio
async def test_retry_definite_failure_clear_save_failure_keeps_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _RetryEpisode()
    saves = 0
    submissions = 0

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def save() -> None:
        nonlocal saves
        saves += 1
        if saves == 2:
            raise RuntimeError("reservation clear failed")

    async def submit_generation_job(**kwargs) -> str:
        nonlocal submissions
        submissions += 1
        raise PodcastSubmissionNotCreatedError(RuntimeError("not submitted"))

    episode.save = save  # type: ignore[method-assign]
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    with pytest.raises(HTTPException, match="could not be cleared") as first:
        await _retry_podcast_episode_locked("episode:failed")

    assert first.value.status_code == 409
    assert episode.retry_submitted.state == "reserved"

    with pytest.raises(HTTPException, match="state is uncertain"):
        await _retry_podcast_episode_locked("episode:failed")

    assert submissions == 1


@pytest.mark.asyncio
async def test_podcast_service_classifies_precommand_rejection_as_not_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.podcast_service as service_module

    async def missing_profile(_: str) -> None:
        return None

    def unexpected_submit(*args, **kwargs):
        raise AssertionError("pre-command rejection must not invoke submit_command")

    monkeypatch.setattr(service_module.EpisodeProfile, "get_by_name", missing_profile)
    monkeypatch.setattr(service_module, "submit_command", unexpected_submit)

    with pytest.raises(PodcastSubmissionNotCreatedError):
        await PodcastService.submit_generation_job(
            episode_profile_name="missing",
            speaker_profile_name="unused",
            episode_name="Rejected",
            content="source",
            classify_submission_failures=True,
        )


@pytest.mark.asyncio
async def test_podcast_service_classifies_submitter_exception_as_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.podcast_service as service_module

    async def profile(_: str) -> object:
        return type("Profile", (), {"speakers": [{}, {}]})()

    async def skip_gate(*args, **kwargs) -> None:
        return None

    def fail_submit(*args, **kwargs):
        raise RuntimeError("submit transport ended without a receipt")

    monkeypatch.setattr(service_module.EpisodeProfile, "get_by_name", profile)
    monkeypatch.setattr(service_module.SpeakerProfile, "get_by_name", profile)
    monkeypatch.setattr(PodcastService, "_gate_offline_cloud_models", skip_gate)
    monkeypatch.setattr(service_module, "submit_command", fail_submit)

    with pytest.raises(PodcastSubmissionUncertainError):
        await PodcastService.submit_generation_job(
            episode_profile_name="episode",
            speaker_profile_name="speakers",
            episode_name="Uncertain",
            content="source",
            classify_submission_failures=True,
        )


@pytest.mark.asyncio
async def test_retry_delete_failure_fences_job_and_reuses_it_without_unlinking_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    episode = _RetryEpisode()
    audio = tmp_path / "episodes" / "uuid" / "episode.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"old audio")
    episode.audio_file = str(audio)
    delete_calls = 0
    submissions: list[dict[str, object]] = []

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        submissions.append(kwargs)
        return "command:fenced"

    async def delete() -> None:
        nonlocal delete_calls
        delete_calls += 1
        raise RuntimeError("old row delete failed")

    episode.delete = delete  # type: ignore[method-assign]
    import api.routers.podcasts as podcasts_router

    monkeypatch.setattr(podcasts_router, "_AUDIO_ROOT", tmp_path / "episodes")
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    with pytest.raises(HTTPException, match="Failed to retry episode"):
        await _retry_podcast_episode_locked("episode:failed")

    assert episode.saved is True
    assert episode.retry_submitted.model_dump(mode="json") == {
        "state": "submitted",
        "operation_id": episode.retry_submitted.operation_id,
        "job_id": "command:fenced",
        "replacement_command": "command:fenced",
        "generation": 1,
    }
    assert episode.command == "command:fenced"
    assert audio.exists()
    assert delete_calls == 1

    reused = await _retry_podcast_episode_locked("episode:failed")

    assert reused == {
        "job_id": "command:fenced",
        "message": "Retry already submitted successfully",
    }
    assert len(submissions) == 1
    assert delete_calls == 1
    assert audio.exists()


@pytest.mark.asyncio
async def test_retry_reservation_save_failure_skips_submission_and_preserves_old_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    audio = tmp_path / "episodes" / "uuid" / "episode.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"old audio")
    episode.audio_file = str(audio)
    submissions = 0

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        nonlocal submissions
        submissions += 1
        return "command:cancel-me"

    async def fail_save() -> None:
        raise RuntimeError("fence save failed")

    async def unexpected_cancel_command_job(job_id: str) -> bool:
        raise AssertionError("a failed reservation must not create or cancel a job")

    episode.save = fail_save  # type: ignore[method-assign]
    monkeypatch.setattr(podcasts_router, "_AUDIO_ROOT", tmp_path / "episodes")
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    monkeypatch.setattr(
        podcasts_router.CommandService,
        "cancel_command_job",
        unexpected_cancel_command_job,
    )

    with pytest.raises(HTTPException):
        await _retry_podcast_episode_locked("episode:failed")

    assert submissions == 0
    assert episode.retry_submitted is None
    assert episode.deleted is False
    assert audio.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_result", [False, "raises"])
async def test_durable_retry_reservation_blocks_a_fresh_reload_after_post_submit_fence_failure(
    monkeypatch: pytest.MonkeyPatch,
    cancel_result: bool | str,
) -> None:
    import api.routers.podcasts as podcasts_router

    persisted: dict[str, object] = {
        "retry_submitted": None,
        "command": "command:old",
    }
    save_attempts = 0
    submissions = 0

    class ReloadedEpisode(_RetryEpisode):
        def __init__(self) -> None:
            super().__init__()
            self.id = f"episode:uncertain-{cancel_result}"
            self.retry_submitted = persisted["retry_submitted"]
            self.command = persisted["command"]

        async def save(self) -> None:
            nonlocal save_attempts
            save_attempts += 1
            if save_attempts == 2:
                raise RuntimeError("submitted fence save failed")
            marker = self.retry_submitted
            self.retry_submitted = marker
            persisted["retry_submitted"] = (
                marker.model_dump(mode="json") if marker is not None else None
            )
            persisted["command"] = self.command

    async def get_episode(_: str) -> _RetryEpisode:
        return ReloadedEpisode()

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        nonlocal submissions
        submissions += 1
        return "command:uncertain"

    async def cancel_command_job(job_id: str) -> bool:
        if cancel_result == "raises":
            raise RuntimeError("cancel uncertain")
        return cancel_result

    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)
    monkeypatch.setattr(
        podcasts_router.CommandService,
        "cancel_command_job",
        cancel_command_job,
    )

    with pytest.raises(HTTPException, match="state is uncertain") as first:
        await _retry_podcast_episode_locked("episode:failed")

    assert first.value.status_code == 409
    marker = persisted["retry_submitted"]
    assert isinstance(marker, dict)
    assert marker["state"] == "reserved"
    assert isinstance(marker["operation_id"], str) and marker["operation_id"]
    assert marker["job_id"] is None
    assert marker["replacement_command"] is None
    assert marker["generation"] == 1

    # The second request deliberately reloads a new episode instance, simulating
    # a process restart with no process-local uncertainty map to consult.
    with pytest.raises(HTTPException, match="state is uncertain") as second:
        await _retry_podcast_episode_locked(f"episode:uncertain-{cancel_result}")

    assert second.value.status_code == 409
    assert submissions == 1


@pytest.mark.asyncio
async def test_retry_deletes_old_row_before_best_effort_audio_unlink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.audio_file = "contained/audio.mp3"
    events: list[str] = []

    class FailingAudioPath:
        parent = None

        def exists(self) -> bool:
            return True

        def unlink(self) -> None:
            events.append("unlink")
            raise OSError("audio unlink failed")

    async def get_episode(_: str) -> _RetryEpisode:
        return episode

    async def profile_exists(_: str) -> object:
        return object()

    async def submit_generation_job(**kwargs) -> str:
        return "command:audio-failure"

    async def delete() -> None:
        events.append("delete")
        episode.deleted = True

    episode.delete = delete  # type: ignore[method-assign]
    monkeypatch.setattr(
        podcasts_router,
        "_resolve_audio_path",
        lambda _: FailingAudioPath(),
    )
    monkeypatch.setattr(PodcastService, "get_episode", get_episode)
    monkeypatch.setattr(EpisodeProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(SpeakerProfile, "get_by_name", profile_exists)
    monkeypatch.setattr(PodcastService, "submit_generation_job", submit_generation_job)

    result = await _retry_podcast_episode_locked("episode:failed")

    assert result["job_id"] == "command:audio-failure"
    assert events == ["delete", "unlink"]
    assert episode.deleted is True


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
            "episode_length": None,
            "review_outline": False,
            "execution_policy": "strict_local",
            "compute_profile": "balanced",
            "include_transcription": False,
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


def _v2_retry_summary(
    *,
    mode: str = "debate",
    episode_length: str = "long",
    execution_policy: str = "strict_local",
    compute_profile: str = "balanced",
    include_transcription: bool = False,
) -> dict[str, object]:
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
            "execution_policy": execution_policy,
            "compute_profile": compute_profile,
            "include_transcription": include_transcription,
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
    monkeypatch.setattr(
        podcasts_router,
        "_podcast_stage_plans",
        lambda *args, **kwargs: [],
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
@pytest.mark.parametrize(
    ("unsafe_key", "unsafe_value"),
    [
        ("api_key", "secret"),
        ("password", "secret"),
        ("token", "secret"),
        ("source_text", "private source body"),
        ("unknown", "unexpected scalar"),
        ("model_id", "local-model"),
    ],
)
async def test_tampered_v2_receipts_reject_unknown_sensitive_or_model_fields(
    unsafe_key: str,
    unsafe_value: str,
) -> None:
    episode = _RetryEpisode()
    episode.id = f"episode:tampered-receipt-{unsafe_key}"
    episode.selection_summary = _v2_retry_summary()
    episode.model_plan_receipts = [{
        "version": 1,
        "role": "podcast_outline",
        "outcome": "ready",
        "resource_tier": "standard",
        "selection_source": "automatic",
        "reason": "route_ready",
        unsafe_key: unsafe_value,
    }]

    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_tampered"


@pytest.mark.asyncio
async def test_actual_v2_matching_retry_replays_settings_and_submits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:matching-real"
    episode.selection_summary = _v2_retry_summary(
        mode="critique",
        episode_length="short",
        execution_policy="local_preferred",
        compute_profile="maximum_quality",
        include_transcription=True,
    )
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
    monkeypatch.setattr(
        podcasts_router,
        "_podcast_stage_plans",
        lambda *args, **kwargs: [],
    )

    result = await _retry_podcast_episode_locked("episode:matching-real", request=object())

    assert result["job_id"] == "command:v2-retry"
    assert len(submitted) == 1
    assert submitted[0]["mode"] == "critique"
    assert submitted[0]["episode_length"] == "short"
    assert submitted[0]["review_outline"] is True
    assert submitted[0]["execution_policy"] == "local_preferred"
    assert submitted[0]["compute_profile"] == "maximum_quality"
    assert submitted[0]["include_transcription"] is True
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
async def test_v2_retry_production_override_receipt_requires_fresh_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:override-receipt"
    episode.selection_summary = _v2_retry_summary()
    episode.model_plan_receipts = [{
        "version": 1,
        "role": "podcast_outline",
        "outcome": "ready",
        "resource_tier": "standard",
        "selection_source": "production_override",
        "reason": "route_ready",
    }]
    called = False

    async def preparation(*args, **kwargs):
        nonlocal called
        called = True
        return _retry_preview(fingerprint="a" * 64, eligible=True)

    monkeypatch.setattr(podcasts_router, "_podcast_selection_preparation", preparation)

    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_unavailable"
    assert called is False


@pytest.mark.asyncio
async def test_v2_retry_route_planner_block_fails_closed_before_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import api.routers.podcasts as podcasts_router

    episode = _RetryEpisode()
    episode.id = "episode:route-blocked"
    episode.selection_summary = _v2_retry_summary(
        execution_policy="strict_local",
        compute_profile="maximum_quality",
        include_transcription=True,
    )

    async def preparation(*args, **kwargs):
        return _retry_preview(fingerprint="a" * 64, eligible=True)

    monkeypatch.setattr(podcasts_router, "_podcast_selection_preparation", preparation)
    monkeypatch.setattr(
        podcasts_router,
        "_podcast_stage_plans",
        lambda *args, **kwargs: [SimpleNamespace(outcome="blocked")],
    )

    result = await _resolve_retry_selection(episode, request=object())

    assert result is not None
    assert result.status == "preview_required"
    assert result.code == "podcast_selection_unavailable"


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
