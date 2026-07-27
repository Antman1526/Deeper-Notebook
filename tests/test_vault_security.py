from __future__ import annotations

import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

from deeper_notebook.vault.security import (
    VaultSecurityError,
    approve_vault_root,
    classify_vault_path,
    secure_read,
)


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    root = tmp_path / "approved-vault"
    root.mkdir()
    return root


def test_approved_root_expands_user_and_accepts_specific_existing_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Desktop" / "BrainPulse Ventures LLC" / "2nd Brains"
    root.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))

    with approve_vault_root("~/Desktop/BrainPulse Ventures LLC/2nd Brains") as approved:
        assert approved.path == root
        assert approved.device > 0
        assert approved.inode > 0


@pytest.mark.parametrize("candidate", ["relative", ".", ".."])
def test_approved_root_rejects_relative_paths(candidate: str) -> None:
    with pytest.raises(VaultSecurityError, match="approved root") as caught:
        approve_vault_root(candidate)
    assert caught.value.code == "invalid_root"
    assert "relative" not in str(caught.value)


def test_approved_root_rejects_missing_file_and_root_symlink(tmp_path: Path) -> None:
    file_path = tmp_path / "file"
    file_path.write_text("not a directory")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    for candidate, code in (
        (tmp_path / "missing", "invalid_root"),
        (file_path, "invalid_root"),
        (link, "unsafe_symlink"),
    ):
        with pytest.raises(VaultSecurityError) as caught:
            approve_vault_root(candidate)
        assert caught.value.code == code


def test_approved_root_rejects_symlink_in_ancestor_chain(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    child = real_parent / "vault"
    child.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(linked_parent / "vault")
    assert caught.value.code == "unsafe_symlink"


@pytest.mark.parametrize(
    "candidate",
    [
        Path("/"),
        Path.home(),
        Path("/System"),
        Path("/Library"),
        Path("/Applications"),
        Path("/Users"),
        Path("/Volumes"),
    ],
)
def test_approved_root_rejects_broad_or_system_roots(candidate: Path) -> None:
    if not candidate.exists():
        pytest.skip("platform path is absent")
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(candidate)
    assert caught.value.code == "unsafe_root"


def test_approved_root_fails_closed_without_descriptor_security(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "deeper_notebook.vault.security._descriptor_security_available",
        lambda: False,
    )
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(tmp_path)
    assert caught.value.code == "unsupported_platform"


def test_approved_root_rejects_drive_or_share_mount_root(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_ismount = os.path.ismount
    monkeypatch.setattr(
        os.path,
        "ismount",
        lambda candidate: Path(candidate) == vault_root or real_ismount(candidate),
    )
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(vault_root)
    assert caught.value.code == "unsafe_root"


@pytest.mark.parametrize(
    ("relative", "kind", "protected"),
    [
        ("note.md", "markdown", False),
        ("NOTE.MARKDOWN", "markdown", False),
        ("board.canvas", "metadata", False),
        ("table.BASE", "metadata", False),
        ("sources/paper.md", "markdown", True),
        ("inbox/raw/capture.md", "markdown", True),
        ("brain-engine/config.json", "connector", True),
        (".git/config", "control", True),
        (".obsidian/workspace.json", "control", True),
        ("logseq/config.edn", "control", True),
        (".hidden/note.md", "control", True),
        ("note.md.tmp", "temporary", False),
        ("note.md~", "temporary", False),
        (".#note.md", "temporary", False),
        ("note.md.swp", "temporary", False),
        ("note.md.lock", "temporary", False),
        ("image.png", "ignored", False),
    ],
)
def test_path_classification(relative: str, kind: str, protected: bool) -> None:
    result = classify_vault_path(relative)
    assert result.kind == kind
    assert result.protected is protected


@pytest.mark.parametrize(
    "relative",
    ["../escape.md", "/absolute.md", "a/../../escape.md", ".", "", r"a\\note.md"],
)
def test_path_classification_rejects_candidate_escape(relative: str) -> None:
    with pytest.raises(VaultSecurityError) as caught:
        classify_vault_path(relative)
    assert caught.value.code == "path_escape"


def test_secure_read_hashes_exact_unicode_crlf_bytes_without_mutation(
    vault_root: Path,
) -> None:
    path = vault_root / "Résumé 文档.md"
    raw = b"# heading\r\nbody\r\n"
    path.write_bytes(raw)
    before = path.stat()

    with approve_vault_root(vault_root) as approved:
        result = secure_read(approved, path.name, max_bytes=1024)

    assert result.content == raw
    assert result.byte_size == len(raw)
    assert len(result.sha256) == 64
    after = path.stat()
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )


def test_secure_read_rejects_ancestor_and_final_symlinks(vault_root: Path) -> None:
    outside = vault_root.parent / f"{vault_root.name}-outside"
    outside.mkdir()
    (outside / "note.md").write_text("secret")
    (vault_root / "linked").symlink_to(outside, target_is_directory=True)
    (vault_root / "final.md").symlink_to(outside / "note.md")

    with approve_vault_root(vault_root) as approved:
        for relative in ("linked/note.md", "final.md"):
            with pytest.raises(VaultSecurityError) as caught:
                secure_read(approved, relative)
            assert caught.value.code == "unsafe_symlink"


def test_secure_read_rejects_hardlinks_and_non_regular_files(
    vault_root: Path,
) -> None:
    original = vault_root / "original.md"
    original.write_text("same inode")
    os.link(original, vault_root / "hardlink.md")
    directory = vault_root / "directory.md"
    directory.mkdir()

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "hardlink.md")
        assert caught.value.code == "unsafe_hardlink"
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "directory.md")
        assert caught.value.code == "not_regular_file"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_secure_read_never_blocks_on_fifo(vault_root: Path) -> None:
    os.mkfifo(vault_root / "pipe.md")
    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "pipe.md")
    assert caught.value.code == "not_regular_file"


