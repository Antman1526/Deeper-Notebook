"""Run the staged/installed default and source-visuals-off smoke proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
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
MAX_BROWSER_RECEIPT_BYTES = 64 * 1024
MAX_BROWSER_STRING_BYTES = 4 * 1024
MAX_BROWSER_STDERR_BYTES = 16 * 1024
MAX_RELEASE_RECEIPT_BYTES = 64 * 1024
BROWSER_PROBE_READ_CHUNK_BYTES = 4 * 1024
BROWSER_PROBE_POLL_SECONDS = 0.05
BROWSER_PROBE_TERMINATE_GRACE_SECONDS = 0.1
BROWSER_PROBE_THREAD_JOIN_SECONDS = 0.25

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


@dataclass(frozen=True)
class BrowserProbeResult:
    """Bounded child output needed to decide whether a browser proof is usable."""

    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_limit_exceeded: bool
    stderr_limit_exceeded: bool
    peak_stdout_bytes: int


class _BoundedPipeCapture:
    """Drain one child pipe continuously while retaining at most its byte limit."""

    def __init__(
        self, limit: int, *, on_limit_exceeded: Callable[[], None] | None = None
    ) -> None:
        self._limit = limit
        self._on_limit_exceeded = on_limit_exceeded
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self.limit_exceeded = False
        self.peak_bytes = 0
        self.error: OSError | None = None
        self._closed_by_parent = threading.Event()

    def drain(self, stream: Any) -> None:
        try:
            while chunk := os.read(stream.fileno(), BROWSER_PROBE_READ_CHUNK_BYTES):
                notify_limit = False
                with self._lock:
                    remaining = self._limit - len(self._buffer)
                    if remaining < len(chunk):
                        if remaining > 0:
                            self._buffer.extend(chunk[:remaining])
                        if not self.limit_exceeded:
                            self.limit_exceeded = True
                            notify_limit = True
                    else:
                        self._buffer.extend(chunk)
                    self.peak_bytes = max(self.peak_bytes, len(self._buffer))
                if notify_limit and self._on_limit_exceeded is not None:
                    self._on_limit_exceeded()
        except OSError as error:
            if not self._closed_by_parent.is_set():
                self.error = error

    def close_stream(self, stream: Any) -> None:
        """Unblock a capture reader without treating our own close as a failure."""
        self._closed_by_parent.set()
        try:
            stream.close()
        except OSError:
            pass

    def captured(self) -> bytes:
        with self._lock:
            return bytes(self._buffer)


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
    uv_cache_dir = Path(_argument(arguments, "uv_cache_dir"))
    try:
        uv_cache_metadata = uv_cache_dir.stat()
    except FileNotFoundError as error:
        raise SmokeFailure(
            f"uv cache directory does not exist: {uv_cache_dir}"
        ) from error
    except OSError as error:
        raise SmokeFailure(
            f"could not inspect uv cache directory: {uv_cache_dir}"
        ) from error
    if not stat.S_ISDIR(uv_cache_metadata.st_mode):
        raise SmokeFailure(f"uv cache path is not a directory: {uv_cache_dir}")

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


def _ensure_fixture_parent(output_root: Path) -> Path:
    """Create or validate the runner-owned parent for fresh mode fixtures."""
    fixtures_parent = output_root / "fixtures"
    _reject_symlinked_output_ancestors(fixtures_parent)
    try:
        fixtures_parent.mkdir(mode=0o700)
    except FileExistsError as error:
        try:
            metadata = fixtures_parent.lstat()
        except OSError as inspect_error:
            raise SmokeFailure(
                f"could not inspect smoke fixture parent: {fixtures_parent}"
            ) from inspect_error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SmokeFailure(
                "smoke fixture parent must be a non-symlink directory"
            ) from error
    except OSError as error:
        raise SmokeFailure(
            f"could not create smoke fixture parent: {fixtures_parent}"
        ) from error
    else:
        try:
            os.chmod(fixtures_parent, 0o700)
        except OSError:
            pass
    return fixtures_parent


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


def _posix_process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _owned_posix_process_group(process: subprocess.Popen[bytes]) -> int | None:
    """Capture the session-created group before the leader can be reaped."""
    if os.name != "posix":
        return None
    try:
        group_id = os.getpgid(process.pid)
        session_id = os.getsid(process.pid)
    except OSError as error:
        raise SmokeFailure(
            "browser probe could not establish its process group"
        ) from error
    if group_id != process.pid or session_id != process.pid:
        raise SmokeFailure("browser probe did not create an isolated process group")
    return group_id


def _terminate_browser_process_tree(
    process: subprocess.Popen[bytes], *, posix_group_id: int | None = None
) -> None:
    """Terminate the verified browser-probe tree while retaining bounded cleanup."""
    if os.name == "posix":
        if posix_group_id is None:
            return
        try:
            os.killpg(posix_group_id, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return
        deadline = time.monotonic() + BROWSER_PROBE_TERMINATE_GRACE_SECONDS
        while (
            _posix_process_group_exists(posix_group_id) and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if _posix_process_group_exists(posix_group_id):
            try:
                os.killpg(posix_group_id, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        return

    if os.name == "nt":
        try:
            taskkill = subprocess.Popen(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                taskkill.wait(timeout=BROWSER_PROBE_TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                taskkill.kill()
                try:
                    taskkill.wait(timeout=BROWSER_PROBE_THREAD_JOIN_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
        except OSError:
            pass
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass


def _wait_for_browser_probe_exit(
    process: subprocess.Popen[bytes], *, posix_group_id: int | None
) -> None:
    """Wait for the probe leader only after a bounded failure cleanup."""
    if process.poll() is not None:
        process.wait()
        return
    try:
        process.wait(timeout=BROWSER_PROBE_THREAD_JOIN_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_browser_process_tree(process, posix_group_id=posix_group_id)
        try:
            process.wait(timeout=BROWSER_PROBE_THREAD_JOIN_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise SmokeFailure("browser probe process did not stop") from error


def _join_browser_capture_threads(
    captures: list[tuple[_BoundedPipeCapture, Any, threading.Thread]],
    process: subprocess.Popen[bytes],
    *,
    posix_group_id: int | None,
) -> bool:
    """Bound output-drain cleanup even if a descendant retained a pipe."""
    for _capture, _stream, thread in captures:
        thread.join(BROWSER_PROBE_THREAD_JOIN_SECONDS)
    if all(not thread.is_alive() for _capture, _stream, thread in captures):
        return True

    _terminate_browser_process_tree(process, posix_group_id=posix_group_id)
    for capture, stream, _thread in captures:
        capture.close_stream(stream)
    for _capture, _stream, thread in captures:
        thread.join(BROWSER_PROBE_THREAD_JOIN_SECONDS)
    return all(not thread.is_alive() for _capture, _stream, thread in captures)


def _run_browser_probe(
    command: list[str], *, cwd: Path, timeout_seconds: float
) -> BrowserProbeResult:
    """Run the browser probe without ever accumulating unbounded pipe output."""
    popen_options: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": False,
    }
    if os.name == "posix":
        popen_options["start_new_session"] = True
    elif os.name == "nt":
        popen_options["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    process = subprocess.Popen(
        command,
        **popen_options,
    )
    posix_group_id = _owned_posix_process_group(process)
    stdout_limit_event = threading.Event()
    termination_lock = threading.Lock()
    termination_started = False

    def terminate_process_tree_once() -> None:
        nonlocal termination_started
        with termination_lock:
            if termination_started:
                return
            termination_started = True
        _terminate_browser_process_tree(process, posix_group_id=posix_group_id)

    def terminate_for_stdout_limit() -> None:
        stdout_limit_event.set()
        terminate_process_tree_once()

    stdout_capture = _BoundedPipeCapture(
        MAX_BROWSER_RECEIPT_BYTES,
        on_limit_exceeded=terminate_for_stdout_limit,
    )
    stderr_capture = _BoundedPipeCapture(MAX_BROWSER_STDERR_BYTES)
    if process.stdout is None or process.stderr is None:
        terminate_process_tree_once()
        _wait_for_browser_probe_exit(process, posix_group_id=posix_group_id)
        raise SmokeFailure("browser probe could not capture its output pipes")
    stdout_thread = threading.Thread(
        target=stdout_capture.drain,
        args=(process.stdout,),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stderr_capture.drain,
        args=(process.stderr,),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    captures = [
        (stdout_capture, process.stdout, stdout_thread),
        (stderr_capture, process.stderr, stderr_thread),
    ]
    timed_out = False
    capture_threads_stopped = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                terminate_process_tree_once()
                break
            stdout_limit_event.wait(min(remaining, BROWSER_PROBE_POLL_SECONDS))
        _wait_for_browser_probe_exit(process, posix_group_id=posix_group_id)
    except BaseException:
        terminate_process_tree_once()
        try:
            _wait_for_browser_probe_exit(process, posix_group_id=posix_group_id)
        except SmokeFailure:
            pass
        raise
    finally:
        terminate_process_tree_once()
        capture_threads_stopped = _join_browser_capture_threads(
            captures, process, posix_group_id=posix_group_id
        )
        for capture, stream, _thread in captures:
            capture.close_stream(stream)

    stdout = stdout_capture.captured()
    stderr = stderr_capture.captured()
    if not capture_threads_stopped:
        raise SmokeFailure("browser probe output drain did not stop")
    if stdout_capture.error is not None or stderr_capture.error is not None:
        raise SmokeFailure("browser probe output capture failed")
    if timed_out:
        raise subprocess.TimeoutExpired(
            command,
            timeout_seconds,
            output=stdout,
            stderr=stderr,
        )
    return BrowserProbeResult(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_limit_exceeded=stdout_capture.limit_exceeded,
        stderr_limit_exceeded=stderr_capture.limit_exceeded,
        peak_stdout_bytes=stdout_capture.peak_bytes,
    )


def _browser_receipt_string(value: object, label: str) -> str:
    """Return a bounded browser-receipt string or fail before retaining it."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SmokeFailure(f"browser receipt {label} was not a valid string")
    try:
        byte_length = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise SmokeFailure(f"browser receipt {label} was not valid UTF-8") from error
    if byte_length > MAX_BROWSER_STRING_BYTES:
        raise SmokeFailure(f"browser receipt {label} exceeded its byte limit")
    return value


