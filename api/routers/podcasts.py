import asyncio
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field

from api.podcast_service import (
    PodcastGenerationRequest,
    PodcastGenerationResponse,
    PodcastService,
)
from api.schemas.podcast_studio import (
    PodcastReadinessRequest,
    PodcastReadinessResponse,
    PodcastSelectionPreviewRequest,
    PodcastSelectionPreviewResponse,
    PodcastStageModelPlanResponse,
    PodcastStudioSubmitRequest,
    PodcastStudioSubmitResponse,
)
from api.utils.iso import iso  # v0.7.182 — Safari-safe datetime serialization
from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.database.repository import repo_query
from deeper_notebook.domain.notebook import Note, Notebook
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.podcasts import file_uri_to_local_path
from deeper_notebook.podcasts.models import (
    EpisodeProfile,
    PodcastOverviewMode,
    TranscriptSegment,
    normalize_podcast_mode,
)
from deeper_notebook.podcasts.profile_names import (
    CANONICAL_LOCAL_EPISODE_PROFILE,
    select_existing_episode_profile_name,
)
from deeper_notebook.podcasts.selection_contracts import (
    AppNoteSelection,
    NotebookSelection,
)
from deeper_notebook.podcasts.selection_service import (
    AppNotebookPodcastSelectionResolver,
    AppNotePodcastSelectionResolver,
    CompositePodcastSelectionResolver,
    KnowledgeEnginePodcastSelectionResolver,
    PodcastSelectionPreparation,
    PodcastSelectionService,
)

router = APIRouter()


_PODCAST_SUBMISSION_LOCKS: dict[str, asyncio.Lock] = {}
_PODCAST_SUBMISSION_LOCKS_GUARD = asyncio.Lock()
_PODCAST_SUBMISSION_RESULTS: dict[str, tuple[str, PodcastStudioSubmitResponse]] = {}


async def _podcast_submission_lock(idempotency_key: str) -> asyncio.Lock:
    async with _PODCAST_SUBMISSION_LOCKS_GUARD:
        lock = _PODCAST_SUBMISSION_LOCKS.get(idempotency_key)
        if lock is None:
            lock = asyncio.Lock()
            _PODCAST_SUBMISSION_LOCKS[idempotency_key] = lock
        return lock


def _submission_request_digest(payload: PodcastStudioSubmitRequest) -> str:
    """Bind an idempotency key to a source-body-free confirmed request."""
    encoded = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _podcast_selection_engine(request: Request):
    """Return only the read projection required for a podcast preview."""
    engine = getattr(request.app.state, "knowledge_engine_service", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "podcast_selection_unavailable"},
        )
    if not callable(getattr(engine, "get_document", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "podcast_selection_unavailable"},
        )
    return engine


def _podcast_notebook_loader(request: Request):
    """Use the app context boundary, with an app-state hook for isolated tests."""
    configured_loader = getattr(request.app.state, "podcast_notebook_loader", None)
    return configured_loader if callable(configured_loader) else Notebook.get


def _podcast_note_loader(request: Request):
    configured_loader = getattr(request.app.state, "podcast_note_loader", None)
    return configured_loader if callable(configured_loader) else Note.get


def _podcast_selection_service(
    request: Request, payload: PodcastSelectionPreviewRequest
) -> PodcastSelectionService:
    resolvers = [
        AppNotebookPodcastSelectionResolver(
            notebook_loader=_podcast_notebook_loader(request)
        ),
        AppNotePodcastSelectionResolver(note_loader=_podcast_note_loader(request)),
    ]
    if any(
        not isinstance(selection, (NotebookSelection, AppNoteSelection))
        for selection in payload.selections
    ):
        resolvers.append(
            KnowledgeEnginePodcastSelectionResolver(
                engine=_podcast_selection_engine(request)
            )
        )
    return PodcastSelectionService(
        resolver=CompositePodcastSelectionResolver(resolvers=tuple(resolvers))
    )


async def _podcast_selection_preparation(
    request: Request, payload: PodcastSelectionPreviewRequest
) -> PodcastSelectionPreparation:
    return await _podcast_selection_service(request, payload).prepare(
        payload.selections
    )


def _stage_plan_response(plan) -> PodcastStageModelPlanResponse:
    return PodcastStageModelPlanResponse(
        role=plan.role,
        outcome=plan.outcome,
        model_id=plan.selected_model_id,
        provider=plan.selected_provider,
        resource_tier=plan.resource_tier,
        selection_source=plan.selection_source,
        reason=plan.route_reason,
        blocked_reason=plan.blocked_reason,
    )


