import operator
import os
from typing import Annotated, List

from ai_prompter import Prompter
from langchain_core.output_parsers.pydantic import PydanticOutputParser
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import vector_search
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content


# v0.7.9 — Per-result content cap for the Ask graph.
#
# `vector_search` returns up to N results where each result's `matches`
# field is `array::flatten(content)` across all chunks that grouped under
# one source/note/insight. A single hot source can easily contribute
# 10-20 chunks of 500-1500 chars each, so one result can be 10-30 KB and
# 10 results 100-300 KB — which is rendered verbatim into the prompt
# `{{results}}` and shipped to the LLM.
#
# For local-model deployments this is catastrophic. A 16k-context server
# (the v0.7.8 default) is overwhelmed: the input alone consumes most of
# the window, leaving no room for the system prompt + 2000-token answer
# reservation. The failure mode is server-side context overflow, often
# surfaced as opaque 500s mid-stream.
#
# Defaults (per-result 1500 chars, max 10 results) keep the worst case
# at ~15 KB ≈ 3.75k tokens — comfortable headroom in a 16k context with
# room for output + template overhead. Users on bigger context windows
# can raise the cap via env vars without code edits.
_ASK_PER_RESULT_CHAR_CAP_DEFAULT = 1500
_ASK_MAX_RESULTS_DEFAULT = 10
_TRUNCATION_MARKER = "\n[...truncated for context budget...]"


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    """Parse a positive integer from env; fall back to default on garbage."""
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


def _truncate_ask_results(results: list) -> list:
    """Cap result count and per-result content size for local-model safety.

    Mutates a *copy* — leaves the original list (which other code might
    still reference) untouched. Each result's `matches` field, if
    present, is joined and truncated to the char cap with a marker so
    the LLM sees that content was elided rather than silently lost.
    Non-`matches` fields (id, parent_id, title, similarity) are
    untouched — they're tiny and the prompt needs them for citation.
    """
    max_results = _env_int(
        "ONP_ASK_MAX_RESULTS", _ASK_MAX_RESULTS_DEFAULT, minimum=1
    )
    char_cap = _env_int(
        "ONP_ASK_PER_RESULT_CHAR_CAP",
        _ASK_PER_RESULT_CHAR_CAP_DEFAULT,
        minimum=200,
    )
    capped = list(results)[:max_results]
    out = []
    for r in capped:
        if not isinstance(r, dict):
            out.append(r)
            continue
        new_r = dict(r)
        matches = new_r.get("matches")
        # `matches` is array::flatten(content) — usually a list of strings,
        # but defensively also handle a single string.
        if isinstance(matches, list):
            joined = "\n".join(m for m in matches if isinstance(m, str))
        elif isinstance(matches, str):
            joined = matches
        else:
            out.append(new_r)
            continue
        if len(joined) > char_cap:
            joined = joined[:char_cap] + _TRUNCATION_MARKER
        new_r["matches"] = joined
        out.append(new_r)
    return out


class SubGraphState(TypedDict):
    question: str
    term: str
    instructions: str
    results: dict
    answer: str
    ids: list  # Added for provide_answer function


class Search(BaseModel):
    term: str
    instructions: str = Field(
        description="Tell the answeting LLM what information you need extracted from this search"
    )


class Strategy(BaseModel):
    reasoning: str
    searches: List[Search] = Field(
        default_factory=list,
        description="You can add up to five searches to this strategy",
    )


class ThreadState(TypedDict):
    question: str
    strategy: Strategy
    answers: Annotated[list, operator.add]
    final_answer: str


async def call_model_with_messages(state: ThreadState, config: RunnableConfig) -> dict:
    try:
        parser = PydanticOutputParser(pydantic_object=Strategy)
        system_prompt = Prompter(prompt_template="ask/entry", parser=parser).render(  # type: ignore[arg-type]
            data=state  # type: ignore[arg-type]
        )
        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("strategy_model"),
            "tools",
            max_tokens=2000,
            structured=dict(type="json"),
        )
        # model = model.bind_tools(tools)
        # First get the raw response from the model
        ai_message = await model.ainvoke(system_prompt)

        # Clean the thinking content from the response
        message_content = extract_text_content(ai_message.content)
        cleaned_content = clean_thinking_content(message_content)

        # Parse the cleaned JSON content
        strategy = parser.parse(cleaned_content)

        return {"strategy": strategy}
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


async def trigger_queries(state: ThreadState, config: RunnableConfig):
    return [
        Send(
            "provide_answer",
            {
                "question": state["question"],
                "instructions": s.instructions,
                "term": s.term,
                # "type": s.type,
            },
        )
        for s in state["strategy"].searches
    ]


async def provide_answer(state: SubGraphState, config: RunnableConfig) -> dict:
    try:
        payload = state
        # if state["type"] == "text":
        #     results = text_search(state["term"], 10, True, True)
        # else:
        results = await vector_search(state["term"], 10, True, True)
        if len(results) == 0:
            return {"answers": []}
        # v0.7.9 — cap result count and per-result content size before
        # passing into the prompt; protects local 16k-context LLMs from
        # context overflow on hot sources with many chunks. See
        # _truncate_ask_results docstring for rationale.
        results = _truncate_ask_results(results)
        payload["results"] = results
        ids = [r["id"] for r in results]
        payload["ids"] = ids
        system_prompt = Prompter(prompt_template="ask/query_process").render(data=payload)  # type: ignore[arg-type]
        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("answer_model"),
            "tools",
            max_tokens=2000,
        )
        ai_message = await model.ainvoke(system_prompt)
        ai_content = extract_text_content(ai_message.content)
        return {"answers": [clean_thinking_content(ai_content)]}
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


async def write_final_answer(state: ThreadState, config: RunnableConfig) -> dict:
    try:
        system_prompt = Prompter(prompt_template="ask/final_answer").render(data=state)  # type: ignore[arg-type]
        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("final_answer_model"),
            "tools",
            max_tokens=2000,
        )
        ai_message = await model.ainvoke(system_prompt)
        final_content = extract_text_content(ai_message.content)
        return {"final_answer": clean_thinking_content(final_content)}
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_node("provide_answer", provide_answer)
agent_state.add_node("write_final_answer", write_final_answer)
agent_state.add_edge(START, "agent")
agent_state.add_conditional_edges("agent", trigger_queries, ["provide_answer"])
agent_state.add_edge("provide_answer", "write_final_answer")
agent_state.add_edge("write_final_answer", END)

graph = agent_state.compile()
