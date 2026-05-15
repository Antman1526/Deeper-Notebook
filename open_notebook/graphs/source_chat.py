import asyncio
import os
import sqlite3
from typing import Annotated, Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.config import LANGGRAPH_CHECKPOINT_FILE
from open_notebook.domain.notebook import Source, SourceInsight
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.context_builder import ContextBuilder
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.message_history import trim_message_history
from open_notebook.utils.text_utils import extract_text_content


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
    raw = os.environ.get(name)
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
    insights: Optional[List[SourceInsight]]
    context: Optional[str]
    model_override: Optional[str]
    context_indicators: Optional[Dict[str, List[str]]]


def call_model_with_source_context(
    state: SourceChatState, config: RunnableConfig
) -> dict:
    """
    Main function that builds source context and calls the model.

    This function:
    1. Uses ContextBuilder to build source-specific context
    2. Applies the source_chat Jinja2 prompt template
    3. Handles model provisioning with override support
    4. Tracks context indicators for referenced insights/content
    """
    try:
        return _call_model_with_source_context_inner(state, config)
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


def _call_model_with_source_context_inner(
    state: SourceChatState, config: RunnableConfig
) -> dict:
    source_id = state.get("source_id")
    if not source_id:
        raise ValueError("source_id is required in state")

    # Build source context using ContextBuilder (run async code in new loop)
    def build_context():
        """Build context in a new event loop"""
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            context_builder = ContextBuilder(
                source_id=source_id,
                include_insights=True,
                include_notes=False,  # Focus on source-specific content
                max_tokens=50000,  # Reasonable limit for source context
            )
            return new_loop.run_until_complete(context_builder.build())
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    # Get the built context
    try:
        # Try to get the current event loop
        asyncio.get_running_loop()
        # If we're in an event loop, run in a thread with a new loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(build_context)
            context_data = future.result()
    except RuntimeError:
        # No event loop running, safe to create a new one
        context_data = build_context()

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
    prompt_data = {
        "source": source.model_dump() if source else None,
        "insights": [insight.model_dump() for insight in insights] if insights else [],
        "context": formatted_context,
        "context_indicators": context_indicators,
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
        env_var_name="ONP_SOURCE_CHAT_HISTORY_CHAR_CAP",
        default_char_cap=8_000,
    )
    payload = [SystemMessage(content=system_prompt)] + history

    # Handle async model provisioning from sync context
    def run_in_new_loop():
        """Run the async function in a new event loop"""
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(
                provision_langchain_model(
                    str(payload),
                    config.get("configurable", {}).get("model_id")
                    or state.get("model_override"),
                    "chat",
                    max_tokens=8192,
                )
            )
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    try:
        # Try to get the current event loop
        asyncio.get_running_loop()
        # If we're in an event loop, run in a thread with a new loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            model = future.result()
    except RuntimeError:
        # No event loop running, safe to use asyncio.run()
        model = asyncio.run(
            provision_langchain_model(
                str(payload),
                config.get("configurable", {}).get("model_id")
                or state.get("model_override"),
                "chat",
                max_tokens=8192,
            )
        )

    ai_message = model.invoke(payload)

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
    }


def _format_source_context(context_data: Dict) -> str:
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
        "ONP_SOURCE_CHAT_SOURCE_CHAR_CAP",
        _SOURCE_CHAT_SOURCE_CHAR_CAP_DEFAULT,
        minimum=500,
    )
    insight_cap = _env_int(
        "ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP",
        _SOURCE_CHAT_INSIGHT_CHAR_CAP_DEFAULT,
        minimum=200,
    )
    max_insights = _env_int(
        "ONP_SOURCE_CHAT_MAX_INSIGHTS",
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
                f"Set ONP_SOURCE_CHAT_MAX_INSIGHTS to raise."
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


# Create SQLite checkpointer
conn = sqlite3.connect(
    LANGGRAPH_CHECKPOINT_FILE,
    check_same_thread=False,
)
memory = SqliteSaver(conn)

# Create the StateGraph
source_chat_state = StateGraph(SourceChatState)
source_chat_state.add_node("source_chat_agent", call_model_with_source_context)
source_chat_state.add_edge(START, "source_chat_agent")
source_chat_state.add_edge("source_chat_agent", END)
source_chat_graph = source_chat_state.compile(checkpointer=memory)
