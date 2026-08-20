"""v0.7.16 — regression tests for /api/sources upload byte cap.

Before v0.7.16, the only ceiling on /api/sources POST was the Next.js
proxy limit. Authenticated direct hits to the API (Docker, pywebview
shell, scripted clients) had no cap and could fill the local disk.
v0.7.1 had already added max_bytes to save_uploaded_file and used it
in the Studio router; this commit applies the same cap to the main
source endpoint.

These tests focus on the helper `_source_upload_max_bytes` + the
413/save_uploaded_file integration.
"""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from api.routers import sources as sources_mod

# ---------------------------------------------------------------------------
# _source_upload_max_bytes — env-driven helper
# ---------------------------------------------------------------------------


def test_default_cap_500mb(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", raising=False)
    assert sources_mod._source_upload_max_bytes() == 500 * 1024 * 1024


def test_env_raises_cap(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", str(2 * 1024**3)
    )  # 2 GB
    assert sources_mod._source_upload_max_bytes() == 2 * 1024**3


def test_env_lowers_cap(monkeypatch):
    """Tight-disk users can shrink the cap below the default."""
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", str(50 * 1024**2)
    )  # 50 MB
    assert sources_mod._source_upload_max_bytes() == 50 * 1024**2


def test_garbage_env_falls_back(monkeypatch):
    """Non-int env value → default, no crash."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", "five-hundred")
    assert sources_mod._source_upload_max_bytes() == 500 * 1024 * 1024


def test_too_low_env_falls_back(monkeypatch):
    """Below 1 MB is almost certainly a typo (rejects every legit
    upload) — fall back to default."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", "100")
    assert sources_mod._source_upload_max_bytes() == 500 * 1024 * 1024


def test_zero_env_falls_back(monkeypatch):
    """Zero is the same typo class as 100 — fall back."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", "0")
    assert sources_mod._source_upload_max_bytes() == 500 * 1024 * 1024


# ---------------------------------------------------------------------------
# save_uploaded_file integration — the cap actually rejects oversize uploads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_oversize(monkeypatch, tmp_path):
    """A file larger than max_bytes raises ValueError mid-stream;
    partial file is cleaned up. This is the v0.7.1 path being reused."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))

    # 3 MB of bytes, cap at 1 MB → must raise
    payload = b"X" * (3 * 1024 * 1024)
    upload_file = UploadFile(filename="big.txt", file=io.BytesIO(payload))

    with pytest.raises(ValueError) as exc_info:
        await sources_mod.save_uploaded_file(upload_file, max_bytes=1024 * 1024)

    assert "exceeds size limit" in str(exc_info.value)
    # Partial file should be cleaned up — no orphans left behind
    leftover = list(tmp_path.glob("big*"))
    assert leftover == [], f"Partial upload not cleaned: {leftover}"


@pytest.mark.asyncio
async def test_save_uploaded_file_accepts_at_cap(monkeypatch, tmp_path):
    """File at exactly the cap is accepted (boundary is `>`, not `>=`)."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))

    cap = 2 * 1024 * 1024
    payload = b"A" * cap
    upload_file = UploadFile(filename="ok.txt", file=io.BytesIO(payload))

    result = await sources_mod.save_uploaded_file(upload_file, max_bytes=cap)
    # File saved successfully
    from pathlib import Path

    assert Path(result).exists()
    assert Path(result).stat().st_size == cap


@pytest.mark.asyncio
async def test_save_uploaded_file_with_no_cap_accepts_large(monkeypatch, tmp_path):
    """Backward compat — max_bytes=None means no cap (Studio path was
    the only caller before v0.7.1; other callers must still work)."""
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(tmp_path))

    payload = b"Y" * (5 * 1024 * 1024)
    upload_file = UploadFile(filename="large.txt", file=io.BytesIO(payload))

    # No max_bytes → no rejection
    result = await sources_mod.save_uploaded_file(upload_file, max_bytes=None)
    from pathlib import Path

    assert Path(result).exists()
