import os
from typing import Annotated, Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

# v0.7.192 — See chat.py for the SqliteSaver / AsyncSqliteSaver split
# rationale. Same pattern applied here.
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger
from typing_extensions import TypedDict

from deeper_notebook.ai.provision import (
    provision_langchain_chat_model,
    provision_langchain_model,
)
from deeper_notebook.config import LANGGRAPH_CHECKPOINT_FILE
from deeper_notebook.domain.notebook import Source, SourceInsight
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import DeeperNotebookError
from deeper_notebook.utils import clean_thinking_content
from deeper_notebook.utils.context_builder import ContextBuilder
from deeper_notebook.utils.error_classifier import classify_error
from deeper_notebook.utils.message_history import trim_message_history
from deeper_notebook.utils.sqlite_checkpoint import get_checkpoint_connection
from deeper_notebook.utils.text_utils import extract_text_content

# v0.7.12 — context-budget caps for the source-chat formatter.
#
# `_format_source_context` previously had ONE cap (source full_text @
# 5000 chars) and zero caps on the insight side. A source typically
# accrues 5-20 insights from transformations, each insight's `content`
# field carrying 500-2000 chars of LLM-generated summary. With no per-
# insight cap and no max-insight-count cap, the formatted_context could
# easily reach 30 KB ≈ 7,500 tokens for a heavily-transformed source.
#
# Combined with the hardcoded `max_tokens=8192` output reservation in
# the LLM call (lines 145, 169), the 16k-context local server (v0.7.8
# default) is overwhelmed: 8,192 (output) + 7,500 (insights) + 1,250
# (source full_text) + ~500 (system template) = 17,442 — over budget
# before the user's message history is even added.
#
# Defaults sized for v0.7.8's 16k chat server: total formatted_context
# stays under ~3,500 tokens (~14 KB), leaving comfortable room for
# the system prompt, message history (v0.7.11 cap), and the 8192-token
# output reservation. Capable-hardware users with bigger context
# windows can raise any of the three knobs independently.
_SOURCE_CHAT_SOURCE_CHAR_CAP_DEFAULT = 4_000
_SOURCE_CHAT_INSIGHT_CHAR_CAP_DEFAULT = 1_000
_SOURCE_CHAT_MAX_INSIGHTS_DEFAULT = 10
_SOURCE_TRUNCATION_MARKER = "\n...[truncated for context budget]"


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = resolve_env(name)
    if raw is None:
        return default
    try:
        val = int(raw)
        if val < minimum:
            logger.warning(
                f"{name}={raw} is below minimum {minimum}; using default {default}"
            )
            return default
        return val
    except ValueError:
        logger.warning(f"{name}={raw!r} is not an int; using default {default}")
        return default


def _cap_text(text: str, cap: int) -> str:
    """Truncate a string to `cap` chars with a visible marker."""
    if len(text) <= cap:
        return text
    return text[:cap] + _SOURCE_TRUNCATION_MARKER


class SourceChatState(TypedDict):
    messages: Annotated[list, add_messages]
    source_id: str
    source: Optional[Source]
    insights: Optional[list[SourceInsight]]
    context: Optional[str]
    model_override: Optional[str]
    context_indicators: Optional[dict[str, list[str]]]
    # v0.8.16 — MCP tool-call payloads from this turn, surfaced via
    # the source-chat router so the same v0.8.1 Item 3 + v0.8.13
    # citation pill popovers work in source chat. None when no MCP
    # tools fired (no enabled servers, or model can't tool-call).
    mcp_tool_calls: Optional[list[dict]]
    # v0.8.44 — per-request MCP server disable list (parity with
    # notebook chat's `disabled_mcp_servers` from v0.8.42). The
    # source-chat router writes this onto the LangGraph state from
    # the request body; the node passes it to
    # `bind_mcp_and_run_tool_loop` so the same "load only what I
    # need" affordance works on source-focused conversations.
    disabled_mcp_servers: Optional[list[str]]


async def call_model_with_source_context(
    state: SourceChatState, config: RunnableConfig
) -> dict:
    """
    Main function that builds source context and calls the model.

    v0.7.37 — native async LangGraph node. Replaces the previous
    sync wrapper that used `concurrent.futures.ThreadPoolExecutor` +
    `asyncio.new_event_loop()` to bridge into async. See chat.py's
    rewrite docstring for full rationale.

    1. Uses ContextBuilder to build source-specific context
    2. Applies the source_chat Jinja2 prompt template
    3. Handles model provisioning with override support
    4. Tracks context indicators for referenced insights/content
    """
    try:
        return await _call_model_with_source_context_inner(state, config)
    except DeeperNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


