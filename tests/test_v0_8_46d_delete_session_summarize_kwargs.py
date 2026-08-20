"""v0.8.46d — delete_session must not pass bad kwargs to the
session-summarizer (regression).

Bug: the v0.8.43 `replace_all` that added
`disabled_mcp_servers=getattr(session, "disabled_mcp_servers", None)`
after every `model_override=getattr(session, "model_override", None),`
in api/routers/chat.py ALSO matched the `_fire_memory_summarize_session(
...)` call inside `delete_session` — passing a kwarg the function's
signature (chat_session_id + model_override only) doesn't accept. That
raised `TypeError` at call-binding time on EVERY session delete, which
the handler's `except Exception` re-wrapped as a 500. delete_session
was effectively broken since v0.8.43.

The pre-existing v0.7.171 tests are source-TEXT guards (assert
substrings) — they never invoke delete_session, so they couldn't catch
a call-binding TypeError. This test actually drives the handler.

Two layers:
  1. Signature contract: `_fire_memory_summarize_session` must NOT
     accept `disabled_mcp_servers` (and the handler must not pass it).
  2. Behavioral: delete_session runs to completion (SuccessResponse),
     not a TypeError-induced 500, with all DB/checkpoint deps mocked.
"""

from __future__ import annotations

import inspect

import pytest

from api.routers import chat as chat_router


def test_summarize_session_signature_has_no_disabled_mcp_servers():
    """The summarizer takes only chat_session_id + model_override. If a
    future edit re-adds disabled_mcp_servers to the CALL without adding
    it to the SIGNATURE, the behavioral test below catches it; this
    asserts the signature contract the call relies on."""
    sig = inspect.signature(chat_router._fire_memory_summarize_session)
    assert "disabled_mcp_servers" not in sig.parameters
    assert set(sig.parameters) == {"chat_session_id", "model_override"}


@pytest.mark.asyncio
async def test_delete_session_does_not_raise_typeerror(monkeypatch):
    """Drive the real delete_session handler with mocked DB +
    checkpoint deps and the REAL `_fire_memory_summarize_session`
    (so the call-site kwarg binding is actually exercised). Pre-fix
    this raised TypeError → 500; post-fix it returns SuccessResponse."""

    full_id = "chat_session:abc"

    class _FakeSession:
        id = full_id
        model_override = None
        disabled_mcp_servers = ["SearXNG"]  # present, to mimic v0.8.43 rows

        async def delete(self):
            return None

    async def _fake_get(session_id):
        return _FakeSession()

    # ChatSession.get is a classmethod/staticmethod on the domain model
    # imported into the router module namespace.
    from deeper_notebook.domain import notebook as nb_mod

    monkeypatch.setattr(nb_mod.ChatSession, "get", staticmethod(_fake_get))

    # The summarizer early-returns when memory env vars are absent —
    # ensure they ARE absent so we don't attempt a real submit, but
    # CRUCIALLY do NOT mock the function itself (the bug is the call
    # binding, which happens before the body's early-return).
    for var in ("MEMORY_SURREAL_URL", "MEMORY_EMBED_URL", "MEMORY_CHAT_LLM_URL"):
        monkeypatch.delenv(var, raising=False)

    # Checkpoint cleanup: give chat_graph a fake checkpointer whose
    # delete_thread is a harmless no-op so the post-delete cleanup
    # block doesn't touch a real SQLite store.
    class _FakeCheckpointer:
        def delete_thread(self, thread_id):
            return None

    class _FakeGraph:
        checkpointer = _FakeCheckpointer()

    monkeypatch.setattr(chat_router, "chat_graph", _FakeGraph())

    # Act — must NOT raise.
    resp = await chat_router.delete_session("abc")

    # Assert success shape (SuccessResponse).
    assert getattr(resp, "success", None) is True
