"""
Credentials Router

Thin HTTP layer for managing individual AI provider credentials.
Business logic lives in api.credentials_service.

Endpoints:
- GET /credentials - List all credentials
- GET /credentials/by-provider/{provider} - List credentials for a provider
- POST /credentials - Create a new credential
- GET /credentials/{credential_id} - Get a specific credential
- PUT /credentials/{credential_id} - Update a credential
- DELETE /credentials/{credential_id} - Delete a credential
- POST /credentials/{credential_id}/test - Test connection
- POST /credentials/{credential_id}/discover - Discover models
- POST /credentials/{credential_id}/register-models - Register models

NEVER returns actual API key values - only metadata.
"""

import asyncio
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import SecretStr

from api.credentials_service import (
    credential_to_response,
    discover_with_config,
    get_provider_status,
    register_models,
    require_encryption_key,
    validate_url,
)
from api.credentials_service import (
    get_env_status as svc_get_env_status,
)
from api.credentials_service import (
    migrate_from_env as svc_migrate_from_env,
)
from api.credentials_service import (
    migrate_from_provider_config as svc_migrate_from_provider_config,
)
from api.credentials_service import (
    test_credential as svc_test_credential,
)
from api.models import (
    CreateCredentialRequest,
    CredentialDeleteResponse,
    CredentialResponse,
    DiscoveredModelResponse,
    DiscoverModelsResponse,
    RegisterModelsRequest,
    RegisterModelsResponse,
    UpdateCredentialRequest,
)
from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_delete,
    repo_query,
)
from deeper_notebook.domain.credential import Credential
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.utils.encryption import get_secret_from_env

router = APIRouter(prefix="/credentials", tags=["credentials"])


def _handle_value_error(e: ValueError, status_code: int = 400) -> HTTPException:
    """Convert a ValueError from the service layer to an HTTPException."""
    return HTTPException(status_code=status_code, detail=str(e))


# =============================================================================
# Status endpoints
# =============================================================================


@router.get("/status")
async def get_status():
    """
    Get configuration status: encryption key status, and per-provider
    configured/source information.
    """
    try:
        return await get_provider_status()
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error fetching status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch credential status")


@router.get("/env-status")
async def get_env_status():
    """Check what's configured via environment variables."""
    try:
        return await svc_get_env_status()
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error checking env status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check environment status"
        )


# =============================================================================
# CRUD endpoints
# =============================================================================


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    provider: Optional[str] = Query(None, description="Filter by provider"),
):
    """List all credentials, optionally filtered by provider."""
    try:
        if provider:
            credentials = await Credential.get_by_provider(provider)
        else:
            credentials = await Credential.get_all(order_by="provider, created")

        # v0.7.163 — N+1 fix: parallelize the per-credential linked-models
        # lookup. Previously the loop sequentially awaited
        # `cred.get_linked_models()` per row; each call hits SurrealDB
        # with `SELECT * FROM model WHERE credential = $cred_id`. A user
        # with 13 configured providers paid ~13 × ~30ms = ~400ms before
        # the Models page list could render. asyncio.gather collapses
        # this into a single wall-clock interval.
        #
        # Same pattern as v0.7.161 (chat-session checkpoint reads). The
        # bigger fix (denormalize a `model_count` field onto the
        # credential row at write time) needs a schema migration + a
        # post-save hook on Model; deferred.
        import asyncio as _asyncio

        linked_models_lists = await _asyncio.gather(
            *[cred.get_linked_models() for cred in credentials]
        )
        result = [
            credential_to_response(cred, len(models))
            for cred, models in zip(credentials, linked_models_lists)
        ]

        return result

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error listing credentials: {e}")
        raise HTTPException(status_code=500, detail="Failed to list credentials")


