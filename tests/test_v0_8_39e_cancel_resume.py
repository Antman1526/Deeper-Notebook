"""v0.8.39e — download cancel + resume tests.

No real network; mock httpx at the stream layer.

Cancel covers:
  - cancel_job sets the flag; the stream loop sets status="cancelled"
    on the NEXT chunk boundary and tears down.
  - cancel_job on a terminal job returns False with a clear detail
    (HTTP layer maps to 409).
  - cancel_job on an unknown id returns False.
  - POST /downloads/{id}/cancel endpoint: happy path 200, 404 for
    unknown, 409 for terminal.

Resume covers:
  - start_download detects an existing .part file and seeds
    resume_from_bytes.
  - _stream_download sends a Range header when resume_from > 0.
  - A 200 response to a Range request → status="failed" (server
    doesn't support Range; corruption guard).
  - Content-Range header populates bytes_total correctly during resume.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models import downloader as dl_mod


@pytest.fixture(autouse=True)
def _reset_jobs():
    dl_mod.reset_for_tests()
    yield
    dl_mod.reset_for_tests()


# ---------------------------------------------------------------------------
# cancel_job behavior
# ---------------------------------------------------------------------------


def test_cancel_job_unknown_id_returns_false():
    ok, detail = dl_mod.cancel_job("does-not-exist")
    assert ok is False
    assert "Unknown" in detail


@pytest.mark.asyncio
async def test_cancel_job_in_flight_sets_flag(tmp_path):
    """A queued or downloading job → cancel sets the flag, ok=True."""
    # Build a job in queued state without firing a real download.
    job = dl_mod.DownloadJob(
        job_id="j1",
        repo_id="r/a",
        filename="x.gguf",
        target_path=str(tmp_path / "x.gguf"),
        status="downloading",
    )
    dl_mod._JOBS[job.job_id] = job
    ok, _detail = dl_mod.cancel_job("j1")
    assert ok is True
    assert job.cancelled is True


@pytest.mark.asyncio
async def test_cancel_job_already_terminal_returns_409_shape(tmp_path):
    """Idempotent — calling cancel on a terminal job returns False
    with a status-aware detail. The HTTP layer maps this to 409."""
    job = dl_mod.DownloadJob(
        job_id="j2",
        repo_id="r/a",
        filename="x.gguf",
        target_path=str(tmp_path / "x.gguf"),
        status="completed",
    )
    dl_mod._JOBS[job.job_id] = job
    ok, detail = dl_mod.cancel_job("j2")
    assert ok is False
    assert "completed" in detail


# ---------------------------------------------------------------------------
# _stream_download cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_aborts_on_cancellation_flag(tmp_path):
    """Set job.cancelled before the second chunk; the loop should
    terminate with status="cancelled" and leave the .part file on
    disk (NOT renamed to the final path)."""
    # Build a small payload split into 2 chunks; cancellation sets
    # in between.
    chunks_emitted: list[bytes] = []

    class _SlowResp:
        status_code = 200
        headers = {"content-length": "2000"}

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            # Yield the first chunk, let the loop set cancelled,
            # then a second one — but the loop check should fire
            # BEFORE this second yield is processed.
            yield b"x" * 1000
            chunks_emitted.append(b"chunk1")
            yield b"y" * 1000  # never written

    class _Ctx:
        async def __aenter__(self):
            return _SlowResp()

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

    job = dl_mod.DownloadJob(
        job_id="j3",
        repo_id="r/a",
        filename="x.gguf",
        target_path=str(tmp_path / "x.gguf"),
    )

    async def _drive():
        # Cancel immediately so the FIRST chunk-boundary check trips.
        job.cancelled = True
        await dl_mod._stream_download(job, tmp_path)

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient", _Client):
        await asyncio.wait_for(_drive(), timeout=5.0)

    assert job.status == "cancelled"
    # Final file NOT renamed.
    assert not (tmp_path / "x.gguf").exists()


# ---------------------------------------------------------------------------
# Resume — start_download seeds resume_from_bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_download_detects_existing_part_file(tmp_path):
    """Pre-existing .part file from a prior cancelled/crashed run →
    next start_download seeds resume_from_bytes from the file size.
    The background task is what actually applies the Range header
    (covered separately below); here we only verify the seed."""
    part = tmp_path / "x.gguf.part"
    part.write_bytes(b"P" * 1500)

    # Block the stream so we can inspect job state before it runs.
    class _R:
        status_code = 206  # partial content for the Range request
        headers = {"content-length": "1500", "content-range": "bytes 1500-2999/3000"}

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield b""

    class _Ctx:
        async def __aenter__(self):
            return _R()

        async def __aexit__(self, *_a):
            pass

    captured_headers = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            pass

        def stream(self, m, u, headers=None):
            captured_headers.append(dict(headers or {}))
            return _Ctx()

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient", _Client):
        job = await dl_mod.start_download("r/a", "x.gguf", tmp_path)
        await asyncio.wait_for(job._task, timeout=5.0)

    # Resume seed was captured at start_download time.
    assert job.resume_from_bytes == 1500
    # And the stream actually sent a Range header.
    assert captured_headers
    assert captured_headers[0].get("Range") == "bytes=1500-"
    # Total derived from Content-Range, not Content-Length.
    assert job.bytes_total == 3000


# ---------------------------------------------------------------------------
# Range corruption guard — server returning 200 to a Range request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_aborts_when_server_returns_200(tmp_path):
    """A server that returns 200 to a Range request is sending the
    FULL file (not the requested suffix). Appending those bytes to
    the existing .part file would duplicate the leading bytes and
    corrupt the GGUF. Stream must detect + fail clearly."""
    part = tmp_path / "x.gguf.part"
    part.write_bytes(b"P" * 800)

    class _R:
        status_code = 200  # mirror that ignored Range
        headers = {"content-length": "3000"}

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield b"x" * 3000

    class _Ctx:
        async def __aenter__(self):
            return _R()

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
    assert "Range" in (job.error or "")
    # .part file is unchanged (we caught the bad response BEFORE
    # opening the file for append). Verify by size.
    assert part.stat().st_size == 800


# ---------------------------------------------------------------------------
# Endpoint /cancel
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a


def test_cancel_endpoint_404_for_unknown_job(app):
    with TestClient(app) as client:
        resp = client.post("/api/local-models/downloads/unknown-xyz/cancel")
    assert resp.status_code == 404


def test_cancel_endpoint_409_when_already_terminal(app, tmp_path):
    job = dl_mod.DownloadJob(
        job_id="j-done",
        repo_id="r/a",
        filename="x.gguf",
        target_path=str(tmp_path / "x.gguf"),
        status="completed",
    )
    dl_mod._JOBS[job.job_id] = job

    with TestClient(app) as client:
        resp = client.post("/api/local-models/downloads/j-done/cancel")
    assert resp.status_code == 409
    assert "completed" in resp.json()["detail"]


def test_cancel_endpoint_happy_path_sets_flag(app, tmp_path):
    job = dl_mod.DownloadJob(
        job_id="j-flag",
        repo_id="r/a",
        filename="x.gguf",
        target_path=str(tmp_path / "x.gguf"),
        status="downloading",
    )
    dl_mod._JOBS[job.job_id] = job

    with TestClient(app) as client:
        resp = client.post("/api/local-models/downloads/j-flag/cancel")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert job.cancelled is True
