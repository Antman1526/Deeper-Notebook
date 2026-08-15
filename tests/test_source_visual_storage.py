from __future__ import annotations

import asyncio
import gc
import hashlib
import multiprocessing as mp
import os
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deeper_notebook.source_visuals.cleanup import SourceVisualCleanup
from deeper_notebook.source_visuals.contracts import (
    PreparedVisualAsset,
    SourceVisualRecord,
)
from deeper_notebook.source_visuals.storage import (
    TOMBSTONE,
    SourceVisualStorageError,
    SourceVisualStore,
    asset_relpath,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)


def _prepared(payload: bytes = b"derived-webp") -> PreparedVisualAsset:
    return PreparedVisualAsset(
        encoded_bytes=payload,
        asset_sha256=hashlib.sha256(payload).hexdigest(),
        width=640,
        height=360,
    )


def _record(
    stored: object,
    *,
    source_id: str = "source:one",
    content_sha256: str = "a" * 64,
    updated_at: datetime = NOW,
) -> SourceVisualRecord:
    return SourceVisualRecord(
        source_id=source_id,
        source_updated_at=NOW,
        source_file_sha256=None,
        content_sha256=content_sha256,
        asset_sha256=getattr(stored, "asset_sha256"),
        asset_relpath=getattr(stored, "asset_relpath"),
        origin="embedded",
        source_locator={"page": 1},
        extractor_version="source-visual-v1",
        alt_text="Source visual",
        width=getattr(stored, "width"),
        height=getattr(stored, "height"),
        created_at=updated_at,
        updated_at=updated_at,
    )


def _publish(
    store: SourceVisualStore,
    payload: bytes = b"derived-webp",
    *,
    source_id: str = "source:one",
    content_sha256: str = "a" * 64,
):
    staged = store.stage(source_id, content_sha256, _prepared(payload))
    return store.publish(staged)


def _install_hash_exchange(
    monkeypatch: pytest.MonkeyPatch, exchange: Callable[[], None]
) -> None:
    storage = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["_hash_fd"]
    )
    original_hash_fd = storage._hash_fd
    original_read = os.read
    exchanged = False

    def exchange_during_hash(fd: int, count: int) -> bytes:
        nonlocal exchanged
        if not exchanged:
            exchange()
            exchanged = True
        return original_read(fd, count)

    def hash_fd(fd: int) -> tuple[str, int]:
        monkeypatch.setattr(
            "deeper_notebook.source_visuals.storage.os.read", exchange_during_hash
        )
        try:
            return original_hash_fd(fd)
        finally:
            monkeypatch.setattr(
                "deeper_notebook.source_visuals.storage.os.read", original_read
            )

    monkeypatch.setattr("deeper_notebook.source_visuals.storage._hash_fd", hash_fd)


def _hold_store_mutation(
    data_folder: str, entered: "mp.synchronize.Event", release: "mp.synchronize.Event"
) -> None:
    store = SourceVisualStore(data_folder=data_folder)
    with store.mutation_guard():
        entered.set()
        release.wait(timeout=5)


def _enter_store_mutation(
    data_folder: str, entered: "mp.synchronize.Event"
) -> None:
    store = SourceVisualStore(data_folder=data_folder)
    with store.mutation_guard():
        entered.set()


def _crash_in_store_mutation(
    data_folder: str, entered: "mp.synchronize.Event"
) -> None:
    store = SourceVisualStore(data_folder=data_folder)
    with store.mutation_guard():
        entered.set()
        os._exit(0)


def _stage_inside_mutation_guard(
    data_folder: str, completed: "mp.synchronize.Event"
) -> None:
    store = SourceVisualStore(data_folder=data_folder)
    with store.mutation_guard():
        store.stage("source:one", "a" * 64, _prepared())
    completed.set()


def _complete_if_store_lock_order_is_safe(
    data_folder: str, completed: "mp.synchronize.Event"
) -> None:
    store = SourceVisualStore(data_folder=data_folder)
    stored = _publish(store)
    record = _record(stored)
    tombstone_waiting = threading.Event()
    reader_in_guard = threading.Event()
    release_tombstone = threading.Event()
    original_guard = store.mutation_guard
    errors: list[BaseException] = []

    @contextmanager
    def controlled_guard():
        if threading.current_thread().name == "tombstone":
            tombstone_waiting.set()
            release_tombstone.wait(timeout=2)
        with original_guard() as root_fd:
            if threading.current_thread().name == "reader":
                reader_in_guard.set()
            yield root_fd

    store.mutation_guard = controlled_guard  # type: ignore[method-assign]

    def tombstone_asset() -> None:
        try:
            store.tombstone(record)
        except BaseException as exc:  # pragma: no cover - failure reported below.
            errors.append(exc)

    def read_asset() -> None:
        try:
            store.read_exact(record)
        except BaseException as exc:  # pragma: no cover - failure reported below.
            errors.append(exc)

    tombstone = threading.Thread(target=tombstone_asset, name="tombstone", daemon=True)
    reader = threading.Thread(target=read_asset, name="reader", daemon=True)
    tombstone.start()
    if not tombstone_waiting.wait(timeout=2):
        return
    reader.start()
    if not reader_in_guard.wait(timeout=2):
        return
    release_tombstone.set()
    tombstone.join(timeout=1)
    reader.join(timeout=1)
    if not tombstone.is_alive() and not reader.is_alive() and not errors:
        completed.set()


def _record_link_durability_events(
    monkeypatch: pytest.MonkeyPatch, **parent_paths: Path
) -> list[str]:
    original_fsync = os.fsync
    original_link = os.link
    original_stat = os.fstat
    original_unlink = os.unlink
    identities = {
        (path.stat().st_dev, path.stat().st_ino): role
        for role, path in parent_paths.items()
    }
    events: list[str] = []

    def fsync(descriptor: int) -> None:
        metadata = original_stat(descriptor)
        role = identities.get((metadata.st_dev, metadata.st_ino), "other")
        events.append(f"fsync:{role}")
        original_fsync(descriptor)

    def link(*args: object, **kwargs: object) -> None:
        original_link(*args, **kwargs)
        events.append("link")

    def unlink(*args: object, **kwargs: object) -> None:
        events.append("unlink")
        original_unlink(*args, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", fsync)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.unlink", unlink)
    return events


def test_asset_relpath_contains_only_derived_hash_segments():
    relpath = asset_relpath("source:one", "a" * 64, "b" * 64)
    assert relpath == (
        f"{hashlib.sha256(b'source:one').hexdigest()[:2]}/{'a' * 64}/{'b' * 64}.webp"
    )
    for invalid in ("A" * 64, "a" * 63, "../" + "a" * 61):
        with pytest.raises(SourceVisualStorageError):
            asset_relpath("source:one", invalid, "b" * 64)


