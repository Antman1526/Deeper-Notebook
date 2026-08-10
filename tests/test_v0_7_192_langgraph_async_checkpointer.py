"""v0.7.192 — Two real bugs caught by end-to-end testing of the
freshly-built v0.7.191 .app on macOS arm64.

  1. **SqliteSaver no longer supports async methods** in newer
     langgraph (≥ 0.6). `chat_graph.astream_events(...)` and
     `chat_graph.ainvoke(...)` internally call `aget_tuple()`, which
     the sync SqliteSaver raises NotImplementedError on. End-user
     symptom: clicking "Send" in chat instantly returned "Chat
     stream failed unexpectedly." (the v0.7.184 sanitised SSE error
     event). The full traceback in api.log pointed at the langgraph
     internals.

     Fix: introduce `AsyncSqliteSaver`-backed twin graphs
     (`get_async_graph()` + `get_async_source_chat_graph()`) for the
     async write paths. Keep the sync SqliteSaver-backed graphs for
     the existing `asyncio.to_thread(graph.get_state, ...)` reads.
     Both savers point at the SAME on-disk SQLite file so
     checkpoint state stays consistent. The async getters are LAZY
     (instantiated on first call) because `aiosqlite.connect(...)`
     captures the event loop at construct time, which doesn't exist
     at module load.

  2. **`llama_cpp[server]` extras missing from the bundled venv.**
     `desktop/requirements.txt` pinned `llama-cpp-python>=0.3.16,<0.4`
     without the `[server]` extra, so `starlette-context`,
     `sse-starlette`, `pydantic-settings`, and `PyYAML` were never
     installed. Every spawn of `python -m llama_cpp.server` failed
     with `ModuleNotFoundError: No module named 'starlette_context'`,
     leaving the local llamacpp_embed + llamacpp_chat servers dead.
     End-user symptom: source uploads stuck "Processing" forever
     (visible in the screenshot the user shared during testing).

     Fix: `llama-cpp-python[server]>=0.3.16,<0.4` + lockfile regen.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Bug 1: lazy AsyncSqliteSaver twin graphs
# ---------------------------------------------------------------------------


def test_chat_module_exports_lazy_async_graph_factory():
    """v0.7.192: deeper_notebook.graphs.chat must export
    `get_async_graph` — the lazy factory that returns the
    AsyncSqliteSaver-backed twin. The lazy pattern is required
    because aiosqlite.connect() captures the event loop at
    construct time, which doesn't exist at module load."""
    from deeper_notebook.graphs import chat
    assert hasattr(chat, "get_async_graph"), (
        "v0.7.192 regression: get_async_graph factory is gone. "
        "Streaming/ainvoke paths will fail with NotImplementedError "
        "against the sync SqliteSaver in newer langgraph."
    )
    # The legacy sync graph must still exist for back-compat with
    # `asyncio.to_thread(graph.get_state, ...)` callers.
    assert hasattr(chat, "graph")


def test_source_chat_module_exports_lazy_async_graph_factory():
    """v0.7.192: same pin for source_chat."""
    from deeper_notebook.graphs import source_chat
    assert hasattr(source_chat, "get_async_source_chat_graph")
    assert hasattr(source_chat, "source_chat_graph")


def test_chat_router_uses_async_graph_for_ainvoke_and_astream():
    """v0.7.192: api.routers.chat must call get_async_graph() before
    every ainvoke() / astream_events() — those are the async write
    paths that LangGraph internally routes through aget_tuple()."""
    src = _read_source("api/routers/chat.py")
    # The import.
    assert "from deeper_notebook.graphs.chat import get_async_graph" in src, (
        "v0.7.192 regression: chat router no longer imports the "
        "lazy async-graph factory. Streaming/ainvoke calls will hit "
        "the sync SqliteSaver and raise NotImplementedError."
    )
    # And it's actually called before the ainvoke / astream_events.
    assert "_chat_graph_async = await get_async_graph()" in src
    # Both write call sites use the local variable.
    assert "_chat_graph_async.ainvoke(" in src
    assert "_chat_graph_async.astream_events(" in src


def test_source_chat_router_uses_async_graph_for_astream():
    """v0.7.192: same pin for source_chat router."""
    src = _read_source("api/routers/source_chat.py")
    assert (
        "from deeper_notebook.graphs.source_chat import get_async_source_chat_graph"
        in src
    )
    assert "_source_chat_graph_async = await get_async_source_chat_graph()" in src
    assert "_source_chat_graph_async.astream_events(" in src


# ---------------------------------------------------------------------------
# Bug 2: llama-cpp[server] extras
# ---------------------------------------------------------------------------


def test_desktop_requirements_pins_llama_cpp_server_extra():
    """v0.7.192: desktop/requirements.txt must include the [server]
    extra on llama-cpp-python. Without it, the bundled venv ships
    `llama_cpp.server.__main__` but missing starlette_context →
    every `python -m llama_cpp.server` spawn dies at import time
    and the local llamacpp_embed + llamacpp_chat servers are dead."""
    src = _read_source("desktop/requirements.txt")
    assert "llama-cpp-python[server]" in src, (
        "v0.7.192 regression: desktop/requirements.txt no longer "
        "pins the [server] extra on llama-cpp-python. Bundled venv "
        "will install llama_cpp.server's entry point but miss its "
        "starlette-context + sse-starlette + pydantic-settings + "
        "PyYAML deps — local llamacpp servers will crash at import."
    )


def test_desktop_lockfile_includes_starlette_context():
    """v0.7.192: after the [server] extra was added, the lockfile
    regen must include starlette-context (the most-visible casualty).
    Forward-guard against someone editing requirements.txt without
    re-running `make build-mac-lock`."""
    lock = _read_source("desktop/requirements.lock")
    assert "starlette-context==" in lock, (
        "v0.7.192 regression: starlette-context missing from "
        "desktop/requirements.lock. Bundled venv will crash llama_cpp.server "
        "at import. Run `make build-mac-lock` after editing "
        "requirements.txt."
    )
    # And the other 3 server-extra deps too.
    for dep in ("sse-starlette==", "pydantic-settings==", "pyyaml=="):
        assert dep in lock, f"v0.7.192 regression: {dep} gone from lockfile."
