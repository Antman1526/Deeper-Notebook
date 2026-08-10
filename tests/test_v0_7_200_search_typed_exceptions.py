"""v0.7.200 — Search/Ask router exception classifier pass-through +
proper task cancellation on disconnect + non-standard HTTP status fix.

Three discrete bugs from the v0.7.199 deferred list:

1. `/search` collapsed `InvalidInputError` and `DatabaseOperationError`
   into generic `HTTPException(400/500, "Search failed")` — defeating
   the v0.7.179–183 typed-exception sweep that taught
   `api/main.py`'s global handlers to render user-friendly classified
   messages. The user saw the literal "Search failed" placeholder
   instead of e.g. "Database connection lost — please retry".

2. `stream_ask_response` had `async for event in
   ask_graph.astream_events(...)` with an `if is_disconnected(): return`
   inside the body. The `return` only fires on the iterator's NEXT
   `await` boundary, which for `write_final_answer` is after the
   full 30-60 s synthesis LLM call completes. Cancellation never
   propagated; local-LLM kept tokenising tokens nobody read.

   Fix: drive the iterator manually with `__anext__()` inside an
   `asyncio.Task`, poll `is_disconnected()` between iterations, cancel
   the task on disconnect. Cancellation propagates into the in-flight
   LLM call (mirrors v0.7.184's chat.py pattern).

3. `/search/ask/simple` raised `HTTPException(status_code=499, ...)`
   on client disconnect — 499 is nginx-only and renders as "Unknown
   status" in FastAPI logs, Sentry, and OTel exporters. Replaced
   with 503 + descriptive detail.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_search_router_bubbles_typed_exceptions():
    """v0.7.200 — `/search` must let DatabaseOperationError +
    InvalidInputError + NotFoundError reach the global classifier
    middleware instead of collapsing them into HTTPException(500,
    "Search failed")."""
    src = _src("api/routers/search.py")
    # The bare "raise HTTPException(status_code=500, detail='Search
    # failed')" inside an InvalidInputError or DatabaseOperationError
    # branch must be gone.
    assert (
        "except DatabaseOperationError as e:\n"
        '        logger.error(f"Database error during search: {str(e)}")'
        in src
    ) is False, (
        "v0.7.200 regression: DatabaseOperationError caught + "
        "collapsed to HTTPException(500). Defeats the v0.7.179-183 "
        "global typed-exception sweep."
    )
    assert (
        "except InvalidInputError as e:\n"
        "        raise HTTPException(status_code=400, detail=str(e))"
        in src
    ) is False, (
        "v0.7.200 regression: InvalidInputError caught + collapsed "
        "to HTTPException(400). Same global-sweep defeat."
    )
    # The new combined handler must exist.
    assert (
        "except (NotFoundError, InvalidInputError, DatabaseOperationError):"
        in src
    ), "v0.7.200 regression: combined typed-exception handler removed."


def test_stream_ask_response_uses_anext_task_with_disconnect_poll():
    """v0.7.200 — `stream_ask_response` must drive its event iterator
    manually with `__anext__()` inside `asyncio.ensure_future`, and
    cancel the task when `is_disconnected()` returns True. The
    previous `async for` pattern could not propagate cancellation
    into a 30-60 s in-flight LLM call (only checked at next yield
    boundary)."""
    src = _src("api/routers/search.py")
    assert "event_iter = ask_graph.astream_events(" in src, (
        "v0.7.200 regression: stream_ask_response no longer holds an "
        "explicit iterator reference. Cannot manually cancel."
    )
    assert "asyncio.ensure_future(event_iter.__anext__())" in src, (
        "v0.7.200 regression: __anext__ task wrapping removed; "
        "cancellation no longer propagates to the in-flight LLM call."
    )
    assert "next_task.cancel()" in src
    # Best-effort iterator close after cancellation.
    assert "await event_iter.aclose()" in src


def test_ask_simple_disconnect_uses_standard_status():
    """v0.7.200 — `/search/ask/simple` client-disconnect path must
    use a standard HTTP status (5xx range), not the nginx-only 499.
    499 renders as "Unknown status" in Sentry/OTel — operators
    cannot graph it."""
    src = _src("api/routers/search.py")
    assert "status_code=499" not in src, (
        "v0.7.200 regression: non-standard 499 status restored. "
        "Operators cannot graph this status in Sentry/OTel."
    )
    # And 503 (or some standard equivalent) must take its place.
    assert (
        "status_code=503" in src
        and "Client disconnected before answer ready" in src
    )


def test_no_remaining_onkeypress_in_search_or_session_manager():
    """v0.7.200 — React 19 deprecates `onKeyPress`. Search page and
    SessionManager were the last callsites. All swapped to
    `onKeyDown` (the modern, fully-supported handler)."""
    for rel in (
        "frontend/src/app/(dashboard)/search/page.tsx",
        "frontend/src/components/source/SessionManager.tsx",
    ):
        src = _src(rel)
        # Strip comments so historical-rationale lines don't false-positive.
        code_only = "\n".join(
            ln for ln in src.splitlines() if not ln.lstrip().startswith("//")
        )
        assert "onKeyPress" not in code_only, (
            f"v0.7.200 regression: {rel} still uses onKeyPress. "
            f"React 19 silently no-ops the handler."
        )
