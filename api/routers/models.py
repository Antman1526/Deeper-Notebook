import os
import traceback
from typing import Dict, List, Optional

from esperanto import AIFactory
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from api.models import (
    DefaultModelsResponse,
    ModelCreate,
    ModelResponse,
    ProviderAvailabilityResponse,
)
from api.utils.iso import iso  # v0.7.182 — Safari-safe datetime serialization
from deeper_notebook.ai.connection_tester import test_individual_model
from deeper_notebook.ai.key_provider import provision_provider_keys
from deeper_notebook.ai.model_discovery import (
    discover_provider_models,
    get_provider_model_count,
    sync_all_providers,
    sync_provider_models,
)
from deeper_notebook.ai.models import DefaultModels, Model
from deeper_notebook.domain.credential import Credential
from deeper_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


# =============================================================================
# Model Discovery Response Models
# =============================================================================


class DiscoveredModelResponse(BaseModel):
    """Response model for a discovered model."""

    name: str
    provider: str
    model_type: str
    description: Optional[str] = None


class ProviderSyncResponse(BaseModel):
    """Response model for provider sync operation."""

    provider: str
    discovered: int
    new: int
    existing: int


class AllProvidersSyncResponse(BaseModel):
    """Response model for syncing all providers."""

    results: dict[str, ProviderSyncResponse]
    total_discovered: int
    total_new: int


class ProviderModelCountResponse(BaseModel):
    """Response model for provider model counts."""

    provider: str
    counts: dict[str, int]
    total: int


class AutoAssignResult(BaseModel):
    """Response model for auto-assign operation."""

    assigned: dict[str, str]  # slot_name -> model_id
    skipped: list[str]  # slots already assigned
    missing: list[str]  # slots with no available models


class ModelTestResponse(BaseModel):
    """Response model for individual model test."""

    success: bool
    message: str
    details: Optional[str] = None


# Provider priority for auto-assignment (higher priority first)
PROVIDER_PRIORITY = [
    "openai",
    "anthropic",
    "google",
    "mistral",
    "groq",
    "deepseek",
    "xai",
    "openrouter",
    "ollama",
    "azure",
    "openai_compatible",
    "dashscope",
    "minimax",
]

