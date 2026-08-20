"""v0.7.190 — Round-9 audit LOW-severity closeout (backend).

Three small but defensible improvements:

1.  `api/main.py` module-level `_BACKGROUND_TASKS: set[asyncio.Task]`
    + `_track_task()` helper. Per the asyncio docs, fire-and-forget
    tasks may be GC'd before they finish because the event loop only
    keeps weak references. The local-var anchor works today but a
    future refactor that extracts the spawn into a helper would
    silently lose the anchor. Wrapped all 3 lifespan tasks
    (digest_scheduler, checkpoint_prune, gmail_prewarm) in
    _track_task as defence-in-depth.

2.  `repo_query()` now accepts an optional `timeout_s` keyword.
    Default None preserves the v0.7.120 behaviour. Callers that
    fan out many small queries (ContextBuilder, memory_recall) can
    pass an explicit per-query budget so a single stuck pool
    connection doesn't pin the route handler.

3.  `deeper_notebook/graphs/tools.py::get_current_timestamp` switched
    from naive local time (`YYYYMMDDHHmmss`) to UTC ISO 8601 basic
    (`YYYYMMDDTHHmmssZ`). The output lands in LLM prompts that may
    be replayed cross-machine; without the TZ marker every
    timestamp was ambiguous.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from task_lifecycle_assertions import assert_lifespan_tracked_task

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Background-task GC anchor
# ---------------------------------------------------------------------------


def test_api_main_exposes_track_task_helper():
    """v0.7.190: module-level _track_task helper anchors background
    tasks to _BACKGROUND_TASKS so the asyncio GC can't reap them."""
    src = _read_source("api/main.py")
    assert '_BACKGROUND_TASKS: "set[asyncio.Task]" = set()' in src, (
        "v0.7.190 regression: _BACKGROUND_TASKS module-level set is "
        "gone. Fire-and-forget tasks risk GC under pressure."
    )
    assert "def _track_task(task:" in src
    assert "_BACKGROUND_TASKS.add(task)" in src
    assert "task.add_done_callback(_BACKGROUND_TASKS.discard)" in src, (
        "v0.7.190 regression: _track_task no longer registers the "
        "done-callback that auto-discards completed tasks. The "
        "_BACKGROUND_TASKS set will leak indefinitely."
    )


def test_lifespan_tasks_use_track_task_anchor():
    """v0.7.190: all 3 lifespan-spawned background tasks (digest
    scheduler, checkpoint pruner, gmail pre-warm) must be wrapped
    in _track_task. The pre-fix local-var anchor worked today but
    was fragile to future refactors."""
    src = _read_source("api/main.py")
    for task_name, coroutine_name in (
        ("digest_scheduler_task", "_digest_run_forever"),
        ("checkpoint_prune_task", "_checkpoint_prune_loop"),
        ("gmail_prewarm_task", "_prewarm_gmail_cache"),
    ):
        assert_lifespan_tracked_task(
            src, task_name=task_name, coroutine_name=coroutine_name
        )


def test_lifespan_task_guard_rejects_untracked_task_with_nested_function_decoy():
    source = """
async def lifespan(app):
    digest_scheduler_task = asyncio.create_task(_digest_run_forever(stop_event))

    async def unused_decoy():
        digest_scheduler_task = _track_task(
            asyncio.create_task(_digest_run_forever(stop_event))
        )

    yield
"""

    with pytest.raises(AssertionError, match="digest_scheduler_task must wrap"):
        assert_lifespan_tracked_task(
            source,
            task_name="digest_scheduler_task",
            coroutine_name="_digest_run_forever",
        )


def test_lifespan_task_guard_rejects_wrong_task_with_nested_class_decoy():
    source = """
async def lifespan(app):
    gmail_prewarm_task = _track_task(asyncio.create_task(_wrong_cache()))

    class UnusedDecoy:
        gmail_prewarm_task = _track_task(
            asyncio.create_task(_prewarm_gmail_cache())
        )

    yield
"""

    with pytest.raises(AssertionError, match="gmail_prewarm_task must wrap"):
        assert_lifespan_tracked_task(
            source,
            task_name="gmail_prewarm_task",
            coroutine_name="_prewarm_gmail_cache",
        )


@pytest.mark.asyncio
async def test_track_task_holds_strong_reference_and_self_evicts():
    """v0.7.190 behavioural: _track_task keeps the task alive while
    running AND removes it from the set when it completes."""
    from api.main import _BACKGROUND_TASKS, _track_task

    async def _quick():
        await asyncio.sleep(0)
        return "ok"

    baseline = len(_BACKGROUND_TASKS)
    task = _track_task(asyncio.create_task(_quick()))
    # While the task is mid-flight, it's in the set.
    assert task in _BACKGROUND_TASKS
    result = await task
    assert result == "ok"
    # done_callback fires after we await — give the loop one tick
    # to process the callback.
    await asyncio.sleep(0)
    assert task not in _BACKGROUND_TASKS
    assert len(_BACKGROUND_TASKS) == baseline


# ---------------------------------------------------------------------------
# repo_query optional timeout
# ---------------------------------------------------------------------------


def test_repo_query_accepts_timeout_kwarg():
    """v0.7.190: repo_query gained an optional `timeout_s` keyword
    for per-call wait_for bounding."""
    import inspect

    from deeper_notebook.database.repository import repo_query

    sig = inspect.signature(repo_query)
    assert "timeout_s" in sig.parameters, (
        "v0.7.190 regression: repo_query no longer accepts `timeout_s`. "
        "Callers can no longer bound individual queries to fail fast on "
        "stuck pool connections."
    )
    # Default must be None for backward compat.
    assert sig.parameters["timeout_s"].default is None


def test_repo_query_default_call_unchanged():
    """v0.7.190 backward-compat pin: existing callers passing only
    (query_str, vars) must still work. The new kwarg is purely
    additive."""
    src = _read_source("deeper_notebook/database/repository.py")
    # The function signature line.
    sig_idx = src.find("async def repo_query(")
    assert sig_idx != -1
    end = src.find(")", sig_idx)
    sig_text = src[sig_idx : end + 1]
    # Must accept (query_str, vars=None) positionally as before.
    assert "query_str: str" in sig_text
    assert "vars: Optional[dict[str, Any]] = None" in sig_text
    # And the new kwarg is keyword-only (after *).
    assert "*," in sig_text


# ---------------------------------------------------------------------------
# tools.py UTC timestamp
# ---------------------------------------------------------------------------


def test_get_current_timestamp_returns_iso8601_with_utc():
    """v0.7.190: get_current_timestamp returns
    `YYYYMMDDTHHmmssZ` (basic ISO 8601 with explicit UTC marker),
    not the previous ambiguous naive local-time
    `YYYYMMDDHHmmss`."""
    from deeper_notebook.graphs.tools import get_current_timestamp

    ts = get_current_timestamp.func()
    # T separator + Z marker.
    assert "T" in ts
    assert ts.endswith("Z")
    # Parseable via strptime with the new format.
    dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ")
    # And it's close to wall-clock UTC (within 60s window for slow CI).
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    diff = abs((now_utc - dt).total_seconds())
    assert diff < 60, (
        f"v0.7.190: get_current_timestamp returned a stamp {diff:.0f}s "
        f"away from current UTC — TZ handling may be broken."
    )
