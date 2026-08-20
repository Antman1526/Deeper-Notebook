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

import asyncio
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain.notebook import Asset, Source


def _source_for(path: Path, *, source_id: str = "source:file") -> Source:
    return Source(
        id=source_id,
        asset=Asset(file_path=str(path)),
        title="Upload cleanup",
    )


def test_upload_cleanup_refuses_file_symlink(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    link = uploads / "link.txt"
    link.symlink_to(outside)
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    _source_for(link)._cleanup_uploaded_file()

    assert link.is_symlink()
    assert outside.read_text() == "outside"


def test_upload_cleanup_refuses_intermediate_symlink_even_when_target_is_inside(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    owned_directory = uploads / "owned-directory"
    owned_directory.mkdir()
    owned_file = owned_directory / "owned.txt"
    owned_file.write_text("preserve")
    linked_directory = uploads / "linked-directory"
    linked_directory.symlink_to(owned_directory, target_is_directory=True)
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    _source_for(linked_directory / owned_file.name)._cleanup_uploaded_file()

    assert linked_directory.is_symlink()
    assert owned_file.read_text() == "preserve"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor defense")
@pytest.mark.parametrize("_iteration", range(50))
def test_upload_cleanup_detects_parent_swap_after_secure_open(
    _iteration,
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    visible_parent = uploads / "parent"
    visible_parent.mkdir()
    safe_file = visible_parent / "owned.txt"
    safe_file.write_text("safe")
    moved_parent = uploads / "original-parent"
    outside_parent = tmp_path / "outside-parent"
    outside_parent.mkdir()
    outside_victim = outside_parent / safe_file.name
    outside_victim.write_text("outside")
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    real_open = os.open
    swapped = False

    def open_then_swap(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == visible_parent.name and dir_fd is not None and not swapped:
            visible_parent.rename(moved_parent)
            visible_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return fd

    monkeypatch.setattr(os, "open", open_then_swap)
    monkeypatch.setattr(
        os,
        "supports_dir_fd",
        os.supports_dir_fd | {open_then_swap},
    )

    _source_for(safe_file)._cleanup_uploaded_file()

    assert swapped
    assert (moved_parent / safe_file.name).read_text() == "safe"
    assert outside_victim.read_text() == "outside"


def test_upload_cleanup_parent_symlink_swap_never_unlinks_outside(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    safe_parent = uploads / "safe-parent"
    safe_parent.mkdir()
    safe_file = safe_parent / "owned.txt"
    safe_file.write_text("safe")
    outside_parent = tmp_path / "outside-parent"
    outside_parent.mkdir()
    outside_victim = outside_parent / safe_file.name
    outside_victim.write_text("outside")
    visible_parent = uploads / "visible-parent"
    visible_parent.symlink_to(safe_parent, target_is_directory=True)
    stored_path = visible_parent / safe_file.name
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    real_exists = Path.exists
    swapped = False

    def exists_after_swap(path: Path) -> bool:
        nonlocal swapped
        if path == stored_path and not swapped:
            visible_parent.unlink()
            visible_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return real_exists(path)

    monkeypatch.setattr(Path, "exists", exists_after_swap)

    _source_for(stored_path)._cleanup_uploaded_file()

    assert safe_file.read_text() == "safe"
    assert outside_victim.read_text() == "outside"


def test_upload_cleanup_missing_file_is_a_noop(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    missing = uploads / "missing.txt"
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    _source_for(missing)._cleanup_uploaded_file()

    assert not missing.exists()


def test_upload_cleanup_refuses_directory(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    directory = uploads / "not-a-file"
    directory.mkdir()
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))

    _source_for(directory)._cleanup_uploaded_file()

    assert directory.is_dir()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unsupported")
def test_upload_cleanup_refuses_fifo_without_blocking_or_leaking_fds(
    tmp_path,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    fifo = uploads / "blocking-upload"
    os.mkfifo(fifo)
    child_code = """
import json
import os
import signal, sys

from deeper_notebook import config
from deeper_notebook.database import repository
from deeper_notebook.domain import base
from deeper_notebook.domain.notebook import Asset, Source
import surreal_commands
from surreal_commands.core import service

calls = []

async def forbidden_async(*args, **kwargs):
    calls.append("database-or-queue")
    raise AssertionError("cleanup touched database or queue")

def forbidden_sync(*args, **kwargs):
    calls.append("database-or-queue")
    raise AssertionError("cleanup touched database or queue")

for name in (
    "repo_create",
    "repo_delete",
    "repo_query",
    "repo_relate",
    "repo_update",
    "repo_upsert",
):
    setattr(repository, name, forbidden_async)
base.repo_delete = forbidden_async
surreal_commands.get_command_status = forbidden_async
service.get_command_service = forbidden_sync
config.UPLOADS_FOLDER = sys.argv[1]
fd_root = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
signal.alarm(2); before = len(os.listdir(fd_root))
Source(
    id="source:fifo",
    title="FIFO",
    asset=Asset(file_path=sys.argv[2]),
)._cleanup_uploaded_file()
signal.alarm(0); after = len(os.listdir(fd_root))
print(json.dumps({"calls": calls, "fd_delta": after - before}))
"""

    result = subprocess.run(
        [sys.executable, "-c", child_code, str(uploads), str(fifo)],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload == {"calls": [], "fd_delta": 0}
    assert fifo.exists()
    assert stat.S_ISFIFO(fifo.stat(follow_symlinks=False).st_mode)


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unsupported")
async def test_source_delete_refuses_fifo_then_runs_expected_database_path(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    fifo = uploads / "source-upload"
    os.mkfifo(fifo)
    queue_calls: list[str] = []

    async def forbidden_queue_call(*_args, **_kwargs):
        queue_calls.append("queue")
        raise AssertionError("source without a command touched queue state")

    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))
    monkeypatch.setattr(
        "surreal_commands.get_command_status",
        forbidden_queue_call,
    )
    repo_query = AsyncMock(return_value=[])
    parent_delete = AsyncMock(return_value=True)
    source = _source_for(fifo, source_id="source:fifo-delete")

    with (
        patch(
            "deeper_notebook.domain.notebook.repo_query",
            repo_query,
        ),
        patch(
            "deeper_notebook.domain.notebook.ObjectModel.delete",
            parent_delete,
        ),
    ):
        result = await asyncio.wait_for(source.delete(), timeout=1)

    assert result is True
    assert queue_calls == []
    assert repo_query.await_count == 5
    parent_delete.assert_awaited_once()
    assert stat.S_ISFIFO(fifo.stat(follow_symlinks=False).st_mode)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix socket unsupported")
def test_upload_cleanup_refuses_unix_socket_without_blocking(
    monkeypatch,
):
    short_base = Path("/private/tmp")
    if not short_base.is_dir():
        short_base = Path("/tmp").resolve()
    with tempfile.TemporaryDirectory(dir=short_base, prefix="dn-") as temp_dir:
        uploads = Path(temp_dir)
        socket_path = uploads / "upload.sock"
        monkeypatch.setattr(
            "deeper_notebook.config.UPLOADS_FOLDER",
            str(uploads),
        )

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            _source_for(socket_path)._cleanup_uploaded_file()

            assert socket_path.exists()
            assert stat.S_ISSOCK(socket_path.stat(follow_symlinks=False).st_mode)


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor defense")
def test_upload_cleanup_fails_closed_without_secure_dir_fd_support(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    owned_file = uploads / "owned.txt"
    owned_file.write_text("preserve")
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))
    monkeypatch.setattr(os, "supports_dir_fd", frozenset())

    _source_for(owned_file)._cleanup_uploaded_file()

    assert owned_file.read_text() == "preserve"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor defense")
def test_upload_cleanup_fails_closed_without_nonblocking_open(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    owned_file = uploads / "owned.txt"
    owned_file.write_text("preserve")
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))
    monkeypatch.delattr(os, "O_NONBLOCK")

    _source_for(owned_file)._cleanup_uploaded_file()

    assert owned_file.read_text() == "preserve"


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor defense")
def test_upload_cleanup_fails_closed_without_capability_metadata(
    tmp_path,
    monkeypatch,
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    owned_file = uploads / "owned.txt"
    owned_file.write_text("preserve")
    monkeypatch.setattr("deeper_notebook.config.UPLOADS_FOLDER", str(uploads))
    monkeypatch.delattr(os, "supports_dir_fd")

    _source_for(owned_file)._cleanup_uploaded_file()

    assert owned_file.read_text() == "preserve"


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
        "deeper_notebook.config.UPLOADS_FOLDER",
        str(uploads),
    )

    source = Source(
        id="source:malicious",
        asset=Asset(file_path=str(victim)),
        title="Tampered",
    )

    # Stub the parent class's delete() so we don't hit SurrealDB
    with (
        patch(
            "deeper_notebook.domain.notebook.ObjectModel.delete",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "deeper_notebook.domain.notebook.repo_query",
            new=AsyncMock(return_value=[]),
        ),
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
        "deeper_notebook.config.UPLOADS_FOLDER",
        str(uploads),
    )

    source = Source(
        id="source:real",
        asset=Asset(file_path=str(real_file)),
        title="Legit",
    )

    with (
        patch(
            "deeper_notebook.domain.notebook.ObjectModel.delete",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "deeper_notebook.domain.notebook.repo_query",
            new=AsyncMock(return_value=[]),
        ),
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
        "deeper_notebook.config.UPLOADS_FOLDER",
        str(uploads),
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

    with (
        patch(
            "deeper_notebook.domain.notebook.ObjectModel.delete",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "deeper_notebook.domain.notebook.repo_query",
            new=AsyncMock(return_value=[]),
        ),
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
    with (
        patch(
            "deeper_notebook.domain.notebook.ObjectModel.delete",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "deeper_notebook.domain.notebook.repo_query",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await source.delete()  # should not raise
    assert result is True
