"""v0.7.181 — Centralised ISO 8601 datetime serialisation for API responses.

Background — the Safari `new Date()` brittleness:

  Python's default `str(datetime)` produces a SPACE-separated
  string ("2026-05-22 10:14:41.123456+00:00"). Safari's
  `new Date(...)` constructor fails to parse this format
  (returns Invalid Date), while every other major browser
  (Chrome, Firefox) accepts it. The standards-compliant ISO
  8601 form uses a T separator ("2026-05-22T10:14:41.123456+00:00"),
  which Safari does accept.

  Every API response that surfaces `created` / `updated` / similar
  timestamps to the frontend MUST use the T form. Pydantic models
  declare these fields as `str` (e.g. `SourceResponse.created: str`),
  so the router code is responsible for the conversion — and the
  natural-looking `str(source.created)` is exactly wrong for Safari.

This helper is:
  - **None-safe**: returns None for None input (no AttributeError).
  - **Idempotent**: if the value is already a string, returns it
    unchanged (we don't try to round-trip parse → format).
  - **Typed**: explicit signature so callers and the AST forward-
    guard can reason about call sites.

Usage:
    from api.utils.iso import iso

    return SourceResponse(
        ...,
        created=iso(source.created),
        updated=iso(source.updated),
    )

Forward-guard test at `tests/test_v0_7_181_iso_helper.py` pins that
files migrated to this helper do not regress back to the unsafe
`str(...)` form.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Union


def iso(value: datetime | str | None) -> Optional[str]:
    """Return an ISO 8601 string (T separator) or None.

    Accepts datetime, str, or None. For datetimes, uses .isoformat()
    which Safari's `new Date()` parses correctly. For strings,
    returns the string unchanged (assumes the caller knows what they
    have — we don't try to validate or reformat). For None, returns
    None so the JSON serialiser can emit `null` instead of `"None"`.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    # Already a string (or string-coercible); leave alone.
    return str(value)
