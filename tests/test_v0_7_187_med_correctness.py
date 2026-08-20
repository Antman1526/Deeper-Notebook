"""v0.7.187 — MED-severity correctness fixes from round-9 audit.

Three independent surfaces tightened:

1.  `api/routers/config.py` version-check TTL switched from
    `time.time()` to `time.monotonic()`. Wall-clock comparisons
    are fragile on laptops: NTP corrections, sleep/resume, and DST
    transitions can either pin a stale cache forever or invalidate
    every call. monotonic is the canonical choice for "elapsed
    time" comparisons. Audit finding #4.

2.  `deeper_notebook/domain/base.py` `created` / `updated` timestamps
    persist as native, timezone-aware UTC datetime objects. Previously
    naive local-time strings broke cross-machine ordering, while the
    intermediate ISO-string fix violated SurrealDB datetime schemas.
    API responses still serialize through the v0.7.181 iso() helper.
    Audit finding #6.

3.  `api/credentials_service.py` AsyncClient() now uses
    `_DISCOVERY_HTTP_TIMEOUT` (connect=5s, read=30s, write=10s,
    pool=5s). Previously no top-level timeout — the per-call
    `timeout=30.0` kwarg only bounded the request-response
    phase, leaving TLS handshake + pool-acquire stages unbounded.
    Same pattern chat_service.py uses. Audit finding #7.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# config.py — TTL uses monotonic clock
# ---------------------------------------------------------------------------


def test_config_version_check_uses_monotonic_clock():
    """v0.7.187: the version-check TTL must use time.monotonic(),
    not time.time(). Wall-clock comparisons break on laptop sleep,
    NTP jumps, DST transitions."""
    src = _read_source("api/routers/config.py")
    # The timestamp field is set with monotonic.
    assert '_version_cache["timestamp"] = time.monotonic()' in src, (
        "v0.7.187 regression: config.py version cache reverted to "
        "time.time(). Laptop sleep + NTP corrections will silently "
        "break the TTL."
    )
    # The age comparison uses monotonic too.
    assert 'time.monotonic() - _version_cache["timestamp"]' in src, (
        "v0.7.187 regression: config.py cache-age comparison reverted to time.time()."
    )


def test_config_no_remaining_time_time_for_ttl():
    """v0.7.187 forward-guard: no `time.time()` code references in
    the _check_version_internal function (comments OK). Sanity
    sweep so a future contributor doesn't reintroduce the bug."""
    src = _read_source("api/routers/config.py")
    fn_start = src.find("async def get_latest_version_cached")
    assert fn_start != -1
    next_def = src.find("\nasync def ", fn_start + 1)
    if next_def == -1:
        next_def = src.find("\ndef ", fn_start + 1)
    region = src[fn_start:next_def] if next_def != -1 else src[fn_start:]
    # Strip comment lines (which legitimately mention `time.time()`
    # in rationale text) before checking.
    code_only = "\n".join(
        line for line in region.splitlines() if not line.lstrip().startswith("#")
    )
    assert "time.time()" not in code_only, (
        "v0.7.187 regression: time.time() back in version-cache "
        "function. Use time.monotonic()."
    )


