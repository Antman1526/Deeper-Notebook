"""API coverage for contained, local Video Overview composition."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import video_overviews as video_mod
from deeper_notebook.video.contracts import VideoOverviewOutput


class _Artifact:
    def __init__(self, root: Path):
        self.id = "studio_artifact:deck"
        self.artifact_type = "slide_deck"
        self.status = "completed"
        self.export_paths: dict[str, str] = {}
        self.output_payload = {
            "schema_version": 1,
            "document": {
                "artifact_type": "slide_deck",
                "title": "Evidence Briefing",
                "audience": "Private researcher",
                "slides": [{"title": "Evidence", "bullets": ["Grounded claim"]}],
            },
        }
        self.root = root
        self.save_count = 0

    async def save(self):
        self.save_count += 1


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(video_mod.router, prefix="/api")
    return TestClient(app)


def test_compose_and_stream_video_overview_stays_inside_local_root(
    monkeypatch, tmp_path
):
    root = tmp_path / "video-overviews"
    root.mkdir()
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"audio")
    artifact = _Artifact(root)

    class FakeArtifactModel:
        @classmethod
        async def get(cls, artifact_id):
            assert artifact_id == artifact.id
            return artifact

    async def fake_episode(_episode_id):
        return SimpleNamespace(
            id="episode:ready",
            audio_file=str(audio),
            transcript_segments=[
                SimpleNamespace(
                    start_seconds=0,
                    end_seconds=2.5,
                    text="Grounded local narration.",
                    citation_ids=["source:1"],
                )
            ],
        )

    def fake_render(_document, output_dir):
        slide = output_dir / "slide-001.png"
        slide.write_bytes(b"png")
        return [slide]

    def fake_compose(_document, output_dir):
        mp4 = output_dir / "overview.mp4"
        vtt = output_dir / "overview.vtt"
        mp4.write_bytes(b"mp4")
        vtt.write_text("WEBVTT\n", encoding="utf-8")
        return VideoOverviewOutput(mp4_path=mp4, vtt_path=vtt, duration_seconds=2.5)

    monkeypatch.setattr(video_mod, "_VIDEO_ROOT", root.resolve())
    monkeypatch.setattr(video_mod, "StudioArtifact", FakeArtifactModel)
    monkeypatch.setattr(video_mod.PodcastService, "get_episode", fake_episode)
    monkeypatch.setattr(video_mod, "_resolve_audio_path", lambda _value: audio)
    monkeypatch.setattr(video_mod, "render_slide_deck_images", fake_render)
    monkeypatch.setattr(video_mod, "compose_local_video_overview", fake_compose)
    video_mod._LOCKS.clear()

    client = _client()
    response = client.post(
        "/api/video-overviews",
        json={
            "slide_deck_artifact_id": artifact.id,
            "podcast_episode_id": "episode:ready",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "artifact_id": artifact.id,
        "episode_id": "episode:ready",
        "duration_seconds": 2.5,
        "media_url": f"/api/video-overviews/{artifact.id}/media",
        "captions_url": f"/api/video-overviews/{artifact.id}/captions",
    }
    assert artifact.save_count == 1
    assert Path(artifact.export_paths["video_mp4"]).is_relative_to(root)
    assert client.get(response.json()["media_url"]).content == b"mp4"
    # Text-mode output uses CRLF on Windows; WebVTT accepts either newline.
    assert (
        client.get(response.json()["captions_url"]).text.replace("\r\n", "\n")
        == "WEBVTT\n"
    )


def test_rejects_audio_overview_without_timestamped_transcript(monkeypatch, tmp_path):
    root = tmp_path / "video-overviews"
    root.mkdir()
    audio = tmp_path / "episode.mp3"
    audio.write_bytes(b"audio")
    artifact = _Artifact(root)

    class FakeArtifactModel:
        @classmethod
        async def get(cls, _artifact_id):
            return artifact

    async def fake_episode(_episode_id):
        return SimpleNamespace(
            id="episode:empty", audio_file=str(audio), transcript_segments=[]
        )

    monkeypatch.setattr(video_mod, "_VIDEO_ROOT", root.resolve())
    monkeypatch.setattr(video_mod, "StudioArtifact", FakeArtifactModel)
    monkeypatch.setattr(video_mod.PodcastService, "get_episode", fake_episode)
    monkeypatch.setattr(video_mod, "_resolve_audio_path", lambda _value: audio)

    response = _client().post(
        "/api/video-overviews",
        json={
            "slide_deck_artifact_id": artifact.id,
            "podcast_episode_id": "episode:empty",
        },
    )

    assert response.status_code == 422
    assert "timestamped transcript" in response.json()["detail"]


def test_preserves_typed_podcast_errors(monkeypatch, tmp_path):
    artifact = _Artifact(tmp_path)

    class FakeArtifactModel:
        @classmethod
        async def get(cls, _artifact_id):
            return artifact

    async def unavailable_episode(_episode_id):
        raise HTTPException(status_code=409, detail="Audio Overview is still running")

    monkeypatch.setattr(video_mod, "StudioArtifact", FakeArtifactModel)
    monkeypatch.setattr(video_mod.PodcastService, "get_episode", unavailable_episode)

    response = _client().post(
        "/api/video-overviews",
        json={
            "slide_deck_artifact_id": artifact.id,
            "podcast_episode_id": "episode:running",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Audio Overview is still running"
