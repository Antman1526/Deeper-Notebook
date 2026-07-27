"""Private Video Overview routes backed only by local Studio and podcast files."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from loguru import logger

from api.podcast_service import PodcastService
from api.routers.podcasts import _resolve_audio_path
from api.schemas.video_overviews import (
    VideoOverviewComposeRequest,
    VideoOverviewResponse,
)
from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.domain.notebook import StudioArtifact
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.podcasts.models import TranscriptSegment
from deeper_notebook.studio.exporters import render_slide_deck_images
from deeper_notebook.studio.payloads import parse_payload_document
from deeper_notebook.studio.schemas import SlideDeckDocument
from deeper_notebook.video import (
    VideoNarrationSegment,
    VideoOverviewDocument,
)
from deeper_notebook.video import (
    compose_video_overview as compose_local_video_overview,
)
from deeper_notebook.video.composer import VideoOverviewError

router = APIRouter(prefix="/video-overviews", tags=["video-overviews"])
_VIDEO_ROOT = (Path(DATA_FOLDER) / "video-overviews").resolve()
_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()


async def _lock_for(artifact_id: str) -> asyncio.Lock:
    async with _LOCKS_GUARD:
        return _LOCKS.setdefault(artifact_id, asyncio.Lock())


def _contained_output(path: str | None, suffix: str) -> Path | None:
    if not path:
        return None
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError:
        return None
    if (
        resolved.suffix.lower() != suffix
        or not resolved.is_file()
        or not resolved.is_relative_to(_VIDEO_ROOT)
    ):
        return None
    return resolved


def _segments(raw_segments: list[TranscriptSegment]) -> list[VideoNarrationSegment]:
    if not raw_segments:
        raise ValueError(
            "The selected Audio Overview has no timestamped transcript yet"
        )
    return [
        VideoNarrationSegment(
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text,
            citation_ids=segment.citation_ids,
        )
        for segment in raw_segments
    ]


async def _slide_deck(artifact_id: str) -> StudioArtifact:
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError) as exc:
        raise HTTPException(
            status_code=404, detail="Slide deck artifact not found"
        ) from exc
    if artifact.artifact_type != "slide_deck" or artifact.status != "completed":
        raise HTTPException(
            status_code=422, detail="Choose a completed Slide deck artifact"
        )
    try:
        document = parse_payload_document("slide_deck", artifact.output_payload)
    except (InvalidInputError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422, detail="Slide deck has no valid visual document"
        ) from exc
    if not isinstance(document, SlideDeckDocument):
        raise HTTPException(
            status_code=422, detail="Slide deck has no valid visual document"
        )
    return artifact


@router.post(
    "", response_model=VideoOverviewResponse, status_code=status.HTTP_201_CREATED
)
async def compose_video_overview(
    payload: VideoOverviewComposeRequest,
) -> VideoOverviewResponse:
    """Join a reviewed slide deck with completed podcast audio on this device."""
    artifact = await _slide_deck(payload.slide_deck_artifact_id)
    try:
        episode = await PodcastService.get_episode(payload.podcast_episode_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Video Overview requested unknown episode {}", payload.podcast_episode_id
        )
        raise HTTPException(status_code=404, detail="Audio Overview not found") from exc
    audio_path = _resolve_audio_path(str(getattr(episode, "audio_file", "") or ""))
    if audio_path is None or not audio_path.is_file():
        raise HTTPException(
            status_code=422,
            detail="The selected Audio Overview has no local audio file",
        )
    try:
        narration_segments = _segments(
            list(getattr(episode, "transcript_segments", []) or [])
        )
        document = parse_payload_document("slide_deck", artifact.output_payload)
        if not isinstance(document, SlideDeckDocument):
            raise ValueError("Slide deck has no valid visual document")
    except (InvalidInputError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    lock = await _lock_for(str(artifact.id))
    async with lock:
        _VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
        artifact_dir = _VIDEO_ROOT / str(artifact.id).replace(":", "-")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="onp-video-slides-") as temporary:
            slides = await asyncio.to_thread(
                render_slide_deck_images, document, Path(temporary)
            )
            try:
                output = await asyncio.to_thread(
                    compose_local_video_overview,
                    VideoOverviewDocument(
                        slide_image_paths=slides,
                        narration_audio_path=audio_path,
                        narration_segments=narration_segments,
                        caption_language=payload.caption_language,
                    ),
                    artifact_dir,
                )
            except VideoOverviewError as exc:
                logger.warning("Video Overview composition failed for {}", artifact.id)
                raise HTTPException(
                    status_code=502, detail="Local Video Overview composition failed"
                ) from exc

        media_url = f"/api/video-overviews/{artifact.id}/media"
        captions_url = f"/api/video-overviews/{artifact.id}/captions"
        artifact.export_paths = {
            **artifact.export_paths,
            "video_mp4": str(output.mp4_path),
            "video_captions": str(output.vtt_path),
        }
        artifact.output_payload = {
            **artifact.output_payload,
            "video_overview": {
                "version": 1,
                "episode_id": str(episode.id),
                "duration_seconds": output.duration_seconds,
                "caption_language": payload.caption_language,
                "media_url": media_url,
                "captions_url": captions_url,
            },
        }
        await artifact.save()
    return VideoOverviewResponse(
        artifact_id=str(artifact.id),
        episode_id=str(episode.id),
        duration_seconds=output.duration_seconds,
        media_url=media_url,
        captions_url=captions_url,
    )


@router.get("/{artifact_id}/media")
async def stream_video_overview(artifact_id: str):
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Video Overview not found") from exc
    path = _contained_output(artifact.export_paths.get("video_mp4"), ".mp4")
    if path is None:
        raise HTTPException(status_code=404, detail="Video Overview file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/{artifact_id}/captions")
async def stream_video_overview_captions(artifact_id: str):
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Video Overview not found") from exc
    path = _contained_output(artifact.export_paths.get("video_captions"), ".vtt")
    if path is None:
        raise HTTPException(status_code=404, detail="Video Overview captions not found")
    return FileResponse(path, media_type="text/vtt", filename=path.name)
