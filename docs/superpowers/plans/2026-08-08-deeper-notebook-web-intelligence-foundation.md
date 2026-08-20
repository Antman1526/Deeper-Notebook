# Deeper Notebook Web Intelligence Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral, immutable evidence adapter to the existing Deeper Notebook web-search path without changing current provider behavior or citation output.

**Architecture:** Keep `deeper_notebook.tools.web_search.run_web_search()` as the only network/provider path. Add a pure `deeper_notebook.tools.web_evidence` module with frozen Pydantic records and a normalizer that validates, bounds, fingerprints, and classifies freshness. Existing callers remain compatible because the adapter is additive and does not change the legacy result list.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest/pytest-asyncio, hashlib, urllib.parse, timezone-aware `datetime`.

## Global Constraints

- Provider access remains opt-in through existing environment keys and existing failover/offline behavior.
- No vault writes, source mutation, watcher changes, credentials logging, or new network clients.
- Invalid or oversized provider data is rejected or skipped before it reaches UI, citations, or durable receipts.
- Preserve the existing `{title, url, snippet}` return shape of `run_web_search`.
- Every behavior change has focused regression coverage before implementation is considered complete.

### Task 1: Add failing evidence-contract tests

**Files:**
- Create: `tests/test_web_evidence.py`

**Interfaces:**
- Tests define `normalize_web_results(results, query, provider, retrieved_at, max_age)` and the `WebEvidence` fields consumed by later tasks.

- [x] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.tools.web_evidence import WebEvidence, normalize_web_results


def test_normalizes_bounded_immutable_evidence_with_fingerprints():
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
```

- [x] **Step 2: Run the focused file to verify it fails**

Run: `uv run pytest -q tests/test_web_evidence.py`

Expected: collection fails because `deeper_notebook.tools.web_evidence` does not exist yet.

### Task 2: Implement the pure normalized evidence adapter

**Files:**
- Create: `deeper_notebook/tools/web_evidence.py`
- Modify: `deeper_notebook/tools/__init__.py` only if the package currently exports tool modules

**Interfaces:**
- Produces `WebEvidence` frozen Pydantic model and `normalize_web_results(...) -> tuple[WebEvidence, ...]`.
- Accepts legacy result mappings without requiring provider-specific fields beyond `title`, `url`, and `snippet`.

- [x] **Step 1: Implement bounded normalization and hashing**

Implement these exact rules:

```python
WebEvidence = BaseModel(extra="forbid", frozen=True)
query: str = Field(min_length=1, max_length=1_000)
provider: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
title: str = Field(min_length=1, max_length=512)
url: str = Field(min_length=1, max_length=4_096)
snippet: str = Field(default="", max_length=4_000)
retrieved_at: datetime
freshness: Literal["fresh", "stale", "unknown"]
degraded: bool = False
source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
evidence_id: str = Field(pattern=r"^[a-f0-9]{64}$")
```

Strip query/title/snippet, remove URL fragments, require `http` or `https`, reject userinfo/blank host, and cap normalization at `max_results` (default 20). Apply a fixed examined-entry ceiling in addition to the accepted-result ceiling so malformed or infinite provider iterables cannot cause unbounded work. Reject oversized raw strings before trimming and reject values that cannot be UTF-8 encoded. Hash canonical JSON with sorted keys and compact separators using SHA-256. `source_fingerprint` excludes retrieval time; `evidence_id` includes query/provider plus the source fingerprint. Classify `fresh` when age is non-negative and within `max_age`, `stale` when older than `max_age`, and `unknown` for future or invalid timestamps. Catch per-entry validation errors and skip only that entry.

- [x] **Step 2: Run focused tests to verify they pass**

Run: `uv run pytest -q tests/test_web_evidence.py`

Expected: all focused evidence tests pass.

- [x] **Step 3: Run compatibility tests**

Run: `uv run pytest -q tests/test_v0_8_64_web_search.py tests/test_search_api.py tests/test_research_api.py`

Expected: all selected existing web/search/research tests pass with no changed legacy result shape.

### Task 2A: Repair adversarial bounded-input gaps found in independent review

**Files:**
- Modify: `deeper_notebook/tools/web_evidence.py`
- Modify: `tests/test_web_evidence.py`

- [x] **Step 1: Add failing regressions**

Cover an infinite/all-invalid iterable with a fixed examined-entry bound, an oversized pre-trim string, an unpaired Unicode surrogate, and a freshness assertion based on a runtime-relative timestamp.

- [x] **Step 2: Implement the smallest repairs**

Reject raw strings above a bounded multiple of their field limit before trimming; reject strings that fail UTF-8 encoding; stop after a fixed examined-entry ceiling even when fewer than `max_results` records were accepted.

- [x] **Step 3: Run focused and compatibility tests**

Run: `uv run pytest -q tests/test_web_evidence.py tests/test_v0_8_64_web_search.py tests/test_search_api.py tests/test_research_api.py`

Expected: all tests pass.

### Task 3: Review, document adoption boundary, and commit

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-deeper-notebook-web-intelligence-foundation-design.md` only if review finds an inconsistency
- Modify: `docs/superpowers/plans/2026-08-08-deeper-notebook-web-intelligence-foundation.md` only to check completed steps

- [x] **Step 1: Run formatting and diff checks**

Run: `uv run ruff check deeper_notebook/tools/web_evidence.py tests/test_web_evidence.py` and `git diff --check`.

Expected: both commands exit 0.

- [x] **Step 2: Inspect the diff for scope and secret safety**

Confirm no provider keys, network clients, vault paths, generated files, or unrelated frontend/backend modules changed.

- [x] **Step 3: Commit the bounded slice**

```bash
git add deeper_notebook/tools/web_evidence.py tests/test_web_evidence.py docs/superpowers/specs/2026-08-08-deeper-notebook-web-intelligence-foundation-design.md docs/superpowers/plans/2026-08-08-deeper-notebook-web-intelligence-foundation.md
git commit -m "feat(web): add normalized evidence foundation"
```