def _podcast_stage_plans(
    request: Request,
    *,
    included_characters: int,
    execution_policy: str,
    compute_profile: str,
    include_transcription: bool,
) -> list[PodcastStageModelPlanResponse]:
    from deeper_notebook.local_models.contracts import RouteRequest
    from deeper_notebook.local_models.planner import plan_model_route

    candidates = list(getattr(request.app.state, "local_model_route_candidates", ()))
    text_context_tokens = max(1, (included_characters + 3) // 4)
    roles: list[tuple[str, tuple[str, ...], bool]] = [
        ("podcast_outline", ("text",), True),
        ("podcast_script", ("text",), False),
        ("text_to_speech", ("audio",), False),
    ]
    if include_transcription:
        roles.append(("speech_to_text", ("audio",), False))
    return [
        _stage_plan_response(
            plan_model_route(
                candidates,
                RouteRequest(
                    role=role,
                    required_context_tokens=(
                        text_context_tokens if role != "text_to_speech" else 0
                    ),
                    modalities=modalities,
                    requires_structured_output=requires_structured_output,
                    execution_policy=execution_policy,
                    compute_profile=compute_profile,
                ),
            )
        )
        for role, modalities, requires_structured_output in roles
    ]


@router.post(
    "/podcasts/selection/preview",
    response_model=PodcastSelectionPreviewResponse,
)
async def preview_podcast_selection(
    request: Request,
    payload: PodcastSelectionPreviewRequest,
) -> PodcastSelectionPreviewResponse:
    """Resolve references for review without starting a model or source mutation."""
    try:
        preview = (await _podcast_selection_preparation(request, payload)).preview
        return PodcastSelectionPreviewResponse.model_validate(preview.model_dump())
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "podcast_selection_not_found"},
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "podcast_selection_unavailable"},
        ) from None
    except Exception as exc:
        logger.warning("Podcast selection preview unavailable ({})", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "podcast_selection_unavailable"},
        ) from None


@router.post("/podcasts/readiness", response_model=PodcastReadinessResponse)
async def podcast_readiness(
    request: Request,
    payload: PodcastReadinessRequest,
) -> PodcastReadinessResponse:
    """Inspect selection and local planner readiness without starting production."""
    try:
        preparation = await _podcast_selection_preparation(request, payload)
        preview = PodcastSelectionPreviewResponse.model_validate(
            preparation.preview.model_dump()
        )
        stage_plans = _podcast_stage_plans(
            request,
            included_characters=preparation.preview.included_characters,
            execution_policy=payload.execution_policy,
            compute_profile=payload.compute_profile,
            include_transcription=payload.include_transcription,
        )
        planner_blocked = any(plan.outcome != "ready" for plan in stage_plans)
        blocked_reasons = list(preparation.preview.blocked_reasons)
        if planner_blocked:
            blocked_reasons.append("podcast_stage_route_blocked")
        return PodcastReadinessResponse(
            preview=preview,
            stage_plans=stage_plans,
            ready=preview.current_worker_eligible and not planner_blocked,
            blocked_reasons=blocked_reasons,
        )
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "podcast_selection_not_found"},
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "podcast_readiness_unavailable"},
        ) from None
    except Exception as exc:
        logger.warning("Podcast readiness unavailable ({})", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "podcast_readiness_unavailable"},
        ) from None


