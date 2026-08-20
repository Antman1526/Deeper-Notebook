"""v0.8.70 — In-app update notifier service.

Checks the project's GitHub Releases for a newer version than the running
build and exposes the result to the frontend (which renders a dismissible
banner). This is intentionally a *notifier only* — it never downloads or
installs anything. The desktop app ships unsigned today, so silently
fetching/replacing binaries would be both unsafe and blocked by
Gatekeeper/SmartScreen; the banner just links to the release page.

Design notes
------------
- **Privacy:** the GitHub request only fires when checking is enabled (default
  on, user-togglable). When disabled, ``check()`` returns the cached/empty
  result without any network call. Deeper Notebook is privacy-first, so the one
  outbound call is gated and disclosed in the UI.
- **Resilience:** any failure (offline, rate-limited, malformed JSON, no
  releases yet) resolves to ``update_available = False``. The notifier must
  never block startup or surface an error to the user.
- **Caching:** results are cached in ``~/.deeper-notebook/update_state.json``
  for ``CHECK_TTL_SECONDS`` so reopening the app within the window doesn't
  re-ping GitHub.
- **State:** the same file persists the user's enabled toggle and the version
  they chose to skip.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlsplit

import httpx
from loguru import logger

from desktop.data_root import active_data_root

# Public GitHub repo that publishes the desktop releases.
GITHUB_OWNER = "Antman1526"
GITHUB_REPO = "Deeper-Notebook"
RELEASES_LATEST_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_FALLBACK_URL = (
    f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

# How long a check result is reused before we ping GitHub again.
CHECK_TTL_SECONDS = 6 * 60 * 60  # 6 hours
# Hard cap on the GitHub request so a hung connection can't stall the endpoint.
REQUEST_TIMEOUT_SECONDS = 8.0

VERIFICATION_VERIFIED = "verified"
VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_UNKNOWN = "unknown"
_VERIFICATION_STATES = frozenset(
    {VERIFICATION_VERIFIED, VERIFICATION_UNVERIFIED, VERIFICATION_UNKNOWN}
)
_STRICT_VERSION_RE = re.compile(
    r"^v?[0-9]+(?:\.[0-9]+){1,4}(?:[-+][A-Za-z0-9.-]{1,24})?$"
)
_DMG_ASSET_RE = re.compile(
    r"^Deeper-Notebook-mac-(?:arm64|x86_64)\.dmg$",
    re.IGNORECASE,
)
_CHECKSUM_ASSET_RE = re.compile(
    r"^(?:SHA256SUMS(?:\.txt)?|.*(?:sha256|checksum)[^/]*\.(?:txt|sha256|sha256sum))$",
    re.IGNORECASE,
)
_MAX_RELEASE_ASSETS = 64


def _state_path() -> Path:
    """Path to the persisted update-notifier state file.

    Shares the ``~/.deeper-notebook`` directory used by launcher prefs so
    all desktop-side state lives in one place.
    """
    return active_data_root() / "update_state.json"


def app_version() -> str:
    """Return the running application version.

    Single source for "what version am I" — the desktop window shows the same
    ``desktop.__version__`` string, so comparing against the latest GitHub tag
    is consistent with what the user sees. Falls back to installed package
    metadata when the desktop package isn't importable (e.g. bare API runs),
    and finally to ``0.0.0`` so a missing version degrades to "no update" math
    rather than crashing.
    """
    try:
        from desktop import __version__  # type: ignore

        if __version__:
            return str(__version__)
    except Exception:  # pragma: no cover - desktop not always importable
        pass
    try:
        from importlib.metadata import version

        return version("deeper-notebook")
    except Exception:  # pragma: no cover
        try:
            return version("open-notebook")
        except Exception:
            return "0.0.0"


def _parse_version(raw: Optional[str]) -> tuple[int, ...]:
    """Parse a version/tag string into a comparable numeric tuple.

    Handles a leading ``v`` (``v0.8.70`` → ``0.8.70``) and ignores any
    pre-release/build suffix (``0.8.70-rc1`` → ``(0, 8, 70)``). Unparseable
    input yields ``(0,)`` so it always compares as "oldest" rather than
    raising.
    """
    if not raw:
        return (0,)
    cleaned = raw.strip().lstrip("vV")
    # Take the leading dotted-number run; drop any -rc1 / +build tail.
    match = re.match(r"\d+(?:\.\d+)*", cleaned)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(0).split("."))


def _is_newer(latest: Optional[str], current: str) -> bool:
    """True when ``latest`` is a strictly greater version than ``current``."""
    if not latest:
        return False
    return _parse_version(latest) > _parse_version(current)


def _strict_release_version(raw: Any) -> str | None:
    """Return a bounded, fully parseable release tag or ``None``."""

    if not isinstance(raw, str) or len(raw) > 64:
        return None
    candidate = raw.strip()
    return candidate if _STRICT_VERSION_RE.fullmatch(candidate) else None


def _canonical_release_url(raw: Any, *, tag: str | None = None) -> str | None:
    """Accept only a public GitHub release page in the canonical repository."""

    if not isinstance(raw, str) or len(raw) > 512:
        return None
    try:
        parsed = urlsplit(raw)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
        parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
        prefix = [GITHUB_OWNER, GITHUB_REPO, "releases"]
        if parts[:3] != prefix:
            return None
        if len(parts) != 5 or parts[3] != "tag":
            return None
        if tag is None or parts[4] != tag:
            return None
        return "https://github.com/" + "/".join(parts)
    except (TypeError, ValueError):
        return None


def _classify_release(release: Any) -> tuple[str, str | None, str | None]:
    """Classify public release metadata without downloading any asset."""

    if not isinstance(release, Mapping):
        return VERIFICATION_UNKNOWN, None, None
    raw_tag = release.get("tag_name")
    tag = _strict_release_version(raw_tag)
    if tag is None:
        return VERIFICATION_UNVERIFIED, None, None
    release_url = _canonical_release_url(release.get("html_url"), tag=tag)
    if release_url is None:
        return VERIFICATION_UNVERIFIED, tag, None
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > _MAX_RELEASE_ASSETS:
        return VERIFICATION_UNVERIFIED, tag, None
    has_dmg = False
    has_checksum = False
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        name = asset.get("name")
        if not isinstance(name, str) or len(name) > 160:
            continue
        has_dmg = has_dmg or bool(_DMG_ASSET_RE.fullmatch(name))
        has_checksum = has_checksum or bool(_CHECKSUM_ASSET_RE.fullmatch(name))
    if not has_dmg or not has_checksum:
        return VERIFICATION_UNVERIFIED, tag, None
    return VERIFICATION_VERIFIED, tag, release_url


def _safe_published_at(raw: Any, *, verification: str) -> str | None:
    """Expose only a verified, timezone-aware ISO timestamp."""

    if verification != VERIFICATION_VERIFIED or not isinstance(raw, str):
        return None
    if len(raw) > 64 or raw.strip() != raw:
        return None
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return raw


def _read_state() -> dict[str, Any]:
    """Load persisted state, tolerating a missing/corrupt file."""
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning(f"update_state.json unreadable ({exc}); ignoring")
        return {}


def _write_state(state: dict[str, Any]) -> None:
    """Persist state atomically; never raise into the caller."""
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning(f"Could not persist update_state.json ({exc})")


def is_enabled() -> bool:
    """Whether automatic update checks are enabled (default: True)."""
    return bool(_read_state().get("enabled", True))


def set_enabled(enabled: bool) -> dict[str, Any]:
    """Persist the enabled toggle and return the resulting status."""
    state = _read_state()
    state["enabled"] = bool(enabled)
    _write_state(state)
    return _status_from_state(state)


def skip_version(version: str) -> dict[str, Any]:
    """Persist a version the user chose to skip; return the new status."""
    state = _read_state()
    state["skipped_version"] = str(version)
    _write_state(state)
    return _status_from_state(state)


def _status_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Build the API status payload from a (possibly cached) state dict."""
    current = app_version()
    cache = state.get("cache") if isinstance(state, Mapping) else None
    cache = cache if isinstance(cache, Mapping) else {}
    latest = _strict_release_version(cache.get("latest"))
    verification = cache.get("verification")
    if verification not in _VERIFICATION_STATES:
        verification = VERIFICATION_UNKNOWN
    release_url = None
    if verification == VERIFICATION_VERIFIED:
        release_url = _canonical_release_url(
            cache.get("release_url") or cache.get("html_url"), tag=latest
        )
        if release_url is None or latest is None:
            verification = VERIFICATION_UNKNOWN
    if verification != VERIFICATION_VERIFIED:
        release_url = None
    current_version = _strict_release_version(current)
    available = (
        verification == VERIFICATION_VERIFIED
        and current_version is not None
        and latest is not None
        and _parse_version(latest) > _parse_version(current_version)
    )
    skipped = _strict_release_version(state.get("skipped_version"))
    published_at = _safe_published_at(
        cache.get("published_at"), verification=verification
    )
    last_check = state.get("last_check")
    if not isinstance(last_check, str) or len(last_check) > 64:
        last_check = None
    return {
        "current": current,
        "latest": latest,
        # The banner hides itself for a skipped version; expose both the raw
        # availability and the skip so the client doesn't re-implement the math.
        "update_available": available,
        "skipped": available and skipped == latest,
        "skipped_version": skipped,
        "html_url": release_url,
        "release_url": release_url,
        "verification": verification,
        "published_at": published_at,
        "enabled": bool(state.get("enabled", True)),
        "last_check": last_check,
    }