async def _call_model_with_source_context_inner(
    state: SourceChatState, config: RunnableConfig
) -> dict:
    source_id = state.get("source_id")
    if not source_id:
        raise ValueError("source_id is required in state")

    # v0.7.37 — direct await replaces the previous ThreadPoolExecutor
    # + new_event_loop bridge. ContextBuilder.build() is already async;
    # the bridge existed only because the node was sync.
    context_builder = ContextBuilder(
        source_id=source_id,
        include_insights=True,
        include_notes=False,  # Focus on source-specific content
        max_tokens=50000,  # Reasonable limit for source context
    )
    context_data = await context_builder.build()

    # Extract source and insights from context
    source = None
    insights = []
    context_indicators: dict[str, list[str | None]] = {
        "sources": [],
        "insights": [],
        "notes": [],
    }

    if context_data.get("sources"):
        source_info = context_data["sources"][0]  # First source
        source = Source(**source_info) if isinstance(source_info, dict) else source_info
        context_indicators["sources"].append(source.id)

    if context_data.get("insights"):
        for insight_data in context_data["insights"]:
            insight = (
                SourceInsight(**insight_data)
                if isinstance(insight_data, dict)
                else insight_data
            )
            insights.append(insight)
            context_indicators["insights"].append(insight.id)

    # Format context for the prompt
    formatted_context = _format_source_context(context_data)

    # Build prompt data for the template
    # v0.7.78 — recall memory facts/preferences for source-chat too. Same
    # READ path as v0.7.71 in chat.py. Source-chat has tighter budget
    # (system prompt already carries source + insights up to ~3.5k tokens)
    # but tone-and-preference hints are still useful — the template emphasizes
    # "stay focused on the source; only weave memory in when directly
    # relevant". Failure is silent — recall_recent_memory returns empty on
    # missing tables (fresh DB, upstream non-desktop build).
    # v0.7.84 — uses the orchestrator (auto recency vs semantic). Pass
    # the latest user turn as the query for the semantic path.
    from deeper_notebook.utils.memory_recall import (
        recall_memory,
        render_memory_block,
    )

    last_user_text = ""
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", None) == "human":
            last_user_text = extract_text_content(m.content)
            break
    memory = await recall_memory(query=last_user_text)
    memory_block = render_memory_block(memory)

    prompt_data = {
        "source": source.model_dump() if source else None,
        "insights": [insight.model_dump() for insight in insights] if insights else [],
        "context": formatted_context,
        "context_indicators": context_indicators,
        "memory_block": memory_block,
    }

    # Apply the source_chat prompt template
    system_prompt = Prompter(prompt_template="source_chat/system").render(
        data=prompt_data
    )
    # v0.7.13 — trim message history before building payload. Source-chat
    # has a smaller default history budget (8_000 vs chat.py's 12_000)
    # because the system prompt already carries up to ~3.5k tokens of
    # source + insight context (v0.7.12 caps), leaving less headroom in
    # a 16k-context local server.
    history = trim_message_history(
        state.get("messages", []),
        env_var_name="DEEPER_NOTEBOOK_SOURCE_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=8_000,
    )
    payload = [SystemMessage(content=system_prompt)] + history

    # v0.7.37 — direct await; no thread bridge.
    # v0.7.65 — size against actual message text, not str(payload). See
    # chat.py for the same fix; same root cause (wrapper noise in
    # repr(list_of_Message) overcounted the context-budget tokens).
    content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)
    # v0.8.66 (audit A-M1) — route the NO-OVERRIDE path through
    # provision_langchain_chat_model so source-chat (the highest-PII surface —
    # raw ~4000-char source text) gets the SAME smart-router AND fail-closed
    # privacy gate as notebook chat. Previously this always called
    # provision_langchain_model directly, bypassing both. An explicit model
    # pick still goes direct (the user chose that specific model).
    _explicit_model = config.get("configurable", {}).get("model_id") or state.get(
        "model_override"
    )
    # v0.8.68 — offline-fallback info from the provisioning gate (parity
    # with chat.py). Empty dict when no substitution happened; returned in
    # the node result so the SSE stream can drive the offline pill.
    offline_fallback_out: dict = {}
    # v0.8.68 — smart-router decision (parity with chat.py / v0.8.1).
    # Source chat routed through provision_langchain_chat_model since
    # v0.8.66 but never captured selection_out, so the local/cloud badge
    # ChatPanel already renders stayed permanently blank on this surface.
    selection_out: dict = {}
    if _explicit_model:
        model = await provision_langchain_model(
            content_for_sizing,
            _explicit_model,
            "chat",
            fallback_out=offline_fallback_out,
            max_tokens=8192,
        )
    else:
        model = await provision_langchain_chat_model(
            content_for_sizing,
            selection_out=selection_out,
            max_tokens=8192,
            fallback_out=offline_fallback_out,
            privacy_gate_bypass=bool(state.get("bypass_privacy_gate")),
        )

    # v0.8.16 — bind MCP tools + run the v0.8.9 in-node tool loop so
    # source-chat gets the same MCP capabilities as notebook chat.
    # Pre-v0.8.16 source-chat called model.ainvoke directly and any
    # registered MCP server was invisible — operators got no MCP
    # behaviour on the source-chat surface. Both graphs now share
    # `bind_mcp_and_run_tool_loop` from chat.py.
    from deeper_notebook.graphs.chat import bind_mcp_and_run_tool_loop

    # v0.8.44 — thread the per-request MCP disable list into the
    # source-chat tool loop (parity with notebook chat's v0.8.42).
    # v0.8.68 — mid-turn offline retry, same semantics as chat.py: a
    # network-classified failure on a non-fallback turn flips the shared
    # network state and retries ONCE with the gated (now local) model.
    try:
        ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(
            model,
            payload,
            exclude_server_names=state.get("disabled_mcp_servers") or None,
        )
    except Exception as e:
        from deeper_notebook.exceptions import NetworkError
        from deeper_notebook.health.network import report_network_failure

        error_class, _ = classify_error(e)
        already_local = bool(offline_fallback_out.get("offline_fallback"))
        if error_class is not NetworkError or already_local:
            raise
        report_network_failure()
        logger.warning(
            "v0.8.68 — source-chat cloud call failed mid-turn with a network "
            "error; retrying once on the local fallback model"
        )
        retry_fallback: dict = {}
        model = await provision_langchain_model(
            content_for_sizing,
            _explicit_model,
            "chat",
            fallback_out=retry_fallback,
            max_tokens=8192,
        )
        if not retry_fallback.get("offline_fallback"):
            raise  # gate didn't substitute (no local model) — original error stands
        offline_fallback_out.update(retry_fallback)
        ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(
            model,
            payload,
            exclude_server_names=state.get("disabled_mcp_servers") or None,
        )

    # Clean thinking content from AI response (e.g., <think>...</think> tags)
    content = extract_text_content(ai_message.content)
    cleaned_content = clean_thinking_content(content)
    cleaned_message = ai_message.model_copy(update={"content": cleaned_content})

    # Update state with context information
    return {
        "messages": cleaned_message,
        "source": source,
        "insights": insights,
        "context": formatted_context,
        "context_indicators": context_indicators,
        # v0.8.16 — surface MCP captures so the source-chat router can
        # include them in the SSE stream (same pipeline as v0.8.1 #3
        # for notebook chat). None when no MCP calls fired this turn.
        "mcp_tool_calls": mcp_captures if mcp_captures else None,
        # v0.8.68 — offline-fallback info (None when no substitution).
        "offline_fallback": offline_fallback_out or None,
        # v0.8.68 — smart-router decision for the local/cloud badge
        # (None when smart routing didn't run / explicit model pick).
        "selected_provider": selection_out.get("selected_provider"),
        "selected_model_id": selection_out.get("selected_model_id"),
    }


