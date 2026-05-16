"""v0.7.71 — pure-render unit tests for memory_recall.

The query path is exercised against the live SurrealDB in integration
tests; here we only verify the parts that are deterministic without
a DB: the SELECT-VALUE coercion helper and the prompt-block renderer.
"""
from __future__ import annotations

import pytest

from open_notebook.utils.memory_recall import (
    _coerce_text,
    render_memory_block,
)


def test_coerce_text_handles_string():
    assert _coerce_text("hello world") == "hello world"
    assert _coerce_text("  trim me  ") == "trim me"


def test_coerce_text_handles_none():
    assert _coerce_text(None) == ""


def test_coerce_text_handles_dict_with_text_field():
    """If SELECT VALUE flattening didn't happen and we got back a row dict,
    fall back to the `text` field rather than stringifying the dict."""
    assert _coerce_text({"text": "fact about user"}) == "fact about user"


def test_coerce_text_handles_dict_without_text_field():
    """An empty dict has no text field; should produce empty string, not 'None'."""
    assert _coerce_text({"text": None}) == ""
    assert _coerce_text({"id": "memory_fact:abc"}) == ""


def test_coerce_text_handles_other_types():
    """Numbers, lists — fall back to stringification."""
    assert _coerce_text(42) == "42"


def test_render_returns_empty_string_for_empty_memory():
    """Empty input → empty string so the Jinja `{% if memory_block %}`
    short-circuits and no section appears in the system prompt."""
    assert render_memory_block({"facts": [], "preferences": []}) == ""
    assert render_memory_block({}) == ""


def test_render_includes_only_preferences_when_only_preferences():
    out = render_memory_block({
        "facts": [],
        "preferences": [{"text": "prefers concise answers"}],
    })
    assert "## User preferences" in out
    assert "prefers concise answers" in out
    # No facts section when facts list is empty
    assert "## Recent facts" not in out


def test_render_includes_only_facts_when_only_facts():
    out = render_memory_block({
        "facts": [{"text": "uses TypeScript"}],
        "preferences": [],
    })
    assert "## Recent facts learned about the user" in out
    assert "uses TypeScript" in out
    # No preferences section
    assert "## User preferences" not in out


def test_render_includes_both_sections_when_both_present():
    out = render_memory_block({
        "facts": [
            {"text": "uses TypeScript"},
            {"text": "lives in Berlin"},
        ],
        "preferences": [
            {"text": "prefers concise answers"},
        ],
    })
    assert "## User preferences" in out
    assert "## Recent facts learned about the user" in out
    # Preferences come BEFORE facts (more authoritative)
    assert out.index("## User preferences") < out.index("## Recent facts")
    # All items appear
    assert "uses TypeScript" in out
    assert "lives in Berlin" in out
    assert "prefers concise answers" in out


def test_render_strips_trailing_whitespace():
    """Trailing newlines/whitespace don't leak into the prompt."""
    out = render_memory_block({
        "facts": [{"text": "fact"}],
        "preferences": [],
    })
    assert out == out.rstrip()


def test_render_handles_missing_keys_gracefully():
    """The recall dict shape should always have both keys, but be defensive."""
    assert render_memory_block({"facts": [{"text": "f"}]}) != ""
    assert render_memory_block({"preferences": [{"text": "p"}]}) != ""


@pytest.mark.parametrize("count", [1, 5, 15])
def test_render_produces_one_bullet_per_item(count: int):
    facts = [{"text": f"fact {i}"} for i in range(count)]
    out = render_memory_block({"facts": facts, "preferences": []})
    # Each fact becomes a bullet line `- fact i`
    assert out.count("\n- ") == count