def test_stage_is_exclusive_hashes_reopened_bytes_and_publish_fsyncs_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    events: list[str] = []
    original_fsync = os.fsync
    original_link = os.link

    def fsync(fd: int) -> None:
        events.append("fsync")
        original_fsync(fd)

    def link(*args: object, **kwargs: object) -> None:
        events.append("link")
        original_link(*args, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", fsync)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.secrets.token_hex",
        lambda _n: "1" * 64,
    )

    prepared = _prepared()
    staged = store.stage("source:one", "a" * 64, prepared)
    with pytest.raises(SourceVisualStorageError) as duplicate:
        store.stage("source:one", "a" * 64, prepared)
    assert duplicate.value.code == "TEMP_CREATE_FAILED"
    stored = store.publish(staged)

    assert events.index("fsync") < events.index("link") < len(events) - 1
    assert events[-1] == "fsync"
    assert store.read_exact(_record(stored)) == prepared.encoded_bytes


def test_publish_keeps_one_root_identity_across_temp_and_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    cache_parent = tmp_path / "source-visual-cache"
    held_parent = tmp_path / "held-cache-parent"
    replacement_root = cache_parent / "v1"
    original_open_regular = store._open_regular_file
    swapped = False

    def open_regular(parent_fd: int, name: str) -> int:
        nonlocal swapped
        descriptor = original_open_regular(parent_fd, name)
        if name == staged.temp_name and not swapped:
            cache_parent.rename(held_parent)
            replacement_root.mkdir(parents=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(store, "_open_regular_file", open_regular)

    stored = store.publish(staged)

    assert (held_parent / "v1" / stored.asset_relpath).read_bytes() == b"derived-webp"
    assert not (replacement_root / stored.asset_relpath).exists()


def test_publish_rejects_temp_path_exchange_after_descriptor_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    original_link = os.link
    exchanged = False

    def exchange_then_link(*args: object, **kwargs: object) -> None:
        nonlocal exchanged
        if not exchanged and args and args[0] == staged.temp_name:
            temp_path = store.root / ".tmp" / staged.temp_name
            verified_path = temp_path.with_suffix(".verified")
            temp_path.rename(verified_path)
            temp_path.write_bytes(b"unverified-replacement")
            exchanged = True
        original_link(*args, **kwargs)

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.link", exchange_then_link
    )

    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert not (store.root / asset_relpath("source:one", "a" * 64, staged.asset_sha256)).exists()


def test_publish_accepts_matching_destination_that_appears_at_link_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    original_link = os.link
    appeared = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal appeared
        if dst == canonical.name and not appeared:
            canonical.write_bytes(b"derived-webp")
            appeared = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)

    stored = store.publish(staged)

    assert appeared
    assert stored.asset_relpath == str(canonical.relative_to(store.root))
    assert canonical.read_bytes() == b"derived-webp"
    assert not (store.root / ".tmp" / staged.temp_name).exists()


def test_publish_revalidates_existing_canonical_path_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    existing = _publish(store)
    staged = store.stage("source:one", "a" * 64, _prepared())
    canonical = store.root / existing.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")
    staged_path = store.root / ".tmp" / staged.temp_name
    original_hash_fd = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["_hash_fd"]
    )._hash_fd
    original_read = os.read
    hash_calls = 0
    exchanged = False

    def exchange_during_hash(fd: int, count: int) -> bytes:
        nonlocal exchanged
        if not exchanged:
            canonical.rename(held)
            canonical.write_bytes(b"canonical-path-replacement")
            exchanged = True
        return original_read(fd, count)

    def hash_fd(fd: int) -> tuple[str, int]:
        nonlocal hash_calls
        hash_calls += 1
        if hash_calls == 2:
            monkeypatch.setattr(
                "deeper_notebook.source_visuals.storage.os.read", exchange_during_hash
            )
            try:
                return original_hash_fd(fd)
            finally:
                monkeypatch.setattr(
                    "deeper_notebook.source_visuals.storage.os.read", original_read
                )
        return original_hash_fd(fd)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage._hash_fd", hash_fd)

    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert hash_calls == 2
    assert exchanged
    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert canonical.read_bytes() == b"canonical-path-replacement"
    assert held.read_bytes() == b"derived-webp"
    assert staged_path.read_bytes() == b"derived-webp"


def test_mutation_guard_serializes_independent_store_processes(tmp_path: Path):
    context = mp.get_context("fork")
    first_entered = context.Event()
    release = context.Event()
    second_entered = context.Event()
    first = context.Process(
        target=_hold_store_mutation,
        args=(str(tmp_path), first_entered, release),
    )
    second = context.Process(
        target=_enter_store_mutation,
        args=(str(tmp_path), second_entered),
    )
    second_started = False
    first.start()
    try:
        assert first_entered.wait(timeout=5)
        second.start()
        second_started = True
        assert not second_entered.wait(timeout=0.25)
        release.set()
        assert second_entered.wait(timeout=5)
    finally:
        release.set()
        if first.pid is not None:
            first.join(timeout=5)
        if second_started:
            second.join(timeout=5)
        if first.is_alive():
            first.kill()
            first.join(timeout=5)
        if second.is_alive():
            second.kill()
            second.join(timeout=5)
    assert first.exitcode == 0
    assert second.exitcode == 0


def test_mutation_guard_lock_file_crash_release_and_fail_closed_entries(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    root_fd = store._ensure_root()
    os.close(root_fd)
    lock_path = store.root / ".mutation.lock"
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"outside")

    lock_path.symlink_to(outside)
    with pytest.raises(SourceVisualStorageError) as symlink_error:
        with store.mutation_guard():
            pass
    assert symlink_error.value.code == "CACHE_LOCK_INVALID"

    lock_path.unlink()
    lock_path.mkdir()
    with pytest.raises(SourceVisualStorageError) as nonregular_error:
        with store.mutation_guard():
            pass
    assert nonregular_error.value.code == "CACHE_LOCK_INVALID"
    lock_path.rmdir()

    context = mp.get_context("fork")
    entered = context.Event()
    crashed = context.Process(
        target=_crash_in_store_mutation,
        args=(str(tmp_path), entered),
    )
    crashed.start()
    assert entered.wait(timeout=5)
    crashed.join(timeout=5)
    assert crashed.exitcode == 0
    with store.mutation_guard():
        pass


def test_publish_destination_appearance_at_no_replace_boundary_preserves_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    original_link = os.link
    appeared = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal appeared
        if dst == canonical.name and not appeared:
            canonical.write_bytes(b"foreign-destination")
            appeared = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert appeared
    assert canonical.read_bytes() == b"foreign-destination"
    assert (store.root / ".tmp" / staged.temp_name).read_bytes() == b"derived-webp"


def test_publish_source_exchange_at_link_boundary_preserves_verified_and_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    temp_path = store.root / ".tmp" / staged.temp_name
    held = temp_path.with_suffix(".held")
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    original_link = os.link
    exchanged = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal exchanged
        if src == staged.temp_name and not exchanged:
            temp_path.rename(held)
            temp_path.write_bytes(b"foreign-stage-replacement")
            exchanged = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged
    assert held.read_bytes() == b"derived-webp"
    assert temp_path.read_bytes() == b"foreign-stage-replacement"
    assert not canonical.exists()