@router.post(
    "/podcasts/studio/submit",
    response_model=PodcastStudioSubmitResponse,
)
async def submit_podcast_studio(
    request: Request,
    payload: PodcastStudioSubmitRequest,
) -> PodcastStudioSubmitResponse:
    """Submit only a fresh, confirmed, locally-routable server-side selection."""
    try:
        preparation = await _podcast_selection_preparation(request, payload)
        preview = preparation.preview
        if payload.selection_fingerprint != preview.selection_fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "podcast_selection_changed"},
            )
        if preview.requires_batch_engine:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "podcast_batch_engine_required"},
            )
        if not preview.current_worker_eligible:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "podcast_selection_not_ready"},
            )
        stage_plans = _podcast_stage_plans(
            request,
            included_characters=preview.included_characters,
            execution_policy=payload.execution_policy,
            compute_profile=payload.compute_profile,
            include_transcription=payload.include_transcription,
        )
        if any(plan.outcome != "ready" for plan in stage_plans):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "podcast_stage_route_blocked"},
            )
        request_digest = _submission_request_digest(payload)
        lock = await _podcast_submission_lock(payload.idempotency_key)
        async with lock:
            cached = _PODCAST_SUBMISSION_RESULTS.get(payload.idempotency_key)
            if cached is not None:
                cached_digest, cached_response = cached
                if cached_digest != request_digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"code": "podcast_idempotency_conflict"},
                    )
                return cached_response
            job_id = await PodcastService.submit_generation_job(
                episode_profile_name=payload.episode_profile,
                speaker_profile_name=payload.speaker_profile,
                episode_name=payload.episode_name,
                content=preparation.content,
                mode=payload.mode,
                custom_prompt=payload.custom_prompt,
                episode_length=payload.episode_length,
                review_outline=payload.review_outline,
            )
            response = PodcastStudioSubmitResponse(
                job_id=job_id,
                status="submitted",
                message="Podcast generation accepted after confirmation.",
                episode_profile=payload.episode_profile,
                episode_name=payload.episode_name,
                mode=payload.mode,
            )
            _PODCAST_SUBMISSION_RESULTS[payload.idempotency_key] = (
                request_digest,
                response,
            )
            return response
    except HTTPException:
        raise
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "podcast_selection_not_found"},
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "podcast_submission_invalid"},
        ) from None
    except Exception as exc:
        logger.warning("Podcast Studio submission unavailable ({})", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "podcast_submission_unavailable"},
        ) from None


# v0.8.70 — per-episode retry serialization. The retry handler reads the
# episode's terminal-state status, then (much later) destructively deletes the
# record + audio and resubmits. Without a guard, a double-click or two
# concurrent retries could both pass the terminal-state check and both
# delete+resubmit — duplicating episodes or deleting content out from under a
# just-started job. These locks serialize retries of the SAME episode within
# this process (the desktop app runs a single Uvicorn worker, so process-level
# is sufficient; a multi-worker deployment would need a DB-level optimistic
# status transition instead). Locks are created lazily and keyed by episode id.
_RETRY_LOCKS: dict[str, asyncio.Lock] = {}
_RETRY_LOCKS_GUARD = asyncio.Lock()


async def _get_retry_lock(episode_id: str) -> asyncio.Lock:
    """Return the (lazily created) per-episode retry lock."""
    async with _RETRY_LOCKS_GUARD:
        lock = _RETRY_LOCKS.get(episode_id)
        if lock is None:
            lock = asyncio.Lock()
            _RETRY_LOCKS[episode_id] = lock
        return lock


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
    mode: PodcastOverviewMode = PodcastOverviewMode.DEEP_DIVE
    custom_prompt: Optional[str] = None
    audio_file: Optional[str] = None
    audio_url: Optional[str] = None
    transcript: Optional[dict] = None
    outline: Optional[dict] = None
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    created: Optional[str] = None
    job_status: Optional[str] = None
    error_message: Optional[str] = None
    # v0.8.68 — per-stage progress / outline-review state (see
    # GENERATION_STAGES in deeper_notebook/podcasts/models.py).
    generation_stage: Optional[str] = None


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
    try:
        raw = (
            Path(file_uri_to_local_path(audio_file))
            if audio_file.startswith("file:")
            else Path(audio_file)
        )
        resolved = raw.resolve()
    except (OSError, ValueError):
        return None
    # is_relative_to handles dotdot traversal (via .resolve canonicalization)
    # AND the sibling-prefix bug that v0.6.31 fixed in model_manager.
    if not resolved.is_relative_to(_AUDIO_ROOT):
        logger.warning(
            "Refusing audio_file path outside _AUDIO_ROOT: {} "
            "(expected under {}). DB may be corrupted.",
            raw,
            _AUDIO_ROOT,
        )
        return None
    return resolved


