"""v0.7.172 — Lifespan-startup stale-command reaper.

If the surreal-commands worker crashes / is OOM-killed mid-job, the
command row stays in `new` / `queued` / `running` forever. The
frontend's `useSourceStatus` polls every 2 seconds while status ∈
{new, queued, running} — silent CPU + DB load forever, with no path
to recovery short of manual SurrealQL.

On API restart we KNOW the worker isn't still mid-job (the launcher's
process tree restarts together), so any pre-restart row in a not-
terminal state is stale. v0.7.172 marks them all failed at lifespan
startup so the frontend stops polling.

This test pins the contract at the AST level so the reaper can't
silently be removed in a future refactor.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_main_py() -> str:
    return (ROOT / "api" / "main.py").read_text(encoding="utf-8")


def test_lifespan_runs_stale_command_reaper():
    """v0.7.172: api/main.py lifespan must run an UPDATE that marks
    stale command rows as failed. Look for the canonical query
    fragments — `WHERE status IN ['new', 'queued', 'running']` and
    `(time::now() - 30m)` — so a future refactor can't drop the
    safety net silently."""
    src = _read_main_py()

    assert "UPDATE command" in src, (
        "v0.7.172 regression: api/main.py lifespan no longer runs "
        "the stale-command reaper. The frontend's useSourceStatus "
        "polls every 2s while a command row is non-terminal — without "
        "this reaper, a worker crash leaves the source in a polling "
        "loop forever."
    )
    assert "status IN ['new', 'queued', 'running']" in src, (
        "v0.7.172 regression: reaper filter clause changed shape. "
        "Must cover all three non-terminal statuses; missing any one "
        "leaves that state's rows still poll-able by the frontend."
    )
    assert "(time::now() - 30m)" in src, (
        "v0.7.172 regression: 30-minute updated-time filter missing. "
        "Belt-and-suspenders so an in-flight job from a future "
        "cross-process worker isn't wiped if the API restarts on "
        "its own."
    )
    # And the error_message must be informative for the user (this
    # surfaces in the frontend's failed-source error panel).
    assert "Marked stale on API restart" in src


def test_reaper_failure_is_non_fatal():
    """v0.7.172: the reaper is wrapped in try/except so a SurrealDB
    blip during startup doesn't block the API from coming up. The
    next worker startup will likely sort things out either way."""
    src = _read_main_py()
    idx = src.index("UPDATE command")
    # Widen the right-side window so the trailing `except Exception`
    # clause (which sits after the result-handling block) is captured.
    region = src[idx - 500 : idx + 1500]
    assert "try:" in region, (
        "v0.7.172 regression: reaper UPDATE is no longer wrapped in "
        "try/except — a SurrealDB hiccup would now prevent the API "
        "from starting."
    )
    assert "except Exception" in region
    assert "non-fatal" in region.lower(), (
        "Comment should explicitly call out the non-fatal contract "
        "so a future maintainer doesn't tighten the except into "
        "a fail-fast."
    )


def test_reaper_logs_at_warning_when_reaping_happens():
    """v0.7.172: when the reaper actually marks rows failed, the
    log line is WARNING level (not debug/info) so an operator sees
    the signal in api.log filters. An install that consistently
    reaps stale rows on every startup is a canary for "the worker
    is unreliable."""
    src = _read_main_py()
    # The reaped-N-rows log must be visible.
    assert "Reaped" in src and "stale command row" in src
    # Find the conditional warning block.
    idx = src.index("Reaped")
    region = src[idx - 100 : idx + 300]
    assert "logger.warning" in region
