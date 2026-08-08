"""Provider-neutral, bounded evidence records for web-search results.

This module deliberately sits *after* :mod:`web_search`: it performs no I/O and
does not change provider selection or the legacy ``{title, url, snippet}``
result shape.  Callers that need durable, provenance-aware records can opt in
by passing those results through :func:`normalize_web_results`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = ["WebEvidence", "normalize_web_results"]

_DEFAULT_MAX_RESULTS = 20
_DEFAULT_MAX_AGE = timedelta(hours=24)
_MAX_QUERY_LENGTH = 1_000
_MAX_PROVIDER_LENGTH = 32
_MAX_TITLE_LENGTH = 512
_MAX_URL_LENGTH = 4_096
_MAX_SNIPPET_LENGTH = 4_000
_PROVIDER_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class WebEvidence(BaseModel):
    """An immutable, normalized observation from a web-search provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=_MAX_QUERY_LENGTH)
    provider: str = Field(
        min_length=1,
        max_length=_MAX_PROVIDER_LENGTH,
        pattern=r"^[a-z0-9_-]+$",
    )
    title: str = Field(min_length=1, max_length=_MAX_TITLE_LENGTH)
    url: str = Field(min_length=1, max_length=_MAX_URL_LENGTH)
    snippet: str = Field(default="", max_length=_MAX_SNIPPET_LENGTH)
    retrieved_at: datetime
    freshness: Literal["fresh", "stale", "unknown"]
    degraded: bool = False
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_id: str = Field(pattern=r"^[a-f0-9]{64}$")


