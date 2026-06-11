import asyncio
from typing import Any, Dict, Optional

from fastapi import HTTPException
from loguru import logger
from pydantic import BaseModel
from surreal_commands import get_command_status, submit_command

from open_notebook.domain.notebook import Notebook
from api.utils.iso import iso  # v0.7.183 — Safari-safe datetime serialization
from open_notebook.exceptions import ConfigurationError  # v0.8.68 — offline gate
from open_notebook.podcasts.models import EpisodeProfile, PodcastEpisode, SpeakerProfile


class PodcastGenerationRequest(BaseModel):
    """Request model for podcast generation"""

    episode_profile: str
    speaker_profile: str
    episode_name: str
    content: Optional[str] = None
    notebook_id: Optional[str] = None
    briefing_suffix: Optional[str] = None


class PodcastGenerationResponse(BaseModel):
    """Response model for podcast generation"""

    job_id: str
    status: str
    message: str
    episode_profile: str
    episode_name: str


class PodcastService:
    """Service layer for podcast operations"""

    @staticmethod
    async def _gate_offline_cloud_models(episode_profile, speaker_profile) -> None:
        """v0.8.68 — raise a clear, typed error when the machine is offline
        (real or Offline-mode toggle) and the podcast's profiles reference
        cloud-provider models. Local providers (llama.cpp / ollama / piper via
        openai_compatible) are never blocked. Best-effort: any failure inside
        the gate itself is swallowed so it can't break a submit that would
        have worked before."""
        try:
            from open_notebook.ai.offline_gate import LOCAL_PROVIDERS
            from open_notebook.health.network import (
                get_network_state_with_settings,
            )

            state = await get_network_state_with_settings()
            if state.status != "offline":
                return

            cloud_models: list[str] = []
            for label, resolver in (
                ("voice (text-to-speech)", speaker_profile.resolve_tts_config),
                ("outline LLM", episode_profile.resolve_outline_config),
                ("transcript LLM", episode_profile.resolve_transcript_config),
            ):
                try:
                    provider, model_name, _cfg = await resolver()
                except Exception:
                    continue  # unresolvable profile keeps its existing error path
                if (provider or "").strip().lower().replace("-", "_") not in LOCAL_PROVIDERS:
                    cloud_models.append(f"{label}: {model_name} ({provider})")
        except ConfigurationError:
            raise
        except Exception as exc:
            logger.debug(f"podcast offline gate skipped (non-fatal): {exc}")
            return

        if cloud_models:
            reason = (
                "Offline mode is on" if state.forced_offline else "You're offline"
            )
            raise ConfigurationError(
                f"{reason}, and this podcast profile uses cloud models that "
                f"can't be reached: {'; '.join(cloud_models)}. Reconnect, or "
                f"switch the profile to local models (Settings → Podcasts)."
            )

    @staticmethod
    async def submit_generation_job(
        episode_profile_name: str,
        speaker_profile_name: str,
        episode_name: str,
        notebook_id: Optional[str] = None,
        content: Optional[str] = None,
        briefing_suffix: Optional[str] = None,
    ) -> str:
        """Submit a podcast generation job for background processing"""
        try:
            # Validate episode profile exists
            episode_profile = await EpisodeProfile.get_by_name(episode_profile_name)
            if not episode_profile:
                raise ValueError(f"Episode profile '{episode_profile_name}' not found")

            # Validate speaker profile exists
            speaker_profile = await SpeakerProfile.get_by_name(speaker_profile_name)
            if not speaker_profile:
                raise ValueError(f"Speaker profile '{speaker_profile_name}' not found")

            # v0.8.68 — offline gate at SUBMIT time (spec §6 follow-up). The
            # podcast worker calls TTS/LLM providers directly (not through
            # provision_langchain_model), so the chat offline gate never sees
            # it: offline + a cloud voice/LLM previously meant a job that hung
            # against an unreachable provider for up to the 1800s timeout
            # before failing. Fail fast HERE with the offending models named,
            # while the user is looking at the submit button. Fail-open on
            # resolution errors: an unresolvable profile keeps its existing
            # downstream error path.
            await PodcastService._gate_offline_cloud_models(
                episode_profile, speaker_profile
            )

            # Get content from notebook if not provided directly
            if not content and notebook_id:
                try:
                    notebook = await Notebook.get(notebook_id)
                    # v0.7.201 — was `str(notebook) if no get_context`
                    # which, on a stale ID (Notebook.get returned None),
                    # silently wrote the literal string "None" as the
                    # podcast's content. Generation then went through
                    # with empty source material and produced a
                    # nonsensical episode. Raise NotFoundError before
                    # touching `notebook` so the user gets a clear
                    # error at submission time.
                    if notebook is None:
                        from open_notebook.exceptions import NotFoundError
                        raise NotFoundError(
                            f"Notebook {notebook_id} not found"
                        )
                    content = (
                        await notebook.get_context()
                        if hasattr(notebook, "get_context")
                        else str(notebook)
                    )
                except Exception as e:
                    # v0.7.201 — let typed NotFoundError pass through
                    # so the global classifier emits a clean 404 with
                    # the user-facing message above. Other failures
                    # still fall back to the notebook-id-only content
                    # path (kept for backward compat with non-fatal
                    # transient DB hiccups).
                    from open_notebook.exceptions import NotFoundError
                    if isinstance(e, NotFoundError):
                        raise
                    logger.warning(
                        f"Failed to get notebook content, using notebook_id as content: {e}"
                    )
                    content = f"Notebook ID: {notebook_id}"

            if not content:
                raise ValueError(
                    "Content is required - provide either content or notebook_id"
                )

            # Prepare command arguments
            command_args = {
                "episode_profile": episode_profile_name,
                "speaker_profile": speaker_profile_name,
                "episode_name": episode_name,
                "content": str(content),
                "briefing_suffix": briefing_suffix,
            }

            # Ensure command modules are imported before submitting
            # This is needed because submit_command validates against local registry
            try:
                import commands.podcast_commands  # noqa: F401
            except ImportError as import_err:
                logger.error(f"Failed to import podcast commands: {import_err}")
                raise ValueError("Podcast commands not available")

            # v0.7.55 — surreal_commands.submit_command opens a SYNCHRONOUS
            # SurrealDB WS connection (sign-in + use + create), which
            # blocks the FastAPI event loop for the duration of the
            # handshake. Under concurrent podcast submissions or general
            # load this stalls every other in-flight request (chat
            # streams, SSE polls, etc.). Move the blocking call onto a
            # worker thread so the event loop stays responsive.
            # v0.7.115 — also wrap in wait_for so a hung pool can't
            # pin the podcast-generation endpoint. Same env knob as
            # CommandService.submit_command_job for consistency.
            import os as _os_for_timeout
            _submit_timeout = float(
                _os_for_timeout.environ.get("ONP_SUBMIT_COMMAND_TIMEOUT_SEC", "10").strip()
                or 10
            )
            try:
                job_id = await asyncio.wait_for(
                    asyncio.to_thread(
                        submit_command, "open_notebook",
                        "generate_podcast", command_args,
                    ),
                    timeout=_submit_timeout,
                )
            except asyncio.TimeoutError as exc:
                raise ValueError(
                    f"Podcast submission timed out after {_submit_timeout:.0f}s. "
                    "The SurrealDB pool may be saturated. Raise "
                    "ONP_SUBMIT_COMMAND_TIMEOUT_SEC or check pool health."
                ) from exc

            # Convert RecordID to string if needed
            if not job_id:
                raise ValueError("Failed to get job_id from submit_command")
            job_id_str = str(job_id)
            logger.info(
                f"Submitted podcast generation job: {job_id_str} for episode '{episode_name}'"
            )
            return job_id_str

        except ValueError as e:
            # v0.7.58 — distinguish user-input errors (missing profile,
            # missing content, "commands not available") from genuine
            # 500s. Previously the broad `except Exception` mapped every
            # one of these to HTTP 500 "Server error", which is wrong:
            # they're caller mistakes, the user should see a 400 with
            # the actual reason ("Episode profile 'X' not found").
            logger.warning(f"Podcast submission rejected: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            # v0.7.177 — Don't echo str(e) back to the client. The
            # underlying exception can carry driver internals (SurrealDB
            # WS frames, connection-pool diagnostics, partial RecordIDs)
            # which are sensitive operationally and useless to the
            # caller. logger.error captures the full picture for ops;
            # the client gets a generic message. Same pattern as the
            # v0.7.168 router sweep that this service file missed.
            logger.error(f"Failed to submit podcast generation job: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to submit podcast generation job",
            )

    @staticmethod
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Get status of a podcast generation job"""
        try:
            status = await get_command_status(job_id)
            return {
                "job_id": job_id,
                "status": status.status if status else "unknown",
                "result": status.result if status else None,
                "error_message": getattr(status, "error_message", None)
                if status
                else None,
                "created": iso(status.created)
                if status and hasattr(status, "created") and status.created
                else None,
                "updated": iso(status.updated)
                if status and hasattr(status, "updated") and status.updated
                else None,
                "progress": getattr(status, "progress", None) if status else None,
            }
        except Exception as e:
            # v0.7.177 — Sanitize 500 detail; logger.error keeps the
            # full exception for ops, the client gets a generic message.
            logger.error(f"Failed to get podcast job status: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to get job status"
            )

    @staticmethod
    async def list_episodes() -> list:
        """List all podcast episodes"""
        try:
            episodes = await PodcastEpisode.get_all(order_by="created desc")
            return episodes
        except Exception as e:
            # v0.7.177 — Sanitize 500 detail (see above).
            logger.error(f"Failed to list podcast episodes: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to list episodes"
            )

    @staticmethod
    async def get_episode(episode_id: str) -> PodcastEpisode:
        """Get a specific podcast episode"""
        # v0.7.204 — was a bare `try/except Exception` that turned
        # EVERY failure (DB connection drop, mid-query timeout,
        # decryption error, etc.) into 404 "Episode not found". An
        # operator looking at logs saw a real backend issue but
        # the API client got the same 404 it would for a stale ID
        # — debugging took 10× longer because the symptom was
        # misclassified. Now: a None return from
        # `PodcastEpisode.get` (the actual "not found" path) raises
        # NotFoundError; everything else propagates as its real
        # type and hits the global classifier with the right
        # HTTP code (500 for DB, 502 for upstream, etc.).
        from open_notebook.exceptions import NotFoundError

        episode = await PodcastEpisode.get(episode_id)
        if episode is None:
            raise NotFoundError(f"Episode {episode_id} not found")
        return episode


class DefaultProfiles:
    """Utility class for creating default profiles (if needed beyond migration data)"""

    @staticmethod
    async def create_default_episode_profiles():
        """Create default episode profiles if they don't exist"""
        try:
            # Check if profiles already exist
            existing = await EpisodeProfile.get_all()
            if existing:
                logger.info(f"Episode profiles already exist: {len(existing)} found")
                return existing

            # This would create profiles, but since we have migration data,
            # this is mainly for future extensibility
            logger.info(
                "Default episode profiles should be created via database migration"
            )
            return []

        except Exception as e:
            logger.error(f"Failed to create default episode profiles: {e}")
            raise

    @staticmethod
    async def create_default_speaker_profiles():
        """Create default speaker profiles if they don't exist"""
        try:
            # Check if profiles already exist
            existing = await SpeakerProfile.get_all()
            if existing:
                logger.info(f"Speaker profiles already exist: {len(existing)} found")
                return existing

            # This would create profiles, but since we have migration data,
            # this is mainly for future extensibility
            logger.info(
                "Default speaker profiles should be created via database migration"
            )
            return []

        except Exception as e:
            logger.error(f"Failed to create default speaker profiles: {e}")
            raise
