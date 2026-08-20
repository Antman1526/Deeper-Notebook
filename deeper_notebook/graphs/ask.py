import asyncio
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

from deeper_notebook.ai.provision import provision_langchain_model
from deeper_notebook.domain.notebook import vector_search
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import (
    DeeperNotebookError,
    ExternalServiceError,
)
from deeper_notebook.graphs.agent_fsm import AgentState  # v0.8.53 — Phase 5.3b
from deeper_notebook.utils import clean_thinking_content
from deeper_notebook.utils.error_classifier import classify_error
from deeper_notebook.utils.text_utils import extract_text_content


async def _evaluate_ask_response(response_text: str) -> None:
    """Best-effort Ask evaluation.

    Ask currently synthesizes result snippets rather than a durable notebook
    selection. It therefore has no safe notebook owner to persist against; the
    extraction call deliberately remains advisory until the router supplies a
    selected-source snapshot.
    """
    if not response_text.strip():
        return
    try:
        from deeper_notebook.evaluation.claims import extract_material_claims

        # Run extraction now so malformed generated text is visible in local
        # diagnostics, but do not invent source ownership for persistence.
        extract_material_claims(response_text)
    except Exception as exc:
        logger.warning("Ask evidence evaluation skipped: {}", exc)


def _schedule_ask_evaluation(response_text: str) -> None:
    if not response_text.strip():
        return
    task = asyncio.create_task(_evaluate_ask_response(response_text))
    task.add_done_callback(
        lambda completed: completed.exception() if not completed.cancelled() else None
    )


# v0.7.138 — Per-node LLM-call timeout for the ask graph (final-sweep
# audit finding #1). Each of the three nodes (strategy, provide_answer,
# write_final_answer) calls `model.ainvoke()` once. Before this
# release, NONE of them had a timeout — a hung provider (e.g., local
# llama-cpp-python that wedges mid-generation, cloud provider with a
# brief outage) would pin the whole /search/ask stream indefinitely.
# The outer SSE handler has `is_disconnected()` checks but no total-
# time wall.
#
# Default 120s per node — generous because the final-answer node
# synthesizes across multiple sub-answers and can legitimately need
# 60-90s on a 16k-context local model. Tunable per-deployment.
_DEFAULT_ASK_NODE_TIMEOUT_SEC = 120.0


def _ask_node_timeout_sec() -> float:
    raw = (resolve_env("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC") or "").strip()
    if not raw:
        return _DEFAULT_ASK_NODE_TIMEOUT_SEC
    try:
        val = float(raw)
        if val <= 0:
            logger.warning(
                "DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC={} must be positive; using default {}s",
                raw,
                _DEFAULT_ASK_NODE_TIMEOUT_SEC,
            )
            return _DEFAULT_ASK_NODE_TIMEOUT_SEC
        return val
    except ValueError:
        logger.warning(
            "DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC={!r} not a float; using default {}s",
            raw,
            _DEFAULT_ASK_NODE_TIMEOUT_SEC,
        )
        return _DEFAULT_ASK_NODE_TIMEOUT_SEC


