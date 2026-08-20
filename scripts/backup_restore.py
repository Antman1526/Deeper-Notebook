#!/usr/bin/env python3
"""Deeper Notebook v0.7.126 — Backup + restore for the Deeper Notebook data
directory.

Operators (and end users running the desktop bundle) need a way to:
  1. Snapshot the database + uploaded files + LangGraph checkpoints
     before risky operations (upgrades, schema migrations, dep bumps)
  2. Restore a snapshot if something goes wrong
  3. Move an install between machines

Without this script, the only recourse was a manual `tar czf` against
a directory structure most users don't know about. v0.7.126 makes
it `make backup` and `make restore PATH=…`.

What gets backed up:
  * SurrealDB data directory (~/.deeper-notebook/db/  OR
    ./data/surreal/ in dev mode)
  * Uploaded source files (UPLOADS_FOLDER)
  * LangGraph SQLite checkpoints (LANGGRAPH_CHECKPOINT_FILE + sidecars)
  * tiktoken cache (small, but worth bundling)

What is NOT backed up:
  * Environment variables (.env) — user's responsibility, may contain
    secrets that don't belong in a shared tarball
  * Locally-bundled .gguf model weights — multi-GB, re-downloadable
  * Log files — recreated on each run
  * uvenv / pyc caches — recreatable

Output: gzipped tar at the user-specified path. Includes a
manifest.json with the bundle version, timestamp, and SHA-256 of
each archived file for integrity verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Bundle format version. Bump if the layout ever changes; the restore
# command refuses to extract bundles from a future version.
BUNDLE_FORMAT_VERSION = "1"

# Hard limits to keep an accidental backup from spiraling.
_MAX_BUNDLE_BYTES = 50 * 1024 * 1024 * 1024  # 50 GB
_HUGE_FILE_THRESHOLD_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB — warn but include


def _human_size(b: int) -> str:
    """Format byte count for log output."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or unit == "TB":
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _resolve_data_root() -> Path:
    """Resolve the root path of the install's data directory.

    Honors:
      * DEEPER_NOTEBOOK_DATA_DIR (canonical), then DN_DATA_DIR
      * OPEN_NOTEBOOK_DATA_DIR or ONP_DATA_DIR (deprecated compatibility)
      * Falls back to ./data/ for dev runs

    Both paths are validated to exist before we proceed.
    """
    raw = next(
        (
            os.environ[name].strip()
            for name in (
                "DEEPER_NOTEBOOK_DATA_DIR",
                "DN_DATA_DIR",
                "OPEN_NOTEBOOK_DATA_DIR",
                "ONP_DATA_DIR",
            )
            if os.environ.get(name, "").strip()
        ),
        "",
    )
    if raw:
        return Path(raw).expanduser().resolve()
    # Dev fallback: project-relative ./data/
    cwd = Path.cwd()
    return (cwd / "data").resolve()


def _hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of file contents, streamed in 1 MB chunks (so we don't
    OOM on multi-GB uploads)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _collect_paths(data_root: Path) -> list[tuple[Path, str]]:
    """Walk the data root and collect (absolute_path, archive_path)
    pairs for every file to back up. archive_path is rooted at
    `data/...` so extracting on a different machine drops the bundle
    into the right place.

    Skips:
      * log files (recreated each run)
      * .DS_Store / Thumbs.db (OS noise)
      * temp uvicorn .lock files
    """
    pairs: list[tuple[Path, str]] = []
    if not data_root.exists():
        return pairs

    skip_names = {".DS_Store", "Thumbs.db", "desktop.ini", ".lock"}
    skip_suffixes = {".log", ".lock", ".pyc"}
    skip_dir_names = {"__pycache__", ".pytest_cache", "logs"}

    for p in sorted(data_root.rglob("*")):
        if not p.is_file():
            continue
        if p.name in skip_names:
            continue
        # Handles both `.lock` (no stem) AND `foo.log` (named suffix)
        if p.suffix in skip_suffixes or p.name.startswith("."):
            # Files starting with a dot AT TOP LEVEL of an upload dir
            # are usually lock/temp markers (uvicorn .lock, vim
            # swap, etc.). User-uploaded files starting with `.`
            # are vanishingly rare in our context, and even if
            # they exist, omitting them from backup is reasonable.
            if p.suffix in skip_suffixes or p.stem == "":
                continue
        if any(part in skip_dir_names for part in p.parts):
            continue
        # Relative path under data_root so the archive is portable
        rel = p.relative_to(data_root)
        pairs.append((p, f"data/{rel.as_posix()}"))
    return pairs


