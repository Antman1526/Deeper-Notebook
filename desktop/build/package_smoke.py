"""Run a packaged desktop smoke probe and write a JSON receipt."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, build_opener

RECEIPT_SCHEMA_VERSION = 2
MAX_TIMEOUT_SECONDS = 300.0
MAX_READINESS_BYTES = 64 * 1024
_LOCAL_OPENER = build_opener(ProxyHandler({}))
_MONITOR_FD_ENV = "DEEPER_NOTEBOOK_PACKAGE_SMOKE_MONITOR_FD"
_MONITOR_LIVENESS_FD_ENV = "DEEPER_NOTEBOOK_PACKAGE_SMOKE_MONITOR_LIVENESS_FD"
_MONITOR_SCRIPT = r'''
import json
import os
import signal
import subprocess
import sys
import threading
import time

descriptor = int(os.environ.pop("DEEPER_NOTEBOOK_PACKAGE_SMOKE_MONITOR_FD"))
liveness_descriptor = int(
    os.environ.pop("DEEPER_NOTEBOOK_PACKAGE_SMOKE_MONITOR_LIVENESS_FD")
)
try:
    application = subprocess.Popen(sys.argv[1:])
    os.write(descriptor, json.dumps({"pid": application.pid}).encode("utf-8"))
except BaseException as error:
    try:
        os.write(descriptor, json.dumps({"error": str(error)}).encode("utf-8"))
    finally:
        os.close(descriptor)
    raise
else:
    os.close(descriptor)

# Reap the direct application even when it exits before the smoke parent asks
# for cleanup. Its independently-forked descendants remain in this retained
# monitor's process group and are still visible to the parent proof.
threading.Thread(target=application.wait, daemon=True).start()

# Keep the group leader alive until the parent has proved that every child in
# the group has stopped.  In particular, do not let SIGTERM reap the leader
# while a stubborn descendant still owns its numeric process group.
signal.signal(signal.SIGTERM, lambda *_args: None)
signal.signal(signal.SIGINT, lambda *_args: None)
while True:
    time.sleep(1)
'''


class SmokeFailure(RuntimeError):
    """A required package proof did not complete."""


class SmokeArgumentParser(argparse.ArgumentParser):
    """Raise receipt-friendly errors instead of exiting before validation."""

    def error(self, message: str) -> None:
        raise SmokeFailure(message)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SmokeFailure(f"artifact does not exist: {path}")
    if path.stat().st_size == 0:
        raise SmokeFailure(f"artifact is empty: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_expected_hashes(values: list[str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for value in values:
        path, separator, digest = value.rpartition("=")
        if not separator or not path or len(digest) != 64:
            raise SmokeFailure(
                "expected artifact hashes must use PATH=64-character-sha256"
            )
        try:
            int(digest, 16)
        except ValueError as error:
            raise SmokeFailure(
                "expected artifact hashes must use PATH=64-character-sha256"
            ) from error
        expected[path] = digest.lower()
    return expected


def parse_environment(values: list[str]) -> dict[str, str]:
    """Parse explicit launcher environment overrides without shell expansion."""
    environment: dict[str, str] = {}
    for value in values:
        key, separator, setting = value.partition("=")
        if (
            not separator
            or not key
            or "\x00" in key
            or "\x00" in setting
        ):
            raise SmokeFailure("environment values must use KEY=VALUE")
        environment[key] = setting
    return environment


def parse_expected_features(values: list[str]) -> dict[str, bool]:
    """Parse feature assertions supplied by the smoke caller."""
    expected: dict[str, bool] = {}
    for value in values:
        name, separator, raw_value = value.partition("=")
        if not separator or not name or raw_value not in {"true", "false"}:
            raise SmokeFailure("expected features must use NAME=BOOL (true or false)")
        expected[name] = raw_value == "true"
    return expected


def check_artifact_signatures(
    artifacts: list[Path], expected_hashes: dict[str, str]
) -> dict[str, str]:
    hashes = {str(artifact): sha256_file(artifact) for artifact in artifacts}
    unknown_artifacts = sorted(set(expected_hashes).difference(hashes))
    if unknown_artifacts:
        raise SmokeFailure(
            "expected artifact hash does not name a supplied artifact: "
            + ", ".join(unknown_artifacts)
        )
    for path, expected in expected_hashes.items():
        if hashes[path] != expected:
            raise SmokeFailure(f"sha256 mismatch for artifact: {path}")
    return hashes


def wait_for_url(url: str, timeout_seconds: float, marker: str | None = None) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            # Package probes target a loopback service launched by this
            # process. Bypass CI/user proxy settings so localhost can never
            # be routed through an unavailable external proxy.
            with _LOCAL_OPENER.open(url, timeout=min(2.0, timeout_seconds)) as response:
                body = response.read().decode("utf-8", errors="replace")
                if not 200 <= response.status < 300:
                    last_error = f"received HTTP {response.status}"
                elif marker and marker not in body:
                    last_error = f"response did not contain required marker {marker!r}"
                else:
                    return
        except (HTTPException, OSError, URLError, ValueError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise SmokeFailure(f"timed out waiting for {url}: {last_error}")


def wait_for_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    """Wait for a successful JSON response from the launched loopback app."""
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            with _LOCAL_OPENER.open(url, timeout=min(2.0, timeout_seconds)) as response:
                body = response.read().decode("utf-8", errors="replace")
                if not 200 <= response.status < 300:
                    last_error = f"received HTTP {response.status}"
                else:
                    payload = json.loads(body)
                    if isinstance(payload, dict):
                        return payload
                    last_error = "response was not a JSON object"
        except (HTTPException, OSError, URLError, ValueError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise SmokeFailure(f"timed out waiting for JSON from {url}: {last_error}")


def validate_http_url(url: str, label: str, *, loopback_only: bool) -> str:
    """Reject malformed URLs before a probe can escape receipt handling."""
    if not url or "\x00" in url or any(character.isspace() for character in url):
        raise SmokeFailure(f"{label} must be an HTTP URL")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise SmokeFailure(f"{label} must be an HTTP URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise SmokeFailure(f"{label} must be an HTTP URL")
    if not loopback_only:
        return url
    try:
        is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise SmokeFailure(f"{label} must be an HTTP loopback URL")
    return url


def require_loopback_url(url: str, label: str) -> str:
    """Reject readiness values that could send a local proof off-device."""
    try:
        return validate_http_url(
            url, f"readiness {label}", loopback_only=True
        )
    except SmokeFailure as error:
        raise SmokeFailure(
            f"readiness {label} must be an HTTP loopback URL"
        ) from error


def require_absent_readiness_file(readiness_file: Path) -> None:
    """Refuse a stale or non-regular marker instead of trusting its contents."""
    try:
        metadata = readiness_file.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise SmokeFailure(
            "readiness file must be an absent regular file before launch"
        )
    raise SmokeFailure("readiness file must not exist before launch")


def read_regular_readiness_file(
    readiness_file: Path,
) -> tuple[dict[str, Any], os.stat_result]:
    """Read one regular, non-symlink marker produced after this launch begins."""
    flags = os.O_RDONLY | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(readiness_file, flags)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise SmokeFailure("readiness file must be a regular file") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SmokeFailure("readiness file must be a regular file")
        contents = os.read(descriptor, MAX_READINESS_BYTES + 1)
        if len(contents) > MAX_READINESS_BYTES:
            raise SmokeFailure("readiness file exceeds the maximum size")
        os.close(descriptor)
        descriptor = -1
        payload = json.loads(contents.decode("utf-8"))
    finally:
        if descriptor != -1:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise SmokeFailure("readiness file must contain a JSON object")
    return payload, metadata


def wait_for_readiness(
    readiness_file: Path,
    process: subprocess.Popen[str],
    timeout_seconds: float,
    launch_started_at_ns: int,
    launched_application_pid: int,
) -> tuple[str, str]:
    """Poll the launcher's atomically-written readiness receipt."""
    deadline = time.monotonic() + timeout_seconds
    last_error = "readiness file has not been written"
    while time.monotonic() < deadline:
        try:
            payload, metadata = read_regular_readiness_file(readiness_file)
        except FileNotFoundError as error:
            last_error = f"readiness file has not been written: {error}"
        except json.JSONDecodeError as error:
            last_error = f"readiness file is not valid JSON: {error}"
        else:
            if metadata.st_mtime_ns < launch_started_at_ns:
                raise SmokeFailure("readiness file is not fresh for this launch")
            if payload.get("status") != "ready":
                last_error = "readiness file is not ready"
            elif type(payload.get("pid")) is not int:
                last_error = "readiness file is missing an integer launch pid"
            elif payload["pid"] != launched_application_pid:
                raise SmokeFailure(
                    "readiness pid does not match launched process"
                )
            else:
                api_url = payload.get("api_url")
                frontend_url = payload.get("frontend_url")
                if not isinstance(api_url, str) or not isinstance(frontend_url, str):
                    last_error = "readiness file is missing api_url or frontend_url"
                else:
                    return (
                        require_loopback_url(api_url, "api_url"),
                        require_loopback_url(frontend_url, "frontend_url"),
                    )
        time.sleep(0.1)
    raise SmokeFailure(
        f"timed out waiting for readiness file {readiness_file}: {last_error}"
    )


