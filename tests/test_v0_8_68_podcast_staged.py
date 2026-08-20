"""v0.8.68 — staged podcast generation: per-stage progress, cancellation,
stage-aware timeout, outline-review workflow.

The runner is tested with a FAKE graph (no live LLM/TTS); the library
integration is pinned by node-name guards so a podcast-creator upgrade that
renames nodes fails the suite instead of silently breaking stages.
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


# ------------------------------------------------------------- library pins


def test_podcast_creator_graph_node_names_are_pinned():
    """The staged runner maps these exact node names to stages. If a
    podcast-creator upgrade renames them, fail HERE with a clear message."""
    from podcast_creator import podcast_graph

    node_names = set(podcast_graph.get_graph().nodes.keys())
    for expected in (
        "generate_outline",
        "generate_transcript",
        "generate_all_audio",
        "combine_audio",
    ):
        assert expected in node_names, (
            f"podcast-creator no longer has node {expected!r} — update "
            f"commands/podcast_staged.py NODE_DONE_NEXT_STAGE"
        )


def test_resume_graph_starts_at_transcript():
    from commands.podcast_staged import get_resume_graph

    nodes = set(get_resume_graph().get_graph().nodes.keys())
    assert "generate_outline" not in nodes
    assert {"generate_transcript", "generate_all_audio", "combine_audio"} <= nodes


# ------------------------------------------------------------- staged runner


class _FakeEpisode:
    def __init__(self):
        self.id = "episode:test"
        self.generation_stage = None
        self.saved_stages: list = []

    async def save(self):
        self.saved_stages.append(self.generation_stage)


class _FakeGraph:
    """Yields updates like langgraph's stream_mode='updates'."""

    def __init__(self, updates, delay=0.0):
        self._updates = updates
        self._delay = delay

    async def astream(self, state, config=None, stream_mode=None):
        for u in self._updates:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield u


def test_stages_progress_and_results_merge(monkeypatch):
    from commands import podcast_staged as ps

    episode = _FakeEpisode()
    graph = _FakeGraph(
        [
            {"generate_outline": {"outline": {"segments": []}}},
            {"generate_transcript": {"transcript": ["d1", "d2"]}},
            {"generate_all_audio": {"audio_clips": ["a.wav"]}},
            {"generate_all_audio": {"audio_clips": ["b.wav"]}},  # Send fan-out
            {"combine_audio": {"final_output_file_path": "/tmp/out.mp3"}},
        ]
    )

    async def _never_cancelled(episode_id):
        return False

    monkeypatch.setattr(ps, "_cancel_requested", _never_cancelled)

    import time as _time

    merged = _run(
        ps.run_graph_with_stages(
            graph,
            {},
            {},
            episode=episode,
            deadline=_time.monotonic() + 60,
            poll_interval=0.05,
        )
    )
    assert merged["final_output_file_path"] == "/tmp/out.mp3"
    assert merged["transcript"] == ["d1", "d2"]
    # Stage transitions recorded in order, audio fan-out deduped.
    assert episode.saved_stages == [
        "generating_transcript",
        "generating_audio",
        "combining_audio",
    ]


def test_cancel_flag_aborts_generation(monkeypatch):
    from commands import podcast_staged as ps

    episode = _FakeEpisode()
    graph = _FakeGraph([{"generate_outline": {"outline": {}}}] * 100, delay=0.2)

    async def _cancelled(episode_id):
        return True

    monkeypatch.setattr(ps, "_cancel_requested", _cancelled)

    import time as _time

    with pytest.raises(ps.CancelledByUser):
        _run(
            ps.run_graph_with_stages(
                graph,
                {},
                {},
                episode=episode,
                deadline=_time.monotonic() + 60,
                poll_interval=0.05,
            )
        )


def test_deadline_raises_timeout(monkeypatch):
    from commands import podcast_staged as ps

    episode = _FakeEpisode()
    graph = _FakeGraph([{"generate_outline": {}}] * 100, delay=0.2)

    async def _never(episode_id):
        return False

    monkeypatch.setattr(ps, "_cancel_requested", _never)

    import time as _time

    with pytest.raises(asyncio.TimeoutError):
        _run(
            ps.run_graph_with_stages(
                graph,
                {},
                {},
                episode=episode,
                deadline=_time.monotonic() - 1,  # already expired
                poll_interval=0.05,
            )
        )


