from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_notebook.overlay.paths import OverlayLayout
from deeper_notebook.overlay.storage import (
    OverlayConflictError,
    OverlaySnapshot,
    OverlayStorage,
    OverlayStorageError,
)


def _storage(tmp_path: Path, *, maximum: int = 10 * 1024 * 1024) -> OverlayStorage:
    return OverlayStorage(
        OverlayLayout.from_data_root(tmp_path),
        max_markdown_bytes=maximum,
    )


def test_create_and_read_are_utf8_lf_and_hash_bound(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    stored = storage.create(
        "Daily/2026-07-29.md",
        "# Today\r\n",
        operation_id="create-1",
    )
    expected = b"# Today\n"

    assert stored.markdown == "# Today\n"
    assert stored.content_hash == hashlib.sha256(expected).hexdigest()
    assert stored.byte_size == len(expected)
    assert storage.read("Daily/2026-07-29.md") == stored
    assert (storage.layout.daily_root / "2026-07-29.md").read_bytes() == expected


def test_create_never_replaces_existing_file(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.create("Notes/one.md", "first\n", operation_id="one")

    with pytest.raises(OverlayConflictError, match="overlay_file_exists"):
        storage.create("Notes/one.md", "second\n", operation_id="two")

    assert storage.read("Notes/one.md").markdown == "first\n"


def test_replace_requires_current_hash_and_preserves_on_failure(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")

    with pytest.raises(OverlayConflictError, match="overlay_hash_conflict"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash="0" * 64,
            revision=2,
            operation_id="two",
        )

    assert storage.read("Notes/one.md") == first


def test_replace_snapshots_previous_bytes_before_atomic_replacement(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")

    second = storage.replace(
        "Notes/one.md",
        "second\r\n",
        expected_hash=first.content_hash,
        revision=2,
        operation_id="two",
    )

    assert second.markdown == "second\n"
    snapshots = list(storage.layout.revisions_root.glob("*.md"))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == b"first\n"


def test_public_snapshot_is_content_hash_bound_and_create_only(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    stored = storage.create("Notes/one.md", "first\n", operation_id="one")

    first = storage.snapshot("overlay_note:one", 1, stored)
    replay = storage.snapshot("overlay_note:one", 1, stored)

    assert isinstance(first, OverlaySnapshot)
    assert replay == first
    assert first.content_hash == stored.content_hash
    assert first.byte_size == stored.byte_size
    assert (
        storage.layout.state_root / first.relative_snapshot
    ).read_bytes() == b"first\n"


def test_source_symlink_and_parent_swap_fail_closed(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("private\n", encoding="utf-8")
    storage.layout.daily_root.mkdir(parents=True)
    (storage.layout.daily_root / "evil.md").symlink_to(outside)

    with pytest.raises(OverlayStorageError):
        storage.read("Daily/evil.md")

    assert outside.read_text(encoding="utf-8") == "private\n"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor traversal")
def test_data_root_symlink_ancestor_is_rejected(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    data_root = real_parent / "data"
    data_root.mkdir(parents=True)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    storage = OverlayStorage(
        OverlayLayout.from_data_root(linked_parent / "data"),
    )

    with pytest.raises(OverlayStorageError):
        storage.create("Notes/one.md", "content\n", operation_id="one")

    assert not (data_root / "overlay").exists()


def test_incoherent_layout_is_rejected_before_mutation(tmp_path: Path) -> None:
    layout = OverlayLayout.from_data_root(tmp_path)
    incoherent = replace(layout, state_root=tmp_path / "unrelated-state")

    with pytest.raises(OverlayStorageError, match="invalid_overlay_layout"):
        OverlayStorage(incoherent)

    assert not (tmp_path / "overlay").exists()


def test_injected_replace_failure_keeps_original_and_removes_owned_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    monkeypatch.setattr(
        "deeper_notebook.overlay.storage.os.replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected")),
    )

    with pytest.raises(OSError, match="injected"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert storage.read("Notes/one.md").markdown == "first\n"
    assert not list(storage.layout.unique_root.glob(".*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX hard-link semantics")
def test_hard_link_target_is_rejected_without_touching_linked_content(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    storage.layout.unique_root.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"private\n")
    os.link(outside, storage.layout.unique_root / "linked.md")

    with pytest.raises(OverlayStorageError, match="overlay_unsafe_file"):
        storage.read("Notes/linked.md")
    with pytest.raises(OverlayStorageError, match="overlay_unsafe_file"):
        storage.create("Notes/linked.md", "replace\n", operation_id="unsafe")

    assert outside.read_bytes() == b"private\n"


def test_directory_target_is_rejected(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    target = storage.layout.unique_root / "directory.md"
    target.mkdir(parents=True)

    with pytest.raises(OverlayStorageError, match="overlay_unsafe_file"):
        storage.read("Notes/directory.md")


def test_root_identity_change_during_read_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    storage.create("Notes/one.md", "first\n", operation_id="one")
    original = storage._verify_path_identity
    calls = 0

    def swap_on_final_check(path: Path, identity: tuple[int, int]) -> None:
        nonlocal calls
        calls += 1
        if path == storage.layout.canonical_root and calls > 1:
            displaced = tmp_path / "displaced-overlay-root"
            storage.layout.canonical_root.rename(displaced)
            storage.layout.canonical_root.mkdir(parents=True)
        original(path, identity)

    monkeypatch.setattr(storage, "_verify_path_identity", swap_on_final_check)

    with pytest.raises(OverlayStorageError, match="overlay_root_changed"):
        storage.read("Notes/one.md")


def test_unicode_normalization_collision_is_rejected(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    composed = unicodedata.normalize("NFC", "e\u0301")
    decomposed = unicodedata.normalize("NFD", composed)
    storage.create(f"Notes/{composed}.md", "first\n", operation_id="one")

    with pytest.raises(OverlayStorageError, match="overlay_unicode_collision"):
        storage.create(
            f"Notes/{decomposed}.md",
            "second\n",
            operation_id="two",
        )

    assert storage.read(f"Notes/{composed}.md").markdown == "first\n"


def test_oversized_payload_is_rejected_before_filesystem_mutation(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path, maximum=8)

    with pytest.raises(OverlayStorageError, match="overlay_file_too_large"):
        storage.create("Notes/large.md", "123456789", operation_id="large")

    assert not storage.layout.canonical_root.exists()


@pytest.mark.parametrize(
    "relative_path",
    [
        "/tmp/one.md",
        "../one.md",
        "Notes/../one.md",
        r"Notes\one.md",
        "Notes//one.md",
        "Templates/one.md",
        "Notes/one.txt",
        "Notes",
    ],
)
def test_invalid_or_non_owned_relative_paths_are_rejected(
    tmp_path: Path,
    relative_path: str,
) -> None:
    storage = _storage(tmp_path)

    with pytest.raises(OverlayStorageError, match="invalid_relative_path"):
        storage.create(relative_path, "content\n", operation_id="invalid")


def test_malformed_utf8_and_non_lf_existing_bytes_are_rejected(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    storage.layout.unique_root.mkdir(parents=True)
    malformed = storage.layout.unique_root / "malformed.md"
    malformed.write_bytes(b"\xff\n")
    crlf = storage.layout.unique_root / "crlf.md"
    crlf.write_bytes(b"line\r\n")

    for relative_path in ("Notes/malformed.md", "Notes/crlf.md"):
        with pytest.raises(OverlayStorageError, match="overlay_invalid_markdown"):
            storage.read(relative_path)


def test_changed_during_read_metadata_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    storage.create("Notes/one.md", "first\n", operation_id="one")
    original = storage._read_all

    def mutate_after_read(file_descriptor: int) -> bytes:
        content = original(file_descriptor)
        os.fchmod(file_descriptor, 0o640)
        return content

    monkeypatch.setattr(storage, "_read_all", mutate_after_read)

    with pytest.raises(OverlayStorageError, match="overlay_file_changed"):
        storage.read("Notes/one.md")


def test_replace_rejects_target_substitution_after_hash_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    original_snapshot = storage.snapshot
    target = storage.layout.unique_root / "one.md"

    def snapshot_then_substitute(
        note_id: str,
        revision: int,
        content,
    ) -> OverlaySnapshot:
        result = original_snapshot(note_id, revision, content)
        target.unlink()
        target.write_bytes(b"substitute\n")
        return result

    monkeypatch.setattr(storage, "snapshot", snapshot_then_substitute)

    with pytest.raises(OverlayStorageError, match="overlay_file_changed"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert target.read_bytes() == b"substitute\n"


def test_cleanup_never_unlinks_a_substituted_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    original_replace = os.replace
    substituted: Path | None = None

    def substitute_then_fail(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        nonlocal substituted
        assert src_dir_fd == dst_dir_fd
        stolen = storage.layout.unique_root / ".stolen.tmp"
        original_replace(
            source,
            stolen.name,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        substituted = storage.layout.unique_root / source
        substituted.write_bytes(b"substitute\n")
        raise OSError("injected substitution")

    monkeypatch.setattr(
        "deeper_notebook.overlay.storage.os.replace", substitute_then_fail
    )

    with pytest.raises(OSError, match="injected substitution"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert substituted is not None
    assert substituted.read_bytes() == b"substitute\n"
    assert storage.read("Notes/one.md") == first
