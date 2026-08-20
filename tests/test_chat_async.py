"""ONP v0.6.10 — Regression test for the event-loop-blocking chat invoke.

Both api/routers/chat.py and api/routers/source_chat.py used to call
`<graph>.invoke(...)` directly from inside async handlers, which blocks
the FastAPI event loop for the entire duration of an LLM call (typically
30s–5min on local models). Every other concurrent request would stall.

The fix wrapped both calls in asyncio.to_thread(). These tests verify
the pattern is in place by AST-inspecting the source — cheap, doesn't
require firing up a graph or mocking LangGraph internals.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest


def _function_calls_in_source(src: str) -> list[str]:
    """Return every call-expression in the source, rendered as dotted text."""
    tree = ast.parse(src)
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            calls.append(ast.unparse(node.func))
    return calls


@pytest.mark.parametrize(
    "module_path, graph_name",
    [
        ("api/routers/chat.py", "chat_graph"),
        ("api/routers/source_chat.py", "source_chat_graph"),
    ],
)
def test_graph_invoke_is_always_wrapped_in_to_thread(module_path, graph_name):
    """A direct `<graph>.invoke(...)` call from an async handler blocks
    the event loop. This test fails if such a call is reintroduced.

    Allowed pattern:
        await asyncio.to_thread(<graph>.invoke, ...)
    Disallowed pattern:
        <graph>.invoke(...)
    """
    repo_root = Path(__file__).resolve().parent.parent
    src = (repo_root / module_path).read_text()

    # Find every Call node and check its callable text. The to_thread
    # case wraps `chat_graph.invoke` as a *function argument* — its
    # `ast.Call.func` is `asyncio.to_thread`, not `chat_graph.invoke`,
    # so it's never reported as a top-level callable here.
    direct_invokes = [
        c for c in _function_calls_in_source(src) if c == f"{graph_name}.invoke"
    ]
    assert not direct_invokes, (
        f"{module_path} contains a direct `{graph_name}.invoke(...)` call. "
        f"This blocks the event loop — wrap in `await asyncio.to_thread(...)` "
        f"like the existing `{graph_name}.get_state` call does."
    )

    # Sanity: confirm the wrapped form IS used.
    assert "asyncio.to_thread" in src, (
        f"{module_path} should use asyncio.to_thread for sync graph calls"
    )