def _bounded_diagnostic(error: object) -> str:
    """Keep failure diagnostics useful without allowing unbounded receipt fields."""
    value = str(error)
    try:
        if len(value.encode("utf-8")) <= MAX_BROWSER_STRING_BYTES:
            return value
    except UnicodeEncodeError:
        pass
    return "release smoke failure omitted an oversized diagnostic"


def _parse_browser_receipt(browser: Any) -> dict[str, Any]:
    """Parse exactly the probe's stdout JSON; stderr is diagnostic-only."""
    if getattr(browser, "stdout_limit_exceeded", False):
        raise SmokeFailure("browser contract receipt exceeded its byte limit")
    if getattr(browser, "stderr_limit_exceeded", False):
        raise SmokeFailure("browser contract diagnostics exceeded their byte limit")
    if isinstance(browser.stdout, bytes):
        output = browser.stdout
    elif isinstance(browser.stdout, str):
        try:
            output = browser.stdout.encode("utf-8")
        except UnicodeEncodeError as error:
            raise SmokeFailure(
                "browser contract did not emit UTF-8 JSON on stdout"
            ) from error
    else:
        raise SmokeFailure("browser contract did not emit text JSON on stdout")
    if len(output) > MAX_BROWSER_RECEIPT_BYTES:
        raise SmokeFailure("browser contract receipt exceeded its byte limit")
    if not output.strip():
        raise SmokeFailure("browser contract did not emit a JSON receipt on stdout")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise SmokeFailure(
            "browser contract did not emit a JSON receipt on stdout"
        ) from error
    if not isinstance(payload, dict):
        raise SmokeFailure("browser contract receipt must be a JSON object")
    status = _browser_receipt_string(payload.get("status"), "status")
    if status == "failed":
        if set(payload) != {"status", "error"}:
            raise SmokeFailure("browser contract failure receipt had an invalid shape")
        _browser_receipt_string(payload["error"], "error")
    return payload


