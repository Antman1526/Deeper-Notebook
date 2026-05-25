from typing import Annotated, Optional

from ai_prompter import Prompter
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
# v0.7.192 — AsyncSqliteSaver for the streaming/ainvoke path.
# Newer langgraph (≥ 0.6) split sync vs async checkpointers; the old
# SqliteSaver raises NotImplementedError when LangGraph internally
# calls aget_tuple() during astream_events / ainvoke. We keep the
# sync SqliteSaver for the existing `asyncio.to_thread(graph.get_state)`
# read paths and add AsyncSqliteSaver for async writes. Both savers
# share the SAME underlying SQLite file so checkpoint state is
# always consistent — they're just two views over the same DB.
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from open_notebook.ai.provision import (
    provision_langchain_chat_model,
    provision_langchain_model,
)
from open_notebook.config import LANGGRAPH_CHECKPOINT_FILE
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.memory_recall import (
    recall_memory,
    render_memory_block,
)
from open_notebook.utils.message_history import (
    HISTORY_TRUNCATION_MARKER as _HISTORY_TRUNCATION_MARKER,  # re-exported for tests
)
from open_notebook.utils.message_history import (
    msg_char_len as _msg_char_len,  # re-exported for tests
)
from open_notebook.utils.message_history import (
    trim_message_history,
)
from open_notebook.utils.sqlite_checkpoint import get_checkpoint_connection
from open_notebook.utils.text_utils import extract_text_content

# v0.7.11 / v0.7.13 — Message-history cap for the chat graph.
#
# Chat sessions persist their message list across turns via LangGraph's
# SqliteSaver checkpointer, and the `add_messages` reducer is append-only:
# every prior turn lives in `state["messages"]` and would be concatenated
# into the prompt at every call without trimming. v0.7.13 factored the
# logic into open_notebook.utils.message_history so the same protection
# applies to source_chat.py too. The chat-graph-specific env var is
# `ONP_CHAT_HISTORY_CHAR_CAP` (default 12_000 chars ≈ 3,000 tokens).


def _trim_message_history(messages: list) -> list:
    """Chat-graph wrapper around the shared trimmer. Kept as a private
    name for backward compatibility with v0.7.11 tests."""
    return trim_message_history(
        messages,
        env_var_name="ONP_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=12_000,
    )


class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]
    notebook: Optional[Notebook]
    context: Optional[str]
    context_config: Optional[dict]
    model_override: Optional[str]


async def _resolve_chat_tools(*, force_servers=None) -> list:
    """Phase 2 — when at least one MCP server is enabled in the
    registry, expose `mcp_search` + `mcp_fetch` that route to the
    first enabled server. Future: per-server tool surfaces (one
    mcp_* function per server) for richer model decisions."""
    from langchain_core.tools import Tool
    from open_notebook.mcp.client import MCPClient
    from open_notebook.mcp.registry import list_enabled_servers

    servers = force_servers if force_servers is not None else await list_enabled_servers()
    if not servers:
        return []
    server = servers[0]
    client = MCPClient(url=server["url"])

    async def _search(query: str) -> str:
        result = await client.call_tool("web_search", {"query": query})
        return result.get("text") or "(no result)"

    async def _fetch(url: str) -> str:
        result = await client.call_tool("fetch_url", {"url": url})
        return result.get("text") or "(no result)"

    # Tool(name, func, description) — func is positional-required in this
    # version of langchain_core; pass func=None + coroutine for async-only tools.
    return [
        Tool(name="mcp_search", func=None, description="Search the web via MCP",
             coroutine=_search),
        Tool(name="mcp_fetch", func=None, description="Fetch a URL via MCP",
             coroutine=_fetch),
    ]


