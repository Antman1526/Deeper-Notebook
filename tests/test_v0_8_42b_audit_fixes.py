"""v0.8.42b — Audit-fix tests for two HIGH-severity findings against
the v0.8.39e/v0.8.40b code.

Both findings caught by an external audit after the v0.8.42 ship:

  1. **`Supervisor.hot_swap_chat` n_ctx rollback** —
     `hot_swap_chat` updates `chat_llm_path` BEFORE calling
     `restart_sidecar("chat")`. On respawn failure, the path is
     rolled back to `old_path` but `chat_llm_n_ctx` keeps the
     newly-resolved value. Next retry sees a mismatched n_ctx
     for the rolled-back path. Documented intent was full rollback.

  2. **Downloader Content-Range mismatch detection** —
     v0.8.39e's `_stream_download` rejects 200-responses to Range
     requests (server doesn't support Range → would corrupt the
     append by duplicating leading bytes). It does NOT verify
     that a 206 response's `Content-Range` header actually starts
     at the requested offset. A broken / malicious mirror could
     return 206 with a mismatched range and silently corrupt
     the file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from deeper_notebook.local_models import downloader as dl_mod


@pytest.fixture(autouse=True)
def _reset_jobs():
    dl_mod.reset_for_tests()
    yield
    dl_mod.reset_for_tests()


# ---------------------------------------------------------------------------
# Finding #1 — hot_swap_chat n_ctx rollback
# ---------------------------------------------------------------------------


def test_hot_swap_chat_restores_n_ctx_on_restart_failure(tmp_path):
    """When `restart_sidecar` returns ok=False, BOTH
    `chat_llm_path` AND `chat_llm_n_ctx` must be restored to their
    pre-swap values. Otherwise a retry sees a mismatched n_ctx for
    the old GGUF path."""
    from desktop.launcher import Supervisor

    # Build a partial Supervisor without going through start_all —
    # the rollback path only reads/writes a handful of attributes.
    sup = Supervisor.__new__(Supervisor)
    sup.cfg = MagicMock(model_dir=tmp_path)
    # Pre-swap state.
    old_gguf = tmp_path / "old.gguf"
    old_gguf.write_bytes(b"x" * 16)
    new_gguf = tmp_path / "new.gguf"
    new_gguf.write_bytes(b"y" * 32)
    sup.chat_llm_path = old_gguf
    sup.chat_llm_n_ctx = 8192  # what the old GGUF was bound at

    # Patch _resolve_chat_llm_n_ctx so the "new" GGUF resolves to a
    # different value. After rollback we expect to see the OLD value
    # again (8192) — not the resolved-from-new 65536.
    resolve_calls = [65536]  # first call returns the new value

    def _fake_resolve():
        return resolve_calls.pop(0) if resolve_calls else 8192

    sup._resolve_chat_llm_n_ctx = _fake_resolve

    # restart_sidecar returns failure to trigger the rollback path.
    def _fail_restart(kind):
        return False, "Simulated spawn failure"

    sup.restart_sidecar = _fail_restart

    ok, detail = sup.hot_swap_chat(str(new_gguf))

    assert ok is False
    assert "failed" in detail.lower()
    # Both attributes restored.
    assert sup.chat_llm_path == old_gguf
    assert sup.chat_llm_n_ctx == 8192, (
        f"n_ctx not rolled back — saw {sup.chat_llm_n_ctx}, "
        f"expected 8192 (the pre-swap value)"
    )


# ---------------------------------------------------------------------------
# Finding #2 — Content-Range mismatch detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_aborts_when_content_range_doesnt_match_request(tmp_path):
    """Server returns 206 with a Content-Range that does NOT match
    the requested offset. Appending the bytes would corrupt the file
    (bytes don't line up with the .part contents). Stream must
    detect + fail clearly without writing."""
    # 1500-byte partial file → request should be `bytes=1500-`
    part = tmp_path / "x.gguf.part"
    part.write_bytes(b"P" * 1500)

    class _MismatchResp:
        status_code = 206
        # Mirror returns bytes 0-1499 instead of 1500-* → mismatch!
        headers = {
            "content-length": "1500",
            "content-range": "bytes 0-1499/3000",
        }

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield b"X" * 1500  # never written if guard works

    class _Ctx:
        async def __aenter__(self):
            return _MismatchResp()

        async def __aexit__(self, *_a):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            pass

        def stream(self, m, u, headers=None):
            return _Ctx()

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient", _Client):
        job = await dl_mod.start_download("r/a", "x.gguf", tmp_path)
        await asyncio.wait_for(job._task, timeout=5.0)

    assert job.status == "failed"
    # Error mentions Content-Range OR mismatch so operators can find it.
    err_lower = (job.error or "").lower()
    assert "range" in err_lower or "offset" in err_lower, (
        f"expected error to mention range/offset, got {job.error!r}"
    )
    # .part file is unchanged (bad response detected BEFORE the open).
    assert part.stat().st_size == 1500


@pytest.mark.asyncio
async def test_resume_accepts_matching_content_range(tmp_path):
    """Regression guard: a CORRECT 206 with a Content-Range starting
    at the requested offset must still work. The new mismatch check
    must not over-reject the happy path."""
    part = tmp_path / "x.gguf.part"
    part.write_bytes(b"P" * 800)

    new_bytes = b"N" * 2200  # 3000 total when combined

    class _GoodResp:
        status_code = 206
        headers = {
            "content-length": "2200",
            "content-range": "bytes 800-2999/3000",
        }

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield new_bytes

    class _Ctx:
        async def __aenter__(self):
            return _GoodResp()

        async def __aexit__(self, *_a):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            pass

        def stream(self, m, u, headers=None):
            return _Ctx()

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient", _Client):
        job = await dl_mod.start_download("r/a", "x.gguf", tmp_path)
        await asyncio.wait_for(job._task, timeout=5.0)

    assert job.status == "completed", f"job.error={job.error}"
    # Combined file = original 800 + appended 2200 = 3000
    final = tmp_path / "x.gguf"
    assert final.exists()
    assert final.stat().st_size == 3000
