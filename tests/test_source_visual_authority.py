from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from deeper_notebook.source_visuals import authority as authority_module
from deeper_notebook.source_visuals.authority import (
    SourceVisualAuthorityError,
    canonical_fingerprint_payload,
    compute_source_visual_authority,
    fingerprint_payload,
)


def _source(
    *,
    source_file_path: Path | None = None,
    upload_root: Path | None = None,
    **overrides: object,
) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "source:one",
        "source_id": "source:one",
        "source_type": "upload",
        "normalized_source_type": "upload",
        "asset_url": None,
        "source_file_sha256": None,
        "full_text_sha256": "b" * 64,
        "extractor_version": "source-visual-v1",
        "source_file_path": source_file_path,
        "upload_root": upload_root,
        "updated": datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        "source_updated_at": datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        "asset": SimpleNamespace(file_path=source_file_path, url=None),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_canonical_fingerprint_is_stable_and_versioned():
    left = canonical_fingerprint_payload(
        source_id="source:one",
        normalized_source_type="upload",
        asset_url=None,
        source_file_sha256="a" * 64,
        full_text_sha256="b" * 64,
        extractor_version="source-visual-v1",
    )
    right = canonical_fingerprint_payload(
        full_text_sha256="b" * 64,
        source_file_sha256="a" * 64,
        asset_url=None,
        normalized_source_type="upload",
        source_id="source:one",
        extractor_version="source-visual-v1",
    )
    assert left == right
    assert left == {
        "schema_version": 1,
        "source_id": "source:one",
        "source_type": "upload",
        "asset_url": None,
        "source_file_sha256": "a" * 64,
        "full_text_sha256": "b" * 64,
        "extractor_version": "source-visual-v1",
    }
    assert fingerprint_payload(left) == fingerprint_payload(right)


@pytest.mark.asyncio
async def test_full_text_change_changes_authority_fingerprint():
    first = await compute_source_visual_authority(_source())
    second = await compute_source_visual_authority(_source(full_text_sha256="c" * 64))
    assert first.content_sha256 != second.content_sha256


@pytest.mark.asyncio
async def test_source_revision_change_is_retained_in_authority():
    first = await compute_source_visual_authority(_source())
    second = await compute_source_visual_authority(
        _source(
            updated=datetime(2026, 8, 14, 12, 1, tzinfo=timezone.utc),
            source_updated_at=datetime(2026, 8, 14, 12, 1, tzinfo=timezone.utc),
        )
    )
    assert first.source_updated_at != second.source_updated_at


@pytest.mark.asyncio
async def test_file_byte_change_changes_authority_fingerprint(tmp_path: Path):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"before")
    first = await compute_source_visual_authority(
        _source(source_file_path=path, upload_root=tmp_path)
    )
    path.write_bytes(b"after")
    second = await compute_source_visual_authority(
        _source(source_file_path=path, upload_root=tmp_path)
    )
    assert first.source_file_sha256 == hashlib.sha256(b"before").hexdigest()
    assert second.source_file_sha256 == hashlib.sha256(b"after").hexdigest()
    assert first.content_sha256 != second.content_sha256


@pytest.mark.asyncio
async def test_file_changing_during_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "asset.bin"
    path.write_bytes(b"asset")
    original_fstat = __import__(
        "deeper_notebook.source_visuals.authority", fromlist=["os"]
    ).os.fstat
    calls = 0

    def changing_fstat(fd: int):
        nonlocal calls
        calls += 1
        result = original_fstat(fd)
        if calls == 2:
            return SimpleNamespace(st_mode=result.st_mode, st_size=result.st_size + 1)
        return result

    monkeypatch.setattr(
        "deeper_notebook.source_visuals.authority.os.fstat", changing_fstat
    )
    with pytest.raises(SourceVisualAuthorityError) as error:
        await compute_source_visual_authority(
            _source(source_file_path=path, upload_root=tmp_path)
        )
    assert error.value.code == "SOURCE_FILE_CHANGED"


@pytest.mark.parametrize(
    "kind", ["symlink", "non_regular", "sibling_prefix", "outside_root"]
)
@pytest.mark.asyncio
async def test_upload_file_root_validation_is_fail_closed(tmp_path: Path, kind: str):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    regular = upload_root / "asset.bin"
    regular.write_bytes(b"asset")
    if kind == "symlink":
        path = upload_root / "link.bin"
        path.symlink_to(regular)
    elif kind == "non_regular":
        path = upload_root / "pipe"
        path.mkdir()
    elif kind == "sibling_prefix":
        sibling = tmp_path / "uploads-other"
        sibling.mkdir()
        path = sibling / "asset.bin"
        path.write_bytes(b"asset")
    else:
        path = tmp_path / "asset.bin"
        path.write_bytes(b"asset")
    with pytest.raises(SourceVisualAuthorityError) as error:
        await compute_source_visual_authority(
            _source(source_file_path=path, upload_root=upload_root)
        )
    assert error.value.code in {
        "SOURCE_FILE_SYMLINK",
        "SOURCE_FILE_NOT_REGULAR",
        "SOURCE_FILE_OUTSIDE_ROOT",
    }
    assert str(path) not in str(error.value)


@pytest.mark.asyncio
async def test_intermediate_symlink_component_is_rejected(tmp_path: Path):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    real_directory = upload_root / "real"
    real_directory.mkdir()
    (real_directory / "asset.bin").write_bytes(b"asset")
    linked_directory = upload_root / "linked"
    linked_directory.symlink_to(real_directory, target_is_directory=True)

    with pytest.raises(SourceVisualAuthorityError) as error:
        await compute_source_visual_authority(
            _source(
                source_file_path=linked_directory / "asset.bin",
                upload_root=upload_root,
            )
        )
    assert error.value.code == "SOURCE_FILE_SYMLINK"


@pytest.mark.asyncio
async def test_file_open_is_descriptor_bound_to_the_upload_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    nested = upload_root / "nested"
    nested.mkdir()
    path = nested / "asset.bin"
    path.write_bytes(b"asset")
    original_open = authority_module.os.open
    calls: list[tuple[object, int, int | None]] = []

    def tracking_open(
        path_value: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        calls.append((path_value, flags, dir_fd))
        if dir_fd is None:
            return original_open(path_value, flags, mode)
        return original_open(path_value, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(authority_module.os, "open", tracking_open)
    await compute_source_visual_authority(
        _source(source_file_path=path, upload_root=upload_root)
    )

    assert calls
    assert any(dir_fd is not None for _, _, dir_fd in calls)
    assert all(os_path != str(path) for os_path, _, _ in calls)
