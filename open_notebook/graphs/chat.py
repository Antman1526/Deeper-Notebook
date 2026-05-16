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
        model = await provision_langchain_model(
            content_for_sizing, model_id, "chat", max_tokens=8192
        )

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
graph = agent_state.compile(checkpointer=memory)
