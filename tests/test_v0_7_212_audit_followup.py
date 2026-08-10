"""v0.7.212 — Three follow-up fixes from the v0.7.210 deep-audit
deferred list: bootstrap partial-extraction recovery, mem0 timeout
short-circuit, wizard SSE reader-thread cleanup.

1. **Bootstrap partial-extraction recovery.**
   `extract_python_runtime` previously short-circuited as soon as
   `<runtime_dir>/python/bin/python3` existed — but a half-
   extracted tarball (interrupted by Force Quit / disk-full /
   Time-Machine restore) leaves the interpreter binary AND a
   partial set of stdlib `.so` files. The interpreter can't even
   `import sys`. Now: probe the file with `python -c "import sys,
   encodings; print(sys.version)"` and re-extract on failure.

2. **mem0 backend-down short-circuit.**
   `apply_tool_call` caught all exceptions but didn't tell the
   caller. A turn with 5 facts could spend ~5 minutes pinned on
   dead 60s retries. Now: connection-class exceptions raise
   `_MemoryBackendUnreachable`; the `extract_turn` driver catches
   it and aborts the remaining calls for THIS turn.

3. **Wizard SSE reader-thread leak.**
   `progress_stream` started a daemon thread that called
   `progress_bus.subscribe(timeout=120s)`. If the user closed
   the wizard window, the writer loop broke but the reader sat
   blocked for the full 120s timeout. Now: a
   `threading.Event()` cancel signal is set on writer exit
   (normal or aborted) and the reader checks it between
   subscribe iterations.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1: bootstrap partial-extraction recovery
# ---------------------------------------------------------------------------


def test_bootstrap_has_interpreter_health_probe():
    """v0.7.212 — `_interpreter_is_healthy` must exist and be
    called from `extract_python_runtime` before the early-return
    skip. Otherwise a partial extraction is silently trusted."""
    src = _src("desktop/bootstrap.py")
    assert "def _interpreter_is_healthy(" in src
    assert "if _interpreter_is_healthy(interpreter):" in src
    # The wipe-and-retry path uses shutil.rmtree with ignore_errors.
    assert "shutil.rmtree(runtime_dir, ignore_errors=True)" in src


def test_interpreter_health_probe_returns_false_on_missing():
    """v0.7.212 — runtime probe on a nonexistent path returns
    False (not raise). Caller depends on this for the wipe-and-
    retry decision."""
    from desktop.bootstrap import _interpreter_is_healthy

    result = _interpreter_is_healthy(Path("/nonexistent/python3"))
    assert result is False


def test_interpreter_health_probe_returns_false_on_garbage_file(tmp_path: Path):
    """v0.7.212 — a file that isn't actually a python executable
    must return False (the partial-extraction case). The probe
    catches `OSError`/`subprocess.TimeoutExpired`."""
    from desktop.bootstrap import _interpreter_is_healthy

    fake = tmp_path / "python3"
    fake.write_bytes(b"#!/bin/sh\necho not python\nexit 1\n")
    fake.chmod(0o755)
    # This `executes` (rc=1) but with non-zero exit code, so the
    # probe should return False per the rc=0 check.
    assert _interpreter_is_healthy(fake) is False


# ---------------------------------------------------------------------------
# Fix 2: mem0 backend-down short-circuit
# ---------------------------------------------------------------------------


def test_apply_tool_call_raises_on_connection_error():
    """v0.7.212 — `apply_tool_call` must raise
    `_MemoryBackendUnreachable` (caught by the driver in
    extract_turn) when mem_client.add raises a connection-class
    exception. Logical errors (bad payload, etc.) still fall
    through to the soft-fail path."""
    from desktop.memory.writer import (
        _MemoryBackendUnreachable,
        apply_tool_call,
    )

    mem_client = MagicMock()
    # Use a built-in connection-class exception so the test
    # doesn't depend on httpx import order.
    mem_client.add.side_effect = ConnectionRefusedError("backend down")

    call = {
        "name": "remember_fact",
        "arguments": {"text": "the sky is blue"},
    }
    import pytest
    with pytest.raises(_MemoryBackendUnreachable):
        apply_tool_call(mem_client, call)


def test_apply_tool_call_swallows_logical_errors():
    """v0.7.212 — logical errors (ValueError on bad payload, etc.)
    must NOT raise — they're soft-fail per v0.5.10 behaviour. Only
    connection-class exceptions trip the circuit breaker."""
    from desktop.memory.writer import apply_tool_call

    mem_client = MagicMock()
    mem_client.add.side_effect = ValueError("bad payload")

    call = {
        "name": "remember_fact",
        "arguments": {"text": "the sky is blue"},
    }
    # Must NOT raise.
    apply_tool_call(mem_client, call)


def test_extract_turn_aborts_remaining_facts_on_backend_down():
    """v0.7.212 — `extract_turn` must stop iterating tool calls
    when `_MemoryBackendUnreachable` is raised, so the worker
    doesn't pin on 60s-per-fact dead retries."""
    from desktop.memory import writer as w

    mem_client = MagicMock()
    # First call raises ConnectionRefusedError; second would too,
    # but should never be invoked.
    mem_client.add.side_effect = [
        ConnectionRefusedError("backend down"),
        ConnectionRefusedError("backend down"),
    ]
    llm = MagicMock()
    # Two tool calls; only the first should be attempted.
    llm.complete.return_value = (
        '<tool_call>{"name":"remember_fact","arguments":{"text":"a"}}</tool_call>\n'
        '<tool_call>{"name":"remember_fact","arguments":{"text":"b"}}</tool_call>'
    )

    w.extract_turn(
        llm=llm, mem_client=mem_client,
        chat_session_id="cs:1", user_text="x", assistant_text="y",
    )
    # Only one call attempted before the circuit breaker fired.
    assert mem_client.add.call_count == 1


# ---------------------------------------------------------------------------
# Fix 3: wizard SSE reader-thread cleanup
# ---------------------------------------------------------------------------


def test_wizard_progress_stream_has_reader_cancel_signal():
    """v0.7.212 — `progress_stream` must use a
    `threading.Event()` to signal the reader thread to stop on
    client disconnect. Without this the reader blocks 120s in
    `progress_bus.subscribe(timeout=120)` after every cancelled
    wizard run."""
    src = _src("desktop/first_run/server.py")
    assert "_reader_cancel = threading.Event()" in src
    assert "if _reader_cancel.is_set():" in src
    # The writer's `finally` block must set the cancel so the
    # reader exits on ALL exit paths (normal completion, exception,
    # client disconnect).
    assert "_reader_cancel.set()" in src
    # And ConnectionResetError must be caught around resp.write
    # (the v0.7.212-specific exit path).
    assert "except (ConnectionResetError, asyncio.CancelledError):" in src
