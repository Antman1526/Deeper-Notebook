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
from urllib.parse import SplitResult, urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from desktop.build.package_smoke import (  # noqa: E402
    SmokeFailure,
    launch_monitored_process,
    require_application_running,
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
APPLICATION_LIVENESS_POLL_SECONDS = 0.25
MAX_BROWSER_OBSERVED_REQUESTS = 64
MAX_BROWSER_OBSERVED_RESPONSES = 64

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
    _reject_symlinked_output_ancestors(output_root)
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


def _reject_symlinked_output_ancestors(output_root: Path) -> None:
    """Reject a new output path that would be created through a symlink."""
    absolute = Path(os.path.abspath(output_root))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise SmokeFailure(
                f"could not inspect smoke output root ancestor: {current}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise SmokeFailure(
                f"smoke output root must not be below a symlinked ancestor: {current}"
            )


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


def _validate_browser_receipt(
    receipt: dict[str, Any],
    mode: ModeSpec,
    frontend_url: str,
    api_url: str,
) -> None:
    """Accept only the complete read-only browser proof for one mode."""
    _validate_browser_receipt_schema(receipt, mode)
    if receipt.get("status") != "passed":
        raise SmokeFailure("browser receipt status must be passed")
    if receipt.get("mode") != mode.browser_mode:
        raise SmokeFailure("browser receipt mode did not match the requested mode")
    if receipt.get("frontend_url") != frontend_url:
        raise SmokeFailure("browser receipt frontend URL did not match readiness")
    if receipt.get("api_url") != api_url:
        raise SmokeFailure("browser receipt API URL did not match readiness")

    frontend_origin = _browser_origin(frontend_url, "frontend URL", strict=True)
    api_origin = _browser_origin(api_url, "API URL", strict=True)
    allowed_origins = {frontend_origin, api_origin}
    requests = _validate_observed_requests(receipt, allowed_origins)
    responses = _validate_observed_responses(receipt, allowed_origins)
    _validate_raw_feature_response(receipt, mode, api_origin, requests, responses)
    _validate_request_derivatives(receipt, requests)

    feature_checks = receipt.get("feature_checks")
    if type(feature_checks) is not dict or set(feature_checks) != set(
        mode.expected_features
    ):
        raise SmokeFailure("browser receipt feature checks were incomplete")
    for name, expected in mode.expected_features.items():
        check = feature_checks[name]
        if type(check) is not dict or set(check) != {
            "expected",
            "actual",
            "passed",
        }:
            raise SmokeFailure("browser receipt feature check had an invalid shape")
        feature_response = receipt["feature_response"]
        actual_features = feature_response["body"]["features"]
        if (
            check["expected"] is not expected
            or check["actual"] is not actual_features[name]
            or check["passed"] is not True
        ):
            raise SmokeFailure("browser receipt feature check did not pass")

    for key in ("blocked_requests", "non_get_requests"):
        if type(receipt.get(key)) is not list or receipt[key] != []:
            raise SmokeFailure(f"browser receipt reported {key}")

    if mode.browser_mode == "default":
        theme = receipt.get("theme")
        if not isinstance(theme, str) or not theme.startswith("gemini-forward-"):
            raise SmokeFailure("browser receipt did not prove the Gemini Forward theme")
        if receipt.get("visual_system_v2_shell_visible") is not True:
            raise SmokeFailure("browser receipt did not prove the Visual System shell")
    else:
        for key in (
            "sources_main_visible",
            "sources_heading_visible",
            "source_list_get_observed",
        ):
            if receipt.get(key) is not True:
                raise SmokeFailure(f"browser receipt did not prove {key}")
        source_list_observed = any(
            request["path"] == "/api/sources" for request in requests
        )
        if receipt["source_list_get_observed"] is not source_list_observed:
            raise SmokeFailure(
                "browser receipt source-list result did not match raw requests"
            )


def _validate_browser_receipt_schema(receipt: dict[str, Any], mode: ModeSpec) -> None:
    common_keys = {
        "status",
        "mode",
        "frontend_url",
        "api_url",
        "feature_response",
        "feature_checks",
        "observed_requests",
        "observed_responses",
        "blocked_requests",
        "http_methods",
        "non_get_requests",
        "visual_mutation_request_observed",
    }
    mode_keys = (
        {"theme", "visual_system_v2_shell_visible"}
        if mode.browser_mode == "default"
        else {
            "sources_main_visible",
            "sources_heading_visible",
            "source_list_get_observed",
        }
    )
    if type(receipt) is not dict or set(receipt) != common_keys | mode_keys:
        raise SmokeFailure("browser receipt had an unexpected schema")


def _browser_origin(value: object, label: str, *, strict: bool) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SmokeFailure(f"browser receipt {label} was not a valid URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise SmokeFailure(f"browser receipt {label} was not a valid URL") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname != "127.0.0.1"
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or (strict and (parsed.query or parsed.fragment))
    ):
        raise SmokeFailure(f"browser receipt {label} was not a valid loopback URL")
    return f"{parsed.scheme}://127.0.0.1:{port}"


def _validate_evidence_url(
    entry: dict[str, Any], allowed_origins: set[str], label: str
) -> SplitResult:
    value = entry.get("url")
    origin = _browser_origin(value, label, strict=False)
    if origin not in allowed_origins:
        raise SmokeFailure(f"browser receipt {label} escaped the allowed origins")
    parsed = urlsplit(value)
    path = entry.get("path")
    expected_path = parsed.path or "/"
    if not isinstance(path, str) or path != expected_path:
        raise SmokeFailure(f"browser receipt {label} had an inconsistent path")
    return parsed


def _validate_observed_requests(
    receipt: dict[str, Any], allowed_origins: set[str]
) -> list[dict[str, Any]]:
    entries = receipt["observed_requests"]
    if type(entries) is not list or len(entries) > MAX_BROWSER_OBSERVED_REQUESTS:
        raise SmokeFailure("browser receipt request evidence exceeded its limit")
    if not entries:
        raise SmokeFailure("browser receipt did not include request evidence")
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"method", "url", "path"}:
            raise SmokeFailure("browser receipt request evidence had an invalid shape")
        if entry["method"] != "GET":
            raise SmokeFailure("browser receipt contained a non-GET request")
        _validate_evidence_url(entry, allowed_origins, "request evidence")
    return entries


