from __future__ import annotations

import hashlib
import inspect
import os
import stat
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

import deeper_notebook.overlay.storage as storage_module
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-replace primitive")
def test_create_publish_race_preserves_substituted_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    target = storage.layout.unique_root / "raced.md"
    original_publish = storage._posix_publish_no_replace
    injected = False

    def substitute_inside_publish(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        nonlocal injected
        if destination_name == "raced.md":
            injected = True
            target.write_bytes(b"substitute\n")
        original_publish(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    monkeypatch.setattr(storage, "_posix_publish_no_replace", substitute_inside_publish)

    with pytest.raises(OverlayConflictError, match="overlay_file_exists"):
        storage.create("Notes/raced.md", "created\n", operation_id="raced")

    assert injected
    assert target.read_bytes() == b"substitute\n"
    assert b"created\n" in {
        path.read_bytes() for path in storage.layout.recovery_root.iterdir()
    }


def test_windows_storage_statically_uses_fail_closed_no_replace_protocol() -> None:
    publish_source = inspect.getsource(
        storage_module.OverlayStorage._windows_publish_no_replace
    )
    create_source = inspect.getsource(storage_module.OverlayStorage._windows_create)
    replace_source = inspect.getsource(storage_module.OverlayStorage._windows_replace)
    snapshot_source = inspect.getsource(storage_module.OverlayStorage._windows_snapshot)
    temp_source = inspect.getsource(storage_module.OverlayStorage._write_windows_temp)
    storage_source = inspect.getsource(storage_module.OverlayStorage)

    assert storage_module._MOVEFILE_WRITE_THROUGH == 0x8
    assert "MoveFileExW" in publish_source
    assert "REPLACE_EXISTING" not in publish_source
    assert "_evacuate_windows_entry" in create_source
    assert "_evacuate_windows_entry" in snapshot_source
    assert "_restore_windows_backup" in replace_source
    assert "_evacuate_windows_entry" in replace_source
    for mutation_source in (create_source, replace_source, snapshot_source):
        assert ".lstat()" in mutation_source
        assert "_require_regular" in mutation_source
        assert "_windows_read_owned" in mutation_source
    assert temp_source.index("os.fsync") < temp_source.index("_require_regular")
    assert "os.replace" not in storage_source
    assert "unlink(" not in storage_source


@pytest.mark.skipif(os.name != "posix", reason="POSIX source substitution")
@pytest.mark.parametrize("operation", ["create", "snapshot"])
@pytest.mark.parametrize("substitution", ["regular", "symlink", "hardlink"])
def test_create_and_snapshot_source_substitution_evacuates_final_and_preserves_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    substitution: str,
) -> None:
    storage = _storage(tmp_path)
    authored_retained = tmp_path / f"authored-{operation}-{substitution}.md"
    substitute_backing = tmp_path / f"substitute-{operation}-{substitution}.md"
    substitute_backing.write_bytes(b"substitute\n")
    original_publish = storage._posix_publish_no_replace

    if operation == "create":
        final_name = "source-raced.md"
        final = storage.layout.unique_root / final_name

        def invoke() -> None:
            storage.create(
                f"Notes/{final_name}",
                "authored\n",
                operation_id="source-raced",
            )

        expected_authored = b"authored\n"
    else:
        stored = storage.create(
            "Notes/snapshot-source.md",
            "authored\n",
            operation_id="snapshot-source",
        )
        note_id = "overlay_note:source-raced"
        note_key = hashlib.sha256(note_id.encode()).hexdigest()
        final_name = f"{note_key}-r1-{stored.content_hash}.md"
        final = storage.layout.revisions_root / final_name

        def invoke() -> None:
            storage.snapshot(note_id, 1, stored)

        expected_authored = b"authored\n"

    def substitute_inside_publish(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        if destination_name == final_name:
            if substitution == "hardlink":
                os.link(
                    source_name,
                    authored_retained,
                    src_dir_fd=source_descriptor,
                )
            else:
                os.rename(
                    source_name,
                    authored_retained,
                    src_dir_fd=source_descriptor,
                )
                if substitution == "regular":
                    descriptor = os.open(
                        source_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=source_descriptor,
                    )
                    try:
                        os.write(descriptor, b"substitute\n")
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                else:
                    os.symlink(
                        substitute_backing,
                        source_name,
                        dir_fd=source_descriptor,
                    )
        original_publish(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    monkeypatch.setattr(storage, "_posix_publish_no_replace", substitute_inside_publish)

    with pytest.raises(OverlayStorageError):
        invoke()

    assert not final.exists()
    assert authored_retained.read_bytes() == expected_authored
    recovery_entries = list(storage.layout.recovery_root.iterdir())
    if substitution == "regular":
        assert b"substitute\n" in {path.read_bytes() for path in recovery_entries}
    elif substitution == "symlink":
        assert any(path.is_symlink() for path in recovery_entries)
        assert substitute_backing.read_bytes() == b"substitute\n"
    else:
        assert expected_authored in {path.read_bytes() for path in recovery_entries}


@pytest.mark.skipif(os.name != "posix", reason="POSIX source substitution")
@pytest.mark.parametrize("substitution", ["regular", "symlink", "hardlink"])
def test_replace_source_substitution_rolls_back_prior_and_preserves_all_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    substitution: str,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    authored_retained = tmp_path / f"authored-replace-{substitution}.md"
    substitute_backing = tmp_path / f"substitute-replace-{substitution}.md"
    substitute_backing.write_bytes(b"substitute\n")
    original_exchange = storage._posix_exchange
    injected = False

    def substitute_inside_exchange(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        nonlocal injected
        if not injected:
            injected = True
            if substitution == "hardlink":
                os.link(
                    source_name,
                    authored_retained,
                    src_dir_fd=source_descriptor,
                )
            else:
                os.rename(
                    source_name,
                    authored_retained,
                    src_dir_fd=source_descriptor,
                )
                if substitution == "regular":
                    descriptor = os.open(
                        source_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=source_descriptor,
                    )
                    try:
                        os.write(descriptor, b"substitute\n")
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                else:
                    os.symlink(
                        substitute_backing,
                        source_name,
                        dir_fd=source_descriptor,
                    )
        original_exchange(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    monkeypatch.setattr(storage, "_posix_exchange", substitute_inside_exchange)

    with pytest.raises(OverlayStorageError):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert storage.read("Notes/one.md") == first
    assert authored_retained.read_bytes() == b"second\n"
    recovery_entries = list(storage.layout.recovery_root.iterdir())
    if substitution == "regular":
        assert b"substitute\n" in {path.read_bytes() for path in recovery_entries}
    elif substitution == "symlink":
        assert any(path.is_symlink() for path in recovery_entries)
        assert substitute_backing.read_bytes() == b"substitute\n"
    else:
        assert b"second\n" in {path.read_bytes() for path in recovery_entries}


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX recovery permissions")
def test_replace_retains_old_bytes_in_random_private_recovery_artifact(
    tmp_path: Path,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="caller-path")

    storage.replace(
        "Notes/one.md",
        "second\n",
        expected_hash=first.content_hash,
        revision=2,
        operation_id="caller-operation",
    )

    recovered = [
        path
        for path in storage.layout.recovery_root.iterdir()
        if path.read_bytes() == b"first\n"
    ]
    assert len(recovered) == 1
    artifact = recovered[0]
    random_segment = artifact.name.removeprefix(".recovery-").removesuffix(".dat")
    assert len(random_segment) == 32
    assert all(character in "0123456789abcdef" for character in random_segment)
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    assert "one" not in artifact.name
    assert "caller" not in artifact.name


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic exchange primitive")
def test_injected_replace_failure_keeps_original_and_retains_owned_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    monkeypatch.setattr(
        storage,
        "_posix_exchange",
        lambda *_args: (_ for _ in ()).throw(OSError("injected")),
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
    assert b"second\n" in {
        path.read_bytes() for path in storage.layout.recovery_root.iterdir()
    }


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic rename primitives")
@pytest.mark.parametrize("kind", ["create", "snapshot"])
def test_create_and_snapshot_publish_only_after_private_temp_is_fsynced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    storage = _storage(tmp_path)
    fsynced: set[tuple[int, int]] = set()
    original_fsync = os.fsync
    publish_calls = 0

    def record_fsync(descriptor: int) -> None:
        status = os.fstat(descriptor)
        if stat.S_ISREG(status.st_mode):
            fsynced.add((status.st_dev, status.st_ino))
        original_fsync(descriptor)

    def inspect_publish(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        nonlocal publish_calls
        publish_calls += 1
        with os.fdopen(
            os.open(source_name, os.O_RDONLY, dir_fd=source_descriptor),
            "rb",
        ) as source:
            source_status = os.fstat(source.fileno())
            assert (source_status.st_dev, source_status.st_ino) in fsynced
            assert source.read() == b"content\n"
        with pytest.raises(FileNotFoundError):
            os.stat(
                destination_name,
                dir_fd=destination_descriptor,
                follow_symlinks=False,
            )
        original_publish(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    monkeypatch.setattr(os, "fsync", record_fsync)
    original_publish = getattr(
        storage,
        "_posix_publish_no_replace",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        storage,
        "_posix_publish_no_replace",
        inspect_publish,
        raising=False,
    )

    if kind == "create":
        storage.create("Notes/atomic.md", "content\n", operation_id="atomic")
        final = storage.layout.unique_root / "atomic.md"
    else:
        stored = storage.create("Notes/source.md", "content\n", operation_id="source")
        publish_calls = 0
        snapshot = storage.snapshot("overlay_note:source", 1, stored)
        final = storage.layout.state_root / snapshot.relative_snapshot

    assert publish_calls == 1
    assert final.read_bytes() == b"content\n"


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic exchange primitive")
def test_replace_swap_race_restores_and_preserves_substituted_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    target = storage.layout.unique_root / "one.md"
    attacker_preserved = tmp_path / "attacker-preserved.md"
    exchange_calls = 0

    original_exchange = getattr(storage, "_posix_exchange", lambda *_args: None)

    def substitute_inside_exchange(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        nonlocal exchange_calls
        exchange_calls += 1
        if exchange_calls == 1:
            target.rename(attacker_preserved)
            target.write_bytes(b"substitute\n")
        original_exchange(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    monkeypatch.setattr(
        storage,
        "_posix_exchange",
        substitute_inside_exchange,
        raising=False,
    )

    with pytest.raises(OverlayStorageError, match="overlay_file_changed"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert exchange_calls == 2
    assert target.read_bytes() == b"substitute\n"
    assert attacker_preserved.read_bytes() == b"first\n"
    assert b"second\n" in {
        path.read_bytes() for path in storage.layout.recovery_root.iterdir()
    }


@pytest.mark.skipif(os.name != "posix", reason="POSIX recovery primitive")
def test_cleanup_primitive_quarantines_a_substitution_instead_of_unlinking_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    retained_written = tmp_path / "retained-written.md"
    cleanup_calls = 0
    original_publish = storage._posix_publish_no_replace

    def fail_publish(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        if destination_name == "one.md":
            raise OSError("injected publish failure")
        original_publish(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )

    original_retain = getattr(storage, "_retain_posix_artifact", lambda *_args: None)

    def substitute_inside_cleanup(
        source_descriptor: int,
        source_name: str,
        recovery_descriptor: int,
    ) -> str | None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        os.rename(
            source_name,
            retained_written,
            src_dir_fd=source_descriptor,
        )
        descriptor = os.open(
            source_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=source_descriptor,
        )
        try:
            os.write(descriptor, b"substitute\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return original_retain(
            source_descriptor,
            source_name,
            recovery_descriptor,
        )

    monkeypatch.setattr(
        storage,
        "_posix_publish_no_replace",
        fail_publish,
        raising=False,
    )
    monkeypatch.setattr(
        storage,
        "_retain_posix_artifact",
        substitute_inside_cleanup,
        raising=False,
    )

    with pytest.raises(OSError, match="injected publish failure"):
        storage.create("Notes/one.md", "written\n", operation_id="one")

    assert cleanup_calls == 1
    assert not (storage.layout.unique_root / "one.md").exists()
    assert retained_written.read_bytes() == b"written\n"
    assert b"substitute\n" in {
        path.read_bytes() for path in storage.layout.recovery_root.iterdir()
    }


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic exchange primitive")
def test_exchange_failure_never_unlinks_a_substituted_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    substituted: Path | None = None

    def substitute_then_fail(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        _destination_name: str,
    ) -> None:
        nonlocal substituted
        assert source_descriptor == destination_descriptor
        stolen = storage.layout.unique_root / ".stolen.tmp"
        os.rename(
            source_name,
            stolen.name,
            src_dir_fd=source_descriptor,
            dst_dir_fd=destination_descriptor,
        )
        substituted = storage.layout.unique_root / source_name
        substituted.write_bytes(b"substitute\n")
        raise OSError("injected substitution")

    monkeypatch.setattr(storage, "_posix_exchange", substitute_then_fail)

    with pytest.raises(OSError, match="injected substitution"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )

    assert substituted is not None
    assert not substituted.exists()
    assert b"substitute\n" in {
        path.read_bytes() for path in storage.layout.recovery_root.iterdir()
    }
    assert (storage.layout.unique_root / ".stolen.tmp").read_bytes() == b"second\n"
    assert storage.read("Notes/one.md") == first
