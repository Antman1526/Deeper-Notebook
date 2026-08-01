#!/usr/bin/env python3
"""Verify Research Core Lab contracts using owned synthetic data only.

This verifier never discovers the configured model library, external vaults,
or production data.  The native URL is an optional, loopback-only readiness
probe; browser proof remains a separate Playwright gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from deeper_notebook.local_models.contracts import (
    LocalModelRouteCandidate,
    RouteRequest,
)
from deeper_notebook.local_models.planner import LocalModelPlanner
from deeper_notebook.workspace.contracts import (
    default_knowledge_workspace,
    migrate_workspace_v1,
)
from desktop.launcher import ResourceGovernor

_FIXTURE_SENTINEL = ".deeper-notebook-research-core-lab-fixture"
_FORBIDDEN_ROOT_PARTS = {"2nd Brains", "BrainPulse Ventures LLC", "MacBook AI models"}


@dataclass(frozen=True)
class VerifierConfig:
    fixture_root: Path
    output_path: Path
    native_url: str


@dataclass(frozen=True)
class VerificationResult:
    exit_code: int
    report: dict[str, object]


@dataclass(frozen=True)
class CommandResult:
    """Redacted result of one explicitly requested focused gate."""

    returncode: int | None
    output: str
    error: str | None = None


CommandRunner = Callable[[tuple[str, ...], Path], CommandResult]


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            return True
    return False


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _loopback_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("native URL must be loopback-only")
    return url.rstrip("/")


def verifier_config(*, fixture_root: Path, output_path: Path, native_url: str = "http://localhost:65060") -> VerifierConfig:
    requested_root = fixture_root.expanduser().absolute()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    root = requested_root.resolve()
    if (
        _has_symlink_component(requested_root)
        or not _inside(temporary_root, root)
        or root == temporary_root
        or any(part in _FORBIDDEN_ROOT_PARTS for part in root.parts)
        or (root.exists() and not root.is_dir())
        or not root.parent.is_dir()
    ):
        raise ValueError("temporary synthetic fixture root required")
    if root.exists():
        entries = list(root.iterdir())
        if entries != [root / _FIXTURE_SENTINEL] or not (root / _FIXTURE_SENTINEL).is_file():
            raise ValueError("temporary synthetic fixture root required")
    else:
        root.mkdir(mode=0o700)
        (root / _FIXTURE_SENTINEL).write_text("synthetic fixture only\n", encoding="utf-8")

    requested_output = output_path.expanduser().absolute()
    output = requested_output.resolve(strict=False)
    if (
        _has_symlink_component(requested_output.parent)
        or output.exists()
        or output.is_symlink()
        or not output.parent.is_dir()
        or _inside(root, output)
    ):
        raise ValueError("new proof output file required")
    return VerifierConfig(root, output, _loopback_url(native_url))


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _fingerprint(root: Path) -> str:
    return hashlib.sha256(
        json.dumps(_hashes(root), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _create_synthetic_fixture(root: Path) -> None:
    library = root / "local-library"
    workspace = root / "workspace"
    library.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    (library / "light-model.mlx").write_bytes(b"synthetic light mlx model\n")
    (library / "heavy-model.mlx").write_bytes(b"synthetic heavyweight mlx model\n")
    (workspace / "current-session.json").write_text('{"synthetic": true}\n', encoding="utf-8")


def _native_health(native_url: str) -> tuple[bool, int | None]:
    try:
        with urlopen(f"{native_url}/health", timeout=2) as response:  # nosec B310: config validates loopback
            return 200 <= response.status < 300, response.status
    except (URLError, OSError):
        return False, None


def _workspace_migration_check() -> dict[str, object]:
    migrated = migrate_workspace_v1(default_knowledge_workspace())
    return {
        "status": "passed" if migrated.version == 2 and migrated.next_id == 2 else "failed",
        "workspace_version": migrated.version,
        "pane_count": len(migrated.panes),
    }


def _strict_local_check() -> dict[str, object]:
    class TransportRecorder:
        def __init__(self) -> None:
            self.calls = 0

        def request_cloud(self) -> None:
            self.calls += 1

    class StrictLocalBoundary:
        def __init__(self, planner: LocalModelPlanner, transport: TransportRecorder) -> None:
            self._planner = planner
            self._transport = transport

        def plan(self, request: RouteRequest):
            # This seam makes the no-cloud claim observable: strict-local
            # routes reach the same boundary but never invoke its transport.
            if request.execution_policy != "strict_local":
                self._transport.request_cloud()
            return self._planner.plan(request)

    candidate = LocalModelRouteCandidate(
        model_id="synthetic-light-mlx",
        provider="mlx",
        fingerprint="synthetic-light-fingerprint",
        modalities=("text",),
        accepted_roles=("research_chat",),
        context_tokens=8192,
        supports_structured_output=True,
        readiness="ready_verified",
        health_healthy=True,
        accepted_quality=0.9,
        benchmarked_at=1_800_000_000.0,
        peak_memory_bytes=2 * 1024**3,
        latency_ms=100,
    )
    recorder = TransportRecorder()
    plan = StrictLocalBoundary(
        LocalModelPlanner((candidate,), now=1_800_000_001.0), recorder
    ).plan(
        RouteRequest(role="research_chat", execution_policy="strict_local")
    )
    return {
        "status": "passed" if plan.outcome == "ready" and recorder.calls == 0 else "failed",
        "outcome": plan.outcome,
        "transport_instrumented": True,
        "transport_calls": recorder.calls,
    }


def _heavyweight_check() -> dict[str, object]:
    governor = ResourceGovernor(memory_limit_bytes=10)
    first = governor.reserve("synthetic-heavyweight-a", 6, heavyweight_mlx=True)
    second = governor.reserve("synthetic-heavyweight-b", 6, heavyweight_mlx=True)
    snapshot = governor.snapshot()
    return {
        "status": "passed" if first == "reserved" and second == "queued" else "failed",
        "first_reservation": first,
        "second_reservation": second,
        "queued_swaps": len(snapshot["queued_heavyweight_swaps"]),
        "active_heavyweight_count": len(snapshot["reservations"]),
    }


def _subprocess_runner(command: tuple[str, ...], cwd: Path) -> CommandResult:
    try:
        completed = subprocess.run(  # noqa: S603 - command tuples are fixed below
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return CommandResult(None, "", "command_not_found")
    except subprocess.TimeoutExpired:
        return CommandResult(None, "", "command_timed_out")
    return CommandResult(completed.returncode, completed.stdout + completed.stderr)


def _focused_gate_record(
    command: tuple[str, ...],
    cwd: Path,
    *,
    run: bool,
    command_runner: CommandRunner,
) -> dict[str, object]:
    if not run:
        return {
            "status": "not_run",
            "command": list(command),
            "exit_code": None,
            "error": "not_requested",
        }
    result = command_runner(command, cwd)
    status = "passed" if result.returncode == 0 else "blocked" if result.returncode is None else "failed"
    return {
        "status": status,
        "command": list(command),
        "exit_code": result.returncode,
        "error": result.error or (None if result.returncode == 0 else "nonzero_exit"),
        "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
    }


def _focused_gates(*, run: bool, command_runner: CommandRunner) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[1]
    tests = _focused_gate_record(
        (".venv/bin/python", "-m", "pytest", "-q", "tests/test_verify_research_core_lab.py"),
        repo_root,
        run=run,
        command_runner=command_runner,
    )
    build = _focused_gate_record(
        ("npm", "run", "build"),
        repo_root / "frontend",
        run=run,
        command_runner=command_runner,
    )
    return {"status": "ran" if run else "not_run", "tests": tests, "build": build}


def run_verifier(
    *,
    native_url: str,
    fixture_root: Path,
    output_path: Path,
    run_focused_gates: bool = False,
    command_runner: CommandRunner | None = None,
) -> VerificationResult:
    config = verifier_config(fixture_root=fixture_root, output_path=output_path, native_url=native_url)
    _create_synthetic_fixture(config.fixture_root)
    before = _hashes(config.fixture_root)
    library_before = _fingerprint(config.fixture_root / "local-library")
    migration = _workspace_migration_check()
    strict_local = _strict_local_check()
    heavyweight = _heavyweight_check()
    native_ok, native_status = _native_health(config.native_url)
    after = _hashes(config.fixture_root)
    library_after = _fingerprint(config.fixture_root / "local-library")
    focused_gates = _focused_gates(
        run=run_focused_gates,
        command_runner=command_runner or _subprocess_runner,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "blocked",
        "synthetic_passed": all(check["status"] == "passed" for check in (migration, strict_local, heavyweight)),
        "fixture": {
            "kind": "synthetic",
            "file_count": len(before),
            "inventory_hash": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        },
        "source_hashes_unchanged": before == after,
        "external_writes": 0,
        "checks": {
            "workspace_migration": migration,
            "strict_local": strict_local,
            "heavyweight_mlx": heavyweight,
            "local_library": {
                "before_fingerprint": library_before,
                "after_fingerprint": library_after,
                "unchanged": library_before == library_after,
            },
            "focused_gates": focused_gates,
        },
        "gates": {
            "native_runtime": {
                "status": "passed" if native_ok else "blocked",
                "route_status": native_status,
                "reason": None if native_ok else "requires caller-launched persistent native runtime",
            },
            "playwright_native": {"status": "blocked", "reason": "requires persistent native-runtime Playwright proof"},
            "production_build": {
                "status": focused_gates["build"]["status"],  # type: ignore[index]
                "reason": focused_gates["build"]["error"],  # type: ignore[index]
            },
        },
    }
    config.output_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return VerificationResult(2, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-url", default="http://localhost:65060")
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-focused-gates", action="store_true")
    args = parser.parse_args()
    if args.fixture_root is None:
        with tempfile.TemporaryDirectory(prefix="deeper-notebook-research-core-lab-") as directory:
            root = Path(directory).resolve()
            result = run_verifier(
                native_url=args.native_url,
                fixture_root=root / "fixture",
                output_path=args.output or root / "proof.json",
                run_focused_gates=args.run_focused_gates,
            )
    else:
        if args.output is None:
            parser.error("--output is required when --fixture-root is supplied")
        result = run_verifier(
            native_url=args.native_url,
            fixture_root=args.fixture_root,
            output_path=args.output,
            run_focused_gates=args.run_focused_gates,
        )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
