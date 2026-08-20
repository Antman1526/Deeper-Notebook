"""ONP v0.6.16 — Regression test for streamed file uploads.

save_uploaded_file used to do `content = await upload_file.read()` which
buffered the entire payload into memory before writing. For a 500 MB upload
that's 500 MB of RAM, plus a peak spike during f.write(content). On a
constrained machine (8 GB Mac, several concurrent uploads, podcast worker
running) this OOMs the API process.

The fix streams in 1 MiB chunks. These tests confirm:
  1. save_uploaded_file calls upload_file.read(size) with a chunk size,
     not the unbounded read() — proves the streaming pattern is in place
     and won't regress to the buffered version.
  2. The function correctly writes ALL chunks (no truncation).
  3. Cleanup on exception still works (the existing try/except path).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api.routers import sources as sources_mod


class _FakeUploadFile:
    """Mimics fastapi.UploadFile enough for save_uploaded_file.

    Tracks every call to read() so the test can assert the chunked pattern.
    """

    def __init__(self, filename: str, payload: bytes):
        self.filename = filename
        self._buffer = io.BytesIO(payload)
        self.read_calls: list[int | None] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_calls.append(size)
        if size < 0:
            return self._buffer.read()
        return self._buffer.read(size)


@pytest.mark.asyncio
async def test_save_uploaded_file_streams_in_chunks(tmp_path, monkeypatch):
    """The streaming fix: read() must be called with a bounded chunk size,
    never the unbounded read() that buffers the entire upload."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))
    payload = b"A" * (1024 * 1024 * 3 + 500)  # 3.000476 MiB — straddles 3 chunks
    f = _FakeUploadFile("biggish.bin", payload)

    saved_path = await sources_mod.save_uploaded_file(f)

    # The streaming pattern: every read() call had a positive chunk size.
    assert f.read_calls, "expected upload_file.read to have been called"
    for size in f.read_calls:
        assert size is not None and size > 0, (
            f"save_uploaded_file regressed to unbounded read() (size={size})"
        )
    # Multiple read() calls — proves it streamed rather than slurped.
    assert len(f.read_calls) >= 3

    # And the saved file has all of the bytes, none missing.
    assert Path(saved_path).read_bytes() == payload


@pytest.mark.asyncio
async def test_save_uploaded_file_handles_small_files(tmp_path, monkeypatch):
    """A small file fits in one chunk — but still flows through the streaming
    loop. Result must be correct."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))
    payload = b"tiny payload"
    f = _FakeUploadFile("tiny.txt", payload)

    saved_path = await sources_mod.save_uploaded_file(f)
    assert Path(saved_path).read_bytes() == payload


@pytest.mark.asyncio
async def test_save_uploaded_file_cleans_up_on_write_failure(tmp_path, monkeypatch):
    """If something explodes mid-write, the partial file must be deleted
    (pre-existing behavior the streaming refactor preserves)."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))

    class _ExplodingFile(_FakeUploadFile):
        async def read(self, size: int = -1) -> bytes:
            raise IOError("simulated read failure")

    f = _ExplodingFile("kaboom.bin", b"")
    with pytest.raises(IOError):
        await sources_mod.save_uploaded_file(f)

    # No leftover file in the upload folder
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"expected no leftover files, got {leftovers}"


@pytest.mark.asyncio
async def test_save_uploaded_file_enforces_max_bytes_mid_stream(tmp_path, monkeypatch):
    """v0.7.1 Issue #1 regression: chunked-transfer uploads bypass the
    UploadFile.size pre-check. save_uploaded_file's max_bytes kwarg must
    abort mid-stream when the cap is exceeded, regardless of whether
    Content-Length was set. Without this, an authenticated client can
    stream arbitrarily large files to disk via chunked transfer encoding."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))
    # Build a file that's 5 MB total. Cap it at 1 MB. Must abort early.
    payload = b"X" * (5 * 1024 * 1024)
    f = _FakeUploadFile("oversize.bin", payload)

    with pytest.raises(ValueError, match=r"exceeds size limit"):
        await sources_mod.save_uploaded_file(f, max_bytes=1 * 1024 * 1024)

    # No leftover file in the upload folder (cleanup path ran)
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"expected partial file cleanup, got {leftovers}"


@pytest.mark.asyncio
async def test_save_uploaded_file_allows_files_under_max_bytes(tmp_path, monkeypatch):
    """Control: a file UNDER the cap saves successfully without raising."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))
    payload = b"Y" * 512  # 512 bytes
    f = _FakeUploadFile("ok.bin", payload)

    saved = await sources_mod.save_uploaded_file(f, max_bytes=1024)
    assert Path(saved).read_bytes() == payload


@pytest.mark.asyncio
async def test_save_uploaded_file_does_not_overwrite_racing_upload(
    tmp_path, monkeypatch
):
    """If another upload creates the selected name just before open(),
    save_uploaded_file must choose a fresh path instead of truncating it."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))

    racing_path = tmp_path / "same-name.pdf"
    fallback_path = tmp_path / "same-name (1).pdf"

    def _racing_unique_filename(_filename, _upload_folder):
        if not racing_path.exists():
            racing_path.write_bytes(b"first upload")
            return str(racing_path)
        return str(fallback_path)

    monkeypatch.setattr(
        sources_mod,
        "generate_unique_filename",
        _racing_unique_filename,
    )

    f = _FakeUploadFile("same-name.pdf", b"second upload")

    saved = await sources_mod.save_uploaded_file(f)

    assert Path(saved) == fallback_path
    assert racing_path.read_bytes() == b"first upload"
    assert fallback_path.read_bytes() == b"second upload"


@pytest.mark.asyncio
async def test_save_uploaded_file_no_cap_when_max_bytes_is_none(tmp_path, monkeypatch):
    """Backward-compat: existing callers that don't pass max_bytes
    keep the prior unbounded behavior (caller is responsible for
    enforcement at a higher layer)."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))
    payload = b"Z" * (2 * 1024 * 1024)  # 2 MB
    f = _FakeUploadFile("big.bin", payload)

    saved = await sources_mod.save_uploaded_file(f)  # no max_bytes
    assert Path(saved).read_bytes() == payload
