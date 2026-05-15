from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from api.podcast_service import (
    PodcastGenerationRequest,
    PodcastGenerationResponse,
    PodcastService,
)
from open_notebook.config import DATA_FOLDER

router = APIRouter()


# v0.7.2 — Containment root for podcast audio files. The generation
# command (commands/podcast_commands.py:build_episode_output_dir) puts
# every episode's audio under `{DATA_FOLDER}/podcasts/episodes/<uuid>/`.
# We pin to that root and refuse to operate on any audio_file path
# that resolves outside it. Defense-in-depth against DB tampering /
# future bug that allows setting episode.audio_file to e.g. /etc/passwd
# (without this check, the FileResponse endpoint would happily serve
# it and the retry/delete handlers would unlink it).
_AUDIO_ROOT = (Path(DATA_FOLDER) / "podcasts" / "episodes").resolve()


class PodcastEpisodeResponse(BaseModel):
    id: str
    name: str
    episode_profile: dict
    speaker_profile: dict
    briefing: str
    audio_file: Optional[str] = None
    audio_url: Optional[str] = None
    transcript: Optional[dict] = None
    outline: Optional[dict] = None
    created: Optional[str] = None
    job_status: Optional[str] = None
    error_message: Optional[str] = None


def _resolve_audio_path(audio_file: str) -> Optional[Path]:
    """Resolve an episode's audio_file string to a Path inside _AUDIO_ROOT.

    Accepts both file:// URLs and raw paths. Returns the resolved Path if
    it lives under {DATA_FOLDER}/podcasts/episodes/; returns None for any
    path outside that root.

    v0.7.2 — added the containment check. Previously this returned
    Path(audio_file) unchecked; downstream callers used the result to
    FileResponse / unlink without validation, so a tampered DB row could
    direct the API to serve or delete arbitrary files. Same family as
    the v0.6.34 Source.delete fix and the v0.6.31 model_manager fix.
    Callers must now handle None — serving sites should 404, cleanup
    sites should skip the unlink with a log warning.
    """
    if audio_file.startswith("file://"):
        parsed = urlparse(audio_file)
        raw = Path(unquote(parsed.path))
    else:
        raw = Path(audio_file)
    try:
        resolved = raw.resolve()
    except (OSError, ValueError):
        return None
    # is_relative_to handles dotdot traversal (via .resolve canonicalization)
    # AND the sibling-prefix bug that v0.6.31 fixed in model_manager.
    if not resolved.is_relative_to(_AUDIO_ROOT):
        logger.warning(
            "Refusing audio_file path outside _AUDIO_ROOT: %s "
            "(expected under %s). DB may be corrupted.",
            raw, _AUDIO_ROOT,
        )
        return None
    return resolved


@router.post("/podcasts/generate", response_model=PodcastGenerationResponse)
async def generate_podcast(request: PodcastGenerationRequest):
    """
    Generate a podcast episode using Episode Profiles.
    Returns immediately with job ID for status tracking.
    """
    try:
        job_id = await PodcastService.submit_generation_job(
            episode_profile_name=request.episode_profile,
            speaker_profile_name=request.speaker_profile,
            episode_name=request.episode_name,
            notebook_id=request.notebook_id,
            content=request.content,
            briefing_suffix=request.briefing_suffix,
        )

        return PodcastGenerationResponse(
            job_id=job_id,
            status="submitted",
            message=f"Podcast generation started for episode '{request.episode_name}'",
            episode_profile=request.episode_profile,
            episode_name=request.episode_name,
        )

    except Exception as e:
        logger.error(f"Error generating podcast: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to generate podcast"
        )


@router.get("/podcasts/jobs/{job_id}")
async def get_podcast_job_status(job_id: str):
    """Get the status of a podcast generation job"""
    try:
        status_data = await PodcastService.get_job_status(job_id)
        return status_data

    except Exception as e:
        logger.error(f"Error fetching podcast job status: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch job status"
        )


@router.get("/podcasts/episodes", response_model=List[PodcastEpisodeResponse])
async def list_podcast_episodes():
    """List all podcast episodes"""
    try:
        episodes = await PodcastService.list_episodes()

        response_episodes = []
        for episode in episodes:
            # Skip incomplete episodes without command or audio
            if not episode.command and not episode.audio_file:
                continue

            # Get job status and error message if available
            job_status = None
            error_message = None
            if episode.command:
                try:
                    detail = await episode.get_job_detail()
                    job_status = detail["status"]
                    error_message = detail["error_message"]
                except Exception:
                    job_status = "unknown"
            else:
                # No command but has audio file = completed import
                job_status = "completed"

            audio_url = None
            if episode.audio_file:
                audio_path = _resolve_audio_path(episode.audio_file)
                # v0.7.2 — _resolve_audio_path now returns None for paths
                # outside _AUDIO_ROOT; treat that as "no audio available".
                if audio_path is not None and audio_path.exists():
                    audio_url = f"/api/podcasts/episodes/{episode.id}/audio"

            response_episodes.append(
                PodcastEpisodeResponse(
                    id=str(episode.id),
                    name=episode.name,
                    episode_profile=episode.episode_profile,
                    speaker_profile=episode.speaker_profile,
                    briefing=episode.briefing,
                    audio_file=episode.audio_file,
                    audio_url=audio_url,
                    transcript=episode.transcript,
                    outline=episode.outline,
                    created=str(episode.created) if episode.created else None,
                    job_status=job_status,
                    error_message=error_message,
                )
            )

        return response_episodes

    except Exception as e:
        logger.error(f"Error listing podcast episodes: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to list podcast episodes"
        )


