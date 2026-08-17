"""v0.8.97 — Debate mode (source-grounded opposition).

Contract: `chat_mode` is per-turn, defaults to "standard", and only the
literal "debate" swaps the system template. The debate template must carry
the same grounding + citation contracts as standard chat — a debate partner
that invents evidence is a regression, not a feature.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.routers.chat import ExecuteChatRequest

_ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_chat_mode_defaults_to_standard():
    req = ExecuteChatRequest(session_id="chat_session:x", message="hi", context={})
    assert req.chat_mode == "standard"


def test_chat_mode_accepts_debate():
    req = ExecuteChatRequest(
        session_id="chat_session:x", message="hi", context={}, chat_mode="debate"
    )
    assert req.chat_mode == "debate"


def test_chat_mode_rejects_unknown_values():
    """A typo'd mode must 422, not silently fall back to standard."""
    with pytest.raises(ValidationError):
        ExecuteChatRequest(
            session_id="chat_session:x", message="hi", context={},
            chat_mode="argument",
        )


def test_router_threads_chat_mode_into_state():
    src = _src("api/routers/chat.py")
    # Both /chat/execute and /chat/stream set the state key from the request.
    assert src.count('state_values["chat_mode"] = request.chat_mode') == 2


def test_graph_selects_debate_template_from_state():
    src = _src("deeper_notebook/graphs/chat.py")
    assert '"chat/debate"' in src
    assert 'state.get("chat_mode") == "debate"' in src
    # The standard path must remain the fallback.
    assert 'else "chat/system"' in src


def test_debate_template_renders_with_and_without_context():
    from ai_prompter import Prompter

    rendered = Prompter(prompt_template="chat/debate").render(
        data={"context": "source:abc — The sky is sometimes green.", "notebook": None,
              "memory_block": ""}
    )
    assert "steelman" in rendered.lower() or "strongest form" in rendered.lower()
    assert "The sky is sometimes green." in rendered

    bare = Prompter(prompt_template="chat/debate").render(data={})
    assert "# CONTEXT" not in bare  # context block is conditional


def test_debate_template_keeps_the_citation_contract():
    text = (_ROOT / "prompts/chat/debate.jinja").read_text(encoding="utf-8")
    for marker in (
        "# GROUNDING & HONESTY",
        "# CITING INSTRUCTIONS",
        "[document_id]",
        "`[mcp:N]`",
        "Never fabricate document IDs",
    ):
        assert marker in text, f"debate template missing {marker}"
    # Debate-specific obligations.
    for marker in ("Steelman", "Concede", "attack the position, never the person"):
        assert marker in text, f"debate template missing {marker}"
