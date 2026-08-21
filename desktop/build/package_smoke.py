"""Run a packaged desktop smoke probe and write a JSON receipt."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, build_opener

RECEIPT_SCHEMA_VERSION = 2
_LOCAL_OPENER = build_opener(ProxyHandler({}))


class SmokeFailure(RuntimeError):
    """A required package proof did not complete."""


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
        except (OSError, URLError) as error:
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
        except (OSError, URLError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise SmokeFailure(f"timed out waiting for JSON from {url}: {last_error}")


def require_loopback_url(url: str, label: str) -> str:
    """Reject readiness values that could send a local proof off-device."""
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SmokeFailure(f"readiness {label} must be an HTTP loopback URL")
    try:
        is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise SmokeFailure(f"readiness {label} must be an HTTP loopback URL")
    return url


def wait_for_readiness(
    readiness_file: Path,
    process: subprocess.Popen[str],
    timeout_seconds: float,
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
            payload = json.loads(readiness_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            last_error = f"readiness file is not valid JSON: {error}"
        else:
            if not isinstance(payload, dict):
                last_error = "readiness file must contain a JSON object"
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


def stop_process(process: subprocess.Popen[str], timeout_seconds: float) -> None:
    if process.poll() is not None:
        process.wait(timeout=timeout_seconds)
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout-seconds must be positive")

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
        if args.readiness_file is not None:
            if args.api_url is not None or args.frontend_url is not None:
                raise SmokeFailure(
                    "--api-url and --frontend-url are forbidden with --readiness-file"
                )
        elif args.api_url is None or args.frontend_url is None:
            raise SmokeFailure(
                "--api-url and --frontend-url are required without --readiness-file"
            )
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

        process = subprocess.Popen(
            [str(args.executable), *args.executable_arg],
            env=launch_environment,
            start_new_session=True,
            text=True,
        )
        time.sleep(0.1)
        if process.poll() is not None:
            raise SmokeFailure(
                f"process exited during startup with code {process.returncode}"
            )
        receipt["checks"]["process_startup"]["passed"] = True

        if args.readiness_file is not None:
            api_url, frontend_url = wait_for_readiness(
                args.readiness_file, process, args.timeout_seconds
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
                "passed": True,
                "skipped": False,
                "url": endpoint_url(api_url, "/api/features"),
                "expected": expected_features,
                "actual": actual_features,
                "results": feature_results,
            }
            if any(not result["passed"] for result in feature_results.values()):
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
    except (OSError, SmokeFailure) as error:
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
