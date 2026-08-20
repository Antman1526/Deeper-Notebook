"""v0.8.67 (audit A4) — ContextItem token count excludes dict-syntax overhead.

Was `token_count(str(self.content))` over the whole dict — counting `{`, `}`,
quotes, and keys ('full_text', 'insights') that never reach the LLM, which
over-counted the budget and under-included real content. Now counts only the
human-readable text fields.
"""

from __future__ import annotations

from deeper_notebook.utils.context_builder import ContextItem, _content_text
from deeper_notebook.utils.token_utils import token_count


def test_extracts_only_text_fields():
    d = {
        "id": "source:1",
        "title": "Title",
        "full_text": "the body text here",
        "insights": [{"content": "insight one"}, {"content": "insight two"}],
    }
    txt = _content_text(d)
    assert "Title" in txt and "the body text here" in txt
    assert "insight one" in txt and "insight two" in txt
    # dict syntax / keys are NOT in the counted text
    assert "full_text" not in txt and "{" not in txt and "'id'" not in txt


def test_token_count_lower_than_str_dict():
    d = {
        "id": "source:1",
        "title": "T",
        "full_text": "hello world body text",
        "insights": [{"content": "insight one"}],
    }
    item = ContextItem(id="source:1", type="source", content=d)
    assert item.token_count == token_count(_content_text(d))
    # strictly fewer tokens than the old str(dict) approach (overhead removed)
    assert item.token_count < token_count(str(d))


def test_note_and_nondict_and_none():
    assert (
        _content_text({"id": "n", "title": "NT", "content": "note body"})
        == "NT\nnote body"
    )
    assert _content_text("plain string") == "plain string"
    assert _content_text(None) == ""


def test_explicit_token_count_is_respected():
    item = ContextItem(
        id="x", type="note", content={"content": "ignored"}, token_count=42
    )
    assert item.token_count == 42
