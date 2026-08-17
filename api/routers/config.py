import asyncio
import os
import time
import tomllib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from loguru import logger

from api.routers.sources import _source_upload_max_bytes
from deeper_notebook.database.repository import repo_query
from deeper_notebook.utils.version_utils import (
    compare_versions,
    get_version_from_github_async,
)

router = APIRouter()

# In-memory cache for version check results
_version_cache: dict = {
    "latest_version": None,
    "has_update": False,
    "timestamp": 0,
    "check_failed": False,
}

# Cache TTL in seconds (24 hours)
VERSION_CACHE_TTL = 24 * 60 * 60


def get_version() -> str:
    """Read version from pyproject.toml"""
    try:
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
            return pyproject.get("project", {}).get("version", "unknown")
    except Exception as e:
        logger.warning(f"Could not read version from pyproject.toml: {e}")
        return "unknown"


async def get_latest_version_cached(current_version: str) -> tuple[Optional[str], bool]:
    """
    Check for the latest version from GitHub with caching.

    Returns:
        tuple: (latest_version, has_update)
        - latest_version: str or None if check failed
        - has_update: bool indicating if update is available
    """
    global _version_cache

    # Check if cache is still valid (within TTL)
    # v0.7.187 — was time.time(). Use monotonic for TTL comparison:
    # wall-clock can jump (NTP correction, sleep/resume on laptops,
    # DST transitions), pinning a stale cache for hours or
    # invalidating prematurely on every call. The desktop target is
    # explicitly a laptop that sleeps. monotonic is the canonical
    # choice for "elapsed time" comparisons. Backend audit #4.
    cache_age = time.monotonic() - _version_cache["timestamp"]
    if _version_cache["timestamp"] > 0 and cache_age < VERSION_CACHE_TTL:
        logger.debug(f"Using cached version check result (age: {cache_age:.0f}s)")
        return _version_cache["latest_version"], _version_cache["has_update"]

    # Cache expired or not yet set
    if _version_cache["timestamp"] > 0:
        logger.info(f"Version cache expired (age: {cache_age:.0f}s), refreshing...")

    # Perform version check with strict error handling
    try:
        logger.info("Checking for latest version from GitHub...")

        # Fetch latest version from GitHub with 10-second timeout.
        # v0.8.85 — compare against THIS fork, not upstream open-notebook.
        # Upstream's pyproject (1.14.x) always outran this fork's (1.8.x), so
        # every install showed a permanent "update available" banner whose
        # link pointed at the fork's releases — an update that did not exist.
        # Comparing installed pyproject vs fork-main pyproject means the
        # banner appears exactly when this repo's main has moved past the
        # running build.
        latest_version = await get_version_from_github_async(
            "https://github.com/Antman1526/Deeper-Notebook", "main"
        )

        logger.info(
            f"Latest version from GitHub: {latest_version}, Current version: {current_version}"
        )

        # Compare versions
        has_update = compare_versions(current_version, latest_version) < 0

        # Cache the result
        _version_cache["latest_version"] = latest_version
        _version_cache["has_update"] = has_update
        _version_cache["timestamp"] = time.monotonic()
        _version_cache["check_failed"] = False

        logger.info(f"Version check complete. Update available: {has_update}")

        return latest_version, has_update

    except Exception as e:
        logger.warning(f"Version check failed: {e}")

        # Cache the failure to avoid repeated attempts
        _version_cache["latest_version"] = None
        _version_cache["has_update"] = False
        _version_cache["timestamp"] = time.monotonic()
        _version_cache["check_failed"] = True

        return None, False


async def check_database_health() -> dict:
    """
    Check if database is reachable using a lightweight query.

    Returns:
        dict with 'status' ("online" | "offline") and optional 'error'
    """
    try:
        # 2-second timeout for database health check
        result = await asyncio.wait_for(repo_query("RETURN 1"), timeout=2.0)
        if result:
            return {"status": "online"}
        return {"status": "offline", "error": "Empty result"}
    except asyncio.TimeoutError:
        logger.warning("Database health check timed out after 2 seconds")
        return {"status": "offline", "error": "Health check timeout"}
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return {"status": "offline", "error": str(e)}


@router.get("/config")
async def get_config(request: Request):
    """
    Get frontend configuration.

    Returns version information and health status.
    Note: The frontend determines the API URL via its own runtime-config endpoint,
    so this endpoint no longer returns apiUrl.

    Also checks for version updates from GitHub (with caching and error handling).
    """
    # Get current version
    current_version = get_version()

    # Check for updates (with caching and error handling)
    # This MUST NOT break the endpoint - wrapped in try-except as extra safety
    latest_version = None
    has_update = False

    try:
        latest_version, has_update = await get_latest_version_cached(current_version)
    except Exception as e:
        # Extra safety: ensure version check never breaks the config endpoint
        logger.error(f"Unexpected error during version check: {e}")

    # Check database health
    db_health = await check_database_health()
    db_status = db_health["status"]

    if db_status == "offline":
        logger.warning(f"Database offline: {db_health.get('error', 'Unknown error')}")

    return {
        "version": current_version,
        "latestVersion": latest_version,
        "hasUpdate": has_update,
        "dbStatus": db_status,
        "sourceUploadMaxBytes": _source_upload_max_bytes(),
    }
