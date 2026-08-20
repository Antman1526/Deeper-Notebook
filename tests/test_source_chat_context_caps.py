"""v0.7.12 — regression tests for source_chat context-budget caps.

`_format_source_context` in deeper_notebook/graphs/source_chat.py
previously had ONE cap (source full_text @ 5000 chars hardcoded) and
zero caps on the insight side. A source with 20 LLM-generated insights
of 1500 chars each = 30 KB ≈ 7,500 tokens of context — which combined
with the 8192-token output reservation already overflowed a
16k-context local server (v0.7.8 default).

These tests pin the new env-configurable caps:
  - DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP    (default 4_000)
  - DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP   (default 1_000)
  - DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS       (default 10)
"""

from __future__ import annotations

from deeper_notebook.graphs import source_chat

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _ctx(sources=None, insights=None):
    """Build a ContextBuilder-shaped dict for testing."""
    return {
        "sources": sources or [],
        "insights": insights or [],
        "metadata": {
            "source_count": len(sources or []),
            "insight_count": len(insights or []),
        },
        "total_tokens": 0,
    }


def _source(rid: str, full_text: str) -> dict:
    return {"id": rid, "title": f"Title for {rid}", "full_text": full_text}


def _insight(rid: str, content: str, itype: str = "summary") -> dict:
    return {"id": rid, "insight_type": itype, "content": content}


# ---------------------------------------------------------------------------
# Source full_text cap
# ---------------------------------------------------------------------------


def test_source_full_text_default_cap_is_4000(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    big = "A" * 10_000
    out = source_chat._format_source_context(_ctx(sources=[_source("source:1", big)]))
    # Content section appears after a header; just verify total source
    # content size is bounded
    assert "AAAA" in out
    assert source_chat._SOURCE_TRUNCATION_MARKER in out
    # The original 10k of A's was reduced — verify not all 10k landed
    assert out.count("A") <= 4_000 + 10  # cap + tiny slack for stray As


def test_source_full_text_respects_env_cap(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", "1000")
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    big = "B" * 5_000
    out = source_chat._format_source_context(_ctx(sources=[_source("source:1", big)]))
    assert source_chat._SOURCE_TRUNCATION_MARKER in out
    assert out.count("B") <= 1_000 + 10


def test_source_under_cap_not_truncated(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    short = "Short article body."
    out = source_chat._format_source_context(_ctx(sources=[_source("s:1", short)]))
    assert short in out
    # No truncation marker for the source section
    # (insights section is empty, so any marker would be from source)
    assert source_chat._SOURCE_TRUNCATION_MARKER not in out


# ---------------------------------------------------------------------------
# Per-insight content cap
# ---------------------------------------------------------------------------


def test_insight_content_default_cap_is_1000(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    fat_insight = _insight("insight:1", "C" * 5_000)
    out = source_chat._format_source_context(_ctx(insights=[fat_insight]))
    assert source_chat._SOURCE_TRUNCATION_MARKER in out
    assert out.count("C") <= 1_000 + 10


def test_insight_content_respects_env_cap(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", "300")
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    fat = _insight("insight:1", "D" * 2_000)
    out = source_chat._format_source_context(_ctx(insights=[fat]))
    assert source_chat._SOURCE_TRUNCATION_MARKER in out
    assert out.count("D") <= 300 + 10


def test_short_insight_not_truncated(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    short = _insight("insight:1", "Brief insight body.")
    out = source_chat._format_source_context(_ctx(insights=[short]))
    assert "Brief insight body." in out
    assert source_chat._SOURCE_TRUNCATION_MARKER not in out


def test_insight_handles_non_string_content(monkeypatch):
    """Defensive: insight content might come back as a list or dict
    from quirky upstream code paths — don't crash."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    weird = {
        "id": "insight:1",
        "insight_type": "summary",
        "content": ["chunk a", "chunk b"],
    }
    # Must not raise
    out = source_chat._format_source_context(_ctx(insights=[weird]))
    assert "insight:1" in out


# ---------------------------------------------------------------------------
# Max insight count cap
# ---------------------------------------------------------------------------


def test_max_insights_default_is_10(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    many = [_insight(f"insight:{i}", f"body {i}") for i in range(25)]
    out = source_chat._format_source_context(_ctx(insights=many))
    # First 10 IDs present
    for i in range(10):
        assert f"insight:{i}" in out
    # 11th+ not present
    for i in range(10, 25):
        assert f"insight:{i}" not in out
    # Marker mentions dropped count
    assert "15 additional insights elided" in out


def test_max_insights_env_override(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", "3")

    many = [_insight(f"insight:{i}", f"body {i}") for i in range(10)]
    out = source_chat._format_source_context(_ctx(insights=many))
    for i in range(3):
        assert f"insight:{i}" in out
    for i in range(3, 10):
        assert f"insight:{i}" not in out
    assert "7 additional insights elided" in out


def test_under_max_no_drop_marker(monkeypatch):
    """If we have fewer insights than the cap, the 'elided' marker
    must NOT appear (no false-positive warnings about drops)."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    few = [_insight(f"insight:{i}", "body") for i in range(3)]
    out = source_chat._format_source_context(_ctx(insights=few))
    assert "elided for context budget" not in out


# ---------------------------------------------------------------------------
# Env-var hardening
# ---------------------------------------------------------------------------


def test_invalid_env_falls_back_to_defaults(monkeypatch):
    """Garbage in any of the three env vars → default applied silently
    (with a warning log) instead of crashing or passing garbage downstream."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", "not-an-int")
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", "abc")
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", "nope")

    src = _source("source:1", "X" * 10_000)
    insights = [_insight(f"insight:{i}", "Y" * 3_000) for i in range(20)]
    # Must not raise
    out = source_chat._format_source_context(_ctx(sources=[src], insights=insights))
    # Defaults kicked in: source ≤ 4000 X's, insights ≤ 10 of them
    assert out.count("X") <= 4_000 + 10
    for i in range(10):
        assert f"insight:{i}" in out
    for i in range(10, 20):
        assert f"insight:{i}" not in out


def test_too_low_env_falls_back(monkeypatch):
    """Caps below the minimum sentinel are typo-protection: fall back
    to default rather than ship a useless 50-char snippet."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP", "50")
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP", "10")
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS", raising=False)

    src = _source("source:1", "X" * 10_000)
    insight = _insight("insight:1", "Y" * 5_000)
    out = source_chat._format_source_context(_ctx(sources=[src], insights=[insight]))
    # Defaults (4000 / 1000) applied — way more than the bogus 50/10
    assert out.count("X") > 100
    assert out.count("Y") > 100