@router.get("/by-provider/{provider}", response_model=list[CredentialResponse])
async def list_credentials_by_provider(provider: str):
    """List all credentials for a specific provider."""
    try:
        credentials = await Credential.get_by_provider(provider.lower())
        result = []
        for cred in credentials:
            models = await cred.get_linked_models()
            result.append(credential_to_response(cred, len(models)))
        return result
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error listing credentials for {provider}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to list credentials for provider"
        )


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(request: CreateCredentialRequest):
    """Create a new credential."""
    try:
        require_encryption_key()
    except ValueError as e:
        raise _handle_value_error(e)

    # Validate all URL fields
    # v0.6.18 — validate_url calls socket.getaddrinfo() for non-IP hostnames,
    # which blocks the event loop for the DNS round-trip (typically 10-200ms,
    # but up to 30s on a misconfigured/slow resolver). With 6 URL fields per
    # credential, a worst-case create blocked the entire API for ~3 min.
    # Run each validation off the event loop.
    for url_field in [
        request.base_url,
        request.endpoint,
        request.endpoint_llm,
        request.endpoint_embedding,
        request.endpoint_stt,
        request.endpoint_tts,
    ]:
        if url_field:
            try:
                await asyncio.to_thread(validate_url, url_field, request.provider)
            except ValueError as e:
                raise _handle_value_error(e)

    try:
        cred = Credential(
            name=request.name,
            provider=request.provider.lower(),
            modalities=request.modalities,
            api_key=SecretStr(request.api_key) if request.api_key else None,
            base_url=request.base_url,
            endpoint=request.endpoint,
            api_version=request.api_version,
            endpoint_llm=request.endpoint_llm,
            endpoint_embedding=request.endpoint_embedding,
            endpoint_stt=request.endpoint_stt,
            endpoint_tts=request.endpoint_tts,
            project=request.project,
            location=request.location,
            credentials_path=request.credentials_path,
        )
        await cred.save()
        return credential_to_response(cred, 0)

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error creating credential: {e}")
        raise HTTPException(status_code=500, detail="Failed to create credential")


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: str):
    """Get a specific credential by ID. Never returns api_key."""
    try:
        cred = await Credential.get(credential_id)
        models = await cred.get_linked_models()
        return credential_to_response(cred, len(models))
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error fetching credential {credential_id}: {e}")
        raise HTTPException(status_code=404, detail="Credential not found")


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(credential_id: str, request: UpdateCredentialRequest):
    """Update an existing credential."""
    try:
        require_encryption_key()
    except ValueError as e:
        raise _handle_value_error(e)

    # Validate all URL fields being updated
    # v0.6.18 — see create_credential above for the rationale on to_thread.
    for url_field in [
        request.base_url,
        request.endpoint,
        request.endpoint_llm,
        request.endpoint_embedding,
        request.endpoint_stt,
        request.endpoint_tts,
    ]:
        if url_field:
            try:
                await asyncio.to_thread(validate_url, url_field, "update")
            except ValueError as e:
                raise _handle_value_error(e)

    try:
        cred = await Credential.get(credential_id)

        if request.name is not None:
            cred.name = request.name
        if request.modalities is not None:
            cred.modalities = request.modalities
        if request.api_key is not None:
            cred.api_key = SecretStr(request.api_key)
        if request.base_url is not None:
            cred.base_url = request.base_url or None
        if request.endpoint is not None:
            cred.endpoint = request.endpoint or None
        if request.api_version is not None:
            cred.api_version = request.api_version or None
        if request.endpoint_llm is not None:
            cred.endpoint_llm = request.endpoint_llm or None
        if request.endpoint_embedding is not None:
            cred.endpoint_embedding = request.endpoint_embedding or None
        if request.endpoint_stt is not None:
            cred.endpoint_stt = request.endpoint_stt or None
        if request.endpoint_tts is not None:
            cred.endpoint_tts = request.endpoint_tts or None
        if request.project is not None:
            cred.project = request.project or None
        if request.location is not None:
            cred.location = request.location or None
        if request.credentials_path is not None:
            cred.credentials_path = request.credentials_path or None

        await cred.save()
        models = await cred.get_linked_models()
        return credential_to_response(cred, len(models))

    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers in
        # api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error updating credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update credential")


