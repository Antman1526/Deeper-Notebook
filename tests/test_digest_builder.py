"""ONP v0.6.2 — Tests for the digest HTML builder.

Smoke-tests `build_digest_html` against a fake GmailIntegration, with
`repo_query` monkey-patched to return fixed rows. We're checking:
  * sections render correctly when each toggle is on/off
  * total count adds up across sections
  * the "no activity" footer kicks in when total == 0
  * HTML escapes hostile input (xss surface)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook import digest as digest_mod


def _make_g(**overrides):
    """Fake GmailIntegration with the attributes build_digest_html reads."""
    g = SimpleNamespace(
        last_sent_at=None,
        include_notebooks=True,
        include_sources=True,
        include_notes=True,
        include_podcasts=True,
        include_memory=True,
    )
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


@pytest.fixture
def fake_query(monkeypatch):
    """Patch _safe_query with a programmable stub. Returns a dict the test
    can mutate per-call to control what each table query returns."""
    rows_for: dict[str, list[dict]] = {}

    async def _stub(query: str, vars: dict):
        # Pick rows by the table referenced in the query.
        for table, rows in rows_for.items():
            if (
                f"FROM {table} " in query
                or f"FROM {table}\n" in query
                or query.rstrip().endswith(f"FROM {table}")
            ):
                return rows
        return []

    monkeypatch.setattr(digest_mod, "_safe_query", _stub)
    return rows_for


@pytest.mark.asyncio
async def test_empty_activity_shows_quiet_days_message(fake_query):
    g = _make_g()
    html, total = await digest_mod.build_digest_html(g)
    assert total == 0
    assert "No notebook activity" in html
    assert "Deeper Notebook" in html  # header rendered
    assert "Open Notebook Plus" not in html


@pytest.mark.asyncio
async def test_notebook_section_renders_and_counts(fake_query):
    fake_query["notebook"] = [
        {"id": "notebook:1", "name": "Research", "description": "AI papers"},
        {"id": "notebook:2", "name": "Planning", "description": ""},
    ]
    g = _make_g()
    html, total = await digest_mod.build_digest_html(g)
    assert total == 2
    assert "Notebooks" in html
    assert "Research" in html
    assert "AI papers" in html
    assert "Planning" in html


@pytest.mark.asyncio
async def test_section_toggles_are_respected(fake_query):
    fake_query["notebook"] = [{"id": "notebook:1", "name": "Visible"}]
    fake_query["source"] = [{"id": "source:1", "title": "Hidden"}]
    g = _make_g(include_sources=False)
    html, total = await digest_mod.build_digest_html(g)
    assert total == 1
    assert "Visible" in html
    assert "Hidden" not in html


@pytest.mark.asyncio
async def test_total_aggregates_across_sections(fake_query):
    fake_query["notebook"] = [{"id": "notebook:1", "name": "A"}]
    fake_query["source"] = [
        {"id": "source:1", "title": "B"},
        {"id": "source:2", "title": "C"},
    ]
    fake_query["note"] = [{"id": "note:1", "title": "D"}]
    fake_query["episode"] = [{"id": "episode:1", "name": "E"}]
    fake_query["memory_fact"] = [
        {"id": "memory_fact:1", "text": "F", "confidence": 0.9}
    ]
    g = _make_g()
    html, total = await digest_mod.build_digest_html(g)
    assert total == 6
    assert "Notebooks" in html
    assert "Sources added" in html
    assert "Notes written" in html
    assert "Podcast episodes" in html
    assert "Memory facts" in html


@pytest.mark.asyncio
async def test_hostile_input_is_html_escaped(fake_query):
    # An evil notebook name should NOT come back as live HTML.
    fake_query["notebook"] = [
        {
            "id": "notebook:xss",
            "name": "<script>alert(1)</script>",
            "description": "<img src=x onerror=alert(1)>",
        }
    ]
    g = _make_g()
    html, _ = await digest_mod.build_digest_html(g)
    # The raw tag is never present; the escaped version is.
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html


@pytest.mark.asyncio
async def test_window_label_changes_after_first_send(fake_query):
    fake_query["notebook"] = [{"id": "notebook:1", "name": "X"}]
    # First-time digest
    g1 = _make_g(last_sent_at=None)
    html1, _ = await digest_mod.build_digest_html(g1)
    assert "in the last 7 days" in html1

    # Subsequent digest
    g2 = _make_g(last_sent_at=datetime.now(timezone.utc) - timedelta(days=1))
    html2, _ = await digest_mod.build_digest_html(g2)
    assert "since last digest" in html2


# ---------------------------------------------------------------------------
# v0.8.27 — severity-aware logging in _safe_query.
#
# Pre-v0.8.27 _safe_query did `except Exception: return []` with NO log —
# identical to the v0.8.19 memory_recall silent-swallow that hid a
# production-broken query for 50+ releases. These tests pin the new
# contract: classify the exception, log at WARNING for genuine schema
# errors, DEBUG for benign "table missing".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v0827_safe_query_logs_warning_on_schema_error(monkeypatch):
    """A SurrealDB 'Parse error' / 'Missing order idiom' / etc. must
    log at WARNING. Pre-v0.8.27 these were silent — the digest would
    omit the section and the user would just see "quiet day", with no
    signal that something was broken."""
    import asyncio

    from loguru import logger

    # Force the production repo_query to raise with a schema error.
    async def _boom(query, vars=None):
        raise RuntimeError("Parse error: Missing order idiom in statement")

    monkeypatch.setattr(digest_mod, "repo_query", _boom)

    # Capture loguru emissions (loguru bypasses stdlib caplog).
    captured: list[dict] = []
    sink_id = logger.add(
        lambda msg: captured.append(
            {"level": msg.record["level"].name, "message": msg.record["message"]}
        ),
        level="DEBUG",
    )
    try:
        result = await digest_mod._safe_query("SELECT * FROM ?", {})
    finally:
        logger.remove(sink_id)

    # Empty result (correct — section gets omitted) ...
    assert result == []
    # ... but at least one WARNING line was emitted, with the schema-
    # error verbiage so the operator can find the broken query.
    warnings = [c for c in captured if c["level"] == "WARNING"]
    assert warnings, (
        "v0.8.27 broken: schema errors in digest queries must surface "
        "as WARNING logs. Without this, a future SurrealDB upgrade "
        "that breaks one of the digest queries silently corrupts the "
        "digest output — same shape as v0.8.19 memory_recall bug."
    )
    assert any("SCHEMA ERROR" in w["message"] for w in warnings), (
        f"Expected SCHEMA ERROR token in WARNING; got: {warnings}"
    )


@pytest.mark.asyncio
async def test_v0827_safe_query_stays_debug_on_table_missing(monkeypatch):
    """Benign fresh-install case (memory_fact table doesn't exist yet
    on a fresh DB) must stay at DEBUG. Otherwise launcher.log fills
    with WARNINGs on every 5-minute digest scheduler tick — the
    operator can't see real bugs through the noise."""
    from loguru import logger

    async def _missing(query, vars=None):
        raise RuntimeError("Table missing: 'memory_fact' not found")

    monkeypatch.setattr(digest_mod, "repo_query", _missing)

    captured: list[dict] = []
    sink_id = logger.add(
        lambda msg: captured.append(
            {"level": msg.record["level"].name, "message": msg.record["message"]}
        ),
        level="DEBUG",
    )
    try:
        result = await digest_mod._safe_query("SELECT * FROM memory_fact", {})
    finally:
        logger.remove(sink_id)

    assert result == []
    # No WARNING / ERROR — only DEBUG.
    noisy = [c for c in captured if c["level"] in ("WARNING", "ERROR")]
    assert not noisy, (
        f"v0.8.27: table-missing must stay at DEBUG. Found "
        f"WARNING/ERROR emissions: {noisy}. Fresh-install installs "
        f"would spam launcher.log every 5 minutes via the digest "
        f"scheduler tick."
    )
    assert any(c["level"] == "DEBUG" for c in captured), (
        f"Expected at least one DEBUG message for table-missing; got: {captured}"
    )


@pytest.mark.asyncio
async def test_v0827_safe_query_logs_warning_on_unknown_error(monkeypatch):
    """An error that's NOT in either substring list (e.g. a connection
    drop or an unknown SurrealDB message format) must still surface as
    WARNING. Better to err on the side of visibility — an unknown
    error suppressing a section is still a bug worth seeing."""
    from loguru import logger

    async def _weird(query, vars=None):
        raise RuntimeError("ConnectionDropped: WS frame 0x4F2C")

    monkeypatch.setattr(digest_mod, "repo_query", _weird)

    captured: list[dict] = []
    sink_id = logger.add(
        lambda msg: captured.append(
            {"level": msg.record["level"].name, "message": msg.record["message"]}
        ),
        level="DEBUG",
    )
    try:
        result = await digest_mod._safe_query("SELECT * FROM source", {})
    finally:
        logger.remove(sink_id)

    assert result == []
    warnings = [c for c in captured if c["level"] == "WARNING"]
    assert warnings, (
        f"v0.8.27: an unknown error must still emit WARNING. Pre-fix "
        f"the digest silently dropped sections on any error; this "
        f"includes the unknown-error case. Got: {captured}"
    )