def _format_source_context(context_data: dict) -> str:
    """
    Format the context data into a readable string for the prompt.

    v0.7.12 — applies env-configurable caps so the formatted output
    stays inside a 16k-context local server's budget. See the
    module-level _SOURCE_CHAT_* constants for rationale.

    Args:
        context_data: Context data from ContextBuilder

    Returns:
        Formatted context string
    """
    source_cap = _env_int(
        "DEEPER_NOTEBOOK_SOURCE_CHAT_SOURCE_CHAR_CAP",
        _SOURCE_CHAT_SOURCE_CHAR_CAP_DEFAULT,
        minimum=500,
    )
    insight_cap = _env_int(
        "DEEPER_NOTEBOOK_SOURCE_CHAT_INSIGHT_CHAR_CAP",
        _SOURCE_CHAT_INSIGHT_CHAR_CAP_DEFAULT,
        minimum=200,
    )
    max_insights = _env_int(
        "DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS",
        _SOURCE_CHAT_MAX_INSIGHTS_DEFAULT,
        minimum=1,
    )

    context_parts = []

    # Add source information
    if context_data.get("sources"):
        context_parts.append("## SOURCE CONTENT")
        for source in context_data["sources"]:
            if isinstance(source, dict):
                context_parts.append(f"**Source ID:** {source.get('id', 'Unknown')}")
                context_parts.append(f"**Title:** {source.get('title', 'No title')}")
                if source.get("full_text"):
                    full_text = _cap_text(source["full_text"], source_cap)
                    context_parts.append(f"**Content:**\n{full_text}")
                context_parts.append("")  # Empty line for separation

    # Add insights — both count- and per-content-capped to keep the
    # formatted_context inside the budget even when a source has
    # accumulated dozens of insights from prior transformations.
    if context_data.get("insights"):
        all_insights = context_data["insights"]
        capped_insights = list(all_insights)[:max_insights]
        dropped_count = len(all_insights) - len(capped_insights)
        context_parts.append("## SOURCE INSIGHTS")
        if dropped_count > 0:
            logger.warning(
                f"Source-chat insights truncated: kept {len(capped_insights)}/"
                f"{len(all_insights)} insights (cap={max_insights}). "
                f"Set DEEPER_NOTEBOOK_SOURCE_CHAT_MAX_INSIGHTS to raise."
            )
            context_parts.append(
                f"_[{dropped_count} additional insights elided for context budget]_"
            )
        for insight in capped_insights:
            if isinstance(insight, dict):
                context_parts.append(f"**Insight ID:** {insight.get('id', 'Unknown')}")
                context_parts.append(
                    f"**Type:** {insight.get('insight_type', 'Unknown')}"
                )
                raw_content = insight.get("content", "No content")
                content_str = (
                    _cap_text(raw_content, insight_cap)
                    if isinstance(raw_content, str)
                    else str(raw_content)
                )
                context_parts.append(f"**Content:** {content_str}")
                context_parts.append("")  # Empty line for separation

    # Add metadata
    if context_data.get("metadata"):
        metadata = context_data["metadata"]
        context_parts.append("## CONTEXT METADATA")
        context_parts.append(f"- Source count: {metadata.get('source_count', 0)}")
        context_parts.append(f"- Insight count: {metadata.get('insight_count', 0)}")
        context_parts.append(f"- Total tokens: {context_data.get('total_tokens', 0)}")
        context_parts.append("")

    return "\n".join(context_parts)


