#!/usr/bin/env python3
"""Two-phase, fail-closed Study Workbench release proof.

The verifier owns a disposable task root, a disjoint read-only sentinel, and
explicit loopback listeners.  ``prepare`` runs the real HTTP source/Study
boundaries and records durable restart state before returning 5.  An operator
or CI runner must start a new stack and invoke ``verify``; the second phase
checks process identity, persisted source/study receipts, and exact cleanup.

The small :func:`run_verifier_fixture` helper is used by the unit suite.  It
uses the same HTTP workflow against a local deterministic fixture server and
never changes product code or a user data root.  Production invocations never
select this fixture path.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import hashlib
import http.server
import json
import os
import pwd
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

TASK_MARKER = ".deeper-notebook-study-proof-root"
TASK_MARKER_VALUE = "study-workbench-proof-root-v1"
EXTERNAL_MARKER = ".deeper-notebook-study-external-sentinel"
EXTERNAL_MARKER_VALUE = "study-workbench-external-sentinel-v1"
REPORT_MARKER = ".deeper-notebook-study-proof-report"
REPORT_MARKER_VALUE = "study-workbench-proof-report-v1"
RECEIPT_NAME = ".study-workbench-restart.json"
MAX_RECEIPT_BYTES = 256 * 1024
MAX_TREE_FILES = 512
MAX_TREE_BYTES = 64 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_SAFE_NAMESPACE = re.compile(r"^study_ns_[a-z0-9_-]{3,64}$")
_SAFE_DATABASE = re.compile(r"^study_db_[a-z0-9_-]{3,64}$")
_WORKFLOW_STAGE_CODES = frozenset(
    {
        "phase_start",
        "receipt_validation",
        "receipt_read_call",
        "receipt_read_done",
        "receipt_loaded",
        "receipt_validated",
        "external_hash_check",
        "source_hash_check",
        "previous_process_check",
        "prior_identity",
        "new_stack_start",
        "restart_workflow",
        "restart_finalization",
        "stack_start",
        "api_ready",
        "auth_status",
        "credential_status",
        "credential_seed",
        "source_upload",
        "source_processing",
        "source_evidence",
        "plan_lifecycle",
        "syllabus_lifecycle",
        "artifact_generation",
        "assistant_invocation",
        "card_lifecycle",
        "progress_projection",
        "anki_export_response",
        "anki_download",
        "anki_download_response",
        "anki_multipart",
        "anki_import_preview",
        "anki_import_status",
        "anki_publish",
        "restart_reads",
        "frontend_route",
    }
)


def _internal_blocker(stage: object) -> str:
    """Return a bounded diagnostic code without exposing exception payloads."""
    code = stage if isinstance(stage, str) and stage in _WORKFLOW_STAGE_CODES else "unknown"
    return f"verification_internal_error:{code}"


def _frontend_request_headers() -> dict[str, str]:
    """Return the exact local setup-completion cookie for the UI request."""
    return {"Cookie": "wizard_completed=1"}


def _task_surreal_password(inputs: Inputs) -> str:
    """Derive a stable disposable DB bootstrap password across restart phases."""
    material = (
        f"study-workbench-surreal:{inputs.task_root.resolve()}:{inputs.namespace}:"
        f"{inputs.database}"
    ).encode()
    return _sha256_bytes(material)[:32]


class ProofRefusal(RuntimeError):
    """Stable, sanitized refusal code for an unsafe or incomplete proof."""


@dataclass(frozen=True)
class ProcessIdentity:
    role: str
    pid: int
    start_token: str
    argv_sha256: str
    listener_port: int | None = None


@dataclass(frozen=True)
class RestartReceipt:
    version: int
    phase: str
    task_root_sha256: str
    namespace: str
    database: str
    previous_api_pid: int
    previous_api_start_token: str
    previous_api_argv_sha256: str
    previous_listener_port: int
    source_hashes: dict[str, str]
    external_hashes: dict[str, str]
    external_writes: int
    previous_processes: tuple[ProcessIdentity, ...] = ()
    source_ids: tuple[str, ...] = ()
    plan_id: str | None = None
    syllabus_version: int | None = None
    artifact_ids: tuple[str, ...] = ()
    card_id: str | None = None
    anki_job_id: str | None = None
    anki_receipt_id: str | None = None
    frontend_marker: str = "study"
    frontend_port: int | None = None
    surreal_port: int | None = None
    model_port: int | None = None
    surreal_container_name: str | None = None
    surreal_container_id: str | None = None
    anki_download_id: str | None = None
    anki_publish_receipt_id: str | None = None


@dataclass(frozen=True)
class CleanupReceipt:
    owned_processes: int
    ports: int
    roots: int
    namespace: str
    database: str


@dataclass(frozen=True)
class FixtureResult:
    prepare_exit: int
    verify_exit: int
    source_hash_before: str
    source_hash_after: str
    external_writes: int
    cleanup: CleanupReceipt


@dataclass(frozen=True)
class Inputs:
    task_root: Path
    external_root: Path
    api_url: str
    frontend_url: str
    api_port: int
    frontend_port: int
    namespace: str
    database: str
    report_path: Path
    surreal_port: int
    model_port: int
    auth_token_file: Path | None = None
    surreal_binary: Path | None = None
    frontend_dir: Path | None = None


@dataclass
class HttpResult:
    status: int
    payload: Any
    headers: dict[str, str]
    body: bytes = b""


@dataclass
class OwnedChild:
    identity: ProcessIdentity
    process: subprocess.Popen[bytes]


class InterruptCleanup:
    """Stop the currently owned stack on cooperative process interruption.

    The handler is deliberately scoped to the stack supplied by ``stack_getter``;
    it never searches by command name, PID pattern, or listener.  SIGKILL cannot
    run Python handlers, so callers still need the exact-identity receipt to
    recover from a forced kill.
    """

    def __init__(self, stack_getter: Callable[[], object | None]) -> None:
        self._stack_getter = stack_getter
        self._previous: dict[int, object] = {}
        self._installed = False
        self._cleaned = False
        self.error: Exception | None = None

    def install(self) -> None:
        if self._installed:
            return
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle)
        atexit.register(self.cleanup)
        self._installed = True

    def _handle(self, _signum: int, _frame: object) -> None:
        self.cleanup()
        raise KeyboardInterrupt

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        stack = self._stack_getter()
        if stack is None:
            return
        try:
            stop = getattr(stack, "stop")
            stop()
        except Exception as exc:  # pragma: no cover - exercised by real teardown
            self.error = exc

    def restore(self) -> None:
        if not self._installed:
            return
        try:
            atexit.unregister(self.cleanup)
        except (AttributeError, ValueError):
            pass
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)
        self._previous.clear()
        self._installed = False


def _inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", value))
        and value != "0" * 64
    )


def _real_home() -> Path:
    """Resolve the OS account home without trusting a test/runtime HOME override."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except (AttributeError, KeyError, OSError):
        return Path.home().resolve()


def _reject_symlink_components(path: Path, stop: Path) -> None:
    stop_resolved = stop.resolve()
    current = path
    while True:
        if current == stop or current.resolve(strict=False) == stop_resolved:
            return
        if current.is_symlink():
            resolved_current = current.resolve(strict=False)
            # macOS commonly exposes /var as a symlink into the private temp
            # volume.  Permit only those ancestor links; the selected root or
            # a descendant alias remains an explicit refusal.
            if not _inside(stop_resolved, resolved_current):
                raise ProofRefusal("refused_root: symlink component")
        if current.parent == current or (
            not _inside(current, stop)
            and not _inside(current.resolve(strict=False), stop_resolved)
        ):
            raise ProofRefusal("refused_root: outside disposable temp root")
        current = current.parent


def _validate_root(
    raw: Path,
    *,
    marker_name: str,
    marker_value: str,
    kind: str,
) -> Path:
    absolute = Path(os.path.abspath(os.fspath(raw)))
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    broad = {
        _real_home(),
        _real_home() / "Documents",
        _real_home() / "Desktop",
        _real_home() / "Library",
        Path("/Users"),
    }
    if not _inside(absolute, temp_root) and (
        absolute in broad or any(_inside(absolute, item) for item in broad)
    ):
        raise ProofRefusal("refused_root: broad or private root")
    if not absolute.exists() or not absolute.is_dir():
        raise ProofRefusal("refused_root: root must be an existing directory")
    _reject_symlink_components(absolute, temp_root)
    resolved = absolute.resolve(strict=True)
    if resolved == temp_root or not _inside(resolved, temp_root):
        raise ProofRefusal("refused_root: outside disposable temp root")
    if absolute.is_symlink():
        raise ProofRefusal("refused_root: symlink root")
    try:
        owner = resolved.stat()
        if hasattr(os, "getuid") and owner.st_uid != os.getuid():
            raise ProofRefusal("refused_root: root is not owned by this user")
        if stat.S_IMODE(owner.st_mode) != 0o700:
            raise ProofRefusal("refused_root: root must be mode 0700")
    except OSError as exc:
        raise ProofRefusal(f"refused_root: {kind} stat failed") from exc
    marker = resolved / marker_name
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.read_text(encoding="utf-8").strip() != marker_value
    ):
        raise ProofRefusal(f"refused_root: {kind} ownership marker missing")
    return resolved


def validate_task_root(raw: Path) -> Path:
    return _validate_root(
        raw, marker_name=TASK_MARKER, marker_value=TASK_MARKER_VALUE, kind="task"
    )


def validate_external_root(raw: Path, task_root: Path) -> Path:
    # Reject overlapping paths before marker/existence checks so a nested or
    # parent alias cannot be interpreted as a missing, otherwise-valid root.
    candidate = Path(os.path.abspath(os.fspath(raw)))
    task = task_root.resolve(strict=True)
    if _inside(candidate, task) or _inside(task, candidate):
        raise ProofRefusal("proof_roots_must_be_disjoint")
    external = _validate_root(
        raw,
        marker_name=EXTERNAL_MARKER,
        marker_value=EXTERNAL_MARKER_VALUE,
        kind="external sentinel",
    )
    if _inside(external, task) or _inside(task, external):
        raise ProofRefusal("proof_roots_must_be_disjoint")
    return external


def validate_loopback_url(raw: str) -> str:
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.port is None
        or not 1 <= parsed.port <= 65535
    ):
        raise ProofRefusal("loopback_url_invalid")
    return raw.rstrip("/")


def _validate_port(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ProofRefusal(f"{label}_port_invalid")
    return value


def _validate_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise ProofRefusal(f"{label}_invalid")
    return value


def _validate_namespace(value: str) -> str:
    if not _SAFE_NAMESPACE.fullmatch(value):
        raise ProofRefusal("namespace_invalid")
    return value


def _validate_database(value: str) -> str:
    if not _SAFE_DATABASE.fullmatch(value):
        raise ProofRefusal("database_invalid")
    return value


def hash_tree(root: Path) -> dict[str, str]:
    """Hash a bounded tree without following symlinks or special files."""
    root = root.resolve(strict=True)
    fingerprints: dict[str, str] = {}
    total = 0
    for candidate in sorted(root.rglob("*")):
        if candidate.name in {TASK_MARKER, EXTERNAL_MARKER, RECEIPT_NAME}:
            continue
        if candidate.is_symlink():
            raise ProofRefusal("fixture_contains_symlink")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ProofRefusal("fixture_contains_special_file")
        relative = candidate.relative_to(root).as_posix()
        if len(fingerprints) >= MAX_TREE_FILES:
            raise ProofRefusal("fixture_too_large")
        data = candidate.read_bytes()
        total += len(data)
        if total > MAX_TREE_BYTES:
            raise ProofRefusal("fixture_too_large")
        fingerprints[relative] = _sha256_bytes(data)
    return fingerprints


def _tree_digest(manifest: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(manifest.items())), sort_keys=True, separators=(",", ":")
    ).encode()
    return _sha256_bytes(encoded)


