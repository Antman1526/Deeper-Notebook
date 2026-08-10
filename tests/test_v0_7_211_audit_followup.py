"""v0.7.211 — Follow-up fixes from the v0.7.210 deep-audit deferred
list. Three discrete fixes:

1. **Worker `--max-tasks` explicit** in the launcher spawn so the
   intent (5 concurrent tasks) is locked in source instead of
   depending on the surreal-commands default. Tunable via
   `DEEPER_NOTEBOOK_WORKER_MAX_TASKS` env, clamped to 1-32.

2. **Missing-GGUF startup warnings** surfaced via the ProgressBus
   so the user can see why local chat / embed silently isn't
   available, instead of opening the app and finding empty
   credential rows with no explanation.

3. **AsyncSqliteSaver connection close on shutdown** for both
   chat.py and source_chat.py. Previously the aiosqlite
   connections + their background threads leaked past the
   FastAPI shutdown — harmless on POSIX but locked the SQLite
   file on Windows and bumped the FD count over long-running
   .app sessions.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1: Worker max-tasks explicit
# ---------------------------------------------------------------------------


def test_worker_spawn_passes_max_tasks_flag():
    """v0.7.211 — `_spawn_worker` must include `--max-tasks` in
    its arg list so the worker's 5-task-concurrency default is
    explicit and tunable via DEEPER_NOTEBOOK_WORKER_MAX_TASKS."""
    src = _src("desktop/launcher.py")
    assert '"--max-tasks", str(max_tasks)' in src
    assert 'DEEPER_NOTEBOOK_WORKER_MAX_TASKS' in src
    # Clamped to [1, 32] so a fat-fingered "0" or "1000" can't
    # destabilise the worker.
    assert "max(1, min(int(max_tasks_raw), 32))" in src


# ---------------------------------------------------------------------------
# Fix 2: Missing-GGUF startup warnings
# ---------------------------------------------------------------------------


def test_app_publishes_warning_when_chat_gguf_missing():
    """v0.7.211 — when `pick_chat_llm_file` returns None on a
    llamacpp-provider install, the launcher must publish a
    `provider.llamacpp` warning to the ProgressBus so the user
    can see why local chat isn't available."""
    src = _src("desktop/app.py")
    assert "v0.7.211" in src and "No chat GGUF found" in src
    assert 'ctx.progress_bus.publish(' in src
    assert '"provider.llamacpp"' in src
    assert '"warning"' in src


def test_app_publishes_warning_when_embedding_gguf_missing():
    """v0.7.211 — same for the embedding GGUF (nomic). Without
    this warning, the user uploads sources and silently gets no
    vector search results."""
    src = _src("desktop/app.py")
    assert "No embedding GGUF found" in src
    assert '"provider.embedding"' in src


# ---------------------------------------------------------------------------
# Fix 3: AsyncSqliteSaver close on shutdown
# ---------------------------------------------------------------------------


def test_chat_module_exposes_close_async_graph():
    """v0.7.211 — chat.py must export an idempotent
    `close_async_graph()` for the API lifespan teardown."""
    src = _src("deeper_notebook/graphs/chat.py")
    assert "async def close_async_graph()" in src
    assert "global _async_graph, _async_aio_conn" in src
    # Idempotent + no-op on never-built graph.
    assert "if conn is None:" in src


def test_source_chat_module_exposes_close_async_graph():
    """v0.7.211 — same teardown helper for source_chat.py."""
    src = _src("deeper_notebook/graphs/source_chat.py")
    assert "async def close_async_source_chat_graph()" in src
    assert "_async_source_chat_aio_conn" in src


def test_api_lifespan_calls_both_close_helpers():
    """v0.7.211 — api/main.py lifespan shutdown must invoke both
    close helpers after the DB pool drain. Otherwise the
    helpers exist but are never wired in."""
    src = _src("api/main.py")
    assert "from deeper_notebook.graphs.chat import close_async_graph" in src
    assert "await close_async_graph()" in src
    assert (
        "from deeper_notebook.graphs.source_chat import (\n"
        "            close_async_source_chat_graph,"
    ) in src
    assert "await close_async_source_chat_graph()" in src


# ---------------------------------------------------------------------------
# Runtime smoke: close helpers are safe on never-constructed graph
# ---------------------------------------------------------------------------


def test_close_async_graph_is_safe_on_never_built(monkeypatch):
    """v0.7.211 — `close_async_graph()` must be safe to call when
    the graph was never lazily constructed (no chat traffic this
    session). API shutdown happens regardless of whether the
    chat path was exercised."""
    import asyncio

    from deeper_notebook.graphs import chat as chat_mod

    # Force the module to look "never built".
    monkeypatch.setattr(chat_mod, "_async_graph", None)
    monkeypatch.setattr(chat_mod, "_async_aio_conn", None)

    async def _run():
        await chat_mod.close_async_graph()

    asyncio.run(_run())  # must not raise
