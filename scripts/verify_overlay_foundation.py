#!/usr/bin/env python3
"""Fail-closed proof runner for the app-owned overlay boundary.

The default invocation is a read-only configuration check. Controlled API
mutation is available only with ``--run-controlled-proof`` and only beneath
an explicitly marked, verifier-owned disposable root in the system temp
directory. A successful first phase records a strict, path-free restart state
inside that exact root. Re-running the same command after an external,
owned-process restart performs the read-only persistence phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

OVERLAY_PARENT_MARKER = ".deeper-notebook-overlay-proof-parent"
OVERLAY_PARENT_MARKER_VALUE = "disposable-overlay-proof-parent-v1"
EXTERNAL_MARKER = ".deeper-notebook-overlay-external-fixture"
EXTERNAL_MARKER_VALUE = "synthetic-read-only-external-fixture-v1"
REQUEST_ID_HEADER = "X-Request-ID"
RESTART_STATE_FILE = ".deeper-notebook-overlay-proof-state.json"
RESTART_STATE_VERSION = 1
MAX_RESTART_STATE_BYTES = 128 * 1024
MAX_EXTERNAL_FILES = 1_000
MAX_EXTERNAL_BYTES = 32 * 1024 * 1024


class ProofRefusal(RuntimeError):
    """A stable, non-secret refusal reason."""


@dataclass(frozen=True)
class Inputs:
    api_url: str
    auth_token_file: Path
    overlay_root: Path
    external_root: Path
    report_path: Path
    run_controlled_proof: bool


@dataclass
class HttpResult:
    status: int
    payload: Any
    headers: dict[str, str]


@dataclass(frozen=True)
class InstanceIdentity:
    nonce: str
    nonce_digest: str
    overlay_root_sha256: str
    pid: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Deeper Notebook overlay isolation",
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--auth-token-file", required=True, type=Path)
    parser.add_argument("--overlay-data-root", required=True, type=Path)
    parser.add_argument("--external-fixture-root", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run-controlled-proof", action="store_true")
    return parser


def _inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_symlink_components(path: Path, stop: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise ProofRefusal("refused_root: symlink component")
        if current == stop:
            return
        if current.parent == current or not _inside(current, stop):
            raise ProofRefusal("refused_root: outside disposable temp root")
        current = current.parent


def _validate_marked_root(
    raw_path: Path,
    marker_name: str,
    marker_value: str,
) -> Path:
    forbidden_exact = {
        Path("/"),
        Path("/Users"),
        Path.home(),
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Desktop" / "2nd Brains",
    }
    forbidden_descendants = {
        Path("/Users"),
        Path.home() / "Desktop",
        Path.home() / "Documents",
    }
    absolute = raw_path.absolute()
    if absolute in forbidden_exact or any(
        _inside(absolute, root) for root in forbidden_descendants
    ):
        raise ProofRefusal("refused_root: broad or private root")
    if not absolute.exists() or not absolute.is_dir():
        raise ProofRefusal("refused_root: root must be an existing directory")

    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved = absolute.resolve(strict=True)
    if not _inside(resolved, temp_root) or resolved == temp_root:
        raise ProofRefusal("refused_root: outside disposable temp root")
    _reject_symlink_components(absolute, temp_root)
    if resolved != absolute.resolve():
        raise ProofRefusal("refused_root: ambiguous resolution")
    if resolved.stat().st_uid != os.getuid():
        raise ProofRefusal("refused_root: root is not owned by this user")

    marker = resolved / marker_name
    if marker.is_symlink() or not marker.is_file():
        raise ProofRefusal("refused_root: ownership marker missing")
    if marker.read_text(encoding="utf-8").strip() != marker_value:
        raise ProofRefusal("refused_root: ownership marker invalid")
    return resolved


def _validate_token_file(raw_path: Path) -> Path:
    absolute = raw_path.absolute()
    if absolute.is_symlink() or not absolute.is_file():
        raise ProofRefusal("auth_token_file_invalid")
    info = absolute.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ProofRefusal("auth_token_file_invalid")
    if info.st_size < 1 or info.st_size > 4_096:
        raise ProofRefusal("auth_token_file_invalid")
    return absolute


def _validate_report_path(raw_path: Path, temp_root: Path) -> Path:
    absolute = raw_path.absolute()
    if absolute.exists() and (absolute.is_symlink() or not absolute.is_file()):
        raise ProofRefusal("report_path_invalid")
    parent = absolute.parent
    if not parent.exists() or parent.is_symlink():
        raise ProofRefusal("report_path_invalid")
    resolved_parent = parent.resolve(strict=True)
    if not _inside(resolved_parent, temp_root) or resolved_parent == temp_root:
        raise ProofRefusal("report_path_invalid")
    _reject_symlink_components(parent, temp_root)
    return absolute


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
        raise ProofRefusal("api_url_must_be_explicit_loopback_http")
    return value.rstrip("/")


def _inputs(namespace: argparse.Namespace) -> Inputs:
    overlay_root = _validate_marked_root(
        namespace.overlay_data_root,
        OVERLAY_PARENT_MARKER,
        OVERLAY_PARENT_MARKER_VALUE,
    )
    external_root = _validate_marked_root(
        namespace.external_fixture_root,
        EXTERNAL_MARKER,
        EXTERNAL_MARKER_VALUE,
    )
    temp_root = Path(tempfile.gettempdir()).resolve()
    report_path = _validate_report_path(namespace.report_path, temp_root)
    if _inside(report_path, external_root):
        raise ProofRefusal("report_path_invalid")
    return Inputs(
        api_url=_validate_api_url(namespace.api_url),
        auth_token_file=_validate_token_file(namespace.auth_token_file),
        overlay_root=overlay_root,
        external_root=external_root,
        report_path=report_path,
        run_controlled_proof=bool(namespace.run_controlled_proof),
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _external_fingerprints(root: Path) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    total_bytes = 0
    for candidate in sorted(root.rglob("*")):
        if candidate.is_symlink():
            raise ProofRefusal("external_fixture_contains_symlink")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ProofRefusal("external_fixture_contains_special_file")
        relative = candidate.relative_to(root).as_posix()
        if relative == EXTERNAL_MARKER:
            continue
        if len(fingerprints) >= MAX_EXTERNAL_FILES:
            raise ProofRefusal("external_fixture_too_large")
        data = candidate.read_bytes()
        total_bytes += len(data)
        if total_bytes > MAX_EXTERNAL_BYTES:
            raise ProofRefusal("external_fixture_too_large")
        fingerprints[relative] = _sha256_bytes(data)
    return fingerprints


def _git_status_digest(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        text=False,
        capture_output=True,
        check=False,
    )
    payload = result.stdout if result.returncode == 0 else b"not-a-git-worktree"
    return _sha256_bytes(payload)


def _read_token(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\x00" in token or "\n" in token or "\r" in token:
        raise ProofRefusal("auth_token_file_invalid")
    return token


def _request(
    inputs: Inputs,
    token: str,
    method: str,
    path: str,
    request_id: str,
    body: dict[str, Any] | None = None,
) -> HttpResult:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        REQUEST_ID_HEADER: request_id,
    }
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{inputs.api_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read(MAX_EXTERNAL_BYTES + 1)
    if len(raw) > MAX_EXTERNAL_BYTES:
        raise ProofRefusal("api_response_too_large")
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise ProofRefusal("api_response_not_json") from exc
    return HttpResult(
        status=int(response.status),
        payload=payload,
        headers={key.lower(): value for key, value in response.headers.items()},
    )


def _route_audit(openapi: Any) -> dict[str, Any]:
    unsafe: list[str] = []
    routes: list[str] = []
    paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}
    for path, methods in sorted(paths.items()):
        if not isinstance(path, str) or not isinstance(methods, dict):
            continue
        for method in sorted(methods):
            lowered = method.lower()
            if lowered not in {"get", "head", "post", "put", "patch", "delete"}:
                continue
            label = f"{lowered.upper()} {path}"
            if "/vaults" in path:
                routes.append(label)
                if lowered in {"put", "patch", "delete"}:
                    unsafe.append(label)
    return {"vault_routes": routes, "unsafe_vault_routes": unsafe}


def _relative_overlay_summary(page: Any) -> dict[str, Any]:
    overlay = page.get("overlay", {}) if isinstance(page, dict) else {}
    return {
        "id": overlay.get("id"),
        "relative_path": overlay.get("relative_path"),
        "revision": overlay.get("revision"),
        "content_hash": overlay.get("content_hash"),
    }


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _stable_blocker(exc: Exception, fallback: str) -> str:
    if isinstance(exc, ProofRefusal) and exc.args:
        return str(exc.args[0])
    return fallback


def _restart_state_path(inputs: Inputs) -> Path:
    return inputs.overlay_root / RESTART_STATE_FILE


def _validate_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProofRefusal("restart_state_invalid")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ProofRefusal("restart_state_invalid")
    return value


def _strict_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "id",
        "relative_path",
        "revision",
        "content_hash",
    }:
        raise ProofRefusal("restart_state_invalid")
    note_id = value["id"]
    revision = value["revision"]
    if (
        not isinstance(note_id, str)
        or not note_id.startswith("overlay_note:")
        or len(note_id) > 128
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not _is_sha256(value["content_hash"])
    ):
        raise ProofRefusal("restart_state_invalid")
    return {
        "id": note_id,
        "relative_path": _validate_relative_path(value["relative_path"]),
        "revision": revision,
        "content_hash": value["content_hash"],
    }


def _source_from_page(page: Any) -> dict[str, Any]:
    return _strict_source(_relative_overlay_summary(page))


def _validate_restart_state(payload: Any) -> dict[str, Any]:
    expected_keys = {
        "version",
        "phase",
        "previous_instance_nonce_sha256",
        "previous_instance_pid",
        "overlay_root_sha256",
        "external_fingerprints",
        "external_git_status",
        "expected_pages",
        "request_ids",
        "completed_instance_nonce_sha256",
        "completed_instance_pid",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ProofRefusal("restart_state_invalid")
    if payload["version"] != RESTART_STATE_VERSION:
        raise ProofRefusal("restart_state_invalid")
    if payload["phase"] not in {"awaiting_restart", "complete"}:
        raise ProofRefusal("restart_state_invalid")
    if (
        not _is_sha256(payload["previous_instance_nonce_sha256"])
        or not _is_sha256(payload["overlay_root_sha256"])
        or not _is_sha256(payload["external_git_status"])
        or isinstance(payload["previous_instance_pid"], bool)
        or not isinstance(payload["previous_instance_pid"], int)
        or payload["previous_instance_pid"] <= 1
    ):
        raise ProofRefusal("restart_state_invalid")

    fingerprints = payload["external_fingerprints"]
    if not isinstance(fingerprints, dict) or len(fingerprints) > MAX_EXTERNAL_FILES:
        raise ProofRefusal("restart_state_invalid")
    normalized_fingerprints: dict[str, str] = {}
    for relative, digest in fingerprints.items():
        normalized_fingerprints[_validate_relative_path(relative)] = digest
        if not _is_sha256(digest):
            raise ProofRefusal("restart_state_invalid")

    raw_pages = payload["expected_pages"]
    if not isinstance(raw_pages, list) or not raw_pages or len(raw_pages) > 16:
        raise ProofRefusal("restart_state_invalid")
    expected_pages = [_strict_source(page) for page in raw_pages]
    if len({page["id"] for page in expected_pages}) != len(expected_pages):
        raise ProofRefusal("restart_state_invalid")

    raw_request_ids = payload["request_ids"]
    if not isinstance(raw_request_ids, list) or len(raw_request_ids) > 64:
        raise ProofRefusal("restart_state_invalid")
    request_ids: list[str] = []
    for request_id in raw_request_ids:
        if (
            not isinstance(request_id, str)
            or not request_id
            or len(request_id) > 128
            or not all(
                character.isascii() and (character.isalnum() or character in {"-", "_"})
                for character in request_id
            )
        ):
            raise ProofRefusal("restart_state_invalid")
        request_ids.append(request_id)

    completed_nonce = payload["completed_instance_nonce_sha256"]
    completed_pid = payload["completed_instance_pid"]
    if payload["phase"] == "awaiting_restart":
        if completed_nonce is not None or completed_pid is not None:
            raise ProofRefusal("restart_state_invalid")
    elif (
        not _is_sha256(completed_nonce)
        or isinstance(completed_pid, bool)
        or not isinstance(completed_pid, int)
        or completed_pid <= 1
    ):
        raise ProofRefusal("restart_state_invalid")

    return {
        **payload,
        "external_fingerprints": normalized_fingerprints,
        "expected_pages": expected_pages,
        "request_ids": request_ids,
    }


def _read_restart_state(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProofRefusal("restart_state_invalid")
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_size < 2
        or info.st_size > MAX_RESTART_STATE_BYTES
    ):
        raise ProofRefusal("restart_state_invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofRefusal("restart_state_invalid") from exc
    return _validate_restart_state(payload)


def _write_restart_state(path: Path, payload: dict[str, Any]) -> None:
    normalized = _validate_restart_state(payload)
    encoded = (
        json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_RESTART_STATE_BYTES:
        raise ProofRefusal("restart_state_invalid")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProofRefusal("restart_state_invalid")
    if path.exists():
        info = path.stat()
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise ProofRefusal("restart_state_invalid")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _get_identity(
    inputs: Inputs,
    token: str,
    request_id: str,
    expected_root_digest: str,
) -> InstanceIdentity:
    result = _request(
        inputs,
        token,
        "GET",
        "/api/deeper-notebook/overlay/proof-identity",
        request_id,
    )
    if result.status != 200:
        raise ProofRefusal("api_identity_unavailable")
    payload = result.payload if isinstance(result.payload, dict) else {}
    nonce = payload.get("instance_nonce")
    reported_root_digest = payload.get("overlay_root_sha256")
    reported_pid = payload.get("instance_pid")
    if not isinstance(nonce, str) or not nonce:
        raise ProofRefusal("instance_nonce_missing")
    if len(nonce) < 43 or len(nonce) > 128:
        raise ProofRefusal("instance_nonce_invalid")
    if not _is_sha256(reported_root_digest):
        raise ProofRefusal("overlay_root_identity_missing")
    if not secrets.compare_digest(reported_root_digest, expected_root_digest):
        raise ProofRefusal("overlay_root_identity_mismatch")
    if (
        isinstance(reported_pid, bool)
        or not isinstance(reported_pid, int)
        or reported_pid <= 1
    ):
        raise ProofRefusal("instance_pid_missing")
    try:
        os.kill(reported_pid, 0)
    except OSError as exc:
        raise ProofRefusal("instance_pid_not_alive") from exc
    return InstanceIdentity(
        nonce=nonce,
        nonce_digest=_sha256_bytes(nonce.encode("utf-8")),
        overlay_root_sha256=reported_root_digest,
        pid=reported_pid,
    )


def _require_same_identity(
    before: InstanceIdentity,
    after: InstanceIdentity,
) -> None:
    if (
        not secrets.compare_digest(before.nonce, after.nonce)
        or before.pid != after.pid
        or not secrets.compare_digest(
            before.overlay_root_sha256,
            after.overlay_root_sha256,
        )
    ):
        raise ProofRefusal("api_instance_changed_during_proof")


def _report(
    inputs: Inputs,
    *,
    outcome: str,
    blocker: str,
    session_id: str,
    identity_nonce_digest: str,
    overlay_root_digest: str,
    external_before: dict[str, str],
    external_after: dict[str, str],
    git_before: str,
    git_after: str,
    route_audit: dict[str, Any] | None = None,
    request_ids: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    states: dict[str, str] | None = None,
) -> None:
    lines = [
        "# Controlled Overlay Foundation Proof",
        "",
        f"- controlled proof: {outcome}",
        f"- blocker: `{blocker}`",
        f"- verifier session: `{session_id}`",
        f"- pinned API nonce SHA-256: `{identity_nonce_digest}`",
        f"- exact overlay root SHA-256: `{overlay_root_digest}`",
        "- external fixture root: `synthetic-external-fixture`",
        f"- external Git-status digest before: `{git_before}`",
        f"- external Git-status digest after: `{git_after}`",
        "",
        "## External fingerprints",
        "",
    ]
    for relative in sorted(set(external_before) | set(external_after)):
        lines.append(
            f"- `{relative}`: before `{external_before.get(relative, 'missing')}`; "
            f"after `{external_after.get(relative, 'missing')}`"
        )
    lines.extend(["", "## Route audit", ""])
    audit = route_audit or {"vault_routes": [], "unsafe_vault_routes": []}
    lines.append(f"- observed vault routes: `{json.dumps(audit['vault_routes'])}`")
    lines.append(f"- unsafe vault routes: `{json.dumps(audit['unsafe_vault_routes'])}`")
    lines.extend(["", "## Overlay sources", ""])
    for source in sources or []:
        lines.append(
            "- `{relative_path}` revision `{revision}` hash `{content_hash}`".format(
                **source
            )
        )
    lines.extend(["", "## Request IDs", ""])
    for request_id in request_ids or []:
        lines.append(f"- `{request_id}`")
    lines.extend(["", "## Proof states", ""])
    for name, state in sorted((states or {}).items()):
        lines.append(f"- {name}: `{state}`")
    lines.extend(
        [
            "",
            "The report intentionally excludes note contents, authentication "
            "tokens, and absolute private-vault paths.",
            "",
        ]
    )
    inputs.report_path.write_text("\n".join(lines), encoding="utf-8")


def _prepare_restart_proof(
    inputs: Inputs,
    token: str,
    session_id: str,
    root_digest: str,
) -> int:
    external_before = _external_fingerprints(inputs.external_root)
    git_before = _git_status_digest(inputs.external_root)
    request_ids: list[str] = []
    sources: list[dict[str, Any]] = []
    audit = {"vault_routes": [], "unsafe_vault_routes": []}
    identity: InstanceIdentity | None = None

    identity_request = f"overlay-proof-{session_id}-identity-before"
    request_ids.append(identity_request)
    try:
        identity = _get_identity(
            inputs,
            token,
            identity_request,
            root_digest,
        )
    except Exception as exc:
        external_after = _external_fingerprints(inputs.external_root)
        git_after = _git_status_digest(inputs.external_root)
        _report(
            inputs,
            outcome="BLOCKED",
            blocker=_stable_blocker(exc, "api_identity_unreachable"),
            session_id=session_id,
            identity_nonce_digest="unavailable",
            overlay_root_digest=root_digest,
            external_before=external_before,
            external_after=external_after,
            git_before=git_before,
            git_after=git_after,
            request_ids=request_ids,
            states={
                "api_instance_identity": "blocked",
                "native_restart": "open",
            },
        )
        return 3

    operation_state = "passed"
    blocker = "native_restart_requires_external_restart"
    expected_pages: dict[str, dict[str, Any]] = {}
    try:
        openapi_id = f"overlay-proof-{session_id}-openapi"
        openapi = _request(
            inputs,
            token,
            "GET",
            "/openapi.json",
            openapi_id,
        )
        request_ids.append(openapi_id)
        if openapi.status != 200:
            raise ProofRefusal("openapi_route_audit_failed")
        audit = _route_audit(openapi.payload)
        if audit["unsafe_vault_routes"]:
            raise ProofRefusal("unsafe_external_vault_mutation_route")

        today = date.today().isoformat()
        daily_ids: list[str] = []
        for attempt in (1, 2):
            request_id = f"overlay-proof-{session_id}-daily-{attempt}"
            result = _request(
                inputs,
                token,
                "PUT",
                f"/api/deeper-notebook/overlay/daily/{today}",
                request_id,
            )
            request_ids.append(request_id)
            if result.status != 200:
                raise ProofRefusal("daily_create_failed")
            source = _source_from_page(result.payload)
            sources.append(source)
            expected_pages[source["id"]] = source
            daily_ids.append(source["id"])
        if daily_ids[0] != daily_ids[1]:
            raise ProofRefusal("daily_replay_not_idempotent")

        unique_pages: list[Any] = []
        for attempt in (1, 2):
            request_id = f"overlay-proof-{session_id}-unique-{attempt}"
            result = _request(
                inputs,
                token,
                "POST",
                "/api/deeper-notebook/overlay/notes/unique",
                request_id,
                {
                    "title": "Controlled Proof",
                    "idempotency_key": request_id,
                },
            )
            request_ids.append(request_id)
            if result.status != 201:
                raise ProofRefusal("unique_create_failed")
            source = _source_from_page(result.payload)
            unique_pages.append(result.payload)
            sources.append(source)
            expected_pages[source["id"]] = source
        if not sources[-1]["relative_path"].endswith("-2.md"):
            raise ProofRefusal("unique_collision_suffix_missing")

        first_unique = unique_pages[0].get("overlay", {})
        if not isinstance(first_unique, dict):
            raise ProofRefusal("unique_create_failed")
        update_id = f"overlay-proof-{session_id}-update"
        updated = _request(
            inputs,
            token,
            "PUT",
            f"/api/deeper-notebook/overlay/notes/{urllib.parse.quote(str(first_unique.get('id', '')), safe='')}",
            update_id,
            {
                "title": "Controlled Proof",
                "markdown": "# Controlled Proof\n\nVerifier-owned draft\n",
                "expected_revision": first_unique.get("revision"),
                "idempotency_key": update_id,
            },
        )
        request_ids.append(update_id)
        if updated.status != 200:
            raise ProofRefusal("overlay_update_failed")
        updated_source = _source_from_page(updated.payload)
        sources.append(updated_source)
        expected_pages[updated_source["id"]] = updated_source

        stale_id = f"overlay-proof-{session_id}-stale"
        stale = _request(
            inputs,
            token,
            "PUT",
            f"/api/deeper-notebook/overlay/notes/{urllib.parse.quote(str(first_unique.get('id', '')), safe='')}",
            stale_id,
            {
                "title": "Controlled Proof",
                "markdown": "# Controlled Proof\n\nStale verifier draft\n",
                "expected_revision": first_unique.get("revision"),
                "idempotency_key": stale_id,
            },
        )
        request_ids.append(stale_id)
        if stale.status != 409:
            raise ProofRefusal("stale_revision_not_rejected")
    except Exception as exc:
        operation_state = "failed"
        blocker = _stable_blocker(exc, "controlled_api_operation_failed")

    after_identity_id = f"overlay-proof-{session_id}-identity-after"
    request_ids.append(after_identity_id)
    try:
        after_identity = _get_identity(
            inputs,
            token,
            after_identity_id,
            root_digest,
        )
        _require_same_identity(identity, after_identity)
    except Exception as exc:
        operation_state = "failed"
        blocker = _stable_blocker(exc, "api_identity_unreachable")

    external_after = _external_fingerprints(inputs.external_root)
    git_after = _git_status_digest(inputs.external_root)
    if external_before != external_after or git_before != git_after:
        operation_state = "failed"
        blocker = "external_fixture_changed"

    if operation_state == "passed":
        state = {
            "version": RESTART_STATE_VERSION,
            "phase": "awaiting_restart",
            "previous_instance_nonce_sha256": identity.nonce_digest,
            "previous_instance_pid": identity.pid,
            "overlay_root_sha256": root_digest,
            "external_fingerprints": external_before,
            "external_git_status": git_before,
            "expected_pages": list(expected_pages.values()),
            "request_ids": request_ids,
            "completed_instance_nonce_sha256": None,
            "completed_instance_pid": None,
        }
        try:
            _write_restart_state(_restart_state_path(inputs), state)
        except Exception as exc:
            operation_state = "failed"
            blocker = _stable_blocker(exc, "restart_state_write_failed")

    _report(
        inputs,
        outcome="BLOCKED" if operation_state == "passed" else "FAILED",
        blocker=blocker,
        session_id=session_id,
        identity_nonce_digest=identity.nonce_digest,
        overlay_root_digest=root_digest,
        external_before=external_before,
        external_after=external_after,
        git_before=git_before,
        git_after=git_after,
        route_audit=audit,
        request_ids=request_ids,
        sources=sources,
        states={
            "api_instance_identity": (
                "passed" if operation_state == "passed" else "failed"
            ),
            "controlled_overlay_operations": operation_state,
            "external_fingerprints": (
                "passed" if external_before == external_after else "failed"
            ),
            "external_git_status": "passed" if git_before == git_after else "failed",
            "native_restart": "pending" if operation_state == "passed" else "open",
        },
    )
    return 4 if operation_state == "passed" else 5


def _resume_restart_proof(
    inputs: Inputs,
    token: str,
    session_id: str,
    root_digest: str,
    state: dict[str, Any],
) -> int:
    if state["phase"] == "complete":
        raise ProofRefusal("restart_proof_already_complete")
    if not secrets.compare_digest(state["overlay_root_sha256"], root_digest):
        raise ProofRefusal("restart_state_root_mismatch")

    external_before = state["external_fingerprints"]
    git_before = state["external_git_status"]
    current_external = _external_fingerprints(inputs.external_root)
    current_git = _git_status_digest(inputs.external_root)
    request_ids = list(state["request_ids"])
    sources = list(state["expected_pages"])
    blocker = ""
    resume_state = "passed"
    identity: InstanceIdentity | None = None

    if current_external != external_before or current_git != git_before:
        blocker = "external_fixture_changed_before_restart_resume"
        resume_state = "failed"
    else:
        identity_id = f"overlay-proof-{session_id}-restart-identity-before"
        request_ids.append(identity_id)
        try:
            identity = _get_identity(
                inputs,
                token,
                identity_id,
                root_digest,
            )
            if secrets.compare_digest(
                identity.nonce_digest,
                state["previous_instance_nonce_sha256"],
            ):
                raise ProofRefusal("native_restart_nonce_unchanged")
            if identity.pid == state["previous_instance_pid"]:
                raise ProofRefusal("native_restart_pid_unchanged")
        except Exception as exc:
            blocker = _stable_blocker(exc, "api_identity_unreachable")
            resume_state = "blocked"

    if resume_state == "passed" and identity is not None:
        try:
            for index, expected in enumerate(state["expected_pages"], start=1):
                request_id = f"overlay-proof-{session_id}-restart-read-{index}"
                request_ids.append(request_id)
                result = _request(
                    inputs,
                    token,
                    "GET",
                    f"/api/deeper-notebook/overlay/notes/{urllib.parse.quote(expected['id'], safe='')}",
                    request_id,
                )
                if result.status != 200:
                    raise ProofRefusal("restart_overlay_note_missing")
                if _source_from_page(result.payload) != expected:
                    raise ProofRefusal("restart_overlay_note_mismatch")
        except Exception as exc:
            blocker = _stable_blocker(exc, "restart_persistence_check_failed")
            resume_state = "failed"

        after_identity_id = f"overlay-proof-{session_id}-restart-identity-after"
        request_ids.append(after_identity_id)
        try:
            after_identity = _get_identity(
                inputs,
                token,
                after_identity_id,
                root_digest,
            )
            _require_same_identity(identity, after_identity)
        except Exception as exc:
            blocker = _stable_blocker(exc, "api_identity_unreachable")
            resume_state = "failed"

    external_after = _external_fingerprints(inputs.external_root)
    git_after = _git_status_digest(inputs.external_root)
    if external_after != external_before or git_after != git_before:
        blocker = "external_fixture_changed"
        resume_state = "failed"

    if resume_state == "passed" and identity is not None:
        completed_state = {
            **state,
            "phase": "complete",
            "completed_instance_nonce_sha256": identity.nonce_digest,
            "completed_instance_pid": identity.pid,
            "request_ids": request_ids,
        }
        try:
            _write_restart_state(_restart_state_path(inputs), completed_state)
        except Exception as exc:
            blocker = _stable_blocker(exc, "restart_state_write_failed")
            resume_state = "failed"

    _report(
        inputs,
        outcome=(
            "PASSED"
            if resume_state == "passed"
            else "BLOCKED"
            if resume_state == "blocked"
            else "FAILED"
        ),
        blocker=blocker or "none",
        session_id=session_id,
        identity_nonce_digest=(
            identity.nonce_digest if identity is not None else "unavailable"
        ),
        overlay_root_digest=root_digest,
        external_before=external_before,
        external_after=external_after,
        git_before=git_before,
        git_after=git_after,
        request_ids=request_ids,
        sources=sources,
        states={
            "api_instance_identity": (
                "passed" if identity is not None else resume_state
            ),
            "controlled_overlay_operations": "passed",
            "external_fingerprints": (
                "passed" if external_before == external_after else "failed"
            ),
            "external_git_status": "passed" if git_before == git_after else "failed",
            "native_restart": resume_state,
            "restart_persistence": resume_state,
        },
    )
    if resume_state == "passed":
        return 0
    return 3 if resume_state == "blocked" else 5


def _controlled_proof(inputs: Inputs) -> int:
    token = _read_token(inputs.auth_token_file)
    session_id = _sha256_bytes(secrets.token_bytes(32))[:12]
    root_digest = _sha256_bytes(str(inputs.overlay_root).encode("utf-8"))
    state_path = _restart_state_path(inputs)
    if state_path.is_symlink() or state_path.exists():
        state = _read_restart_state(state_path)
        return _resume_restart_proof(
            inputs,
            token,
            session_id,
            root_digest,
            state,
        )
    return _prepare_restart_proof(
        inputs,
        token,
        session_id,
        root_digest,
    )


def main(argv: list[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    try:
        inputs = _inputs(namespace)
        if not inputs.run_controlled_proof:
            print(
                "CHECK ONLY: arguments and disposable ownership markers are valid; "
                "no network request or filesystem mutation was performed."
            )
            return 0
        return _controlled_proof(inputs)
    except ProofRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("verification_internal_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
