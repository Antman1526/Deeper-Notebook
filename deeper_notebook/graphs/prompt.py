import asyncio
from typing import Any, Optional

from ai_prompter import Prompter
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from deeper_notebook.ai.provision import provision_langchain_model
from deeper_notebook.exceptions import ExternalServiceError

# v0.8.26 — Share the transformation graph's timeout knob since both
# graphs serve the same workload family ("apply a prompt template to
# user content"). One env var to remember instead of two.
from deeper_notebook.graphs.transformation import _transform_node_timeout_sec
from deeper_notebook.utils.text_utils import (
    clean_thinking_content,
    extract_text_content,
)


class PatternChainState(TypedDict):
    prompt: str
    parser: Optional[Any]
    input_text: str
    output: str


async def call_model(state: dict, config: RunnableConfig) -> dict:
    content = state["input_text"]
    system_prompt = Prompter(
        template_text=state["prompt"], parser=state.get("parser")
    ).render(data=state)
    payload = [SystemMessage(content=system_prompt)] + [HumanMessage(content=content)]
    # v0.7.75 — size against message text only, not str(payload). See
    # chat.py/source_chat.py/transformation.py for the same fix —
    # repr of a list of LangChain Messages adds wrapper noise that
    # mis-triggers the 105k large_context cutoff for cosmetic reasons.
    content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)
    chain = await provision_langchain_model(
        content_for_sizing,
        config.get("configurable", {}).get("model_id"),
        "transformation",
        max_tokens=5000,
    )

    # v0.8.26 — bound the LLM call (same family as the ask-graph
    # v0.7.138 fix and the transformation-graph v0.8.26 fix that
    # this graph mirrors). Without the bound, a wedged provider
    # pins whatever caller invoked the prompt graph (notes
    # router's title-generation flow, etc.). Shares the
    # DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC knob with transformation.py.
    timeout = _transform_node_timeout_sec()
    try:
        response = await asyncio.wait_for(
            chain.ainvoke(payload),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise ExternalServiceError(
            f"Prompt graph: LLM call timed out after {timeout:.0f}s. "
            f"Try a smaller/faster model, raise "
            f"DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC, or check that the "
            f"provider is responsive."
        ) from exc

    # Clean thinking tags from response (handles extended thinking models)
    output = clean_thinking_content(extract_text_content(response.content))
    return {"output": output}


agent_state = StateGraph(PatternChainState)
agent_state.add_node("agent", call_model)  # type: ignore[type-var]
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)

graph = agent_state.compile()
