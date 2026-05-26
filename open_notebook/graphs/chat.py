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
    # v0.8.1 — Smart-router decision plumbed back to /chat/execute so the
    # HTTP response can include `selected_provider` ("local"/"cloud"). The
    # node sets this when OPEN_NOTEBOOK_AUTO_ROUTE_CHAT is on; otherwise
    # it stays None and the response field is omitted/None.
    selected_provider: Optional[str]
    selected_model_id: Optional[str]
    # v0.8.1 Item 3 — list of MCP tool-call records made during this
    # turn. Reset per turn (call_model_with_messages clears it before
    # binding tools). The /chat router includes this in
    # ExecuteChatResponse so the frontend can render citation pill
    # popovers with the real search query + result text.
    mcp_tool_calls: Optional[list]


def _json_schema_to_pydantic_model(
    tool_name: str, schema: dict,
):
    """v0.8.11 — Build a Pydantic model from a JSON Schema dict.

    Minimal converter covering the common MCP shapes:
      {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    Field types: string / integer / number / boolean / array / object →
    Python primitives. Anything unrecognised falls through to `Any`.
    Required fields are mandatory; the rest default to None.

    The resulting model class name is `MCPArgs_<tool_name>` (sanitised)
    so it shows up clearly in tracebacks and LangChain debug output.
    """
    from typing import Any, Optional
    from pydantic import create_model, Field

    type_map = {
        "string": str, "integer": int, "number": float,
        "boolean": bool, "array": list, "object": dict,
    }

    props = (schema or {}).get("properties", {}) or {}
    required = set((schema or {}).get("required", []) or [])

    fields: dict[str, tuple] = {}
    for name, spec in props.items():
        py_type = type_map.get(spec.get("type"), Any)
        description = spec.get("description", "")
        if name in required:
            fields[name] = (py_type, Field(..., description=description))
        else:
            fields[name] = (Optional[py_type], Field(None, description=description))

    safe_name = "".join(c if c.isalnum() else "_" for c in tool_name)
    if not fields:
        # No-arg tool — pydantic.create_model with no fields is fine
        # but LangChain prefers a non-empty schema. Pydantic rejects
        # leading-underscore field names, so use a normal name marked
        # excluded from serialisation.
        fields = {"unused": (Optional[str], Field(None, exclude=True))}

    return create_model(f"MCPArgs_{safe_name}", **fields)