def _process_start_token(pid: int) -> str | None:
    if pid <= 1:
        return None
    if sys.platform.startswith("linux"):
        try:
            fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
            return fields[21]
        except (OSError, IndexError):
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
        value = result.stdout.strip()
        return value or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _process_argv(pid: int) -> str | None:
    if sys.platform.startswith("linux"):
        try:
            return (
                Path(f"/proc/{pid}/cmdline")
                .read_bytes()
                .replace(b"\x00", b" ")
                .decode(errors="replace")
                .strip()
            )
        except OSError:
            return None
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
        value = result.stdout.strip()
        return value or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def process_identity(
    pid: int, role: str, listener_port: int | None = None
) -> ProcessIdentity:
    token = _process_start_token(pid)
    argv = _process_argv(pid)
    if not token or not argv:
        raise ProofRefusal("process_identity_unavailable")
    return ProcessIdentity(
        role=role,
        pid=pid,
        start_token=token,
        argv_sha256=_sha256_bytes(argv.encode()),
        listener_port=listener_port,
    )


def _process_matches(identity: ProcessIdentity) -> bool:
    try:
        current = process_identity(identity.pid, identity.role, identity.listener_port)
    except ProofRefusal:
        return False
    return (
        current.start_token == identity.start_token
        and current.argv_sha256 == identity.argv_sha256
    )


def _listener_pids(port: int) -> set[int]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
            text=True,
            capture_output=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {
        int(line[1:])
        for line in result.stdout.splitlines()
        if line.startswith("p") and line[1:].isdigit()
    }


def _wait_port(port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(("127.0.0.1", port))
            except OSError:
                time.sleep(0.05)
            else:
                return
    raise ProofRefusal(f"listener_timeout:{port}")


def _spawn_owned(
    args: list[str],
    *,
    role: str,
    cwd: Path,
    env: Mapping[str, str],
    listener_port: int | None = None,
    log_dir: Path | None = None,
) -> OwnedChild:
    if not args or any("\x00" in item for item in args):
        raise ProofRefusal("process_argv_invalid")
    stdout_handle = stderr_handle = None
    try:
        if log_dir is not None:
            log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            stdout_handle = (log_dir / f".study-workbench-{role}.stdout.log").open(
                "ab", buffering=0
            )
            stderr_handle = (log_dir / f".study-workbench-{role}.stderr.log").open(
                "ab", buffering=0
            )
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle or subprocess.DEVNULL,
            stderr=stderr_handle or subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        for handle in (stdout_handle, stderr_handle):
            if handle is not None:
                handle.close()
        raise ProofRefusal(f"process_spawn_failed:{role}") from exc
    finally:
        for handle in (stdout_handle, stderr_handle):
            if handle is not None:
                handle.close()
    try:
        identity = process_identity(process.pid, role, listener_port)
    except Exception:
        process.terminate()
        process.wait(timeout=2)
        raise
    return OwnedChild(identity, process)


def stop_owned(children: Iterable[OwnedChild], *, timeout: float = 8.0) -> int:
    """Stop only children whose PID/start/argv identity still matches."""
    stopped = 0
    for child in list(children):
        identity = child.identity
        if _process_matches(identity):
            try:
                if os.name != "nt":
                    os.killpg(identity.pid, signal.SIGTERM)
                else:
                    child.process.terminate()
            except (OSError, ProcessLookupError):
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and _process_matches(identity):
            time.sleep(0.05)
        if _process_matches(identity):
            try:
                if os.name != "nt":
                    os.killpg(identity.pid, signal.SIGKILL)
                else:
                    child.process.kill()
            except (OSError, ProcessLookupError):
                pass
        try:
            child.process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if not _process_matches(identity):
            stopped += 1
    return stopped


def cleanup_owned(
    children: Iterable[OwnedChild],
    ports: Iterable[int],
    task_root: Path,
    namespace: str,
    database: str,
) -> CleanupReceipt:
    children_list = list(children)
    stopped = stop_owned(children_list)
    leaked = [
        item.identity.pid for item in children_list if _process_matches(item.identity)
    ]
    if leaked:
        raise ProofRefusal("owned_processes_remain")
    busy = [port for port in ports if _listener_pids(port)]
    if busy:
        raise ProofRefusal("owned_listeners_remain")
    if task_root.exists():
        validate_task_root(task_root)
        shutil.rmtree(task_root)
    return CleanupReceipt(
        owned_processes=len(children_list) - stopped,
        ports=len(busy),
        roots=0 if not task_root.exists() else 1,
        namespace=namespace,
        database=database,
    )


def previous_processes_are_gone(receipt: RestartReceipt) -> bool:
    """Check recorded identities without creating probe processes."""
    return not any(
        _process_matches(identity) for identity in receipt.previous_processes
    )


def _receipt_dict(receipt: RestartReceipt) -> dict[str, Any]:
    return {
        "version": receipt.version,
        "phase": receipt.phase,
        "task_root_sha256": receipt.task_root_sha256,
        "namespace": receipt.namespace,
        "database": receipt.database,
        "previous_api_pid": receipt.previous_api_pid,
        "previous_api_start_token": receipt.previous_api_start_token,
        "previous_api_argv_sha256": receipt.previous_api_argv_sha256,
        "previous_listener_port": receipt.previous_listener_port,
        "source_hashes": receipt.source_hashes,
        "external_hashes": receipt.external_hashes,
        "external_writes": receipt.external_writes,
        "previous_processes": [item.__dict__ for item in receipt.previous_processes],
        "source_ids": list(receipt.source_ids),
        "plan_id": receipt.plan_id,
        "syllabus_version": receipt.syllabus_version,
        "artifact_ids": list(receipt.artifact_ids),
        "card_id": receipt.card_id,
        "anki_job_id": receipt.anki_job_id,
        "anki_receipt_id": receipt.anki_receipt_id,
        "frontend_marker": receipt.frontend_marker,
        "frontend_port": receipt.frontend_port,
        "surreal_port": receipt.surreal_port,
        "model_port": receipt.model_port,
        "surreal_container_name": receipt.surreal_container_name,
        "surreal_container_id": receipt.surreal_container_id,
        "anki_download_id": receipt.anki_download_id,
        "anki_publish_receipt_id": receipt.anki_publish_receipt_id,
    }


def _receipt_from_dict(payload: object) -> RestartReceipt:
    if not isinstance(payload, dict):
        raise ProofRefusal("restart_receipt_invalid")
    required = {
        "version",
        "phase",
        "task_root_sha256",
        "namespace",
        "database",
        "previous_api_pid",
        "previous_api_start_token",
        "previous_api_argv_sha256",
        "previous_listener_port",
        "source_hashes",
        "external_hashes",
        "external_writes",
    }
    if not required.issubset(payload):
        raise ProofRefusal("restart_receipt_invalid")
    raw_processes = payload.get("previous_processes", [])
    if not isinstance(raw_processes, list):
        raise ProofRefusal("restart_receipt_invalid")
    processes: list[ProcessIdentity] = []
    for item in raw_processes:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("role"), str)
            or not isinstance(item.get("pid"), int)
            or not isinstance(item.get("start_token"), str)
            or not isinstance(item.get("argv_sha256"), str)
        ):
            raise ProofRefusal("restart_receipt_invalid")
        processes.append(
            ProcessIdentity(
                role=item["role"],
                pid=item["pid"],
                start_token=item["start_token"],
                argv_sha256=item["argv_sha256"],
                listener_port=item.get("listener_port"),
            )
        )
    return RestartReceipt(
        version=payload["version"],
        phase=payload["phase"],
        task_root_sha256=payload["task_root_sha256"],
        namespace=payload["namespace"],
        database=payload["database"],
        previous_api_pid=payload["previous_api_pid"],
        previous_api_start_token=payload["previous_api_start_token"],
        previous_api_argv_sha256=payload["previous_api_argv_sha256"],
        previous_listener_port=payload["previous_listener_port"],
        source_hashes=dict(payload["source_hashes"]),
        external_hashes=dict(payload["external_hashes"]),
        external_writes=payload["external_writes"],
        previous_processes=tuple(processes),
        source_ids=tuple(payload.get("source_ids", [])),
        plan_id=payload.get("plan_id"),
        syllabus_version=payload.get("syllabus_version"),
        artifact_ids=tuple(payload.get("artifact_ids", [])),
        card_id=payload.get("card_id"),
        anki_job_id=payload.get("anki_job_id"),
        anki_receipt_id=payload.get("anki_receipt_id"),
        frontend_marker=payload.get("frontend_marker", "study"),
        frontend_port=payload.get("frontend_port"),
        surreal_port=payload.get("surreal_port"),
        model_port=payload.get("model_port"),
        surreal_container_name=payload.get("surreal_container_name"),
        surreal_container_id=payload.get("surreal_container_id"),
        anki_download_id=payload.get("anki_download_id"),
        anki_publish_receipt_id=payload.get("anki_publish_receipt_id"),
    )


def validate_restart_receipt(
    receipt: RestartReceipt, task_root: Path, inputs: Inputs | None = None
) -> RestartReceipt:
    expected_root = _sha256_bytes(str(task_root.resolve(strict=True)).encode())
    if receipt.version != 1 or receipt.phase not in {"awaiting_restart", "complete"}:
        raise ProofRefusal("restart_receipt_invalid")
    if receipt.task_root_sha256 != expected_root:
        raise ProofRefusal("restart_state_root_mismatch")
    _validate_namespace(receipt.namespace)
    _validate_database(receipt.database)
    if (
        receipt.external_writes != 0
        or receipt.previous_api_pid <= 1
        or receipt.previous_listener_port < 1
    ):
        raise ProofRefusal("restart_receipt_invalid")
    if not receipt.previous_api_start_token or not _is_sha256(
        receipt.previous_api_argv_sha256
    ):
        raise ProofRefusal("restart_receipt_invalid")
    for collection in (receipt.source_hashes, receipt.external_hashes):
        if (
            not isinstance(collection, dict)
            or not collection
            or any(
                not isinstance(key, str) or not _is_sha256(value)
                for key, value in collection.items()
            )
        ):
            raise ProofRefusal("restart_source_hash_mismatch")
    if any(
        not _is_sha256(item.argv_sha256) or item.pid <= 1 or not item.start_token
        for item in receipt.previous_processes
    ):
        raise ProofRefusal("restart_receipt_invalid")
    if inputs is not None and (
        receipt.frontend_port is None
        or receipt.surreal_port is None
        or receipt.model_port is None
        or receipt.surreal_container_name is None
        or receipt.surreal_container_id is None
        or not re.fullmatch(
            r"dn-study-[a-f0-9]{12}", receipt.surreal_container_name or ""
        )
        or not re.fullmatch(r"[a-f0-9]{12,64}", receipt.surreal_container_id or "")
    ):
        raise ProofRefusal("restart_inputs_mismatch")
    if inputs is not None:
        _validate_port(receipt.previous_listener_port, "api")
        _validate_port(receipt.frontend_port or 0, "frontend")
        _validate_port(receipt.surreal_port or 0, "surreal")
        _validate_port(receipt.model_port or 0, "model")
        if (
            len(
                {
                    receipt.previous_listener_port,
                    receipt.frontend_port,
                    receipt.surreal_port,
                    receipt.model_port,
                }
            )
            != 4
        ):
            raise ProofRefusal("restart_receipt_ports_not_unique")
    if inputs is not None and (
        receipt.namespace != inputs.namespace
        or receipt.database != inputs.database
        or receipt.previous_listener_port != inputs.api_port
        or receipt.frontend_port != inputs.frontend_port
        or receipt.surreal_port != inputs.surreal_port
        or receipt.model_port != inputs.model_port
    ):
        raise ProofRefusal("restart_inputs_mismatch")
    return receipt


