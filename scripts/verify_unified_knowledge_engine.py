#!/usr/bin/env python3
"""Read-only verifier for server-owned legacy/unified projection equivalence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_SYNTHETIC_FILES = 10_000
MAX_SYNTHETIC_FILE_BYTES = 10 * 1024 * 1024
MAX_SYNTHETIC_TOTAL_BYTES = 100 * 1024 * 1024
SCAN_STABILIZATION_SECONDS = 2.1
BACKFILL_WAIT_SECONDS = 60.0
BACKFILL_POLL_SECONDS = 0.1
_SPACE_ID_PATTERN = re.compile(r"^knowledge_engine_space:[A-Za-z0-9_-]+$")
_RECORD_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:[A-Za-z0-9_-]+$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FILE_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_EVIDENCE_PARSE_STATUSES = frozenset({"parsed", "unsupported", "invalid"})
_KNOWN_MISMATCH_CODES = frozenset(
    {
        "space_id_mismatch",
        "document_count_mismatch",
        "block_count_mismatch",
        "relation_count_mismatch",
        "task_count_mismatch",
        "property_count_mismatch",
        "tag_count_mismatch",
        "asset_count_mismatch",
        "document_hash_mismatch",
        "identity_pair_mismatch",
        "outgoing_membership_mismatch",
        "backlink_membership_mismatch",
        "graph_membership_mismatch",
        "exact_search_membership_mismatch",
        "authority_mismatch",
        "source_kind_mismatch",
        "format_mismatch",
        "provenance_mismatch",
        "capabilities_mismatch",
        "overlay_revision_mapping_mismatch",
    }
)


class VerificationRefusal(RuntimeError):
    """A stable, content-free reason to refuse unsafe verifier input."""


class VerificationUnavailable(RuntimeError):
    """A stable local transport failure with no endpoint details."""


def _engine_space_id(source_ref: str) -> str:
    return f"knowledge_engine_space:{hashlib.sha256(source_ref.encode()).hexdigest()}"


def _startup_checkpoint_space_ids(parent_vault_id: str) -> tuple[str, str]:
    """Derive the only startup spaces the controlled proof is allowed to trust."""
    overlay_space_id = _engine_space_id("overlay:default")
    parent_space_id = _engine_space_id(parent_vault_id)
    if overlay_space_id < parent_space_id:
        return overlay_space_id, parent_space_id
    return parent_space_id, overlay_space_id


@dataclass(frozen=True, slots=True)
class Inputs:
    api_url: str
    token_path: Path
    report_path: Path
    space_ids: tuple[str, ...]
    exact_queries: tuple[str, ...]
    require_shadow_enabled: bool
    proof_phase: str | None = None
    synthetic_manifest: Path | None = None
    expected_prior_state: Path | None = None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify unified projection equivalence"
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--auth-token-file", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--space-id", action="append", default=[])
    parser.add_argument("--exact-query", action="append", default=[])
    parser.add_argument("--require-shadow-enabled", action="store_true")
    parser.add_argument("--proof-phase", choices=("prepare", "verify"))
    parser.add_argument("--synthetic-manifest", type=Path)
    parser.add_argument("--expected-prior-state", type=Path)
    return parser


def _inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_api_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.port is None
    ):
        raise VerificationRefusal("api_url_must_be_explicit_loopback_http")
    return value.rstrip("/")


def _validate_token_path(path: Path) -> Path:
    candidate = path.absolute()
    if candidate.is_symlink() or not candidate.is_file():
        raise VerificationRefusal("auth_token_file_invalid")
    details = candidate.stat()
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_mode & 0o077
        or not 1 <= details.st_size <= 4096
    ):
        raise VerificationRefusal("auth_token_file_invalid")
    return candidate.resolve(strict=True)


def _validate_report_path(path: Path, token_path: Path) -> Path:
    candidate = path.absolute()
    if candidate == token_path or _inside(candidate, ROOT):
        raise VerificationRefusal("report_path_invalid")
    if candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
        raise VerificationRefusal("report_path_invalid")
    parent = candidate.parent
    if not parent.exists() or parent.is_symlink() or not parent.is_dir():
        raise VerificationRefusal("report_path_invalid")
    resolved_parent = parent.resolve(strict=True)
    if _inside(resolved_parent, ROOT) or resolved_parent == ROOT:
        raise VerificationRefusal("report_path_invalid")
    return resolved_parent / candidate.name


def _read_token(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\x00" in token or "\n" in token or "\r" in token:
        raise VerificationRefusal("auth_token_file_invalid")
    return token


def _inputs(namespace: argparse.Namespace) -> Inputs:
    space_ids = tuple(namespace.space_id)
    exact_queries = tuple(namespace.exact_query)
    if (
        not space_ids
        or len(set(space_ids)) != len(space_ids)
        or any(
            not isinstance(value, str) or _SPACE_ID_PATTERN.fullmatch(value) is None
            for value in space_ids
        )
        or not 1 <= len(exact_queries) <= 32
        or any(not query.strip() or len(query) > 256 for query in exact_queries)
    ):
        raise VerificationRefusal("verification_inventory_invalid")
    token_path = _validate_token_path(namespace.auth_token_file)
    report_path = _validate_report_path(namespace.report_path, token_path)
    proof_values = (
        namespace.proof_phase,
        namespace.synthetic_manifest,
        namespace.expected_prior_state,
    )
    if any(value is not None for value in proof_values) and not all(
        value is not None for value in proof_values
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    return Inputs(
        api_url=_validate_api_url(namespace.api_url),
        token_path=token_path,
        report_path=report_path,
        space_ids=space_ids,
        exact_queries=exact_queries,
        require_shadow_enabled=bool(namespace.require_shadow_enabled),
        proof_phase=namespace.proof_phase,
        synthetic_manifest=namespace.synthetic_manifest,
        expected_prior_state=namespace.expected_prior_state,
    )


def _disjoint(first: Path, second: Path) -> bool:
    return not _inside(first, second) and not _inside(second, first)


def _safe_synthetic_root(path: Path, marker: str, protected: tuple[Path, ...]) -> Path:
    candidate = path.absolute()
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    home = Path.home().resolve(strict=True)
    desktop = home / "Desktop"
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise VerificationRefusal("synthetic_manifest_invalid") from None
    if (
        candidate != resolved
        or not resolved.is_dir()
        or not _inside(resolved, temporary_root)
        or resolved in {temporary_root, home, desktop, ROOT}
        or not _disjoint(resolved, home)
        or not _disjoint(resolved, desktop)
        or not _disjoint(resolved, ROOT)
        or any(not _disjoint(resolved, item) for item in protected)
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    marker_path = resolved / marker
    try:
        if (
            marker_path.is_symlink()
            or marker_path.read_text(encoding="utf-8") != "synthetic-proof-v1\n"
        ):
            raise VerificationRefusal("synthetic_manifest_invalid")
        for parent, directories, files in os.walk(resolved, followlinks=False):
            for name in [*directories, *files]:
                entry = Path(parent) / name
                details = entry.lstat()
                if entry.is_symlink() or (
                    stat.S_ISREG(details.st_mode) and details.st_nlink != 1
                ):
                    raise VerificationRefusal("synthetic_manifest_invalid")
    except (OSError, UnicodeError):
        raise VerificationRefusal("synthetic_manifest_invalid") from None
    return resolved


def _proof_path(value: Any, temporary_root: Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError
    candidate = Path(value).absolute()
    parent = candidate.parent.absolute()
    if candidate.exists() and candidate.is_symlink():
        raise ValueError
    if not parent.exists() or parent.is_symlink():
        raise ValueError
    resolved_parent = parent.resolve(strict=True)
    if parent != resolved_parent or not _inside(resolved_parent, temporary_root):
        raise ValueError
    return candidate


def _synthetic_fingerprints(root: Path, marker: str) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    total_bytes = 0
    for parent, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        for name in files:
            path = Path(parent) / name
            if path.name == marker:
                continue
            details = path.lstat()
            if (
                path.is_symlink()
                or not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
            ):
                raise VerificationRefusal("synthetic_manifest_invalid")
            total_bytes += details.st_size
            if (
                details.st_size > MAX_SYNTHETIC_FILE_BYTES
                or total_bytes > MAX_SYNTHETIC_TOTAL_BYTES
                or len(fingerprints) >= MAX_SYNTHETIC_FILES
            ):
                raise VerificationRefusal("synthetic_manifest_invalid")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fingerprints[path.relative_to(root).as_posix()] = digest
    return dict(sorted(fingerprints.items()))


def _synthetic_git_digest(root: Path) -> str | None:
    git_directory = root / ".git"
    if not git_directory.exists():
        return None
    if git_directory.is_symlink() or not git_directory.is_dir():
        raise VerificationRefusal("synthetic_manifest_invalid")
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z"],
        check=False,
        capture_output=True,
        timeout=5,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "core.hooksPath",
            "GIT_CONFIG_VALUE_1": os.devnull,
        },
    )
    if result.returncode != 0:
        raise VerificationRefusal("synthetic_manifest_invalid")
    return hashlib.sha256(result.stdout).hexdigest()


def _synthetic_root_evidence(
    root_name: str,
    root: Path,
    marker: str,
) -> dict[str, Any]:
    if root_name not in {"overlay", "parent", "child"}:
        raise VerificationRefusal("synthetic_manifest_invalid")
    fingerprints = _synthetic_fingerprints(root, marker)
    if root_name == "overlay":
        fingerprints = {
            relative_path: digest
            for relative_path, digest in fingerprints.items()
            if not relative_path.startswith("logs/")
        }
    return {
        "fingerprints": fingerprints,
        "git_status_sha256": _synthetic_git_digest(root),
    }


def _proof_manifest(inputs: Inputs) -> dict[str, Any]:
    assert inputs.synthetic_manifest is not None
    try:
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        manifest_path = _proof_path(inputs.synthetic_manifest, temporary_root)
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != 1
            or payload.get("marker") != ".deeper-notebook-synthetic-proof-v1"
            or not isinstance(payload.get("roots"), dict)
            or set(payload["roots"]) != {"overlay", "parent", "child"}
            or not isinstance(payload.get("paths"), dict)
            or set(payload["paths"]) != {"database", "state", "report", "token"}
            or not isinstance(payload.get("expected"), dict)
        ):
            raise ValueError
        paths = {
            name: _proof_path(value, temporary_root)
            for name, value in payload["paths"].items()
        }
        if (
            paths["report"] != inputs.report_path
            or paths["token"] != inputs.token_path
            or paths["state"] != inputs.expected_prior_state
            or len(set(paths.values())) != len(paths)
        ):
            raise ValueError
        database = paths["database"]
        if (
            not database.exists()
            or not database.is_dir()
            or database.is_symlink()
            or (database / payload["marker"]).read_text(encoding="utf-8")
            != "synthetic-proof-v1\n"
        ):
            raise ValueError
        protected = tuple(path.absolute() for path in (*paths.values(), manifest_path))
        roots = {
            name: _safe_synthetic_root(Path(value), payload["marker"], protected)
            for name, value in payload["roots"].items()
            if isinstance(value, str)
        }
        if set(roots) != {"overlay", "parent", "child"} or any(
            not _disjoint(first, second)
            for name, first in roots.items()
            for other, second in roots.items()
            if name < other
        ):
            raise ValueError
        if any(not _disjoint(root, manifest_path) for root in roots.values()):
            raise ValueError
        payload["roots"] = {name: str(path) for name, path in roots.items()}
        payload["paths"] = {name: str(path) for name, path in paths.items()}
        return payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise VerificationRefusal("synthetic_manifest_invalid") from None


def _get(inputs: Inputs, token: str, path: str) -> tuple[int, Any]:
    request = urllib.request.Request(
        f"{inputs.api_url}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    except (TimeoutError, urllib.error.URLError) as error:
        raise VerificationUnavailable("api_unavailable") from error
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        response_status = int(response.status)
    finally:
        response.close()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise VerificationRefusal("api_response_invalid")
    try:
        return response_status, json.loads(raw) if raw else None
    except json.JSONDecodeError as error:
        raise VerificationRefusal("api_response_invalid") from error


def _json_request(
    inputs: Inputs, token: str, method: str, path: str, payload: dict[str, Any]
) -> tuple[int, Any]:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{inputs.api_url}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=encoded,
        method=method,
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    except (TimeoutError, urllib.error.URLError) as error:
        raise VerificationUnavailable("api_unavailable") from error
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        response_status = int(response.status)
    finally:
        response.close()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise VerificationRefusal("api_response_invalid")
    try:
        return response_status, json.loads(raw) if raw else None
    except json.JSONDecodeError as error:
        raise VerificationRefusal("api_response_invalid") from error


def _proof_identity(inputs: Inputs, token: str) -> dict[str, Any]:
    response_status, payload = _get(
        inputs, token, "/api/deeper-notebook/overlay/proof-identity"
    )
    if (
        response_status != 200
        or not isinstance(payload, dict)
        or not isinstance(payload.get("instance_nonce"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", payload["instance_nonce"])
        or not isinstance(payload.get("instance_pid"), int)
        or payload["instance_pid"] <= 1
        or not isinstance(payload.get("overlay_root_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["overlay_root_sha256"])
    ):
        raise VerificationRefusal("api_response_invalid")
    return payload


def _wait_for_terminal_backfill(
    inputs: Inputs,
    token: str,
    expected_space_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    if (
        not 1 <= len(expected_space_ids) <= 32
        or len(set(expected_space_ids)) != len(expected_space_ids)
        or any(_SPACE_ID_PATTERN.fullmatch(item) is None for item in expected_space_ids)
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    query = urllib.parse.urlencode(
        [("space_id", space_id) for space_id in expected_space_ids]
    )
    deadline = time.monotonic() + BACKFILL_WAIT_SECONDS
    expected = set(expected_space_ids)
    while True:
        response_status, payload = _get(
            inputs,
            token,
            "/api/deeper-notebook/knowledge-engine/backfill-checkpoints?"
            f"{query}",
        )
        if response_status != 200 or not isinstance(payload, list):
            raise VerificationRefusal("api_response_invalid")
        checkpoints: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in payload:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"space_id", "status", "projected", "unchanged", "failed"}
                or not isinstance(item.get("space_id"), str)
                or item["space_id"] not in expected
                or item["space_id"] in seen
                or item.get("status")
                not in {"pending", "running", "completed", "failed"}
                or any(
                    isinstance(item.get(field), bool)
                    or not isinstance(item.get(field), int)
                    or item[field] < 0
                    for field in ("projected", "unchanged", "failed")
                )
            ):
                raise VerificationRefusal("api_response_invalid")
            seen.add(item["space_id"])
            checkpoints.append(dict(item))
        checkpoints.sort(key=lambda item: item["space_id"])
        if any(item["status"] == "failed" for item in checkpoints):
            raise VerificationUnavailable("backfill_not_terminal")
        if seen == expected and all(
            item["status"] == "completed" for item in checkpoints
        ):
            return checkpoints
        if time.monotonic() >= deadline:
            raise VerificationUnavailable("backfill_not_terminal")
        time.sleep(BACKFILL_POLL_SECONDS)


def _record_id(value: Any) -> str:
    if not isinstance(value, str) or _RECORD_ID_PATTERN.fullmatch(value) is None:
        raise VerificationRefusal("api_response_invalid")
    return value


def _content_hash(value: Any) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise VerificationRefusal("api_response_invalid")
    return value


def _canonical_relative(value: Any) -> str:
    if not isinstance(value, str):
        raise VerificationRefusal("api_response_invalid")
    path = PurePosixPath(value)
    if (
        not value
        or value.strip() != value
        or path.is_absolute()
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise VerificationRefusal("api_response_invalid")
    return value


def _successful_get(
    inputs: Inputs,
    token: str,
    path: str,
    expected_type: type,
) -> Any:
    status_code, payload = _get(inputs, token, path)
    if status_code != 200 or not isinstance(payload, expected_type):
        raise VerificationRefusal("api_response_invalid")
    return payload


def _mount_evidence(
    inputs: Inputs,
    token: str,
    *,
    vault_id: str,
    expected_name: str,
    expected_root: str,
    expected_parent_id: str | None,
) -> dict[str, Any]:
    payload = _successful_get(
        inputs,
        token,
        f"/api/deeper-notebook/vaults/{urllib.parse.quote(vault_id, safe=':')}",
        dict,
    )
    if (
        _record_id(payload.get("id")) != vault_id
        or payload.get("name") != expected_name
        or payload.get("root_path") != expected_root
        or payload.get("parent_vault_id") != expected_parent_id
        or payload.get("format_mode") not in {"markdown", "obsidian", "logseq"}
        or payload.get("state")
        not in {"ready-read-only", "degraded", "conflict", "unavailable"}
        or not isinstance(payload.get("watch_enabled"), bool)
    ):
        raise VerificationRefusal("api_response_invalid")
    return {
        "id": vault_id,
        "name_sha256": hashlib.sha256(expected_name.encode()).hexdigest(),
        "root_sha256": hashlib.sha256(expected_root.encode()).hexdigest(),
        "parent_vault_id": expected_parent_id,
        "format_mode": payload["format_mode"],
        "state": payload["state"],
        "watch_enabled": payload["watch_enabled"],
    }


def _file_evidence(
    inputs: Inputs,
    token: str,
    *,
    vault_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], set[str], set[str]]:
    payload = _successful_get(
        inputs,
        token,
        f"/api/deeper-notebook/vaults/{urllib.parse.quote(vault_id, safe=':')}"
        "/files?limit=500&offset=0",
        list,
    )
    if len(payload) > 500:
        raise VerificationRefusal("api_response_invalid")
    files: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    outgoing_ids: set[str] = set()
    backlink_ids: set[str] = set()
    graph_edge_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise VerificationRefusal("api_response_invalid")
        file_id = _record_id(item.get("id"))
        note_id = _record_id(item.get("note_id"))
        parse_status = item.get("parse_status")
        file_kind = item.get("file_kind")
        if (
            _record_id(item.get("vault_id")) != vault_id
            or parse_status not in _EVIDENCE_PARSE_STATUSES
            or not isinstance(file_kind, str)
            or _FILE_KIND_PATTERN.fullmatch(file_kind) is None
            or item.get("deleted_state") != "present"
        ):
            raise VerificationRefusal("api_response_invalid")
        relative_path = _canonical_relative(item.get("relative_path"))
        source_hash = _content_hash(item.get("content_hash"))
        files.append(
            {
                "id": file_id,
                "note_id": note_id,
                "relative_locator_sha256": hashlib.sha256(
                    relative_path.encode()
                ).hexdigest(),
                "source_hash": source_hash,
                "file_kind": file_kind,
                "parse_status": parse_status,
                "deleted_state": "present",
            }
        )
        if parse_status != "parsed":
            continue
        page_base = (
            f"/api/deeper-notebook/vaults/{urllib.parse.quote(vault_id, safe=':')}"
            f"/pages/{urllib.parse.quote(note_id, safe=':')}"
        )
        page = _successful_get(inputs, token, page_base, dict)
        if (
            not isinstance(page.get("file"), dict)
            or page["file"].get("id") != file_id
            or not isinstance(page.get("tasks"), list)
            or len(page["tasks"]) > 10_000
        ):
            raise VerificationRefusal("api_response_invalid")
        for task in page["tasks"]:
            if not isinstance(task, dict):
                raise VerificationRefusal("api_response_invalid")
            tasks.append({"id": _record_id(task.get("id"))})
        for suffix, target in (
            ("outgoing", outgoing_ids),
            ("backlinks", backlink_ids),
        ):
            links = _successful_get(inputs, token, f"{page_base}/{suffix}", list)
            if len(links) > 500:
                raise VerificationRefusal("api_response_invalid")
            for link in links:
                if not isinstance(link, dict) or not isinstance(
                    link.get("resolved"), bool
                ):
                    raise VerificationRefusal("api_response_invalid")
                target.add(_record_id(link.get("id")))
        graph_query = urllib.parse.urlencode(
            {"center_note_id": note_id, "depth": 8, "limit": 500}
        )
        graph = _successful_get(
            inputs,
            token,
            f"/api/deeper-notebook/vaults/{urllib.parse.quote(vault_id, safe=':')}"
            f"/graph?{graph_query}",
            dict,
        )
        if (
            not isinstance(graph.get("nodes"), list)
            or not isinstance(graph.get("edges"), list)
            or len(graph["nodes"]) > 500
            or len(graph["edges"]) > 500
        ):
            raise VerificationRefusal("api_response_invalid")
        for node in graph["nodes"]:
            if not isinstance(node, dict):
                raise VerificationRefusal("api_response_invalid")
            _record_id(node.get("id"))
        for edge in graph["edges"]:
            if not isinstance(edge, dict):
                raise VerificationRefusal("api_response_invalid")
            graph_edge_ids.add(_record_id(edge.get("id")))
    return (
        sorted(files, key=lambda item: item["id"]),
        sorted(tasks, key=lambda item: item["id"]),
        outgoing_ids,
        backlink_ids,
        graph_edge_ids,
    )


def _trust_evidence(
    inputs: Inputs,
    token: str,
    parent_id: str,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    base = (
        f"/api/deeper-notebook/vaults/{urllib.parse.quote(parent_id, safe=':')}/trust"
    )
    summary = _successful_get(inputs, token, f"{base}/summary", dict)
    if (
        set(summary) != {"total", "resolved", "unresolved"}
        or any(
            isinstance(summary[key], bool)
            or not isinstance(summary[key], int)
            or summary[key] < 0
            for key in summary
        )
        or summary["total"] != summary["resolved"] + summary["unresolved"]
    ):
        raise VerificationRefusal("api_response_invalid")
    records = _successful_get(inputs, token, f"{base}?limit=500&offset=0", list)
    if len(records) > 500 or len(records) != summary["total"]:
        raise VerificationRefusal("api_response_invalid")
    evidence: list[dict[str, Any]] = []
    for record in records:
        if (
            not isinstance(record, dict)
            or record.get("status") != "approved"
            or record.get("resolution_state") not in {"resolved", "unresolved"}
        ):
            raise VerificationRefusal("api_response_invalid")
        manifest_id = record.get("manifest_id")
        if not isinstance(manifest_id, str) or not manifest_id:
            raise VerificationRefusal("api_response_invalid")
        evidence.append(
            {
                "id": _record_id(record.get("id")),
                "manifest_id_sha256": hashlib.sha256(manifest_id.encode()).hexdigest(),
                "status": "approved",
                "resolution_state": record["resolution_state"],
                "content_hash": _content_hash(record.get("content_hash")),
            }
        )
    return dict(sorted(summary.items())), sorted(evidence, key=lambda item: item["id"])


def _knowledge_evidence(
    inputs: Inputs,
    token: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    documents: list[dict[str, Any]] = []
    search_membership = {
        hashlib.sha256(query.encode()).hexdigest(): [] for query in inputs.exact_queries
    }
    for space_id in inputs.space_ids:
        query = urllib.parse.urlencode(
            {"space_id": space_id, "limit": 500, "offset": 0}
        )
        summaries = _successful_get(
            inputs,
            token,
            f"/api/deeper-notebook/knowledge-engine/documents?{query}",
            list,
        )
        if not summaries or len(summaries) > 500:
            raise VerificationRefusal("api_response_invalid")
        for summary in summaries:
            if not isinstance(summary, dict) or summary.get("space_id") != space_id:
                raise VerificationRefusal("api_response_invalid")
            document_id = _record_id(summary.get("id"))
            relative_locator = _canonical_relative(summary.get("relative_locator"))
            document = {
                "id": document_id,
                "space_id": space_id,
                "relative_locator_sha256": hashlib.sha256(
                    relative_locator.encode()
                ).hexdigest(),
                "source_hash": _content_hash(summary.get("source_hash")),
                "source_revision_id": _record_id(summary.get("source_revision_id")),
                "state": summary.get("state"),
            }
            if not isinstance(document["state"], str) or not document["state"]:
                raise VerificationRefusal("api_response_invalid")
            detail = _successful_get(
                inputs,
                token,
                f"/api/deeper-notebook/knowledge-engine/documents/"
                f"{urllib.parse.quote(document_id, safe=':')}",
                dict,
            )
            if any(
                detail.get(key) != summary.get(key)
                for key in (
                    "id",
                    "space_id",
                    "relative_locator",
                    "source_hash",
                    "source_revision_id",
                )
            ):
                raise VerificationRefusal("api_response_invalid")
            body = detail.get("normalized_body")
            if (
                not isinstance(body, str)
                or len(body.encode("utf-8")) > MAX_RESPONSE_BYTES
            ):
                raise VerificationRefusal("api_response_invalid")
            for exact_query in inputs.exact_queries:
                if exact_query in body:
                    search_membership[
                        hashlib.sha256(exact_query.encode()).hexdigest()
                    ].append(document_id)
            documents.append(document)
    return (
        sorted(documents, key=lambda item: (item["space_id"], item["id"])),
        {key: sorted(values) for key, values in sorted(search_membership.items())},
    )


def _capture_projection_snapshot(
    inputs: Inputs,
    token: str,
    manifest: dict[str, Any],
    parent_id: str,
    child_id: str,
) -> dict[str, Any]:
    expected = manifest["expected"]
    parent_mount = _mount_evidence(
        inputs,
        token,
        vault_id=parent_id,
        expected_name=expected["parent_name"],
        expected_root=manifest["roots"]["parent"],
        expected_parent_id=None,
    )
    child_mount = _mount_evidence(
        inputs,
        token,
        vault_id=child_id,
        expected_name=expected["child_name"],
        expected_root=manifest["roots"]["child"],
        expected_parent_id=parent_id,
    )
    parent = _file_evidence(inputs, token, vault_id=parent_id)
    child = _file_evidence(inputs, token, vault_id=child_id)
    trust_summary, trust_records = _trust_evidence(inputs, token, parent_id)
    documents, search_membership = _knowledge_evidence(inputs, token)
    all_tasks = sorted([*parent[1], *child[1]], key=lambda item: item["id"])
    outgoing_ids = sorted(parent[2] | child[2])
    backlink_ids = sorted(parent[3] | child[3])
    graph_edge_ids = sorted(parent[4] | child[4])
    counts = {
        "parent_files": len(parent[0]),
        "child_files": len(child[0]),
        "tasks": len(all_tasks),
        "outgoing_links": len(outgoing_ids),
        "backlinks": len(backlink_ids),
        "graph_edges": len(graph_edge_ids),
        "trust_records": len(trust_records),
        "knowledge_documents": len(documents),
    }
    minima = {
        "parent_files": expected["minimum_parent_files"],
        "child_files": expected["minimum_child_files"],
        "tasks": expected["minimum_tasks"],
        "graph_edges": expected["minimum_graph_edges"],
        "trust_records": expected["minimum_trust_records"],
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in minima.values()
    ) or any(counts[key] < value for key, value in minima.items()):
        raise VerificationRefusal("api_response_invalid")
    return {
        "mounts": [parent_mount, child_mount],
        "files": sorted([*parent[0], *child[0]], key=lambda item: item["id"]),
        "tasks": all_tasks,
        "outgoing_link_ids": outgoing_ids,
        "backlink_ids": backlink_ids,
        "graph_edge_ids": graph_edge_ids,
        "trust_summary": trust_summary,
        "trust_records": trust_records,
        "knowledge_documents": documents,
        "exact_search_membership": search_membership,
        "counts": counts,
    }


def _overlay_evidence(
    inputs: Inputs,
    token: str,
    overlay_note_id: str,
) -> dict[str, Any]:
    page = _successful_get(
        inputs,
        token,
        "/api/deeper-notebook/overlay/notes/"
        f"{urllib.parse.quote(overlay_note_id, safe=':')}",
        dict,
    )
    overlay = page.get("overlay")
    body = page.get("editable_markdown")
    if (
        not isinstance(overlay, dict)
        or _record_id(overlay.get("id")) != overlay_note_id
        or not isinstance(body, str)
        or len(body.encode("utf-8")) > MAX_RESPONSE_BYTES
    ):
        raise VerificationRefusal("api_response_invalid")
    revision = overlay.get("revision")
    title = overlay.get("title")
    relative_path = _canonical_relative(overlay.get("relative_path"))
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not isinstance(title, str)
        or not title
    ):
        raise VerificationRefusal("api_response_invalid")
    return {
        "id": overlay_note_id,
        "projected_note_id": _record_id(overlay.get("projected_note_id")),
        "revision": revision,
        "title_sha256": hashlib.sha256(title.encode()).hexdigest(),
        "relative_locator_sha256": hashlib.sha256(relative_path.encode()).hexdigest(),
        "content_hash": _content_hash(overlay.get("content_hash")),
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "projection_state": overlay.get("projection_state"),
    }


def _request(inputs: Inputs, token: str, space_id: str) -> tuple[int, Any]:
    query = urllib.parse.urlencode(
        [("space_id", space_id)]
        + [("exact_query", exact_query) for exact_query in inputs.exact_queries]
    )
    return _get(
        inputs,
        token,
        f"/api/deeper-notebook/knowledge-engine/equivalence?{query}",
    )


def _codes(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(
        payload.get("differences"), list
    ):
        raise VerificationRefusal("verification_inventory_invalid")
    codes: list[str] = []
    for difference in payload["differences"]:
        if (
            not isinstance(difference, dict)
            or not isinstance(difference.get("code"), str)
            or difference["code"] not in _KNOWN_MISMATCH_CODES
        ):
            raise VerificationRefusal("verification_inventory_invalid")
        codes.append(difference["code"])
    return sorted(set(codes))


def _write_report(path: Path, report: dict[str, Any]) -> None:
    payload = (
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        parent_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def _scan_vaults(inputs: Inputs, token: str, vault_ids: tuple[str, ...]) -> bool:
    if not vault_ids or len(vault_ids) != len(set(vault_ids)):
        raise VerificationRefusal("synthetic_manifest_invalid")
    for vault_id in vault_ids:
        _record_id(vault_id)
    count_fields = (
        "observed",
        "parsed",
        "unchanged",
        "unsupported",
        "invalid",
        "missing",
    )
    for round_index in range(2):
        for vault_id in vault_ids:
            scan_status, scan = _json_request(
                inputs,
                token,
                "POST",
                f"/api/deeper-notebook/vaults/"
                f"{urllib.parse.quote(vault_id, safe=':')}/scan",
                {},
            )
            if (
                scan_status != 200
                or not isinstance(scan, dict)
                or scan.get("state")
                not in {"ready-read-only", "degraded", "conflict", "unavailable"}
                or any(
                    isinstance(scan.get(field), bool)
                    or not isinstance(scan.get(field), int)
                    or scan[field] < 0
                    for field in count_fields
                )
            ):
                return False
        if round_index == 0:
            time.sleep(SCAN_STABILIZATION_SECONDS)
    return True


def _controlled_prepare(inputs: Inputs, manifest: dict[str, Any], token: str) -> int:
    """Run the narrowly allowlisted synthetic mutations, then require restart."""
    expected = manifest["expected"]
    required = {
        "overlay_note_id",
        "overlay_revision",
        "overlay_title",
        "overlay_markdown",
        "overlay_idempotency_key",
        "parent_vault_id",
        "parent_name",
        "child_name",
        "manifest_relative_path",
        "minimum_parent_files",
        "minimum_child_files",
        "minimum_tasks",
        "minimum_graph_edges",
        "minimum_trust_records",
    }
    integer_fields = {
        "overlay_revision",
        "minimum_parent_files",
        "minimum_child_files",
        "minimum_tasks",
        "minimum_graph_edges",
        "minimum_trust_records",
    }
    if (
        set(expected) != required
        or not all(
            isinstance(expected[key], str)
            for key in required - integer_fields
        )
        or any(
            isinstance(expected[key], bool) or not isinstance(expected[key], int)
            for key in integer_fields
        )
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    relative_manifest = PurePosixPath(expected["manifest_relative_path"])
    if (
        relative_manifest.is_absolute()
        or any(part in {"", ".", ".."} for part in relative_manifest.parts)
        or not re.fullmatch(r"overlay_note:[A-Za-z0-9_-]+", expected["overlay_note_id"])
        or not re.fullmatch(r"vault_mount:[A-Za-z0-9_-]+", expected["parent_vault_id"])
        or not 1 <= expected["overlay_revision"]
        or any(
            not value.strip() or len(value) > 512
            for value in (
                expected["overlay_title"],
                expected["overlay_idempotency_key"],
                expected["parent_name"],
                expected["child_name"],
            )
        )
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")

    def root_evidence() -> dict[str, dict[str, Any]]:
        return {
            name: _synthetic_root_evidence(
                name,
                Path(root),
                manifest["marker"],
            )
            for name, root in manifest["roots"].items()
        }

    before_evidence = root_evidence()
    identity = _proof_identity(inputs, token)
    backfill_before_restart = _wait_for_terminal_backfill(
        inputs,
        token,
        _startup_checkpoint_space_ids(expected["parent_vault_id"]),
    )
    overlay_status, overlay_payload = _json_request(
        inputs,
        token,
        "PUT",
        f"/api/deeper-notebook/overlay/notes/{urllib.parse.quote(expected['overlay_note_id'], safe=':')}",
        {
            "title": expected["overlay_title"],
            "markdown": expected["overlay_markdown"],
            "expected_revision": expected["overlay_revision"],
            "idempotency_key": expected["overlay_idempotency_key"],
        },
    )
    if (
        overlay_status != 200
        or not isinstance(overlay_payload, dict)
        or not isinstance(overlay_payload.get("overlay"), dict)
        or overlay_payload["overlay"].get("id") != expected["overlay_note_id"]
        or overlay_payload["overlay"].get("revision")
        != expected["overlay_revision"] + 1
        or overlay_payload["overlay"].get("title") != expected["overlay_title"]
        or overlay_payload.get("editable_markdown") != expected["overlay_markdown"]
    ):
        return 3
    parent_status, parent = _get(
        inputs,
        token,
        f"/api/deeper-notebook/vaults/{urllib.parse.quote(expected['parent_vault_id'], safe=':')}",
    )
    if (
        parent_status != 200
        or not isinstance(parent, dict)
        or parent.get("id") != expected["parent_vault_id"]
        or parent.get("name") != expected["parent_name"]
        or parent.get("root_path") != manifest["roots"]["parent"]
    ):
        return 3
    parent_id = expected["parent_vault_id"]
    child_status, child = _json_request(
        inputs,
        token,
        "POST",
        "/api/deeper-notebook/vaults",
        {
            "name": expected["child_name"],
            "path": manifest["roots"]["child"],
            "format_mode": "markdown",
            "parent_vault_id": parent_id,
            "watch_enabled": False,
        },
    )
    if (
        child_status != 201
        or not isinstance(child, dict)
        or _RECORD_ID_PATTERN.fullmatch(str(child.get("id") or "")) is None
        or child.get("name") != expected["child_name"]
        or child.get("root_path") != manifest["roots"]["child"]
        or child.get("parent_vault_id") != parent_id
        or child.get("format_mode") != "markdown"
        or child.get("watch_enabled") is not False
    ):
        return 3
    if not _scan_vaults(inputs, token, (parent_id, child["id"])):
        return 3
    trust_path = expected["manifest_relative_path"]
    imports = [
        _json_request(
            inputs,
            token,
            "POST",
            f"/api/deeper-notebook/vaults/{urllib.parse.quote(parent_id, safe=':')}/trust/import",
            {"manifest_relative_path": trust_path},
        )
        for _ in range(2)
    ]
    if any(
        code != 200
        or not isinstance(value, dict)
        or set(value) != {"changed", "unchanged", "resolved", "unresolved"}
        or any(
            isinstance(count, bool) or not isinstance(count, int) or count < 0
            for count in value.values()
        )
        for code, value in imports
    ):
        return 3
    if (
        imports[0][1]["changed"] < 1
        or imports[1][1]["changed"] != 0
        or imports[1][1]["unchanged"] < 1
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    assert inputs.expected_prior_state is not None
    after_evidence = root_evidence()
    projection_snapshot = _capture_projection_snapshot(
        inputs,
        token,
        manifest,
        parent_id,
        child["id"],
    )
    overlay_snapshot = _overlay_evidence(
        inputs,
        token,
        expected["overlay_note_id"],
    )
    _write_report(
        inputs.expected_prior_state,
        {
            "state": "knowledge_engine_restart_required",
            "proof_identity": identity,
            "backfill_before_restart": backfill_before_restart,
            "synthetic_roots": manifest["roots"],
            "parent_vault_id": parent_id,
            "child_vault_id": child["id"],
            "external_before": before_evidence,
            "external_after": after_evidence,
            "projection_snapshot": projection_snapshot,
            "overlay_snapshot": overlay_snapshot,
            "trust_import_replay": {
                "first": imports[0][1],
                "second": imports[1][1],
            },
        },
    )
    return 5


def _controlled_verify(inputs: Inputs, manifest: dict[str, Any], token: str) -> int:
    assert inputs.expected_prior_state is not None
    try:
        prior = json.loads(inputs.expected_prior_state.read_text(encoding="utf-8"))
        prior_identity = prior["proof_identity"]
        if prior.get("state") != "knowledge_engine_restart_required" or not isinstance(
            prior_identity, dict
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise VerificationRefusal("synthetic_manifest_invalid") from None
    current_identity = _proof_identity(inputs, token)
    if (
        current_identity["instance_pid"] == prior_identity.get("instance_pid")
        or current_identity["instance_nonce"] == prior_identity.get("instance_nonce")
        or current_identity["overlay_root_sha256"]
        != prior_identity.get("overlay_root_sha256")
    ):
        return 3
    parent_id = prior.get("parent_vault_id")
    child_id = prior.get("child_vault_id")
    if (
        not isinstance(parent_id, str)
        or not isinstance(child_id, str)
        or _RECORD_ID_PATTERN.fullmatch(parent_id) is None
        or _RECORD_ID_PATTERN.fullmatch(child_id) is None
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    startup_checkpoint_space_ids = _startup_checkpoint_space_ids(parent_id)
    child_space_id = _engine_space_id(child_id)
    restart_checkpoint_space_ids = tuple(
        sorted({*startup_checkpoint_space_ids, child_space_id})
    )
    backfill_after_restart = _wait_for_terminal_backfill(
        inputs,
        token,
        restart_checkpoint_space_ids,
    )
    prior_checkpoints = prior.get("backfill_before_restart")
    if (
        not isinstance(prior_checkpoints, list)
        or {
            item.get("space_id")
            for item in prior_checkpoints
            if isinstance(item, dict)
        }
        != set(startup_checkpoint_space_ids)
        or any(
            not isinstance(item, dict) or item.get("status") != "completed"
            for item in prior_checkpoints
        )
    ):
        raise VerificationRefusal("synthetic_manifest_invalid")
    current_evidence = {
        name: _synthetic_root_evidence(
            name,
            Path(root),
            manifest["marker"],
        )
        for name, root in manifest["roots"].items()
    }
    if current_evidence != prior.get("external_after"):
        return 3
    projection_snapshot = _capture_projection_snapshot(
        inputs,
        token,
        manifest,
        parent_id,
        child_id,
    )
    overlay_snapshot = _overlay_evidence(
        inputs,
        token,
        manifest["expected"]["overlay_note_id"],
    )
    if projection_snapshot != prior.get(
        "projection_snapshot"
    ) or overlay_snapshot != prior.get("overlay_snapshot"):
        return 3
    result = run(inputs)
    if result != 0:
        return result
    try:
        report = json.loads(inputs.report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise VerificationUnavailable("verification_unavailable") from None
    report["controlled_proof"] = {
        "restart_verified": True,
        "prior_instance_pid": prior_identity["instance_pid"],
        "current_instance_pid": current_identity["instance_pid"],
        "projection_sha256": hashlib.sha256(
            json.dumps(
                projection_snapshot,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "overlay_sha256": hashlib.sha256(
            json.dumps(
                overlay_snapshot,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "counts": projection_snapshot["counts"],
        "source_fingerprints_preserved": True,
        "trust_import_idempotent": (
            prior.get("trust_import_replay", {}).get("second", {}).get("changed") == 0
        ),
        "backfill_before_restart": prior_checkpoints,
        "backfill_after_restart": backfill_after_restart,
    }
    _write_report(inputs.report_path, report)
    return 0


def run(inputs: Inputs) -> int:
    token = _read_token(inputs.token_path)
    if inputs.require_shadow_enabled:
        status_code, status_payload = _get(
            inputs, token, "/api/deeper-notebook/knowledge-engine/status"
        )
        if status_code != 200 or not isinstance(status_payload, dict):
            return 3
        if any(
            not isinstance(status_payload.get(field), int)
            for field in ("projected", "unchanged", "failed")
        ):
            return 3
    spaces: list[dict[str, Any]] = []
    for space_id in inputs.space_ids:
        response_status, payload = _request(inputs, token, space_id)
        if response_status in {404, 503}:
            return 3
        if response_status != 200 or not isinstance(payload, dict):
            return 3
        passed = payload.get("passed")
        if not isinstance(passed, bool):
            raise VerificationRefusal("verification_inventory_invalid")
        result: dict[str, Any] = {"space_id": space_id, "passed": passed}
        if not passed:
            result["difference_codes"] = _codes(payload)
        elif _codes(payload):
            raise VerificationRefusal("verification_inventory_invalid")
        spaces.append(result)
    passed = all(space["passed"] for space in spaces)
    _write_report(inputs.report_path, {"passed": passed, "spaces": spaces})
    return 0 if passed else 4


def main() -> int:
    try:
        inputs = _inputs(_parser().parse_args())
        if inputs.proof_phase is not None:
            manifest = _proof_manifest(inputs)
            token = _read_token(inputs.token_path)
            if inputs.proof_phase == "prepare":
                return _controlled_prepare(inputs, manifest, token)
            return _controlled_verify(inputs, manifest, token)
        return run(inputs)
    except VerificationRefusal as error:
        print(str(error), file=sys.stderr)
        return 2
    except VerificationUnavailable:
        print("verification_unavailable", file=sys.stderr)
        return 3
    except OSError:
        print("verification_unavailable", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
