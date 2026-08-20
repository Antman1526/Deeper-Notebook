from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
import uuid
from pathlib import Path

import pytest

try:
    import pwd
except ImportError:  # pragma: no cover - Windows skips POSIX vault tests
    pwd = None  # type: ignore[assignment]

from deeper_notebook.vault.security import (
    VaultSecurityError,
    _is_lexically_unsafe_root,
    approve_vault_root,
    approve_vault_root_bounded,
    classify_vault_path,
    list_secure_candidates_bounded,
    secure_read,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)


@pytest.fixture
def tmp_path() -> Path:
    assert pwd is not None
    base = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache" / "deeper-notebook-tests"
    unique = base / uuid.uuid4().hex
    unique.mkdir(parents=True)
    try:
        yield unique
    finally:
        shutil.rmtree(unique, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


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


def test_bounded_root_approval_returns_a_safe_timeout_when_open_stalls(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def stalled_open(_root: Path | str):
        started.set()
        release.wait()
        return approve_vault_root(vault_root)

    monkeypatch.setattr(
        "deeper_notebook.vault.security.approve_vault_root", stalled_open
    )

    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root_bounded(vault_root, timeout_seconds=0.01)

    assert started.is_set()
    assert caught.value.code == "root_open_timeout"
    release.set()


def test_bounded_candidate_listing_returns_a_safe_timeout_when_walk_stalls(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def stalled_walk(_root):
        started.set()
        release.wait()
        return []

    monkeypatch.setattr(
        "deeper_notebook.vault.security.list_secure_candidates", stalled_walk
    )

    with approve_vault_root(vault_root) as approved:
        with pytest.raises(VaultSecurityError) as caught:
            list_secure_candidates_bounded(approved, timeout_seconds=0.01)

    assert started.is_set()
    assert caught.value.code == "scan_timeout"
    release.set()


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
        Path("/usr/local"),
        Path("/Applications/Utilities"),
    ],
)
def test_approved_root_rejects_broad_or_system_roots(candidate: Path) -> None:
    if not candidate.exists():
        pytest.skip("platform path is absent")
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(candidate)
    assert caught.value.code == "unsafe_root"


def test_approved_root_rejects_broad_home_collections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("Desktop", "Documents", "Downloads"):
        candidate = tmp_path / name
        candidate.mkdir()
        with pytest.raises(VaultSecurityError) as caught:
            approve_vault_root(candidate)
        assert caught.value.code == "unsafe_root"


@pytest.mark.parametrize(
    "candidate",
    [
        "/private/etc",
        "/private/etc/ssh",
        "/private/tmp",
        "/private/tmp/deeper",
        "/private/var/log",
        "/private/var/log/deeper",
        "/private/var/db",
        "/private/var/db/deeper",
        "/private/var/tmp",
        "/private/var/tmp/deeper",
        "/private/var/run",
        "/private/var/run/deeper",
        "/private/var/root",
        "/private/var/audit",
        "/private/var/at",
        "/private/var/networkd",
        "/private/var/protected",
        "/private/var/spool",
        "/private/var/empty",
        "/private/var/select",
        "/private/var/vm",
        "/private/var/install",
        "/private/var/folders",
        "/private/var/folders/arbitrary/deeper",
    ],
)
def test_canonical_macos_system_trees_and_descendants_are_unsafe(
    candidate: str,
) -> None:
    assert _is_lexically_unsafe_root(Path(candidate)) is True


@pytest.mark.parametrize(
    "candidate",
    [
        "/PRIVATE/VAR/SPOOL",
        "/Private/Var/Arbitrary/Deeper",
        "/SYSTEM",
        "/sYsTeM/Library",
        "/USERS",
        "/vOlUmEs",
        "/UsR/Local",
    ],
)
def test_mixed_case_macos_system_trees_and_descendants_are_unsafe(
    candidate: str,
) -> None:
    assert _is_lexically_unsafe_root(Path(candidate)) is True


def _swap_ascii_case(value: str) -> str:
    return "".join(
        character.lower() if character.isupper() else character.upper()
        for character in value
    )


@pytest.mark.parametrize(
    "candidate",
    [
        "/PRIVATE/VAR/SPOOL",
        "/sYsTeM/Library",
        "/USERS",
    ],
)
def test_mixed_case_system_root_rejects_before_descriptor_open(
    candidate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_calls: list[tuple[object, ...]] = []

    def unexpected_open(*args: object, **kwargs: object) -> int:
        open_calls.append(args)
        raise AssertionError(f"os.open must not run: {kwargs}")

    monkeypatch.setattr(
        "deeper_notebook.vault.security._descriptor_security_available",
        lambda: True,
    )
    monkeypatch.setattr(os, "open", unexpected_open)

    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(candidate)
    assert caught.value.code == "unsafe_root"
    assert open_calls == []


@pytest.mark.parametrize(
    "candidate",
    [
        "//PRIVATE/VAR/SPOOL",
        "//sYsTeM/Library",
        "//server/share/vault",
        "///server/share/vault",
        "////server/share/vault",
        r"\\server\share\vault",
        r"\\\\server\share\vault",
    ],
)
def test_network_style_root_rejects_before_descriptor_open(
    candidate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_calls: list[tuple[object, ...]] = []

    def unexpected_open(*args: object, **kwargs: object) -> int:
        open_calls.append(args)
        raise AssertionError(f"os.open must not run: {kwargs}")

    monkeypatch.setattr(
        "deeper_notebook.vault.security._descriptor_security_available",
        lambda: True,
    )
    monkeypatch.setattr(os, "open", unexpected_open)

    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(candidate)
    assert caught.value.code == "unsafe_root"
    assert open_calls == []


def test_case_varied_home_and_desktop_reject_before_descriptor_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    candidates = [
        _swap_ascii_case(str(home)),
        str(Path(_swap_ascii_case(str(home))) / "dEsKtOp"),
    ]
    open_calls: list[tuple[object, ...]] = []

    def unexpected_open(*args: object, **kwargs: object) -> int:
        open_calls.append(args)
        raise AssertionError(f"os.open must not run: {kwargs}")

    monkeypatch.setattr(
        "deeper_notebook.vault.security._descriptor_security_available",
        lambda: True,
    )
    monkeypatch.setattr(os, "open", unexpected_open)

    for candidate in candidates:
        with pytest.raises(VaultSecurityError) as caught:
            approve_vault_root(candidate)
        assert caught.value.code == "unsafe_root"
    assert open_calls == []


def test_case_varied_deep_desktop_descendant_remains_lexically_allowed() -> None:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    candidate = (
        Path(_swap_ascii_case(str(home)))
        / "dEsKtOp"
        / "BrainPulse Ventures LLC"
        / "2nd Brains"
    )
    assert _is_lexically_unsafe_root(candidate) is False


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


def test_approved_root_rejects_mount_backed_ancestor(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_ismount = os.path.ismount
    monkeypatch.setattr(
        os.path,
        "ismount",
        lambda candidate: (
            Path(candidate) == vault_root.parent or real_ismount(candidate)
        ),
    )
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(vault_root)
    assert caught.value.code == "unsafe_root"


def test_approval_detects_replacement_during_mount_query(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = vault_root.parent / "moved-during-mount-check"
    real_ismount = os.path.ismount
    replaced = False

    def replacing_ismount(candidate: str | os.PathLike[str]) -> bool:
        nonlocal replaced
        if Path(candidate) == vault_root and not replaced:
            replaced = True
            vault_root.rename(moved)
            vault_root.mkdir()
            return False
        return real_ismount(candidate)

    monkeypatch.setattr(os.path, "ismount", replacing_ismount)
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(vault_root)
    assert caught.value.code == "root_changed"


def test_approval_rejects_symlink_substitution_immediately_before_open(
    vault_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = vault_root.parent / "moved-before-open"
    real_open = os.open
    substituted = False

    def substituting_open(
        path: str | bytes, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal substituted
        if path == vault_root.name and not substituted:
            substituted = True
            vault_root.rename(moved)
            vault_root.symlink_to(moved, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "deeper_notebook.vault.security._descriptor_security_available",
        lambda: True,
    )
    monkeypatch.setattr(os, "open", substituting_open)
    with pytest.raises(VaultSecurityError) as caught:
        approve_vault_root(vault_root)
    assert caught.value.code == "unsafe_symlink"


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
    [
        "../escape.md",
        "/absolute.md",
        "a/../../escape.md",
        ".",
        "",
        r"a\\note.md",
        "a//b.md",
        "a/./b.md",
        "./b.md",
    ],
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
    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    temp_parent = real_home / ".cache" / "dn-sockets"
    temp_parent.mkdir(parents=True, exist_ok=True)
    short_root = Path(tempfile.mkdtemp(prefix="dn-vault-", dir=temp_parent))
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
        try:
            temp_parent.rmdir()
        except OSError:
            pass


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
            secure_read(
                approved, "changing.md", _between_read_passes=mutate_after_first_pass
            )
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


def test_secure_read_detects_approved_root_ancestor_replacement(
    vault_root: Path,
) -> None:
    (vault_root / "note.md").write_bytes(b"same")
    approved = approve_vault_root(vault_root)
    original_parent = vault_root.parent
    moved_parent = original_parent.parent / f"{original_parent.name}-moved"
    try:
        original_parent.rename(moved_parent)
        original_parent.mkdir()
        replacement = original_parent / vault_root.name
        replacement.mkdir()
        (replacement / "note.md").write_bytes(b"same")
        with pytest.raises(VaultSecurityError) as caught:
            secure_read(approved, "note.md")
        assert caught.value.code == "root_changed"
    finally:
        approved.close()


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


def test_approved_root_chain_close_stress_does_not_leak(vault_root: Path) -> None:
    fd_root = Path("/dev/fd")
    before = len(list(fd_root.iterdir())) if fd_root.exists() else None
    for _ in range(100):
        approved = approve_vault_root(vault_root)
        approved.close()
        approved.close()
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
