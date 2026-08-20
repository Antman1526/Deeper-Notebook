"""v0.8.65h — /chat/stream must strip <think> blocks from streamed tokens.

Reasoning models (Qwen3, DeepSeek-R1, ...) emit <think>…</think> before the
answer. Pre-v0.8.65h the raw chunks (incl. the think content) were streamed to
the user and only replaced by the cleaned answer at the `done` event, so users
saw raw reasoning flash by. `_visible_streamed_text` derives the visible
(non-think) prefix from the accumulated stream so only the answer is emitted.
"""

from __future__ import annotations

from api.routers.chat import _visible_streamed_text


def _simulate_stream(chunks: list[str]) -> str:
    """Replay chunks through the same delta logic as the stream handler;
    return the concatenation of everything actually emitted to the client."""
    accum = ""
    sent = ""
    emitted: list[str] = []
    for c in chunks:
        accum += c
        visible = _visible_streamed_text(accum)
        if visible.startswith(sent) and len(visible) > len(sent):
            emitted.append(visible[len(sent) :])
            sent = visible
        elif visible != sent:
            sent = visible  # resync (think opened after answer text)
    return "".join(emitted)


def test_complete_think_block_removed():
    assert _visible_streamed_text("<think>reasoning</think>The answer") == "The answer"


def test_unclosed_think_is_fully_suppressed():
    assert _visible_streamed_text("<think>still reasoning about it") == ""


def test_text_before_think_kept():
    assert _visible_streamed_text("Quick note. <think>then think") == "Quick note. "


def test_no_think_passthrough():
    assert _visible_streamed_text("just a normal answer") == "just a normal answer"


def test_case_insensitive_multiblock():
    assert _visible_streamed_text("<THINK>a</THINK>X<think>b</think>Y") == "XY"


def test_trailing_partial_open_tag_withheld():
    # A partial "<th" at the end must not leak — it could become "<think>".
    assert _visible_streamed_text("answer <th") == "answer "
    assert _visible_streamed_text("answer <thi") == "answer "


def test_stream_split_tag_never_leaks_think():
    """The open tag is split across chunks; the answer streams cleanly."""
    out = _simulate_stream(
        ["<th", "ink>reason", "ing here</think>", "Final ", "answer."]
    )
    assert "<think>" not in out and "reasoning" not in out
    assert out == "Final answer."


def test_stream_normal_model_unchanged():
    """A non-reasoning model streams identically to the raw chunks (concatenated)."""
    chunks = ["Hello", ", ", "world", "!"]
    assert _simulate_stream(chunks) == "Hello, world!"


def test_stream_close_tag_split_stays_suppressed():
    out = _simulate_stream(["<think>think", "ing</thi", "nk>Answer ", "here."])
    assert "thinking" not in out
    assert out == "Answer here."
