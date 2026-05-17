import time
import uuid
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.config import DATA_FOLDER
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.podcasts.models import (
    EpisodeProfile,
    PodcastEpisode,
    SpeakerProfile,
    _resolve_model_config,
)

try:
    from podcast_creator import configure, create_podcast
except ImportError as e:
    logger.error(f"Failed to import podcast_creator: {e}")
    raise ValueError("podcast_creator library not available")


def build_episode_output_dir(data_folder: str) -> tuple[str, Path]:
    """Build a filesystem-safe output directory path for a podcast episode.

    Uses a UUID as the directory name so the path is safe regardless of
    what the user typed as episode name (spaces, special chars, etc.).

    Returns:
        A tuple of (episode_dir_name, output_dir_path).
    """
    episode_dir_name = str(uuid.uuid4())
    output_dir = Path(f"{data_folder}/podcasts/episodes/{episode_dir_name}")
    return episode_dir_name, output_dir


def full_model_dump(model):
    if isinstance(model, BaseModel):
        return model.model_dump()
    elif isinstance(model, dict):
        return {k: full_model_dump(v) for k, v in model.items()}
    elif isinstance(model, list):
        return [full_model_dump(item) for item in model]
    else:
        return model


class PodcastGenerationInput(CommandInput):
    episode_profile: str
    speaker_profile: str
    episode_name: str
    content: str
    briefing_suffix: Optional[str] = None


class PodcastGenerationOutput(CommandOutput):
    success: bool
    episode_id: Optional[str] = None
    audio_file_path: Optional[str] = None
    transcript: Optional[dict] = None
    outline: Optional[dict] = None
    processing_time: float
    error_message: Optional[str] = None


