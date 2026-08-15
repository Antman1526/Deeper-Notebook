from __future__ import annotations

import asyncio
import hashlib
import os
import threading
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
    original_replace = os.replace

    def fsync(fd: int) -> None:
        events.append("fsync")
        original_fsync(fd)

    def replace(*args: object, **kwargs: object) -> None:
        events.append("replace")
        original_replace(*args, **kwargs)

    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.fsync", fsync)
    monkeypatch.setattr("deeper_notebook.source_visuals.storage.os.replace", replace)
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

    assert events.index("fsync") < events.index("replace") < len(events) - 1
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
    original_replace = os.replace
    exchanged = False

    def exchange_then_replace(*args: object, **kwargs: object) -> None:
        nonlocal exchanged
        if not exchanged and args and args[0] == staged.temp_name:
            temp_path = store.root / ".tmp" / staged.temp_name
            verified_path = temp_path.with_suffix(".verified")
            temp_path.rename(verified_path)
            temp_path.write_bytes(b"unverified-replacement")
            exchanged = True
        original_replace(*args, **kwargs)

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.storage.os.replace", exchange_then_replace
    )

    with pytest.raises(SourceVisualStorageError) as error:
        store.publish(staged)

    assert error.value.code == "ASSET_HASH_MISMATCH"
    assert not (store.root / asset_relpath("source:one", "a" * 64, staged.asset_sha256)).exists()


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
