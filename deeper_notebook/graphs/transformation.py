import asyncio
import os

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger
from typing_extensions import TypedDict

from deeper_notebook.ai.provision import provision_langchain_model
from deeper_notebook.domain.notebook import Source
from deeper_notebook.domain.transformation import DefaultPrompts, Transformation
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import DeeperNotebookError, ExternalServiceError
from deeper_notebook.utils import clean_thinking_content
from deeper_notebook.utils.error_classifier import classify_error
from deeper_notebook.utils.text_utils import extract_text_content

# v0.8.26 — Per-node LLM-call timeout for the transformation graph.
# Same family as the v0.7.138 ask-graph fix that was missed for this
# file. `run_transformation` calls `chain.ainvoke()` once; pre-v0.8.26
# that call had NO timeout, so a wedged local LLM (llama-cpp-python
# mid-generation hang, cloud provider brief outage, gRPC stream stuck)
# would pin the surreal_commands worker holding the process_source
# job indefinitely. With max_attempts=15 and wait_max=120s in the
# process_source retry config, a wedge could keep a worker slot
# unavailable for roughly half an hour before surreal_commands gives
# up — backing up the entire transformation queue.
#
# Default 180s per node — more generous than ask.py's 120s because
# transformations include outline + insight generation that runs over
# the full (capped) source content, not just a short query.
_DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC = 180.0


def _transform_node_timeout_sec() -> float:
    raw = (resolve_env("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC") or "").strip()
    if not raw:
        return _DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC
    try:
        val = float(raw)
        if val <= 0:
            logger.warning(
                "DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC={} must be positive; "
                "using default {}s",
                raw,
                _DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC,
            )
            return _DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC
        return val
    except ValueError:
        logger.warning(
            "DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC={!r} not a float; using "
            "default {}s",
            raw,
            _DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC,
        )
        return _DEFAULT_TRANSFORM_NODE_TIMEOUT_SEC


# v0.7.10 — Input-text cap for transformations.
#
# `run_transformation` previously passed `source.full_text` (or
# `input_text`) into the prompt verbatim with no upper bound. A modest
# 50 KB source ≈ 12,500 tokens; combined with the (existing) 8192-token
# `max_tokens` output reservation, this already exceeds a 16k-context
# local LLM server's budget (the v0.7.8 default) before the system
# prompt is even counted.
#
# Default 12,000 chars ≈ 3,000 tokens leaves ample headroom in a 16k
# context after 8192-token output reservation + system prompt. Users
# on larger-context models (Hermes-3 @ 131k, Qwen 2.5 @ 32k+) can raise
# the cap via `DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP` without code edits.
_TRANSFORMATION_INPUT_CAP_DEFAULT = 12_000
_TRUNCATION_MARKER = "\n\n[... transformation input truncated for context budget ...]"


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


def _truncate_transformation_input(content: str) -> str:
    """Cap transformation input length for local-model safety.

    Adds a visible marker so the LLM (and any human inspecting the
    prompt) sees the input was elided rather than silently lost.
    """
    cap = _env_int(
        "DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP",
        _TRANSFORMATION_INPUT_CAP_DEFAULT,
        minimum=500,
    )
    if len(content) <= cap:
        return content
    logger.warning(
        f"Transformation input truncated from {len(content)} to {cap} chars "
        f"(set DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP to raise the limit)"
    )
    return content[:cap] + _TRUNCATION_MARKER


class TransformationState(TypedDict):
    input_text: str
    source: Source
    transformation: Transformation
    output: str


async def run_transformation(state: dict, config: RunnableConfig) -> dict:
    source_obj = state.get("source")
    source: Source = source_obj if isinstance(source_obj, Source) else None  # type: ignore[assignment]
    content = state.get("input_text")
    assert source or content, "No content to transform"
    transformation: Transformation = state["transformation"]

    try:
        if not content:
            content = source.full_text
        transformation_template_text = transformation.prompt
        default_prompts: DefaultPrompts = DefaultPrompts(
            transformation_instructions=None
        )
        if default_prompts.transformation_instructions:
            transformation_template_text = f"{default_prompts.transformation_instructions}\n\n{transformation_template_text}"

        transformation_template_text = f"{transformation_template_text}\n\n# INPUT"

        system_prompt = Prompter(template_text=transformation_template_text).render(
            data=state
        )
        content_str = str(content) if content else ""
        # v0.7.10 — cap input length before LLM call so a large source
        # doesn't overflow a 16k-context local server. See
        # `_truncate_transformation_input` docstring for rationale.
        content_str = _truncate_transformation_input(content_str)
        payload = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content_str),
        ]
        # v0.7.75 — size against the actual message text, not str(payload).
        # Same fix as v0.7.65 chat.py/source_chat.py: Python's repr of a
        # list of LangChain Message objects adds ~80-120 chars of
        # wrapper boilerplate per message, which the 105k large_context
        # cutoff in provision_langchain_model would then mis-trigger
        # earlier than the actual prompt size warrants.
        content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)
        chain = await provision_langchain_model(
            content_for_sizing,
            config.get("configurable", {}).get("model_id"),
            "transformation",
            max_tokens=8192,
        )

        # v0.8.26 — bound the LLM call so a wedged local model can't
        # pin the surreal_commands worker indefinitely. TimeoutError
        # maps to ExternalServiceError (502 at the global handler).
        timeout = _transform_node_timeout_sec()
        try:
            response = await asyncio.wait_for(
                chain.ainvoke(payload),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ExternalServiceError(
                f"Transformation graph: LLM call timed out after "
                f"{timeout:.0f}s. Try a smaller/faster model, raise "
                f"DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC, or check that the "
                f"provider is responsive."
            ) from exc

        # Clean thinking content from the response
        response_content = extract_text_content(response.content)
        cleaned_content = clean_thinking_content(response_content)

        if source:
            await source.add_insight(transformation.title, cleaned_content)

        return {
            "output": cleaned_content,
        }
    except DeeperNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


agent_state = StateGraph(TransformationState)
agent_state.add_node("agent", run_transformation)  # type: ignore[type-var]
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)
graph = agent_state.compile()
