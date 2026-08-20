"""v0.7.126 — tests for the backup + restore tooling.

Round-trip tests on tmp_path-rooted fake data directories. No real
SurrealDB / no real LangGraph state — the backup tool is filesystem-
agnostic and only cares about (a) walking the directory + (b) writing
a deterministic tarball.

Covers:
  * Backup walks the data dir + produces a tar.gz + manifest
  * Round-trip: backup → restore reproduces the data dir byte-for-byte
  * Skip patterns: log files, __pycache__, .DS_Store excluded
  * Integrity: SHA-256 mismatch in the manifest is detected
  * Restore refuses to overwrite non-empty data dir without --force
  * verify-only mode doesn't write anything
  * Format version: future bundles are rejected with a clear error
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

import pytest

# Make the scripts/ dir importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import backup_restore as br  # noqa: E402


def test_data_root_env_prefers_canonical_and_accepts_legacy(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical"
    legacy = tmp_path / "legacy"
    canonical.mkdir()
    legacy.mkdir()

    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(canonical))
    monkeypatch.setenv("ONP_DATA_DIR", str(legacy))
    assert br._resolve_data_root() == canonical.resolve()

    monkeypatch.delenv("DEEPER_NOTEBOOK_DATA_DIR")
    assert br._resolve_data_root() == legacy.resolve()


def _make_fake_data_dir(root: Path) -> dict[str, bytes]:
    """Build a small data directory with the file types ONP actually
    creates. Returns {relpath: bytes} so tests can verify what was
    backed up + restored."""
    contents = {
        "sqlite-db/checkpoints.sqlite": b"SQLite format 3\x00fake-data" * 50,
        "sqlite-db/checkpoints.sqlite-wal": b"WAL\x00" * 100,
        "uploads/source-1.pdf": b"%PDF-1.4 fake pdf content " * 80,
        "uploads/source-2.docx": b"docx fake content " * 200,
        "tiktoken-cache/some_encoding": b"cached encoding " * 10,
        # These should be SKIPPED:
        "logs/api.log": b"log noise should not be backed up",
        "__pycache__/foo.pyc": b"pyc bytes",
        ".DS_Store": b"\x00\x00\x00\x00",
        "uploads/.lock": b"upload lock noise",
    }
    for rel, payload in contents.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return contents


def _rewrite_with_windows_manifest_paths(
    bundle: Path, output: Path, *, corrupt_member: str | None = None
) -> None:
    """Write a bundle whose manifest uses Windows path separators.

    Python's tar implementation stores portable slash-separated member names,
    while older Windows backups recorded ``Path`` strings in the manifest.
    This fixture reproduces that cross-platform shape on every test runner.
    """
    with tarfile.open(bundle, "r:gz") as src_tar:
        with tarfile.open(output, "w:gz") as dst_tar:
            for member in src_tar.getmembers():
                if member.name == "manifest.json":
                    manifest = json.loads(src_tar.extractfile(member).read())
                    for entry in manifest["files"]:
                        entry["path"] = entry["path"].replace("/", chr(92))
                    blob = json.dumps(manifest).encode()
                    info = tarfile.TarInfo(name="manifest.json")
                    info.size = len(blob)
                    info.mtime = member.mtime
                    dst_tar.addfile(info, fileobj=br._BytesIO(blob))
                elif member.name == corrupt_member:
                    fake = b"X" * member.size
                    info = tarfile.TarInfo(name=member.name)
                    info.size = len(fake)
                    info.mtime = member.mtime
                    dst_tar.addfile(info, fileobj=br._BytesIO(fake))
                else:
                    src_file = src_tar.extractfile(member)
                    if src_file is None:
                        dst_tar.addfile(member)
                    else:
                        dst_tar.addfile(member, fileobj=src_file)


def test_backup_creates_tarball_with_manifest(tmp_path):
    """v0.7.126 — backup() produces a gzipped tar with a manifest.json
    listing every backed-up file + its SHA-256."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _make_fake_data_dir(data_root)

    out = tmp_path / "test.tar.gz"
    result = br.backup(out, data_root=data_root)

    assert out.exists()
    assert result["file_count"] > 0
    assert result["total_bytes"] > 0
    assert result["compressed_bytes"] > 0
    assert result["elapsed_seconds"] >= 0

    # Inspect the archive
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        # The 4 NON-skipped files should be present, prefixed with data/
        assert "data/sqlite-db/checkpoints.sqlite" in names
        assert "data/uploads/source-1.pdf" in names
        assert "data/uploads/source-2.docx" in names
        # Skipped files should NOT be present
        assert "data/logs/api.log" not in names
        assert "data/__pycache__/foo.pyc" not in names
        assert "data/.DS_Store" not in names
        assert "data/uploads/.lock" not in names

        # Verify the manifest is internally consistent
        mf = json.loads(tar.extractfile("manifest.json").read())
        assert mf["format_version"] == br.BUNDLE_FORMAT_VERSION
        assert mf["file_count"] == result["file_count"]
        # Each entry has sha256, bytes, mtime
        for entry in mf["files"]:
            assert "path" in entry
            assert "bytes" in entry
            assert "sha256" in entry
            assert "mtime" in entry
            assert len(entry["sha256"]) == 64


