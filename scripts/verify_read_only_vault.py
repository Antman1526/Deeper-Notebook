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


@dataclass(frozen=True)
class OutputTarget:
    path: Path
    parent_device: int
    parent_inode: int


@dataclass(frozen=True)
class RootIdentity:
    path: Path
    resolved_path: Path
    device: int
    inode: int


class VerificationError(Exception):
    """A safe, human-readable verification failure."""


class ScanVerificationError(VerificationError):
    """A scan failed after its mandatory post-scan source observation."""

    def __init__(self, hashes_changed: bool, git_changed: bool, observed: Snapshot):
        super().__init__("scan request failed")
        self.hashes_changed = hashes_changed
        self.git_changed = git_changed
        self.observed = observed


class SourceChangedError(VerificationError):
    """An API operation observed a source mutation in its mandatory after snapshot."""


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


def _capture_root_identity(root: Path) -> RootIdentity:
    """Bind verification to the validated directory, not a replaceable path."""
    try:
        resolved = root.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise VerificationError("source root changed during verification") from exc
    if not resolved.is_dir():
        raise VerificationError("source root changed during verification")
    return RootIdentity(root, resolved, metadata.st_dev, metadata.st_ino)


def _revalidate_root(identity: RootIdentity) -> Path:
    """Fail closed if the approved root path no longer names its original directory."""
    try:
        resolved = identity.path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise VerificationError("source root changed during verification") from exc
    if (
        not resolved.is_dir()
        or resolved != identity.resolved_path
        or (metadata.st_dev, metadata.st_ino) != (identity.device, identity.inode)
    ):
        raise VerificationError("source root changed during verification")
    return resolved


def _safe_output(value: str, root: Path) -> OutputTarget:
    """Resolve the destination before any report write or source observation."""
    try:
        output = Path(value).expanduser().resolve(strict=False)
    except OSError as exc:
        raise VerificationError("output path is invalid") from exc
    if output == root or root in output.parents:
        raise VerificationError("output must be outside the source root")
    if output.exists():
        raise VerificationError("output must be a new file outside the source root")
    try:
        parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise VerificationError("output parent is invalid") from exc
    if not parent.is_dir() or parent == root or root in parent.parents:
        raise VerificationError("output must be outside the source root")
    try:
        parent_stat = parent.stat()
    except OSError as exc:
        raise VerificationError("output parent is invalid") from exc
    return OutputTarget(output, parent_stat.st_dev, parent_stat.st_ino)


def _relative_files(root: Path) -> list[Path]:
    """Enumerate regular non-symlink files without changing the tree."""
    try:
        files: list[Path] = []
        for directory, names, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            names[:] = [
                name
                for name in names
                if name != ".git" and not (directory_path / name).is_symlink()
            ]
            for filename in filenames:
                candidate = directory_path / filename
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                files.append(candidate.relative_to(root))
        return sorted(files, key=lambda item: item.as_posix())
    except OSError as exc:
        raise VerificationError("source inventory failed") from exc


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_status(root: Path) -> tuple[str, bool]:
    if (root / ".git" / "index.lock").exists():
        return "git_status_unavailable", False
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "git_status_unavailable", False
    if result.returncode != 0:
        return "git_status_unavailable", False
    return result.stdout, True


def _snapshot(root: Path, identity: RootIdentity) -> Snapshot:
    _revalidate_root(identity)
    try:
        git_status, git_status_available = _git_status(root)
        snapshot = Snapshot(
            hashes={
                relative.as_posix(): _hash_file(root / relative)
                for relative in _relative_files(root)
            },
            git_status=git_status,
            git_status_available=git_status_available,
        )
    except VerificationError:
        raise
    except (OSError, UnicodeError) as exc:
        raise VerificationError("source observation failed") from exc
    _revalidate_root(identity)
    return snapshot