def _write_receipt(path: Path, receipt: RestartReceipt) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProofRefusal("restart_receipt_path_invalid")
    encoded = (
        json.dumps(_receipt_dict(receipt), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise ProofRefusal("restart_receipt_too_large")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_receipt(path: Path, task_root: Path) -> RestartReceipt:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_RECEIPT_BYTES
    ):
        raise ProofRefusal("restart_receipt_invalid")
    try:
        receipt = _receipt_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProofRefusal("restart_receipt_invalid") from exc
    return validate_restart_receipt(receipt, task_root)


_SECRET_KEYS = {
    "token",
    "password",
    "api_key",
    "secret",
    "prompt",
    "content",
    "body",
    "path",
    "absolute_path",
    "provider_payload",
}


def sanitize_receipt(value: object) -> str:
    def scrub(item: object, key: str | None = None) -> object:
        if key and key.lower() in _SECRET_KEYS:
            return "<redacted>"
        if isinstance(item, Mapping):
            return {str(k): scrub(v, str(k)) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [scrub(v) for v in item]
        if isinstance(item, str):
            return re.sub(
                r"/(?:Users|private|tmp|var)/[^\s`\"']+", "<redacted-path>", item
            )
        return item

    return json.dumps(scrub(value), sort_keys=True, indent=2)


def _write_report(path: Path, payload: Mapping[str, object]) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProofRefusal("report_path_invalid")
    if path.name != "study-workbench-report.md":
        raise ProofRefusal("report_path_invalid")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ProofRefusal("report_path_invalid")
    marker = path.parent / REPORT_MARKER
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.read_text(encoding="utf-8").strip() != REPORT_MARKER_VALUE
    ):
        raise ProofRefusal("report_path_not_owned")
    if path.resolve() == Path(path.anchor) or path.parent.resolve() == Path(
        path.anchor
    ):
        raise ProofRefusal("report_path_invalid")
    if path.exists() and not path.read_text(encoding="utf-8").startswith(
        "# Study Workbench verification"
    ):
        raise ProofRefusal("report_path_not_owned")
    path.write_text(
        "# Study Workbench verification\n\n```json\n"
        + sanitize_receipt(payload)
        + "\n```\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _multipart(
    fields: Mapping[str, str],
    file_field: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> tuple[bytes, str]:
    boundary = "----study-workbench-" + hashlib.sha256(data).hexdigest()[:20]
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            data,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _http_request(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: object | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    token: str | None = None,
    extra_headers: Mapping[str, str] | None = None,
    timeout: float = 10.0,
) -> HttpResult:
    headers = {"Accept": "application/json", "X-Study-Workbench-Proof": "1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    data = body
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        base_url.rstrip("/") + path, data=data, headers=headers, method=method
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ProofRefusal("api_response_too_large")
    try:
        parsed: Any = json.loads(raw) if raw else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = None
    return HttpResult(
        int(response.status),
        parsed,
        {key.lower(): value for key, value in response.headers.items()},
        raw,
    )


def _expect(result: HttpResult, statuses: set[int], code: str) -> Any:
    if result.status not in statuses:
        # Preserve a bounded, server-issued domain code when the product
        # returns one (for example ``revision_conflict``) so a real proof
        # blocker is actionable without copying provider payloads into the
        # receipt.  The fallback remains the stable HTTP-only code used by
        # the deterministic fixture and unit checks.
        detail_code: str | None = None
        if isinstance(result.payload, Mapping):
            detail = result.payload.get("detail")
            if isinstance(detail, Mapping):
                candidate = detail.get("code")
                if isinstance(candidate, str) and re.fullmatch(
                    r"[a-z][a-z0-9_]{1,63}", candidate
                ):
                    detail_code = candidate
        suffix = f":{detail_code}" if detail_code else ""
        raise ProofRefusal(f"{code}:http_{result.status}{suffix}")
    return result.payload


def _synthetic_fixtures(root: Path) -> dict[str, Path]:
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(fixture_dir, 0o700)
    pdf = fixture_dir / "study-proof.pdf"
    video = fixture_dir / "study-proof.mp4"
    try:
        import fitz

        document = fitz.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 720), "Synthetic Study Workbench evidence.", fontsize=12)
        pdf.write_bytes(document.tobytes(garbage=4, deflate=True))
        document.close()
    except (ImportError, OSError, RuntimeError) as exc:
        raise ProofRefusal("pdf_fixture_generator_unavailable") from exc
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            # The production video processor extracts an audio track for STT;
            # keep this fixture tiny but include a bounded sine stream so the
            # real worker reaches nonblank source readiness.
            subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=32x32:r=1",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=880:sample_rate=16000",
                    "-t",
                    "0.4",
                    "-shortest",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "24k",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(video),
                ],
                check=True,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            video.write_bytes(
                b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41synthetic-study-video"
            )
    else:
        raise ProofRefusal("ffmpeg_fixture_generator_unavailable")
    return {"pdf": pdf, "video": video}


def _source_hashes(fixtures: Mapping[str, Path]) -> dict[str, str]:
    return {name: _sha256_bytes(path.read_bytes()) for name, path in fixtures.items()}


