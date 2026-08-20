"""v0.7.171 — LangGraph checkpoint cleanup on session delete.

Background: `ChatSession.delete()` removes the SurrealDB row but
never touched the LangGraph SQLite checkpoint store. The checkpoint
+ writes tables (keyed by `thread_id = full_session_id`) kept the
full message history forever:

  - Disk usage grew unbounded with every delete
  - If a chat_session: ID ever collided with a past one (test
    harness, manual SurrealQL insert, etc.), the "new" session
    inherited the old transcript as its history (security/privacy
    issue — wrong conversation surfaced to a different user/session)
  - The v0.7.125 checkpoint_prune background task cleans
    per-thread limit (keeps N newest checkpoints per thread) but
    does NOT delete entire orphaned threads

v0.7.171 adds an explicit `checkpointer.delete_thread(...)` call
in both `delete_session` endpoints (chat.py + source_chat.py),
wrapped in best-effort try/except so a checkpoint-cleanup failure
doesn't block the primary SurrealDB delete.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AST-level guards: cleanup MUST be present in both delete paths
# ---------------------------------------------------------------------------


def test_chat_delete_session_invokes_checkpoint_cleanup():
    """v0.7.171: /chat/sessions/{id} DELETE must call
    `checkpointer.delete_thread(full_session_id)` (via to_thread,
    because SqliteSaver is sync) AFTER session.delete().
    """
    src = _read_source("api/routers/chat.py")

    # The cleanup block must reference the checkpointer + delete_thread
    # attribute lookup (defensive — supports older LangGraph versions
    # that may not ship the method).
    assert 'getattr(chat_graph, "checkpointer"' in src, (
        "v0.7.171 regression: chat.py delete_session no longer "
        "fetches `chat_graph.checkpointer`."
    )
    assert 'getattr(checkpointer, "delete_thread"' in src
    assert "await asyncio.to_thread(delete_thread, full_session_id)" in src


def test_source_chat_delete_session_invokes_checkpoint_cleanup():
    """v0.7.171: same fix for the source-chat delete endpoint.
    `source_chat.py` keeps a separate `source_chat_graph` with its
    own checkpoint store; both need the cleanup."""
    src = _read_source("api/routers/source_chat.py")
    assert 'getattr(source_chat_graph, "checkpointer"' in src
    assert 'getattr(checkpointer, "delete_thread"' in src
    assert "await asyncio.to_thread(delete_thread, full_session_id)" in src


def test_cleanup_is_best_effort_wrapped():
    """v0.7.171: the cleanup MUST be wrapped in try/except so a
    failure (e.g. LangGraph version without delete_thread, SQLite
    transient lock) doesn't 500 the delete endpoint. The
    SurrealDB delete has already succeeded by this point;
    failing the response would mislead the caller into thinking
    the delete didn't happen.

    The fallback narrative is intentionally surfaced via logger.warning
    so operators can see if cleanup is consistently failing (canary
    for "the LangGraph upgrade broke our private method assumption").
    """
    for rel in ("api/routers/chat.py", "api/routers/source_chat.py"):
        src = _read_source(rel)
        # Find the cleanup block region (widen to 400 chars back so
        # the enclosing `try:` keyword is captured).
        idx = src.index("await asyncio.to_thread(delete_thread, full_session_id)")
        region = src[idx - 400 : idx + 500]
        assert "try:" in region, (
            f"v0.7.171 regression in {rel}: cleanup is no longer "
            f"wrapped in try/except. Region:\n{region}"
        )
        assert "except Exception" in region, (
            f"v0.7.171 regression in {rel}: cleanup must catch broadly so "
            f"unexpected LangGraph API drift doesn't 500 the delete."
        )
        assert "logger.warning" in region, (
            f"v0.7.171 regression in {rel}: cleanup failure must surface "
            f"a WARNING (canary). debug-level would hide a systematic issue."
        )


def test_cleanup_runs_AFTER_session_delete_not_before():
    """v0.7.171: order matters. If we called delete_thread BEFORE
    session.delete() and the SurrealDB delete then failed, we'd have
    a session row pointing at zero history (worst of both worlds —
    user sees the session but it's empty). Order: SurrealDB row goes
    first; checkpoint cleanup is the cleanup pass."""
    for rel in ("api/routers/chat.py", "api/routers/source_chat.py"):
        src = _read_source(rel)
        # session.delete() must appear before the to_thread cleanup call.
        idx_session_delete = src.index("await session.delete()")
        idx_cleanup = src.index(
            "await asyncio.to_thread(delete_thread, full_session_id)"
        )
        assert idx_session_delete < idx_cleanup, (
            f"v0.7.171 regression in {rel}: session.delete() must run "
            f"BEFORE the LangGraph cleanup. Got reverse order — risks "
            f"orphaned session rows pointing at empty histories on partial "
            f"failure."
        )
