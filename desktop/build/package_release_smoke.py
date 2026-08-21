"""Run the staged/installed default and source-visuals-off smoke proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from desktop.build.package_smoke import (  # noqa: E402
    SmokeFailure,
    launch_monitored_process,
    stop_process,
    utc_now,
    wait_for_readiness,
    write_receipt,
)
from desktop.build.package_smoke_fixture import (  # noqa: E402
    prepare_smoke_fixture,
)

PACKAGE_BROWSER_PROBE = (
    REPOSITORY_ROOT / "desktop" / "build" / "package_browser_probe.cjs"
)
SUMMARY_RECEIPT_NAME = "summary.json"
MAX_TIMEOUT_SECONDS = 300.0

DEFAULT_EXPECTED_FEATURES: dict[str, bool] = {
    "evidenceStudio": True,
    "modelFleet": True,
    "researchRuns": True,
    "sourceVisuals": True,
    "studyWorkbench": True,
    "visualRefresh": True,
}
OFF_EXPECTED_FEATURES: dict[str, bool] = {
    **DEFAULT_EXPECTED_FEATURES,
    "sourceVisuals": False,
}


@dataclass(frozen=True)
class ModeSpec:
    name: str
    browser_mode: str
    source_visuals: bool
    expected_features: dict[str, bool]
    receipt_name: str


MODE_SPECS: dict[str, ModeSpec] = {
    "default": ModeSpec(
        name="default",
        browser_mode="default",
        source_visuals=True,
        expected_features=DEFAULT_EXPECTED_FEATURES,
        receipt_name="default.json",
    ),
    "source-visuals-off": ModeSpec(
        name="source-visuals-off",
        browser_mode="off",
        source_visuals=False,
        expected_features=OFF_EXPECTED_FEATURES,
        receipt_name="source-visuals-off.json",
    ),
}


def _argument(arguments: argparse.Namespace, name: str, default: Any = None) -> Any:
    """Read an argument from a Namespace while keeping tests lightweight."""
    return getattr(arguments, name, default)


def _mode_spec(mode: str) -> ModeSpec:
    try:
        return MODE_SPECS[mode]
    except KeyError as error:
        raise SmokeFailure(f"unknown release smoke mode: {mode}") from error


def _validate_output_root(output_root: Path) -> None:
    """Allow a new or empty output root, never append to an existing receipt set."""
    try:
        metadata = output_root.lstat()
    except FileNotFoundError:
        output_root.mkdir(parents=True)
        return
    except OSError as error:
        raise SmokeFailure(
            f"could not inspect smoke output root: {output_root}"
        ) from error

    if output_root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise SmokeFailure("smoke output root must be a non-symlink directory")
    try:
        has_entries = any(output_root.iterdir())
    except OSError as error:
        raise SmokeFailure(
            f"could not inspect smoke output root: {output_root}"
        ) from error
    if has_entries:
        raise SmokeFailure(f"smoke output root must be empty: {output_root}")


def _validate_inputs(arguments: argparse.Namespace) -> str:
    executable = Path(_argument(arguments, "executable"))
    artifact = Path(_argument(arguments, "artifact"))
    playwright_module = Path(_argument(arguments, "playwright_module"))
    if not executable.is_file():
        raise SmokeFailure(f"executable does not exist: {executable}")
    if not PACKAGE_BROWSER_PROBE.is_file():
        raise SmokeFailure(f"browser probe does not exist: {PACKAGE_BROWSER_PROBE}")
    if not playwright_module.exists():
        raise SmokeFailure(f"Playwright module does not exist: {playwright_module}")

    try:
        expected_hash = _argument(arguments, "expected_artifact_sha256")
        artifact_hash = _sha256_file(artifact)
    except OSError as error:
        raise SmokeFailure(f"could not read artifact: {artifact}") from error
    if expected_hash is not None:
        expected_hash = str(expected_hash).lower()
        if len(expected_hash) != 64:
            raise SmokeFailure(
                "expected artifact sha256 must be 64 hexadecimal characters"
            )
        try:
            int(expected_hash, 16)
        except ValueError as error:
            raise SmokeFailure(
                "expected artifact sha256 must be 64 hexadecimal characters"
            ) from error
        if artifact_hash != expected_hash:
            raise SmokeFailure(f"sha256 mismatch for artifact: {artifact}")
    return artifact_hash


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SmokeFailure(f"artifact does not exist: {path}")
    if path.stat().st_size == 0:
        raise SmokeFailure(f"artifact is empty: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timeout(arguments: argparse.Namespace) -> float:
    value = _argument(arguments, "timeout_seconds", 300.0)
    try:
        timeout = float(value)
    except (TypeError, ValueError) as error:
        raise SmokeFailure(
            "timeout-seconds must be a finite number from 0 to 300"
        ) from error
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise SmokeFailure("timeout-seconds must be a finite number from 0 to 300")
    return timeout


def _fixture_root(output_root: Path, mode: str) -> Path:
    return output_root / "fixtures" / mode


def _browser_command(
    *, mode: ModeSpec, frontend_url: str, api_url: str, playwright_module: Path
) -> list[str]:
    return [
        "node",
        str(PACKAGE_BROWSER_PROBE),
        "--mode",
        mode.browser_mode,
        "--frontend-url",
        frontend_url,
        "--api-url",
        api_url,
        "--playwright-module",
        str(playwright_module),
    ]


def _parse_browser_receipt(browser: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Parse exactly the probe's stdout JSON; stderr is diagnostic-only."""
    output = browser.stdout.strip()
    if not output:
        raise SmokeFailure("browser contract did not emit a JSON receipt on stdout")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise SmokeFailure(
            "browser contract did not emit a JSON receipt on stdout"
        ) from error
    if not isinstance(payload, dict):
        raise SmokeFailure("browser contract receipt must be a JSON object")
    return payload