def backup(output_path: Path, *, data_root: Path | None = None) -> dict:
    """Build a gzipped tar bundle at `output_path`. Returns a result
    dict with file_count, total_bytes, elapsed_seconds, manifest_sha."""
    root = data_root or _resolve_data_root()
    if not root.exists():
        raise RuntimeError(
            f"Data directory not found: {root}. Is the API running and "
            "have you ever started it? Set DEEPER_NOTEBOOK_DATA_DIR if your install "
            "uses a non-default path."
        )

    start = time.monotonic()
    pairs = _collect_paths(root)
    if not pairs:
        raise RuntimeError(
            f"Data directory at {root} contains no files to back up. "
            "Either the install is empty, or the wrong "
            "DEEPER_NOTEBOOK_DATA_DIR is set."
        )

    # Pre-flight: total size check + huge-file warnings
    total_bytes = 0
    huge_files: list[str] = []
    for abs_p, arc_p in pairs:
        sz = abs_p.stat().st_size
        total_bytes += sz
        if sz > _HUGE_FILE_THRESHOLD_BYTES:
            huge_files.append(f"  {arc_p} ({_human_size(sz)})")

    if total_bytes > _MAX_BUNDLE_BYTES:
        raise RuntimeError(
            f"Data directory total is {_human_size(total_bytes)}; bundle "
            f"would exceed the {_human_size(_MAX_BUNDLE_BYTES)} safety cap. "
            "Likely a misconfigured DEEPER_NOTEBOOK_DATA_DIR pointing at a directory "
            "outside the install, or unprocessed uploads bloating things."
        )

    if huge_files:
        print(
            f"⚠️  {len(huge_files)} file(s) over 1 GB will be archived:",
            file=sys.stderr,
        )
        for line in huge_files:
            print(line, file=sys.stderr)

    # Compute SHA-256 manifest as we go so the restore step can
    # verify integrity. Doing this BEFORE the tar write so we can
    # embed the manifest into the archive.
    file_entries: list[dict] = []
    for abs_p, arc_p in pairs:
        st = abs_p.stat()
        file_entries.append(
            {
                "path": arc_p,
                "bytes": st.st_size,
                "sha256": _hash_file(abs_p),
                "mtime": st.st_mtime,
            }
        )

    manifest = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(root),
        "file_count": len(file_entries),
        "total_bytes": total_bytes,
        "files": file_entries,
    }
    manifest_blob = json.dumps(manifest, indent=2).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_blob).hexdigest()

    # Write to a sibling temp file first, then rename — so a crash
    # mid-archive doesn't leave a half-written bundle at the target path.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with tarfile.open(tmp_path, "w:gz") as tar:
            # manifest.json FIRST so a streaming restore can read it
            # before allocating disk for the rest.
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_blob)
            info.mtime = int(time.time())
            tar.addfile(info, fileobj=_BytesIO(manifest_blob))

            for abs_p, arc_p in pairs:
                tar.add(abs_p, arcname=arc_p)
        # os.replace atomically overwrites a prior bundle on both POSIX and
        # Windows. Path.rename cannot replace an existing destination there.
        os.replace(tmp_path, output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    elapsed = time.monotonic() - start
    return {
        "output_path": str(output_path),
        "file_count": len(pairs),
        "total_bytes": total_bytes,
        "compressed_bytes": output_path.stat().st_size,
        "elapsed_seconds": round(elapsed, 2),
        "manifest_sha256": manifest_sha,
    }


def _BytesIO(b: bytes):
    """Local import shim so this file has no top-level io import (keeps
    the module load cheap when only the CLI argparser fires)."""
    import io

    return io.BytesIO(b)


def restore(
    bundle_path: Path,
    *,
    data_root: Path | None = None,
    force: bool = False,
    verify_only: bool = False,
) -> dict:
    """Extract a bundle to `data_root`. By default REFUSES to extract
    over a non-empty data_root unless `force=True`.

    Args:
        bundle_path: Path to the gzipped tar produced by backup().
        data_root: Where to extract. Defaults to the same resolution
            as backup() (DEEPER_NOTEBOOK_DATA_DIR, a deprecated alias, or ./data).
        force: Allow overwriting an existing data_root.
        verify_only: Read the manifest + compare SHA-256s but DON'T
            actually write anything. Useful for "is my backup intact?"
            preflights before relying on it.

    Returns dict with: file_count, total_bytes, manifest, verification.
    """
    root = data_root or _resolve_data_root()
    if not bundle_path.exists():
        raise RuntimeError(f"Bundle not found: {bundle_path}")

    # Open the tar + read manifest first
    with tarfile.open(bundle_path, "r:gz") as tar:
        # The manifest is always the first member (per backup() above)
        try:
            mf_member = tar.getmember("manifest.json")
        except KeyError:
            raise RuntimeError(
                f"Bundle {bundle_path} has no manifest.json — "
                "either it's not an ONP backup, or the bundle is corrupted."
            )

        manifest = json.loads(tar.extractfile(mf_member).read())
        bundle_version = manifest.get("format_version", "unknown")
        if bundle_version != BUNDLE_FORMAT_VERSION:
            raise RuntimeError(
                f"Bundle format version {bundle_version!r} is incompatible "
                f"with this restore tool (expects {BUNDLE_FORMAT_VERSION!r}). "
                "Either downgrade the tool to match the bundle or "
                "re-create the bundle with a newer backup tool."
            )

        # Pre-flight: refuse to overwrite non-empty data_root
        if root.exists() and any(root.iterdir()) and not force and not verify_only:
            raise RuntimeError(
                f"Refusing to restore over non-empty data dir {root}. "
                "Either remove the directory first (DANGER — destroys "
                "existing data) or pass --force."
            )

        # Verify integrity by hash. For verify_only mode we read each
        # archived file out of the tar and SHA-256 the bytes without
        # writing to disk.
        # Tar member names are portable POSIX paths, but older backups made
        # on Windows recorded Path strings with backslashes in the manifest.
        # Canonicalize both sides so those bundles remain verifiable.
        expected_hashes = {
            e["path"].replace("\\", "/"): e["sha256"] for e in manifest["files"]
        }
        verified = 0
        mismatched: list[str] = []
        for member in tar.getmembers():
            if member.name == "manifest.json":
                continue
            member_path = member.name.replace("\\", "/")
            if member_path not in expected_hashes:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            h = hashlib.sha256()
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
            if h.hexdigest() == expected_hashes[member_path]:
                verified += 1
            else:
                mismatched.append(member_path)

        if mismatched:
            raise RuntimeError(
                f"Bundle integrity check FAILED — {len(mismatched)} files' "
                f"SHA-256 didn't match the manifest. First mismatch: "
                f"{mismatched[0]!r}. Bundle is corrupt; DO NOT restore."
            )

        if verify_only:
            return {
                "verified_files": verified,
                "total_files": manifest["file_count"],
                "manifest": manifest,
                "integrity_ok": True,
            }

        # Actually extract. Recreate the data_root if missing.
        root.mkdir(parents=True, exist_ok=True)
        # Members are stored with `data/...` prefix; extract relative
        # to root.parent so the `data/` directory lands AT root.
        tar.extractall(path=root.parent, filter="data")

    return {
        "data_root": str(root),
        "verified_files": verified,
        "total_files": manifest["file_count"],
        "manifest_format_version": bundle_version,
        "integrity_ok": True,
    }


def _cli():
    parser = argparse.ArgumentParser(
        description="ONP backup / restore for the data directory."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="Create a backup bundle.")
    p_backup.add_argument(
        "--output",
        "-o",
        required=True,
        type=Path,
        help="Path for the output .tar.gz bundle.",
    )
    p_backup.add_argument(
        "--data-root",
        type=Path,
        help="Override the auto-detected data root.",
    )

    p_restore = sub.add_parser("restore", help="Restore a backup bundle.")
    p_restore.add_argument("bundle", type=Path, help="Path to the .tar.gz bundle.")
    p_restore.add_argument(
        "--data-root",
        type=Path,
        help="Override the auto-detected data root.",
    )
    p_restore.add_argument(
        "--force",
        action="store_true",
        help="Overwrite non-empty data_root. DANGER — destroys existing data.",
    )
    p_restore.add_argument(
        "--verify-only",
        action="store_true",
        help="Check bundle integrity without writing anything.",
    )

    args = parser.parse_args()

    if args.cmd == "backup":
        result = backup(args.output, data_root=args.data_root)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "restore":
        result = restore(
            args.bundle,
            data_root=args.data_root,
            force=args.force,
            verify_only=args.verify_only,
        )
        print(json.dumps(result, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli())