def test_secure_read_rejects_socket() -> None:
    short_root = Path(tempfile.mkdtemp(prefix="dn-vault-", dir="/private/tmp"))
    socket_path = short_root / "socket.md"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(socket_path))
    try:
        with approve_vault_root(short_root) as approved:
            with pytest.raises(VaultSecurityError) as caught:
                secure_read(approved, "socket.md")
        assert caught.value.code == "not_regular_file"
    finally:
        server.close()
        shutil.rmtree(short_root)


def test_secure_read_detects_oversize_before_returning_content(
    vault_root: Path,
) -> None:
    (vault_root / "large.md").write_bytes(b"12345")
    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "large.md", max_bytes=4)
    assert caught.value.code == "file_too_large"


def test_secure_read_detects_change_during_read(vault_root: Path) -> None:
    path = vault_root / "changing.md"
    path.write_bytes(b"first")
    calls = 0

    def mutate_after_first_pass() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            path.write_bytes(b"second")

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "changing.md", _between_read_passes=mutate_after_first_pass)
    assert caught.value.code == "changed_during_read"


def test_secure_read_rejects_final_symlink_swap_between_passes(
    vault_root: Path,
) -> None:
    path = vault_root / "changing.md"
    alternate = vault_root / "alternate.md"
    path.write_bytes(b"first")
    alternate.write_bytes(b"other")

    def replace_path_with_symlink() -> None:
        path.unlink()
        path.symlink_to(alternate)

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(
                approved,
                "changing.md",
                _between_read_passes=replace_path_with_symlink,
            )
    assert caught.value.code == "changed_during_read"


def test_secure_read_detects_ancestor_directory_replacement(
    vault_root: Path,
) -> None:
    directory = vault_root / "folder"
    directory.mkdir()
    (directory / "note.md").write_bytes(b"same")
    moved = vault_root / "moved"

    def replace_ancestor() -> None:
        directory.rename(moved)
        directory.mkdir()
        (directory / "note.md").write_bytes(b"same")

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(
                approved,
                "folder/note.md",
                _between_read_passes=replace_ancestor,
            )
    assert caught.value.code == "changed_during_read"


def test_secure_read_detects_approved_root_rename_and_replacement(
    vault_root: Path,
) -> None:
    path = vault_root / "note.md"
    path.write_bytes(b"same")
    moved_root = vault_root.parent / "moved-root"

    with approve_vault_root(vault_root) as approved:

        def replace_root() -> None:
            vault_root.rename(moved_root)
            vault_root.mkdir()
            (vault_root / "note.md").write_bytes(b"same")

        with pytest.raises(VaultSecurityError) as caught:
            secure_read(
                approved,
                "note.md",
                _between_read_passes=replace_root,
            )
    assert caught.value.code == "root_changed"


def test_secure_read_detects_size_and_mtime_preserving_content_race(
    vault_root: Path,
) -> None:
    path = vault_root / "changing.md"
    path.write_bytes(b"first")
    original_mtime = path.stat().st_mtime_ns

    def mutate_and_restore_mtime() -> None:
        path.write_bytes(b"other")
        os.utime(path, ns=(original_mtime, original_mtime))

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(
                approved,
                "changing.md",
                _between_read_passes=mutate_and_restore_mtime,
            )
    assert caught.value.code == "changed_during_read"


def test_secure_read_permission_error_is_typed_without_path_leak(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (vault_root / "private.md").write_text("top secret")
    real_open = os.open

    def denied(path: str | bytes, flags: int, *args: object, **kwargs: object) -> int:
        if path == "private.md":
            raise PermissionError
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    with approve_vault_root(vault_root) as approved:
        monkeypatch.setattr(os, "open", denied)
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "private.md")
    assert caught.value.code == "unreadable"
    assert "private.md" not in str(caught.value)


def test_secure_read_fd_stress_does_not_leak(vault_root: Path) -> None:
    (vault_root / "note.md").write_text("body")
    fd_root = Path("/dev/fd")
    before = len(list(fd_root.iterdir())) if fd_root.exists() else None
    with approve_vault_root(vault_root) as approved:
        for _ in range(200):
            assert secure_read(approved, "note.md").content == b"body"
    if before is not None:
        assert len(list(fd_root.iterdir())) <= before + 2


def test_secure_read_opens_only_read_only_without_create_or_truncate(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (vault_root / "note.md").write_text("body")
    real_open = os.open
    flags_seen: list[int] = []

    def audited_open(
        path: str | bytes, flags: int, *args: object, **kwargs: object
    ) -> int:
        flags_seen.append(flags)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    with approve_vault_root(vault_root) as approved:
        monkeypatch.setattr(os, "open", audited_open)
        assert secure_read(approved, "note.md").content == b"body"

    forbidden = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert flags_seen
    assert all(flags & forbidden == 0 for flags in flags_seen)