def _source_inventory_digest(hashes: dict[str, str]) -> str:
    """Return a stable commitment to the private per-file inventory."""
    digest = hashlib.sha256()
    for relative_path, file_hash in sorted(hashes.items()):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _provenance_digest(mapping: dict[str, list[Any]]) -> str:
    return hashlib.sha256(
        json.dumps(
            mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _manifest_counts(root: Path, identity: RootIdentity) -> dict[str, Any]:
    _revalidate_root(identity)
    manifest = root / MANIFEST_PATH
    if not manifest.is_file() or manifest.is_symlink():
        raise VerificationError("connector manifest is unavailable")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("connector manifest is invalid") from exc
    if not isinstance(payload, dict):
        raise VerificationError("connector manifest is invalid")
    has_documents = "documents" in payload
    has_records = "records" in payload
    if has_documents and has_records:
        raise VerificationError("connector manifest is ambiguous")
    records = payload.get("documents") if has_documents else payload.get("records")
    if not isinstance(records, list):
        raise VerificationError("connector manifest has no supported records list")
    record_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise VerificationError("connector manifest has invalid records")
        record_id = record.get("id")
        evidence_class = record.get("evidenceClass")
        if (
            not isinstance(record_id, str)
            or not record_id
            or not isinstance(evidence_class, str)
            or not evidence_class.strip()
        ):
            raise VerificationError("connector manifest has invalid records")
        if record_id in record_ids:
            raise VerificationError("connector manifest has duplicate records")
        record_ids.add(record_id)
    synthesis = [
        record
        for record in records
        if isinstance(record, dict) and record.get("evidenceClass") == "synthesis"
    ]
    expected_derived_from: dict[str, list[Any]] = {}
    for record in synthesis:
        record_id = record.get("id")
        derived_from = record.get("derivedFrom")
        if (
            not isinstance(record_id, str)
            or not record_id
            or not isinstance(derived_from, list)
        ):
            raise VerificationError(
                "connector manifest has invalid synthesis provenance"
            )
        if record_id in expected_derived_from:
            raise VerificationError(
                "connector manifest has duplicate synthesis records"
            )
        expected_derived_from[record_id] = derived_from
    counts = {
        "expected_trust_records": len(records),
        "expected_synthesis_records": len(synthesis),
        "expected_synthesis_with_derived_from": sum(
            isinstance(record.get("derivedFrom"), list) and bool(record["derivedFrom"])
            for record in synthesis
        ),
        "expected_derived_from": expected_derived_from,
        "expected_derived_from_digest": _provenance_digest(expected_derived_from),
    }
    _revalidate_root(identity)
    return counts


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
    api: str,
    name: str,
    path: Path,
    format_mode: str,
    parent_vault_id: str | None,
    watch_enabled: bool,
    request: Any,
) -> str:
    mounts = request("GET", api, "")
    if not isinstance(mounts, list):
        raise VerificationError("canonical vault API returned an invalid mount list")
    named_mounts = [
        mount
        for mount in mounts
        if isinstance(mount, dict) and mount.get("name") == name
    ]
    if named_mounts:
        if len(named_mounts) != 1:
            raise VerificationError(
                "existing vault mount conflicts with controlled verification"
            )
        value = named_mounts[0].get("id")
        if not isinstance(value, str) or not value:
            raise VerificationError(
                "canonical vault API returned an invalid existing mount"
            )
        detail = request("GET", api, f"/{value}")
        _validate_mount_detail(
            detail, value, name, path, format_mode, parent_vault_id, watch_enabled
        )
        return value
    payload: dict[str, Any] = {
        "name": name,
        "path": os.fspath(path),
        "format_mode": format_mode,
        "watch_enabled": watch_enabled,
    }
    if parent_vault_id:
        payload["parent_vault_id"] = parent_vault_id
    created = request("POST", api, "", payload)
    if not isinstance(created, dict) or not isinstance(created.get("id"), str):
        raise VerificationError("canonical vault API returned an invalid mount")
    value = created["id"]
    detail = request("GET", api, f"/{value}")
    _validate_mount_detail(
        detail, value, name, path, format_mode, parent_vault_id, watch_enabled
    )
    return value


def _validate_mount_detail(
    detail: Any,
    value: str,
    name: str,
    path: Path,
    format_mode: str,
    parent_vault_id: str | None,
    watch_enabled: bool,
) -> None:
    if not isinstance(detail, dict):
        raise VerificationError("canonical vault API returned an invalid mount detail")
    try:
        detail_path = Path(detail["root_path"]).expanduser().resolve(strict=True)
        expected_path = path.resolve(strict=True)
    except (KeyError, OSError, TypeError) as exc:
        raise VerificationError(
            "canonical vault API returned an invalid mount detail"
        ) from exc
    if (
        detail.get("id") != value
        or detail.get("name") != name
        or detail_path != expected_path
        or detail.get("format_mode") != format_mode
        or detail.get("parent_vault_id") != parent_vault_id
        or detail.get("watch_enabled") is not watch_enabled
    ):
        raise VerificationError("vault mount conflicts with controlled verification")


def _snapshot_differences(left: Snapshot, right: Snapshot) -> tuple[bool, bool]:
    return (
        left.hashes != right.hashes,
        left.git_status != right.git_status
        or left.git_status_available != right.git_status_available,
    )


class _ObservedApi:
    """Run every API request with a mandatory before/after source reconciliation."""

    def __init__(
        self,
        root: Path,
        identity: RootIdentity,
        baseline: Snapshot,
        report: dict[str, Any],
    ):
        self.root = root
        self.identity = identity
        self.baseline = baseline
        self.report = report

    def request(
        self, method: str, api: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        before = _snapshot(self.root, self.identity)
        before_hashes, before_git = _snapshot_differences(before, self.baseline)
        if before_hashes or before_git:
            _record_observation(self.report, before_hashes, before_git, before)
            raise SourceChangedError("source changed before API operation")
        request_failed = False
        try:
            result = _request_json(method, api, path, payload)
        except VerificationError:
            request_failed = True
            raise
        finally:
            after = _snapshot(self.root, self.identity)
            after_hashes, after_git = _snapshot_differences(after, self.baseline)
            if after_hashes or after_git:
                _record_observation(
                    self.report,
                    after_hashes,
                    after_git,
                    after,
                )
                if not request_failed:
                    raise SourceChangedError("source changed during API operation")
        return result


def _scan_once(
    api: str,
    mount_ids: list[str],
    root: Path,
    identity: RootIdentity,
    baseline: Snapshot,
    request: Any,
) -> tuple[int, bool, bool, Snapshot | None]:
    changed = 0
    for mount_id in mount_ids:
        before = _snapshot(root, identity)
        request_failed = False
        result: Any = None
        try:
            result = request("POST", api, f"/{mount_id}/scan")
        except SourceChangedError:
            after = _snapshot(root, identity)
            hashes_changed, git_changed = _snapshot_differences(after, baseline)
            return changed, hashes_changed, git_changed, after
        except VerificationError:
            request_failed = True
        finally:
            after = _snapshot(root, identity)
        before_hashes, before_git = _snapshot_differences(before, baseline)
        after_hashes, after_git = _snapshot_differences(after, baseline)
        if request_failed:
            raise ScanVerificationError(
                before_hashes or after_hashes, before_git or after_git, after
            )
        if not isinstance(result, dict) or not isinstance(result.get("parsed"), int):
            raise VerificationError("canonical vault API returned an invalid scan")
        changed += result["parsed"]
        if before_hashes or before_git or after_hashes or after_git:
            return (
                changed,
                before_hashes or after_hashes,
                before_git or after_git,
                after,
            )
    return changed, False, False, None


def _write_report(
    output: OutputTarget, root_identity: RootIdentity, report: dict[str, Any]
) -> None:
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        root = _revalidate_root(root_identity)
        resolved_output = output.path.resolve(strict=False)
        parent = resolved_output.parent.resolve(strict=True)
        if (
            resolved_output == root
            or root in resolved_output.parents
            or parent == root
            or root in parent.parents
        ):
            raise VerificationError("output must remain outside the source root")
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(parent, flags)
        try:
            parent_stat = os.fstat(parent_descriptor)
            if (parent_stat.st_dev, parent_stat.st_ino) != (
                output.parent_device,
                output.parent_inode,
            ):
                raise VerificationError("output parent changed during verification")
            descriptor = os.open(
                resolved_output.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
        finally:
            os.close(parent_descriptor)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(payload)
    except (OSError, VerificationError) as exc:
        raise VerificationError("sanitized report could not be created") from exc


def _safe_report(
    root: Path, initial: Snapshot, counts: dict[str, Any], mode: str
) -> dict[str, Any]:
    return {
        "root_label": root.name,
        "mode": mode,
        "source_files_observed": len(initial.hashes),
        "source_inventory_digest": _source_inventory_digest(initial.hashes),
        "source_files_changed": 0,
        "git_status_changed": False,
        "git_status_available": initial.git_status_available,
        "git_status": initial.git_status
        if not initial.git_status_available
        else "captured",
        "second_scan_changed_projections": 0,
        "expected_trust_records": counts["expected_trust_records"],
        "expected_synthesis_records": counts["expected_synthesis_records"],
        "expected_synthesis_with_derived_from": counts[
            "expected_synthesis_with_derived_from"
        ],
        "expected_derived_from_digest": counts["expected_derived_from_digest"],
        "trust_records": 0,
        "synthesis_records": 0,
        "synthesis_with_derived_from": 0,
        "receipts": 0,
        "failures": [],
    }


def _record_git_status(report: dict[str, Any], snapshot: Snapshot) -> None:
    report["git_status_available"] = snapshot.git_status_available
    report["git_status"] = (
        snapshot.git_status if not snapshot.git_status_available else "captured"
    )


def _record_observation(
    report: dict[str, Any], hashes_changed: bool, git_changed: bool, observed: Snapshot
) -> None:
    report["source_files_changed"] = int(
        bool(report["source_files_changed"] or hashes_changed)
    )
    report["git_status_changed"] = bool(report["git_status_changed"] or git_changed)
    _record_git_status(report, observed)
    if hashes_changed:
        if "source_hash_mismatch" not in report["failures"]:
            report["failures"].append("source_hash_mismatch")
    if git_changed:
        if "git_status_mismatch" not in report["failures"]:
            report["failures"].append("git_status_mismatch")


def run(
    root: Path,
    root_identity: RootIdentity,
    api: str,
    output: OutputTarget,
    check_only: bool,
) -> int:
    initial = _snapshot(root, root_identity)
    counts = _manifest_counts(root, root_identity)
    report = _safe_report(
        root, initial, counts, "check-only" if check_only else "controlled"
    )
    if check_only:
        _write_report(output, root_identity, report)
        return 0
    try:
        observed_api = _ObservedApi(root, root_identity, initial, report)
        request = observed_api.request
        parent_id = _mount_id(api, "2nd Brains", root, "mixed", None, False, request)
        obsidian_id = _mount_id(
            api,
            "Obsidian Brain",
            root / "Obsidian Brain",
            "obsidian",
            parent_id,
            True,
            request,
        )
        logseq_id = _mount_id(
            api,
            "Logseq Brain",
            root / "Logseq Brain",
            "logseq",
            parent_id,
            True,
            request,
        )
        request(
            "POST",
            api,
            f"/{parent_id}/trust/import",
            {"manifest_relative_path": MANIFEST_PATH},
        )
        scan_mounts = [obsidian_id, logseq_id]
        _, first_hash_mismatch, first_git_mismatch, first_observed = _scan_once(
            api, scan_mounts, root, root_identity, initial, request
        )
        if first_hash_mismatch or first_git_mismatch:
            _record_observation(
                report,
                first_hash_mismatch,
                first_git_mismatch,
                first_observed or initial,
            )
            _write_report(output, root_identity, report)
            return 1
        second_changed, second_hash_mismatch, second_git_mismatch, second_observed = (
            _scan_once(api, scan_mounts, root, root_identity, initial, request)
        )
        report["second_scan_changed_projections"] = second_changed
        if second_hash_mismatch or second_git_mismatch:
            _record_observation(
                report,
                second_hash_mismatch,
                second_git_mismatch,
                second_observed or initial,
            )
            _write_report(output, root_identity, report)
            return 1
        trust = request("GET", api, f"/{parent_id}/trust")
        summary = request("GET", api, f"/{parent_id}/trust/summary")
        receipts = request("GET", api, f"/{parent_id}/receipts")
    except SourceChangedError:
        _write_report(output, root_identity, report)
        return 1
    except ScanVerificationError as exc:
        _record_observation(report, exc.hashes_changed, exc.git_changed, exc.observed)
        report["failures"].append("scan_request_failed")
        _write_report(output, root_identity, report)
        return 2
    except VerificationError:
        report["failures"].append("verification_operation_failed")
        _write_report(output, root_identity, report)
        return 2
    if (
        not isinstance(trust, list)
        or not isinstance(summary, dict)
        or not isinstance(receipts, list)
    ):
        report["failures"].append("verification_operation_failed")
        _write_report(output, root_identity, report)
        return 2
    report["trust_records"] = len(trust)
    report["synthesis_records"] = sum(
        item.get("evidence_class") == "synthesis"
        for item in trust
        if isinstance(item, dict)
    )
    report["synthesis_with_derived_from"] = sum(
        item.get("evidence_class") == "synthesis"
        and isinstance(item.get("derived_from"), list)
        and bool(item["derived_from"])
        for item in trust
        if isinstance(item, dict)
    )
    report["receipts"] = len(receipts)
    returned_derived_from = {
        item.get("manifest_id"): item.get("derived_from")
        for item in trust
        if isinstance(item, dict) and item.get("evidence_class") == "synthesis"
    }
    if (
        summary.get("total") != report["trust_records"]
        or report["trust_records"] != counts["expected_trust_records"]
    ):
        report["failures"].append("trust_count_mismatch")
    if report["synthesis_records"] != counts["expected_synthesis_records"]:
        report["failures"].append("synthesis_count_mismatch")
    if (
        report["synthesis_with_derived_from"]
        != counts["expected_synthesis_with_derived_from"]
        or returned_derived_from != counts["expected_derived_from"]
    ):
        report["failures"].append("derived_from_mismatch")
    if report["source_files_changed"]:
        report["failures"].append("source_hash_mismatch")
    if report["git_status_changed"]:
        report["failures"].append("git_status_mismatch")
    if report["second_scan_changed_projections"]:
        report["failures"].append("second_scan_not_idempotent")
    _write_report(output, root_identity, report)
    return 1 if report["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Explicit external vault root")
    parser.add_argument(
        "--api", required=True, help="Canonical Deeper Notebook API base URL"
    )
    parser.add_argument("--output", required=True, help="Sanitized JSON report path")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and hash only; never call the API",
    )
    args = parser.parse_args(argv)
    try:
        root = _safe_root(args.root)
        root_identity = _capture_root_identity(root)
        output = _safe_output(args.output, root)
        return run(root, root_identity, args.api, output, args.check_only)
    except Exception:
        print("verification failed: safe verification error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