# ---------------------------------------------------------------------------
# base.py — aware UTC datetime persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_credential_persists_aware_utc_datetime_objects(monkeypatch):
    """Credential creation must send native UTC datetimes to SurrealDB.

    Credential.created/updated are schema-defined datetime fields. Sending ISO
    strings makes SurrealDB reject a new credential before the API can return it.
    """
    from deeper_notebook.domain import base
    from deeper_notebook.domain.credential import Credential

    captured: dict = {}

    async def fake_repo_create(table: str, data: dict):
        captured["table"] = table
        captured["data"] = dict(data)
        return {"id": "credential:timestamp-regression", **data}

    monkeypatch.setattr(base, "repo_create", fake_repo_create)

    credential = Credential(
        name="Timestamp regression",
        provider="ollama",
        modalities=["language"],
    )
    await credential.save()

    assert captured["table"] == "credential"
    for field in ("created", "updated"):
        value = captured["data"][field]
        assert isinstance(value, datetime), (
            f"{field} must be a native datetime, got {type(value).__name__}"
        )
        assert value.tzinfo is not None
        assert value.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_existing_credential_persists_aware_utc_datetime_objects(monkeypatch):
    """Credential updates must not turn their native timestamps into strings."""
    from deeper_notebook.domain import base
    from deeper_notebook.domain.credential import Credential

    captured: dict = {}
    legacy_created = datetime(2026, 7, 27, 8, 0)

    async def fake_repo_update(table: str, record_id: str, data: dict):
        captured["table"] = table
        captured["record_id"] = record_id
        captured["data"] = dict(data)
        return {"id": record_id, **data}

    monkeypatch.setattr(base, "repo_update", fake_repo_update)

    credential = Credential(
        id="credential:timestamp-regression",
        name="Timestamp regression",
        provider="ollama",
        modalities=["language"],
        created=legacy_created,
    )
    await credential.save()

    assert captured["table"] == "credential"
    assert captured["record_id"] == "credential:timestamp-regression"
    for field in ("created", "updated"):
        value = captured["data"][field]
        assert isinstance(value, datetime)
        assert value.tzinfo is not None
        assert value.utcoffset() == timedelta(0)
    assert captured["data"]["created"].replace(tzinfo=None) == legacy_created


def test_credential_response_keeps_iso_timestamp_strings():
    """Native persistence datetimes still serialize as ISO strings at the API."""
    from api.credentials_service import credential_to_response
    from deeper_notebook.domain.credential import Credential

    stamp = datetime(2026, 7, 28, 12, 34, 56, 123456, tzinfo=timezone.utc)
    credential = Credential(
        id="credential:timestamp-response",
        name="Timestamp response",
        provider="ollama",
        modalities=["language"],
        created=stamp,
        updated=stamp,
    )

    response = credential_to_response(credential)

    assert response.created == stamp.isoformat()
    assert response.updated == stamp.isoformat()


def test_base_module_imports_timezone():
    """v0.7.187: base.py must import timezone from datetime. Without
    the import, the aware-UTC persistence calls raise NameError."""
    src = _read_source("deeper_notebook/domain/base.py")
    assert "from datetime import datetime, timezone" in src, (
        "v0.7.187 regression: timezone import gone from base.py. "
        "The aware-UTC datetime.now(timezone.utc) calls will fail."
    )


# ---------------------------------------------------------------------------
# credentials_service.py — httpx timeout config
# ---------------------------------------------------------------------------


def test_credentials_service_uses_shared_timeout():
    """v0.7.187: every `httpx.AsyncClient(...)` in
    credentials_service must pass `timeout=_DISCOVERY_HTTP_TIMEOUT`.
    Bare AsyncClient() leaves TLS handshake + pool-acquire
    unbounded; per-call timeout kwarg doesn't cover those."""
    src = _read_source("api/credentials_service.py")
    # The shared timeout constant exists.
    assert "_DISCOVERY_HTTP_TIMEOUT = httpx.Timeout(" in src
    # No bare `httpx.AsyncClient()` calls (without any args)
    # remain. Match the precise empty-args shape.
    bare = re.findall(r"httpx\.AsyncClient\(\s*\)", src)
    assert not bare, (
        f"v0.7.187 regression: credentials_service.py has "
        f"{len(bare)} bare `httpx.AsyncClient()` call(s) without "
        f"top-level timeout. Use "
        f"`httpx.AsyncClient(timeout=_DISCOVERY_HTTP_TIMEOUT)`."
    )
    # At least one call uses the shared timeout — proves the
    # migration ran.
    assert "httpx.AsyncClient(timeout=_DISCOVERY_HTTP_TIMEOUT)" in src