async def call_model_with_messages(
    state: ThreadState, config: RunnableConfig
) -> dict:
    """Async LangGraph node. v0.7.37 rewrite.

    Previously this was sync and bridged into async via a per-call
    `concurrent.futures.ThreadPoolExecutor` running a fresh
    `asyncio.new_event_loop()`. The bridge was originally needed
    because `provision_langchain_model` is async and the node was
    declared sync. The bridge cost ~30ms/turn, killed httpx/aiohttp
    keepalive pools, and was fragile on exception paths (the new
    loop was closed before pending tasks drained).

    The node is now natively async — LangGraph supports `async def`
    nodes via `graph.ainvoke()` / `graph.astream_events()`. We call
    `provision_langchain_model` directly with `await` and use
    `model.ainvoke()` for the LLM round trip. This is also a
    prerequisite for v0.7.38's token streaming, which uses
    `astream_events` on the compiled graph.
    """
    try:
        # v0.7.71 — pull memory facts + preferences for the system
        # prompt. Companion to v0.7.68 / v0.7.70 (the WRITE path):
        # without recall here, the assistant kept extracting facts
        # every turn but never remembered them across sessions.
        # v0.7.84 — use the orchestrator. Below ~30 rows it does
        # recency (saves an embed round trip); above that it does
        # semantic search against the user's current message and
        # falls back to recency on any failure. Override via
        # ONP_MEMORY_RECALL_MODE = recent | semantic | auto.
        last_user_text = ""
        for m in reversed(state.get("messages", [])):
            if getattr(m, "type", None) == "human":
                last_user_text = extract_text_content(m.content)
                break
        memory = await recall_memory(query=last_user_text)
        memory_block = render_memory_block(memory)
        prompt_data: dict = dict(state)  # type: ignore[arg-type]
        prompt_data["memory_block"] = memory_block
        system_prompt = Prompter(prompt_template="chat/system").render(data=prompt_data)
        # v0.7.11 — trim accumulated message history before building the
        # LLM payload so a long-running session doesn't overflow a
        # 16k-context local server. See `_trim_message_history` docstring
        # for rationale.
        history = _trim_message_history(state.get("messages", []))
        payload = [SystemMessage(content=system_prompt)] + history
        model_id = config.get("configurable", {}).get("model_id") or state.get(
            "model_override"
        )

        # v0.7.65 — size the context against the actual message text
        # only. The previous version passed `str(payload)`, which is
        # Python's `repr` of a list of LangChain Message objects and
        # includes wrapper noise like
        #     [SystemMessage(content='...', additional_kwargs={}, response_metadata={}), ...]
        # That overhead is ~80-120 chars per message; for a long chat
        # session (50 turns) the wrapper alone added ~5k phantom
        # "tokens" to the count provision_langchain_model uses for its
        # 105k large_context cutoff. Net effect: the chat could be
        # routed to the large_context model earlier than intended for
        # purely cosmetic reasons. Now we extract `.content` per
        # message and join — the same text that actually goes to the
        # LLM.
        content_for_sizing = "\n".join(
            extract_text_content(m.content) for m in payload
        )
        # v0.8.0 Phase 3 Task 12 — use smart-routed wrapper when no explicit
        # model_id override is present. When model_id is set (per-request
        # override via configurable or state.model_override) the wrapper is
        # bypassed and the existing explicit-model path in
        # provision_langchain_model runs instead — routing never clobbers a
        # deliberate caller override.
        if model_id:
            model = await provision_langchain_model(
                content_for_sizing, model_id, "chat", max_tokens=8192
            )
        else:
            model = await provision_langchain_chat_model(
                content_for_sizing, max_tokens=8192
            )

        # v0.8.0 Phase 2 Task 8 — bind MCP tools when any server is
        # enabled. We resolve tools each turn so the list reflects the
        # current registry state without requiring a server restart.
        # Wrapped in try/except because local-only providers (llama-cpp,
        # Ollama without tool support, etc.) raise NotImplementedError or
        # AttributeError on .bind_tools(); the chat still works normally
        # without MCP when binding fails.
        try:
            mcp_tools = await _resolve_chat_tools()
            if mcp_tools:
                model = model.bind_tools(mcp_tools)
        except Exception:
            # v0.8.0 — local providers may not implement bind_tools; degrade gracefully
            pass

        ai_message = await model.ainvoke(payload)

        # Clean thinking content from AI response (e.g., <think>...</think> tags)
        content = extract_text_content(ai_message.content)
        cleaned_content = clean_thinking_content(content)
        cleaned_message = ai_message.model_copy(update={"content": cleaned_content})

        return {"messages": cleaned_message}
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