def test_generation_exception_propagates(monkeypatch):
    from commands import podcast_staged as ps

    class _BoomGraph:
        async def astream(self, state, config=None, stream_mode=None):
            raise RuntimeError("TTS provider exploded")
            yield  # pragma: no cover

    async def _never(episode_id):
        return False

    monkeypatch.setattr(ps, "_cancel_requested", _never)

    import time as _time

    with pytest.raises(RuntimeError, match="TTS provider exploded"):
        _run(
            ps.run_graph_with_stages(
                _BoomGraph(),
                {},
                {},
                episode=_FakeEpisode(),
                deadline=_time.monotonic() + 60,
                poll_interval=0.05,
            )
        )


# ------------------------------------------------------------- API schemas


def test_outline_update_schema_validates():
    from api.routers.podcasts import OutlineSegmentUpdate, OutlineUpdateRequest

    req = OutlineUpdateRequest(
        segments=[
            {"name": "Intro", "description": "Welcome", "size": "short"},
            {"name": "Deep dive", "description": "The meat", "size": "long"},
        ]
    )
    assert len(req.segments) == 2

    with pytest.raises(Exception):
        OutlineUpdateRequest(segments=[])  # at least one segment
    with pytest.raises(Exception):
        OutlineSegmentUpdate(name="x", description="y", size="huge")


def test_generation_request_carries_review_outline():
    from api.podcast_service import PodcastGenerationRequest

    req = PodcastGenerationRequest(
        episode_profile="ep",
        speaker_profile="sp",
        episode_name="n",
        content="c",
        review_outline=True,
    )
    assert req.review_outline is True
    assert (
        PodcastGenerationRequest(
            episode_profile="ep",
            speaker_profile="sp",
            episode_name="n",
            content="c",
        ).review_outline
        is False
    )


def test_overview_mode_bounds_keep_length_control_inside_its_format_contract():
    from commands.podcast_staged import segments_for_overview_mode

    assert segments_for_overview_mode("brief", "long", profile_segments=8) == 4
    assert segments_for_overview_mode("debate", "short", profile_segments=3) == 4
    assert segments_for_overview_mode("deep_dive", None, profile_segments=99) == 8


def test_overview_mode_uses_its_exact_speaker_count():
    from commands.podcast_staged import speaker_profile_for_overview_mode

    class FakeProfile:
        def __init__(self, speakers):
            self.speakers = speakers

        def model_copy(self, *, update):
            return FakeProfile(update["speakers"])

    assert (
        len(
            speaker_profile_for_overview_mode(FakeProfile(["a", "b"]), "brief").speakers
        )
        == 1
    )
    assert (
        len(
            speaker_profile_for_overview_mode(
                FakeProfile(["a", "b", "c"]), "debate"
            ).speakers
        )
        == 2
    )
    with pytest.raises(ValueError, match="requires 2 speakers"):
        speaker_profile_for_overview_mode(FakeProfile(["a"]), "critique")


# ------------------------------------------------------------- wiring guards


def test_worker_wiring_anchors():
    src = (_REPO / "commands" / "podcast_commands.py").read_text()
    assert "run_graph_with_stages(" in src
    assert "get_full_graph()" in src
    assert "get_resume_graph()" in src
    assert "resume_podcast" in src
    assert "STAGE_AWAITING_REVIEW" in src
    assert "except CancelledByUser:" in src
    assert "mode=mode" in src
    assert "custom_prompt=custom_prompt" in src
    assert "transcript_segments_from_payload" in src


def test_router_exposes_new_endpoints():
    src = (_REPO / "api" / "routers" / "podcasts.py").read_text()
    assert '"/podcasts/episodes/{episode_id}/cancel"' in src
    assert '"/podcasts/episodes/{episode_id}/outline"' in src
    assert '"/podcasts/episodes/{episode_id}/approve-outline"' in src
    assert 'generation_stage=getattr(episode, "generation_stage", None)' in src