# Model preference patterns (preferred models within each provider)
MODEL_PREFERENCES = {
    "openai": ["gpt-4o", "gpt-4", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-5-sonnet", "claude-3-opus", "claude-3-sonnet"],
    "google": ["gemini-2.0", "gemini-1.5-pro", "gemini-pro"],
    "mistral": ["mistral-large", "mixtral"],
    "groq": ["llama-3.3", "llama-3.1", "mixtral"],
    "dashscope": ["qwen-max", "qwen-plus", "qwen-turbo"],
    "minimax": ["MiniMax-M2.5", "MiniMax-M2.5-highspeed"],
}


async def _check_provider_has_credential(provider: str) -> bool:
    """Check if a provider has any credentials configured in the database."""
    try:
        credentials = await Credential.get_by_provider(provider)
        return len(credentials) > 0
    except Exception as exc:
        # v0.8.29 — log the failure. Pre-v0.8.29 this was silent —
        # any DB error (connection drop, schema mismatch, auth
        # failure) returned False, causing the /providers status
        # endpoint to silently report "provider not configured" for
        # an actually-configured-via-DB provider. The downstream
        # `has_env` fallback in /providers covers the env-var path
        # so impact is limited, but a credential-only install
        # would briefly show all providers as unconfigured during
        # a DB blip with no signal in launcher.log. DEBUG because
        # the endpoint is read-heavy (polled by the Settings UI)
        # and a WARNING would spam launcher.log on every poll
        # during a sustained DB outage.
        logger.debug(
            "_check_provider_has_credential({!r}) failed; "
            "treating as 'no DB credential' — env-var fallback "
            "in /providers will still surface env-configured "
            "providers correctly. error={}",
            provider,
            exc,
        )
    return False


def _check_azure_support(mode: str) -> bool:
    """
    Check if Azure OpenAI provider is available for a specific mode.

    Args:
        mode: One of 'LLM', 'EMBEDDING', 'STT', 'TTS'

    Returns:
        bool: True if either generic or mode-specific env vars are set
    """
    # Check generic configuration (applies to all modes)
    generic = (
        os.environ.get("AZURE_OPENAI_API_KEY") is not None
        and os.environ.get("AZURE_OPENAI_ENDPOINT") is not None
        and os.environ.get("AZURE_OPENAI_API_VERSION") is not None
    )

    # Check mode-specific configuration (takes precedence)
    specific = (
        os.environ.get(f"AZURE_OPENAI_API_KEY_{mode}") is not None
        and os.environ.get(f"AZURE_OPENAI_ENDPOINT_{mode}") is not None
        and os.environ.get(f"AZURE_OPENAI_API_VERSION_{mode}") is not None
    )

    return generic or specific


def _check_openai_compatible_support(mode: str) -> bool:
    """
    Check if OpenAI-compatible provider is available for a specific mode.

    Args:
        mode: One of 'LLM', 'EMBEDDING', 'STT', 'TTS'

    Returns:
        bool: True if either generic or mode-specific env var is set
    """
    generic = os.environ.get("OPENAI_COMPATIBLE_BASE_URL") is not None
    specific = os.environ.get(f"OPENAI_COMPATIBLE_BASE_URL_{mode}") is not None
    generic_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY") is not None
    specific_key = os.environ.get(f"OPENAI_COMPATIBLE_API_KEY_{mode}") is not None
    return generic or specific or generic_key or specific_key


@router.get("/models", response_model=list[ModelResponse])
async def get_models(
    type: Optional[str] = Query(None, description="Filter by model type"),
):
    """Get all configured models with optional type filtering."""
    try:
        if type:
            models = await Model.get_models_by_type(type)
        else:
            models = await Model.get_all()

        return [
            ModelResponse(
                id=model.id,
                name=model.name,
                provider=model.provider,
                type=model.type,
                credential=model.credential,
                created=iso(model.created),
                updated=iso(model.updated),
            )
            for model in models
        ]
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error fetching models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching models")


@router.post("/models", response_model=ModelResponse)
async def create_model(model_data: ModelCreate):
    """Create a new model configuration."""
    try:
        # Validate model type
        valid_types = ["language", "embedding", "text_to_speech", "speech_to_text"]
        if model_data.type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model type. Must be one of: {valid_types}",
            )

        # Check for duplicate model name under the same provider and type (case-insensitive)
        from deeper_notebook.database.repository import repo_query

        existing = await repo_query(
            "SELECT * FROM model WHERE string::lowercase(provider) = $provider AND string::lowercase(name) = $name AND string::lowercase(type) = $type LIMIT 1",
            {
                "provider": model_data.provider.lower(),
                "name": model_data.name.lower(),
                "type": model_data.type.lower(),
            },
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model_data.name}' already exists for provider '{model_data.provider}' with type '{model_data.type}'",
            )

        new_model = Model(
            name=model_data.name,
            provider=model_data.provider,
            type=model_data.type,
            credential=model_data.credential,
        )
        await new_model.save()

        return ModelResponse(
            id=new_model.id or "",
            name=new_model.name,
            provider=new_model.provider,
            type=new_model.type,
            credential=new_model.credential,
            created=iso(new_model.created),
            updated=iso(new_model.updated),
        )
    except HTTPException:
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating model: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating model")


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a model configuration."""
    try:
        model = await Model.get(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        await model.delete()

        return {"message": "Model deleted successfully"}
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error deleting model {model_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting model")


@router.post("/models/{model_id}/test", response_model=ModelTestResponse)
async def test_model(model_id: str):
    """Test if a specific model is correctly configured and functional."""
    try:
        model = await Model.get(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Model not found")

    try:
        success, message = await test_individual_model(model)
        return ModelTestResponse(success=success, message=message)
    except Exception as e:
        logger.error(f"Error testing model {model_id}: {traceback.format_exc()}")
        return ModelTestResponse(
            success=False,
            message=str(e)[:200],
        )


@router.get("/models/defaults", response_model=DefaultModelsResponse)
async def get_default_models():
    """Get default model assignments."""
    try:
        defaults = await DefaultModels.get_instance()

        return DefaultModelsResponse(
            default_chat_model=defaults.default_chat_model,  # type: ignore[attr-defined]
            default_transformation_model=defaults.default_transformation_model,  # type: ignore[attr-defined]
            large_context_model=defaults.large_context_model,  # type: ignore[attr-defined]
            default_text_to_speech_model=defaults.default_text_to_speech_model,  # type: ignore[attr-defined]
            default_speech_to_text_model=defaults.default_speech_to_text_model,  # type: ignore[attr-defined]
            default_embedding_model=defaults.default_embedding_model,  # type: ignore[attr-defined]
            default_tools_model=defaults.default_tools_model,  # type: ignore[attr-defined]
            default_reasoning_model=getattr(defaults, "default_reasoning_model", None),
            # v0.8.1 / v0.8.37 — surface the smart-router config so
            # Settings can render the toggle + provider-pref dropdown.
            auto_route_cloud=getattr(defaults, "auto_route_cloud", None),
            auto_route_enabled=getattr(defaults, "auto_route_enabled", False),
            auto_route_provider_pref=getattr(
                defaults, "auto_route_provider_pref", "auto"
            ),
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error fetching default models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching default models")


@router.put("/models/defaults", response_model=DefaultModelsResponse)
async def update_default_models(defaults_data: DefaultModelsResponse):
    """Update default model assignments."""
    try:
        defaults = await DefaultModels.get_instance()

        # Update only provided fields
        if defaults_data.default_chat_model is not None:
            defaults.default_chat_model = defaults_data.default_chat_model  # type: ignore[attr-defined]
        if defaults_data.default_transformation_model is not None:
            defaults.default_transformation_model = (
                defaults_data.default_transformation_model
            )  # type: ignore[attr-defined]
        if defaults_data.large_context_model is not None:
            defaults.large_context_model = defaults_data.large_context_model  # type: ignore[attr-defined]
        if defaults_data.default_text_to_speech_model is not None:
            defaults.default_text_to_speech_model = (
                defaults_data.default_text_to_speech_model
            )  # type: ignore[attr-defined]
        if defaults_data.default_speech_to_text_model is not None:
            defaults.default_speech_to_text_model = (
                defaults_data.default_speech_to_text_model
            )  # type: ignore[attr-defined]
        if defaults_data.default_embedding_model is not None:
            defaults.default_embedding_model = defaults_data.default_embedding_model  # type: ignore[attr-defined]
        if defaults_data.default_tools_model is not None:
            defaults.default_tools_model = defaults_data.default_tools_model  # type: ignore[attr-defined]
        if defaults_data.default_reasoning_model is not None:
            defaults.default_reasoning_model = defaults_data.default_reasoning_model  # type: ignore[attr-defined]
        # v0.8.1 — auto_route_cloud is the dedicated cloud slot for the
        # smart router. Empty string sent from the UI dropdown means
        # "unset" — translate to None so it actually unlinks the field.
        if defaults_data.auto_route_cloud is not None:
            defaults.auto_route_cloud = defaults_data.auto_route_cloud or None  # type: ignore[attr-defined]
        # v0.8.37 — UI smart-routing toggle + provider-pref dropdown.
        # Booleans always overwrite (False is a meaningful value, unlike
        # "unset"), so we check for explicit None rather than truthiness.
        if defaults_data.auto_route_enabled is not None:
            defaults.auto_route_enabled = bool(defaults_data.auto_route_enabled)  # type: ignore[attr-defined]
        if defaults_data.auto_route_provider_pref is not None:
            # Defensive — clamp to the allowed set so a future schema
            # drift can't write garbage to the DB.
            pref = defaults_data.auto_route_provider_pref
            if pref not in ("auto", "local", "cloud"):
                pref = "auto"
            defaults.auto_route_provider_pref = pref  # type: ignore[attr-defined]

        await defaults.update()

        # No cache refresh needed - next access will fetch fresh data from DB

        return DefaultModelsResponse(
            default_chat_model=defaults.default_chat_model,  # type: ignore[attr-defined]
            default_transformation_model=defaults.default_transformation_model,  # type: ignore[attr-defined]
            large_context_model=defaults.large_context_model,  # type: ignore[attr-defined]
            default_text_to_speech_model=defaults.default_text_to_speech_model,  # type: ignore[attr-defined]
            default_speech_to_text_model=defaults.default_speech_to_text_model,  # type: ignore[attr-defined]
            default_embedding_model=defaults.default_embedding_model,  # type: ignore[attr-defined]
            default_tools_model=defaults.default_tools_model,  # type: ignore[attr-defined]
            default_reasoning_model=getattr(defaults, "default_reasoning_model", None),
            auto_route_cloud=getattr(defaults, "auto_route_cloud", None),
            auto_route_enabled=getattr(defaults, "auto_route_enabled", False),
            auto_route_provider_pref=getattr(
                defaults, "auto_route_provider_pref", "auto"
            ),
        )
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.179 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error updating default models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating default models")


@router.get("/models/providers", response_model=ProviderAvailabilityResponse)
async def get_provider_availability():
    """Get provider availability based on database config and environment variables."""
    try:
        # Check which providers have credentials in the database or env vars
        # For each provider, check DB credentials first, then env vars as fallback

        # Simple env var mapping for backward compatibility
        env_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "xai": "XAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "voyage": "VOYAGE_API_KEY",
            "elevenlabs": "ELEVENLABS_API_KEY",
            "ollama": "OLLAMA_API_BASE",
            "dashscope": "DASHSCOPE_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }

        provider_status = {}

        # Check simple providers: credential in DB or env var
        for provider, env_var in env_var_map.items():
            has_cred = await _check_provider_has_credential(provider)
            has_env = os.environ.get(env_var) is not None
            provider_status[provider] = has_cred or has_env

        # Google also supports GEMINI_API_KEY
        if not provider_status.get("google"):
            provider_status["google"] = os.environ.get("GEMINI_API_KEY") is not None

        # Vertex: DB credential or env vars
        provider_status["vertex"] = (
            await _check_provider_has_credential("vertex")
            or os.environ.get("VERTEX_PROJECT") is not None
        )

        # Azure: DB credential or env vars
        provider_status["azure"] = (
            await _check_provider_has_credential("azure")
            or _check_azure_support("LLM")
            or _check_azure_support("EMBEDDING")
            or _check_azure_support("STT")
            or _check_azure_support("TTS")
        )

        # OpenAI-compatible: DB credential or env vars
        provider_status["openai_compatible"] = (
            await _check_provider_has_credential("openai_compatible")
            or _check_openai_compatible_support("LLM")
            or _check_openai_compatible_support("EMBEDDING")
            or _check_openai_compatible_support("STT")
            or _check_openai_compatible_support("TTS")
        )

        available_providers = [k for k, v in provider_status.items() if v]
        unavailable_providers = [k for k, v in provider_status.items() if not v]

        # Get supported model types from Esperanto
        esperanto_available = AIFactory.get_available_providers()

        # Build supported types mapping only for available providers
        supported_types: dict[str, list[str]] = {}
        for provider in available_providers:
            supported_types[provider] = []

            # Map Esperanto model types to our environment variable modes
            mode_mapping = {
                "language": "LLM",
                "embedding": "EMBEDDING",
                "speech_to_text": "STT",
                "text_to_speech": "TTS",
            }

            esperanto_provider = (
                "openai-compatible" if provider == "openai_compatible" else provider
            )

            # Special handling for openai-compatible to check mode-specific availability.
            # Esperanto names the provider with a hyphen, but ONP's public API and
            # stored model rows use snake_case.
            if provider == "openai_compatible":
                has_db_cred = await _check_provider_has_credential("openai_compatible")
                for model_type, mode in mode_mapping.items():
                    if (
                        model_type in esperanto_available
                        and esperanto_provider in esperanto_available[model_type]
                    ):
                        if has_db_cred or _check_openai_compatible_support(mode):
                            supported_types[provider].append(model_type)
            # Special handling for azure to check mode-specific availability
            elif provider == "azure":
                has_db_cred = await _check_provider_has_credential("azure")
                for model_type, mode in mode_mapping.items():
                    if (
                        model_type in esperanto_available
                        and provider in esperanto_available[model_type]
                    ):
                        if has_db_cred or _check_azure_support(mode):
                            supported_types[provider].append(model_type)
            else:
                # Standard provider detection
                for model_type, providers in esperanto_available.items():
                    if esperanto_provider in providers:
                        supported_types[provider].append(model_type)

        return ProviderAvailabilityResponse(
            available=available_providers,
            unavailable=unavailable_providers,
            supported_types=supported_types,
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error checking provider availability: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error checking provider availability"
        )


# =============================================================================
# Model Discovery Endpoints
# =============================================================================


@router.get("/models/discover/{provider}", response_model=list[DiscoveredModelResponse])
async def discover_models(provider: str):
    """
    Discover available models from a provider without registering them.

    This endpoint queries the provider's API to list available models
    but does not save them to the database. Use the sync endpoint
    to both discover and register models.
    """
    try:
        # Provision DB-stored credentials into env vars before discovery
        await provision_provider_keys(provider)
        discovered = await discover_provider_models(provider)
        return [
            DiscoveredModelResponse(
                name=m.name,
                provider=m.provider,
                model_type=m.model_type,
                description=m.description,
            )
            for m in discovered
        ]
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error discovering models for {provider}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error discovering models. Check server logs for details.",
        )


@router.post("/models/sync/{provider}", response_model=ProviderSyncResponse)
async def sync_models(provider: str):
    """
    Sync models for a specific provider.

    Discovers available models from the provider's API and registers
    any new models in the database. Existing models are skipped.

    Returns counts of discovered, new, and existing models.
    """
    try:
        # Provision DB-stored credentials into env vars before discovery
        await provision_provider_keys(provider)
        discovered, new, existing = await sync_provider_models(
            provider, auto_register=True
        )
        return ProviderSyncResponse(
            provider=provider,
            discovered=discovered,
            new=new,
            existing=existing,
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error syncing models for {provider}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error syncing models. Check server logs for details.",
        )


@router.post("/models/sync", response_model=AllProvidersSyncResponse)
async def sync_all_models():
    """
    Sync models for all configured providers.

    Discovers and registers models from all providers that have
    valid API keys configured. This is useful for initial setup
    or periodic refresh of available models.
    """
    try:
        results = await sync_all_providers()

        response_results = {}
        total_discovered = 0
        total_new = 0

        for provider, (discovered, new, existing) in results.items():
            response_results[provider] = ProviderSyncResponse(
                provider=provider,
                discovered=discovered,
                new=new,
                existing=existing,
            )
            total_discovered += discovered
            total_new += new

        return AllProvidersSyncResponse(
            results=response_results,
            total_discovered=total_discovered,
            total_new=total_new,
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error syncing all models: {str(e)}")
        raise HTTPException(status_code=500, detail="Error syncing all models")


@router.get("/models/count/{provider}", response_model=ProviderModelCountResponse)
async def get_model_count(provider: str):
    """
    Get count of registered models for a provider, grouped by type.

    Returns counts for each model type (language, embedding,
    speech_to_text, text_to_speech) as well as total count.
    """
    try:
        counts = await get_provider_model_count(provider)
        total = sum(counts.values())
        return ProviderModelCountResponse(
            provider=provider,
            counts=counts,
            total=total,
        )
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error getting model count for {provider}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error getting model count")


@router.get("/models/by-provider/{provider}", response_model=list[ModelResponse])
async def get_models_by_provider(provider: str):
    """
    Get all registered models for a specific provider.

    Returns models from the database that belong to the specified provider.
    """
    try:
        from deeper_notebook.database.repository import repo_query

        models = await repo_query(
            "SELECT * FROM model WHERE provider = $provider ORDER BY type, name",
            {"provider": provider},
        )

        return [
            ModelResponse(
                id=model.get("id", ""),
                name=model.get("name", ""),
                provider=model.get("provider", ""),
                type=model.get("type", ""),
                credential=model.get("credential"),
                created=str(model.get("created", "")),
                updated=str(model.get("updated", "")),
            )
            for model in models
        ]
    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error fetching models for {provider}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching models")


def _get_preferred_model(
    models: list[dict], provider_priority: list[str], model_preferences: dict
) -> Optional[dict]:
    """
    Select the best model from a list based on provider priority and model preferences.

    Args:
        models: List of model dictionaries with 'provider', 'name', 'id' keys
        provider_priority: List of providers in preference order
        model_preferences: Dict mapping provider to list of preferred model name patterns

    Returns:
        The best model dict, or None if no models available
    """
    if not models:
        return None

    # Group models by provider
    by_provider: dict[str, list[dict]] = {}
    for model in models:
        provider = model.get("provider", "")
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(model)

    # Find first provider with models (in priority order)
    for provider in provider_priority:
        if provider in by_provider:
            provider_models = by_provider[provider]

            # Check for preferred models within this provider
            if provider in model_preferences:
                for preference in model_preferences[provider]:
                    for model in provider_models:
                        if preference.lower() in model.get("name", "").lower():
                            return model

            # Fall back to first model from this provider
            return provider_models[0]

    # Fall back to first model from any provider
    return models[0] if models else None


@router.post("/models/auto-assign", response_model=AutoAssignResult)
async def auto_assign_defaults():
    """
    Auto-assign default models based on available models.

    This endpoint intelligently assigns the first available model of each
    required type to the corresponding default slot. It uses provider
    priority (preferring premium providers like OpenAI, Anthropic) and
    model preferences within each provider.

    Returns:
        - assigned: Dict of slot names to assigned model IDs
        - skipped: List of slots that already have models assigned
        - missing: List of slots with no available models
    """
    try:
        from deeper_notebook.database.repository import repo_query

        # Get current defaults
        defaults = await DefaultModels.get_instance()

        # Get all models grouped by type
        all_models = await repo_query(
            "SELECT * FROM model ORDER BY provider, name",
            {},
        )

        # Group models by type
        models_by_type: dict[str, list[dict]] = {
            "language": [],
            "embedding": [],
            "text_to_speech": [],
            "speech_to_text": [],
        }

        for model in all_models:
            model_type = model.get("type", "")
            if model_type in models_by_type:
                models_by_type[model_type].append(model)

        # Define slot configuration: (slot_name, model_type, current_value)
        slot_configs = [
            ("default_chat_model", "language", defaults.default_chat_model),  # type: ignore[attr-defined]
            (
                "default_transformation_model",
                "language",
                defaults.default_transformation_model,
            ),  # type: ignore[attr-defined]
            ("default_tools_model", "language", defaults.default_tools_model),  # type: ignore[attr-defined]
            ("large_context_model", "language", defaults.large_context_model),  # type: ignore[attr-defined]
            # ONP v0.5 — 8th slot for slow-but-deep reasoning models.
            (
                "default_reasoning_model",
                "language",
                getattr(defaults, "default_reasoning_model", None),
            ),
            ("default_embedding_model", "embedding", defaults.default_embedding_model),  # type: ignore[attr-defined]
            (
                "default_text_to_speech_model",
                "text_to_speech",
                defaults.default_text_to_speech_model,
            ),  # type: ignore[attr-defined]
            (
                "default_speech_to_text_model",
                "speech_to_text",
                defaults.default_speech_to_text_model,
            ),  # type: ignore[attr-defined]
        ]

        assigned: dict[str, str] = {}
        skipped: list[str] = []
        missing: list[str] = []

        for slot_name, model_type, current_value in slot_configs:
            if current_value:
                # Slot already has a value
                skipped.append(slot_name)
                continue

            available_models = models_by_type.get(model_type, [])
            if not available_models:
                # No models of this type available
                missing.append(slot_name)
                continue

            # Select best model for this slot
            best_model = _get_preferred_model(
                available_models, PROVIDER_PRIORITY, MODEL_PREFERENCES
            )

            if best_model:
                model_id = best_model.get("id", "")
                assigned[slot_name] = model_id
                # Update the defaults object
                setattr(defaults, slot_name, model_id)

        # Save updated defaults if any assignments were made
        if assigned:
            await defaults.update()

        return AutoAssignResult(
            assigned=assigned,
            skipped=skipped,
            missing=missing,
        )

    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error auto-assigning defaults: {str(e)}")
        raise HTTPException(status_code=500, detail="Error auto-assigning defaults")


@router.post("/models/auto-assign-capability", response_model=AutoAssignResult)
async def auto_assign_capability(force: bool = False):
    """ONP v0.5.2 — capability-aware re-evaluation.

    Replaces upstream's PROVIDER_PRIORITY logic with our local-model-aware
    scorer (desktop/auto_register/capability + assigner). Designed for the
    "Re-evaluate model assignments" button in the Settings UI: lets users
    refresh picks after downloading a new model, raising/lowering the chat
    RAM ceiling, or changing the registry.

    force=true wipes existing assignments before scoring — without this the
    "never overwrite a manual override" guarantee makes the button a no-op.
    """
    try:
        from deeper_notebook.database.repository import repo_query

        try:
            from desktop.auto_register.assigner import SLOTS, assign_all
            from desktop.auto_register.capability import score_model
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "desktop.auto_register not importable from upstream API "
                    "process. Rebuild required (PyInstaller spec must bundle "
                    "desktop/auto_register/ into upstream/desktop/). "
                    f"Underlying: {type(exc).__name__}: {exc}"
                ),
            )

        # Get all models
        all_models = await repo_query(
            "SELECT * FROM model ORDER BY provider, name",
            {},
        )

        # Score each model + run the assigner
        pool = [score_model(m.get("name", "")) for m in all_models if m.get("name")]
        picks = assign_all(pool)

        # Map slot → upstream DefaultModels field
        slot_to_field = {
            "chat": "default_chat_model",
            "tools": "default_tools_model",
            "transformation": "default_transformation_model",
            "large_context": "large_context_model",
            "reasoning": "default_reasoning_model",
            "embedding": "default_embedding_model",
            "tts": "default_text_to_speech_model",
            "stt": "default_speech_to_text_model",
        }

        # Build a model-name → id lookup so we can write the upstream ID
        name_to_model = {m.get("name", ""): m for m in all_models}

        defaults = await DefaultModels.get_instance()
        assigned: dict[str, str] = {}
        skipped: list[str] = []
        missing: list[str] = []

        for slot in SLOTS:
            field = slot_to_field.get(slot)
            if not field:
                continue
            pick = picks.get(slot)
            if pick is None or pick.model is None:
                missing.append(field)
                continue
            current = getattr(defaults, field, None)
            if current and not force:
                skipped.append(field)
                continue
            m = name_to_model.get(pick.model.name)
            if not m:
                missing.append(field)
                continue
            model_id = m.get("id", "")
            assigned[field] = model_id
            setattr(defaults, field, model_id)

        if assigned:
            await defaults.update()

        return AutoAssignResult(
            assigned=assigned,
            skipped=skipped,
            missing=missing,
        )

    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error in capability-aware auto-assign: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error in capability-aware auto-assign",
        )