@command("generate_podcast", app="open_notebook", retry={"max_attempts": 1})
async def generate_podcast_command(
    input_data: PodcastGenerationInput,
) -> PodcastGenerationOutput:
    """
    Real podcast generation using podcast-creator library with Episode Profiles
    """
    start_time = time.time()

    try:
        logger.info(
            f"Starting podcast generation for episode: {input_data.episode_name}"
        )
        logger.info(f"Using episode profile: {input_data.episode_profile}")

        # 1. Load Episode and Speaker profiles from SurrealDB
        episode_profile = await EpisodeProfile.get_by_name(input_data.episode_profile)
        if not episode_profile:
            raise ValueError(
                f"Episode profile '{input_data.episode_profile}' not found"
            )

        speaker_profile = await SpeakerProfile.get_by_name(
            episode_profile.speaker_config
        )
        if not speaker_profile:
            raise ValueError(
                f"Speaker profile '{episode_profile.speaker_config}' not found"
            )

        logger.info(f"Loaded episode profile: {episode_profile.name}")
        logger.info(f"Loaded speaker profile: {speaker_profile.name}")

        # 2. Validate that model registry fields are populated
        if not episode_profile.outline_llm:
            raise ValueError(
                f"Episode profile '{episode_profile.name}' has no outline model configured. "
                "Please update the profile to select an outline model."
            )
        if not episode_profile.transcript_llm:
            raise ValueError(
                f"Episode profile '{episode_profile.name}' has no transcript model configured. "
                "Please update the profile to select a transcript model."
            )
        if not speaker_profile.voice_model:
            raise ValueError(
                f"Speaker profile '{speaker_profile.name}' has no voice model configured. "
                "Please update the profile to select a voice model."
            )

        # 3. Resolve model configs with credentials
        outline_provider, outline_model_name, outline_config = (
            await episode_profile.resolve_outline_config()
        )
        transcript_provider, transcript_model_name, transcript_config = (
            await episode_profile.resolve_transcript_config()
        )
        tts_provider, tts_model_name, tts_config = (
            await speaker_profile.resolve_tts_config()
        )

        logger.info(
            f"Resolved models - outline: {outline_provider}/{outline_model_name}, "
            f"transcript: {transcript_provider}/{transcript_model_name}, "
            f"tts: {tts_provider}/{tts_model_name}"
        )

        # 4. Load all profiles and configure podcast-creator
        episode_profiles = await repo_query("SELECT * FROM episode_profile")
        speaker_profiles = await repo_query("SELECT * FROM speaker_profile")

        # Transform the surrealdb array into a dictionary for podcast-creator
        episode_profiles_dict = {
            profile["name"]: profile for profile in episode_profiles
        }
        speaker_profiles_dict = {
            profile["name"]: profile for profile in speaker_profiles
        }

        # 5. Inject resolved model configs into profile dicts
        # Resolve ALL episode profiles (podcast-creator validates all).
        # Remove profiles that fail resolution to prevent validation errors.
        for ep_name in list(episode_profiles_dict.keys()):
            ep_dict = episode_profiles_dict[ep_name]
            try:
                if ep_dict.get("outline_llm"):
                    prov, model, conf = await _resolve_model_config(
                        str(ep_dict["outline_llm"])
                    )
                    ep_dict["outline_provider"] = prov
                    ep_dict["outline_model"] = model
                    ep_dict["outline_config"] = conf
                if ep_dict.get("transcript_llm"):
                    prov, model, conf = await _resolve_model_config(
                        str(ep_dict["transcript_llm"])
                    )
                    ep_dict["transcript_provider"] = prov
                    ep_dict["transcript_model"] = model
                    ep_dict["transcript_config"] = conf
            except Exception as e:
                logger.warning(
                    f"Failed to resolve models for episode profile '{ep_name}', "
                    f"removing from config to prevent validation errors: {e}"
                )
                del episode_profiles_dict[ep_name]

        # Resolve TTS for ALL speaker profiles (podcast-creator validates all).
        # Remove profiles that fail resolution to prevent validation errors.
        for sp_name in list(speaker_profiles_dict.keys()):
            sp_dict = speaker_profiles_dict[sp_name]
            if sp_dict.get("voice_model"):
                try:
                    prov, model, conf = await _resolve_model_config(
                        str(sp_dict["voice_model"])
                    )
                    sp_dict["tts_provider"] = prov
                    sp_dict["tts_model"] = model
                    sp_dict["tts_config"] = conf
                except Exception as e:
                    logger.warning(
                        f"Failed to resolve TTS for speaker profile '{sp_name}', "
                        f"removing from config to prevent validation errors: {e}"
                    )
                    del speaker_profiles_dict[sp_name]
                    continue

            # Per-speaker TTS overrides
            for speaker in sp_dict.get("speakers", []):
                if speaker.get("voice_model"):
                    try:
                        prov, model, conf = await _resolve_model_config(
                            str(speaker["voice_model"])
                        )
                        speaker["tts_provider"] = prov
                        speaker["tts_model"] = model
                        speaker["tts_config"] = conf
                    except Exception as e:
                        logger.warning(
                            f"Failed to resolve per-speaker TTS for '{speaker.get('name')}': {e}"
                        )

        # 6. Generate briefing
        briefing = episode_profile.default_briefing
        if input_data.briefing_suffix:
            briefing += f"\n\nAdditional instructions: {input_data.briefing_suffix}"

        # Create the record for the episode and associate with the ongoing command
        episode = PodcastEpisode(
            name=input_data.episode_name,
            episode_profile=full_model_dump(episode_profile.model_dump()),
            speaker_profile=full_model_dump(speaker_profile.model_dump()),
            command=ensure_record_id(input_data.execution_context.command_id)
            if input_data.execution_context
            else None,
            briefing=briefing,
            content=input_data.content,
            audio_file=None,
            transcript=None,
            outline=None,
        )
        await episode.save()

        configure("speakers_config", {"profiles": speaker_profiles_dict})
        configure("episode_config", {"profiles": episode_profiles_dict})

        logger.info("Configured podcast-creator with episode and speaker profiles")

        logger.info(f"Generated briefing (length: {len(briefing)} chars)")

        # 7. Create output directory using UUID for filesystem-safe paths
        episode_dir_name, output_dir = build_episode_output_dir(DATA_FOLDER)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created output directory: {output_dir}")

        # 8. Generate podcast using podcast-creator.
        # v0.7.3 — wrap in try/except so we can clean up empty output_dir
        # if generation fails. Without this, every failed generation
        # leaves an empty UUID directory under data/podcasts/episodes/
        # that accumulates over time (disk-fill). We only remove the dir
        # if it's empty post-failure — never delete partial output that
        # might still be useful for diagnostics.
        logger.info("Starting podcast generation with podcast-creator...")

        try:
            result = await create_podcast(
                content=input_data.content,
                briefing=briefing,
                episode_name=episode_dir_name,
                output_dir=str(output_dir),
                speaker_config=speaker_profile.name,
                episode_profile=episode_profile.name,
            )
        except Exception:
            # Leave non-empty dirs alone — those have partial output
            # (transcript file, intermediate WAVs) that the user can
            # inspect to understand the failure.
            try:
                if output_dir.exists() and not any(output_dir.iterdir()):
                    output_dir.rmdir()
                    logger.info(
                        "Cleaned up empty output dir after failure: {}",
                        output_dir,
                    )
            except Exception as cleanup_exc:
                logger.warning(
                    "Could not clean up output dir {} after failure: {}",
                    output_dir, cleanup_exc,
                )
            raise

        # v0.7.3 — defensive: result may be None (early-return) or a
        # partial dict missing keys (future podcast-creator versions, edge
        # cases where audio succeeded but transcript/outline failed). The
        # PodcastGenerationOutput block below already uses .get() for the
        # same fields — this block was inconsistent and would KeyError on
        # the indexed access, masking a partial success as a worker crash.
        episode.audio_file = (
            str(result.get("final_output_file_path")) if result else None
        )
        episode.transcript = {
            "transcript": full_model_dump(result.get("transcript"))
            if result and result.get("transcript") is not None
            else None
        }
        episode.outline = (
            full_model_dump(result.get("outline"))
            if result and result.get("outline") is not None
            else None
        )
        await episode.save()

        processing_time = time.time() - start_time
        logger.info(
            f"Successfully generated podcast episode: {episode.id} in {processing_time:.2f}s"
        )

        # v0.7.69 — harden against `result is None` and partial-result
        # shapes. The earlier `episode.audio_file = ...` block (lines
        # 286-298) was fixed in v0.7.3 to handle this, but THIS return
        # block was missed — `result["transcript"]` / `result["outline"]`
        # subscript access would AttributeError on a None result, masking
        # what is otherwise a successful (but transcript/outline-less)
        # generation as a worker crash that the user can't retry from
        # (max_attempts=1). The earlier block uses the same `.get()`
        # pattern below, applied uniformly.
        transcript_payload = None
        outline_payload = None
        audio_path = None
        if result:
            audio_path = (
                str(result.get("final_output_file_path"))
                if result.get("final_output_file_path") is not None
                else None
            )
            t = result.get("transcript")
            if t is not None:
                transcript_payload = {"transcript": full_model_dump(t)}
            o = result.get("outline")
            if o is not None:
                outline_payload = full_model_dump(o)

        return PodcastGenerationOutput(
            success=True,
            episode_id=str(episode.id),
            audio_file_path=audio_path,
            transcript=transcript_payload,
            outline=outline_payload,
            processing_time=processing_time,
        )

    except ValueError:
        raise

    except Exception as e:
        logger.error(f"Podcast generation failed: {e}")
        logger.exception(e)

        error_msg = str(e)
        if "Invalid json output" in error_msg or "Expecting value" in error_msg:
            error_msg += (
                "\n\nNOTE: This error commonly occurs with GPT-5 models that use extended thinking. "
                "The model may be putting all output inside <think> tags, leaving nothing to parse. "
                "Try using gpt-4o, gpt-4o-mini, or gpt-4-turbo instead in your episode profile."
            )

        raise RuntimeError(error_msg) from e