def test_backup_restore_round_trip(tmp_path):
    """v0.7.126 — Restore the bundle into a fresh dir and verify
    every file matches byte-for-byte."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    original = _make_fake_data_dir(src_root)

    bundle = tmp_path / "bundle.tar.gz"
    br.backup(bundle, data_root=src_root)

    # Restore into a fresh location (different parent dir)
    restore_root = tmp_path / "restored" / "data"
    restore_root.parent.mkdir(parents=True)
    result = br.restore(bundle, data_root=restore_root)

    assert result["integrity_ok"] is True
    assert result["verified_files"] > 0

    # Spot-check that each NON-skipped file came back with identical bytes
    expected_paths = {
        rel: payload
        for rel, payload in original.items()
        if not any(
            skip in rel for skip in ("logs/", "__pycache__", ".DS_Store", ".lock")
        )
    }
    for rel, payload in expected_paths.items():
        restored = restore_root / rel
        assert restored.exists(), f"{rel} missing after restore"
        assert restored.read_bytes() == payload, f"{rel} content mismatch"


def test_backup_replaces_existing_bundle_when_windows_blocks_rename(
    tmp_path, monkeypatch
):
    """A repeated backup replaces its prior bundle even when the filesystem
    forbids rename-overwrite, as Windows does."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "bundle.tar.gz"
    br.backup(bundle, data_root=src_root)

    original_rename = Path.rename

    def windows_rename(self, target):
        if self.suffix == ".tmp" and Path(target).exists():
            raise FileExistsError("Windows rename cannot replace a file")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", windows_rename)
    br.backup(bundle, data_root=src_root)

    assert bundle.exists()


def test_restore_refuses_non_empty_data_dir(tmp_path):
    """v0.7.126 — Restore refuses to overwrite an existing data dir
    unless --force. Prevents accidental destruction."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    # Create a non-empty target
    target = tmp_path / "target" / "data"
    target.mkdir(parents=True)
    (target / "existing-file.txt").write_bytes(b"important")

    with pytest.raises(RuntimeError) as exc_info:
        br.restore(bundle, data_root=target)
    assert "non-empty" in str(exc_info.value).lower()
    assert "force" in str(exc_info.value).lower()
    # Existing file is untouched
    assert (target / "existing-file.txt").read_bytes() == b"important"


def test_restore_force_allows_overwrite(tmp_path):
    """v0.7.126 — With force=True, restore writes into a non-empty
    target. Existing files in the target are NOT auto-deleted
    (extractall doesn't clear; user is expected to wipe first if
    they want clean state)."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    target = tmp_path / "t" / "data"
    target.mkdir(parents=True)
    (target / "marker.txt").write_bytes(b"x")

    br.restore(bundle, data_root=target, force=True)
    # Backed-up files are present
    assert (target / "sqlite-db/checkpoints.sqlite").exists()
    # The pre-existing marker file is still there (extractall doesn't
    # remove unrelated files — that's the user's responsibility)
    assert (target / "marker.txt").exists()