def _cleanup_episode_dir(audio_path: Path) -> None:
    """v0.8.68 — best-effort removal of the episode's UUID directory after
    its audio file is unlinked. Unlinking alone left an empty (or
    transcript-only) directory under data/podcasts/episodes/ behind for
    every deleted/retried episode — slow disk fill with zero user value.
    Only removes the dir when it is (a) strictly inside _AUDIO_ROOT, (b) not
    the root itself, and (c) empty — partial artifacts (transcripts,
    intermediate WAVs) are kept for diagnostics, matching the worker's
    failure-cleanup policy in commands/podcast_commands.py."""
    try:
        episode_dir = audio_path.parent
        if (
            episode_dir.is_relative_to(_AUDIO_ROOT)
            and episode_dir != _AUDIO_ROOT
            and episode_dir.exists()
            and not any(episode_dir.iterdir())
        ):
            episode_dir.rmdir()
            logger.info(f"Removed empty episode directory: {episode_dir}")
    except Exception as exc:
        logger.warning(f"Could not remove episode dir {audio_path.parent}: {exc}")


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
            mode=request.mode,
            custom_prompt=request.resolved_custom_prompt,
            episode_length=request.episode_length,
            review_outline=request.review_outline,
        )

        return PodcastGenerationResponse(
            job_id=job_id,
            status="submitted",
            message=f"Podcast generation started for episode '{request.episode_name}'",
            episode_profile=request.episode_profile,
            episode_name=request.episode_name,
            mode=request.mode,
        )

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers.
        raise
    except Exception as e:
        logger.error(f"Error generating podcast: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate podcast")


@router.get("/podcasts/jobs/{job_id}")
async def get_podcast_job_status(job_id: str):
    """Get the status of a podcast generation job"""
    try:
        status_data = await PodcastService.get_job_status(job_id)
        return status_data

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers.
        raise
    except Exception as e:
        logger.error(f"Error fetching podcast job status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job status")


@router.get("/podcasts/episodes", response_model=list[PodcastEpisodeResponse])
async def list_podcast_episodes(
    response: Response,
    offset: int = Query(
        0, ge=0, description="Skip the first N completed episodes (default 0)"
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Return at most N episodes (default 50, max 200)"
    ),
):
    """List podcast episodes with offset/limit pagination.

    v0.7.130 — pagination added without breaking the existing response
    shape (still `list[PodcastEpisodeResponse]`). The total count is
    returned in the `X-Total-Count` response header so clients that
    need to render "X of N" can read it without a separate API call.
    Existing callers that don't pass query params get the first 50
    episodes — a sensible behavior change for any install with more
    than 50 episodes that was previously loading every one on every
    list call.

    Filtering rules (unchanged): episodes with no `command` AND no
    `audio_file` are skipped — those are in-flight failures that
    never produced anything useful. The `total` header reflects the
    count AFTER this filter is applied, not the raw row count.
    """
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
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
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
                    mode=normalize_podcast_mode(getattr(episode, "mode", None)),
                    custom_prompt=getattr(episode, "custom_prompt", None),
                    audio_file=episode.audio_file,
                    audio_url=audio_url,
                    transcript=episode.transcript,
                    outline=episode.outline,
                    transcript_segments=getattr(episode, "transcript_segments", []),
                    created=iso(episode.created) if episode.created else None,
                    job_status=job_status,
                    error_message=error_message,
                    generation_stage=getattr(episode, "generation_stage", None),
                )
            )

        # v0.7.130 — apply pagination AFTER filtering. The filter
        # (`if not episode.command and not episode.audio_file: continue`)
        # above strips never-started failed episodes; the X-Total-Count
        # we emit is the count of episodes that pass that filter, not
        # the raw row count. This matches what the client sees in the
        # body and lets the UI render "Showing X-Y of N" accurately.
        total = len(response_episodes)
        paginated = response_episodes[offset : offset + limit]
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Offset"] = str(offset)
        response.headers["X-Limit"] = str(limit)

        return paginated

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers.
        raise
    except Exception as e:
        logger.error(f"Error listing podcast episodes: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list podcast episodes")


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
            except HTTPException:
                # v0.7.108 — re-raise typed HTTPExceptions so the next
                # `except Exception` doesn't clobber them to 500.
                raise
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
            mode=normalize_podcast_mode(getattr(episode, "mode", None)),
            custom_prompt=getattr(episode, "custom_prompt", None),
            audio_file=episode.audio_file,
            audio_url=audio_url,
            transcript=episode.transcript,
            outline=episode.outline,
            transcript_segments=getattr(episode, "transcript_segments", []),
            created=iso(episode.created) if episode.created else None,
            job_status=job_status,
            error_message=error_message,
            generation_stage=getattr(episode, "generation_stage", None),
        )

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers.
        raise
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
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        # The broad `except Exception` below otherwise masks legitimate
        # 404/400 cases as generic 500s.
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

    # v0.8.68 — media type by extension. Was hardcoded audio/mpeg, which
    # mislabels .wav/.m4a/.ogg output if podcast-creator's output format
    # ever differs from MP3 (and breaks strict clients). Unknown extensions
    # keep the historical audio/mpeg default.
    _MEDIA_TYPES = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".flac": "audio/flac",
    }
    return FileResponse(
        audio_path,
        media_type=_MEDIA_TYPES.get(audio_path.suffix.lower(), "audio/mpeg"),
        filename=audio_path.name,
    )


