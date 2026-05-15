import asyncio
import os
import sqlite3
from typing import Annotated, Optional

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
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content


# v0.7.11 — Message-history cap for the chat graph.
#
# Chat sessions persist their message list across turns via LangGraph's
# SqliteSaver checkpointer, and the `add_messages` reducer is append-only:
# every prior turn lives in `state["messages"]` and is concatenated into
# the prompt at line 33 (`payload = [SystemMessage(...)] + state["messages"]`).
# After a 30-turn conversation the history alone can be 30+ KB ≈ 7.5k+
# tokens, which combined with the 8192-token `max_tokens` output
# reservation already overflows a 16k-context local server (v0.7.8 default)
# before the system prompt is even counted.
#
# Default 12_000 chars (~3,000 tokens) keeps the worst case fitting
# comfortably inside a 16k context with an 8192-token output reservation
# and a ~1500-token system prompt (which carries the notebook context).
# Users on bigger context windows can raise it via env var.
#
# We always keep the most-recent message (the current user turn — dropping
# it would be nonsensical) and add a system-style marker so the model
# sees that earlier conversation was elided rather than silently lost.
_CHAT_HISTORY_CHAR_CAP_DEFAULT = 12_000
_HISTORY_TRUNCATION_MARKER = (
    "[Earlier conversation turns were elided to fit the model's context "
    "budget. Resume the conversation from the messages that follow.]"
)


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


def _msg_char_len(msg) -> int:
    """Approximate the prompt-character footprint of one message.

    Handles both langchain BaseMessage objects (with .content) and
    plain dicts/strings defensively — the chat graph receives whatever
    the router or checkpoint store hands it.
    """
    if hasattr(msg, "content"):
        c = msg.content
    elif isinstance(msg, dict):
        c = msg.get("content", "")
    else:
        c = msg
    if isinstance(c, str):
        return len(c)
    # Multi-modal content lists / other shapes: stringify defensively
    return len(str(c))


def _trim_message_history(messages: list) -> list:
    """Drop oldest messages until the total fits under the char cap.

    Always preserves the most-recent message (current user turn).
    Prepends a SystemMessage marker when truncation actually occurs,
    so the model knows context was elided and won't hallucinate a
    nonexistent earlier exchange.
    """
    if not messages:
        return messages
    cap = _env_int(
        "ONP_CHAT_HISTORY_CHAR_CAP",
        _CHAT_HISTORY_CHAR_CAP_DEFAULT,
        minimum=500,
    )
    total = sum(_msg_char_len(m) for m in messages)
    if total <= cap:
        return messages

    # Walk from the end (most recent), keep messages while the running
    # total stays under the cap. Always include the last message — it's
    # the current user turn; dropping it would break the conversation.
    kept: list = []
    running = 0
    for m in reversed(messages):
        mlen = _msg_char_len(m)
        if not kept:
            # Always keep the most recent message, even if it alone exceeds
            # the cap (truncation of a single oversize message is a
            # separate concern handled elsewhere).
            kept.append(m)
            running += mlen
            continue
        if running + mlen > cap:
            break
        kept.append(m)
        running += mlen
    kept.reverse()
    dropped = len(messages) - len(kept)
    # Only emit warning + marker if we actually dropped messages. A
    # single oversize current-turn message that triggers the "always
    # keep last" path isn't a history truncation — it's just a fat
    # message, handled separately by per-message caps elsewhere.
    if dropped == 0:
        return kept
    logger.warning(
        f"Chat history truncated: kept {len(kept)}/{len(messages)} messages "
        f"(~{running}/{total} chars; cap={cap}). "
        f"Set ONP_CHAT_HISTORY_CHAR_CAP to raise."
    )
    return [SystemMessage(content=_HISTORY_TRUNCATION_MARKER)] + kept


class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]
    notebook: Optional[Notebook]
    context: Optional[str]
    context_config: Optional[dict]
    model_override: Optional[str]


def call_model_with_messages(state: ThreadState, config: RunnableConfig) -> dict:
    try:
        system_prompt = Prompter(prompt_template="chat/system").render(data=state)  # type: ignore[arg-type]
        # v0.7.11 — trim accumulated message history before building the
        # LLM payload so a long-running session doesn't overflow a
        # 16k-context local server. See `_trim_message_history` docstring
        # for rationale.
        history = _trim_message_history(state.get("messages", []))
        payload = [SystemMessage(content=system_prompt)] + history
        model_id = config.get("configurable", {}).get("model_id") or state.get(
            "model_override"
        )

        # Handle async model provisioning from sync context
        def run_in_new_loop():
            """Run the async function in a new event loop"""
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(
                    provision_langchain_model(
                        str(payload), model_id, "chat", max_tokens=8192
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
                    model_id,
                    "chat",
                    max_tokens=8192,
                )
            )

        ai_message = model.invoke(payload)

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


conn = sqlite3.connect(
    LANGGRAPH_CHECKPOINT_FILE,
    check_same_thread=False,
)
memory = SqliteSaver(conn)

agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)
graph = agent_state.compile(checkpointer=memory)