def _base_mode_receipt(mode: ModeSpec, arguments: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "failed",
        "mode": mode.name,
        "browser_mode": mode.browser_mode,
        "source_visuals": mode.source_visuals,
        "executable": str(Path(_argument(arguments, "executable"))),
        "expected_features": mode.expected_features,
        "checks": {
            "fixture": {"passed": False},
            "process_startup": {"passed": False},
            "readiness": {"passed": False},
            "browser_ui": {"passed": False},
            "clean_shutdown": {"passed": False},
        },
        "started_at": utc_now(),
    }


def run_mode(mode: str, arguments: argparse.Namespace) -> dict[str, Any]:
    """Run one mode and always leave its machine-readable receipt behind."""
    mode_spec = _mode_spec(mode)
    output_root = Path(_argument(arguments, "output_root"))
    output_root.mkdir(parents=True, exist_ok=True)
    receipt_path = output_root / mode_spec.receipt_name
    receipt = _base_mode_receipt(mode_spec, arguments)
    process: subprocess.Popen[str] | Any | None = None
    timeout = 0.0
    try:
        timeout = _timeout(arguments)
        fixture = prepare_smoke_fixture(
            _fixture_root(output_root, mode),
            source_visuals=mode_spec.source_visuals,
            uv_cache_dir=Path(_argument(arguments, "uv_cache_dir")),
        )
        receipt["fixture"] = {
            "root": str(fixture.root),
            "home": str(fixture.home),
            "data_dir": str(fixture.data_dir),
            "model_dir": str(fixture.model_dir),
            "readiness_file": str(fixture.readiness_file),
        }
        receipt["checks"]["fixture"] = {"passed": True}
        environment = os.environ.copy()
        if mode_spec.source_visuals:
            environment.pop("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", None)
        environment.update(fixture.environment)
        launch_started_at_ns = time.time_ns()
        process, launched_application_pid = launch_monitored_process(
            [str(Path(_argument(arguments, "executable")))], environment, timeout
        )
        receipt["checks"]["process_startup"] = {
            "passed": True,
            "application_pid": launched_application_pid,
        }
        api_url, frontend_url = wait_for_readiness(
            fixture.readiness_file,
            process,
            timeout,
            launch_started_at_ns,
            launched_application_pid,
        )
        receipt["checks"]["readiness"] = {
            "passed": True,
            "api_url": api_url,
            "frontend_url": frontend_url,
            "application_pid": launched_application_pid,
        }
        browser_command = _browser_command(
            mode=mode_spec,
            frontend_url=frontend_url,
            api_url=api_url,
            playwright_module=Path(_argument(arguments, "playwright_module")),
        )
        receipt["browser_command"] = browser_command
        browser = subprocess.run(
            browser_command,
            cwd=REPOSITORY_ROOT / "frontend",
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
        browser_receipt = _parse_browser_receipt(browser)
        receipt["browser"] = browser_receipt
        if browser.returncode != 0 or browser_receipt.get("status") != "passed":
            error = browser_receipt.get("error", "browser contract failed")
            raise SmokeFailure(f"browser contract failed: {error}")
        receipt["checks"]["browser_ui"] = {"passed": True}
        receipt["status"] = "passed"
    except Exception as error:
        receipt["error"] = str(error)
    finally:
        if process is None:
            receipt["checks"]["clean_shutdown"] = {"passed": True, "skipped": True}
        else:
            try:
                stop_process(process, min(timeout or 30.0, 30.0))
                receipt["checks"]["clean_shutdown"] = {"passed": True}
            except (OSError, SmokeFailure, subprocess.SubprocessError) as error:
                receipt["checks"]["clean_shutdown"] = {"passed": False}
                receipt.setdefault("error", str(error))
                receipt["status"] = "failed"
        receipt["completed_at"] = utc_now()
        write_receipt(receipt_path, receipt)
    return receipt


def run_release_smoke(arguments: argparse.Namespace) -> int:
    """Verify the artifact, then run default and off strictly serially."""
    output_root = Path(_argument(arguments, "output_root"))
    summary: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed",
        "started_at": utc_now(),
        "modes": [],
    }
    summary_path: Path | None = None
    active_mode: str | None = None
    try:
        _validate_output_root(output_root)
        summary_path = output_root / SUMMARY_RECEIPT_NAME
        artifact_hash = _validate_inputs(arguments)
        summary["artifact"] = str(Path(_argument(arguments, "artifact")))
        summary["artifact_sha256"] = artifact_hash
        summary["expected_artifact_sha256"] = _argument(
            arguments, "expected_artifact_sha256"
        )
        for mode in MODE_SPECS:
            active_mode = mode
            result = run_mode(mode, arguments)
            summary["modes"].append(
                {
                    "mode": mode,
                    "status": result.get("status"),
                    "receipt": str(output_root / _mode_spec(mode).receipt_name),
                }
            )
            if result.get("status") != "passed":
                summary["failed_mode"] = mode
                raise SmokeFailure(
                    f"{mode} smoke failed: {result.get('error', 'unknown error')}"
                )
        summary["status"] = "passed"
        return 0
    except Exception as error:
        summary["error"] = str(error)
        if active_mode is not None and "failed_mode" not in summary:
            summary["failed_mode"] = active_mode
        return 1
    finally:
        summary["completed_at"] = utc_now()
        if summary_path is None:
            try:
                _validate_output_root(output_root)
                summary_path = output_root / SUMMARY_RECEIPT_NAME
            except Exception:
                summary_path = None
        if summary_path is not None:
            write_receipt(summary_path, summary)


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--uv-cache-dir", type=Path, required=True)
    parser.add_argument("--playwright-module", type=Path, required=True)
    parser.add_argument("--expected-artifact-sha256")
    parser.add_argument("--timeout-seconds", default="300")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    try:
        parsed = parse_args(arguments)
        return run_release_smoke(parsed)
    except (OSError, SmokeFailure, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
