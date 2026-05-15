import asyncio
import sqlite3
from typing import Annotated, Optional

from ai_prompter import Prompter
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.config import LANGGRAPH_CHECKPOINT_FILE
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.message_history import (
    HISTORY_TRUNCATION_MARKER as _HISTORY_TRUNCATION_MARKER,  # re-exported for tests
    msg_char_len as _msg_char_len,  # re-exported for tests
    trim_message_history,
)
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
