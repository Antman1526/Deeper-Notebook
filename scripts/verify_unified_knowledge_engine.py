#!/usr/bin/env python3
"""Read-only verifier for server-owned legacy/unified projection equivalence."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 1024 * 1024
_SPACE_ID_PATTERN = re.compile(r"^knowledge_engine_space:[A-Za-z0-9_-]+$")
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


@dataclass(frozen=True, slots=True)
class Inputs:
    api_url: str
    token_path: Path
    report_path: Path
    space_ids: tuple[str, ...]
    exact_queries: tuple[str, ...]
    require_shadow_enabled: bool


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify unified projection equivalence")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--auth-token-file", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--space-id", action="append", default=[])
    parser.add_argument("--exact-query", action="append", default=[])
    parser.add_argument("--require-shadow-enabled", action="store_true")
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
            not isinstance(value, str)
            or _SPACE_ID_PATTERN.fullmatch(value) is None
            for value in space_ids
        )
        or not 1 <= len(exact_queries) <= 32
        or any(not query.strip() or len(query) > 256 for query in exact_queries)
    ):
        raise VerificationRefusal("verification_inventory_invalid")
    token_path = _validate_token_path(namespace.auth_token_file)
    report_path = _validate_report_path(namespace.report_path, token_path)
    return Inputs(
        api_url=_validate_api_url(namespace.api_url),
        token_path=token_path,
        report_path=report_path,
        space_ids=space_ids,
        exact_queries=exact_queries,
        require_shadow_enabled=bool(namespace.require_shadow_enabled),
    )


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
    if not isinstance(payload, dict) or not isinstance(payload.get("differences"), list):
        raise VerificationRefusal("verification_inventory_invalid")
    codes: list[str] = []
    for difference in payload["differences"]:
        if not isinstance(difference, dict) or not isinstance(
            difference.get("code"), str
        ) or difference["code"] not in _KNOWN_MISMATCH_CODES:
            raise VerificationRefusal("verification_inventory_invalid")
        codes.append(difference["code"])
    return sorted(set(codes))


def _write_report(path: Path, report: dict[str, Any]) -> None:
    payload = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
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