def test_tombstone_source_exchange_does_not_move_foreign_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    canonical = store.root / record.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")
    original_link = os.link
    exchanged = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal exchanged
        if src == canonical.name and not exchanged:
            canonical.rename(held)
            canonical.write_bytes(b"foreign-canonical")
            exchanged = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged
    assert held.read_bytes() == b"derived-webp"
    assert canonical.read_bytes() == b"foreign-canonical"
    assert all(
        path.read_bytes() != b"derived-webp"
        for path in canonical.parent.glob(".expired-*.webp")
    )


def test_restore_destination_appearance_preserves_destination_and_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    tombstone_path = canonical.with_name(tombstone.tombstone_name)
    original_link = os.link
    appeared = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal appeared
        if dst == canonical.name and not appeared:
            canonical.write_bytes(b"foreign-destination")
            appeared = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.restore_tombstone(tombstone)

    assert error.value.code == "TOMBSTONE_INVALID"
    assert appeared
    assert canonical.read_bytes() == b"foreign-destination"
    assert tombstone_path.read_bytes() == b"derived-webp"


def test_restore_source_exchange_fails_without_cleaning_verified_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    tombstone_path = canonical.with_name(tombstone.tombstone_name)
    held = tombstone_path.with_name(f"{tombstone_path.name}.held")
    original_link = os.link
    exchanged = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal exchanged
        if src == tombstone.tombstone_name and not exchanged:
            tombstone_path.rename(held)
            tombstone_path.write_bytes(b"foreign-tombstone")
            exchanged = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.restore_tombstone(tombstone)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged
    assert held.read_bytes() == b"derived-webp"
    assert tombstone_path.read_bytes() == b"foreign-tombstone"
    assert canonical.read_bytes() == b"foreign-tombstone"


def test_remove_source_exchange_retains_foreign_and_quarantine_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    source = store.root / record.asset_relpath
    tombstone_path = source.with_name(tombstone.tombstone_name)
    held = tombstone_path.with_name(f"{tombstone_path.name}.held")
    original_link = os.link
    exchanged = False

    def link(src: object, dst: object, **kwargs: object) -> None:
        nonlocal exchanged
        if src == tombstone.tombstone_name and not exchanged:
            tombstone_path.rename(held)
            tombstone_path.write_bytes(b"foreign-tombstone")
            exchanged = True
        original_link(src, dst, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.remove_tombstone(tombstone)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged
    assert held.read_bytes() == b"derived-webp"
    assert tombstone_path.read_bytes() == b"foreign-tombstone"
    assert any(
        path.read_bytes() == b"foreign-tombstone"
        for path in source.parent.glob(".expired-*.webp")
        if path != tombstone_path
    )


@pytest.mark.asyncio
async def test_reconciliation_keeps_verified_tombstone_when_canonical_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    canonical.write_bytes(b"derived-webp")
    held = canonical.with_name(f"{canonical.name}.held")
    storage = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["_hash_fd"]
    )
    original_hash_fd = storage._hash_fd
    exchanged = False

    def hash_fd(fd: int) -> tuple[str, int]:
        nonlocal exchanged
        result = original_hash_fd(fd)
        if not exchanged:
            canonical.rename(held)
            canonical.write_bytes(b"foreign-canonical")
            exchanged = True
        return result

    monkeypatch.setattr(storage, "_hash_fd", hash_fd)
    repository = _Repository([record])
    processed = await SourceVisualCleanup(store, repository).reconcile_tombstones(
        limit=100
    )

    assert processed == 0
    assert exchanged
    assert tombstone is not None
    assert (canonical.parent / tombstone.tombstone_name).read_bytes() == b"derived-webp"
    assert canonical.read_bytes() == b"foreign-canonical"
    assert held.read_bytes() == b"derived-webp"


@pytest.mark.parametrize("entry_kind", ["symlink", "directory"])
def test_lock_and_quarantine_entries_fail_closed_without_traversal(
    tmp_path: Path, entry_kind: str
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    parent = store.root / record.asset_relpath
    parent = parent.parent
    quarantine = parent / f".expired-{'a' * 16}-{record.asset_sha256}.webp"
    if entry_kind == "symlink":
        outside = tmp_path / "outside-quarantine"
        outside.write_bytes(b"outside")
        quarantine.symlink_to(outside)
    else:
        quarantine.mkdir()

    with pytest.raises(SourceVisualStorageError) as error:
        store.list_tombstones(limit=100)
    assert error.value.code == "TOMBSTONE_INVALID"


def test_stage_rejects_asset_hash_mismatch(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    prepared = _prepared().model_copy(update={"asset_sha256": "f" * 64})
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, prepared)
    assert error.value.code == "ASSET_HASH_MISMATCH"


def test_publish_binds_temp_identity_to_staged_content_and_asset_hash(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())

    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(replace(staged, content_sha256="b" * 64))

    assert error.value.code == "TEMP_INVALID"


def test_store_rejects_symlinked_root_segment_file_and_nonregular_file(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    cache_parent = tmp_path / "source-visual-cache"
    cache_parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SourceVisualStorageError) as root_error:
        SourceVisualStore(data_folder=tmp_path).stage(
            "source:one", "a" * 64, _prepared()
        )
    assert root_error.value.code == "CACHE_ROOT_SYMLINK"

    cache_parent.unlink()
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    asset = tmp_path / "source-visual-cache" / "v1" / record.asset_relpath
    asset.unlink()
    asset.symlink_to(outside / "asset.webp")
    with pytest.raises(SourceVisualStorageError) as file_error:
        store.read_exact(record)
    assert file_error.value.code == "ASSET_SYMLINK"

    asset.unlink()
    asset.mkdir()
    with pytest.raises(SourceVisualStorageError) as regular_error:
        store.read_exact(record)
    assert regular_error.value.code == "ASSET_NOT_REGULAR"

    asset.rmdir()
    content_dir = asset.parent
    content_dir.rmdir()
    content_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SourceVisualStorageError) as segment_error:
        store.read_exact(record)
    assert segment_error.value.code == "CACHE_PATH_SYMLINK"


