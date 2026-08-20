from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.tools.web_evidence import WebEvidence, normalize_web_results


def test_normalizes_bounded_immutable_evidence_with_fingerprints():
    # Keep the freshness assertion relative to the runtime clock so the test
    # remains fresh after the historical implementation date has passed.
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    records = normalize_web_results(
        [
            {
                "title": "  Example  ",
                "url": "https://example.com/page#part",
                "snippet": "  A source  ",
            }
        ],
        query="  latest research ",
        provider="serper",
        retrieved_at=now,
    )
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, WebEvidence)
    assert record.query == "latest research"
    assert record.url == "https://example.com/page"
    assert record.freshness == "fresh"
    assert len(record.source_fingerprint) == 64
    assert len(record.evidence_id) == 64
    with pytest.raises((TypeError, ValidationError)):
        record.title = "changed"


def test_fingerprint_is_deterministic_and_changes_with_source_content():
    now = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
    first = normalize_web_results(
        [{"title": "T", "url": "https://example.com", "snippet": "S"}],
        query="q",
        provider="tavily",
        retrieved_at=now,
    )[0]
    same = normalize_web_results(
        [{"title": "T", "url": "https://example.com", "snippet": "S"}],
        query="q",
        provider="tavily",
        retrieved_at=now + timedelta(seconds=1),
    )[0]
    changed = normalize_web_results(
        [{"title": "T", "url": "https://example.com", "snippet": "different"}],
        query="q",
        provider="tavily",
        retrieved_at=now,
    )[0]
    assert first.source_fingerprint == same.source_fingerprint
    assert first.evidence_id == same.evidence_id
    assert first.source_fingerprint != changed.source_fingerprint


def test_bounds_results_text_and_urls_and_skips_invalid_entries():
    now = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
    records = normalize_web_results(
        [
            {"title": "x" * 5000, "url": "javascript:alert(1)", "snippet": "x"},
            {"title": "good", "url": "https://example.com", "snippet": "y" * 10000},
            "not a mapping",
        ],
        query="q",
        provider="searxng",
        retrieved_at=now,
        max_results=1,
    )
    assert len(records) == 1
    assert records[0].title == "good"
    assert len(records[0].snippet) <= 4_000


def test_freshness_and_degraded_state_are_explicit():
    now = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
    records = normalize_web_results(
        [{"title": "T", "url": "https://example.com", "snippet": "S"}],
        query="q",
        provider="searxng",
        retrieved_at=now - timedelta(hours=2),
        max_age=timedelta(hours=1),
        degraded=True,
    )
    assert records[0].freshness == "stale"
    assert records[0].degraded is True


def test_invalid_entries_are_bounded_by_examined_entry_budget():
    examined = 0

    def invalid_entries():
        nonlocal examined
        for _ in range(1_000):
            examined += 1
            yield {"title": "", "url": "https://example.com", "snippet": ""}

    records = normalize_web_results(
        invalid_entries(),
        query="q",
        provider="searxng",
        max_results=1,
    )

    assert records == ()
    assert examined == 100


def test_rejects_oversized_raw_text_before_trimming():
    oversized_title = (" " * 2_049) + "good"

    records = normalize_web_results(
        [{"title": oversized_title, "url": "https://example.com", "snippet": "ok"}],
        query="q",
        provider="searxng",
    )

    assert records == ()


def test_skips_text_with_unpaired_unicode_surrogates_before_hashing():
    records = normalize_web_results(
        [{"title": "malformed\ud800", "url": "https://example.com", "snippet": "ok"}],
        query="q",
        provider="searxng",
    )

    assert records == ()


def test_skips_url_with_unpaired_unicode_surrogates_before_hashing():
    records = normalize_web_results(
        [{"title": "ok", "url": "https://example.com/\ud800", "snippet": "ok"}],
        query="q",
        provider="searxng",
    )

    assert records == ()


def test_rejects_query_with_unpaired_unicode_surrogates_before_hashing():
    records = normalize_web_results(
        [{"title": "ok", "url": "https://example.com", "snippet": "ok"}],
        query="malformed\ud800",
        provider="searxng",
    )

    assert records == ()