async def _ask_invoke(model, payload, *, node: str):
    """v0.7.138 — Wrap a single ask-node LLM invocation with the
    per-node timeout. A TimeoutError becomes ExternalServiceError
    (HTTP 502 at the global handler) with a message naming the
    failing node, so users see actionable info rather than a generic
    500 + stack trace.

    Why ExternalServiceError specifically: the failure mode is
    upstream (the LLM provider hung), and 502 Bad Gateway is the
    canonical status for "I tried to talk to an upstream service
    and it didn't respond properly".
    """
    timeout = _ask_node_timeout_sec()
    try:
        return await asyncio.wait_for(model.ainvoke(payload), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise ExternalServiceError(
            f"Ask graph: {node!r} node LLM call timed out after "
            f"{timeout:.0f}s. Try a smaller/faster model, raise "
            f"DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC, or check that the provider "
            f"is responsive."
        ) from exc


# v0.8.53 — Phase 5.3b: optional agent-FSM completion gate for the ask graph.
# The graph fans out the strategy's searches and then synthesizes a final
# answer. When NONE of the searches returned grounded content, asking the LLM
# to "synthesize" means writing from an empty context — precisely the case
# where weak local models confidently hallucinate. When DEEPER_NOTEBOOK_AGENT_FSM is on we
# instead declare CLARIFY (per the agent_fsm state vocabulary) and ask the user
# to refine, rather than emit an ungrounded answer. Explicit off → unchanged.
_AGENT_FSM_CLARIFY_MESSAGE = (
    "I couldn't find anything relevant to that question in your sources. "
    "Try rephrasing it, using different keywords, or adding sources that "
    "cover the topic — then ask again."
)


def _agent_fsm_enabled() -> bool:
    raw = resolve_env("DEEPER_NOTEBOOK_AGENT_FSM")
    if raw is None:
        return True
    raw = raw.strip().lower()
    return raw in ("on", "1", "true", "yes")


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
        "DEEPER_NOTEBOOK_ASK_MAX_RESULTS", _ASK_MAX_RESULTS_DEFAULT, minimum=1
    )
    char_cap = _env_int(
        "DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP",
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
    searches: list[Search] = Field(
        default_factory=list,
        description="You can add up to five searches to this strategy",
    )


class ThreadState(TypedDict, total=False):
    question: str
    strategy: Strategy
    answers: Annotated[list, operator.add]
    final_answer: str
    agent_state: str  # v0.8.53 — Phase 5.3b: "complete" | "clarify" (FSM-gated)


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
        # First get the raw response from the model.
        # v0.7.138 — bounded by _ask_invoke instead of bare ainvoke.
        ai_message = await _ask_invoke(model, system_prompt, node="strategy")

        # Clean the thinking content from the response
        message_content = extract_text_content(ai_message.content)
        cleaned_content = clean_thinking_content(message_content)

        # Parse the cleaned JSON content
        strategy = parser.parse(cleaned_content)

        return {"strategy": strategy}
    except DeeperNotebookError:
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
        system_prompt = Prompter(prompt_template="ask/query_process").render(
            data=payload
        )  # type: ignore[arg-type]
        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("answer_model"),
            "tools",
            max_tokens=2000,
        )
        # v0.7.138 — bounded by _ask_invoke instead of bare ainvoke.
        ai_message = await _ask_invoke(model, system_prompt, node="provide_answer")
        ai_content = extract_text_content(ai_message.content)
        return {"answers": [clean_thinking_content(ai_content)]}
    except DeeperNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


async def write_final_answer(state: ThreadState, config: RunnableConfig) -> dict:
    try:
        # v0.8.53 — Phase 5.3b agent-FSM completion gate (default on). If no
        # search produced grounded content, don't ask the LLM to synthesize
        # from an empty context (where weak local models hallucinate) — declare
        # CLARIFY and prompt the user to refine. Streaming-safe: search.py
        # captures `final_answer` from this node's on_chain_end terminal event,
        # so the message is delivered even without streamed token deltas.
        if _agent_fsm_enabled():
            answers = state.get("answers") or []
            if not any(isinstance(a, str) and a.strip() for a in answers):
                logger.info(
                    "ask agent-FSM: no grounded answers from the strategy's "
                    "searches → declaring CLARIFY instead of ungrounded synthesis"
                )
                return {
                    "final_answer": _AGENT_FSM_CLARIFY_MESSAGE,
                    "agent_state": AgentState.CLARIFY.value,
                }
        system_prompt = Prompter(prompt_template="ask/final_answer").render(data=state)  # type: ignore[arg-type]
        model = await provision_langchain_model(
            system_prompt,
            config.get("configurable", {}).get("final_answer_model"),
            "tools",
            max_tokens=2000,
        )
        # v0.7.138 — bounded by _ask_invoke. The final-answer node
        # synthesizes across multiple sub-answers and is typically the
        # slowest node in the graph; the default 120s budget should
        # cover it, but operators with bigger contexts can raise
        # DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC.
        ai_message = await _ask_invoke(model, system_prompt, node="write_final_answer")
        final_content = extract_text_content(ai_message.content)
        cleaned_answer = clean_thinking_content(final_content)
        _schedule_ask_evaluation(cleaned_answer)
        result: dict = {"final_answer": cleaned_answer}
        if _agent_fsm_enabled():
            result["agent_state"] = AgentState.COMPLETE.value
        return result
    except DeeperNotebookError:
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