@router.get("/podcasts/episodes/{episode_id}", response_model=PodcastEpisodeResponse)
async def get_podcast_episode(episode_id: str):
    """Get a specific podcast episode"""
    try:
        episode = await PodcastService.get_episode(episode_id)

        # Get job status and error message if available
        job_status = None
        error_message = None
        if episode.command:
            try:
                detail = await episode.get_job_detail()
                job_status = detail["status"]
                error_message = detail["error_message"]
            except Exception:
                job_status = "unknown"
        else:
            # No command but has audio file = completed import
            job_status = "completed" if episode.audio_file else "unknown"

        audio_url = None
        if episode.audio_file:
            audio_path = _resolve_audio_path(episode.audio_file)
            if audio_path is not None and audio_path.exists():
                audio_url = f"/api/podcasts/episodes/{episode.id}/audio"

        return PodcastEpisodeResponse(
            id=str(episode.id),
            name=episode.name,
            episode_profile=episode.episode_profile,
            speaker_profile=episode.speaker_profile,
            briefing=episode.briefing,
            audio_file=episode.audio_file,
            audio_url=audio_url,
            transcript=episode.transcript,
            outline=episode.outline,
            created=str(episode.created) if episode.created else None,
            job_status=job_status,
            error_message=error_message,
        )

    except Exception as e:
        logger.error(f"Error fetching podcast episode: {str(e)}")
        raise HTTPException(status_code=404, detail="Episode not found")


@router.get("/podcasts/episodes/{episode_id}/audio")
async def stream_podcast_episode_audio(episode_id: str):
    """Stream the audio file associated with a podcast episode"""
    try:
        episode = await PodcastService.get_episode(episode_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching podcast episode for audio: {str(e)}")
        raise HTTPException(status_code=404, detail="Episode not found")

    if not episode.audio_file:
        raise HTTPException(status_code=404, detail="Episode has no audio file")

    audio_path = _resolve_audio_path(episode.audio_file)
    # v0.7.2 — _resolve_audio_path returns None for paths outside the
    # podcast output root. 404 instead of serving the file — same status
    # code as the not-found-on-disk case so the API can't be used to
    # distinguish "file exists but outside root" from "file missing"
    # (information leak).
    if audio_path is None or not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename=audio_path.name,
    )


@router.post("/podcasts/episodes/{episode_id}/retry")
async def retry_podcast_episode(episode_id: str):
    """Retry a failed podcast episode by deleting it and submitting a new job"""
    try:
        episode = await PodcastService.get_episode(episode_id)

        # Validate episode is in a failed state
        detail = await episode.get_job_detail()
        if detail["status"] not in ("failed", "error"):
            raise HTTPException(
                status_code=400,
                detail=f"Episode is not in a failed state (current: {detail['status']})",
            )

        # Extract params for re-submission
        ep_profile_name = episode.episode_profile.get("name")
        sp_profile_name = episode.speaker_profile.get("name")
        episode_name = episode.name
        content = episode.content

        if not ep_profile_name or not sp_profile_name:
            raise HTTPException(
                status_code=400,
                detail="Cannot retry: episode or speaker profile name missing from stored data",
            )

        # Delete audio file if any. v0.7.2 — skip unlink for paths
        # outside _AUDIO_ROOT (None) instead of trusting the DB value.
        if episode.audio_file:
            audio_path = _resolve_audio_path(episode.audio_file)
            if audio_path is None:
                logger.warning(
                    "Retry: skipping audio cleanup — episode.audio_file "
                    "(%s) is outside the podcast output root",
                    episode.audio_file,
                )
            elif audio_path.exists():
                try:
                    audio_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete audio file {audio_path}: {e}")

        # Delete the failed episode
        await episode.delete()

        # Submit a new job
        job_id = await PodcastService.submit_generation_job(
            episode_profile_name=ep_profile_name,
            speaker_profile_name=sp_profile_name,
            episode_name=episode_name,
            content=content,
        )

        return {"job_id": job_id, "message": "Retry submitted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying podcast episode: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to retry episode"
        )


@router.delete("/podcasts/episodes/{episode_id}")
async def delete_podcast_episode(episode_id: str):
    """Delete a podcast episode and its associated audio file"""
    try:
        # Get the episode first to check if it exists and get the audio file path
        episode = await PodcastService.get_episode(episode_id)

        # Delete the physical audio file if it exists.
        # v0.7.2 — skip unlink for paths outside _AUDIO_ROOT (DB tampering
        # defense). The episode record itself still gets deleted below
        # — losing track of a renegade file is better than deleting it.
        if episode.audio_file:
            audio_path = _resolve_audio_path(episode.audio_file)
            if audio_path is None:
                logger.warning(
                    "Delete: skipping audio cleanup — episode.audio_file "
                    "(%s) is outside the podcast output root",
                    episode.audio_file,
                )
            elif audio_path.exists():
                try:
                    audio_path.unlink()
                    logger.info(f"Deleted audio file: {audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete audio file {audio_path}: {e}")

        # Delete the episode from the database
        await episode.delete()

        logger.info(f"Deleted podcast episode: {episode_id}")
        return {"message": "Episode deleted successfully", "episode_id": episode_id}

    except HTTPException:
        # v0.7.2 Issue #9 — preserve 404/400 from PodcastService.get_episode
        # instead of swallowing them into a generic 500. Matches the
        # retry handler's pattern at line 263-264.
        raise
    except Exception as e:
        logger.error(f"Error deleting podcast episode: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to delete episode"
        )