def test_record_relpath_cannot_escape_to_sibling_prefix(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    escaped = record.model_copy(update={"asset_relpath": "../v1-sibling/file.webp"})
    with pytest.raises(SourceVisualStorageError) as error:
        store.read_exact(escaped)
    assert error.value.code == "ASSET_RELPATH_INVALID"


def test_read_exact_rejects_changed_bytes(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    asset = tmp_path / "source-visual-cache" / "v1" / record.asset_relpath
    asset.write_bytes(b"changed")
    with pytest.raises(SourceVisualStorageError) as error:
        store.read_exact(record)
    assert error.value.code == "ASSET_HASH_MISMATCH"


def test_bounded_cache_scans_close_the_owned_root_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    _publish(store)
    opened: list[int] = []
    closed: list[int] = []
    original_ensure_root = store._ensure_root
    original_close = os.close

    def ensure_root() -> int:
        descriptor = original_ensure_root()
        opened.append(descriptor)
        return descriptor

    def close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(store, "_ensure_root", ensure_root)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.close", close)

    store.list_tombstones(limit=100)
    store.cache_size_bytes()

    assert opened
    assert set(opened).issubset(closed)


def test_cache_scan_uses_the_open_root_descriptor_after_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    expected_size = stored.byte_size
    outside = tmp_path / "outside"
    outside_asset = outside / Path(stored.asset_relpath)
    outside_asset.parent.mkdir(parents=True)
    outside_asset.write_bytes(b"outside-controlled-root" * 2)
    original_ensure_root = store._ensure_root
    swapped = False

    def ensure_and_swap() -> int:
        nonlocal swapped
        descriptor = original_ensure_root()
        if not swapped:
            held = tmp_path / "held-cache-root"
            store.root.rename(held)
            store.root.symlink_to(outside, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(store, "_ensure_root", ensure_and_swap)

    assert store.cache_size_bytes() == expected_size
    assert outside_asset.read_bytes() == b"outside-controlled-root" * 2


def test_cache_root_descent_stays_on_open_parent_after_parent_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    outside = tmp_path / "outside-parent"
    outside_asset = outside / "v1" / Path(stored.asset_relpath)
    outside_asset.parent.mkdir(parents=True)
    outside_asset.write_bytes(b"outside")
    cache_parent = tmp_path / "source-visual-cache"
    held_parent = tmp_path / "held-cache-parent"
    swapped = False
    original_open_child_dir = store._open_child_dir
    original_path_mkdir = Path.mkdir

    def swap_parent() -> None:
        nonlocal swapped
        if swapped:
            return
        cache_parent.rename(held_parent)
        cache_parent.symlink_to(outside, target_is_directory=True)
        swapped = True

    def path_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        original_path_mkdir(path, *args, **kwargs)
        if path == cache_parent:
            swap_parent()

    def open_child_dir(parent_fd: int, name: str, *, create: bool) -> int:
        descriptor = original_open_child_dir(parent_fd, name, create=create)
        if name == "source-visual-cache":
            swap_parent()
        return descriptor

    monkeypatch.setattr(Path, "mkdir", path_mkdir)
    monkeypatch.setattr(store, "_open_child_dir", open_child_dir)

    assert store.cache_size_bytes() == stored.byte_size
    assert outside_asset.read_bytes() == b"outside"


def test_cache_scan_bounds_noncanonical_entries(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    root_fd = store._ensure_root()
    os.close(root_fd)
    for index in range(4097):
        (store.root / f"junk-{index:04d}").touch()

    with pytest.raises(SourceVisualStorageError) as error:
        store.cache_size_bytes()

    assert error.value.code == "CACHE_SCAN_LIMIT"


def test_tombstone_revalidates_canonical_path_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    canonical = store.root / record.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")

    def exchange() -> None:
        canonical.rename(held)
        canonical.write_bytes(b"foreign-canonical-replacement")

    _install_hash_exchange(monkeypatch, exchange)

    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert canonical.read_bytes() == b"foreign-canonical-replacement"
    assert held.read_bytes() == b"derived-webp"
    assert all(
        path.read_bytes() != b"derived-webp"
        for path in canonical.parent.glob(".expired-*.webp")
    )


def test_restore_revalidates_tombstone_path_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    tombstone_path = canonical.with_name(tombstone.tombstone_name)
    held = tombstone_path.with_name(f"{tombstone_path.name}.held")

    def exchange() -> None:
        tombstone_path.rename(held)
        tombstone_path.write_bytes(b"foreign-tombstone-replacement")

    _install_hash_exchange(monkeypatch, exchange)

    with pytest.raises(SourceVisualStorageError) as error:
        store.restore_tombstone(tombstone)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert canonical.read_bytes() == b"foreign-tombstone-replacement"
    assert tombstone_path.read_bytes() == b"foreign-tombstone-replacement"
    assert held.read_bytes() == b"derived-webp"


def test_restore_revalidates_destination_absence_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    tombstone_path = canonical.with_name(tombstone.tombstone_name)

    def exchange() -> None:
        canonical.write_bytes(b"new-canonical-asset")

    _install_hash_exchange(monkeypatch, exchange)

    with pytest.raises(SourceVisualStorageError) as error:
        store.restore_tombstone(tombstone)

    assert error.value.code == "TOMBSTONE_INVALID"
    assert canonical.read_bytes() == b"new-canonical-asset"
    assert tombstone_path.read_bytes() == b"derived-webp"


def test_remove_revalidates_tombstone_path_after_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    tombstone_path = store.root / record.asset_relpath
    tombstone_path = tombstone_path.with_name(tombstone.tombstone_name)
    held = tombstone_path.with_name(f"{tombstone_path.name}.held")

    def exchange() -> None:
        tombstone_path.rename(held)
        tombstone_path.write_bytes(b"foreign-tombstone-replacement")

    _install_hash_exchange(monkeypatch, exchange)

    with pytest.raises(SourceVisualStorageError) as error:
        store.remove_tombstone(tombstone)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert tombstone_path.read_bytes() == b"foreign-tombstone-replacement"
    assert held.read_bytes() == b"derived-webp"


def test_tombstone_restore_remove_and_replacement_window(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    with pytest.raises(SourceVisualStorageError):
        store.read_exact(record)
    store.restore_tombstone(tombstone)
    assert store.read_exact(record) == b"derived-webp"

    tombstone = store.tombstone(record)
    assert tombstone is not None
    store.remove_tombstone(tombstone)
    assert store.tombstone(record) is None


def test_active_read_fences_tombstone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store, b"x" * (256 * 1024))
    record = _record(stored)
    entered = threading.Event()
    release = threading.Event()
    original_read = os.read

    def blocked_read(fd: int, count: int) -> bytes:
        entered.set()
        release.wait(timeout=5)
        return original_read(fd, count)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.read", blocked_read)
    thread = threading.Thread(target=store.read_exact, args=(record,), daemon=True)
    thread.start()
    assert entered.wait(timeout=5)
    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)
    assert error.value.code == "ASSET_BUSY"
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_mutation_guard_and_active_reads_share_one_lock_order(tmp_path: Path):
    context = mp.get_context("fork")
    completed = context.Event()
    child = context.Process(
        target=_complete_if_store_lock_order_is_safe,
        args=(str(tmp_path), completed),
    )
    child.start()
    try:
        child.join(timeout=5)
    finally:
        if child.is_alive():
            child.kill()
            child.join(timeout=5)

    assert child.exitcode == 0
    assert completed.is_set()


def test_publish_fsyncs_destination_before_unlinking_staged_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    destination = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    destination.parent.mkdir(parents=True)
    events = _record_link_durability_events(
        monkeypatch,
        destination=destination.parent,
        stage=store.root / ".tmp",
    )

    store.publish(staged)

    assert events.index("link") < events.index("fsync:destination") < events.index(
        "unlink"
    )
    assert events[-1] == "fsync:stage"


def test_tombstone_fsyncs_link_before_unlinking_canonical_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    events = _record_link_durability_events(
        monkeypatch,
        asset=(store.root / record.asset_relpath).parent,
    )

    assert store.tombstone(record) is not None

    assert events.index("link") < events.index("fsync:asset") < events.index("unlink")
    assert events[-1] == "fsync:asset"


def test_restore_fsyncs_link_before_unlinking_tombstone_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    events = _record_link_durability_events(
        monkeypatch,
        asset=(store.root / record.asset_relpath).parent,
    )

    store.restore_tombstone(tombstone)

    assert events.index("link") < events.index("fsync:asset") < events.index("unlink")
    assert events[-1] == "fsync:asset"


def test_remove_fsyncs_quarantine_link_before_unlinking_tombstone_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    events = _record_link_durability_events(
        monkeypatch,
        asset=(store.root / record.asset_relpath).parent,
    )

    store.remove_tombstone(tombstone)

    assert events.index("link") < events.index("fsync:asset") < events.index("unlink")
    assert events[-1] == "fsync:asset"


def test_cross_store_read_holds_mutation_guard_until_tombstone_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reader_store = SourceVisualStore(data_folder=tmp_path)
    mutator_store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(reader_store, b"x" * (256 * 1024))
    record = _record(stored)
    canonical = reader_store.root / record.asset_relpath
    entered = threading.Event()
    release = threading.Event()
    tombstone_finished = threading.Event()
    original_read = os.read
    read_blocked = False
    reader_results: list[bytes] = []
    reader_errors: list[BaseException] = []
    tombstone_errors: list[BaseException] = []
    tombstones: list[object] = []

    def blocked_read(descriptor: int, count: int) -> bytes:
        nonlocal read_blocked
        if not read_blocked:
            read_blocked = True
            entered.set()
            release.wait(timeout=5)
        return original_read(descriptor, count)

    def read_asset() -> None:
        try:
            reader_results.append(reader_store.read_exact(record))
        except BaseException as exc:  # pragma: no cover - failure is asserted below.
            reader_errors.append(exc)

    def tombstone_asset() -> None:
        try:
            tombstones.append(mutator_store.tombstone(record))
        except BaseException as exc:  # pragma: no cover - failure is asserted below.
            tombstone_errors.append(exc)
        finally:
            tombstone_finished.set()

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.read", blocked_read)
    reader = threading.Thread(target=read_asset, daemon=True)
    mutator = threading.Thread(target=tombstone_asset, daemon=True)
    reader.start()
    try:
        assert entered.wait(timeout=5)
        mutator.start()
        assert not tombstone_finished.wait(timeout=0.25)
        assert canonical.exists()
    finally:
        release.set()
        reader.join(timeout=5)
        mutator.join(timeout=5)

    assert not reader.is_alive()
    assert not mutator.is_alive()
    assert reader_errors == []
    assert tombstone_errors == []
    assert reader_results == [b"x" * (256 * 1024)]
    assert len(tombstones) == 1
    assert not canonical.exists()


class _Repository:
    def __init__(self, records: list[SourceVisualRecord]):
        self.records = list(records)
        self.active: set[str] = set()
        self.fail_delete = False
        self.list_limits: list[int] = []

    async def find_ready_by_asset_relpath(
        self, relpath: str
    ) -> SourceVisualRecord | None:
        return next(
            (record for record in self.records if record.asset_relpath == relpath), None
        )

    async def delete_ready_if_current(self, record: SourceVisualRecord) -> bool:
        if self.fail_delete:
            raise RuntimeError("database unavailable")
        for index, current in enumerate(self.records):
            if current == record:
                self.records.pop(index)
                return True
        return False

    async def list_ready_for_eviction(self, *, limit: int) -> list[SourceVisualRecord]:
        self.list_limits.append(limit)
        return sorted(self.records, key=lambda record: record.updated_at)[:limit]

    async def is_claim_active(self, record: SourceVisualRecord) -> bool:
        return record.asset_relpath in self.active


@pytest.mark.asyncio
async def test_database_delete_failure_restores_original(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    repository = _Repository([record])
    repository.fail_delete = True
    cleanup = SourceVisualCleanup(store, repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await cleanup.delete_record(record)
    assert store.read_exact(record) == b"derived-webp"
    assert repository.records == [record]


@pytest.mark.asyncio
async def test_unlink_failure_leaves_tombstone_for_bounded_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    repository = _Repository([record])
    cleanup = SourceVisualCleanup(store, repository)
    original_remove = store.remove_tombstone

    def fail_remove(_tombstone: object) -> None:
        raise OSError("busy")

    monkeypatch.setattr(store, "remove_tombstone", fail_remove)
    assert await cleanup.delete_record(record) is True
    assert repository.records == []
    monkeypatch.setattr(store, "remove_tombstone", original_remove)
    assert await cleanup.reconcile_tombstones(limit=100) == 1
    assert store.list_tombstones(limit=100) == ()


@pytest.mark.asyncio
async def test_reconcile_restores_referenced_tombstone_and_ignores_malformed_names(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    parent = tmp_path / "source-visual-cache" / "v1" / Path(record.asset_relpath).parent
    (parent / ".expired-bad.webp").write_bytes(b"unowned")
    repository = _Repository([record])
    cleanup = SourceVisualCleanup(store, repository)

    assert await cleanup.reconcile_tombstones(limit=100) == 1
    assert store.read_exact(record) == b"derived-webp"
    assert (parent / ".expired-bad.webp").read_bytes() == b"unowned"


@pytest.mark.asyncio
async def test_reconcile_removes_old_tombstone_when_exact_replacement_exists(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    replacement = store.root / record.asset_relpath
    replacement.write_bytes(b"derived-webp")
    repository = _Repository([record])

    processed = await SourceVisualCleanup(store, repository).reconcile_tombstones(
        limit=100
    )

    assert processed == 1
    assert store.read_exact(record) == b"derived-webp"
    assert store.list_tombstones(limit=100) == ()


@pytest.mark.asyncio
async def test_reconcile_processes_at_most_requested_owned_tombstones(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    records: list[SourceVisualRecord] = []
    for index in range(5):
        content_hash = f"{index + 1:064x}"
        stored = _publish(store, f"asset-{index}".encode(), content_sha256=content_hash)
        record = _record(stored, content_sha256=content_hash)
        records.append(record)
        assert store.tombstone(record) is not None
    cleanup = SourceVisualCleanup(store, _Repository([]))
    assert await cleanup.reconcile_tombstones(limit=3) == 3
    assert len(store.list_tombstones(limit=100)) == 2


@pytest.mark.asyncio
async def test_eviction_is_bounded_oldest_first_skips_active_and_preserves_sources(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    source = tmp_path / "uploads" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(b"authoritative source")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    records: list[SourceVisualRecord] = []
    for index, size in enumerate((40, 50, 60)):
        content_hash = f"{index + 1:064x}"
        stored = _publish(store, bytes([index + 1]) * size, content_sha256=content_hash)
        records.append(
            _record(
                stored,
                content_sha256=content_hash,
                updated_at=NOW + timedelta(minutes=index),
            )
        )
    repository = _Repository(records)
    repository.active.add(records[0].asset_relpath)
    cleanup = SourceVisualCleanup(store, repository)

    removed = await cleanup.evict_to_budget(max_bytes=45, page_size=2)

    assert removed == 2
    assert repository.records == [records[0]]
    assert repository.list_limits and all(
        limit <= 2 for limit in repository.list_limits
    )
    assert store.read_exact(records[0]) == bytes([1]) * 40
    assert source.read_bytes() == b"authoritative source"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


@pytest.mark.asyncio
async def test_eviction_stops_when_bounded_page_makes_no_progress(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store, b"x" * 100)
    record = _record(stored)
    repository = _Repository([record])
    repository.active.add(record.asset_relpath)
    cleanup = SourceVisualCleanup(store, repository)

    assert (
        await asyncio.wait_for(
            cleanup.evict_to_budget(max_bytes=1, page_size=100), timeout=1
        )
        == 0
    )
    assert repository.records == [record]


@pytest.mark.asyncio
async def test_eviction_remeasures_physical_bytes_when_tombstone_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    records = [
        _record(
            _publish(
                store,
                payload,
                content_sha256=f"{index + 1:064x}",
            ),
            content_sha256=f"{index + 1:064x}",
        )
        for index, payload in enumerate((b"a" * 100, b"b" * 100))
    ]
    repository = _Repository(records)
    cleanup = SourceVisualCleanup(store, repository)
    original_cache_size = store.cache_size_bytes
    observed_sizes: list[int] = []

    def cache_size() -> int:
        size = original_cache_size()
        observed_sizes.append(size)
        return size

    def fail_remove(_tombstone: object) -> None:
        raise OSError("unlink failed")

    monkeypatch.setattr(store, "cache_size_bytes", cache_size)
    monkeypatch.setattr(store, "remove_tombstone", fail_remove)

    removed = await asyncio.wait_for(
        cleanup.evict_to_budget(max_bytes=150, page_size=100), timeout=1
    )

    assert removed == 2
    assert repository.records == []
    assert observed_sizes[0] == observed_sizes[-1] == 200
    assert len(observed_sizes) == 3
    assert store.cache_size_bytes() > 150


def test_stage_maps_write_failure_and_removes_only_the_owned_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)

    def fail_write(_fd: int, _payload: object) -> int:
        raise OSError("write failed")

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.write", fail_write)
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "ASSET_IO_FAILED"
    assert not list((store.root / ".tmp").glob("stage-*.tmp"))


def test_stage_keeps_unverified_temp_when_initial_fstat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    original_open = os.open
    original_fstat = os.fstat
    created_stage_fds: set[int] = set()

    def open_file(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if str(path).startswith(("stage-", ".unverified-stage-")) and flags & os.O_EXCL:
            created_stage_fds.add(descriptor)
        return descriptor

    def fail_initial_stage_fstat(descriptor: int) -> os.stat_result:
        if descriptor in created_stage_fds:
            raise OSError("initial stage stat failed")
        return original_fstat(descriptor)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.open", open_file)
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.fstat", fail_initial_stage_fstat
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "TEMP_CREATE_FAILED"
    temp_dir = store.root / ".tmp"
    assert not list(temp_dir.glob("stage-*.tmp"))
    assert len(list(temp_dir.glob(".unverified-stage-*"))) == 1


def test_stage_initial_fstat_failure_preserves_an_exchanged_foreign_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    original_open = os.open
    original_fstat = os.fstat
    created_stage_fds: set[int] = set()
    held: Path | None = None

    def open_file(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if str(path).startswith(("stage-", ".unverified-stage-")) and flags & os.O_EXCL:
            created_stage_fds.add(descriptor)
        return descriptor

    def exchange_then_fail(descriptor: int) -> os.stat_result:
        nonlocal held
        if descriptor in created_stage_fds:
            temp_dir = store.root / ".tmp"
            stage_path = next(
                iter(list(temp_dir.glob(".unverified-stage-*")) + list(temp_dir.glob("stage-*.tmp")))
            )
            held = stage_path.with_suffix(".held")
            stage_path.rename(held)
            stage_path.write_bytes(b"foreign-stage")
            raise OSError("initial stage stat failed")
        return original_fstat(descriptor)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.open", open_file)
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.fstat", exchange_then_fail
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "TEMP_CREATE_FAILED"
    assert held is not None and held.exists()
    temp_dir = store.root / ".tmp"
    assert not list(temp_dir.glob("stage-*.tmp"))
    unverified = next(
        candidate
        for candidate in temp_dir.glob(".unverified-stage-*")
        if candidate.suffix == ".tmp"
    )
    assert unverified.read_bytes() == b"foreign-stage"
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fstat", original_fstat)
    assert store.reconcile_staged_files(limit=100, now=time.time() + 601) == 0
    assert unverified.read_bytes() == b"foreign-stage"


def test_publish_rejects_same_inode_bytes_changed_at_link_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    stage_path = store.root / ".tmp" / staged.temp_name
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    original_link = os.link

    def mutate_then_link(*args: object, **kwargs: object) -> None:
        if args and args[0] == staged.temp_name:
            stage_path.write_bytes(b"altered-webp")
        original_link(*args, **kwargs)

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.link", mutate_then_link
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert not canonical.exists()
    assert stage_path.read_bytes() == b"altered-webp"


def test_tombstone_fenced_removal_preserves_exchange_at_removal_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    canonical = store.root / record.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")
    original_rename = os.rename
    original_unlink = os.unlink
    exchanged = False

    def exchange_source() -> None:
        nonlocal exchanged
        if not exchanged:
            original_rename(canonical, held)
            canonical.write_bytes(b"foreign-canonical")
            exchanged = True

    def rename(*args: object, **kwargs: object) -> None:
        if args and args[0] == canonical.name:
            exchange_source()
        original_rename(*args, **kwargs)

    def unlink(*args: object, **kwargs: object) -> None:
        if args and args[0] == canonical.name:
            exchange_source()
        original_unlink(*args, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.rename", rename)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.unlink", unlink)
    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged
    assert canonical.read_bytes() == b"foreign-canonical"
    assert held.read_bytes() == b"derived-webp"
    assert not list(canonical.parent.glob(".unlink-fence-*"))


def test_tombstone_fence_recovers_foreign_bytes_when_name_reappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    canonical = store.root / record.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")
    original_rename = os.rename
    original_link = os.link
    exchanged = reoccupied = False

    def rename(*args: object, **kwargs: object) -> None:
        nonlocal exchanged
        if args and args[0] == canonical.name and not exchanged:
            original_rename(canonical, held)
            canonical.write_bytes(b"foreign-canonical")
            exchanged = True
        original_rename(*args, **kwargs)

    def link(*args: object, **kwargs: object) -> None:
        nonlocal reoccupied
        if exchanged and args and args[0] == canonical.name and not reoccupied:
            canonical.write_bytes(b"third-canonical")
            reoccupied = True
        original_link(*args, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.rename", rename)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.link", link)
    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert exchanged and reoccupied
    assert canonical.read_bytes() == b"third-canonical"
    assert held.read_bytes() == b"derived-webp"
    assert not list(canonical.parent.glob(".unlink-fence-*"))
    recovered = list(canonical.parent.glob(".unlink-recovery-*"))
    assert len(recovered) == 1
    assert recovered[0].read_bytes() == b"foreign-canonical"


def test_publish_rechecks_bytes_after_staged_source_path_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    stage_path = store.root / ".tmp" / staged.temp_name
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    original_rename = os.rename

    def mutate_then_rename(*args: object, **kwargs: object) -> None:
        if args and args[0] == staged.temp_name:
            stage_path.write_bytes(b"altered-webp")
        original_rename(*args, **kwargs)

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.rename", mutate_then_rename
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert not canonical.exists()


def test_created_cache_directory_fsync_failure_prevents_child_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path / "data")
    original_mkdir = os.mkdir
    original_fsync = os.fsync
    cache_directory_created = False

    def mkdir(path: object, *args: object, **kwargs: object) -> None:
        nonlocal cache_directory_created
        original_mkdir(path, *args, **kwargs)
        if path == "source-visual-cache":
            cache_directory_created = True

    def fsync(descriptor: int) -> None:
        if cache_directory_created:
            raise OSError("parent directory sync failed")
        original_fsync(descriptor)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.mkdir", mkdir)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", fsync)
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "ASSET_IO_FAILED"
    assert not (store.root / "x").exists()
    assert not store.root.exists()


@pytest.mark.parametrize("nested", [False, True])
def test_store_rejects_symlinked_data_folder_ancestors(
    tmp_path: Path, nested: bool
):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    data_folder = alias / "nested-data" if nested else alias
    store = SourceVisualStore(data_folder=data_folder)

    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "CACHE_ROOT_SYMLINK"
    assert not (target / "nested-data" / "source-visual-cache").exists()
    assert not (target / "source-visual-cache").exists()


def test_stage_failure_preserves_a_foreign_temp_path_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    held: Path | None = None

    def exchange_then_fail(_fd: int, _payload: object) -> int:
        nonlocal held
        temp_path = next((store.root / ".tmp").glob("stage-*.tmp"))
        held = temp_path.with_suffix(".held")
        temp_path.rename(held)
        temp_path.write_bytes(b"foreign-temp")
        raise OSError("write failed")

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.write", exchange_then_fail
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "ASSET_IO_FAILED"
    assert held is not None and held.exists()
    assert next((store.root / ".tmp").glob("stage-*.tmp")).read_bytes() == b"foreign-temp"


@pytest.mark.asyncio
async def test_reconciliation_removes_only_old_owned_staged_files(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    old = store.stage("source:one", "a" * 64, _prepared(b"old-stage"))
    recent = store.stage("source:two", "b" * 64, _prepared(b"recent-stage"))
    old_path = store.root / ".tmp" / old.temp_name
    recent_path = store.root / ".tmp" / recent.temp_name
    now = time.time()
    os.utime(old_path, (now - 601, now - 601))
    cleanup = SourceVisualCleanup(store, _Repository([]))

    assert await cleanup.reconcile_tombstones(limit=100) == 0
    assert not old_path.exists()
    assert recent_path.exists()
    assert store.cache_size_bytes() == recent.byte_size


def test_staged_reconciliation_rejects_exact_owned_symlinks_and_keeps_malformed(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    temp_dir = store.root / ".tmp"
    (temp_dir / staged.temp_name).unlink()
    malformed = temp_dir / "stage-not-owned.tmp"
    malformed.write_bytes(b"malformed")
    outside = tmp_path / "outside-stage"
    outside.write_bytes(b"outside")
    exact_name = f"stage-{'a' * 64}-{'b' * 64}.tmp"
    (temp_dir / exact_name).symlink_to(outside)

    with pytest.raises(SourceVisualStorageError) as error:
        store.reconcile_staged_files(limit=100, now=time.time() + 601)

    assert error.value.code == "TEMP_INVALID"
    assert malformed.read_bytes() == b"malformed"
    assert (temp_dir / exact_name).is_symlink()


def test_cache_size_counts_owned_stage_tombstone_and_quarantine_inodes_once(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store, b"persistent-asset")
    record = _record(stored)
    tombstone = store.tombstone(record)
    assert tombstone is not None
    canonical = store.root / record.asset_relpath
    tombstone_path = canonical.with_name(tombstone.tombstone_name)
    os.link(tombstone_path, canonical)
    quarantine = canonical.with_name(
        f".expired-{'c' * 16}-{record.asset_sha256}.webp"
    )
    os.link(tombstone_path, quarantine)
    staged = store.stage("source:two", "b" * 64, _prepared(b"staged-bytes"))

    assert store.cache_size_bytes() == stored.byte_size + staged.byte_size


def test_publish_revalidates_final_canonical_path_after_final_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    staged = store.stage("source:one", "a" * 64, _prepared())
    canonical = store.root / asset_relpath(
        "source:one", "a" * 64, staged.asset_sha256
    )
    held = canonical.with_name(f"{canonical.name}.held")
    storage = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["_hash_fd"]
    )
    original_hash_fd = storage._hash_fd
    original_read = os.read
    hash_calls = 0
    exchanged = False

    def exchange_during_final_hash(fd: int, count: int) -> bytes:
        nonlocal exchanged
        if not exchanged:
            canonical.rename(held)
            canonical.write_bytes(b"foreign-canonical")
            exchanged = True
        return original_read(fd, count)

    def hash_fd(fd: int) -> tuple[str, int]:
        nonlocal hash_calls
        hash_calls += 1
        if hash_calls == 3:
            monkeypatch.setattr(
                "deeper_notebook.source_visuals.storage.os.read",
                exchange_during_final_hash,
            )
            try:
                return original_hash_fd(fd)
            finally:
                monkeypatch.setattr(
                    "deeper_notebook.source_visuals.storage.os.read", original_read
                )
        return original_hash_fd(fd)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage._hash_fd", hash_fd)
    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert hash_calls == 3
    assert exchanged
    assert canonical.read_bytes() == b"foreign-canonical"
    assert held.read_bytes() == b"derived-webp"


def test_fresh_store_reconciles_post_move_foreign_fence_and_counts_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    record = _record(stored)
    canonical = store.root / record.asset_relpath
    held = canonical.with_name(f"{canonical.name}.held")
    foreign = b"foreign-canonical"
    original_rename = os.rename
    original_fsync = os.fsync
    moved = False

    def exchange_then_rename(*args: object, **kwargs: object) -> None:
        nonlocal moved
        if args and args[0] == canonical.name and not moved:
            original_rename(canonical, held)
            canonical.write_bytes(foreign)
            moved = True
        original_rename(*args, **kwargs)

    def fail_after_move(descriptor: int) -> None:
        if moved:
            raise OSError("post-move sync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.rename", exchange_then_rename
    )
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.fsync", fail_after_move
    )
    with pytest.raises(SourceVisualStorageError) as error:
        store.tombstone(record)

    assert error.value.code == "ASSET_IO_FAILED"
    parent = canonical.parent
    assert canonical.read_bytes() == foreign
    assert list(parent.glob(".unlink-fence-*"))
    assert store.cache_size_bytes() == len(b"derived-webp") + len(foreign)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", original_fsync)
    recovered_store = SourceVisualStore(data_folder=tmp_path)
    assert recovered_store.reconcile_staged_files(limit=100) == 0
    assert canonical.read_bytes() == foreign
    assert held.read_bytes() == b"derived-webp"
    assert not list(parent.glob(".unlink-fence-*"))


def test_unverified_stage_is_counted_and_blocks_another_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = SourceVisualStore(data_folder=tmp_path)
    original_open = os.open
    original_fstat = os.fstat
    created_stage_fds: set[int] = set()

    def open_file(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if str(path).startswith(".unverified-stage-") and flags & os.O_EXCL:
            created_stage_fds.add(descriptor)
        return descriptor

    def fail_initial_stage_fstat(descriptor: int) -> os.stat_result:
        if descriptor in created_stage_fds:
            raise OSError("initial stage stat failed")
        return original_fstat(descriptor)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.open", open_file)
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.fstat", fail_initial_stage_fstat
    )
    with pytest.raises(SourceVisualStorageError) as first_error:
        store.stage("source:one", "a" * 64, _prepared())

    assert first_error.value.code == "TEMP_CREATE_FAILED"
    unverified = next((store.root / ".tmp").glob(".unverified-stage-*"))
    unverified.write_bytes(b"unverified")
    assert store.cache_size_bytes() == unverified.stat().st_size
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fstat", original_fstat)
    with pytest.raises(SourceVisualStorageError) as second_error:
        store.stage("source:two", "b" * 64, _prepared())

    assert second_error.value.code == "CACHE_RECOVERY_REQUIRED"
    assert len(list((store.root / ".tmp").glob(".unverified-stage-*"))) == 1


def test_recovery_entries_are_counted_and_cap_future_mutations(tmp_path: Path):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    parent = (store.root / stored.asset_relpath).parent
    payload = b"foreign-recovery"
    for index in range(8):
        (parent / f".unlink-recovery-{index:032x}").write_bytes(payload)

    assert store.cache_size_bytes() == stored.byte_size + 8 * len(payload)
    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:two", "b" * 64, _prepared())

    assert error.value.code == "CACHE_RECOVERY_REQUIRED"


@pytest.mark.asyncio
async def test_eviction_reports_recovery_bytes_without_deleting_foreign_data(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    parent = (store.root / stored.asset_relpath).parent
    recovery = parent / f".unlink-recovery-{'a' * 32}"
    recovery.write_bytes(b"foreign-recovery")
    cleanup = SourceVisualCleanup(store, _Repository([]))

    assert await cleanup.evict_to_budget(max_bytes=0) == 0
    assert store.cache_size_bytes() == stored.byte_size + recovery.stat().st_size
    assert recovery.read_bytes() == b"foreign-recovery"


def test_malformed_fence_journal_blocks_mutation_without_deleting_its_file(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    parent = (store.root / stored.asset_relpath).parent
    fence = parent / f".unlink-fence-{'b' * 32}"
    fence.mkdir(mode=0o700)
    moved = fence / Path(stored.asset_relpath).name
    moved.write_bytes(b"foreign-fence")
    (fence / ".journal").write_text("not-json", encoding="ascii")

    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:two", "b" * 64, _prepared())

    assert error.value.code == "CACHE_RECOVERY_REQUIRED"
    assert moved.read_bytes() == b"foreign-fence"


@pytest.mark.parametrize("location", ["temp", "content"])
def test_recovery_scan_rejects_unbounded_irrelevant_entries_before_mutation(
    tmp_path: Path, location: str
):
    store = SourceVisualStore(data_folder=tmp_path)
    if location == "temp":
        parent = store.root / ".tmp"
        root_fd = store._ensure_root()
        os.close(root_fd)
        parent.mkdir(exist_ok=True)
    else:
        stored = _publish(store)
        parent = (store.root / stored.asset_relpath).parent
    for index in range(4097):
        (parent / f"irrelevant-{index:04x}").write_bytes(b"x")

    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:two", "b" * 64, _prepared())

    assert error.value.code == "CACHE_SCAN_LIMIT"
    assert not list((store.root / ".tmp").glob("stage-*.tmp"))


@pytest.mark.parametrize("window", ["before-journal", "after-journal-removal"])
def test_fresh_store_retires_empty_fence_crash_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    parent = (store.root / stored.asset_relpath).parent
    fence = parent / f".unlink-fence-{'c' * 32}"
    fence.mkdir(mode=0o700)
    if window == "after-journal-removal":
        (fence / ".journal").write_text(
            '{"dev":1,"ino":1,"name":"placeholder","operation":"unlink"}',
            encoding="ascii",
        )
        (fence / ".journal").unlink()

    original_fsync = os.fsync
    parent_identity = (parent.stat().st_dev, parent.stat().st_ino)
    synced_parent = False

    def fsync(descriptor: int) -> None:
        nonlocal synced_parent
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) == parent_identity:
            synced_parent = True
        original_fsync(descriptor)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", fsync)
    fresh_store = SourceVisualStore(data_folder=tmp_path)
    staged = fresh_store.stage("source:two", "b" * 64, _prepared())

    assert staged.temp_name
    assert not fence.exists()
    assert synced_parent


def test_nonempty_fence_without_journal_blocks_recovery_without_deletion(
    tmp_path: Path,
):
    store = SourceVisualStore(data_folder=tmp_path)
    stored = _publish(store)
    parent = (store.root / stored.asset_relpath).parent
    fence = parent / f".unlink-fence-{'d' * 32}"
    fence.mkdir(mode=0o700)
    foreign = fence / "foreign"
    foreign.write_bytes(b"foreign-fence")

    with pytest.raises(SourceVisualStorageError) as error:
        SourceVisualStore(data_folder=tmp_path).stage(
            "source:two", "b" * 64, _prepared()
        )

    assert error.value.code == "CACHE_RECOVERY_REQUIRED"
    assert fence.exists()
    assert foreign.read_bytes() == b"foreign-fence"


def test_mutation_guard_is_reentrant_for_stage_in_the_same_thread(tmp_path: Path):
    context = mp.get_context("fork")
    completed = context.Event()
    child = context.Process(
        target=_stage_inside_mutation_guard,
        args=(str(tmp_path), completed),
    )
    child.start()
    try:
        assert completed.wait(timeout=3)
    finally:
        child.join(timeout=3)
        if child.is_alive():
            child.kill()
            child.join(timeout=3)
    assert child.exitcode == 0


def test_storage_fails_closed_before_mutation_when_locking_is_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    storage = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["fcntl"]
    )
    monkeypatch.setattr(storage, "fcntl", None)
    store = SourceVisualStore(data_folder=tmp_path)

    with pytest.raises(SourceVisualStorageError) as error:
        store.stage("source:one", "a" * 64, _prepared())

    assert error.value.code == "CACHE_LOCK_UNSUPPORTED"
    assert not store.root.exists()


def test_process_mutation_guard_registry_retires_unused_roots(tmp_path: Path):
    storage = __import__(
        "deeper_notebook.source_visuals.storage", fromlist=["_PROCESS_MUTATION_GUARDS"]
    )
    storage._PROCESS_MUTATION_GUARDS.clear()
    stores = [SourceVisualStore(data_folder=tmp_path / str(index)) for index in range(24)]
    for store in stores:
        with store.mutation_guard():
            pass

    del store
    del stores
    gc.collect()
    assert len(storage._PROCESS_MUTATION_GUARDS) == 0