@router.delete("/{credential_id}", response_model=CredentialDeleteResponse)
async def delete_credential(
    credential_id: str,
    migrate_to: Optional[str] = Query(
        None, description="Migrate linked models to this credential ID"
    ),
):
    """
    Delete a credential.

    If the credential has linked models:
    - Pass migrate_to=<credential_id> to reassign them to another credential
    - Otherwise, linked models are cascade-deleted automatically
    """
    try:
        try:
            cred = await Credential.get(credential_id)
        except ValueError as decrypt_err:
            # Credential exists but can't be decrypted (wrong encryption key).
            # Fall back to direct DB operations for deletion.
            logger.warning(
                f"Cannot decrypt credential {credential_id}, "
                f"falling back to direct delete: {decrypt_err}"
            )

            # Query linked models
            linked = await repo_query(
                "SELECT * FROM model WHERE credential = $cred_id",
                {"cred_id": ensure_record_id(credential_id)},
            )
            deleted_models = 0

            if linked and migrate_to:
                # Migrate models to another credential
                target_cred = await Credential.get(migrate_to)
                for model_row in linked:
                    model_id = str(model_row.get("id", ""))
                    if model_id:
                        await repo_query(
                            "UPDATE $model_id SET credential = $target_id",
                            {
                                "model_id": ensure_record_id(model_id),
                                "target_id": ensure_record_id(target_cred.id),
                            },
                        )
            elif linked:
                # Cascade-delete linked models
                for model_row in linked:
                    model_id = str(model_row.get("id", ""))
                    if model_id:
                        await repo_delete(model_id)
                        deleted_models += 1

            # Delete the credential itself
            await repo_delete(credential_id)

            return CredentialDeleteResponse(
                message="Credential deleted successfully",
                deleted_models=deleted_models,
            )

        linked_models = await cred.get_linked_models()

        deleted_models = 0

        if linked_models and migrate_to:
            # Migrate models to another credential
            target_cred = await Credential.get(migrate_to)
            for model in linked_models:
                model.credential = target_cred.id
                await model.save()

        elif linked_models:
            # Cascade-delete linked models (default behavior when no migrate_to)
            for model in linked_models:
                await model.delete()
                deleted_models += 1

        # Delete the credential
        await cred.delete()

        return CredentialDeleteResponse(
            message="Credential deleted successfully",
            deleted_models=deleted_models,
        )

    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers in
        # api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error deleting credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete credential")


# =============================================================================
# Test / Discover / Register endpoints
# =============================================================================


@router.post("/{credential_id}/test")
async def test_credential(credential_id: str):
    """Test connection using this credential's configuration."""
    return await svc_test_credential(credential_id)


@router.post("/{credential_id}/discover", response_model=DiscoverModelsResponse)
async def discover_models_for_credential(credential_id: str):
    """Discover available models using this credential's API key."""
    # v0.7.110 — wrap discover_with_config in wait_for. Discovery calls
    # the provider's list-models endpoint which can paginate slowly for
    # OpenRouter (300+ models) or hang if the base_url is misconfigured.
    # Default 30s aligns with the connection-test timeout (v0.7.100).
    import asyncio

    _discover_timeout = float(
        resolve_env("DEEPER_NOTEBOOK_DISCOVER_MODELS_TIMEOUT_SEC", "30").strip() or 30
    )
    try:
        cred = await Credential.get(credential_id)
        config = cred.to_esperanto_config()
        provider = cred.provider.lower()

        try:
            discovered = await asyncio.wait_for(
                discover_with_config(provider, config),
                timeout=_discover_timeout,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail=(
                    f"Model discovery timed out after {_discover_timeout:.0f}s. "
                    "The provider may be slow or the base_url is unreachable. "
                    "Raise DEEPER_NOTEBOOK_DISCOVER_MODELS_TIMEOUT_SEC if discovery "
                    "legitimately takes longer."
                ),
            )

        return DiscoverModelsResponse(
            credential_id=cred.id or "",
            provider=provider,
            discovered=[
                DiscoveredModelResponse(
                    name=d["name"],
                    provider=d["provider"],
                    description=d.get("description"),
                )
                for d in discovered
            ],
        )

    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error discovering models for credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to discover models")