@router.post("/podcasts/episodes/{episode_id}/retry")
async def retry_podcast_episode(episode_id: str):
    """Retry or regenerate a podcast episode by deleting it and submitting a
    new job with the same parameters.

    v0.8.68 — also allowed from "completed": regenerating an episode you're
    not happy with is a first-class workflow (NotebookLM parity), not an
    error. Still blocked while queued/running — retrying an in-flight job
    would orphan the running generation and race it for the episode record.
    """
    # v0.8.70 — serialize concurrent retries of the same episode so the
    # check-then-delete-then-resubmit sequence below is atomic per episode.
    retry_lock = await _get_retry_lock(episode_id)
    try:
        async with retry_lock:
            return await _retry_podcast_episode_locked(episode_id)
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        raise
    except Exception as e:
        logger.error(f"Failed to retry episode {episode_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry episode")


async def _retry_podcast_episode_locked(episode_id: str):
    """Body of the retry handler; runs while holding the per-episode lock."""
    try:
        episode = await PodcastService.get_episode(episode_id)

        # Validate episode is in a terminal state (failed OR completed).
        detail = await episode.get_job_detail()
        if detail["status"] not in ("failed", "error", "completed"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Episode is still in progress (current: "
                    f"{detail['status']}). Wait for it to finish or fail "
                    f"before retrying."
                ),
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

        # v0.7.72 — validate the referenced profiles still exist BEFORE
        # we destructively delete the old episode + its audio file.
        # Previous flow:
        #   delete audio → delete record → submit (which validates
        #   profile names via EpisodeProfile.get_by_name).
        # If the user had renamed or deleted the profile after the
        # original submission, submit_generation_job's ValueError →
        # 400 (added in v0.7.58) would fire AFTER the old episode was
        # already gone — they couldn't even see the failed entry to
        # diagnose, and lost their stored content. Now we resolve
        # profiles upfront so the 400 lands without side effects.
        from deeper_notebook.podcasts.models import (
            EpisodeProfile,
            SpeakerProfile,
        )

        ep_profile_check = await EpisodeProfile.get_by_name(ep_profile_name)
        if ep_profile_check is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot retry: the original episode profile "
                    f"'{ep_profile_name}' no longer exists. Restore the "
                    f"profile (or create a new one with the same name) "
                    f"and retry."
                ),
            )
        sp_profile_check = await SpeakerProfile.get_by_name(sp_profile_name)
        if sp_profile_check is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot retry: the original speaker profile "
                    f"'{sp_profile_name}' no longer exists. Restore the "
                    f"profile (or create a new one with the same name) "
                    f"and retry."
                ),
            )

        # Delete audio file if any. v0.7.2 — skip unlink for paths
        # outside _AUDIO_ROOT (None) instead of trusting the DB value.
        if episode.audio_file:
            audio_path = _resolve_audio_path(episode.audio_file)
            if audio_path is None:
                logger.warning(
                    "Retry: skipping audio cleanup — episode.audio_file "
                    "({}) is outside the podcast output root",
                    episode.audio_file,
                )
            elif audio_path.exists():
                try:
                    audio_path.unlink()
                    # v0.8.68 — also sweep the now-empty UUID directory.
                    _cleanup_episode_dir(audio_path)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
                except Exception as e:
                    logger.warning(f"Failed to delete audio file {audio_path}: {e}")

        # Delete the failed episode
        await episode.delete()

        # Submit a new job.
        # v0.8.68 — replay the user's per-episode customization. The suffix
        # was previously dropped on retry, silently regenerating with the
        # base briefing only (different output than the user asked for).
        job_id = await PodcastService.submit_generation_job(
            episode_profile_name=ep_profile_name,
            speaker_profile_name=sp_profile_name,
            episode_name=episode_name,
            content=content,
            briefing_suffix=getattr(episode, "briefing_suffix", None),
            mode=getattr(episode, "mode", None),
            custom_prompt=(
                getattr(episode, "custom_prompt", None)
                or getattr(episode, "briefing_suffix", None)
            ),
        )

        return {"job_id": job_id, "message": "Retry submitted successfully"}

    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        # The broad `except Exception` below otherwise masks legitimate
        # 404/400 cases as generic 500s.
        raise
    except Exception as e:
        logger.error(f"Error retrying podcast episode: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retry episode")


