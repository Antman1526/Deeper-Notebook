"""v0.8.68 — podcast reliability + capability pass.

Covers: briefing_suffix persistence/replay on retry, retry-from-completed,
content token budget at submit, language passed to create_podcast, the
selected-profile guard, empty episode-dir cleanup, and media-type mapping.
Mix of unit tests and source-anchor guards (the worker command needs a live
podcast-creator + DB to run end-to-end; anchors keep the wiring honest).
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ------------------------------------------------------------- briefing_suffix


def test_episode_model_stores_briefing_suffix():
    from deeper_notebook.podcasts.models import PodcastEpisode

    assert "briefing_suffix" in PodcastEpisode.model_fields
    ep = PodcastEpisode(
        name="e",
        episode_profile={},
        speaker_profile={},
        briefing="b",
        content="c",
        briefing_suffix="make it funny",
    )
    assert ep.briefing_suffix == "make it funny"


def test_worker_persists_suffix_and_passes_language():
    import commands.podcast_commands as pc

    src = inspect.getsource(pc)
    assert "briefing_suffix=input_data.briefing_suffix" in src, (
        "worker must persist the raw suffix on the episode record"
    )
    assert "language=_episode_language" in src, (
        "EpisodeProfile.language must be passed to create_podcast"
    )
    assert "episode_profile.name not in episode_profiles_dict" in src, (
        "selected-profile guard must exist after the removal loops"
    )


def test_retry_replays_suffix_and_allows_completed():
    router_src = (_REPO / "api" / "routers" / "podcasts.py").read_text()
    assert 'briefing_suffix=getattr(episode, "briefing_suffix", None)' in router_src
    assert '("failed", "error", "completed")' in router_src, (
        "retry must be allowed from completed (regenerate workflow)"
    )


# ------------------------------------------------------------- content budget


def test_submit_rejects_oversized_content(monkeypatch):
    from api.podcast_service import PodcastService
    from deeper_notebook.exceptions import InvalidInputError

    async def _fake_ep(name):
        return SimpleNamespace(
            name=name,
            resolve_outline_config=_local_resolver,
            resolve_transcript_config=_local_resolver,
        )

    async def _fake_sp(name):
        return SimpleNamespace(
            name=name,
            speakers=["Host", "Guest"],
            resolve_tts_config=_local_resolver,
        )

    async def _local_resolver():
        return ("openai_compatible", "m", {})

    import api.podcast_service as svc

    monkeypatch.setattr(svc.EpisodeProfile, "get_by_name", _fake_ep)
    monkeypatch.setattr(svc.SpeakerProfile, "get_by_name", _fake_sp)
    monkeypatch.setenv("DEEPER_NOTEBOOK_PODCAST_MAX_CONTENT_TOKENS", "100")

    with pytest.raises(InvalidInputError) as exc:
        _run(
            PodcastService.submit_generation_job(
                episode_profile_name="ep",
                speaker_profile_name="sp",
                episode_name="too big",
                content="word " * 5000,  # far beyond 100 tokens
            )
        )
    assert "too large" in str(exc.value)


def test_budget_disabled_with_zero(monkeypatch):
    """DEEPER_NOTEBOOK_PODCAST_MAX_CONTENT_TOKENS=0 disables the check (content this
    size then proceeds to job submission, which we stub to observe)."""
    from api.podcast_service import PodcastService

    async def _fake_ep(name):
        return SimpleNamespace(
            name=name,
            resolve_outline_config=_local_resolver,
            resolve_transcript_config=_local_resolver,
        )

    async def _fake_sp(name):
        return SimpleNamespace(
            name=name,
            speakers=["Host", "Guest"],
            resolve_tts_config=_local_resolver,
        )

    async def _local_resolver():
        return ("openai_compatible", "m", {})

    import api.podcast_service as svc

    monkeypatch.setattr(svc.EpisodeProfile, "get_by_name", _fake_ep)
    monkeypatch.setattr(svc.SpeakerProfile, "get_by_name", _fake_sp)
    monkeypatch.setenv("DEEPER_NOTEBOOK_PODCAST_MAX_CONTENT_TOKENS", "0")

    reached = {}

    def _fake_submit(*a, **k):
        reached["submitted"] = True
        return SimpleNamespace(id="command:xyz")

    monkeypatch.setattr(svc, "submit_command", _fake_submit)

    job_id = _run(
        PodcastService.submit_generation_job(
            episode_profile_name="ep",
            speaker_profile_name="sp",
            episode_name="big but allowed",
            content="word " * 5000,
        )
    )
    assert reached.get("submitted") is True
    assert job_id


# ------------------------------------------------------------- dir cleanup


def test_cleanup_episode_dir_removes_empty_uuid_dir(tmp_path, monkeypatch):
    import api.routers.podcasts as pr

    root = tmp_path / "episodes"
    episode_dir = root / "some-uuid"
    episode_dir.mkdir(parents=True)
    audio = episode_dir / "final.mp3"
    audio.write_bytes(b"x")
    monkeypatch.setattr(pr, "_AUDIO_ROOT", root.resolve())

    audio.unlink()
    pr._cleanup_episode_dir(audio.resolve())
    assert not episode_dir.exists()
    assert root.exists()  # never removes the root itself


def test_cleanup_episode_dir_keeps_partial_artifacts(tmp_path, monkeypatch):
    import api.routers.podcasts as pr

    root = tmp_path / "episodes"
    episode_dir = root / "some-uuid"
    episode_dir.mkdir(parents=True)
    (episode_dir / "transcript.json").write_text("{}")
    audio = episode_dir / "final.mp3"
    audio.write_bytes(b"x")
    monkeypatch.setattr(pr, "_AUDIO_ROOT", root.resolve())

    audio.unlink()
    pr._cleanup_episode_dir(audio.resolve())
    assert episode_dir.exists()  # transcript kept for diagnostics


# ------------------------------------------------------------- media type


def test_audio_media_type_mapping_present():
    router_src = (_REPO / "api" / "routers" / "podcasts.py").read_text()
    assert '".wav": "audio/wav"' in router_src
    assert (
        'media_type=_MEDIA_TYPES.get(audio_path.suffix.lower(), "audio/mpeg")'
        in router_src
    )


# ------------------------------------------------------------- docs accuracy


def test_docs_no_longer_claim_silent_audio_fallback():
    for doc in (_REPO / "CLAUDE.md", _REPO / "deeper_notebook" / "CLAUDE.md"):
        assert "Fall back to silent audio" not in doc.read_text(), (
            f"{doc} still claims a silent-audio TTS fallback that the code "
            f"does not implement"
        )