# v0.7.32 — use the shared, WAL-tuned, integrity-checked connection.
# The previous direct sqlite3.connect created a separate connection
# in each graph module and ran without WAL or busy_timeout — concurrent
# chat sessions could hit "database is locked". See the
# open_notebook.utils.sqlite_checkpoint docstring for the full
# rationale.
conn = get_checkpoint_connection(LANGGRAPH_CHECKPOINT_FILE)
memory = SqliteSaver(conn)

agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)
# Default `graph` exposes the SYNC checkpointer for back-compat with
# every existing `chat_graph.get_state(...)` caller (wrapped in
# asyncio.to_thread by the router code).
graph = agent_state.compile(checkpointer=memory)


# v0.7.192 — Lazy async-graph initializer.
#
# Newer langgraph (≥ 0.6) raises NotImplementedError when
# astream_events / ainvoke internally calls aget_tuple() against the
# sync SqliteSaver. The async variant needs AsyncSqliteSaver wrapping
# an aiosqlite connection.
#
# Why lazy instead of constructing at module load:
#
#   `aiosqlite.connect(...)` captures the CURRENT event loop at
#   construct time (it calls asyncio.get_running_loop() in __init__).
#   Module load happens at import time when there's no event loop
#   yet — the .connect() call fails with "no running event loop".
#
#   We can't fall back to "construct in lifespan startup" cleanly
#   either, because the lifespan would have to wire the resulting
#   graph into every router module's import scope. Defer to the
#   first call instead — `get_async_graph()` returns the cached
#   AsyncSqliteSaver-backed graph after lazily constructing it on
#   first use.
#
# Why a threading.Lock rather than an asyncio.Lock: same reason as
# above — asyncio.Lock() needs an event loop at construct time. A
# threading.Lock is loop-agnostic. `await` inside the `with` block
# is fine; the lock prevents two coroutines on the same loop from
# both entering the slow-path simultaneously.
import threading

import aiosqlite

_async_graph: "object | None" = None
_async_graph_lock = threading.Lock()
# v0.7.211 — keep a handle to the aiosqlite connection so
# `close_async_graph()` can close it on shutdown. Previously the
# connection was held only inside the AsyncSqliteSaver wrapper
# with no way to reach it; on `app.shutdown` the file descriptor
# leaked and a background aiosqlite thread stayed alive past the
# lifespan teardown.
_async_aio_conn: "object | None" = None


async def get_async_graph():
    """Return the AsyncSqliteSaver-backed twin of `graph`, lazily
    constructed on first call.

    Same nodes + topology as the sync `graph`; just a different
    persistence backend. Both savers point at the SAME on-disk SQLite
    file (LANGGRAPH_CHECKPOINT_FILE) — checkpoints written through
    one are visible to reads through the other, courtesy of SQLite
    WAL mode (configured in open_notebook.utils.sqlite_checkpoint).
    """
    global _async_graph, _async_aio_conn
    if _async_graph is not None:
        return _async_graph
    with _async_graph_lock:
        if _async_graph is not None:
            return _async_graph
        aio_conn = await aiosqlite.connect(LANGGRAPH_CHECKPOINT_FILE)
        async_memory = AsyncSqliteSaver(aio_conn)
        _async_graph = agent_state.compile(checkpointer=async_memory)
        _async_aio_conn = aio_conn
    return _async_graph


async def close_async_graph() -> None:
    """v0.7.211 — Tear down the AsyncSqliteSaver's aiosqlite
    connection on FastAPI lifespan shutdown.

    Without this the connection (and its background thread) leaks
    past the API process's clean shutdown — harmless on POSIX but
    annoying on Windows where the SQLite file stays locked for the
    next launcher session, and on long-running .app sessions where
    the leaked FD count creeps up over hundreds of relaunches.
    Safe to call multiple times (idempotent) and on a never-
    constructed graph (no-op).
    """
    global _async_graph, _async_aio_conn
    conn = _async_aio_conn
    _async_aio_conn = None
    _async_graph = None
    if conn is None:
        return
    try:
        # aiosqlite's close is an awaitable; mypy is OK with this.
        await conn.close()  # type: ignore[attr-defined]
    except Exception:
        # Never crash shutdown on a checkpoint close failure.
        pass