def _sha256_json(value: Mapping[str, str]) -> str:
    """Hash a small canonical JSON object with deterministic separators."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_text(value: object, *, max_length: int, truncate: bool) -> str | None:
    """Return a bounded string, or ``None`` when the value is not acceptable."""

    if not isinstance(value, str):
        return None
    try:
        text = value.strip()
    except Exception:
        return None
    if not text:
        return "" if truncate else None
    if len(text) > max_length:
        if not truncate:
            return None
        text = text[:max_length]
    return text


def _normalize_query(value: object) -> str | None:
    query = _normalized_text(value, max_length=_MAX_QUERY_LENGTH, truncate=False)
    return query if query else None


def _normalize_provider(value: object) -> str | None:
    provider = _normalized_text(
        value,
        max_length=_MAX_PROVIDER_LENGTH,
        truncate=False,
    )
    if not provider:
        return None
    provider = provider.lower()
    return provider if _PROVIDER_PATTERN.fullmatch(provider) else None


def _normalize_url(value: object) -> str | None:
    """Normalize a result URL and reject non-public-web URL shapes.

    This is intentionally a syntax boundary only.  Network/DNS policy belongs
    to the provider path; the evidence adapter never fetches or resolves a URL.
    """

    if not isinstance(value, str):
        return None
    try:
        raw_url = value.strip()
    except Exception:
        return None
    if not raw_url or len(raw_url) > _MAX_URL_LENGTH:
        return None

    try:
        parts = urlsplit(raw_url)
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"} or not parts.netloc:
            return None
        if any(ord(char) < 32 or char.isspace() for char in parts.netloc):
            return None
        # Accessing username/password/hostname/port can raise for malformed
        # bracketed hosts or ports; malformed provider entries are skipped.
        if parts.username is not None or parts.password is not None:
            return None
        hostname = parts.hostname
        port = parts.port
    except (TypeError, ValueError, AttributeError):
        return None

    if not hostname:
        return None
    try:
        hostname = hostname.lower()
    except Exception:
        return None

    # ``urlsplit`` accepts an empty explicit port (``example.com:``) as None;
    # reject it instead of emitting a subtly different URL identity.
    if port is None and parts.netloc.endswith(":"):
        return None

    if ":" in hostname and not hostname.startswith("["):
        normalized_host = f"[{hostname}]"
    else:
        normalized_host = hostname
    normalized_netloc = (
        f"{normalized_host}:{port}" if port is not None else normalized_host
    )

    try:
        normalized = urlunsplit(
            (scheme, normalized_netloc, parts.path, parts.query, "")
        )
    except (TypeError, ValueError):
        return None
    return normalized if 0 < len(normalized) <= _MAX_URL_LENGTH else None


def _utc_timestamp(value: datetime | None) -> tuple[datetime, bool]:
    """Return an aware UTC timestamp and whether the input was valid/aware."""

    if value is None:
        return datetime.now(timezone.utc), True
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc), False
    try:
        offset = value.utcoffset()
        if offset is None:
            # Preserve the supplied wall-clock value but make the record's
            # timestamp structurally timezone-aware.  Freshness remains
            # ``unknown`` because a naive timestamp has no reliable timezone.
            return value.replace(tzinfo=timezone.utc), False
        return value.astimezone(timezone.utc), True
    except (AttributeError, OverflowError, TypeError, ValueError):
        return datetime.now(timezone.utc), False


def _freshness(
    retrieved_at: datetime,
    timestamp_valid: bool,
    max_age: timedelta | None,
) -> Literal["fresh", "stale", "unknown"]:
    if not timestamp_valid or not isinstance(max_age, timedelta) or max_age < timedelta(0):
        return "unknown"
    try:
        age = datetime.now(timezone.utc) - retrieved_at
    except (OverflowError, TypeError, ValueError):
        return "unknown"
    if age < timedelta(0):
        return "unknown"
    return "fresh" if age <= max_age else "stale"


def _result_limit(value: object) -> int:
    if value is None:
        return _DEFAULT_MAX_RESULTS
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    if value <= 0:
        return 0
    return min(value, _DEFAULT_MAX_RESULTS)


def _entry_values(entry: object) -> tuple[object, object, object] | None:
    if not isinstance(entry, Mapping):
        return None
    try:
        return entry.get("title"), entry.get("url"), entry.get("snippet", "")
    except Exception:
        return None


def normalize_web_results(
    results: Iterable[Mapping[str, object]] | None,
    query: str,
    provider: str,
    retrieved_at: datetime | None = None,
    max_age: timedelta | None = _DEFAULT_MAX_AGE,
    max_results: int | None = _DEFAULT_MAX_RESULTS,
    degraded: bool = False,
) -> tuple[WebEvidence, ...]:
    """Normalize legacy search mappings into bounded immutable evidence.

    Invalid function-level metadata returns no records.  Invalid individual
    provider entries are skipped, allowing later valid entries to survive a
    provider shape change without exposing malformed data to callers.
    """

    normalized_query = _normalize_query(query)
    normalized_provider = _normalize_provider(provider)
    limit = _result_limit(max_results)
    if (
        normalized_query is None
        or normalized_provider is None
        or limit == 0
        or not isinstance(degraded, bool)
    ):
        return ()

    normalized_retrieved_at, timestamp_valid = _utc_timestamp(retrieved_at)
    try:
        iterator = iter(results) if results is not None else iter(())
    except Exception:
        return ()

    records: list[WebEvidence] = []
    while len(records) < limit:
        try:
            entry = next(iterator)
        except StopIteration:
            break
        except Exception:
            break

        values = _entry_values(entry)
        if values is None:
            continue
        raw_title, raw_url, raw_snippet = values
        title = _normalized_text(
            raw_title,
            max_length=_MAX_TITLE_LENGTH,
            truncate=False,
        )
        url = _normalize_url(raw_url)
        snippet = _normalized_text(
            raw_snippet,
            max_length=_MAX_SNIPPET_LENGTH,
            truncate=True,
        )
        if title is None or url is None or snippet is None:
            continue

        source_fingerprint = _sha256_json(
            {
                "provider": normalized_provider,
                "snippet": snippet,
                "title": title,
                "url": url,
            }
        )
        evidence_id = _sha256_json(
            {
                "provider": normalized_provider,
                "query": normalized_query,
                "source_fingerprint": source_fingerprint,
            }
        )
        try:
            records.append(
                WebEvidence(
                    query=normalized_query,
                    provider=normalized_provider,
                    title=title,
                    url=url,
                    snippet=snippet,
                    retrieved_at=normalized_retrieved_at,
                    freshness=_freshness(
                        normalized_retrieved_at,
                        timestamp_valid,
                        max_age,
                    ),
                    degraded=degraded,
                    source_fingerprint=source_fingerprint,
                    evidence_id=evidence_id,
                )
            )
        except (ValidationError, TypeError, ValueError):
            continue

    return tuple(records)
