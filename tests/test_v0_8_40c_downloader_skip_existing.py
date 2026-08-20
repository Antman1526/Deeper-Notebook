"""v0.8.40c — downloader skips redownload when the file already exists.

Bug surfaced by the post-v0.8.40b audit: `start_download` deduplicates
only IN-FLIGHT jobs (same repo_id+filename mid-download), not already-
completed downloads. A user who triggers Download → completes → comes
back days later and clicks Download again would re-download the same
multi-GB GGUF for no benefit. With v0.8.40c the second click returns
a synthetic completed job immediately.

Tests:
  - start_download returns status="completed" + no HTTP fired when the
    target file already exists on disk.
  - The synthetic completed job does NOT poison the in-flight dedupe
    registry — a SUBSEQUENT call after deleting the file kicks off a
    real download.
  - Zero-byte existing file is NOT treated as "already downloaded"
    (matches the v0.8.39 inventory filter — zero-byte = failed prior
    download).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from deeper_notebook.local_models import downloader as dl_mod


@pytest.fixture(autouse=True)
def _reset_jobs():
    dl_mod.reset_for_tests()
    yield
    dl_mod.reset_for_tests()


@pytest.mark.asyncio
async def test_start_download_skips_when_final_already_exists(tmp_path):
    """Existing non-empty .gguf at dest_dir/filename → start_download
    returns a completed job immediately without firing any HTTP."""
    # Pre-create the "already downloaded" file
    existing = tmp_path / "model.gguf"
    existing.write_bytes(b"FAKE-EXISTING-GGUF-CONTENT")

    # If httpx.AsyncClient ever gets called, fail loudly.
    def _explode_async_client(*a, **k):
        raise AssertionError(
            "httpx.AsyncClient called even though file already exists",
        )

    with patch(
        "deeper_notebook.local_models.downloader.httpx.AsyncClient",
        _explode_async_client,
    ):
        job = await dl_mod.start_download(
            "bartowski/Some-Model-GGUF",
            "model.gguf",
            tmp_path,
        )

    assert job.status == "completed"
    assert job.target_path == str(existing)
    # The synthetic job reports the file's size so the UI can show it
    # as 100% done.
    assert job.bytes_total == len(b"FAKE-EXISTING-GGUF-CONTENT")
    assert job.bytes_downloaded == job.bytes_total
    # No background task should have been spawned (the synthetic job
    # is complete from the start).
    assert job._task is None


@pytest.mark.asyncio
async def test_start_download_does_not_poison_registry_after_skip(tmp_path):
    """If the user deletes the file and triggers download again, the
    real download path runs (not stuck on the synthetic completed job).
    Verifies the skip-existing path doesn't leak into the in-flight
    dedupe."""
    f = tmp_path / "model.gguf"
    f.write_bytes(b"x" * 100)

    # First call — file exists, skip.
    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient"):
        first = await dl_mod.start_download("r/x", "model.gguf", tmp_path)
    assert first.status == "completed"

    # User deletes the file.
    f.unlink()

    # Second call — file gone; should start a real download.
    # Mock httpx to return a tiny payload so the background task
    # completes cleanly.
    fake_bytes = b"NEW-DOWNLOAD-PAYLOAD"

    class _R:
        status_code = 200
        headers = {"content-length": str(len(fake_bytes))}

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield fake_bytes

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
        second = await dl_mod.start_download("r/x", "model.gguf", tmp_path)
        # Real download was kicked off — should have a background task.
        assert second._task is not None
        await asyncio.wait_for(second._task, timeout=5.0)

    assert second.status == "completed"
    assert (tmp_path / "model.gguf").read_bytes() == fake_bytes
    # The two jobs must have different IDs — the skip-existing one
    # shouldn't be cached and returned for the real second call.
    assert first.job_id != second.job_id


@pytest.mark.asyncio
async def test_start_download_does_not_skip_zero_byte_stub(tmp_path):
    """A 0-byte file at the target path is a failed prior download
    artifact, not "already downloaded". Must trigger a real download.
    Matches the v0.8.39 inventory's _is_gguf_candidate filter."""
    stub = tmp_path / "model.gguf"
    stub.write_bytes(b"")  # zero-byte

    fake_bytes = b"REAL-PAYLOAD"

    class _R:
        status_code = 200
        headers = {"content-length": str(len(fake_bytes))}

        def raise_for_status(self):
            pass

        async def aiter_bytes(self, chunk_size=1024 * 1024):
            yield fake_bytes

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
        job = await dl_mod.start_download("r/x", "model.gguf", tmp_path)
        assert job._task is not None
        await asyncio.wait_for(job._task, timeout=5.0)

    assert job.status == "completed"
    assert (tmp_path / "model.gguf").read_bytes() == fake_bytes