def _cache_projection(release: Any) -> dict[str, Any]:
    """Persist only bounded classifier output, never raw asset metadata."""

    verification, tag, release_url = _classify_release(release)
    projected: dict[str, Any] = {
        "latest": tag,
        "verification": verification,
    }
    if release_url is not None:
        projected["release_url"] = release_url
        projected["html_url"] = release_url
    published_at = _safe_published_at(
        release.get("published_at") if isinstance(release, Mapping) else None,
        verification=verification,
    )
    if published_at is not None:
        projected["published_at"] = published_at
    return projected


def _cache_fresh(state: dict[str, Any]) -> bool:
    """True when the last check is within the TTL window."""
    last = state.get("last_check")
    if not last:
        return False
    try:
        ts = datetime.fromisoformat(last)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age < CHECK_TTL_SECONDS


async def _fetch_latest_release() -> Optional[dict[str, Any]]:
    """Query GitHub for the latest release. Returns None on any failure.

    A 404 here is normal and expected when the repo has no published releases
    yet — treated as "no update", not an error.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{GITHUB_REPO}-update-notifier",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(RELEASES_LATEST_URL, headers=headers)
        if resp.status_code != 200:
            logger.info(
                f"Update check: GitHub returned {resp.status_code} "
                "(no published release or rate limited)"
            )
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError) as exc:
        logger.info(f"Update check failed (non-fatal): {exc}")
        return None


async def check(force: bool = False) -> dict[str, Any]:
    """Return the current update status, refreshing from GitHub when due.

    Honors the enabled toggle (no network call when disabled) and the TTL
    cache (no network call when the last check is still fresh, unless
    ``force``). Always returns a status payload — never raises.
    """
    state = _read_state()

    # Disabled → never touch the network; report current version only.
    if not state.get("enabled", True):
        return _status_from_state(state)

    # Fresh cache → reuse it.
    if not force and _cache_fresh(state):
        return _status_from_state(state)

    release = await _fetch_latest_release()
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    if release is not None:
        state["cache"] = _cache_projection(release)
    # On failure we still stamp last_check so we back off for the TTL window
    # rather than hammering GitHub on every page load while offline.
    _write_state(state)
    return _status_from_state(state)