# v0.7.32 — shared WAL-tuned, integrity-checked checkpoint connection.
# Both this module and chat.py target the same DB file; the shared
# helper returns the SAME connection so we don't race two writers.
# See deeper_notebook.utils.sqlite_checkpoint docstring for details.
conn = get_checkpoint_connection(LANGGRAPH_CHECKPOINT_FILE)
memory = SqliteSaver(conn)

# Create the StateGraph
source_chat_state = StateGraph(SourceChatState)
source_chat_state.add_node("source_chat_agent", call_model_with_source_context)
source_chat_state.add_edge(START, "source_chat_agent")
source_chat_state.add_edge("source_chat_agent", END)
# Default `source_chat_graph` keeps SqliteSaver for back-compat with
# every existing sync `.get_state()` call. Streaming endpoints use
# `get_async_source_chat_graph()` (lazy) instead.
source_chat_graph = source_chat_state.compile(checkpointer=memory)


# v0.7.192 — Lazy async-graph initializer. See deeper_notebook/graphs/chat.py
# for the full rationale on the lazy/threading-lock pattern (aiosqlite
# captures the event loop at construct time, so we can't build at
# module load).
import threading

import aiosqlite

_async_source_chat_graph: "object | None" = None
_async_source_chat_graph_lock = threading.Lock()
# v0.7.211 — same connection-handle pattern as chat.py for clean
# shutdown. See chat.py:close_async_graph for rationale.
_async_source_chat_aio_conn: "object | None" = None


async def get_async_source_chat_graph():
    """Return the AsyncSqliteSaver-backed twin of `source_chat_graph`,
    lazily constructed on first call."""
    global _async_source_chat_graph, _async_source_chat_aio_conn
    if _async_source_chat_graph is not None:
        return _async_source_chat_graph
    with _async_source_chat_graph_lock:
        if _async_source_chat_graph is not None:
            return _async_source_chat_graph
        aio_conn = await aiosqlite.connect(LANGGRAPH_CHECKPOINT_FILE)
        async_memory = AsyncSqliteSaver(aio_conn)
        _async_source_chat_graph = source_chat_state.compile(
            checkpointer=async_memory,
        )
        _async_source_chat_aio_conn = aio_conn
    return _async_source_chat_graph


async def close_async_source_chat_graph() -> None:
    """v0.7.211 — Tear down the AsyncSqliteSaver connection on
    shutdown. Same idempotent + safe-on-never-built pattern as
    chat.py:close_async_graph."""
    global _async_source_chat_graph, _async_source_chat_aio_conn
    conn = _async_source_chat_aio_conn
    _async_source_chat_aio_conn = None
    _async_source_chat_graph = None
    if conn is None:
        return
    try:
        await conn.close()  # type: ignore[attr-defined]
    except Exception:
        pass
