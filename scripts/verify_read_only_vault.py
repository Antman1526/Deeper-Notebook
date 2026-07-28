#!/usr/bin/env python3
"""Prove a user-invoked external vault scan left source files unchanged.

This utility only receives a vault path from its explicit CLI invocation.  It
never discovers candidate roots and never attempts to repair Git state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MANIFEST_PATH = "brain-engine/generated/deepercode-connector/manifest.json"
API_PREFIX = "/vaults"


@dataclass(frozen=True)
class Snapshot:
    hashes: dict[str, str]
    git_status: str
    git_status_available: bool


class VerificationError(Exception):
    """A safe, human-readable verification failure."""


def _safe_root(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate == Path("/") or candidate == Path.home():
        raise VerificationError("root must be a non-home, non-root directory")
    try:
        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise VerificationError("root must be a non-home, non-root directory") from exc
    if root == Path("/") or root == Path.home().resolve() or not root.is_dir():
        raise VerificationError("root must be a non-home, non-root directory")
    return root


def _safe_output(value: str, root: Path) -> Path:
    """Resolve the destination before any report write or source observation."""
    try:
        output = Path(value).expanduser().resolve(strict=False)
    except OSError as exc:
        raise VerificationError("output path is invalid") from exc
    if output == root or root in output.parents or (output.exists() and output.is_dir()):
        raise VerificationError("output must be outside the source root")
    return output


def _relative_files(root: Path) -> list[Path]:
    """Enumerate regular non-symlink files without changing the tree."""
    command = [
        "git",
        "-C",
        os.fspath(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode == 0:
        candidates = [
            Path(item.decode("utf-8", "surrogateescape"))
            for item in result.stdout.split(b"\0")
            if item
        ]
    else:
        candidates = [
            item.relative_to(root)
            for item in root.rglob("*")
            if ".git" not in item.relative_to(root).parts
        ]
    files: list[Path] = []
    for relative in candidates:
        if ".git" in relative.parts:
            continue
        candidate = root / relative
        if candidate.is_file() and not candidate.is_symlink():
            files.append(relative)
    return sorted(files, key=lambda item: item.as_posix())


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_status(root: Path) -> tuple[str, bool]:
    if (root / ".git" / "index.lock").exists():
        return "git_status_unavailable", False
    result = subprocess.run(
        ["git", "-C", os.fspath(root), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return "git_status_unavailable", False
    return result.stdout, True


def _snapshot(root: Path) -> Snapshot:
    git_status, git_status_available = _git_status(root)
    return Snapshot(
        hashes={relative.as_posix(): _hash_file(root / relative) for relative in _relative_files(root)},
        git_status=git_status,
        git_status_available=git_status_available,
    )


def _manifest_counts(root: Path) -> dict[str, int]:
    manifest = root / MANIFEST_PATH
    if not manifest.is_file() or manifest.is_symlink():
        raise VerificationError("connector manifest is unavailable")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("connector manifest is invalid") from exc
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise VerificationError("connector manifest has no records list")
    synthesis = [
        record
        for record in records
        if isinstance(record, dict) and record.get("evidenceClass") == "synthesis"
    ]
    expected_derived_from: dict[str, list[Any]] = {}
    for record in synthesis:
        record_id = record.get("id")
        derived_from = record.get("derivedFrom")
        if not isinstance(record_id, str) or not record_id or not isinstance(derived_from, list):
            raise VerificationError("connector manifest has invalid synthesis provenance")
        if record_id in expected_derived_from:
            raise VerificationError("connector manifest has duplicate synthesis records")
        expected_derived_from[record_id] = derived_from
    return {
        "expected_trust_records": len(records),
        "expected_synthesis_records": len(synthesis),
        "expected_synthesis_with_derived_from": sum(
            isinstance(record.get("derivedFrom"), list) and bool(record["derivedFrom"])
            for record in synthesis
        ),
        "expected_derived_from": expected_derived_from,
    }


def _request_json(
    method: str, api: str, path: str, payload: dict[str, Any] | None = None
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{api.rstrip('/')}{API_PREFIX}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urlopen(request, timeout=30) as response:  # nosec B310: CLI API supplied by owner
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("canonical vault API request failed") from exc


def _mount_id(
    api: str, name: str, path: Path, format_mode: str, parent_vault_id: str | None, watch_enabled: bool
) -> str:
    mounts = _request_json("GET", api, "")
    if isinstance(mounts, list):
        named_mounts = [mount for mount in mounts if isinstance(mount, dict) and mount.get("name") == name]
        if named_mounts:
            if len(named_mounts) != 1:
                raise VerificationError("existing vault mount conflicts with controlled verification")
            value = named_mounts[0].get("id")
            if not isinstance(value, str) or not value:
                raise VerificationError("canonical vault API returned an invalid existing mount")
            detail = _request_json("GET", api, f"/{value}")
            if not isinstance(detail, dict):
                raise VerificationError("canonical vault API returned an invalid existing mount")
            try:
                detail_path = Path(detail["root_path"]).expanduser().resolve(strict=True)
            except (KeyError, OSError, TypeError) as exc:
                raise VerificationError("canonical vault API returned an invalid existing mount") from exc
            expected_path = path.resolve(strict=True)
            if (
                detail.get("id") != value
                or detail.get("name") != name
                or detail_path != expected_path
                or detail.get("format_mode") != format_mode
                or detail.get("parent_vault_id") != parent_vault_id
                or detail.get("watch_enabled") is not watch_enabled
            ):
                raise VerificationError("existing vault mount conflicts with controlled verification")
            return value
    payload: dict[str, Any] = {
        "name": name,
        "path": os.fspath(path),
        "format_mode": format_mode,
        "watch_enabled": watch_enabled,
    }
    if parent_vault_id:
        payload["parent_vault_id"] = parent_vault_id
    created = _request_json("POST", api, "", payload)
    if not isinstance(created, dict) or not isinstance(created.get("id"), str):
        raise VerificationError("canonical vault API returned an invalid mount")
    return created["id"]


def _snapshot_differences(left: Snapshot, right: Snapshot) -> tuple[bool, bool]:
    return (
        left.hashes != right.hashes,
        left.git_status != right.git_status
        or left.git_status_available != right.git_status_available,
    )


def _scan_once(
    api: str, mount_ids: list[str], root: Path, baseline: Snapshot
) -> tuple[int, bool, bool, Snapshot | None]:
    changed = 0
    for mount_id in mount_ids:
        before = _snapshot(root)
        result = _request_json("POST", api, f"/{mount_id}/scan")
        after = _snapshot(root)
        if not isinstance(result, dict) or not isinstance(result.get("parsed"), int):
            raise VerificationError("canonical vault API returned an invalid scan")
        changed += result["parsed"]
        before_hashes, before_git = _snapshot_differences(before, baseline)
        after_hashes, after_git = _snapshot_differences(after, baseline)
        if before_hashes or before_git or after_hashes or after_git:
            return changed, before_hashes or after_hashes, before_git or after_git, after
    return changed, False, False, None


def _write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_report(root: Path, initial: Snapshot, counts: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "root_label": root.name,
        "mode": mode,
        "source_hashes": initial.hashes,
        "source_files_observed": len(initial.hashes),
        "source_files_changed": 0,
        "git_status_changed": False,
        "git_status_available": initial.git_status_available,
        "git_status": initial.git_status if not initial.git_status_available else "captured",
        "second_scan_changed_projections": 0,
        **counts,
        "trust_records": 0,
        "synthesis_records": 0,
        "synthesis_with_derived_from": 0,
        "receipts": 0,
        "failures": [],
    }


def _record_git_status(report: dict[str, Any], snapshot: Snapshot) -> None:
    report["git_status_available"] = snapshot.git_status_available
    report["git_status"] = snapshot.git_status if not snapshot.git_status_available else "captured"


def run(root: Path, api: str, output: Path, check_only: bool) -> int:
    initial = _snapshot(root)
    counts = _manifest_counts(root)
    report = _safe_report(root, initial, counts, "check-only" if check_only else "controlled")
    if check_only:
        _write_report(output, report)
        return 0

    parent_id = _mount_id(api, "2nd Brains", root, "mixed", None, False)
    obsidian_id = _mount_id(api, "Obsidian Brain", root / "Obsidian Brain", "obsidian", parent_id, True)
    logseq_id = _mount_id(api, "Logseq Brain", root / "Logseq Brain", "logseq", parent_id, True)
    _request_json("POST", api, f"/{parent_id}/trust/import", {"manifest_relative_path": MANIFEST_PATH})
    mounts = [parent_id, obsidian_id, logseq_id]
    _, first_hash_mismatch, first_git_mismatch, first_observed = _scan_once(api, mounts, root, initial)
    if first_hash_mismatch or first_git_mismatch:
        report["source_files_changed"] = int(first_hash_mismatch)
        report["git_status_changed"] = first_git_mismatch
        if first_observed:
            _record_git_status(report, first_observed)
        if first_hash_mismatch:
            report["failures"].append("source_hash_mismatch")
        if first_git_mismatch:
            report["failures"].append("git_status_mismatch")
        _write_report(output, report)
        return 1
    second_changed, second_hash_mismatch, second_git_mismatch, second_observed = _scan_once(api, mounts, root, initial)
    report["second_scan_changed_projections"] = second_changed
    if second_hash_mismatch or second_git_mismatch:
        report["source_files_changed"] = int(second_hash_mismatch)
        report["git_status_changed"] = second_git_mismatch
        if second_observed:
            _record_git_status(report, second_observed)
        if second_hash_mismatch:
            report["failures"].append("source_hash_mismatch")
        if second_git_mismatch:
            report["failures"].append("git_status_mismatch")
        _write_report(output, report)
        return 1

    trust = _request_json("GET", api, f"/{parent_id}/trust")
    summary = _request_json("GET", api, f"/{parent_id}/trust/summary")
    receipts = _request_json("GET", api, f"/{parent_id}/receipts")
    if not isinstance(trust, list) or not isinstance(summary, dict) or not isinstance(receipts, list):
        raise VerificationError("canonical vault API returned invalid reconciliation data")
    report["trust_records"] = len(trust)
    report["synthesis_records"] = sum(item.get("evidence_class") == "synthesis" for item in trust if isinstance(item, dict))
    report["synthesis_with_derived_from"] = sum(
        item.get("evidence_class") == "synthesis" and isinstance(item.get("derived_from"), list) and bool(item["derived_from"])
        for item in trust if isinstance(item, dict)
    )
    report["receipts"] = len(receipts)
    returned_derived_from = {
        item.get("id"): item.get("derived_from")
        for item in trust
        if isinstance(item, dict) and item.get("evidence_class") == "synthesis"
    }
    if summary.get("total") != report["trust_records"] or report["trust_records"] != counts["expected_trust_records"]:
        report["failures"].append("trust_count_mismatch")
    if report["synthesis_records"] != counts["expected_synthesis_records"]:
        report["failures"].append("synthesis_count_mismatch")
    if (
        report["synthesis_with_derived_from"] != counts["expected_synthesis_with_derived_from"]
        or returned_derived_from != counts["expected_derived_from"]
    ):
        report["failures"].append("derived_from_mismatch")
    if report["source_files_changed"]:
        report["failures"].append("source_hash_mismatch")
    if report["git_status_changed"]:
        report["failures"].append("git_status_mismatch")
    if report["second_scan_changed_projections"]:
        report["failures"].append("second_scan_not_idempotent")
    _write_report(output, report)
    return 1 if report["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Explicit external vault root")
    parser.add_argument("--api", required=True, help="Canonical Deeper Notebook API base URL")
    parser.add_argument("--output", required=True, help="Sanitized JSON report path")
    parser.add_argument("--check-only", action="store_true", help="Validate and hash only; never call the API")
    args = parser.parse_args(argv)
    try:
        root = _safe_root(args.root)
        output = _safe_output(args.output, root)
        return run(root, args.api, output, args.check_only)
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