def _validate_observed_responses(
    receipt: dict[str, Any], allowed_origins: set[str]
) -> list[dict[str, Any]]:
    entries = receipt["observed_responses"]
    if type(entries) is not list or len(entries) > MAX_BROWSER_OBSERVED_RESPONSES:
        raise SmokeFailure("browser receipt response evidence exceeded its limit")
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"status", "url", "path"}:
            raise SmokeFailure("browser receipt response evidence had an invalid shape")
        if type(entry["status"]) is not int or not 100 <= entry["status"] <= 599:
            raise SmokeFailure(
                "browser receipt response evidence had an invalid status"
            )
        _validate_evidence_url(entry, allowed_origins, "response evidence")
    return entries


def _validate_raw_feature_response(
    receipt: dict[str, Any],
    mode: ModeSpec,
    api_origin: str,
    requests: list[dict[str, Any]],
    responses: list[dict[str, Any]],
) -> None:
    feature_response = receipt["feature_response"]
    if type(feature_response) is not dict or set(feature_response) != {
        "status",
        "body",
    }:
        raise SmokeFailure("browser receipt feature response had an invalid shape")
    body = feature_response["body"]
    if type(feature_response["status"]) is not int or feature_response["status"] != 200:
        raise SmokeFailure("browser receipt feature response was not HTTP 200")
    if type(body) is not dict or set(body) != {"features"}:
        raise SmokeFailure("browser receipt feature response body had an invalid shape")
    features = body["features"]
    if type(features) is not dict or set(features) != set(mode.expected_features):
        raise SmokeFailure("browser receipt feature response did not match the mode")
    if any(
        features[name] is not expected
        for name, expected in mode.expected_features.items()
    ):
        raise SmokeFailure("browser receipt feature response did not match the mode")
    feature_path = "/api/features"
    if not any(
        _browser_origin(request["url"], "request evidence", strict=False) == api_origin
        and request["path"] == feature_path
        for request in requests
    ):
        raise SmokeFailure("browser receipt did not observe the feature request")
    if not any(
        _browser_origin(response["url"], "response evidence", strict=False)
        == api_origin
        and response["path"] == feature_path
        and response["status"] == feature_response["status"]
        for response in responses
    ):
        raise SmokeFailure("browser receipt did not observe the feature response")


def _validate_request_derivatives(
    receipt: dict[str, Any], requests: list[dict[str, Any]]
) -> None:
    methods = sorted({request["method"] for request in requests})
    if receipt["http_methods"] != methods or methods != ["GET"]:
        raise SmokeFailure("browser receipt HTTP methods did not match raw requests")
    non_get_requests = [request for request in requests if request["method"] != "GET"]
    if receipt["non_get_requests"] != non_get_requests:
        raise SmokeFailure(
            "browser receipt non-GET requests did not match raw requests"
        )
    visual_mutation = any(
        "/visual" in request["path"] and request["method"] != "GET"
        for request in requests
    )
    if receipt["visual_mutation_request_observed"] is not visual_mutation:
        raise SmokeFailure(
            "browser receipt visual-mutation result did not match raw requests"
        )
    if visual_mutation:
        raise SmokeFailure("browser receipt reported a visual mutation request")


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
        require_application_running(
            process, min(timeout, APPLICATION_LIVENESS_POLL_SECONDS)
        )
        browser_receipt = _parse_browser_receipt(browser)
        receipt["browser"] = browser_receipt
        if browser.returncode != 0 or browser_receipt.get("status") != "passed":
            error = browser_receipt.get("error", "browser contract failed")
            raise SmokeFailure(f"browser contract failed: {error}")
        _validate_browser_receipt(
            browser_receipt,
            mode_spec,
            frontend_url,
            api_url,
        )
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
