"""v0.7.202 — closeout pass on the LOW-tier deferred items from
v0.7.201's audit.

Five fixes:

1. credentials_service discovery branches: per-call `timeout=10.0`
   / `timeout=30.0` kwargs REPLACED the client-level structured
   Timeout (connect=5/read=30/write=10/pool=5). Partially undid
   v0.7.187. Dropped per-call kwargs so the client's budgets apply.

2. command_service.list_command_jobs: was emitting raw
   `str(row.get("created"))` which renders as
   `surrealdb.DateTime(...)` repr in some driver versions —
   breaks Safari `new Date()`. Use the iso() helper the rest of
   the codebase standardised on.

3. main.py /healthz/deep: `checks["database"]` and
   `checks["migrations"]` were dict-accessed without verifying
   they'd been populated; any exception in the probe path before
   the assignment yielded a KeyError that the framework rendered
   as 500-stack-trace instead of the structured 503 health
   payload operators expect.

4. NoteEditorDialog: `if (!notebookId) { console.error; return }`
   gave the user zero feedback after clicking Save. Added a
   toast so the failure is visible.

5. use-sources.ts: `useSourceStatus` polled every 2s while
   status ∈ {new, queued, running} with no cumulative cap. A
   stuck-running worker polled forever. After 15 min (450 ticks)
   fall back to 30s background pulse.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_credentials_service_drops_per_call_timeouts():
    """v0.7.202 — none of the discovery branches must pass
    `timeout=10.0` or `timeout=30.0` to `client.get(...)`. The
    client-level `_DISCOVERY_HTTP_TIMEOUT` (structured connect/
    read/write/pool budgets) must own the contract."""
    src = _src("api/credentials_service.py")
    # Strip Python comments so historical-rationale blocks don't
    # false-positive the regex.
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "timeout=10.0" not in code_only, (
        "v0.7.202 regression: per-call timeout=10.0 kwarg restored "
        "in credentials_service. Partially undoes v0.7.187 "
        "structured-timeout fix."
    )
    assert "timeout=30.0" not in code_only, (
        "v0.7.202 regression: per-call timeout=30.0 kwarg restored."
    )


def test_command_service_uses_iso_for_list_jobs():
    """v0.7.202 — list_command_jobs must use iso() for created/
    updated columns, not raw str(). Driver-version-dependent
    surrealdb.DateTime repr breaks Safari new Date()."""
    src = _src("api/command_service.py")
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert (
        'str(row.get("created")) if row.get("created") else None'
        not in code_only
    ), (
        "v0.7.202 regression: list_command_jobs reverted to raw "
        "str(row.get('created')). Safari new Date() breaks."
    )
    # Must use iso() helper instead.
    assert '"created": iso(row.get("created"))' in src
    assert '"updated": iso(row.get("updated"))' in src


def test_healthz_deep_has_defensive_check_defaults():
    """v0.7.202 — /healthz/deep populates `checks["database"]` and
    `checks["migrations"]` with `{"ok": False, ...}` defaults at
    the top of the function. Otherwise any exception in the probe
    path before assignment KeyErrors out and renders 500-stack
    instead of the structured 503 payload."""
    src = _src("api/main.py")
    # Pin the defensive-default block by its v0.7.202 marker.
    assert (
        'checks["database"] = {"ok": False, "status": "unknown"}'
        in src
    )
    assert 'checks["migrations"] = {"ok": False}' in src


def test_note_editor_dialog_shows_toast_on_missing_notebook_id():
    """v0.7.202 — NoteEditorDialog must show a toast when
    `notebookId` is missing on Save, not silently swallow the
    click via `console.error + return`. Otherwise the user
    watches the dialog freeze with no feedback."""
    src = _src("frontend/src/app/(dashboard)/notebooks/components/NoteEditorDialog.tsx")
    assert "useToast" in src
    # The toast call must be inside the !notebookId branch.
    assert "Cannot create note without notebook_id" in src
    # And the v0.7.202 marker for the toast addition.
    assert "v0.7.202 — was silent" in src


def test_source_status_polling_has_cumulative_cap():
    """v0.7.202 — useSourceStatus must back off from 2 s to 30 s
    after ~15 min (450 ticks) of consecutive polls without status
    changing. Otherwise a stuck-running worker polls the API
    forever for sources the user has abandoned."""
    src = _src("frontend/src/lib/hooks/use-sources.ts")
    # Pin the backoff threshold + interval explicitly so a careless
    # refactor that drops them is caught.
    assert "ticks > 450" in src, (
        "v0.7.202 regression: cumulative-poll cap removed from "
        "useSourceStatus. Stuck workers will burn API requests "
        "forever."
    )
    assert "return 30000" in src