def _validate_browser_receipt(
    receipt: dict[str, Any],
    mode: ModeSpec,
    frontend_url: str,
    api_url: str,
) -> None:
    """Accept only the complete read-only browser proof for one mode."""
    _validate_browser_receipt_schema(receipt, mode)
    if _browser_receipt_string(receipt.get("status"), "status") != "passed":
        raise SmokeFailure("browser receipt status must be passed")
    if _browser_receipt_string(receipt.get("mode"), "mode") != mode.browser_mode:
        raise SmokeFailure("browser receipt mode did not match the requested mode")
    if (
        _browser_receipt_string(receipt.get("frontend_url"), "frontend URL")
        != frontend_url
    ):
        raise SmokeFailure("browser receipt frontend URL did not match readiness")
    if _browser_receipt_string(receipt.get("api_url"), "API URL") != api_url:
        raise SmokeFailure("browser receipt API URL did not match readiness")

    frontend_origin = _browser_origin(frontend_url, "frontend URL", strict=True)
    api_origin = _browser_origin(api_url, "API URL", strict=True)
    allowed_origins = {frontend_origin, api_origin}
    requests = _validate_observed_requests(receipt, allowed_origins)
    responses = _validate_observed_responses(receipt, allowed_origins)
    _validate_response_correlation(mode, api_origin, requests, responses)
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
        theme = _browser_receipt_string(receipt.get("theme"), "theme")
        if not theme.startswith("gemini-forward-"):
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
    value = _browser_receipt_string(value, label)
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
    path = _browser_receipt_string(entry.get("path"), f"{label} path")
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
        if _browser_receipt_string(entry["method"], "request method") != "GET":
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
        if type(entry["status"]) is not int or not 200 <= entry["status"] <= 299:
            raise SmokeFailure("browser receipt response evidence was not successful")
        _validate_evidence_url(entry, allowed_origins, "response evidence")
    return entries