def test_verify_only_does_not_write(tmp_path):
    """v0.7.126 — verify_only=True checks integrity but writes nothing.
    Useful before a real restore to confirm the bundle is intact."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    target = tmp_path / "verify-target"
    result = br.restore(bundle, data_root=target, verify_only=True)
    assert result["integrity_ok"] is True
    # target was never created
    assert not target.exists()


def test_verify_accepts_windows_style_manifest_paths(tmp_path):
    """Verification matches portable tar members to Windows manifest paths."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    windows_bundle = tmp_path / "windows-paths.tar.gz"
    _rewrite_with_windows_manifest_paths(bundle, windows_bundle)

    result = br.restore(
        windows_bundle,
        data_root=tmp_path / "target",
        verify_only=True,
    )

    assert result["integrity_ok"] is True
    assert result["verified_files"] == result["total_files"]


def test_verify_detects_corrupted_bundle(tmp_path):
    """v0.7.126 — A bundle where the content doesn't match the
    manifest's SHA-256 must fail integrity check, NOT silently
    extract corrupt data."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    # Model a Windows-created manifest while keeping portable tar member
    # names, then tamper one member without updating its original hash.
    tampered = tmp_path / "tampered.tar.gz"
    _rewrite_with_windows_manifest_paths(
        bundle,
        tampered,
        corrupt_member="data/uploads/source-1.pdf",
    )

    with pytest.raises(RuntimeError) as exc_info:
        br.restore(tampered, data_root=tmp_path / "target", verify_only=True)
    assert "integrity" in str(exc_info.value).lower()
    assert "corrupt" in str(exc_info.value).lower()


def test_restore_rejects_future_bundle_version(tmp_path):
    """v0.7.126 — Bundles from a future format version are refused
    with a clear error. Operators with mismatched tools see a
    helpful message, not a confusing extraction error."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    _make_fake_data_dir(src_root)
    bundle = tmp_path / "b.tar.gz"
    br.backup(bundle, data_root=src_root)

    # Manually rewrite the manifest with a future version
    future_bundle = tmp_path / "future.tar.gz"
    with tarfile.open(bundle, "r:gz") as src_tar:
        with tarfile.open(future_bundle, "w:gz") as dst_tar:
            for member in src_tar.getmembers():
                if member.name == "manifest.json":
                    mf = json.loads(src_tar.extractfile(member).read())
                    mf["format_version"] = "999"
                    blob = json.dumps(mf).encode()
                    info = tarfile.TarInfo(name="manifest.json")
                    info.size = len(blob)
                    info.mtime = member.mtime
                    dst_tar.addfile(info, fileobj=br._BytesIO(blob))
                else:
                    f = src_tar.extractfile(member)
                    if f is None:
                        dst_tar.addfile(member)
                    else:
                        dst_tar.addfile(member, fileobj=f)

    with pytest.raises(RuntimeError) as exc_info:
        br.restore(future_bundle, data_root=tmp_path / "x", verify_only=True)
    assert "format version" in str(exc_info.value).lower()
    assert "999" in str(exc_info.value)


def test_backup_raises_on_empty_data_dir(tmp_path):
    """v0.7.126 — Backing up an empty data dir is almost certainly a
    misconfiguration (wrong DEEPER_NOTEBOOK_DATA_DIR). Raise with an actionable
    error message."""
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(RuntimeError) as exc_info:
        br.backup(tmp_path / "out.tar.gz", data_root=empty)
    assert "no files" in str(exc_info.value).lower()
    assert "DEEPER_NOTEBOOK_DATA_DIR" in str(exc_info.value)


def test_backup_raises_on_missing_data_dir(tmp_path):
    """v0.7.126 — Pointing at a non-existent dir errors with
    actionable text mentioning DEEPER_NOTEBOOK_DATA_DIR."""
    with pytest.raises(RuntimeError) as exc_info:
        br.backup(tmp_path / "out.tar.gz", data_root=tmp_path / "does-not-exist")
    assert "not found" in str(exc_info.value).lower()
    assert "DEEPER_NOTEBOOK_DATA_DIR" in str(exc_info.value)
