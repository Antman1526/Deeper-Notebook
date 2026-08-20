"""v0.7.181 — Centralised ISO 8601 datetime serialisation for API responses.

Background — Safari `new Date()` brittleness:

  Python's `str(datetime)` produces a SPACE-separated string
  (e.g. "2026-05-22 10:14:41.123456+00:00"). Safari's `new Date()`
  refuses to parse this; every other major browser accepts it.
  ISO 8601 uses a T separator ("2026-05-22T10:14:41.123456+00:00"),
  which Safari accepts.

  Every API response that surfaces `created` / `updated` to the
  frontend MUST use the T form. Pydantic response models declare
  these fields as `str`, so the router code is responsible for
  the conversion. The natural-looking `str(model.created)` is
  exactly wrong for Safari.

v0.7.181 introduces `api/utils/iso.py::iso()` — a None-safe,
idempotent helper that returns `value.isoformat()` for datetimes
(T-separator, Safari-safe) and passes strings through unchanged.

This test suite verifies:
  1. The helper's behavioral contract.
  2. AST-level pins that the four highest-traffic routers
     (sources, notebooks, notes, chat) have migrated their
     `str(X.created)` / `str(X.updated)` calls to `iso(...)`.
  3. Forward-guard against regression on migrated files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# iso() behavioural contract
# ---------------------------------------------------------------------------


def test_iso_returns_none_for_none():
    """v0.7.181: iso(None) → None. Without this guard, callers would
    have to write `iso(x) if x else None` at every call site —
    defeats the centralization."""
    from api.utils.iso import iso

    assert iso(None) is None


def test_iso_uses_t_separator_for_datetime():
    """v0.7.181 CORE INVARIANT: iso(datetime) MUST produce the T-
    separator form. This is the whole reason the helper exists.
    `str(datetime)` produces a SPACE separator that Safari refuses;
    `.isoformat()` produces a T separator that Safari accepts."""
    from api.utils.iso import iso

    dt = datetime(2026, 5, 22, 10, 14, 41, 123456, tzinfo=timezone.utc)
    result = iso(dt)
    assert result is not None
    assert "T" in result, (
        f"v0.7.181 regression: iso(datetime) returned a string "
        f"without a T separator: {result!r}. Safari new Date() "
        f"will fail. The helper must call .isoformat(), not str()."
    )
    # Belt-and-suspenders: no space between date and time.
    date_part, time_part = result.split("T", 1)
    assert " " not in date_part
    assert ":" in time_part


def test_iso_passes_strings_through_unchanged():
    """v0.7.181: iso() is idempotent for strings. If a caller hands
    us a pre-formatted ISO string (e.g. from SurrealDB direct), we
    don't try to round-trip parse → reformat — the str is what the
    DB gave us, leave it alone."""
    from api.utils.iso import iso

    already_iso = "2026-05-22T10:14:41.123456+00:00"
    assert iso(already_iso) == already_iso


def test_iso_handles_naive_datetime_without_crashing():
    """v0.7.181: a naive datetime (no tzinfo) should still serialize
    — .isoformat() handles both cases. The v0.7.170 aware/naive
    normalization runs upstream of this helper at the repository
    layer, but defense-in-depth here means a stray naive datetime
    in a test fixture doesn't crash the response."""
    from api.utils.iso import iso

    dt_naive = datetime(2026, 5, 22, 10, 14, 41)
    result = iso(dt_naive)
    assert result is not None and "T" in result


# ---------------------------------------------------------------------------
# Per-router migration pins
# ---------------------------------------------------------------------------


_MIGRATED_ROUTERS = (
    "api/routers/sources.py",
    "api/routers/notebooks.py",
    "api/routers/notes.py",
    "api/routers/chat.py",
)


def test_migrated_routers_import_iso_helper():
    """v0.7.181: each migrated router must import the iso helper.
    Without the import, the iso() calls below it are NameErrors
    and the endpoint 500s on every request."""
    for rel in _MIGRATED_ROUTERS:
        src = _read_source(rel)
        assert "from api.utils.iso import iso" in src, (
            f"v0.7.181 regression: {rel} no longer imports the iso "
            f"helper. The iso() calls below will NameError."
        )


def test_migrated_routers_do_not_use_str_on_created_or_updated():
    """v0.7.181: the four migrated routers must NOT have any
    `str(X.created)` / `str(X.updated)` calls left. The forward-
    guard catches a future contributor who adds a new endpoint
    using the unsafe pattern, OR who reverts an iso() call back
    to str()."""
    offenders: list[tuple[str, int, str]] = []
    for rel in _MIGRATED_ROUTERS:
        src = _read_source(rel)
        for i, line in enumerate(src.splitlines(), start=1):
            stripped = line.strip()
            # Match `created=str(X.created)` and friends — anything
            # that turns a `.created` or `.updated` attribute into a
            # str() coercion in a response-construction context.
            if "str(" in stripped and (
                ".created)" in stripped or ".updated)" in stripped
            ):
                offenders.append((rel, i, stripped))

    assert not offenders, (
        "v0.7.181 regression: migrated routers contain unsafe "
        "`str(X.created)` / `str(X.updated)` calls. Safari "
        "new Date() will fail on these. Replace with iso(...).\n"
        + "\n".join(f"  {rel}:{ln} → {text}" for rel, ln, text in offenders)
    )


# ---------------------------------------------------------------------------
# Sanity: helper is callable from the canonical import path
# ---------------------------------------------------------------------------


def test_iso_helper_lives_at_api_utils_iso():
    """v0.7.181: pin the canonical import path. If a future refactor
    moves the helper, all migrated routers need updating in lock-
    step. This test makes the dependency explicit."""
    import importlib

    mod = importlib.import_module("api.utils.iso")
    assert hasattr(mod, "iso"), "api.utils.iso.iso is missing"


# ---------------------------------------------------------------------------
# Forward-guard: routers swept in v0.7.181 NotFoundError pass
# ---------------------------------------------------------------------------


def test_v181_notfounderror_sweep_credentials_and_transformations():
    """v0.7.181: credentials.py and transformations.py both got the
    typed re-raise treatment (continuation of the v0.7.179 sweep).
    Pin that the imports + clauses are present so the next pass
    doesn't have to re-discover the same gap."""
    for rel in (
        "api/routers/credentials.py",
        "api/routers/transformations.py",
    ):
        src = _read_source(rel)
        assert "from deeper_notebook.exceptions" in src
        assert "NotFoundError" in src, (
            f"v0.7.181 regression: NotFoundError import is gone "
            f"from {rel}. The typed re-raise clauses below will "
            f"NameError at import time and the entire router will "
            f"500 on every request."
        )
        assert "except (NotFoundError, InvalidInputError):" in src, (
            f"v0.7.181 regression: typed re-raise clause is gone "
            f"from {rel}. The broad `except Exception` will mask "
            f"404s as 500s again."
        )
