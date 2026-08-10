"""v0.7.188 — Desktop reliability fixes from the round-9 audit.

Two surfaces tightened that meaningfully improve the user experience
on a flaky network / dead-child failure:

1.  Model downloads (`desktop/model_downloads.py`) migrated from
    `urllib.request.urlopen` to `httpx.stream` with:
      - Resumable downloads via `Range: bytes=<offset>-` against an
        existing `.tmp` file (a 5GB GGUF interrupted at 4.8GB now
        resumes from 4.8GB on next launch instead of byte 0).
      - Per-chunk read timeout (30s) — a stalled CDN connection
        fails fast instead of hanging the launcher forever.
      - `.tmp` PRESERVED on failure (the prior contract deleted it,
        defeating any resume support before it could exist).
      - Defence against servers that ignore Range and return 200
        instead of 206 — we restart from byte 0 to avoid duplicating
        the prefix.

2.  Launcher readiness probes (`desktop/launcher.py::_wait_tcp` +
    `_wait_http`) accept an optional `proc` argument. Between probes
    they `proc.poll()`; a non-None returncode means the child died
    and there is no chance the port/endpoint will come up — raise
    immediately with the exit code. Pre-fix, a crashed-in-200ms
    uvicorn left the user staring at "Starting…" for the full
    180s probe timeout.

3.  (Audited-no-fix) `progress.jsonl` rotation — already implemented
    in v0.5.10. ProgressBus._rotate_if_oversized() rotates to
    `.old` at 2MB on startup. Custom check+rename pattern (not
    RotatingFileHandler) so no Windows concurrency issue.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import httpx

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Readiness probes — early-exit on dead child
# ---------------------------------------------------------------------------


def test_wait_tcp_accepts_proc_argument():
    """v0.7.188: _wait_tcp must accept an optional `proc` keyword
    so callers can plumb in the just-spawned Popen and the probe
    can early-exit when the child dies before binding."""
    src = _read_source("desktop/launcher.py")
    # Signature includes proc kwarg.
    sig_idx = src.find("def _wait_tcp(")
    assert sig_idx != -1
    sig_end = src.find("\n", src.find("):", sig_idx))
    sig = src[sig_idx:sig_end]
    assert "proc" in sig, (
        "v0.7.188 regression: _wait_tcp no longer takes a `proc` "
        "argument. The launcher will hang the full timeout on a "
        "child that crashed in 200ms."
    )


def test_wait_http_accepts_proc_argument():
    """v0.7.188: same early-exit treatment for _wait_http."""
    src = _read_source("desktop/launcher.py")
    sig_idx = src.find("def _wait_http(")
    assert sig_idx != -1
    sig_end = src.find("\n", src.find("):", sig_idx))
    sig = src[sig_idx:sig_end]
    assert "proc" in sig, (
        "v0.7.188 regression: _wait_http no longer takes a `proc` "
        "argument. /readyz wait will hang the full 180s on a dead "
        "uvicorn."
    )


def test_wait_tcp_early_exits_when_proc_dies(monkeypatch):
    """v0.7.188 behavioural: with a proc whose `poll()` returns a
    non-None exit code, _wait_tcp must raise RuntimeError IMMEDIATELY
    — not after the full timeout. We don't want to wait 30s in a
    test, so we set the timeout to 30s but verify the raise happens
    within 2s."""
    import time as _time

    from desktop.launcher import _wait_tcp

    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1  # dead
    fake_proc.returncode = 1

    # Make socket.create_connection always fail so the loop hits
    # the poll check.
    import socket as _socket
    def _always_refuse(*a, **kw):
        raise OSError("connection refused")
    monkeypatch.setattr(_socket, "create_connection", _always_refuse)

    start = _time.monotonic()
    try:
        _wait_tcp("127.0.0.1", 65432, timeout=30, proc=fake_proc)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        elapsed = _time.monotonic() - start
        assert elapsed < 2.0, (
            f"v0.7.188 regression: _wait_tcp took {elapsed:.1f}s to "
            f"detect a dead child — should be near-instant."
        )
        assert "exited rc=1" in str(exc)


# ---------------------------------------------------------------------------
# Model download — resumable httpx.stream
# ---------------------------------------------------------------------------


def test_model_downloads_uses_httpx_stream_not_urllib():
    """v0.7.188: the migration from urllib to httpx is what enables
    Range-header resume and per-chunk read timeouts. A revert would
    lose both."""
    src = _read_source("desktop/model_downloads.py")
    assert "import httpx" in src
    assert "httpx.stream(" in src, (
        "v0.7.188 regression: model_downloads reverted to urllib. "
        "Lose resume support + per-chunk timeout."
    )
    # The bad import must be gone.
    code_only = "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "import urllib.request" not in code_only, (
        "v0.7.188 regression: urllib.request re-imported in "
        "model_downloads. Resume support is broken."
    )


def test_model_downloads_sends_range_header_on_resume():
    """v0.7.188 — the resume path must inspect tmp size before
    constructing the request, and add a Range header when bytes
    have already been written."""
    src = _read_source("desktop/model_downloads.py")
    # The Range-header construction is present in the code.
    assert 'headers["Range"]' in src, (
        "v0.7.188 regression: Range header construction is gone "
        "from model_downloads. Resume support is broken."
    )
    assert 'f"bytes={start_at_byte}-"' in src


def test_model_downloads_preserves_tmp_on_failure():
    """v0.7.188 INVARIANT: on download failure, the partial .tmp
    MUST NOT be deleted. The whole resume design depends on the
    partial surviving across launches.

    Specifically: the `except` block in `_download_one` must NOT
    call `tmp.unlink(...)` — the pre-fix code did, defeating the
    resume support before it could activate.

    Behavioural test: simulate a failure mid-stream and assert
    the .tmp file is still on disk afterward."""
    import tempfile

    from desktop.model_downloads import _download_one

    class _FailingMid:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_bytes(self, chunk_size=None):
            yield b"partial data " * 100  # writes ~1300 bytes
            raise httpx.ReadTimeout("idle stall")

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "model.gguf"
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        import desktop.model_downloads as md
        orig_stream = md.httpx.stream
        md.httpx.stream = lambda *a, **kw: _FailingMid()
        try:
            ok = _download_one("https://example.com/x", dest, "test")
        finally:
            md.httpx.stream = orig_stream
        assert ok is False
        assert tmp.exists(), (
            "v0.7.188 regression: _download_one's except block "
            "deletes the .tmp file on failure. Resume support is "
            "broken — next launch will restart from byte 0."
        )


def test_model_downloads_handles_server_ignoring_range(monkeypatch, tmp_path):
    """v0.7.188 — if the CDN doesn't support Range and returns 200
    (full content) when we asked for 206 (partial), we MUST restart
    from byte 0. Appending would duplicate the prefix and corrupt
    the file."""
    from desktop.model_downloads import _download_one

    dest = tmp_path / "model.gguf"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(b"old partial 1234567890")

    full_content = b"complete fresh download " * 1000  # plenty above min_bytes

    class _FullContentResp:
        status_code = 200  # server ignored our Range request
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_bytes(self, chunk_size=None):
            yield full_content

    monkeypatch.setattr(
        "desktop.model_downloads.httpx.stream",
        lambda *a, **kw: _FullContentResp(),
    )

    ok = _download_one("https://example.com/x", dest, "test")
    assert ok is True
    # File MUST be only the fresh content (not pre-existing + fresh).
    assert dest.read_bytes() == full_content, (
        "v0.7.188 regression: server-ignored-Range path appended "
        "fresh bytes to old partial — file is corrupted."
    )


# ---------------------------------------------------------------------------
# progress.jsonl rotation (audited-no-fix)
# ---------------------------------------------------------------------------


def test_progress_bus_has_size_based_rotation():
    """v0.7.188 — pin that the v0.5.10 rotation is still in place.
    The audit thought this was missing; it wasn't. Forward-guard
    against a future contributor "simplifying" the constructor
    and dropping the rotation check."""
    src = _read_source("desktop/progress.py")
    assert "_MAX_LOG_BYTES" in src, (
        "v0.7.188 regression: ProgressBus lost its size cap. "
        "progress.jsonl will grow unbounded across launches."
    )
    assert "_rotate_if_oversized" in src
