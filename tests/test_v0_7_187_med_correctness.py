"""v0.7.187 — MED-severity correctness fixes from round-9 audit.

Three independent surfaces tightened:

1.  `api/routers/config.py` version-check TTL switched from
    `time.time()` to `time.monotonic()`. Wall-clock comparisons
    are fragile on laptops: NTP corrections, sleep/resume, and DST
    transitions can either pin a stale cache forever or invalidate
    every call. monotonic is the canonical choice for "elapsed
    time" comparisons. Audit finding #4.

2.  `deeper_notebook/domain/base.py` `created` / `updated` timestamps
    now serialise as `datetime.now(timezone.utc).isoformat()` —
    aware UTC ISO 8601. Previously naive local-time with a
    non-ISO format string. Cross-machine sync produced off-by-N-
    hour ordering; the v0.7.181 iso() helper couldn't reconstruct
    a TZ that was never stored. Audit finding #6.

3.  `api/credentials_service.py` AsyncClient() now uses
    `_DISCOVERY_HTTP_TIMEOUT` (connect=5s, read=30s, write=10s,
    pool=5s). Previously no top-level timeout — the per-call
    `timeout=30.0` kwarg only bounded the request-response
    phase, leaving TLS handshake + pool-acquire stages unbounded.
    Same pattern chat_service.py uses. Audit finding #7.
"""
from __future__ import annotations

import re
from pathlib import Path


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
    assert "_version_cache[\"timestamp\"] = time.monotonic()" in src, (
        "v0.7.187 regression: config.py version cache reverted to "
        "time.time(). Laptop sleep + NTP corrections will silently "
        "break the TTL."
    )
    # The age comparison uses monotonic too.
    assert "time.monotonic() - _version_cache[\"timestamp\"]" in src, (
        "v0.7.187 regression: config.py cache-age comparison "
        "reverted to time.time()."
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
        line for line in region.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "time.time()" not in code_only, (
        "v0.7.187 regression: time.time() back in version-cache "
        "function. Use time.monotonic()."
    )


# ---------------------------------------------------------------------------
# base.py — aware UTC ISO 8601 timestamps
# ---------------------------------------------------------------------------


def test_object_model_save_uses_aware_utc_timestamps():
    """v0.7.187: ObjectModel.save() must use
    `datetime.now(timezone.utc).isoformat()` for created/updated.
    Naive local-time silently broke cross-machine ordering."""
    src = _read_source("deeper_notebook/domain/base.py")
    # The aware-UTC isoformat pattern is present at least twice
    # (one for updated, one for created on new records).
    aware_count = src.count("datetime.now(timezone.utc).isoformat()")
    assert aware_count >= 2, (
        f"v0.7.187 regression: ObjectModel.save() lost its "
        f"aware-UTC timestamp serialisation (found {aware_count} "
        f"occurrences, expected >=2). Cross-machine sync will "
        f"break again."
    )
    # The old naive strftime form must be gone from the save() block
    # (rationale comments are allowed to reference it).
    save_idx = src.find("async def save(")
    assert save_idx != -1
    next_async_def = src.find("\n    async def ", save_idx + 1)
    save_region = src[save_idx:next_async_def] if next_async_def != -1 else src[save_idx:save_idx + 3000]
    # Strip comment lines before checking.
    code_only = "\n".join(
        line for line in save_region.splitlines()
        if not line.lstrip().startswith("#")
    )
    bad = 'datetime.now().strftime("%Y-%m-%d %H:%M:%S")'
    assert bad not in code_only, (
        f"v0.7.187 regression: naive datetime.now() back in save(). "
        f"Use datetime.now(timezone.utc).isoformat()."
    )


def test_base_module_imports_timezone():
    """v0.7.187: base.py must import timezone from datetime. Without
    the import, the v0.7.187 aware-UTC isoformat calls NameError
    at import time."""
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
