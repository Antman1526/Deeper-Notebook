"""v0.8.67 (audit A3) — Note.get_context('short') token-budgeted truncation.

Was a flat 100-CHAR slice that cut mid-word with no marker, so the LLM treated a
fragment as the whole note. Now a ~160-token budget with an explicit ' […]'
marker, trimmed on a word boundary. 'long' mode is unchanged.
"""

from __future__ import annotations

from deeper_notebook.domain.notebook import Note
from deeper_notebook.utils.token_utils import token_count


def _note(content):
    return Note(title="t", content=content, note_type="human")


def test_short_under_budget_is_unchanged():
    n = _note("hello world, this is a short note")
    assert n.get_context("short")["content"] == "hello world, this is a short note"


def test_short_over_budget_truncated_with_marker_on_word_boundary():
    big = ("word " * 400).strip()  # ~400 tokens, well over the 160 budget
    out = _note(big).get_context("short")["content"]
    assert out.endswith(" […]"), "truncation marker missing"
    # within the token budget (+ a little slack for the marker)
    assert token_count(out) <= 175
    # no mid-word cut: every token before the marker is a whole 'word'
    body = out[: -len(" […]")].strip()
    assert all(tok == "word" for tok in body.split())


def test_long_mode_is_full_content():
    big = ("word " * 400).strip()
    assert _note(big).get_context("long")["content"] == big


def test_none_content_is_none():
    # NB: empty-string content is rejected at construction
    # (Note.content_must_not_be_empty), so only None is a valid "no content"
    # case to exercise here. _short_content() returns None for it.
    assert _note(None).get_context("short")["content"] is None
