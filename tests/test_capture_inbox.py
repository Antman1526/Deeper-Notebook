"""Proof for the local-only Capture Inbox filesystem boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from deeper_notebook.capture.contracts import CaptureInboxItem
from deeper_notebook.capture.watcher import CaptureInboxWatcher


@dataclass
class InMemoryCaptureRepository:
    """Small durable-store substitute; tests never need a live database."""

    items: list[CaptureInboxItem]
    fingerprints: set[tuple[str, int]]

    def __init__(self) -> None:
        self.items = []
        self.fingerprints = set()

    async def has_fingerprint(self, sha256: str, byte_size: int) -> bool:
        return (sha256, byte_size) in self.fingerprints

    async def record_fingerprint(self, sha256: str, byte_size: int) -> None:
        self.fingerprints.add((sha256, byte_size))

    async def save_item(self, item: CaptureInboxItem) -> CaptureInboxItem:
        self.items.append(item)
        return item


@pytest.mark.asyncio
async def test_file_requires_two_stable_scans_before_becoming_ready(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inbox"
    root.mkdir()
    source = root / "meeting-notes.md"
    source.write_text("Private notes", encoding="utf-8")
    repository = InMemoryCaptureRepository()
    watcher = CaptureInboxWatcher(
        approved_roots=[root], repository=repository, stable_after_seconds=2
    )

    first = await watcher.scan_root(root, now_monotonic=100.0)
    second = await watcher.scan_root(root, now_monotonic=101.0)
    ready = await watcher.scan_root(root, now_monotonic=102.0)

    assert [item.state for item in first] == ["pending"]
    assert [item.state for item in second] == ["pending"]
    assert [item.state for item in ready] == ["ready"]
    assert repository.fingerprints == {(ready[0].sha256, len(b"Private notes"))}


@pytest.mark.asyncio
async def test_seen_fingerprint_marks_a_renamed_file_as_duplicate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inbox"
    root.mkdir()
    source = root / "first.txt"
    source.write_text("same content", encoding="utf-8")
    repository = InMemoryCaptureRepository()
    watcher = CaptureInboxWatcher(
        approved_roots=[root], repository=repository, stable_after_seconds=2
    )
    await watcher.scan_root(root, now_monotonic=1.0)
    await watcher.scan_root(root, now_monotonic=3.0)

    source.rename(root / "renamed.txt")
    restarted_watcher = CaptureInboxWatcher(
        approved_roots=[root], repository=repository, stable_after_seconds=2
    )
    await restarted_watcher.scan_root(root, now_monotonic=10.0)
    items = await restarted_watcher.scan_root(root, now_monotonic=12.0)

    assert [item.state for item in items] == ["duplicate"]


@pytest.mark.asyncio
async def test_hidden_temp_unsupported_and_escaping_symlink_never_import(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inbox"
    root.mkdir()
    (root / ".hidden.md").write_text("hidden", encoding="utf-8")
    (root / "upload.part").write_text("temporary", encoding="utf-8")
    (root / "program.exe").write_bytes(b"no")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("The current filesystem does not permit symlink creation")

    repository = InMemoryCaptureRepository()
    watcher = CaptureInboxWatcher(approved_roots=[root], repository=repository)
    items = await watcher.scan_root(root, now_monotonic=1.0)

    assert {item.state for item in items} == {"ignored"}
    assert {item.reason for item in items} == {
        "hidden_or_temporary",
        "unsupported_type",
        "symlink_escape",
    }
    assert repository.fingerprints == set()


@pytest.mark.asyncio
async def test_unapproved_root_is_rejected_before_any_filesystem_read(
    tmp_path: Path,
) -> None:
    approved = tmp_path / "approved"
    unapproved = tmp_path / "unapproved"
    approved.mkdir()
    unapproved.mkdir()
    (unapproved / "note.md").write_text("not allowed", encoding="utf-8")
    watcher = CaptureInboxWatcher(
        approved_roots=[approved], repository=InMemoryCaptureRepository()
    )

    with pytest.raises(ValueError, match="not an approved capture root"):
        await watcher.scan_root(unapproved)
