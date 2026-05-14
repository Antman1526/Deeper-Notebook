"""GmailIntegration — single-record domain model for the OAuth + digest config.

ONP is single-user so we use a fixed record id 'gmail_integration:singleton'.
OAuth tokens are encrypted with the same Fernet key used for Credential records
(`OPEN_NOTEBOOK_ENCRYPTION_KEY`) so they're never readable from a raw DB dump.

The token-expiry math is approximate: Google access tokens are valid for ~1h.
We store `token_expires_at` and refresh proactively when ~5 min away from expiry.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel

from open_notebook.database.repository import repo_query, repo_upsert


SINGLETON_ID = "gmail_integration:singleton"


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
        if no record exists yet."""
        try:
            result = await repo_query(
                "SELECT * FROM ONLY $rid",
                {"rid": SINGLETON_ID},
            )
        except Exception:
            return cls()
        if not result:
            return cls()
        if isinstance(result, list):
            row = result[0] if result else {}
        else:
            row = result
        if not isinstance(row, dict):
            return cls()
        return cls(
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
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        # SurrealDB returns ISO strings
        s = str(v).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None
