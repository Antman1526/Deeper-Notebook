"""GmailIntegration — single-record domain model for the OAuth + digest config.

ONP is single-user so we use a fixed record id 'gmail_integration:singleton'.
OAuth tokens are encrypted with the same Fernet key used for Credential records
(`DEEPER_NOTEBOOK_ENCRYPTION_KEY`) so they're never readable from a raw DB dump.

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

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_query,
    repo_upsert,
)
from deeper_notebook.environment import resolve_env
from deeper_notebook.utils.encryption import get_secret_from_env

SINGLETON_ID = "gmail_integration:singleton"

# v0.7.157 — Process-level TTL cache for GmailIntegration.get().
#
# Background: the SurrealDB `SELECT * FROM ONLY $rid` lookup for this
# singleton was observed taking 4-8 seconds on cold-start (see api.log
# slow-query warnings on every fresh launch). The frontend polls
# the canonical Gmail status endpoint on mount (60s adaptive interval) and the
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

# v0.8.35d — single-flight lock for cache-miss DB queries. Without
# this, concurrent first-callers (the v0.7.157 comment above names them:
# sidebar button + setup panel mounting together on the same page load)
# each see `_CACHE["value"] is None`, each await `repo_query`, and each
# write the same result. That's 2× ~4-8s of duplicate SurrealDB work
# per cold load — exactly the problem v0.7.157 set out to solve, but
# only solved for SECOND callers (cache hit). The lock closes the gap
# for the FIRST set of concurrent callers. Lazy-constructed because
# `asyncio.Lock()` doesn't need a running event loop in Python 3.10+
# but lazy init mirrors the v0.8.35b pattern in
# `deeper_notebook/ai/provision.py` for the same reasons.
_CACHE_LOCK: "asyncio.Lock | None" = None


def _get_cache_lock() -> asyncio.Lock:
    """v0.8.35d — lazily construct the cache-miss lock. See _CACHE_LOCK
    comment for motivation."""
    global _CACHE_LOCK
    if _CACHE_LOCK is None:
        _CACHE_LOCK = asyncio.Lock()
    return _CACHE_LOCK


def _invalidate_cache() -> None:
    """Drop the cached singleton. Called on save / clear / disconnect so
    the next .get() reads fresh data from SurrealDB.

    Note: does NOT reset the v0.8.35d _CACHE_LOCK — the lock has no
    state that needs invalidating (it's just a mutex, not stale data).
    Tests that want a clean lock state should set _CACHE_LOCK = None
    explicitly (see tests/test_v0_8_35d_gmail_single_flight.py)."""
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
    key = resolve_env(
        "DEEPER_NOTEBOOK_ENCRYPTION_KEY",
        getter=get_secret_from_env,
    )
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
    except Exception as exc:
        # v0.8.28 — log the failure. Pre-v0.8.28 this swallowed the
        # exception silently and the caller (_enc) raised
        # "DEEPER_NOTEBOOK_ENCRYPTION_KEY not set; cannot encrypt Gmail
        # tokens" — a misleading message because the key WAS set,
        # Fernet construction just failed (cryptography library bug,
        # binary-garbage env var, etc.). Without this log the operator
        # chases a non-existent missing-env-var problem when the real
        # issue is Fernet itself. WARNING level because this is a
        # security-boundary failure even if it's edge-case-y.
        logger.warning(
            "_fernet: Fernet construction failed despite "
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY being set. The downstream "
            "RuntimeError saying the key is unset is misleading — the "
            # v0.8.66 (audit E-2) — loguru uses {}-style formatting, not
            # printf %s; with "%s" the exception detail was silently dropped.
            "real cause is here: {}",
            exc,
        )
        return None


def _enc(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    f = _fernet()
    if f is None:
        # Should never happen in production — wizard sets encryption_key.
        # If it does happen we'd rather fail loudly than store plaintext.
        raise RuntimeError(
            "DEEPER_NOTEBOOK_ENCRYPTION_KEY not set; cannot encrypt Gmail tokens. "
            "Did the wizard run?"
        )
    return f.encrypt(v.encode()).decode()


def _dec(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    f = _fernet()
    if f is None:
        return None
    # v0.8.28 — split the two cases. InvalidToken is the canonical
    # "wrong key" / "tampered ciphertext" path and is benign at this
    # callsite (we're loading an existing row; the operator may have
    # rotated the encryption key, and the token shows as None until
    # they reconnect Gmail). Anything ELSE (binary garbage input,
    # cryptography library bug, OOM) is a real bug worth surfacing
    # so we don't silently drop GmailIntegration credentials.
    try:
        return f.decrypt(v.encode()).decode()
    except InvalidToken:
        # Quiet: expected when keys rotate or the row was never
        # encrypted (legacy data).
        return None
    except Exception as exc:
        logger.warning(
            "_dec: unexpected error decrypting Gmail token — "
            "returning None and the integration will appear "
            # v0.8.66 (audit E-2) — {}-style, not printf %s (loguru drops %s).
            "unconfigured. error={}",
            exc,
        )
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
        # v0.7.157 — TTL cache hit fast-path (no lock — every chat
        # poll would otherwise pay lock-acquire latency for nothing).
        now = time.monotonic()
        cached = _CACHE.get("value")
        if cached is not None and (now - _CACHE["ts"]) < _CACHE_TTL_S:
            return cached.model_copy()  # v0.8.66 (E-3) — copy, never alias the cache

        # v0.8.35d — single-flight slow path. Before the lock, two
        # concurrent first-callers (the v0.7.157 sidebar + setup panel
        # case) each ran the query independently. Now the first
        # acquirer queries + writes the cache; the others wait and
        # re-check the cache under the lock, returning the leader's
        # result without re-querying.
        async with _get_cache_lock():
            now = time.monotonic()
            cached = _CACHE.get("value")
            if cached is not None and (now - _CACHE["ts"]) < _CACHE_TTL_S:
                return (
                    cached.model_copy()
                )  # v0.8.66 (E-3) — copy, never alias the cache

            try:
                # v0.7.157 — bounded wait. If SurrealDB hasn't responded in
                # 3 seconds we give up and serve the default — better than
                # holding a request line open for 8s.
                result = await asyncio.wait_for(
                    repo_query(
                        "SELECT * FROM ONLY $rid",
                        # v0.8.66 (audit follow-up) — bind a RecordID, NOT the
                        # raw "gmail_integration:singleton" STRING. SurrealDB
                        # treats a bound string in `FROM ONLY $rid` as a string
                        # value (not a record id), so this returned [] every
                        # time and GmailIntegration.get() always saw an
                        # unconfigured account. Same ensure_record_id-missing
                        # class as the H3 MCP fix. Verified against live
                        # SurrealDB 2.1.0.
                        {"rid": ensure_record_id(SINGLETON_ID)},
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
            except Exception as exc:
                # v0.8.33 — log non-timeout failures. Pre-v0.8.33 this was
                # silent: any DB error other than timeout (connection drop,
                # schema mismatch, auth fail) returned a default
                # GmailIntegration so the UI showed the user "Connect Gmail"
                # as if they'd never configured it. The timeout path above
                # logs at WARNING; mirror that for symmetry so operators can
                # see WHY the integration appears unconfigured.
                # Same family as the v0.8.28 silent-swallow sweep.
                logger.warning(
                    "GmailIntegration.get(): SurrealDB query failed "
                    "({}) — returning default. UI will appear "
                    "unconfigured until the next successful poll.",
                    exc,
                )
                return cls()
            if not result:
                instance = cls()
                _CACHE["value"] = instance
                _CACHE["ts"] = now
                return instance.model_copy()
            # v0.8.35d — row parsing + decryption + cache write must
            # remain INSIDE the single-flight lock so the leader's
            # cache write happens before followers re-check the cache.
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
            # v0.8.66 (audit E-3) — return a COPY, never the shared cached
            # instance. Callers (disconnect/forget/settings/send) MUTATE the
            # returned object before save(); handing out the cached instance
            # aliased those mutations into every concurrent reader within the
            # TTL window. model_copy() is shallow (all fields are scalars), so
            # field reassignment on the copy can't touch the cached original.
            return instance.model_copy()

    async def save(self) -> None:
        """Encrypt-and-persist. SurrealDB upsert preserves fields we don't set."""
        from deeper_notebook.database.repository import ensure_record_id

        data = {
            "client_id_enc": _enc(self.client_id),
            "client_secret_enc": _enc(self.client_secret),
            "access_token_enc": _enc(self.access_token),
            "refresh_token_enc": _enc(self.refresh_token),
            "token_expires_at": self.token_expires_at.isoformat()
            if self.token_expires_at
            else None,
            "email_address": self.email_address,
            "enabled": self.enabled,
            "frequency": self.frequency,
            "include_notebooks": self.include_notebooks,
            "include_sources": self.include_sources,
            "include_notes": self.include_notes,
            "include_podcasts": self.include_podcasts,
            "include_memory": self.include_memory,
            "last_sent_at": self.last_sent_at.isoformat()
            if self.last_sent_at
            else None,
        }
        # v0.8.66 (audit C2) — the credential/token surface must ALWAYS be
        # written, even when None. `repo_upsert` issues `UPSERT … MERGE $data`,
        # and SurrealDB's MERGE only overwrites keys PRESENT in the payload while
        # silently preserving omitted ones. The previous blanket
        # `if v is not None` filter dropped every None, which made
        # `disconnect()` and `forget_credentials()` — both of which set these
        # fields to None and then call save() — DB-level NO-OPs: the old
        # encrypted refresh_token survived in the row, so the account stayed
        # effectively connected and a "forgotten" client_id/secret lingered on
        # disk. We force-write the six credential/token keys so clearing them
        # actually nulls them in the database. The remaining config fields
        # (enabled / frequency / include_* / last_sent_at) keep the None-skip,
        # since they are never legitimately None and we don't want a partial
        # save to wipe them.
        _ALWAYS_WRITE = {
            "client_id_enc",
            "client_secret_enc",
            "access_token_enc",
            "refresh_token_enc",
            "token_expires_at",
            "email_address",
        }
        data = {k: v for k, v in data.items() if v is not None or k in _ALWAYS_WRITE}
        await repo_upsert(
            # v0.8.66 — FULL record id, not bare "singleton" (repo_upsert runs
            # `UPSERT {id} MERGE`; a bare id is parsed as a TABLE → orphan rows).
            "gmail_integration",
            SINGLETON_ID,
            data,
            add_timestamp=True,
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
        return (
            datetime.now(timezone.utc) + timedelta(minutes=5) >= self.token_expires_at
        )


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