def _evidence_key(entry: dict[str, Any], label: str) -> str:
    """Use the full validated URL so response evidence cannot change a query."""
    _browser_origin(entry["url"], label, strict=False)
    return entry["url"]


def _validate_response_correlation(
    mode: ModeSpec,
    api_origin: str,
    requests: list[dict[str, Any]],
    responses: list[dict[str, Any]],
) -> None:
    """Require one successful retained response per retained GET request."""
    request_counts = Counter(
        _evidence_key(request, "request evidence") for request in requests
    )
    critical_paths = {"/api/features"}
    if mode.browser_mode == "off":
        critical_paths.add("/api/sources")
    critical_counts = Counter()

    for response in responses:
        response_key = _evidence_key(response, "response evidence")
        if request_counts[response_key] <= 0:
            raise SmokeFailure(
                "browser receipt response evidence did not match a request"
            )
        request_counts[response_key] -= 1
        if (
            _browser_origin(response["url"], "response evidence", strict=False)
            == api_origin
            and response["path"] in critical_paths
        ):
            critical_counts[response["path"]] += 1

    for path in critical_paths:
        if not any(
            _browser_origin(request["url"], "request evidence", strict=False)
            == api_origin
            and request["path"] == path
            for request in requests
        ):
            raise SmokeFailure(f"browser receipt did not observe the {path} request")
        if critical_counts[path] != 1:
            raise SmokeFailure(
                f"browser receipt did not include exactly one successful {path} response"
            )


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
    feature_url = f"{api_origin}/api/features"
    feature_requests = [
        request for request in requests if request["url"] == feature_url
    ]
    if len(feature_requests) != 1:
        raise SmokeFailure(
            "browser receipt did not observe exactly one canonical feature request"
        )
    feature_responses = [
        response for response in responses if response["url"] == feature_url
    ]
    if (
        len(feature_responses) != 1
        or feature_responses[0]["status"] != feature_response["status"]
    ):
        raise SmokeFailure(
            "browser receipt did not correlate the feature response to the canonical API URL"
        )


