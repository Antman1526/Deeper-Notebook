"""v0.7.175 — `/sources/{id}/insights` routes through CommandService.

Background: the insight-submission endpoint used a bare
`asyncio.to_thread(submit_command, ...)` which had NO timeout cap.
When the SurrealDB connection pool saturated (or a WebSocket
handshake hung), the call blocked the worker indefinitely, pinning
a pool slot per stuck call. Every other call site already routed
through `CommandService.submit_command_job` — which wraps the
to_thread call in `asyncio.wait_for(timeout=10)` and raises
ValueError on timeout. This endpoint was the lone holdout.

v0.7.175 routes the insight submission through CommandService too,
and translates the ValueError into HTTP 503 ("service overloaded,
retry") rather than the generic 500.

This test is AST-level — verifies the source file calls the right
helper and produces the right HTTP status, without needing a live
SurrealDB / running command broker.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_insights_endpoint_routes_through_command_service():
    """v0.7.175: the create_source_insight (or equivalent) endpoint
    must call CommandService.submit_command_job for run_transformation,
    NOT bare `asyncio.to_thread(submit_command, ...)`. The bare call
    had no timeout cap and could pin worker slots forever."""
    src = _read_source("api/routers/sources.py")

    # The CommandService helper must be imported / used.
    assert "from api.command_service import CommandService" in src, (
        "v0.7.175 regression: CommandService import gone — the bare "
        "asyncio.to_thread(submit_command, ...) is back."
    )

    # The run_transformation submission must go through the helper.
    # Find the run_transformation submit block, then assert it is
    # in the same neighborhood as a submit_command_job call.
    idx_run_xform = src.find('"run_transformation"')
    assert idx_run_xform != -1, (
        "v0.7.175: cannot locate run_transformation submit block — "
        "test pin needs updating if the endpoint moved."
    )
    region = src[idx_run_xform - 800 : idx_run_xform + 200]
    assert "CommandService.submit_command_job" in region, (
        "v0.7.175 regression: run_transformation submission no "
        "longer routes through CommandService.submit_command_job. "
        "If this comes back as bare asyncio.to_thread(submit_command, "
        "...) the timeout cap is gone and the endpoint can block "
        "workers indefinitely on a saturated pool."
    )


def test_insights_endpoint_returns_503_on_timeout():
    """v0.7.175: when CommandService.submit_command_job raises
    ValueError (its timeout signal), the endpoint must translate
    that to HTTP 503 — not the generic 500. 503 tells the client
    'retry shortly' which is the correct semantic for an
    overloaded job-queue."""
    src = _read_source("api/routers/sources.py")
    # Find the run_transformation block.
    idx = src.find('"run_transformation"')
    assert idx != -1
    # Look forward for the ValueError handler that follows the submit.
    region = src[idx : idx + 1500]
    assert "except ValueError" in region, (
        "v0.7.175 regression: the ValueError-on-timeout handler is "
        "gone. Without it, a saturated pool would bubble up as 500 "
        "'Error starting insight generation' which gives the client "
        "no signal to retry. Restore the `except ValueError: raise "
        "HTTPException(status_code=503, ...)` block."
    )
    assert "status_code=503" in region, (
        "v0.7.175 regression: the status_code=503 response is gone. "
        "Without 503, callers can't distinguish overload (transient, "
        "retry) from a real 500 (likely permanent until fixed)."
    )


def test_insights_endpoint_logs_timeout_before_raising():
    """v0.7.175: the timeout path must logger.warning before
    raising — otherwise saturated-pool incidents are invisible
    until the user complains."""
    src = _read_source("api/routers/sources.py")
    # The warning lives between the except ValueError and the
    # HTTPException raise.
    idx = src.find('"Insight submission timed out / failed')
    assert idx != -1, (
        "v0.7.175 regression: the 'Insight submission timed out' "
        "logger.warning line is gone. Without it, pool-saturation "
        "incidents are silent — restore it inside the except "
        "ValueError block."
    )
