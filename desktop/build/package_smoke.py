"""Run a packaged desktop smoke probe and write a JSON receipt."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
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
_LOCAL_OPENER = build_opener(ProxyHandler({}))


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


def read_regular_readiness_file(readiness_file: Path) -> tuple[dict[str, Any], os.stat_result]:
    """Read one regular, non-symlink marker produced after this launch begins."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(readiness_file, flags)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise SmokeFailure("readiness file must be a regular file") from error
    with os.fdopen(descriptor, "r", encoding="utf-8") as marker_file:
        metadata = os.fstat(marker_file.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise SmokeFailure("readiness file must be a regular file")
        payload = json.load(marker_file)
    if not isinstance(payload, dict):
        raise SmokeFailure("readiness file must contain a JSON object")
    return payload, metadata


def wait_for_readiness(
    readiness_file: Path,
    process: subprocess.Popen[str],
    timeout_seconds: float,
    launch_started_at_ns: int,
) -> tuple[str, str]:
    """Poll the launcher's atomically-written readiness receipt."""
    deadline = time.monotonic() + timeout_seconds
    last_error = "readiness file has not been written"
    while time.monotonic() < deadline:
        returncode = process.poll()
        if returncode is not None:
            raise SmokeFailure(
                f"process exited with code {returncode} before readiness"
            )
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
            elif payload["pid"] != process.pid:
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


def stop_process(
    process: subprocess.Popen[str],
    timeout_seconds: float,
    owned_process_group: int | None = None,
) -> None:
    """Stop only the session created for this smoke process, then reap its leader."""
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
    parser.add_argument("--executable", type=Path, required=True)
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
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout-seconds", default="60.0")
    return parser.parse_args(arguments)


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
        process = subprocess.Popen(
            [str(args.executable), *args.executable_arg],
            env=launch_environment,
            start_new_session=True,
            text=True,
        )
        if os.name == "posix":
            setattr(process, "_package_smoke_owned_process_group", process.pid)
        time.sleep(0.1)
        if process.poll() is not None:
            raise SmokeFailure(
                f"process exited during startup with code {process.returncode}"
            )
        receipt["checks"]["process_startup"]["passed"] = True

        if args.readiness_file is not None:
            api_url, frontend_url = wait_for_readiness(
                args.readiness_file,
                process,
                args.timeout_seconds,
                launch_started_at_ns,
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
    except (HTTPException, OSError, SmokeFailure, ValueError) as error:
        receipt["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if process is not None:
            try:
                stop_process(process, args.timeout_seconds)
                receipt["checks"]["clean_shutdown"]["passed"] = True
            except (OSError, subprocess.TimeoutExpired) as error:
                receipt.setdefault("error", str(error))
        receipt["completed_at"] = utc_now()
        write_receipt(args.receipt, receipt)


if __name__ == "__main__":
    raise SystemExit(main())
