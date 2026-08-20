"""v0.7.165 — LangGraph state-shape variance regression tests.

CLAUDE.md's standing audit calls subscript / `.get()` against an
`ainvoke()` return value WITHOUT a dual `isinstance(result, dict)` /
`getattr(result, 'attr', default)` guard a recurring footgun. The
codebase has been bitten by this in v0.7.52, 55, 56, 75, 81, 95 —
and v0.7.165 closes the next two sites the audit found:

  1. `api/routers/chat.py:632-649` non-streaming /chat/execute path
     used `result.get("messages", [])` twice. Now normalized via a
     single `result_messages` local that handles both dict and
     Pydantic state shapes.

  2. `deeper_notebook/graphs/source.py:168,172` used `result["output"]`
     against the transformation graph. Now normalized via an
     `output_text` local with the same dual-path.

These tests pin the AST-level invariant: the affected files MUST
contain an `isinstance(result, dict)` check immediately before the
.get()/subscript so a future refactor that drops the guard fails
deterministically here rather than at runtime against a Pydantic
state.
"""

from __future__ import annotations

import ast
from pathlib import Path

from task_lifecycle_assertions import assert_lifespan_tracked_task

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_chat_execute_normalizes_result_messages_via_dual_path():
    """v0.7.165: api/routers/chat.py must normalize `result_messages`
    using isinstance(result, dict) before iterating. The normalization
    must happen ONCE — both the response-conversion loop and the
    memory-extractor loop read the same local."""
    src = _read_source("api/routers/chat.py")

    # Find the `result_messages = ...` assignment introduced by v0.7.165.
    assert "result_messages = (" in src, (
        "v0.7.165 regression: api/routers/chat.py missing the "
        "`result_messages = (...)` dual-path normalization. A future "
        "refactor that goes back to per-iteration `result.get('messages')` "
        "loses the Pydantic-state guard."
    )

    # The normalization itself must include the isinstance + getattr pair.
    # We look at the 6 lines following the introduction.
    idx = src.index("result_messages = (")
    region = src[idx : idx + 400]
    assert "isinstance(result, dict)" in region, (
        f"result_messages normalization missing isinstance guard. Got:\n{region!r}"
    )
    assert "getattr(result," in region, (
        f"result_messages normalization missing getattr fallback. Got:\n{region!r}"
    )

    # Both iteration sites must use the local, not the raw result.get().
    # The post-v0.7.165 source has zero `result.get("messages"` references
    # in the non-streaming handler.
    # (The streaming handler at line ~820 uses its own dual-path; we
    # don't break that out separately here.)
    # Count `result.get("messages"` — should be 0 or only inside the
    # streaming-path block. Trying to enforce "0 anywhere in the file"
    # is too strict; instead enforce that the original two iteration
    # sites use `result_messages`.
    for snippet in (
        "for msg in result_messages:",
        "for msg in reversed(result_messages):",
    ):
        assert snippet in src, (
            f"v0.7.165 regression: chat.py iteration site no longer "
            f"reads `result_messages` local. Looking for: {snippet!r}"
        )


def test_source_transform_normalizes_output_via_dual_path():
    """v0.7.165: deeper_notebook/graphs/source.py must normalize
    `output_text` before using it in both `source.add_insight(...)`
    and the returned `{"output": output_text}` dict.
    """
    src = _read_source("deeper_notebook/graphs/source.py")

    assert "output_text = (" in src, (
        "v0.7.165 regression: source.py missing the `output_text = (...)` "
        "dual-path normalization. A future refactor that goes back to "
        "raw `result['output']` loses the Pydantic-state guard."
    )

    # The normalization itself must include the isinstance + getattr pair.
    idx = src.index("output_text = (")
    region = src[idx : idx + 200]
    assert "isinstance(result, dict)" in region
    assert "getattr(result," in region

    # Both downstream uses must reference the local, not raw subscript.
    assert "source.add_insight(transformation.title, output_text)" in src
    assert '"output": output_text,' in src


def test_chat_py_is_syntactically_valid():
    """Belt-and-suspenders: the v0.7.165 edits must leave the file
    parseable. Catches accidental edit damage that the test runner
    would otherwise only report as an ImportError at collection time."""
    src = _read_source("api/routers/chat.py")
    ast.parse(src)  # raises SyntaxError on broken edits


def test_source_graph_is_syntactically_valid():
    """Same as above for the graph module."""
    src = _read_source("deeper_notebook/graphs/source.py")
    ast.parse(src)


def test_api_main_holds_gmail_prewarm_task_reference():
    """v0.7.165: api/main.py must assign the gmail-prewarm task to a
    local variable, not fire-and-forget via bare `asyncio.create_task(...)`.

    Without a strong reference Python 3.11+ can GC the task before it
    runs (documented foot-gun), silently dropping the pre-warm. The
    fix mirrors the existing pattern for digest_scheduler_task and
    checkpoint_prune_task in the same lifespan handler.
    """
    src = _read_source("api/main.py")

    assert_lifespan_tracked_task(
        src,
        task_name="gmail_prewarm_task",
        coroutine_name="_prewarm_gmail_cache",
    )

    # And the shutdown path must reference it
    assert "gmail_prewarm_task.done()" in src, (
        "v0.7.165 regression: api/main.py shutdown no longer waits "
        "for the gmail-prewarm task — possible task leak past lifespan."
    )
