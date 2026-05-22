"""GmailIntegration — single-record domain model for the OAuth + digest config.

ONP is single-user so we use a fixed record id 'gmail_integration:singleton'.
OAuth tokens are encrypted with the same Fernet key used for Credential records
(`OPEN_NOTEBOOK_ENCRYPTION_KEY`) so they're never readable from a raw DB dump.

The token-expiry math is approximate: Google access tokens are valid for ~1h.
We store `token_expires_at` and refresh proactively when ~5 min away from expiry.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from pydantic import BaseModel

from open_notebook.database.repository import repo_query, repo_upsert

SINGLETON_ID = "gmail_integration:singleton"

# v0.7.157 — Process-level TTL cache for GmailIntegration.get().
#
# Background: the SurrealDB `SELECT * FROM ONLY $rid` lookup for this
# singleton was observed taking 4-8 seconds on cold-start (see api.log
# slow-query warnings on every fresh launch). The frontend polls
# `/api/onp/gmail/status` on mount (60s adaptive interval) and the
# /settings/api-keys page mounts BOTH the GmailIntegration panel AND
# the GmailSidebarButton, so two concurrent slow queries fire on
# every cold load → 8+ seconds of perceived freeze.
#
# This cache:
#   - 30-second TTL: shorter than the frontend's 60s polling cadence
#     so every other poll is a free in-memory hit. The data only
#     changes when the user explicitly OAuth-connects/disconnects,
#     and those write paths invalidate the cache below.
#   - Module-level (single-user app): no need for per-tenant scoping.
#   - Stores the FULL GmailIntegration instance (already decrypted)
#     so cache hits skip both the query AND the Fernet decryption.
#
# Cache invalidation: `save()`, `clear_credentials()`, and the
# disconnect path explicitly invalidate; the implicit TTL is a safety
# net for any code path that mutates via raw `repo_upsert`.
_CACHE: dict = {"value": None, "ts": 0.0}
_CACHE_TTL_S = 30.0


def _invalidate_cache() -> None:
    """Drop the cached singleton. Called on save / clear / disconnect so
    the next .get() reads fresh data from SurrealDB."""
    _CACHE["value"] = None
    _CACHE["ts"] = 0.0


# v0.7.157 — How long to wait for the SurrealDB lookup before giving up
# and returning a default-constructed instance. The previous unbounded
# wait blocked the API for 4-8s on every cold poll. 3s is a generous
# upper bound for a single-record fetch by ID; if SurrealDB takes
# longer than that, something else is wrong and the user is better
# served by a default-constructed instance + a warning log.
_QUERY_TIMEOUT_S = 3.0


def _fernet() -> Optional[Fernet]:
    key = os.environ.get("OPEN_NOTEBOOK_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        # Match the Credential encryption pattern: derive a Fernet key from
        # the urlsafe base64-encoded user-provided string.
        import base64
        import hashlib
        digest = hashlib.sha256(key.encode()).digest()
        fkey = base64.urlsafe_b64encode(digest)
        return Fernet(fkey)
    except Exception:
        return None


def _enc(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    f = _fernet()
    if f is None:
        # Should never happen in production — wizard sets encryption_key.
        # If it does happen we'd rather fail loudly than store plaintext.
        raise RuntimeError(
            "OPEN_NOTEBOOK_ENCRYPTION_KEY not set; cannot encrypt Gmail tokens. "
            "Did the wizard run?"
        )
    return f.encrypt(v.encode()).decode()


def _dec(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(v.encode()).decode()
    except (InvalidToken, Exception):
        return None


class GmailIntegration(BaseModel):
    """In-memory shape of the gmail_integration singleton record."""

    # OAuth client configuration (user-provided via Settings)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    # OAuth tokens (set by callback)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    # Account info
    email_address: Optional[str] = None
    # Digest preferences
    enabled: bool = False
    frequency: str = "daily"  # daily | weekly | manual
    include_notebooks: bool = True
    include_sources: bool = True
    include_notes: bool = True
    include_podcasts: bool = True
    include_memory: bool = True
    last_sent_at: Optional[datetime] = None

    @classmethod
    async def get(cls) -> "GmailIntegration":
        """Load the singleton from DB. Returns a default-constructed instance
        if no record exists yet.

        v0.7.157 — Wrapped in a 30-second TTL cache + 3-second query
        timeout. The slow `SELECT * FROM ONLY $rid` lookup (4-8s
        cold-start observed in api.log) used to block every page load
        for two concurrent calls (sidebar button + main panel both
        polling on mount). Now the first call pays the cost ONCE, every
        poll within 30s is a free in-memory hit, and a misbehaving
        SurrealDB can no longer hold the request line beyond 3s.
        """
        # v0.7.157 — TTL cache hit fast-path
        now = time.monotonic()
        cached = _CACHE.get("value")
        if cached is not None and (now - _CACHE["ts"]) < _CACHE_TTL_S:
            return cached

        try:
            # v0.7.157 — bounded wait. If SurrealDB hasn't responded in
            # 3 seconds we give up and serve the default — better than
            # holding a request line open for 8s.
            result = await asyncio.wait_for(
                repo_query(
                    "SELECT * FROM ONLY $rid",
                    {"rid": SINGLETON_ID},
                ),
                timeout=_QUERY_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "GmailIntegration.get(): SurrealDB query exceeded "
                f"{_QUERY_TIMEOUT_S}s — returning default. Subsequent "
                "polls will retry on the next cache miss."
            )
            return cls()
        except Exception:
            return cls()
        if not result:
            instance = cls()
            _CACHE["value"] = instance
            _CACHE["ts"] = now
            return instance
        if isinstance(result, list):
            row = result[0] if result else {}
        else:
            row = result
        if not isinstance(row, dict):
            return cls()
        instance = cls(
            client_id=_dec(row.get("client_id_enc")),
            client_secret=_dec(row.get("client_secret_enc")),
            access_token=_dec(row.get("access_token_enc")),
            refresh_token=_dec(row.get("refresh_token_enc")),
            token_expires_at=_parse_dt(row.get("token_expires_at")),
            email_address=row.get("email_address"),
            enabled=bool(row.get("enabled", False)),
            frequency=row.get("frequency", "daily"),
            include_notebooks=bool(row.get("include_notebooks", True)),
            include_sources=bool(row.get("include_sources", True)),
            include_notes=bool(row.get("include_notes", True)),
            include_podcasts=bool(row.get("include_podcasts", True)),
            include_memory=bool(row.get("include_memory", True)),
            last_sent_at=_parse_dt(row.get("last_sent_at")),
        )
        # v0.7.157 — cache the fully-decrypted instance so subsequent
        # polls within the TTL window skip both the DB hit AND the
        # per-field Fernet decryption.
        _CACHE["value"] = instance
        _CACHE["ts"] = now
        return instance

    async def save(self) -> None:
        """Encrypt-and-persist. SurrealDB upsert preserves fields we don't set."""
        from open_notebook.database.repository import ensure_record_id
        data = {
            "client_id_enc": _enc(self.client_id),
            "client_secret_enc": _enc(self.client_secret),
            "access_token_enc": _enc(self.access_token),
            "refresh_token_enc": _enc(self.refresh_token),
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "email_address": self.email_address,
            "enabled": self.enabled,
            "frequency": self.frequency,
            "include_notebooks": self.include_notebooks,
            "include_sources": self.include_sources,
            "include_notes": self.include_notes,
            "include_podcasts": self.include_podcasts,
            "include_memory": self.include_memory,
            "last_sent_at": self.last_sent_at.isoformat() if self.last_sent_at else None,
        }
        # Drop None so upsert doesn't clobber pre-existing values
        data = {k: v for k, v in data.items() if v is not None}
        await repo_upsert(
            "gmail_integration", "singleton", data, add_timestamp=True,
        )
        # v0.7.157 — invalidate the read cache so the next .get() sees
        # the freshly-persisted state instead of a stale snapshot.
        _invalidate_cache()

    @property
    def is_connected(self) -> bool:
        return bool(self.refresh_token and self.email_address)

    @property
    def needs_refresh(self) -> bool:
        """True if access_token is missing or near-expired (5 min buffer)."""
        if not self.access_token or not self.token_expires_at:
            return True
        return datetime.now(timezone.utc) + timedelta(minutes=5) >= self.token_expires_at


def _parse_dt(v) -> Optional[datetime]:
    """Parse a datetime-shaped value into an UTC-aware datetime.

    v0.7.170 — Always returns a TIMEZONE-AWARE datetime (or None).
    The previous form could leak a naive datetime through two paths:
      1. `isinstance(v, datetime)` branch returned `v` as-is, even if
         SurrealDB had handed us a naive datetime
      2. `datetime.fromisoformat("2026-05-21T17:00:00")` (no tz
         suffix) returns a naive datetime
    Downstream comparison code (`needs_refresh` at line 242 does
    `datetime.now(timezone.utc) >= self.token_expires_at`) raises
    `TypeError: can't compare offset-naive and offset-aware
    datetimes` when fed a naive value. Now any naive input is
    treated as UTC — matches the rest of the codebase convention.
    """
    if not v:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    try:
        # SurrealDB returns ISO strings; the `Z` suffix is the
        # canonical UTC marker but fromisoformat needs +00:00.
        s = str(v).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None