class OutlineSegmentUpdate(BaseModel):
    """v0.8.68 — one outline segment, mirroring podcast-creator's Segment."""

    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1, max_length=5000)
    size: str = Field("medium", pattern="^(short|medium|long)$")


class OutlineUpdateRequest(BaseModel):
    segments: list[OutlineSegmentUpdate] = Field(..., min_length=1, max_length=20)


@router.post("/podcasts/episodes/{episode_id}/cancel")
async def cancel_podcast_episode(episode_id: str):
    """v0.8.68 — request cancellation of an in-flight generation. The worker
    polls the flag every ~5s and aborts the graph task; the episode ends up
    failed with a 'cancelled by user' message. No-op (400) for episodes that
    aren't queued/running."""
    try:
        episode = await PodcastService.get_episode(episode_id)
        detail = await episode.get_job_detail()
        if detail["status"] not in ("queued", "running", "submitted", "new"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Episode is not in progress (current: "
                    f"{detail['status']}) — nothing to cancel."
                ),
            )
        episode.cancel_requested = True
        await episode.save()
        return {"message": "Cancellation requested", "episode_id": episode_id}
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        raise
    except Exception as e:
        logger.error(f"Error cancelling podcast episode: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel episode")


@router.put("/podcasts/episodes/{episode_id}/outline")
async def update_episode_outline(episode_id: str, request: OutlineUpdateRequest):
    """v0.8.68 — outline-review workflow: save the user's edited outline.
    Only allowed while the episode is awaiting review (the outline is about
    to drive transcript + TTS; editing it after audio exists would lie)."""
    from deeper_notebook.podcasts.models import STAGE_AWAITING_REVIEW

    try:
        episode = await PodcastService.get_episode(episode_id)
        if episode.generation_stage != STAGE_AWAITING_REVIEW:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Outline can only be edited while the episode is awaiting review."
                ),
            )
        episode.outline = {"segments": [s.model_dump() for s in request.segments]}
        await episode.save()
        return {"message": "Outline updated", "outline": episode.outline}
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        raise
    except Exception as e:
        logger.error(f"Error updating episode outline: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update outline")


@router.post("/podcasts/episodes/{episode_id}/approve-outline")
async def approve_episode_outline(episode_id: str):
    """v0.8.68 — outline-review workflow: approve the (possibly edited)
    outline and generate transcript + audio from it."""
    try:
        job_id = await PodcastService.submit_outline_approval(episode_id)
        return {
            "job_id": job_id,
            "message": "Outline approved — generating transcript and audio",
        }
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error approving episode outline: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to approve outline")


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
                    "({}) is outside the podcast output root",
                    episode.audio_file,
                )
            elif audio_path.exists():
                try:
                    audio_path.unlink()
                    logger.info(f"Deleted audio file: {audio_path}")
                    # v0.8.68 — also sweep the now-empty UUID directory.
                    _cleanup_episode_dir(audio_path)
                except HTTPException:
                    # v0.7.108 — re-raise typed HTTPExceptions so the next
                    # `except Exception` doesn't clobber them to 500.
                    raise
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
        raise HTTPException(status_code=500, detail="Failed to delete episode")


# ---------------------------------------------------------------------------
# v0.7.31 — /podcasts/suggest
#
# Analyzes selected source IDs / notebook IDs and recommends:
#   - The best-fit episode preset (one of the v0.7.30 9 presets)
#   - A length in minutes calibrated to total content volume
#   - An auto-derived episode title (from the notebook or first source)
#   - Optional briefing additions that pin the suggestion to the
#     content's distinguishing features
#
# Pure heuristic — no LLM call. Local-deploy friendly: instant,
# deterministic, no cost. The user can always override every field
# the suggestion returns before generation.
# ---------------------------------------------------------------------------


class SuggestRequest(BaseModel):
    """Inputs for /podcasts/suggest. Either notebook_id OR source_ids
    (or both) — the endpoint will union the available content."""

    notebook_id: Optional[str] = Field(
        None, description="Notebook ID; sources + notes from it are analyzed"
    )
    source_ids: Optional[list[str]] = Field(
        None, description="Explicit source IDs to analyze"
    )


