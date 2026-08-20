"""v0.8.48 — notebook delete must clean cascade-deleted sessions'
LangGraph checkpoint threads (regression / leak fix).

`Notebook.delete()` cascade-deletes the `chat_session` rows linked via
the `refers_to` edge (v0.7.61), but the domain layer can't touch the
LangGraph checkpointer (layering). The single-session delete path
(api/routers/chat.py v0.7.171) cleans checkpoints; the notebook-cascade
path never did, so those threads leaked forever —
`prune_old_checkpoints` only trims the OLDEST snapshots WITHIN a thread
that exceeds the per-thread retention (50), so an orphaned
<50-checkpoint thread is unreachable.

Fix: `Notebook.delete()` now returns `deleted_chat_session_ids`, and the
notebooks router feeds them to `_cleanup_checkpoint_threads`, which
mirrors the chat router's best-effort `delete_thread` cleanup.

The meaningful new logic is the router-side helper (the domain delete is
a live-SurrealDB integration path covered by the integration suite); we
test the helper behaviorally and guard the two-halves contract by source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.routers import notebooks as nb_router

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_source(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _cleanup_checkpoint_threads — behavioral
# ---------------------------------------------------------------------------


class _FakeCheckpointer:
    def __init__(self, boom: set[str] | None = None):
        self.calls: list[str] = []
        self._boom = boom or set()

    def delete_thread(self, thread_id: str) -> None:
        self.calls.append(thread_id)
        if thread_id in self._boom:
            raise RuntimeError("simulated checkpoint store failure")


class _FakeGraph:
    def __init__(self, checkpointer):
        self.checkpointer = checkpointer


@pytest.mark.asyncio
async def test_cleanup_calls_delete_thread_per_session(monkeypatch):
    cp = _FakeCheckpointer()
    monkeypatch.setattr(
        "deeper_notebook.graphs.chat.chat_graph", _FakeGraph(cp), raising=False
    )
    n = await nb_router._cleanup_checkpoint_threads(
        ["chat_session:a", "chat_session:b"], context="test"
    )
    assert n == 2
    assert cp.calls == ["chat_session:a", "chat_session:b"]


@pytest.mark.asyncio
async def test_cleanup_is_best_effort_and_continues_past_failure(monkeypatch):
    """One thread's cleanup blowing up must NOT abort the rest, and must
    NOT raise (the SurrealDB rows are already gone)."""
    cp = _FakeCheckpointer(boom={"chat_session:boom"})
    monkeypatch.setattr(
        "deeper_notebook.graphs.chat.chat_graph", _FakeGraph(cp), raising=False
    )
    n = await nb_router._cleanup_checkpoint_threads(
        ["chat_session:a", "chat_session:boom", "chat_session:c"], context="test"
    )
    # All three attempted, the failing one not counted.
    assert cp.calls == ["chat_session:a", "chat_session:boom", "chat_session:c"]
    assert n == 2


@pytest.mark.asyncio
async def test_cleanup_noop_on_empty_list():
    assert await nb_router._cleanup_checkpoint_threads([], context="t") == 0


@pytest.mark.asyncio
async def test_cleanup_noop_when_checkpointer_lacks_delete_thread(monkeypatch):
    """An older/alternate checkpointer without delete_thread → no-op, no
    crash."""
    monkeypatch.setattr(
        "deeper_notebook.graphs.chat.chat_graph",
        _FakeGraph(object()),  # plain object has no delete_thread
        raising=False,
    )
    n = await nb_router._cleanup_checkpoint_threads(["chat_session:a"], context="t")
    assert n == 0


# ---------------------------------------------------------------------------
# Two-halves contract — source guard
# ---------------------------------------------------------------------------


def test_domain_delete_returns_session_ids_key():
    """Notebook.delete() must surface the cascade-deleted session ids
    under the exact key the router reads."""
    src = _read_source("deeper_notebook/domain/notebook.py")
    assert '"deleted_chat_session_ids"' in src
    assert "deleted_chat_session_ids = (" in src  # the stringify line


def test_router_delete_invokes_cleanup_with_domain_key():
    """delete_notebook must feed the domain's returned ids into the
    checkpoint cleanup. Guards against the key being renamed on one side
    only."""
    src = _read_source("api/routers/notebooks.py")
    assert "_cleanup_checkpoint_threads(" in src
    assert 'result.get("deleted_chat_session_ids")' in src
