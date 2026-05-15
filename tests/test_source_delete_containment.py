"""ONP v0.6.34 — Regression test for Source.delete() file-path containment.

Pre-fix, Source.delete() did:
    if file_path.exists():
        os.unlink(file_path)

…with NO check that file_path was inside UPLOADS_FOLDER. If the DB ever
contained a malicious asset.file_path (raw SurrealQL injection, future
unaudited write path, manual db edit), deletion would happily unlink
arbitrary files the API process can write to.

The create path (api/routers/sources.py:358) already validates
containment via startswith(uploads + os.sep). Symmetry: delete now does
the same via Path.is_relative_to.

This test plants a Source whose asset.file_path points OUTSIDE the
uploads folder, calls .delete(), and asserts the outside file is
untouched. It uses a MagicMock for the parent ObjectModel.delete() so we
don't need a live SurrealDB.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.domain.notebook import Asset, Source


@pytest.mark.asyncio
async def test_source_delete_refuses_path_outside_uploads(tmp_path, monkeypatch):
    """The actual v0.6.34 regression test. Plant a source whose
    asset.file_path is a sibling of UPLOADS_FOLDER (legitimate-looking but
    OUTSIDE it). Call .delete(). Confirm the file still exists."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    # Victim file outside uploads — adversary's target
    victim = tmp_path / "important_data.txt"
    victim.write_text("DO NOT DELETE ME")

    # Patch UPLOADS_FOLDER on the config module so the lazy import inside
    # Source.delete sees our test value
    monkeypatch.setattr(
        "open_notebook.config.UPLOADS_FOLDER", str(uploads),
    )

    source = Source(
        id="source:malicious",
        asset=Asset(file_path=str(victim)),
        title="Tampered",
    )

    # Stub the parent class's delete() so we don't hit SurrealDB
    with patch(
        "open_notebook.domain.notebook.ObjectModel.delete",
        new=AsyncMock(return_value=True),
    ), patch(
        "open_notebook.domain.notebook.repo_query",
        new=AsyncMock(return_value=[]),
    ):
        await source.delete()

    # The crucial assertion: the file OUTSIDE uploads is still there.
    assert victim.exists(), (
        "Source.delete() unlinked a file outside UPLOADS_FOLDER — "
        "containment check failed"
    )
    assert victim.read_text() == "DO NOT DELETE ME"


@pytest.mark.asyncio
async def test_source_delete_does_remove_file_inside_uploads(tmp_path, monkeypatch):
    """Control test: a legitimate file inside UPLOADS_FOLDER should still
    be deleted. We don't want the new containment check to over-correct
    and break normal deletes."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    real_file = uploads / "legitimate.pdf"
    real_file.write_bytes(b"pdf content")

    monkeypatch.setattr(
        "open_notebook.config.UPLOADS_FOLDER", str(uploads),
    )

    source = Source(
        id="source:real",
        asset=Asset(file_path=str(real_file)),
        title="Legit",
    )

    with patch(
        "open_notebook.domain.notebook.ObjectModel.delete",
        new=AsyncMock(return_value=True),
    ), patch(
        "open_notebook.domain.notebook.repo_query",
        new=AsyncMock(return_value=[]),
    ):
        await source.delete()

    assert not real_file.exists(), (
        "Source.delete() did NOT delete a file inside UPLOADS_FOLDER — "
        "the containment check over-rejected"
    )


@pytest.mark.asyncio
async def test_source_delete_handles_dotdot_traversal_in_db(tmp_path, monkeypatch):
    """A DB-stored file_path containing `..` segments must resolve OUTSIDE
    uploads (after `.resolve()`) and be refused."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    victim = tmp_path / "secret.key"
    victim.write_text("api-key-data")

    monkeypatch.setattr(
        "open_notebook.config.UPLOADS_FOLDER", str(uploads),
    )

    # An attacker-crafted file_path that LOOKS like it's inside uploads
    # but actually escapes via `..`
    malicious_path = str(uploads / ".." / "secret.key")
    assert Path(malicious_path).resolve() == victim.resolve()  # confirms escape

    source = Source(
        id="source:tampered",
        asset=Asset(file_path=malicious_path),
        title="Tampered",
    )

    with patch(
        "open_notebook.domain.notebook.ObjectModel.delete",
        new=AsyncMock(return_value=True),
    ), patch(
        "open_notebook.domain.notebook.repo_query",
        new=AsyncMock(return_value=[]),
    ):
        await source.delete()

    assert victim.exists(), (
        "Source.delete() followed a ../ traversal from the DB-stored "
        "file_path and unlinked the victim file"
    )


@pytest.mark.asyncio
async def test_source_delete_skips_when_asset_is_none(monkeypatch):
    """Source with no asset → file-cleanup branch must short-circuit
    cleanly. Don't crash on a None reference."""
    source = Source(id="source:no-asset", asset=None, title="No file")
    with patch(
        "open_notebook.domain.notebook.ObjectModel.delete",
        new=AsyncMock(return_value=True),
    ), patch(
        "open_notebook.domain.notebook.repo_query",
        new=AsyncMock(return_value=[]),
    ):
        result = await source.delete()  # should not raise
    assert result is True