class SuggestResponse(BaseModel):
    episode_profile_name: str = Field(
        ..., description="Recommended preset name (matches an existing profile)"
    )
    length_minutes: int = Field(..., description="Recommended episode length")
    title: str = Field(..., description="Auto-generated episode title")
    briefing_addition: str = Field(
        default="",
        description=(
            "Optional briefing suffix that focuses the suggested preset "
            "on this content's distinguishing features. May be empty."
        ),
    )
    reasoning: str = Field(..., description="One-line plain-English why-we-picked-this")
    matched_signals: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Heuristic scores per preset, for transparency / debugging. "
            "Highest score wins."
        ),
    )


# Keyword signals: each list is OR'd; matching titles / topics nudges the
# corresponding preset's score. Tuned for low false-positive rate — only
# strong, near-unambiguous indicators.
_SIGNALS: dict[str, list[str]] = {
    "Tutorial": [
        "how to",
        "how-to",
        "tutorial",
        "guide",
        "walkthrough",
        "getting started",
        "step-by-step",
        "step by step",
        "beginners",
        "intro to",
        "introduction to",
        "primer",
        "lesson",
        "cookbook",
        "handbook",
    ],
    "News Roundup": [
        "news",
        "weekly",
        "daily",
        "roundup",
        "digest",
        "headlines",
        "this week",
        "report",
        "press release",
        "announcement",
    ],
    "Debate": [
        "vs",
        "versus",
        "debate",
        "argument",
        "controversy",
        "critique",
        "rebuttal",
        "for and against",
        "pros and cons",
        "case against",
        "case for",
    ],
    "Recap & Review": [
        "review",
        "recap",
        "verdict",
        "rating",
        "assessment",
        "post-mortem",
        "retrospective",
        "book",
        "paper",
        "thesis",
        "dissertation",
    ],
    "Story Mode": [
        "story",
        "history of",
        "the rise of",
        "the fall of",
        "biography",
        "memoir",
        "chronicle",
        "narrative",
        "saga",
    ],
    "Q&A Interview": [
        "interview",
        "q&a",
        "ask me anything",
        "ama",
        "questions",
        "conversation with",
    ],
    "Deep Dive": [
        "deep dive",
        "everything you",
        "in depth",
        "comprehensive",
        "complete guide",
        "definitive guide",
        "explained",
    ],
}