async def _resolve_chat_tools(
    *, force_servers=None, captures=None,
    force_tool_names=None, force_tools_full=None,
) -> list:
    """Phase 2 — when at least one MCP server is enabled in the
    registry, expose its tools to the chat LLM.

    v0.8.10 CRITICAL: pre-v0.8.10 this hardcoded `mcp_search` → MCP
    tool `web_search` and `mcp_fetch` → `fetch_url`. Most MCP servers
    in the wild expose different names — gbrain (the integration
    documented in v0.8.2 Item B) ships `search`, `think`,
    `find_trajectory`, etc. So registering gbrain would result in
    `tool web_search not found` errors every time the LLM tried to
    use it. Fix: discover the server's tools via
    `client.list_tool_names()` and wrap each one as `mcp_<name>`. The
    LLM sees what the server actually offers; arg dispatch is generic
    via `{name, args}` rather than name-specific schemas (richer
    schemas can come in v0.9 via `list_tools()` instead of just names).

    v0.8.1 Item 3 — `captures` is an optional list[dict] accumulator.
    When provided, each tool closure appends a record
    {index, name, args, text} on completion so callers can surface
    the real search query + result text in citation pill popovers.
    text is truncated to 4000 chars to keep response sizes sane.

    `force_tool_names` is a test hook so unit tests can skip the
    network discovery and pin the bound names.
    """
    from langchain_core.tools import StructuredTool
    from open_notebook.mcp.client import MCPClient
    from open_notebook.mcp.registry import list_enabled_servers

    servers = force_servers if force_servers is not None else await list_enabled_servers()
    if not servers:
        return []
    server = servers[0]
    client = MCPClient(url=server["url"])

    # v0.8.11 — Discover the server's FULL tool surface (name +
    # description + input_schema) so we can build StructuredTools
    # with proper args_schema. Pre-v0.8.11 we only knew names; the
    # LLM had to guess what args to pass via the no-schema fallback
    # (`input: str`). With real schemas, `bind_tools` sends the LLM
    # the real arg names + types, dramatically reducing tool-call
    # malformatting.
    #
    # Backward compat: `force_tool_names` still works (just gives a
    # name list; we synthesise empty schemas). `force_tools_full`
    # is the new test hook for cases that want to pin the schemas.
    if force_tools_full is not None:
        available = list(force_tools_full)
    elif force_tool_names is not None:
        # Old test hook — synthesise minimal-shape entries so tests
        # written against the v0.8.10 API keep passing.
        available = [
            {"name": n, "description": "", "input_schema": {"type": "object", "properties": {}}}
            for n in force_tool_names
        ]
    else:
        try:
            available = await client.list_tools_full()
        except Exception:
            available = []

    if not available:
        return []

    def _make_tool(remote_name: str, description: str, schema: dict):
        """Build a StructuredTool that calls the server's `remote_name`.

        Closure captures `remote_name` per iteration (not the loop
        variable) so the bound tool calls the right MCP tool.

        v0.8.10 retained behaviour: the coroutine still accepts BOTH
        positional-dict and kwargs dispatch styles defensively (some
        LangChain code paths still drop into either). With a proper
        args_schema bound, kwargs is the common path.
        """
        async def _invoke(*args, **kwargs) -> str:
            if "input" in kwargs and isinstance(kwargs["input"], dict):
                invocation_args = kwargs["input"]
            elif args and isinstance(args[0], dict):
                invocation_args = args[0]
            else:
                invocation_args = dict(kwargs)
            result = await client.call_tool(remote_name, invocation_args)
            text = result.get("text") or "(no result)"
            if captures is not None:
                captures.append({
                    "index": len(captures) + 1,
                    "name": remote_name,
                    "args": invocation_args,
                    "text": text[:4000],
                })
            return text

        args_model = _json_schema_to_pydantic_model(remote_name, schema)
        return StructuredTool.from_function(
            coroutine=_invoke,
            name=f"mcp_{remote_name}",
            description=(
                description
                or f"Call the MCP server's `{remote_name}` tool. Use this "
                f"when the user's question depends on information not in "
                f"the notebook context."
            ),
            args_schema=args_model,
        )

    return [
        _make_tool(t["name"], t.get("description", ""), t.get("input_schema") or {})
        for t in available
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
        # v0.8.1 — capture smart-router's local/cloud decision via
        # selection_out so the chat router can include `selected_provider`
        # in ExecuteChatResponse. Explicit model_override path bypasses
        # the router entirely (the user picked a specific model), so
        # selection_out stays empty there — `selected_provider` is None.
        selection_out: dict = {}
        if model_id:
            model = await provision_langchain_model(
                content_for_sizing, model_id, "chat", max_tokens=8192
            )
        else:
            model = await provision_langchain_chat_model(
                content_for_sizing,
                selection_out=selection_out,
                max_tokens=8192,
            )

        # v0.8.0 Phase 2 Task 8 — bind MCP tools when any server is
        # enabled. We resolve tools each turn so the list reflects the
        # current registry state without requiring a server restart.
        # Wrapped in try/except because local-only providers (llama-cpp,
        # Ollama without tool support, etc.) raise NotImplementedError or
        # AttributeError on .bind_tools(); the chat still works normally
        # without MCP when binding fails.
        #
        # v0.8.1 Item 3 — accumulator for MCP tool-call payloads in this
        # turn. Reset per turn so subsequent turns don't see stale entries.
        mcp_captures: list = []
        mcp_tools: list = []
        try:
            mcp_tools = await _resolve_chat_tools(captures=mcp_captures)
            if mcp_tools:
                model = model.bind_tools(mcp_tools)
        except Exception:
            # v0.8.0 — local providers may not implement bind_tools; degrade gracefully
            mcp_tools = []

        ai_message = await model.ainvoke(payload)

        # v0.8.9 CRITICAL — in-node tool execution loop. Pre-v0.8.9 the
        # chat graph was START → agent → END with no ToolNode, so
        # `bind_tools(mcp_tools)` made the tools VISIBLE to the LLM
        # (schemas in the system prompt) but no code ever executed any
        # `tool_calls` the LLM emitted. mcp_captures stayed empty;
        # [mcp:N] markers in the LLM's text were pure hallucination;
        # the v0.8.1 Item 3 pill-popover payload pipeline never fired.
        #
        # Fix: loop here until the model stops emitting tool_calls or
        # we hit MAX_TOOL_ITERATIONS (safety bound against runaway).
        # Keeps the graph topology unchanged — no separate ToolNode —
        # so /chat/execute's existing message-list extraction logic
        # keeps working without surgery.
        MAX_TOOL_ITERATIONS = 4
        tool_lookup = {t.name: t for t in mcp_tools} if mcp_tools else {}
        tool_iters = 0
        # The history list we accumulate so the model sees its own
        # earlier tool_call AI messages + the tool results on each
        # re-invocation. The very first model.ainvoke already saw
        # `payload`, so we start the history there.
        running_payload = list(payload)
        running_payload.append(ai_message)
        while (
            tool_lookup
            and tool_iters < MAX_TOOL_ITERATIONS
            and getattr(ai_message, "tool_calls", None)
        ):
            tool_iters += 1
            from langchain_core.messages import ToolMessage
            tool_msgs: list = []
            for call in ai_message.tool_calls:
                # langchain tool_call shape: {"name", "args", "id"}
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
                tool = tool_lookup.get(name)
                if tool is None:
                    # Model hallucinated a tool name we didn't bind.
                    # Reply with an error so the model can recover
                    # rather than spinning on the same call.
                    tool_msgs.append(ToolMessage(
                        content=f"Tool {name!r} is not available.",
                        tool_call_id=call_id,
                    ))
                    continue
                try:
                    # v0.8.10 — call the coroutine directly with **args
                    # rather than going through Tool.ainvoke(args). The
                    # latter requires an args_schema; without one, the
                    # dict gets bound to a single `input` arg and the
                    # closure receives empty kwargs. The model's args
                    # dict already matches the MCP call shape, so
                    # direct dispatch is both correct and cheaper.
                    safe_args = args if isinstance(args, dict) else {}
                    result = await tool.coroutine(**safe_args)
                except Exception as tool_exc:
                    # Tool failure → ToolMessage with the error. The
                    # model can decide to apologise to the user or
                    # try a different approach next iteration.
                    result = f"Tool {name!r} failed: {tool_exc}"
                tool_msgs.append(ToolMessage(
                    content=str(result),
                    tool_call_id=call_id,
                ))
            running_payload.extend(tool_msgs)
            ai_message = await model.ainvoke(running_payload)
            running_payload.append(ai_message)

        # Clean thinking content from AI response (e.g., <think>...</think> tags)
        content = extract_text_content(ai_message.content)
        cleaned_content = clean_thinking_content(content)
        cleaned_message = ai_message.model_copy(update={"content": cleaned_content})

        # v0.8.1 — return the routing decision alongside the new message
        # so the /chat/execute router (api/routers/chat.py) can surface
        # `selected_provider` in ExecuteChatResponse. Keys are absent
        # when smart routing didn't run (model_override path or
        # OPEN_NOTEBOOK_AUTO_ROUTE_CHAT off) — callers treat absence as
        # None.
        # v0.8.1 Item 3 — include MCP tool-call captures. None when no
        # MCP calls were made this turn (empty captures list → None).
        return {
            "messages": cleaned_message,
            "selected_provider": selection_out.get("selected_provider"),
            "selected_model_id": selection_out.get("selected_model_id"),
            "mcp_tool_calls": mcp_captures if mcp_captures else None,
        }
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
