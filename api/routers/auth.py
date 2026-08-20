"""
Authentication router for Deeper Notebook API.
Provides endpoints to check authentication status.
"""

from fastapi import APIRouter

from deeper_notebook.environment import resolve_env
from deeper_notebook.utils.encryption import get_secret_from_env

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status")
async def get_auth_status():
    """
    Check if authentication is enabled.
    Returns whether a password is required to access the API.
    Supports Docker secrets via DEEPER_NOTEBOOK_PASSWORD_FILE and the
    deprecated DEEPER_NOTEBOOK_PASSWORD_FILE alias.
    """
    auth_enabled = bool(
        resolve_env("DEEPER_NOTEBOOK_PASSWORD", getter=get_secret_from_env)
    )

    return {
        "auth_enabled": auth_enabled,
        "message": "Authentication is required"
        if auth_enabled
        else "Authentication is disabled",
    }
