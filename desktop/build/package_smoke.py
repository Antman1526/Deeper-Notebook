"""Run a packaged desktop smoke probe and write a JSON receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

RECEIPT_SCHEMA_VERSION = 1
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


def stop_process(process: subprocess.Popen[str], timeout_seconds: float) -> None:
    if process.poll() is not None:
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
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--frontend-url", required=True)
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
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "failed",
        "started_at": utc_now(),
        "executable": str(args.executable),
        "checks": {
            "process_startup": {"passed": False},
            "api_readiness": {"passed": False, "url": args.api_url},
            "bundled_runtime_paths": {"passed": False, "paths": runtime_paths},
            "frontend_route_load": {"passed": False, "url": args.frontend_url},
            "clean_shutdown": {"passed": False},
            "artifact_signatures": {"passed": False, "sha256": {}},
        },
    }
    process: subprocess.Popen[str] | None = None

    try:
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
            start_new_session=os.name == "posix",
            text=True,
        )
        time.sleep(0.1)
        if process.poll() is not None:
            raise SmokeFailure(
                f"process exited during startup with code {process.returncode}"
            )
        receipt["checks"]["process_startup"]["passed"] = True

        wait_for_url(args.api_url, args.timeout_seconds)
        receipt["checks"]["api_readiness"]["passed"] = True

        wait_for_url(args.frontend_url, args.timeout_seconds, args.frontend_marker)
        receipt["checks"]["frontend_route_load"]["passed"] = True

        stop_process(process, args.timeout_seconds)
        receipt["checks"]["clean_shutdown"]["passed"] = True
        process = None
        receipt["status"] = "passed"
        return 0
    except (OSError, SmokeFailure) as error:
        receipt["error"] = str(error)
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