def _workflow(
    api_url: str,
    frontend_url: str,
    fixtures: Mapping[str, Path],
    *,
    token: str | None = None,
    existing: Mapping[str, Any] | None = None,
    model_url: str | None = None,
    seed: Mapping[str, Any] | None = None,
    trace: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Exercise real HTTP routes; returned values contain metadata only."""
    def mark(stage: str) -> None:
        if trace is not None:
            trace["code"] = stage

    mark("api_ready")
    _expect(_http_request(api_url, "GET", "/readyz", token=token), {200}, "api_ready")
    mark("auth_status")
    auth = _expect(
        _http_request(api_url, "GET", "/api/auth/status", token=token),
        {200},
        "auth_status",
    )
    if isinstance(auth, dict) and auth.get("auth_enabled") and not token:
        raise ProofRefusal("auth_token_required")
    mark("credential_status")
    _expect(
        _http_request(api_url, "GET", "/api/credentials/status", token=token),
        {200, 503},
        "credential_status",
    )
    state: dict[str, Any] = dict(existing or {})
    if not existing:
        mark("credential_seed")
        # Seed synthetic local credentials/models through the public API. The
        # API stores the key encrypted and returns metadata only.
        if seed:
            state.update(seed)
        else:
            # The unit-only HTTP fixture does not invoke a provider; keep its
            # synthetic credential URL deterministic while production callers
            # always pass the task-owned loopback model endpoint explicitly.
            model_url = model_url or f"{api_url.rstrip('/')}/v1"
            credential = _expect(
                _http_request(
                    api_url,
                    "POST",
                    "/api/credentials",
                    token=token,
                    payload={
                        "name": "Task-owned local proof",
                        "provider": "openai_compatible",
                        "modalities": ["language", "embedding"],
                        "api_key": "task-proof-key",
                        "base_url": model_url,
                    },
                ),
                {200, 201},
                "credential_create",
            )
            credential_id = (
                credential.get("id") if isinstance(credential, dict) else None
            )
            model = _expect(
                _http_request(
                    api_url,
                    "POST",
                    "/api/models",
                    token=token,
                    payload={
                        "name": "study-proof-local",
                        "provider": "openai_compatible",
                        "type": "language",
                        "credential": credential_id,
                    },
                ),
                {200, 201},
                "model_create",
            )
            model_id = model.get("id") if isinstance(model, dict) else None
            _expect(
                _http_request(
                    api_url,
                    "PUT",
                    "/api/models/defaults",
                    token=token,
                    payload={
                        "default_chat_model": model_id,
                        "large_context_model": model_id,
                        "default_tools_model": model_id,
                    },
                ),
                {200},
                "defaults_update",
            )
            state.update({"credential_id": credential_id, "model_id": model_id})
        upload_ids: list[str] = []
        uploaded_kinds: dict[str, str] = {}
        for kind, path in fixtures.items():
            mark("source_upload")
            # Source readiness requires an evidence fingerprint.  Supply the
            # fingerprint through the public upload contract, derived from the
            # exact bounded text emitted by the production PDF/STT processors;
            # no source body or internal database write is injected.
            expected_text = (
                "Synthetic Study Workbench evidence."
                if kind == "pdf"
                else "Synthetic video evidence."
            )
            upload_provenance = json.dumps(
                {"content_fingerprint": _sha256_bytes(expected_text.encode("utf-8"))},
                separators=(",", ":"),
            )
            data, ctype = _multipart(
                {
                    "type": "upload",
                    "title": f"Synthetic {kind} evidence",
                    "embed": "false",
                    "async_processing": "true",
                    "provenance": upload_provenance,
                },
                "file",
                path.name,
                "application/pdf" if kind == "pdf" else "video/mp4",
                path.read_bytes(),
            )
            source = _expect(
                _http_request(
                    api_url,
                    "POST",
                    "/api/sources",
                    token=token,
                    body=data,
                    content_type=ctype,
                ),
                {200, 201},
                f"{kind}_upload",
            )
            source_id = source.get("id") if isinstance(source, dict) else None
            if not isinstance(source_id, str):
                raise ProofRefusal(f"{kind}_source_id_missing")
            uploaded_kinds[source_id] = kind
            deadline = time.monotonic() + 180
            while True:
                mark("source_processing")
                status_payload = _expect(
                    _http_request(
                        api_url,
                        "GET",
                        f"/api/sources/{urllib.parse.quote(source_id, safe='')}/status",
                        token=token,
                    ),
                    {200},
                    f"{kind}_processing_status",
                )
                status = (
                    status_payload.get("status")
                    if isinstance(status_payload, dict)
                    else None
                )
                if status in {None, "completed"}:
                    break
                if status in {"failed", "unknown"}:
                    raise ProofRefusal(f"{kind}_processing_{status}")
                if time.monotonic() >= deadline:
                    raise ProofRefusal(f"{kind}_processing_deadline")
                time.sleep(0.25)
            upload_ids.append(source_id)
        state["source_ids"] = upload_ids
        source_evidence: dict[str, str] = {}
        source_hashes: dict[str, str] = {}
        mark("source_evidence")
        for source_id in upload_ids:
            kind = uploaded_kinds.get(source_id)
            query = (
                "Synthetic Study Workbench evidence."
                if kind == "pdf"
                else "Synthetic video evidence."
            )
            located = _expect(
                _http_request(
                    api_url,
                    "POST",
                    f"/api/sources/{urllib.parse.quote(source_id, safe='')}/locate-passage",
                    token=token,
                    payload={"query": query},
                ),
                {200},
                "source_evidence_locate",
            )
            match = located.get("match") if isinstance(located, dict) else None
            snippet = match.get("snippet") if isinstance(match, dict) else None
            if not isinstance(snippet, str) or not snippet.strip():
                raise ProofRefusal("source_evidence_missing")
            source_evidence[source_id] = snippet
            source_hashes[source_id] = _sha256_bytes(snippet.encode("utf-8"))
        state["source_evidence"] = source_evidence
        state["source_content_hashes"] = source_hashes
        mark("plan_lifecycle")
        plan = _expect(
            _http_request(
                api_url,
                "POST",
                "/api/study/plans",
                token=token,
                payload={
                    "goal": "Explain the synthetic evidence boundary",
                    "starting_level": "beginner",
                },
            ),
            {200, 201},
            "plan_create",
        )
        state["plan_id"] = plan.get("plan_id") if isinstance(plan, dict) else None
        revision = int(plan.get("version", 1)) if isinstance(plan, dict) else 1
        for source_id in upload_ids:
            linked = _expect(
                _http_request(
                    api_url,
                    "POST",
                    f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/sources",
                    token=token,
                    payload={"source_id": source_id, "expected_revision": revision},
                ),
                {200, 201},
                "source_link",
            )
            revision += 1
            if not isinstance(linked, dict):
                raise ProofRefusal("source_link_receipt_missing")
        readiness = _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/sources/readiness",
                token=token,
            ),
            {200},
            "source_readiness",
        )
        if not isinstance(readiness, dict) or readiness.get("ready") is not True:
            items = readiness.get("items", []) if isinstance(readiness, dict) else []
            summary: list[str] = []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    source_id = item.get("source_id")
                    if isinstance(source_id, str):
                        summary.append(
                            f"{source_id.split(':', 1)[0]}:{item.get('reason', 'unknown')}:{item.get('fingerprint_status', 'unknown')}"
                        )
            raise ProofRefusal(
                "source_readiness:not_ready:" + ",".join(sorted(summary))[:256]
            )
        items = readiness.get("items", [])
        if not isinstance(items, list) or {
            item.get("source_id") for item in items if isinstance(item, dict)
        } != set(upload_ids):
            raise ProofRefusal("source_readiness:source_set_mismatch")
        if any(
            not isinstance(item, dict)
            or item.get("ready") is not True
            or item.get("reason") != "ready"
            or item.get("fingerprint_status") != "available"
            for item in items
        ):
            raise ProofRefusal("source_readiness:item_not_ready")
        mark("syllabus_lifecycle")
        syllabus = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/syllabus:propose",
                token=token,
                payload={"expected_revision": revision},
            ),
            {200},
            "syllabus_propose",
        )
        version = int(syllabus.get("version", 1)) if isinstance(syllabus, dict) else 1
        units = syllabus.get("units") if isinstance(syllabus, dict) else None
        if not isinstance(units, list) or not units:
            raise ProofRefusal("syllabus_units_missing")
        unit = dict(units[0])
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str):
            raise ProofRefusal("syllabus_unit_id_missing")
        unit["title"] = "Synthetic evidence foundations"
        syllabus_manifest = syllabus.get("source_manifest_sha256")
        version += 1
        _expect(
            _http_request(
                api_url,
                "PUT",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/syllabus",
                token=token,
                payload={
                    "expected_revision": revision + 1,
                    "version": version,
                    "source_manifest_sha256": syllabus_manifest,
                    "units": [unit],
                },
            ),
            {200},
            "syllabus_edit",
        )
        approved = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/syllabus:approve",
                token=token,
                payload={
                    "syllabus_version": version,
                    "expected_revision": revision + 2,
                },
            ),
            {200},
            "syllabus_approve",
        )
        # Approval returns the plan projection, but the verifier must bind the
        # next mutation to a fresh authoritative read rather than trusting a
        # driver-specific transaction projection.  This also catches a
        # product-side revision drift as an exact blocker before generation.
        if not isinstance(approved, dict) or approved.get("state") != "approved":
            raise ProofRefusal("syllabus_approve:invalid_projection")
        current_plan = _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}",
                token=token,
            ),
            {200},
            "approved_plan_read",
        )
        if (
            not isinstance(current_plan, dict)
            or current_plan.get("state") != "approved"
        ):
            raise ProofRefusal("approved_plan_read:not_approved")
        current_revision = current_plan.get("version")
        if (
            isinstance(current_revision, bool)
            or not isinstance(current_revision, int)
            or current_revision < 1
        ):
            raise ProofRefusal("approved_plan_read:revision_missing")
        revision = current_revision
        state["syllabus_version"] = version
        mark("artifact_generation")
        generated = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/generate",
                token=token,
                payload={
                    "unit_id": unit_id,
                    "artifact_types": ["study_guide", "flashcards"],
                    "expected_revision": revision,
                },
            ),
            {200},
            "unit_generate",
        )
        artifacts = (
            generated.get("artifacts", []) if isinstance(generated, dict) else []
        )
        state["artifact_ids"] = [
            item.get("artifact_id")
            for item in artifacts
            if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
        ]
        for role, authority in (("source_guide", "ask"), ("practice_coach", "coach")):
            mark("assistant_invocation")
            assistant = _expect(
                _http_request(
                    api_url,
                    "POST",
                    f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/assistants/{role}:invoke",
                    token=token,
                    payload={
                        "authority": authority,
                        "prompt": f"Explain the selected source for {role}",
                        "unit_id": unit_id,
                        "selected_source_ids": upload_ids,
                        "model_route": "local",
                        "network_allowed": False,
                        "approved_network_scope": [],
                        "timeout_seconds": 60,
                    },
                ),
                {200},
                f"{role}_invoke",
            )
            if not isinstance(assistant, dict) or not assistant.get("answer"):
                raise ProofRefusal(f"{role}_answer_missing")
        evidence_text = str(
            state.get("source_evidence", {}).get(upload_ids[0], "Synthetic")
        )
        quote = "Synthetic" if "Synthetic" in evidence_text else evidence_text[:32]
        start = evidence_text.index(quote)
        mark("card_lifecycle")
        card = _expect(
            _http_request(
                api_url,
                "POST",
                "/api/study/cards",
                token=token,
                payload={
                    "artifact_id": state["artifact_ids"][0]
                    if state["artifact_ids"]
                    else "study_artifact:proof",
                    "artifact_card_id": "synthetic-card",
                    "front": "What does the synthetic proof verify?",
                    "back": "It verifies source-to-study durability.",
                    "citations": [
                        {
                            "source_id": upload_ids[0],
                            "source_content_sha256": state.get(
                                "source_content_hashes", {}
                            ).get(
                                upload_ids[0],
                                _sha256_bytes(evidence_text.encode("utf-8")),
                            ),
                            "source_state": "current",
                            "offset_encoding": "unicode_codepoint",
                            "start": start,
                            "end": start + len(quote),
                            "quote": quote,
                        }
                    ],
                },
            ),
            {200, 201},
            "card_create",
        )
        state["card_id"] = card.get("id") if isinstance(card, dict) else None
        if not isinstance(state["card_id"], str):
            raise ProofRefusal("card_id_missing")
        reviewed = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/cards/{urllib.parse.quote(state['card_id'], safe='')}/reviews",
                token=token,
                payload={"request_id": "study-proof-review-1", "rating": "good"},
            ),
            {200},
            "card_review",
        )
        if not isinstance(reviewed, dict):
            raise ProofRefusal("review_receipt_missing")
        mark("progress_projection")
        _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/progress",
                token=token,
            ),
            {200},
            "progress_projection",
        )
        mark("anki_export_response")
        exported = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/anki/export",
                token=token,
                payload={"schema_version": 1, "options": {"schema_version": 1}},
            ),
            {200},
            "anki_export",
        )
        state["anki_receipt_id"] = (
            (exported.get("receipt") or {}).get("receipt_id")
            if isinstance(exported, dict)
            else None
        )
        download_id = (
            exported.get("download_id") if isinstance(exported, dict) else None
        )
        if not isinstance(download_id, str):
            raise ProofRefusal("anki_download_id_missing")
        mark("anki_download")
        downloaded = _http_request(
            api_url,
            "GET",
            f"/api/study/plans/anki/download/{urllib.parse.quote(download_id, safe='')}",
            token=token,
        )
        mark("anki_download_response")
        if downloaded.status != 200 or not downloaded.body:
            raise ProofRefusal("anki_download_failed")
        mark("anki_multipart")
        data, ctype = _multipart(
            {"options": json.dumps({"schema_version": 1})},
            "file",
            "study-proof.apkg",
            "application/octet-stream",
            downloaded.body,
        )
        mark("anki_import_preview")
        preview = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/anki/import",
                token=token,
                body=data,
                content_type=ctype,
            ),
            {200, 201},
            "anki_import_preview",
        )
        state["anki_job_id"] = (
            preview.get("job_id") if isinstance(preview, dict) else None
        )
        state["anki_download_id"] = download_id
        if not isinstance(state["anki_job_id"], str):
            raise ProofRefusal("anki_job_id_missing")
        mark("anki_import_status")
        _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/anki/import/{urllib.parse.quote(state['anki_job_id'], safe='')}",
                token=token,
            ),
            {200},
            "anki_import_status",
        )
        mark("anki_publish")
        publish = _expect(
            _http_request(
                api_url,
                "POST",
                f"/api/study/plans/{urllib.parse.quote(str(state['plan_id']), safe='')}/anki/import/{urllib.parse.quote(state['anki_job_id'], safe='')}:publish",
                token=token,
                payload={
                    "upload_id": state["anki_job_id"],
                    "request_id": "study-proof-anki-publish-1",
                    "options": {"schema_version": 1},
                },
            ),
            {200},
            "anki_import_publish",
        )
        if not isinstance(publish, dict):
            raise ProofRefusal("anki_publish_receipt_missing")
        publish_receipt = publish.get("receipt")
        state["anki_publish_receipt_id"] = (
            publish_receipt.get("receipt_id")
            if isinstance(publish_receipt, dict)
            else None
        )
        if not isinstance(state["anki_publish_receipt_id"], str):
            raise ProofRefusal("anki_publish_receipt_missing")
    else:
        mark("restart_reads")
        plan_id = state.get("plan_id")
        if not isinstance(plan_id, str):
            raise ProofRefusal("restart_plan_id_missing")
        plan_payload = _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}",
                token=token,
            ),
            {200},
            "restart_plan_read",
        )
        if (
            not isinstance(plan_payload, dict)
            or plan_payload.get("plan_id") != plan_id
            or plan_payload.get("state") not in {"approved", "completed"}
        ):
            raise ProofRefusal("restart_plan_parity_mismatch")
        readiness = _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}/sources/readiness",
                token=token,
            ),
            {200},
            "restart_source_read",
        )
        readiness_items = readiness.get("items") if isinstance(readiness, dict) else None
        if (
            not isinstance(readiness, dict)
            or readiness.get("ready") is not True
            or not isinstance(readiness_items, list)
            or {
                item.get("source_id")
                for item in readiness_items
                if isinstance(item, dict)
            }
            != set(state.get("source_ids", ()))
            or any(
                not isinstance(item, dict)
                or item.get("ready") is not True
                or item.get("fingerprint_status") != "available"
                for item in readiness_items
            )
        ):
            raise ProofRefusal("restart_source_parity_mismatch")
        syllabus_version = state.get("syllabus_version")
        syllabus_payload = _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}/syllabus"
                + (
                    f"?version={int(syllabus_version)}"
                    if isinstance(syllabus_version, int)
                    else ""
                ),
                token=token,
            ),
            {200},
            "restart_syllabus_read",
        )
        if (
            not isinstance(syllabus_payload, dict)
            or syllabus_payload.get("plan_id") != plan_id
            or (
                isinstance(syllabus_version, int)
                and syllabus_payload.get("version") != syllabus_version
            )
        ):
            raise ProofRefusal("restart_syllabus_parity_mismatch")
        artifact_ids = tuple(
            item for item in state.get("artifact_ids", ()) if isinstance(item, str)
        )
        units = syllabus_payload.get("units") if isinstance(syllabus_payload, dict) else None
        if artifact_ids:
            unit_id = (
                units[0].get("unit_id")
                if isinstance(units, list) and units and isinstance(units[0], dict)
                else None
            )
            expected_revision = plan_payload.get("version")
            if not isinstance(unit_id, str) or not isinstance(expected_revision, int):
                raise ProofRefusal("restart_artifact_parity_inputs_missing")
            generated = _expect(
                _http_request(
                    api_url,
                    "POST",
                    f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}/generate",
                    token=token,
                    payload={
                        "unit_id": unit_id,
                        "artifact_types": ["study_guide", "flashcards"],
                        "expected_revision": expected_revision,
                    },
                ),
                {200},
                "restart_artifact_read",
            )
            returned_artifact_ids = tuple(
                item.get("artifact_id")
                for item in (generated.get("artifacts", []) if isinstance(generated, dict) else [])
                if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
            )
            if set(returned_artifact_ids) != set(artifact_ids):
                raise ProofRefusal("restart_artifact_parity_mismatch")
        if isinstance(state.get("card_id"), str):
            reviewed = _expect(
                _http_request(
                    api_url,
                    "POST",
                    f"/api/study/cards/{urllib.parse.quote(state['card_id'], safe='')}/reviews",
                    token=token,
                    payload={"request_id": "study-proof-review-1", "rating": "good"},
                ),
                {200},
                "restart_card_read",
            )
            reviewed_card = reviewed.get("card") if isinstance(reviewed, dict) else None
            if not isinstance(reviewed_card, dict) or reviewed_card.get("id") != state["card_id"]:
                raise ProofRefusal("restart_card_parity_mismatch")
        _expect(
            _http_request(
                api_url,
                "GET",
                f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}/progress",
                token=token,
            ),
            {200},
            "restart_progress_read",
        )
        if isinstance(state.get("anki_job_id"), str):
            anki_status = _expect(
                _http_request(
                    api_url,
                    "GET",
                    f"/api/study/plans/{urllib.parse.quote(plan_id, safe='')}/anki/import/{urllib.parse.quote(state['anki_job_id'], safe='')}",
                    token=token,
                ),
                {200},
                "restart_anki_read",
            )
            if (
                not isinstance(anki_status, dict)
                or anki_status.get("job_id") != state["anki_job_id"]
                or anki_status.get("status") != "published"
            ):
                raise ProofRefusal("restart_anki_job_parity_mismatch")
            publish_receipt_id = state.get("anki_publish_receipt_id")
            if isinstance(publish_receipt_id, str) and anki_status.get("receipt_id") != publish_receipt_id:
                raise ProofRefusal("restart_anki_receipt_parity_mismatch")
        if isinstance(state.get("anki_download_id"), str):
            downloaded = _http_request(
                api_url,
                "GET",
                f"/api/study/plans/anki/download/{urllib.parse.quote(state['anki_download_id'], safe='')}",
                token=token,
            )
            if downloaded.status != 200 or not downloaded.body:
                raise ProofRefusal("restart_anki_download_parity_mismatch")
    mark("frontend_route")
    # The production Next proxy intentionally redirects first-launch clients
    # to the setup wizard.  The real proof seeds the disposable model and
    # credential state above, then supplies the same completion cookie a
    # browser would receive from the wizard so the actual /study page renders.
    frontend = _http_request(
        frontend_url,
        "GET",
        "/study",
        token=token,
        extra_headers=_frontend_request_headers(),
    )
    # Next's production RSC response may carry the route marker in lowercase
    # inside the streamed tree even though the rendered heading is localized.
    if frontend.status != 200 or b"study" not in frontend.body.lower():
        raise ProofRefusal("frontend_study_route_unavailable")
    return state


_MODEL_SERVER_SOURCE = textwrap.dedent(
    r"""
    import json, os, re
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    PORT = int(os.environ["MODEL_PORT"])
    MODEL = "study-proof-local"

    def _source_ids(payload):
        text = json.dumps(payload, ensure_ascii=False)
        values = re.findall(r"source:(?:⟨[^⟩]{1,256}⟩|[A-Za-z0-9_-]{1,256})", text)
        return list(dict.fromkeys(values)) or ["source:proof"]

    def _message_text(payload):
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            return ""
        parts = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                )
        return "\n".join(parts)

    def _requested_schema(payload):
        text = _message_text(payload)
        decoder = json.JSONDecoder()
        for marker in ("Required JSON Schema:", "JSON Schema:"):
            if marker not in text:
                continue
            candidate = text.split(marker, 1)[1].lstrip()
            try:
                schema, _end = decoder.raw_decode(candidate)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(schema, dict):
                return schema
        return {}

    def _content(payload):
        text = _message_text(payload)
        requested_schema = _requested_schema(payload)
        schema_properties = requested_schema.get("properties", {})
        schema_fields = set(schema_properties) if isinstance(schema_properties, dict) else set()
        source_ids = _source_ids(payload)
        source_id = source_ids[0]
        # Assistant prompts intentionally carry syllabus/card context.  Route
        # by the exact assistant contract or parsed JSON Schema, never by a
        # context keyword that can occur in otherwise unrelated evidence.
        assistant_fields = {"answer", "citations", "proposed_actions"}
        if assistant_fields <= schema_fields or "Return one JSON object with answer, citations, and proposed_actions." in text:
            return {"answer": "Synthetic evidence supports the requested explanation.", "citations": [{"source_id": source_id, "quote": "Synthetic"}], "proposed_actions": []}
        if {"artifact_type", "units", "knowledge_gaps"} <= schema_fields:
            return {"title": "Synthetic Study Syllabus", "units": [{"unit_id": "foundations", "title": "Synthetic evidence foundations", "objectives": ["Explain source-grounded evidence"], "prerequisite_unit_ids": [], "estimated_minutes": 10, "source_ids": source_ids[:2], "activities": []}], "knowledge_gaps": []}
        if {"artifact_type", "cards"} <= schema_fields:
            return {"cards": [{"front": "What does local evidence preserve?", "back": "It preserves source-grounded study work.", "citations": ["[S1]"]}, {"front": "What is the proof boundary?", "back": "Only selected evidence is used.", "citations": ["[S1]"]}, {"front": "What is durable?", "back": "The source and study receipts are durable.", "citations": ["[S1]"]}], "artifact_type": "flashcards", "title": "Synthetic evidence cards"}
        if {"artifact_type", "sections"} <= schema_fields:
            return {"artifact_type": "study_guide", "title": "Synthetic evidence guide", "summary": "A bounded source-grounded guide.", "sections": [{"heading": "Evidence", "body": "Synthetic evidence is selected before study output.", "citations": ["[S1]"]}]}
        return {"answer": "Synthetic evidence supports the requested explanation.", "citations": [{"source_id": source_id, "quote": "Synthetic"}], "proposed_actions": []}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.rstrip("/") in {"/v1/models", "/models"}:
                self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "task-proof"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if self.path.rstrip("/") in {"/v1/audio/transcriptions", "/audio/transcriptions"}:
                self.rfile.read(length)
                self._send(200, {"text": "Synthetic video evidence."})
                return
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                payload = {}
            if self.path.rstrip("/") in {"/v1/chat/completions", "/chat/completions"}:
                content = json.dumps(_content(payload), separators=(",", ":"))
                self._send(200, {"id": "chatcmpl-study-proof", "object": "chat.completion", "model": MODEL, "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
            else:
                self._send(404, {"error": "not found"})

        def log_message(self, *_args):
            return

    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    """
)


def _prepare_local_model_fixture(root: Path) -> Path:
    """Create a bounded MLX-shaped identity; the loopback server does all inference."""
    model_dir = root / "models"
    model_path = model_dir / "MLX" / "study-proof-local"
    model_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    (model_path / "config.json").write_text(
        json.dumps(
            {"model_type": "study-proof", "max_position_embeddings": 32768},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (model_path / "model.safetensors").write_bytes(
        b"bounded task-owned proof weights\n"
    )
    server = root / "study-proof-model-server.py"
    server.write_text(_MODEL_SERVER_SOURCE, encoding="utf-8")
    os.chmod(server, 0o700)
    manifests = model_dir / "Manifests"
    manifests.mkdir(mode=0o700, parents=True, exist_ok=True)
    return model_path


def _write_local_benchmark_proof(
    model_dir: Path, model_path: Path, model_id: str
) -> None:
    now = time.time()
    fingerprint = _sha256_bytes(str(model_path.resolve()).encode())
    quality = {
        "schema_valid": True,
        "citation_fidelity": True,
        "instruction_following": True,
        "tool_calling": True,
        "context_recall": True,
        "answer_correctness": True,
        "refusal_when_evidence_absent": True,
    }
    rows = []
    for role in ("chat", "source_synthesis", "study_fast"):
        rows.append(
            {
                "role": role,
                "label": role.replace("_", " ").title(),
                "status": "completed",
                "model_name": "study-proof-local",
                "model_path": str(model_path.resolve()),
                "model_runtime": "mlx",
                "model_id": model_id,
                "provider": "openai_compatible",
                "latency_ms": 1,
                "tokens_per_second": 100.0,
                "peak_memory_bytes": 32 * 1024 * 1024,
                "benchmark_fingerprint": fingerprint,
                "completed_at": now,
                "quality": quality,
                "normalized_metrics": {
                    "latency": 100.0,
                    "throughput": 100.0,
                    "schema": 100.0,
                    "citation": 100.0,
                    "instruction": 100.0,
                    "context": 100.0,
                    "correctness": 100.0,
                    "refusal": 100.0,
                },
                "score": 100.0,
            }
        )
    path = model_dir / "Manifests" / "deeper-notebook-benchmarks.json"
    path.write_text(
        json.dumps({"results": rows}, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (model_dir / "Manifests" / "model_inventory.md").write_text(
        "| Category | Role | Repo | Local path | Runtime | Status | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| Study | Primary study | study-proof-local | {model_path.resolve()} | mlx | installed verified | local study fast source synthesis chat |\n",
        encoding="utf-8",
    )


def _seed_model(
    api_url: str, model_url: str, *, token: str | None = None
) -> dict[str, str]:
    credential = _expect(
        _http_request(
            api_url,
            "POST",
            "/api/credentials",
            token=token,
            payload={
                "name": "Task-owned local proof",
                "provider": "openai_compatible",
                "modalities": ["language", "embedding"],
                "api_key": "task-proof-key",
                "base_url": model_url,
            },
        ),
        {200, 201},
        "credential_create",
    )
    credential_id = credential.get("id") if isinstance(credential, dict) else None
    if not isinstance(credential_id, str):
        raise ProofRefusal("credential_id_missing")
    model = _expect(
        _http_request(
            api_url,
            "POST",
            "/api/models",
            token=token,
            payload={
                "name": "study-proof-local",
                "provider": "openai_compatible",
                "type": "language",
                "credential": credential_id,
            },
        ),
        {200, 201},
        "model_create",
    )
    model_id = model.get("id") if isinstance(model, dict) else None
    if not isinstance(model_id, str):
        raise ProofRefusal("model_id_missing")
    stt_model = _expect(
        _http_request(
            api_url,
            "POST",
            "/api/models",
            token=token,
            payload={
                "name": "study-proof-local-stt",
                "provider": "openai_compatible",
                "type": "speech_to_text",
                "credential": credential_id,
            },
        ),
        {200, 201},
        "stt_model_create",
    )
    stt_model_id = stt_model.get("id") if isinstance(stt_model, dict) else None
    if not isinstance(stt_model_id, str):
        raise ProofRefusal("stt_model_id_missing")
    _expect(
        _http_request(
            api_url,
            "PUT",
            "/api/models/defaults",
            token=token,
            payload={
                "default_chat_model": model_id,
                "large_context_model": model_id,
                "default_tools_model": model_id,
                "default_speech_to_text_model": stt_model_id,
            },
        ),
        {200},
        "defaults_update",
    )
    return {
        "credential_id": credential_id,
        "model_id": model_id,
        "stt_model_id": stt_model_id,
        "model_url": model_url,
    }


class Stack:
    def __init__(self, inputs: Inputs, *, model_url: str):
        self.inputs = inputs
        self.model_url = model_url
        self.children: list[OwnedChild] = []
        # The prepare and verify invocations are separate processes.  A
        # random bootstrap password would make the persisted Surreal root
        # account unreachable after restart; derive a disposable task-local
        # value instead of writing credentials into the receipt.
        self.password = _task_surreal_password(inputs)
        self.container_name = (
            "dn-study-" + _sha256_bytes(str(inputs.task_root.resolve()).encode())[:12]
        )
        self.container_id: str | None = None
        self.seed: dict[str, str] = {}
        self.model_path = _prepare_local_model_fixture(inputs.task_root)

    def _refresh(self, child: OwnedChild, *, listener_port: int | None = None) -> None:
        child.identity = process_identity(
            child.process.pid,
            child.identity.role,
            listener_port or child.identity.listener_port,
        )

    def _docker(self) -> Path:
        docker = shutil.which("docker")
        if not docker:
            raise ProofRefusal("docker_unavailable")
        candidate = Path(docker)
        if not candidate.is_file() or not os.access(candidate.resolve(), os.X_OK):
            raise ProofRefusal("docker_binary_invalid")
        resolved = candidate.resolve()
        allowed_prefixes = (
            Path("/Applications/Docker.app/Contents/Resources/bin"),
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
        )
        if not any(
            _inside(resolved, prefix) or resolved == prefix / "docker"
            for prefix in allowed_prefixes
        ):
            raise ProofRefusal("docker_binary_invalid")
        return resolved

    def _container_identity(self, docker: Path) -> tuple[str, str] | None:
        try:
            result = subprocess.run(
                [
                    str(docker),
                    "inspect",
                    "--format",
                    '{{.Id}} {{.Name}} {{index .Config.Labels "com.deeper-notebook.study-proof"}}',
                    self.container_name,
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        fields = result.stdout.strip().split()
        if (
            len(fields) != 3
            or fields[1] != f"/{self.container_name}"
            or fields[2] != "1"
        ):
            raise ProofRefusal("surreal_container_identity_mismatch")
        if not re.fullmatch(r"[a-f0-9]{12,64}", fields[0]):
            raise ProofRefusal("surreal_container_identity_invalid")
        return fields[0], fields[1].lstrip("/")

    def _start_surreal(self, env: Mapping[str, str]) -> None:
        docker = self._docker()
        data = self.inputs.task_root / "surreal-data"
        data.mkdir(mode=0o700, parents=True, exist_ok=True)
        args = [
            str(docker),
            "run",
            "--rm",
            "--name",
            self.container_name,
            "--label",
            "com.deeper-notebook.study-proof=1",
            "--label",
            f"com.deeper-notebook.study-root={self.inputs.task_root.name}",
            "-p",
            f"127.0.0.1:{self.inputs.surreal_port}:8000",
            "-v",
            f"{data}:/data",
            "surrealdb/surrealdb:v2",
            "start",
            "--log",
            "warn",
            "--user",
            "root",
            "--pass",
            self.password,
            "file:/data",
        ]
        existing = self._container_identity(docker)
        if existing is not None:
            raise ProofRefusal("surreal_container_name_already_owned")
        child = _spawn_owned(
            args,
            role="surreal",
            cwd=self.inputs.task_root,
            env=env,
            listener_port=self.inputs.surreal_port,
            log_dir=self.inputs.task_root,
        )
        self.children.append(child)
        try:
            _wait_port(self.inputs.surreal_port, time.monotonic() + 45)
            identity = self._container_identity(docker)
            if identity is None:
                raise ProofRefusal("surreal_container_not_running")
            self.container_id = identity[0]
        except Exception:
            stop_owned([child])
            raise

    def _remove_surreal(self) -> None:
        docker = self._docker()
        current = self._container_identity(docker)
        if current is None:
            return
        if self.container_id is not None and current[0] != self.container_id:
            raise ProofRefusal("surreal_container_identity_mismatch")
        result = subprocess.run(
            [str(docker), "rm", "-f", self.container_name],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0 and self._container_identity(docker) is not None:
            raise ProofRefusal("surreal_container_cleanup_failed")

    def start(self, *, seed_model: bool = False, token: str | None = None) -> None:
        root = self.inputs.task_root
        env = dict(os.environ)
        for key in tuple(env):
            if (
                "PASSWORD" in key
                or "API_KEY" in key
                or key.startswith(("OPENAI_", "ANTHROPIC_", "GOOGLE_", "GEMINI_"))
            ):
                env.pop(key, None)
        model_dir = root / "models"
        env.update(
            {
                "HOME": str(root / "home"),
                "USERPROFILE": str(root / "home"),
                "DEEPER_NOTEBOOK_DATA_DIR": str(root / "desktop-data"),
                "DATA_FOLDER": str(root / "data"),
                "SURREAL_USER": "root",
                "SURREAL_PASSWORD": self.password,
                "SURREAL_NAMESPACE": self.inputs.namespace,
                "SURREAL_DATABASE": self.inputs.database,
                "SURREAL_URL": f"ws://127.0.0.1:{self.inputs.surreal_port}/rpc",
                "API_PORT": str(self.inputs.api_port),
                "DEEPER_NOTEBOOK_ENCRYPTION_KEY": _sha256_bytes(os.urandom(32)),
                "DEEPER_NOTEBOOK_STUDY_WORKBENCH": "1",
                "DEEPER_NOTEBOOK_PASSWORD": "",
                "OPENAI_COMPATIBLE_BASE_URL": self.model_url,
                "OPENAI_COMPATIBLE_API_KEY": "task-proof-key",
                "DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL": self.model_url,
                "DEEPER_NOTEBOOK_MODEL_DIR": str(model_dir),
                "DEEPER_NOTEBOOK_MODEL_DIR_DEFAULT": str(model_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        for path in (root / "home", root / "desktop-data", root / "data", model_dir):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(path, 0o700)
        self._start_model(env)
        self._start_surreal(env)
        python = sys.executable
        api_child = _spawn_owned(
            [
                python,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.inputs.api_port),
            ],
            role="api",
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            listener_port=self.inputs.api_port,
            log_dir=self.inputs.task_root,
        )
        self.children.append(api_child)
        _wait_port(self.inputs.api_port, time.monotonic() + 90)
        self._refresh(api_child, listener_port=self.inputs.api_port)
        if not _listener_pids(self.inputs.api_port):
            raise ProofRefusal("api_listener_not_owned")
        self.children.append(
            _spawn_owned(
                [
                    python,
                    "-m",
                    "surreal_commands.cli.worker",
                    "--import-modules",
                    "commands",
                    "--max-tasks",
                    "1",
                ],
                role="worker",
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                log_dir=self.inputs.task_root,
            )
        )
        if seed_model:
            self.seed = _seed_model(self.inputs.api_url, self.model_url, token=token)
            _write_local_benchmark_proof(
                model_dir, self.model_path, self.seed["model_id"]
            )
        elif not (
            model_dir / "Manifests" / "deeper-notebook-benchmarks.json"
        ).is_file():
            raise ProofRefusal("local_benchmark_receipt_missing")
        frontend_dir = (
            self.inputs.frontend_dir or Path(__file__).resolve().parents[1] / "frontend"
        )
        if not (frontend_dir / ".next").is_dir():
            raise ProofRefusal("frontend_build_missing")
        server = frontend_dir / "start-server.js"
        node = shutil.which("node")
        if not node or not server.is_file() or server.is_symlink():
            raise ProofRefusal("frontend_server_unavailable")
        frontend_env = dict(env)
        frontend_env.update(
            {
                "API_URL": self.inputs.api_url,
                "INTERNAL_API_URL": self.inputs.api_url,
                "NEXT_PUBLIC_API_URL": self.inputs.api_url,
                "NEXT_PUBLIC_DN_STUDY_WORKBENCH": "1",
                "NEXT_PUBLIC_DN_LUMINOUS_FOLIO": "1",
                "HOSTNAME": "127.0.0.1",
                "PORT": str(self.inputs.frontend_port),
            }
        )
        frontend_child = _spawn_owned(
            [str(Path(node).resolve()), str(server)],
            role="frontend",
            cwd=frontend_dir,
            env=frontend_env,
            listener_port=self.inputs.frontend_port,
            log_dir=self.inputs.task_root,
        )
        self.children.append(frontend_child)
        _wait_port(self.inputs.frontend_port, time.monotonic() + 90)
        self._refresh(frontend_child, listener_port=self.inputs.frontend_port)
        if not _listener_pids(self.inputs.frontend_port):
            raise ProofRefusal("frontend_listener_not_owned")

    def _start_model(self, env: Mapping[str, str]) -> None:
        script = self.inputs.task_root / "study-proof-model-server.py"
        child_env = dict(env)
        child_env["MODEL_PORT"] = str(self.inputs.model_port)
        child = _spawn_owned(
            [sys.executable, str(script)],
            role="model",
            cwd=self.inputs.task_root,
            env=child_env,
            listener_port=self.inputs.model_port,
            log_dir=self.inputs.task_root,
        )
        self.children.append(child)
        _wait_port(self.inputs.model_port, time.monotonic() + 20)
        self._refresh(child, listener_port=self.inputs.model_port)
        if not _listener_pids(self.inputs.model_port):
            raise ProofRefusal("model_listener_not_owned")

    def stop(self) -> int:
        stopped = stop_owned(self.children)
        self._remove_surreal()
        return stopped


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify isolated Study Workbench durability"
    )
    parser.add_argument(
        "--proof-phase", choices=("check", "prepare", "verify"), required=True
    )
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--external-sentinel-root", required=True, type=Path)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--api-port", required=True, type=int)
    parser.add_argument("--frontend-port", required=True, type=int)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--surreal-port", type=int, default=0)
    parser.add_argument("--model-port", type=int, default=0)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--auth-token-file", type=Path)
    parser.add_argument("--surreal-binary", type=Path)
    parser.add_argument("--frontend-dir", type=Path)
    return parser


def _inputs(namespace: argparse.Namespace) -> Inputs:
    task = validate_task_root(namespace.task_root)
    external = validate_external_root(namespace.external_sentinel_root, task)
    api_url = validate_loopback_url(namespace.api_url)
    frontend_url = validate_loopback_url(namespace.frontend_url)
    api_port = _validate_port(namespace.api_port, "api")
    frontend_port = _validate_port(namespace.frontend_port, "frontend")
    surreal_port = _validate_port(namespace.surreal_port or api_port + 1, "surreal")
    model_port = _validate_port(namespace.model_port or api_port + 2, "model")
    if len({api_port, frontend_port, surreal_port, model_port}) != 4:
        raise ProofRefusal("task_ports_must_be_unique")
    if (
        urllib.parse.urlsplit(api_url).port != api_port
        or urllib.parse.urlsplit(frontend_url).port != frontend_port
    ):
        raise ProofRefusal("url_port_mismatch")
    report = namespace.report_path or task.parent / "study-workbench-report.md"
    report = Path(os.path.abspath(os.fspath(report)))
    if report.is_symlink():
        raise ProofRefusal("report_path_invalid")
    report = report.resolve(strict=False)
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if (
        report.name != "study-workbench-report.md"
        or report.parent != task.parent
        or _inside(report, task)
        or _inside(report, external)
        or report == task / RECEIPT_NAME
        or not report.parent.is_dir()
        or report.parent.is_symlink()
    ):
        raise ProofRefusal("report_path_invalid")
    _reject_symlink_components(report.parent, temp_root)
    report_parent_stat = report.parent.stat()
    if stat.S_IMODE(report_parent_stat.st_mode) != 0o700:
        raise ProofRefusal("report_path_invalid")
    report_marker = report.parent / REPORT_MARKER
    if (
        report_marker.is_symlink()
        or not report_marker.is_file()
        or report_marker.read_text(encoding="utf-8").strip() != REPORT_MARKER_VALUE
    ):
        raise ProofRefusal("report_path_not_owned")
    if report.exists() and not report.is_symlink():
        try:
            if not report.read_text(encoding="utf-8").startswith(
                "# Study Workbench verification"
            ):
                raise ProofRefusal("report_path_not_owned")
        except UnicodeError as exc:
            raise ProofRefusal("report_path_not_owned") from exc
    token = namespace.auth_token_file
    if token is not None:
        token = Path(os.path.abspath(os.fspath(token)))
        if token.is_symlink() or not token.is_file() or token.stat().st_mode & 0o077:
            raise ProofRefusal("auth_token_file_invalid")
    return Inputs(
        task,
        external,
        api_url,
        frontend_url,
        api_port,
        frontend_port,
        _validate_namespace(namespace.namespace),
        _validate_database(namespace.database),
        report,
        surreal_port,
        model_port,
        token,
        namespace.surreal_binary,
        namespace.frontend_dir,
    )


def _read_token(path: Path | None) -> str | None:
    if path is None:
        return None
    value = path.read_text(encoding="utf-8").strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ProofRefusal("auth_token_file_invalid")
    return value


def _run_real_phase(inputs: Inputs, phase: str) -> int:
    receipt_path = inputs.task_root / RECEIPT_NAME
    external_before = hash_tree(inputs.external_root)
    fixtures = (
        _synthetic_fixtures(inputs.task_root)
        if phase == "prepare"
        else {
            name: inputs.task_root / "fixtures" / f"study-proof.{ext}"
            for name, ext in (("pdf", "pdf"), ("video", "mp4"))
        }
    )
    source_before = _source_hashes(fixtures)
    token = _read_token(inputs.auth_token_file)
    children: list[OwnedChild] = []
    stack: Stack | None = None
    interrupt_cleanup = InterruptCleanup(lambda: stack)
    interrupt_cleanup.install()
    state: dict[str, Any] = {}
    blocker = "none"
    outcome = "PASSED"
    return_code = 3
    trace = {"code": "phase_start"}
    try:
        if phase == "prepare":
            if receipt_path.exists():
                raise ProofRefusal("restart_proof_already_exists")
            model_url = f"http://127.0.0.1:{inputs.model_port}/v1"
            stack = Stack(inputs, model_url=model_url)
            trace["code"] = "stack_start"
            stack.start(seed_model=True, token=token)
            children = stack.children
            state = _workflow(
                inputs.api_url,
                inputs.frontend_url,
                fixtures,
                token=token,
                model_url=model_url,
                seed=stack.seed,
                trace=trace,
            )
            identities = tuple(item.identity for item in children)
            api_identity = next(
                (item for item in identities if item.role == "api"), None
            )
            if api_identity is None:
                raise ProofRefusal("api_identity_missing")
            external_after = hash_tree(inputs.external_root)
            if external_after != external_before:
                raise ProofRefusal("external_fixture_changed")
            receipt = RestartReceipt(
                version=1,
                phase="awaiting_restart",
                task_root_sha256=_sha256_bytes(
                    str(inputs.task_root.resolve()).encode()
                ),
                namespace=inputs.namespace,
                database=inputs.database,
                previous_api_pid=api_identity.pid,
                previous_api_start_token=api_identity.start_token,
                previous_api_argv_sha256=api_identity.argv_sha256,
                previous_listener_port=inputs.api_port,
                source_hashes=source_before,
                external_hashes=external_before,
                external_writes=0,
                previous_processes=identities,
                source_ids=tuple(state.get("source_ids", [])),
                plan_id=state.get("plan_id"),
                syllabus_version=state.get("syllabus_version"),
                artifact_ids=tuple(state.get("artifact_ids", [])),
                card_id=state.get("card_id"),
                anki_job_id=state.get("anki_job_id"),
                anki_receipt_id=state.get("anki_receipt_id"),
                frontend_port=inputs.frontend_port,
                surreal_port=inputs.surreal_port,
                model_port=inputs.model_port,
                surreal_container_name=stack.container_name,
                surreal_container_id=stack.container_id,
                anki_download_id=state.get("anki_download_id"),
                anki_publish_receipt_id=state.get("anki_publish_receipt_id"),
            )
            validate_restart_receipt(receipt, inputs.task_root, inputs)
            _write_receipt(receipt_path, receipt)
            return_code = 5
            blocker = "external_restart_required"
        else:
            trace["code"] = "receipt_read_call"
            receipt = _read_receipt(receipt_path, inputs.task_root)
            trace["code"] = "receipt_read_done"
            validate_restart_receipt(receipt, inputs.task_root, inputs)
            trace["code"] = "receipt_validated"
            trace["code"] = "external_hash_check"
            if hash_tree(inputs.external_root) != receipt.external_hashes:
                raise ProofRefusal("external_fixture_changed_before_restart_resume")
            trace["code"] = "source_hash_check"
            if _source_hashes(fixtures) != receipt.source_hashes:
                raise ProofRefusal("source_fixture_changed_before_restart_resume")
            trace["code"] = "previous_process_check"
            if not previous_processes_are_gone(receipt):
                raise ProofRefusal("native_restart_previous_process_alive")
            trace["code"] = "prior_identity"
            stack = Stack(inputs, model_url=f"http://127.0.0.1:{inputs.model_port}/v1")
            previous_container = stack._container_identity(stack._docker())
            if previous_container is not None:
                raise ProofRefusal("native_restart_previous_container_alive")
            trace["code"] = "new_stack_start"
            stack.start(seed_model=False, token=token)
            children = stack.children
            current_api = next(
                (item.identity for item in children if item.identity.role == "api"),
                None,
            )
            if (
                current_api is None
                or current_api.pid == receipt.previous_api_pid
                or current_api.start_token == receipt.previous_api_start_token
            ):
                raise ProofRefusal("native_restart_identity_not_new")
            state = {
                "plan_id": receipt.plan_id,
                "source_ids": receipt.source_ids,
                "card_id": receipt.card_id,
                "anki_job_id": receipt.anki_job_id,
            }
            trace["code"] = "restart_workflow"
            _workflow(
                inputs.api_url,
                inputs.frontend_url,
                fixtures,
                token=token,
                existing=state,
                model_url=stack.model_url,
                trace=trace,
            )
            trace["code"] = "restart_finalization"
            if hash_tree(inputs.external_root) != receipt.external_hashes:
                raise ProofRefusal("external_fixture_changed")
            _write_receipt(receipt_path, replace(receipt, phase="complete"))
            return_code = 0
    except KeyboardInterrupt:
        outcome = "BLOCKED"
        blocker = "interrupted:cooperative_cleanup_complete"
        return_code = 130
    except ProofRefusal as exc:
        outcome = "BLOCKED"
        blocker = str(exc)
        return_code = 3
    except Exception:
        outcome = "BLOCKED"
        # Keep unexpected verifier failures fail-closed while preserving only
        # an allowlisted stage code. Exception text can contain credentials or
        # source content and must never enter the report.
        blocker = _internal_blocker(trace.get("code"))
        return_code = 3
    finally:
        interrupt_cleanup.cleanup()
        interrupt_cleanup.restore()
        if interrupt_cleanup.error is not None:
            outcome = "BLOCKED"
            blocker = "owned_cleanup_failed"
            return_code = 3
        report_payload = {
            "phase": phase,
            "outcome": outcome,
            "blocker": blocker,
            "namespace": inputs.namespace,
            "database": inputs.database,
            "api_port": inputs.api_port,
            "frontend_port": inputs.frontend_port,
            "source_hashes": source_before,
            "external_hashes": external_before,
            "external_writes": 0,
            "processes": [
                {
                    "role": child.identity.role,
                    "pid": child.identity.pid,
                    "start_token_sha256": _sha256_bytes(
                        child.identity.start_token.encode()
                    ),
                    "argv_sha256": child.identity.argv_sha256,
                }
                for child in children
            ],
            "frontend": "study route checked",
            "supervisor": "verifier-local production command supervisor; desktop Supervisor not used because it binds canonical user state",
        }
        try:
            _write_report(inputs.report_path, report_payload)
        except Exception:
            outcome = "BLOCKED"
            blocker = "report_write_failed"
            return_code = 3
        if phase == "verify" and return_code == 0:
            try:
                validate_task_root(inputs.task_root)
                inputs.task_root / RECEIPT_NAME
                shutil.rmtree(inputs.task_root)
            except Exception:
                return_code = 3
    return return_code


class _FixtureState:
    def __init__(self) -> None:
        self.plan_id = "study_plan:fixture"
        self.sources = {
            "source:pdf": "Synthetic PDF evidence.",
            "source:video": "Synthetic video evidence.",
        }
        self.card_id = "study_card:fixture"
        self.anki_job = "anki_job:fixture"


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    state = _FixtureState()

    def _json(self, status: int, payload: object, body: bytes | None = None) -> None:
        raw = (
            body
            if body is not None
            else json.dumps(payload, separators=(",", ":")).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _payload(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        try:
            return json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            self.rfile.read(size)
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in {"/readyz", "/api/auth/status", "/api/credentials/status"}:
            self._json(
                200,
                {"auth_enabled": False}
                if path.endswith("auth/status")
                else {"status": "ready"},
            )
        elif path == "/api/study/cards/due":
            self._json(200, [{"id": self.state.card_id}])
        elif path == "/study":
            self._json(200, {"marker": "Study"})
        elif path.startswith("/api/sources/") and path.endswith("/status"):
            self._json(200, {"status": "completed"})
        elif path.startswith("/api/sources/"):
            source_id = path.split("/")[3]
            self._json(
                200,
                {
                    "id": source_id,
                    "full_text": self.state.sources.get(
                        source_id, "Synthetic evidence."
                    ),
                    "status": "completed",
                },
            )
        elif path.startswith("/api/study/plans/") and path.endswith("/progress"):
            self._json(
                200,
                {"plan_id": self.state.plan_id, "completed_count": 1, "total_count": 1},
            )
        elif path.startswith("/api/study/plans/") and "/anki/import/" in path:
            self._json(
                200,
                {
                    "job_id": self.state.anki_job,
                    "status": "published",
                    "card_count": 1,
                    "transformed_count": 1,
                    "skipped_count": 0,
                    "rejected_count": 0,
                    "package_sha256": "a" * 64,
                    "collection_member": "collection.anki2",
                    "receipt_id": "anki_receipt:fixture",
                },
            )
        elif path.startswith("/api/study/plans/") and path.endswith(
            "/sources/readiness"
        ):
            self._json(
                200,
                {
                    "ready": True,
                    "items": [
                        {
                            "source_id": "source:pdf",
                            "title": "Synthetic PDF",
                            "kind": "upload",
                            "ready": True,
                            "command_id": None,
                            "fingerprint_status": "available",
                            "reason": "ready",
                        },
                        {
                            "source_id": "source:video",
                            "title": "Synthetic video",
                            "kind": "upload",
                            "ready": True,
                            "command_id": None,
                            "fingerprint_status": "available",
                            "reason": "ready",
                        },
                    ],
                },
            )
        elif path.startswith("/api/study/plans/") and path.endswith("/syllabus"):
            self._json(
                200,
                {
                    "plan_id": self.state.plan_id,
                    "version": 1,
                    "source_manifest_sha256": "b" * 64,
                    "units": [
                        {
                            "unit_id": "foundations",
                            "title": "Foundations",
                            "objectives": ["Explain"],
                            "prerequisite_unit_ids": [],
                            "estimated_minutes": 10,
                            "source_ids": ["source:pdf"],
                            "activities": [],
                        }
                    ],
                    "approved_at": "2026-08-12T12:00:00Z",
                },
            )
        elif path.startswith("/api/study/plans/"):
            # The fixture is intentionally already at the approved revision
            # after the lifecycle calls above; mirror the production plan
            # projection used by the post-approval authoritative read.
            self._json(
                200,
                {
                    "plan_id": self.state.plan_id,
                    "goal": "Synthetic",
                    "starting_level": "beginner",
                    "source_links": [
                        {"source_id": "source:pdf"},
                        {"source_id": "source:video"},
                    ],
                    "state": "approved",
                    "version": 4,
                },
            )
        elif path.startswith("/api/study/plans/anki/download/"):
            self._json(200, {}, body=b"fixture-anki-package")
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/api/credentials":
            self._payload()
            self._json(201, {"id": "credential:fixture"})
        elif path == "/api/models":
            self._payload()
            self._json(201, {"id": "model:fixture"})
        elif path == "/api/sources":
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            source_id = "source:pdf" if b"study-proof.pdf" in body else "source:video"
            self._json(
                201, {"id": source_id, "full_text": self.state.sources[source_id]}
            )
        elif path == "/api/study/plans":
            self._payload()
            self._json(
                201,
                {
                    "plan_id": self.state.plan_id,
                    "version": 1,
                    "state": "draft",
                    "source_links": [],
                },
            )
        elif path.startswith("/api/sources/") and path.endswith("/locate-passage"):
            payload = self._payload()
            source_id = path.split("/")[3]
            text = self.state.sources.get(source_id, "Synthetic evidence.")
            query = str(payload.get("query", ""))
            snippet = (
                text if query and query.split()[0].lower() in text.lower() else None
            )
            self._json(
                200,
                {
                    "match": {
                        "start": 0,
                        "end": len(snippet),
                        "score": 1.0,
                        "snippet": snippet,
                    }
                    if snippet
                    else None
                },
            )
        elif path.endswith("/syllabus:propose"):
            self._payload()
            self._json(
                200,
                {
                    "plan_id": self.state.plan_id,
                    "version": 1,
                    "source_manifest_sha256": "b" * 64,
                    "units": [
                        {
                            "unit_id": "foundations",
                            "title": "Foundations",
                            "objectives": ["Explain"],
                            "prerequisite_unit_ids": [],
                            "estimated_minutes": 10,
                            "source_ids": ["source:pdf"],
                            "activities": [],
                        }
                    ],
                },
            )
        elif path.endswith("/syllabus:approve"):
            self._payload()
            self._json(
                200, {"plan_id": self.state.plan_id, "version": 4, "state": "approved"}
            )
        elif path.endswith("/generate"):
            self._payload()
            self._json(
                200,
                {
                    "plan_id": self.state.plan_id,
                    "unit_id": "foundations",
                    "artifacts": [
                        {
                            "artifact_id": "study_artifact:fixture",
                            "artifact_type": "study_guide",
                            "status": "completed",
                            "unit_id": "foundations",
                        }
                    ],
                },
            )
        elif "/assistants/" in path:
            role = path.split("/assistants/", 1)[1].split(":", 1)[0]
            self._payload()
            self._json(
                200,
                {
                    "plan_id": self.state.plan_id,
                    "role": role,
                    "authority": "ask",
                    "answer": "Synthetic cited explanation.",
                    "citations": [{"source_id": "source:pdf", "quote": "Synthetic"}],
                    "proposed_actions": [],
                },
            )
        elif path == "/api/study/cards":
            self._payload()
            self._json(201, {"id": self.state.card_id})
        elif path.startswith("/api/study/cards/") and path.endswith("/reviews"):
            self._payload()
            self._json(
                200,
                {
                    "card": {"id": self.state.card_id},
                    "review": {"request_id": "study-proof-review-1"},
                },
            )
        elif path.endswith("/anki/export"):
            self._payload()
            self._json(
                200,
                {
                    "download_id": "anki_download:fixture",
                    "receipt": {"receipt_id": "anki_receipt:fixture"},
                },
            )
        elif path.endswith("/anki/import"):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self._json(
                201,
                {
                    "job_id": self.state.anki_job,
                    "status": "preview_ready",
                    "package_sha256": "a" * 64,
                    "collection_member": "collection.anki2",
                },
            )
        elif ":publish" in path:
            self._payload()
            self._json(
                200,
                {
                    "status": "published",
                    "receipt": {"receipt_id": "anki_receipt:fixture"},
                },
            )
        else:
            self._json(200, {"source_id": "source:pdf"})

    def do_PUT(self) -> None:  # noqa: N802
        self._payload()
        self._json(
            200, {"plan_id": self.state.plan_id, "version": 3, "state": "editing"}
        )

    def log_message(self, *_args: object) -> None:
        return


def _reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_verifier_fixture(tmp_path: Path) -> FixtureResult:
    """Deterministic local proof used only by verifier unit tests."""
    task = tmp_path / "study-task"
    external = tmp_path / "study-external"
    task.mkdir(mode=0o700)
    external.mkdir(mode=0o700)
    (task / TASK_MARKER).write_text(TASK_MARKER_VALUE + "\n", encoding="utf-8")
    (external / EXTERNAL_MARKER).write_text(
        EXTERNAL_MARKER_VALUE + "\n", encoding="utf-8"
    )
    os.chmod(task, 0o700)
    os.chmod(external, 0o700)
    (external / "sentinel.txt").write_text("immutable sentinel\n", encoding="utf-8")
    fixtures = _synthetic_fixtures(task)
    source_manifest = _source_hashes(fixtures)
    source_digest_before = _tree_digest(source_manifest)
    external_before = hash_tree(external)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    children: list[OwnedChild] = []
    try:
        for role in ("api", "frontend", "model"):
            children.append(
                _spawn_owned(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    role=role,
                    cwd=task,
                    env=os.environ.copy(),
                )
            )
        state = _workflow(url, url, fixtures)
        api_child = next(item for item in children if item.identity.role == "api")
        receipt = RestartReceipt(
            1,
            "awaiting_restart",
            _sha256_bytes(str(task.resolve()).encode()),
            "study_ns_fixture000000",
            "study_db_fixture000000",
            api_child.identity.pid,
            api_child.identity.start_token,
            api_child.identity.argv_sha256,
            server.server_address[1],
            source_manifest,
            external_before,
            0,
            tuple(item.identity for item in children),
            tuple(state["source_ids"]),
            state["plan_id"],
            1,
            tuple(state.get("artifact_ids", [])),
            state.get("card_id"),
            state.get("anki_job_id"),
            state.get("anki_receipt_id"),
        )
        _write_receipt(task / RECEIPT_NAME, receipt)
        prepare_exit = 5
        stop_owned(children)
        children = []
        loaded = _read_receipt(task / RECEIPT_NAME, task)
        if any(_process_matches(item) for item in loaded.previous_processes):
            raise ProofRefusal("native_restart_previous_process_alive")
        for role in ("api", "frontend", "model"):
            children.append(
                _spawn_owned(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    role=role,
                    cwd=task,
                    env=os.environ.copy(),
                )
            )
        _workflow(
            url,
            url,
            fixtures,
            existing={
                "plan_id": loaded.plan_id,
                "source_ids": loaded.source_ids,
                "card_id": loaded.card_id,
                "anki_job_id": loaded.anki_job_id,
            },
        )
        stop_owned(children)
        children = []
        external_after = hash_tree(external)
        if external_after != external_before:
            raise ProofRefusal("external_fixture_changed")
        source_digest_after = _tree_digest(_source_hashes(fixtures))
        shutil.rmtree(task)
        return FixtureResult(
            prepare_exit,
            0,
            source_digest_before,
            source_digest_after,
            0,
            CleanupReceipt(0, 0, 0, loaded.namespace, loaded.database),
        )
    finally:
        stop_owned(children)
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        if task.exists():
            shutil.rmtree(task)


def main(argv: list[str] | None = None) -> int:
    try:
        namespace = _parser().parse_args(argv)
        inputs = _inputs(namespace)
        if namespace.proof_phase == "check":
            print(
                "CHECK ONLY: isolated roots, explicit ports, namespace, and database are valid; no network or mutation performed."
            )
            return 0
        return _run_real_phase(inputs, namespace.proof_phase)
    except ProofRefusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("verification_internal_error", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