def endpoint_url(base_url: str, path: str) -> str:
    """Resolve a fixed API path from a readiness URL without retaining a path."""
    return urljoin(base_url, path)


def check_expected_features(
    api_url: str, expected_features: dict[str, bool], timeout_seconds: float
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Probe dynamic feature flags and return observed values plus assertions."""
    features_url = endpoint_url(api_url, "/api/features")
    payload = wait_for_json(features_url, timeout_seconds)
    actual_features = payload.get("features")
    if not isinstance(actual_features, dict):
        raise SmokeFailure("feature response did not contain a features object")

    feature_results: dict[str, dict[str, Any]] = {}
    for name, expected in expected_features.items():
        actual = actual_features.get(name)
        passed = actual is expected
        feature_results[name] = {
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
    return actual_features, feature_results


def _read_monitor_application_pid(
    descriptor: int,
    timeout_seconds: float,
) -> int:
    """Read the private launch identity without polling/reaping its monitor."""
    deadline = time.monotonic() + timeout_seconds
    chunks: list[bytes] = []
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([descriptor], [], [], min(0.1, remaining))
            if not readable:
                continue
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            chunks.append(chunk)
            try:
                payload = json.loads(b"".join(chunks))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                break
            pid = payload.get("pid")
            if type(pid) is int and pid > 0:
                return pid
            message = payload.get("error")
            if isinstance(message, str) and message:
                raise SmokeFailure(f"launch monitor failed: {message}")
            break
    finally:
        os.close(descriptor)
    raise SmokeFailure("launch monitor did not report an application pid")


def launch_monitored_process(
    command: list[str],
    launch_environment: dict[str, str],
    timeout_seconds: float,
) -> tuple[subprocess.Popen[str], int]:
    """Start an app under a retained session leader and record its real PID."""
    if os.name != "posix":
        process = subprocess.Popen(
            command,
            env=launch_environment,
            start_new_session=True,
            text=True,
        )
        return process, process.pid

    read_descriptor, write_descriptor = os.pipe()
    liveness_read_descriptor, liveness_write_descriptor = os.pipe()
    os.set_inheritable(write_descriptor, True)
    os.set_inheritable(liveness_write_descriptor, True)
    monitor_environment = launch_environment.copy()
    monitor_environment[_MONITOR_FD_ENV] = str(write_descriptor)
    monitor_environment[_MONITOR_LIVENESS_FD_ENV] = str(liveness_write_descriptor)
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", _MONITOR_SCRIPT, *command],
            env=monitor_environment,
            start_new_session=True,
            text=True,
            pass_fds=(write_descriptor, liveness_write_descriptor),
        )
        setattr(process, "_package_smoke_owned_process_group", process.pid)
        setattr(process, "_package_smoke_retained_monitor", True)
        setattr(process, "_package_smoke_monitor_liveness_fd", liveness_read_descriptor)
    except BaseException:
        os.close(read_descriptor)
        os.close(liveness_read_descriptor)
        raise
    finally:
        os.close(write_descriptor)
        os.close(liveness_write_descriptor)
    try:
        application_pid = _read_monitor_application_pid(
            read_descriptor, min(timeout_seconds, 5.0)
        )
        return process, application_pid
    except BaseException:
        try:
            if process is not None:
                stop_process(process, min(max(timeout_seconds, 0.1), 5.0))
        except (OSError, SmokeFailure, subprocess.TimeoutExpired):
            pass
        if process is None:
            os.close(liveness_read_descriptor)
        raise


def _owned_process_group_descendants(
    process_group: int, leader_pid: int
) -> set[int]:
    """Return live members other than the retained leader, or fail closed."""
    try:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,pgid="],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        raise SmokeFailure("could not inspect owned process group") from error
    if listing.returncode != 0:
        raise SmokeFailure("could not inspect owned process group")
    descendants: set[int] = set()
    for line in listing.stdout.splitlines():
        columns = line.split()
        if len(columns) != 2:
            continue
        try:
            pid, group = (int(column) for column in columns)
        except ValueError:
            continue
        if group == process_group and pid != leader_pid:
            descendants.add(pid)
    return descendants


def _wait_for_owned_process_group_descendants(
    process_group: int, leader_pid: int, timeout_seconds: float
) -> set[int]:
    deadline = time.monotonic() + timeout_seconds
    descendants: set[int] = set()
    while True:
        descendants = _owned_process_group_descendants(process_group, leader_pid)
        if not descendants or time.monotonic() >= deadline:
            return descendants
        time.sleep(0.02)


def _assert_retained_monitor_is_live(process: subprocess.Popen[str]) -> None:
    """Fail closed if the monitor no longer reserves its process group."""
    descriptor = getattr(process, "_package_smoke_monitor_liveness_fd", None)
    if not isinstance(descriptor, int):
        raise SmokeFailure("owned monitor liveness proof is unavailable")
    try:
        readable, _, _ = select.select([descriptor], [], [], 0)
        if readable and os.read(descriptor, 1) == b"":
            raise SmokeFailure(
                "cannot safely stop an owned process group after its monitor exited"
            )
    except OSError as error:
        raise SmokeFailure("owned monitor liveness proof is unavailable") from error


def _close_retained_monitor_liveness(process: subprocess.Popen[str]) -> None:
    descriptor = getattr(process, "_package_smoke_monitor_liveness_fd", None)
    if isinstance(descriptor, int):
        os.close(descriptor)
        delattr(process, "_package_smoke_monitor_liveness_fd")


def stop_process(
    process: subprocess.Popen[str],
    timeout_seconds: float,
    owned_process_group: int | None = None,
) -> None:
    """Stop only the session created for this smoke process, then reap its leader."""
    if os.name == "posix" and getattr(
        process, "_package_smoke_retained_monitor", False
    ):
        if process.returncode is not None:
            raise SmokeFailure(
                "cannot safely stop an owned process group after its monitor was reaped"
            )
        _assert_retained_monitor_is_live(process)
        process_group = owned_process_group or getattr(
            process, "_package_smoke_owned_process_group", process.pid
        )
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError as error:
            raise SmokeFailure("owned process group disappeared before cleanup") from error

        descendants = _wait_for_owned_process_group_descendants(
            process_group, process.pid, timeout_seconds
        )
        if descendants:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError as error:
                raise SmokeFailure(
                    "owned process group disappeared before forced cleanup"
                ) from error
            descendants = _wait_for_owned_process_group_descendants(
                process_group, process.pid, max(timeout_seconds, 0.25)
            )
            if descendants:
                raise SmokeFailure(
                    "owned process group still has descendants after forced cleanup"
                )

        # The monitor deliberately ignores SIGTERM so its PID continues to
        # reserve the group identity until all descendants are gone.  Kill
        # that known direct child only after the proof above, then reap it.
        try:
            process.kill()
        except ProcessLookupError as error:
            raise SmokeFailure("owned monitor disappeared before reaping") from error
        process.wait(timeout=timeout_seconds)
        _close_retained_monitor_liveness(process)
        return

    if os.name == "posix":
        # `start_new_session=True` makes this the launcher's process group.
        # Preserve it at spawn time instead of deriving a PID after the leader
        # has exited, when that PID could already refer to unrelated work.
        process_group = owned_process_group or getattr(
            process, "_package_smoke_owned_process_group", process.pid
        )
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=timeout_seconds)


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(receipt, temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = SmokeArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--executable-arg", action="append", default=[])
    parser.add_argument("--api-url")
    parser.add_argument("--frontend-url")
    parser.add_argument("--readiness-file", type=Path)
    parser.add_argument("--environment", action="append", default=[])
    parser.add_argument("--expected-feature", action="append", default=[])
    parser.add_argument("--frontend-marker", default="__next_f")
    parser.add_argument(
        "--required-runtime-path", type=Path, action="append", default=[]
    )
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--expected-artifact-sha256", action="append", default=[])
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--timeout-seconds", default="60.0")
    parser.add_argument("--make-smoke-inputs", action="store_true")
    return parser.parse_args(arguments)


def apply_make_smoke_inputs(args: argparse.Namespace) -> None:
    """Read Make-owned values directly from env without a shell expansion."""
    if not args.make_smoke_inputs:
        if args.executable is None or args.receipt is None:
            raise SmokeFailure("--executable and --receipt are required")
        return

    required = {
        "SMOKE_EXECUTABLE": "executable",
        "SMOKE_READINESS_FILE": "readiness file",
        "SMOKE_ARTIFACT": "artifact",
        "SMOKE_RECEIPT": "receipt",
    }
    values = {name: os.environ.get(name, "") for name in required}
    missing = [label for name, label in required.items() if not values[name]]
    if missing:
        raise SmokeFailure(
            "make smoke inputs require " + ", ".join(sorted(missing))
        )
    args.executable = Path(values["SMOKE_EXECUTABLE"])
    args.readiness_file = Path(values["SMOKE_READINESS_FILE"])
    args.artifact = [Path(values["SMOKE_ARTIFACT"])]
    args.receipt = Path(values["SMOKE_RECEIPT"])
    args.timeout_seconds = os.environ.get(
        "SMOKE_TIMEOUT_SECONDS", args.timeout_seconds
    )
    environment = os.environ.get("SMOKE_ENVIRONMENT", "")
    args.environment = [environment] if environment else []
    expected_hash = os.environ.get("SMOKE_ARTIFACT_SHA256", "")
    args.expected_artifact_sha256 = (
        [f"{args.artifact[0]}={expected_hash}"] if expected_hash else []
    )
    expected_feature = os.environ.get("SMOKE_EXPECTED_FEATURE", "")
    args.expected_feature = [expected_feature] if expected_feature else []


def parse_timeout_seconds(value: str) -> float:
    """Keep invalid caller timeouts inside the normal receipt failure path."""
    try:
        timeout_seconds = float(value)
    except (TypeError, ValueError) as error:
        raise SmokeFailure(
            "timeout-seconds must be a finite number from 0 to 300"
        ) from error
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise SmokeFailure("timeout-seconds must be a finite number from 0 to 300")
    return timeout_seconds


def receipt_path_from_arguments(arguments: list[str]) -> Path | None:
    """Find an explicit receipt path even when later CLI parsing fails."""
    for index, argument in enumerate(arguments):
        if argument == "--receipt" and index + 1 < len(arguments):
            return Path(arguments[index + 1])
        if argument.startswith("--receipt="):
            return Path(argument.removeprefix("--receipt="))
    if "--make-smoke-inputs" in arguments:
        receipt = os.environ.get("SMOKE_RECEIPT", "")
        if receipt:
            return Path(receipt)
    return None


def write_argument_failure_receipt(arguments: list[str], error: SmokeFailure) -> None:
    """Write a minimal, machine-readable failure record when its path is known."""
    receipt_path = receipt_path_from_arguments(arguments)
    if receipt_path is None:
        return
    timestamp = utc_now()
    write_receipt(
        receipt_path,
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "status": "failed",
            "started_at": timestamp,
            "completed_at": timestamp,
            "checks": {},
            "error": str(error),
        },
    )


def main() -> int:
    arguments = sys.argv[1:]
    try:
        args = parse_args(arguments)
        apply_make_smoke_inputs(args)
    except SmokeFailure as error:
        write_argument_failure_receipt(arguments, error)
        print(str(error), file=sys.stderr)
        return 1

    runtime_paths = [str(path) for path in args.required_runtime_path]
    resolved_urls = {
        "api_url": args.api_url,
        "frontend_url": args.frontend_url,
    }
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "failed",
        "started_at": utc_now(),
        "executable": str(args.executable),
        "resolved_urls": resolved_urls,
        "expected_features": {},
        "feature_results": {},
        "checks": {
            "process_startup": {"passed": False},
            "api_readiness": {"passed": False, "url": args.api_url},
            "bundled_runtime_paths": {"passed": False, "paths": runtime_paths},
            "frontend_route_load": {"passed": False, "url": args.frontend_url},
            "runtime_features": {
                "passed": False,
                "skipped": args.readiness_file is None,
                "url": None,
                "expected": {},
                "actual": {},
                "results": {},
            },
            "clean_shutdown": {"passed": False},
            "artifact_signatures": {"passed": False, "sha256": {}},
        },
    }
    process: subprocess.Popen[str] | None = None
    launched_application_pid: int | None = None

    try:
        args.timeout_seconds = parse_timeout_seconds(args.timeout_seconds)
        if args.readiness_file is not None:
            if args.api_url is not None or args.frontend_url is not None:
                raise SmokeFailure(
                    "--api-url and --frontend-url are forbidden with --readiness-file"
                )
            require_absent_readiness_file(args.readiness_file)
        elif args.api_url is None or args.frontend_url is None:
            raise SmokeFailure(
                "--api-url and --frontend-url are required without --readiness-file"
            )
        else:
            validate_http_url(args.api_url, "api-url", loopback_only=False)
            validate_http_url(args.frontend_url, "frontend-url", loopback_only=False)
        launch_environment = os.environ.copy()
        launch_environment.update(parse_environment(args.environment))
        expected_features = parse_expected_features(args.expected_feature)
        receipt["expected_features"] = expected_features
        receipt["checks"]["runtime_features"]["expected"] = expected_features

        if not args.artifact:
            raise SmokeFailure(
                "at least one artifact is required for signature validation"
            )
        expected_hashes = parse_expected_hashes(args.expected_artifact_sha256)
        artifact_hashes = check_artifact_signatures(args.artifact, expected_hashes)
        receipt["checks"]["artifact_signatures"] = {
            "passed": True,
            "sha256": artifact_hashes,
        }

        missing_runtime_paths = [
            path for path in args.required_runtime_path if not path.exists()
        ]
        if missing_runtime_paths:
            raise SmokeFailure(
                "missing bundled runtime path: "
                + ", ".join(str(path) for path in missing_runtime_paths)
            )
        receipt["checks"]["bundled_runtime_paths"]["passed"] = True

        launch_started_at_ns = time.time_ns()
        process, launched_application_pid = launch_monitored_process(
            [str(args.executable), *args.executable_arg],
            launch_environment,
            args.timeout_seconds,
        )
        receipt["checks"]["process_startup"]["passed"] = True

        if args.readiness_file is not None:
            api_url, frontend_url = wait_for_readiness(
                args.readiness_file,
                process,
                args.timeout_seconds,
                launch_started_at_ns,
                launched_application_pid,
            )
            resolved_urls.update(api_url=api_url, frontend_url=frontend_url)
            receipt["checks"]["api_readiness"]["url"] = endpoint_url(
                api_url, "/readyz"
            )
            receipt["checks"]["frontend_route_load"]["url"] = frontend_url
        else:
            api_url = args.api_url
            frontend_url = args.frontend_url

        api_readiness_url = (
            endpoint_url(api_url, "/readyz")
            if args.readiness_file is not None
            else api_url
        )
        wait_for_url(api_readiness_url, args.timeout_seconds)
        receipt["checks"]["api_readiness"]["passed"] = True

        if args.readiness_file is not None:
            actual_features, feature_results = check_expected_features(
                api_url, expected_features, args.timeout_seconds
            )
            receipt["feature_results"] = feature_results
            receipt["checks"]["runtime_features"] = {
                "passed": all(
                    result["passed"] for result in feature_results.values()
                ),
                "skipped": False,
                "url": endpoint_url(api_url, "/api/features"),
                "expected": expected_features,
                "actual": actual_features,
                "results": feature_results,
            }
            if not receipt["checks"]["runtime_features"]["passed"]:
                raise SmokeFailure("feature mismatch for expected runtime features")
        else:
            receipt["checks"]["runtime_features"]["passed"] = True

        wait_for_url(frontend_url, args.timeout_seconds, args.frontend_marker)
        receipt["checks"]["frontend_route_load"]["passed"] = True

        stop_process(process, args.timeout_seconds)
        receipt["checks"]["clean_shutdown"]["passed"] = True
        process = None
        receipt["status"] = "passed"
        return 0
    except KeyboardInterrupt:
        receipt["cancelled"] = True
        receipt["error"] = "smoke probe cancelled"
        print(receipt["error"], file=sys.stderr)
        return 130
    except (HTTPException, OSError, SmokeFailure, ValueError) as error:
        receipt["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if process is not None:
            try:
                stop_process(process, args.timeout_seconds)
                receipt["checks"]["clean_shutdown"]["passed"] = True
            except (OSError, SmokeFailure, subprocess.TimeoutExpired) as error:
                receipt.setdefault("error", str(error))
        receipt["completed_at"] = utc_now()
        write_receipt(args.receipt, receipt)


if __name__ == "__main__":
    raise SystemExit(main())