def _validate_request_derivatives(
    receipt: dict[str, Any], requests: list[dict[str, Any]]
) -> None:
    methods = sorted({request["method"] for request in requests})
    reported_methods = receipt["http_methods"]
    if type(reported_methods) is not list or any(
        _browser_receipt_string(method, "reported HTTP method") != "GET"
        for method in reported_methods
    ):
        raise SmokeFailure("browser receipt HTTP methods had an invalid shape")
    if reported_methods != methods or methods != ["GET"]:
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


def _receipt_json_bytes(receipt: dict[str, Any]) -> bytes:
    try:
        serialized = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        return serialized.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SmokeFailure("release smoke receipt could not be serialized") from error


def _write_bounded_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Persist only receipts no larger than the documented 64 KiB protocol cap."""
    if len(_receipt_json_bytes(receipt)) > MAX_RELEASE_RECEIPT_BYTES:
        raise SmokeFailure("release smoke receipt exceeded its byte limit")
    write_receipt(path, receipt)


def _replace_with_bounded_failure(
    receipt: dict[str, Any], *, kind: str, error: object
) -> None:
    receipt.clear()
    receipt.update(
        {
            "schema_version": 1,
            "status": "failed",
            "receipt_kind": kind,
            "error": _bounded_diagnostic(error),
            "completed_at": utc_now(),
        }
    )


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
        _ensure_fixture_parent(output_root)
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
        browser = _run_browser_probe(
            browser_command,
            cwd=REPOSITORY_ROOT / "frontend",
            timeout_seconds=timeout,
        )
        require_application_running(
            process, min(timeout, APPLICATION_LIVENESS_POLL_SECONDS)
        )
        browser_receipt = _parse_browser_receipt(browser)
        if browser.returncode != 0:
            error = "browser contract failed"
            if browser_receipt.get("status") == "failed":
                error = _browser_receipt_string(browser_receipt.get("error"), "error")
            raise SmokeFailure(f"browser contract failed: {error}")
        if browser_receipt.get("status") != "passed":
            raise SmokeFailure("browser contract did not report a passed receipt")
        _validate_browser_receipt(
            browser_receipt,
            mode_spec,
            frontend_url,
            api_url,
        )
        receipt["browser"] = browser_receipt
        receipt["checks"]["browser_ui"] = {"passed": True}
        receipt["status"] = "passed"
    except Exception as error:
        receipt["error"] = _bounded_diagnostic(error)
    finally:
        if process is None:
            receipt["checks"]["clean_shutdown"] = {"passed": True, "skipped": True}
        else:
            try:
                stop_process(process, min(timeout or 30.0, 30.0))
                receipt["checks"]["clean_shutdown"] = {"passed": True}
            except (OSError, SmokeFailure, subprocess.SubprocessError) as error:
                receipt["checks"]["clean_shutdown"] = {"passed": False}
                receipt.setdefault("error", _bounded_diagnostic(error))
                receipt["status"] = "failed"
        receipt["completed_at"] = utc_now()
        try:
            _write_bounded_receipt(receipt_path, receipt)
        except SmokeFailure as error:
            _replace_with_bounded_failure(receipt, kind="mode", error=error)
            _write_bounded_receipt(receipt_path, receipt)
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
        summary["error"] = _bounded_diagnostic(error)
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
            try:
                _write_bounded_receipt(summary_path, summary)
            except SmokeFailure as error:
                _replace_with_bounded_failure(summary, kind="summary", error=error)
                _write_bounded_receipt(summary_path, summary)


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
