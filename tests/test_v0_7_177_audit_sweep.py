"""v0.7.177 — Round-4 deferred sweep.

Three independent fixes bundled under one version tag because they
came out of the same deep-scan but each touch a different file:

1.  podcast_service.py 500/404 details echoed str(e) back to clients.
    The v0.7.168 router sweep handled all `routers/*.py` files but
    missed `api/podcast_service.py` (a service file, not a router).
    Driver internals shouldn't surface to the client; logger.error
    keeps them for ops.

2.  command_service.py.cancel_command_job imported the private
    surreal_commands `core.service` module directly. An upstream
    rename of `core.service` would silently break ALL job
    cancellation with an ImportError swallowed by the broad
    `except Exception` further down. Wrap the private import in
    try/ImportError and fall back to a direct repo_query UPDATE
    on the `command` table.

3.  No code change but a meta-test: the migration idempotency pattern
    introduced in v0.7.176 should hold for any future migration
    added to the catalog. Sentinel test that fails loudly if anyone
    adds a new migration without `IF NOT EXISTS` / `OVERWRITE`
    guards.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# podcast_service.py str(e) leak sweep
# ---------------------------------------------------------------------------


def test_podcast_service_does_not_leak_str_e_in_500_details():
    """v0.7.177: the four 500/404 HTTPException raises in
    podcast_service.py must NOT echo `str(e)` back to the client.
    Driver internals (SurrealDB WS frames, RecordIDs, connection-
    pool diagnostics) can ride that string out to the browser.
    logger.error captures the full picture for ops; the client
    gets a generic message that's actionable but doesn't leak."""
    src = _read_source("api/podcast_service.py")

    # All four sanitized HTTPException details must be plain strings.
    # We pin specifically that there are no detail= bodies that
    # echo str(e) for 500-level responses.
    bad_patterns = [
        'detail=f"Failed to submit podcast generation job: {str(e)}"',
        'detail=f"Failed to get job status: {str(e)}"',
        'detail=f"Failed to list episodes: {str(e)}"',
        'detail=f"Episode not found: {str(e)}"',
    ]
    for pat in bad_patterns:
        assert pat not in src, (
            f"v0.7.177 regression: podcast_service.py is leaking str(e) "
            f"in an HTTPException detail again. Offending pattern: {pat}"
        )

    # And the sanitized strings are present.
    assert 'detail="Failed to submit podcast generation job"' in src
    assert 'detail="Failed to get job status"' in src
    assert 'detail="Failed to list episodes"' in src
    # v0.7.204 — `get_episode` was restructured to raise
    # `NotFoundError` (which the global classifier formats as 404)
    # instead of wrapping every Exception as a synthetic 404
    # "Episode not found". The HTTPException(404) is gone; the
    # NotFoundError form is what we pin now.
    assert 'raise NotFoundError(f"Episode {episode_id} not found")' in src


def test_podcast_service_still_logs_full_exception():
    """v0.7.177: sanitizing the client-facing detail must NOT remove
    the `logger.error(...{e})` lines that capture the full exception
    for ops. Without those, the only signal of a failure would be
    the generic 500 — diagnosis would be impossible."""
    src = _read_source("api/podcast_service.py")
    # Each of the four sanitized blocks still has a preceding
    # logger.error that captures the exception.
    # v0.7.204 — `get_episode` no longer has a try/except (it
    # restructured to raise NotFoundError on the None return, letting
    # all other exceptions classify naturally). So the
    # `"Failed to get podcast episode {episode_id}"` log line is
    # gone — by design — and removed from the needles.
    for needle in (
        "Failed to submit podcast generation job: {e}",
        "Failed to get podcast job status: {e}",
        "Failed to list podcast episodes: {e}",
    ):
        assert needle in src, (
            f"v0.7.177 regression: logger.error for {needle!r} is gone. "
            f"The full exception is no longer captured for ops — "
            f"diagnosis becomes impossible."
        )


# ---------------------------------------------------------------------------
# cancel_command_job private-API fallback
# ---------------------------------------------------------------------------


def test_cancel_command_job_guards_private_core_service_import():
    """v0.7.177: the `surreal_commands.core.service.get_command_service`
    import is wrapped in try/ImportError so an upstream rename of
    `core.service` doesn't silently break all job cancellation.

    The fallback path uses a direct repo_query UPDATE on the `command`
    table — same pattern as the lifespan stale-command reaper."""
    src = _read_source("api/command_service.py")

    # The private import is now guarded.
    assert "try:\n                from surreal_commands.core.service import" in src, (
        "v0.7.177 regression: the surreal_commands.core.service "
        "import is no longer wrapped in try/ImportError. An upstream "
        "module-layout change will break ALL cancellation with an "
        "ImportError swallowed by the broad `except Exception` below."
    )
    assert "except ImportError:" in src

    # The fallback to direct UPDATE on the command table is present.
    assert "from deeper_notebook.database.repository import repo_query" in src
    assert "SET status = 'canceled'" in src, (
        "v0.7.177 regression: the direct-UPDATE fallback for "
        "cancel_command_job is gone. Without it, an ImportError on "
        "the private surreal_commands API leaves cancellation broken."
    )


def test_cancel_command_job_handles_command_prefix_consistently():
    """v0.7.177: the fallback path normalizes job_id whether or not
    it already carries the `command:` table prefix — matches the
    pattern surreal_commands uses internally and what callers from
    the routers pass."""
    src = _read_source("api/command_service.py")
    # The prefix handling appears in the fallback block.
    assert 'job_id.startswith("command:")' in src, (
        "v0.7.177 regression: the fallback UPDATE no longer normalizes "
        "the `command:` table prefix. Callers from the router pass "
        "the raw job_id, so without prefix handling the UPDATE will "
        "target the wrong record."
    )


# ---------------------------------------------------------------------------
# Forward-looking migration guard
# ---------------------------------------------------------------------------


def test_every_up_migration_uses_idempotent_defines():
    """v0.7.177: meta-test. Every up migration (.surrealql, NOT
    _down) in the catalog must use `IF NOT EXISTS` or `OVERWRITE`
    on every DEFINE statement, OR be a data-only migration with no
    DEFINE statements at all. This prevents a future contributor
    from adding migration 17+ with the same idempotency footgun
    that v0.7.176 just fixed in 12 and 16."""
    migrations_dir = ROOT / "deeper_notebook" / "database" / "migrations"
    offenders: list[tuple[str, str]] = []
    for path in sorted(migrations_dir.glob("*.surrealql")):
        if "_down" in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped.upper().startswith("DEFINE "):
                continue
            up = stripped.upper()
            if "IF NOT EXISTS" not in up and "OVERWRITE" not in up:
                offenders.append((path.name, stripped))

    assert not offenders, (
        "v0.7.177 forward-guard tripped: at least one up migration "
        "has a DEFINE without IF NOT EXISTS / OVERWRITE. This is "
        "the same footgun v0.7.176 just fixed — without the guard, "
        "re-running after _sbl_migrations rollback / restore / DR "
        "will half-apply the schema. Offenders:\n  - "
        + "\n  - ".join(f"{name}: {line}" for name, line in offenders)
    )