@router.post("/{credential_id}/register-models", response_model=RegisterModelsResponse)
async def register_models_for_credential(
    credential_id: str, request: RegisterModelsRequest
):
    """Register discovered models and link them to this credential."""
    try:
        result = await register_models(credential_id, request.models)
        return RegisterModelsResponse(**result)
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Error registering models for credential {credential_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to register models")


# =============================================================================
# Migration endpoints
# =============================================================================


@router.post("/migrate-from-provider-config")
async def migrate_from_provider_config():
    """Migrate existing ProviderConfig data to individual credential records."""
    try:
        return await svc_migrate_from_provider_config()
    except ValueError as e:
        raise _handle_value_error(e)
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(
            f"ProviderConfig migration FAILED: {type(e).__name__}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Migration from provider config failed"
        )


@router.post("/detect-osaurus")
async def detect_osaurus():
    """v0.8.36 — On-demand probe + auto-register for a running Osaurus
    instance (https://github.com/osaurus-ai/osaurus).

    Mirrors the launcher's startup-time auto-register flow but exposed
    as an API so users who installed Osaurus AFTER launching ONP can
    one-click connect without restarting. Response shape:

      { "running": bool, "port": int, "models_registered": int,
        "credential_id": str | None, "detail": str }

    Idempotent: if the Osaurus credential already exists, the call
    refreshes its base_url (in case the port changed) and registers
    any newly-discovered models that aren't already in the catalog.
    """
    import httpx as _httpx

    from desktop.auto_register.osaurus import (
        _osaurus_port,
        _osaurus_running,
        register_osaurus_models,
    )

    port = _osaurus_port()
    running, discovered = _osaurus_running(port)
    if not running:
        return {
            "running": False,
            "port": port,
            "models_registered": 0,
            "credential_id": None,
            "detail": (
                f"No Osaurus instance reachable on http://127.0.0.1:{port}/v1/models. "
                "Install via `brew install --cask osaurus` and launch it, "
                "then retry."
            ),
        }

    # Reuse the launcher's auto_register code path. It expects a sync
    # httpx.Client + sets of existing credential names / model keys so
    # it can be idempotent. We fetch those here on the API side.
    base = "http://127.0.0.1:5055"  # self — same FastAPI process
    headers = {}
    pw = resolve_env(
        "DEEPER_NOTEBOOK_PASSWORD",
        getter=get_secret_from_env,
    )
    if pw:
        headers["Authorization"] = f"Bearer {pw}"

    def _do_register() -> tuple[bool, int, str | None]:
        # Sync httpx in a thread — auto_register helpers expect sync.
        with _httpx.Client(base_url=base, headers=headers, timeout=10.0) as cli:
            creds_resp = cli.get("/api/credentials")
            creds_resp.raise_for_status()
            existing_cred_names = {c.get("name", "").lower() for c in creds_resp.json()}
            models_resp = cli.get("/api/models")
            models_resp.raise_for_status()
            existing_model_keys = {
                (m.get("name", "").lower(), m.get("type", "").lower())
                for m in models_resp.json()
            }
            before = len(existing_model_keys)
            registered = register_osaurus_models(
                client=cli,
                existing_cred_names=existing_cred_names,
                existing_model_keys=existing_model_keys,
                port=port,
            )
            # Re-fetch to compute "how many new"; cheaper than tracking
            # inside the helper (which returns a bool).
            after_resp = cli.get("/api/credentials")
            after_resp.raise_for_status()
            cred_id = None
            for c in after_resp.json():
                if c.get("name", "").lower() == "osaurus (local mlx)":
                    cred_id = c.get("id")
                    break
            new_models_resp = cli.get("/api/models")
            new_models_resp.raise_for_status()
            after = len(new_models_resp.json())
            return registered, max(0, after - before), cred_id

    # Run the sync auto-register in a worker thread so we don't block
    # the FastAPI event loop on the network round-trips.
    try:
        registered, delta, cred_id = await asyncio.to_thread(_do_register)
    except _httpx.HTTPError as exc:
        logger.warning("Osaurus auto-register failed: {}", exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "Osaurus is reachable but the local model catalog could "
                "not be synced. Try again or check API logs."
            ),
        )

    return {
        "running": True,
        "port": port,
        "models_registered": delta,
        "credential_id": cred_id,
        "detail": (
            f"Connected to Osaurus on port {port}. "
            f"{len(discovered)} model(s) discovered, {delta} newly registered."
        ),
    }


@router.post("/migrate-from-env")
async def migrate_from_env():
    """Migrate API keys from environment variables to credential records."""
    try:
        return await svc_migrate_from_env()
    except ValueError as e:
        raise _handle_value_error(e)
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to global handlers.
        raise
    except Exception as e:
        logger.error(f"Env migration FAILED: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Migration from environment variables failed"
        )
