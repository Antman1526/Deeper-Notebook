"""v0.7.170 — Aware/naive datetime normalization.

Two sites previously could leak naive datetimes into code that
expected aware (timezone-bearing) ones:

  1. `deeper_notebook/database/repository.py:repo_update` —
     `datetime.fromisoformat(data["created"])` returns a naive
     datetime when the input string has no timezone suffix. The
     adjacent line writes `data["updated"] = datetime.now(timezone.utc)`
     (aware), so the row would end up with a mixed pair. Any
     downstream comparison between the two would TypeError.

  2. `deeper_notebook/domain/gmail.py:_parse_dt` — returns whatever
     `fromisoformat` produces, plus passes through naive datetime
     INSTANCES unchanged. `needs_refresh` at line 242 then does
     `datetime.now(timezone.utc) >= self.token_expires_at` which
     raises `TypeError: can't compare offset-naive and offset-aware
     datetimes` when fed a naive value.

These tests pin the contract that BOTH parse sites coerce a naive
input to UTC-aware. The fix is the same one-liner pattern
(`if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)`) at both
sites; documenting the convention in tests prevents future code
from re-introducing the inconsistency.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deeper_notebook.domain.gmail import _parse_dt

# ---------------------------------------------------------------------------
# gmail._parse_dt
# ---------------------------------------------------------------------------


def test_parse_dt_naive_iso_string_returns_aware():
    """v0.7.170: naive ISO string → aware UTC datetime."""
    result = _parse_dt("2026-05-21T17:00:00")
    assert result is not None
    assert result.tzinfo is not None, (
        "v0.7.170: _parse_dt must coerce naive ISO strings to UTC-aware "
        f"datetimes. Got: {result!r} (tzinfo={result.tzinfo})"
    )
    assert result.tzinfo == timezone.utc


def test_parse_dt_z_suffix_string_returns_aware():
    """The `Z` suffix is the canonical UTC marker but fromisoformat
    doesn't accept it. The function already replaces Z with +00:00;
    this test pins that contract."""
    result = _parse_dt("2026-05-21T17:00:00Z")
    assert result is not None
    assert result.tzinfo is not None
    assert result.utcoffset().total_seconds() == 0


def test_parse_dt_aware_string_passes_through():
    """An ISO string that ALREADY has a tz offset must round-trip
    cleanly without double-applying UTC."""
    result = _parse_dt("2026-05-21T17:00:00-05:00")
    assert result is not None
    assert result.tzinfo is not None
    # Should preserve the -05:00 offset, not force UTC.
    assert result.utcoffset().total_seconds() == -5 * 3600


def test_parse_dt_naive_datetime_instance_returns_aware():
    """v0.7.170: when SurrealDB hands us a datetime object directly
    (not a string), it might still be naive. Coerce."""
    naive = datetime(2026, 5, 21, 17, 0, 0)  # NO tzinfo
    assert naive.tzinfo is None  # sanity
    result = _parse_dt(naive)
    assert result is not None
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc


def test_parse_dt_aware_datetime_instance_passes_through():
    """Aware input → unchanged."""
    aware = datetime(2026, 5, 21, 17, 0, 0, tzinfo=timezone.utc)
    result = _parse_dt(aware)
    assert result is not None
    assert result.tzinfo == timezone.utc


def test_parse_dt_none_and_empty_return_none():
    """Falsy inputs return None — preserves the existing contract."""
    assert _parse_dt(None) is None
    assert _parse_dt("") is None
    assert _parse_dt(0) is None


def test_parse_dt_unparseable_returns_none():
    """Strings that aren't datetime-shaped don't crash; they
    fall through to None."""
    assert _parse_dt("not-a-datetime") is None


# ---------------------------------------------------------------------------
# gmail.needs_refresh — the downstream comparison that USED to TypeError
# ---------------------------------------------------------------------------


def test_needs_refresh_does_not_typeerror_on_naive_db_input():
    """v0.7.170: the historic crash was

        datetime.now(timezone.utc) + timedelta(minutes=5) >= self.token_expires_at

    when `self.token_expires_at` came from a naive parse. Now
    `_parse_dt` always returns aware, so the comparison succeeds
    on every code path that builds a GmailIntegration from DB rows.
    """
    from deeper_notebook.domain.gmail import GmailIntegration

    # Simulate SurrealDB returning a naive ISO string (the historic
    # bug input). _parse_dt now coerces to aware.
    g = GmailIntegration(
        access_token="fake",
        refresh_token="fake-refresh",
        token_expires_at=_parse_dt("2030-01-01T00:00:00"),  # naive input
    )
    # No TypeError; comparison returns a bool.
    result = g.needs_refresh
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# repository.py:repo_update created-string normalization
# ---------------------------------------------------------------------------


def test_repo_update_normalizes_naive_created_string():
    """v0.7.170 AST/text guard: repository.py:repo_update must
    coerce a naive `created` string to UTC-aware before writing
    it back to SurrealDB. Otherwise the row ends up with a mixed
    naive `created` + aware `updated` pair (line 470 already uses
    `datetime.now(timezone.utc)` for updated).
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    src = (root / "deeper_notebook/database/repository.py").read_text()

    assert 'parsed = datetime.fromisoformat(data["created"])' in src
    # The normalization must immediately follow the parse.
    idx = src.index("parsed = datetime.fromisoformat")
    region = src[idx : idx + 200]
    assert "if parsed.tzinfo is None:" in region, (
        "v0.7.170 regression: repo_update no longer normalizes naive "
        f"`created` strings. Region:\n{region}"
    )
    assert "parsed.replace(tzinfo=timezone.utc)" in region