def _score_signals(text: str) -> dict[str, int]:
    """Return a {preset_name: hit_count} score map from a corpus string."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for preset, keywords in _SIGNALS.items():
        scores[preset] = sum(1 for kw in keywords if kw in lower)
    return scores


def _length_from_volume(total_chars: int, source_count: int) -> int:
    """Map content volume → recommended episode length in minutes."""
    # Calibrated for ~150 wpm conversational pace.
    # < 3 KB or only 1 source → quick brief (4 min)
    # 3-15 KB → standard (~6-8 min)
    # 15-60 KB → medium-deep (~10-12 min)
    # > 60 KB → deep dive (~15 min)
    if total_chars < 3_000 or source_count <= 1:
        return 4
    if total_chars < 15_000:
        return 7
    if total_chars < 60_000:
        return 11
    return 15


@router.post("/podcasts/suggest", response_model=SuggestResponse)
async def suggest_episode(req: SuggestRequest):
    """Recommend an episode profile + length + title based on content.

    Heuristic-only — no LLM call. Returns instantly. The user can
    override every suggested field in the generation dialog.

    Decision rule:
      1. Collect titles + topics + total content size from the inputs.
      2. Score each preset by keyword hits in titles/topics.
      3. If the top score is ≥ 2, pick that preset.
      4. Otherwise default by volume: small → Quick Brief, large →
         Deep Dive, mid → Deeper Notebook Local (the safe default).
    """
    # ---- 1. Resolve content from the request ----
    source_ids: list[str] = list(req.source_ids or [])
    notebook_title: Optional[str] = None

    if req.notebook_id:
        # Pull the notebook + all its source IDs
        try:
            nb_rows = await repo_query(
                "SELECT name FROM ONLY $id;",
                {"id": req.notebook_id},
            )
            if isinstance(nb_rows, list) and nb_rows:
                notebook_title = nb_rows[0].get("name")
            elif isinstance(nb_rows, dict):
                notebook_title = nb_rows.get("name")
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("suggest: notebook fetch failed: {}", exc)
        try:
            # Sources are linked via a reference edge (`reference`).
            ref_rows = await repo_query(
                "SELECT <-reference<-source.id AS source_ids FROM ONLY $id;",
                {"id": req.notebook_id},
            )
            ids: list[str] = []
            if isinstance(ref_rows, list) and ref_rows:
                ids = ref_rows[0].get("source_ids") or []
            elif isinstance(ref_rows, dict):
                ids = ref_rows.get("source_ids") or []
            source_ids.extend([str(s) for s in ids])
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("suggest: notebook source fetch failed: {}", exc)

    # Dedupe while preserving order
    seen = set()
    source_ids = [s for s in source_ids if not (s in seen or seen.add(s))]

    titles: list[str] = []
    topics_corpus: list[str] = []
    total_chars = 0
    if source_ids:
        try:
            # Single SurrealQL trip; aggregate fields we need for scoring.
            rows = await repo_query(
                "SELECT title, topics, string::len(full_text) AS chars "
                "FROM source WHERE id INSIDE $ids;",
                {"ids": source_ids},
            )
            for r in rows or []:
                t = r.get("title")
                if isinstance(t, str):
                    titles.append(t)
                topics = r.get("topics") or []
                if isinstance(topics, list):
                    topics_corpus.extend(str(x) for x in topics)
                chars = r.get("chars")
                if isinstance(chars, (int, float)):
                    total_chars += int(chars)
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("suggest: source fetch failed: {}", exc)

    # ---- 2. Score presets against the corpus ----
    corpus = " ".join(filter(None, [notebook_title] + titles + topics_corpus))
    scores = _score_signals(corpus) if corpus.strip() else {}
    top_preset = max(scores.items(), key=lambda kv: kv[1], default=("", 0))

    # ---- 3. Pick a preset ----
    available_presets: set = set()
    try:
        # Resolve real presets from DB so we never recommend a name
        # the user has deleted. Falls back to the v0.7.30 default if
        # this fetch fails.
        prof_rows = await repo_query("SELECT name FROM episode_profile;")
        available_presets = {r.get("name") for r in prof_rows or [] if r.get("name")}
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as exc:
        logger.warning("suggest: episode_profile list failed: {}", exc)

    source_count = len(source_ids)
    if top_preset[1] >= 2 and top_preset[0] in available_presets:
        chosen = top_preset[0]
        reason = (
            f"Source titles strongly suggest '{chosen}' format "
            f"({top_preset[1]} matching signals)."
        )
    else:
        # Volume-based default
        if source_count <= 1 or total_chars < 3_000:
            chosen = "Quick Brief"
            reason = "Small content volume — a tight brief works best."
        elif total_chars >= 60_000:
            chosen = "Deep Dive"
            reason = "Large content volume — long-form deep dive fits."
        else:
            chosen = CANONICAL_LOCAL_EPISODE_PROFILE
            reason = "Balanced two-host format for mid-sized content."
        equivalent = select_existing_episode_profile_name(
            chosen,
            available_presets,
        )
        if equivalent is not None:
            chosen = equivalent
        # If our default isn't available (user deleted everything but
        # one), fall back to whatever exists.
        if chosen not in available_presets and available_presets:
            chosen = sorted(available_presets)[0]
            reason += f" (Falling back to available preset '{chosen}'.)"
        elif chosen not in available_presets:
            # No presets at all in DB. Return the chosen name anyway;
            # the frontend will surface the error if generation fails.
            reason += " (Warning: no matching preset is configured.)"

    # ---- 4. Length + title + briefing addition ----
    length = _length_from_volume(total_chars, source_count)
    title = notebook_title or (titles[0] if titles else "Untitled Episode")
    # Trim long titles for the episode_name field (UI shows it raw).
    title = title.strip()[:120] or "Untitled Episode"

    briefing_addition = ""
    if notebook_title and source_count > 0:
        briefing_addition = (
            f"Center the episode on the notebook '{notebook_title}'. "
            f"The material spans {source_count} source"
            f"{'s' if source_count != 1 else ''}."
        )

    return SuggestResponse(
        episode_profile_name=chosen,
        length_minutes=length,
        title=title,
        briefing_addition=briefing_addition,
        reasoning=reason,
        matched_signals=scores,
    )
