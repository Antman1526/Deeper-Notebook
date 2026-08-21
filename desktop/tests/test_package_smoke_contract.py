"""Contract tests for the packaged desktop smoke receipt."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from desktop.build import package_smoke as smoke

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SMOKE_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "package_smoke.py"


def run_smoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACKAGE_SMOKE_SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def wait_for_path(path: Path, timeout_seconds: float = 3) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def assert_process_is_gone(pid: int, timeout_seconds: float = 3) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} survived cleanup")


def test_parse_environment_accepts_key_value_pairs() -> None:
    assert smoke.parse_environment(["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0"]) == {
        "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED": "0"
    }


def test_parse_environment_rejects_malformed_values() -> None:
    for value in ("missing-separator", "=missing-key", "bad\x00value=x"):
        try:
            smoke.parse_environment([value])
        except smoke.SmokeFailure as error:
            assert "KEY=VALUE" in str(error)
        else:
            raise AssertionError(f"expected malformed environment rejection: {value}")


def test_parse_expected_features_requires_boolean_values() -> None:
    assert smoke.parse_expected_features(["sourceVisuals=false"]) == {
        "sourceVisuals": False
    }
    for value in ("sourceVisuals", "sourceVisuals=yes", "=true"):
        try:
            smoke.parse_expected_features([value])
        except smoke.SmokeFailure as error:
            assert "NAME=BOOL" in str(error)
        else:
            raise AssertionError(f"expected malformed feature rejection: {value}")


def test_smoke_writes_a_machine_readable_receipt_for_the_required_proofs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_path = tmp_path / "bundled-runtime"
    artifact = tmp_path / "Open-Notebook-Plus-fixture"
    receipt_path = tmp_path / "package-smoke-receipt.json"
    runtime_path.mkdir()
    artifact.write_bytes(b"fixture artifact")

    class Response:
        status = 200

        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    class Opener:
        def open(self, url: str, **_kwargs):
            body = b'{"status":"ready"}' if url.endswith("/healthz") else b"__next_f"
            return Response(body)

    class Process:
        pid = 1234

        def poll(self):
            return None

    monkeypatch.setattr(smoke, "_LOCAL_OPENER", Opener())
    monkeypatch.setattr(
        smoke,
        "launch_monitored_process",
        lambda *_args, **_kwargs: (Process(), Process.pid),
    )
    monkeypatch.setattr(smoke, "stop_process", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--api-url",
            "http://127.0.0.1:5055/healthz",
            "--frontend-url",
            "http://127.0.0.1:5055/notebooks",
            "--required-runtime-path",
            str(runtime_path),
            "--artifact",
            str(artifact),
            "--expected-artifact-sha256",
            f"{artifact}={hashlib.sha256(artifact.read_bytes()).hexdigest()}",
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "5",
        ],
    )

    assert smoke.main() == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["status"] == "passed"
    assert receipt["executable"] == sys.executable
    assert receipt["resolved_urls"] == {
        "api_url": "http://127.0.0.1:5055/healthz",
        "frontend_url": "http://127.0.0.1:5055/notebooks",
    }
    assert receipt["expected_features"] == {}
    assert receipt["feature_results"] == {}
    assert receipt["checks"]["process_startup"] == {"passed": True}
    assert receipt["checks"]["api_readiness"] == {
        "passed": True,
        "url": "http://127.0.0.1:5055/healthz",
    }
    assert receipt["checks"]["bundled_runtime_paths"] == {
        "passed": True,
        "paths": [str(runtime_path)],
    }
    assert receipt["checks"]["frontend_route_load"] == {
        "passed": True,
        "url": "http://127.0.0.1:5055/notebooks",
    }
    assert receipt["checks"]["runtime_features"] == {
        "passed": True,
        "skipped": True,
        "url": None,
        "expected": {},
        "actual": {},
        "results": {},
    }
    assert receipt["checks"]["clean_shutdown"] == {"passed": True}
    assert receipt["checks"]["artifact_signatures"] == {
        "passed": True,
        "sha256": {str(artifact): hashlib.sha256(artifact.read_bytes()).hexdigest()},
    }


def test_dynamic_smoke_discovers_loopback_urls_and_checks_features(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "dynamic-receipt.json"
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    class Opener:
        def open(self, url: str, **_kwargs):
            observed.setdefault("urls", []).append(url)
            if url.endswith("/readyz"):
                return Response(b'{"status":"ready"}')
            if url.endswith("/api/features"):
                return Response(b'{"features":{"sourceVisuals":true}}')
            return Response(b"__next_f")

    class Process:
        pid = 1234

        def poll(self):
            return None

        def wait(self, **_kwargs):
            observed["waited"] = True
            return 0

    def launch(command, environment, _timeout):
        observed["command"] = command
        observed["env"] = environment
        readiness.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "ready",
                    "pid": 1234,
                    "api_url": "http://127.0.0.1:62000",
                    "frontend_url": "http://127.0.0.1:62001/",
                }
            ),
            encoding="utf-8",
        )
        return Process(), Process.pid

    monkeypatch.setenv("PACKAGE_SMOKE_PARENT", "preserved")
    monkeypatch.setattr(smoke, "_LOCAL_OPENER", Opener())
    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: process.wait())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--environment",
            "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0",
            "--expected-feature",
            "sourceVisuals=true",
            "--artifact",
            str(artifact),
            "--expected-artifact-sha256",
            f"{artifact}={hashlib.sha256(artifact.read_bytes()).hexdigest()}",
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "5",
        ],
    )

    assert smoke.main() == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "passed"
    assert receipt["resolved_urls"] == {
        "api_url": "http://127.0.0.1:62000",
        "frontend_url": "http://127.0.0.1:62001/",
    }
    assert receipt["expected_features"] == {"sourceVisuals": True}
    assert receipt["feature_results"] == {
        "sourceVisuals": {"expected": True, "actual": True, "passed": True}
    }
    assert receipt["checks"]["runtime_features"]["passed"] is True
    assert observed["env"]["PACKAGE_SMOKE_PARENT"] == "preserved"
    assert observed["env"]["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED"] == "0"
    assert observed["waited"] is True


def test_dynamic_smoke_rejects_readiness_urls_outside_loopback(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    stopped: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        readiness.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "pid": 4321,
                    "api_url": "https://example.com/api",
                    "frontend_url": "http://127.0.0.1:62001/",
                }
            ),
            encoding="utf-8",
        )
        return Process(), Process.pid

    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "loopback" in receipt["error"]
    assert stopped


def test_dynamic_smoke_rejects_preexisting_readiness_before_launch(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    readiness.write_text(
        json.dumps(
            {
                "status": "ready",
                "pid": 4321,
                "api_url": "http://127.0.0.1:62000",
                "frontend_url": "http://127.0.0.1:62001/",
            }
        ),
        encoding="utf-8",
    )
    launched: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        launched.append(object())
        return Process(), Process.pid

    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "must not exist before launch" in receipt["error"]
    assert launched == []


def test_dynamic_smoke_rejects_symlink_readiness_before_launch(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    marker_target = tmp_path / "marker-target.json"
    marker_target.write_text("{}", encoding="utf-8")
    readiness = tmp_path / "desktop-readiness.json"
    readiness.symlink_to(marker_target)
    receipt_path = tmp_path / "receipt.json"
    launched: list[object] = []

    monkeypatch.setattr(
        smoke.subprocess,
        "Popen",
        lambda *_args, **_kwargs: launched.append(object()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "regular file" in receipt["error"]
    assert launched == []


def test_dynamic_smoke_rejects_unbound_or_stale_readiness_identity(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    stopped: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        readiness.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "pid": 9999,
                    "api_url": "http://127.0.0.1:62000",
                    "frontend_url": "http://127.0.0.1:62001/",
                }
            ),
            encoding="utf-8",
        )
        return Process(), Process.pid

    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "does not match launched process" in receipt["error"]
    assert stopped


def test_dynamic_smoke_rejects_readiness_older_than_this_launch(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        readiness.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "pid": 4321,
                    "api_url": "http://127.0.0.1:62000",
                    "frontend_url": "http://127.0.0.1:62001/",
                }
            ),
            encoding="utf-8",
        )
        os.utime(readiness, ns=(1, 1))
        return Process(), Process.pid

    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "fresh" in receipt["error"]


def test_dynamic_smoke_reports_missing_readiness_urls_and_cleans_up(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    stopped: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        readiness.write_text(
            '{"status":"ready","pid":4321,"api_url":"http://127.0.0.1:62000"}',
            encoding="utf-8",
        )
        return Process(), Process.pid

    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "0.01",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "readiness" in receipt["error"]
    assert stopped


def test_dynamic_smoke_times_out_when_the_retained_monitor_has_no_readiness(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    waited: list[object] = []

    class Process:
        pid = 4321

        def wait(self, **_kwargs):
            waited.append(self)
            return 17

    monkeypatch.setattr(
        smoke,
        "launch_monitored_process",
        lambda *_args, **_kwargs: (Process(), Process.pid),
    )
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "1",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "timed out waiting for readiness" in receipt["error"]
    assert waited


def test_dynamic_smoke_rejects_an_exited_child_despite_healthy_unrelated_endpoints(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b'{"features":{}}' if self.path == "/api/features" else b"__next_f"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]
    application = (
        "import json, os, pathlib, sys; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'status':'ready', "
        "'pid':os.getpid(), 'api_url':sys.argv[2], 'frontend_url':sys.argv[2]}), "
        "encoding='utf-8')"
    )
    try:
        result = run_smoke(
            "--executable",
            sys.executable,
            "--executable-arg=-c",
            f"--executable-arg={application}",
            f"--executable-arg={readiness}",
            f"--executable-arg=http://127.0.0.1:{port}",
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "2",
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    assert result.returncode == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "launched application exited with code 0" in receipt["error"]
    assert receipt["checks"]["process_startup"] == {"passed": False}


def test_dynamic_smoke_reports_usr_bin_true_as_child_exit(tmp_path: Path) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    receipt_path = tmp_path / "receipt.json"

    result = run_smoke(
        "--executable",
        "/usr/bin/true",
        "--readiness-file",
        str(tmp_path / "desktop-readiness.json"),
        "--artifact",
        str(artifact),
        "--receipt",
        str(receipt_path),
        "--timeout-seconds",
        "2",
    )

    assert result.returncode == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "launched application exited with code 0" in receipt["error"]
    assert receipt["checks"]["process_startup"] == {"passed": False}
    assert "timed out" not in receipt["error"]


def test_dynamic_smoke_detects_child_exit_while_a_healthy_probe_is_in_flight(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    probe_started = tmp_path / "probe-started"

    class DelayedHealthyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            probe_started.write_text("started", encoding="utf-8")
            time.sleep(0.2)
            body = b'{"features":{}}' if self.path == "/api/features" else b"__next_f"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHealthyHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]
    application = (
        "import json, os, pathlib, sys, time\n"
        "readiness, probe, url = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]\n"
        "readiness.write_text(json.dumps({'status':'ready', 'pid':os.getpid(), "
        "'api_url':url, 'frontend_url':url}), encoding='utf-8')\n"
        "deadline = time.monotonic() + 2\n"
        "while not probe.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
    )
    try:
        result = run_smoke(
            "--executable",
            sys.executable,
            "--executable-arg=-c",
            f"--executable-arg={application}",
            f"--executable-arg={readiness}",
            f"--executable-arg={probe_started}",
            f"--executable-arg=http://127.0.0.1:{port}",
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "2",
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    assert result.returncode == 1, result.stderr
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "launched application exited with code 0" in receipt["error"]
    assert receipt["checks"]["api_readiness"] == {
        "passed": False,
        "url": f"http://127.0.0.1:{port}/readyz",
    }


def test_sigterm_to_the_verifier_writes_a_receipt_and_leaves_no_owned_group(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    application = (
        "import json, os, pathlib, sys, time; "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'status':'ready', "
        "'pid':os.getpid(), 'api_url':'http://127.0.0.1:9', "
        "'frontend_url':'http://127.0.0.1:9'}), encoding='utf-8'); time.sleep(60)"
    )
    verifier = subprocess.Popen(
        [
            sys.executable,
            str(PACKAGE_SMOKE_SCRIPT),
            "--executable",
            sys.executable,
            "--executable-arg=-c",
            f"--executable-arg={application}",
            f"--executable-arg={readiness}",
            "--readiness-file",
            str(readiness),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "5",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    monitor_pid: int | None = None
    application_pid: int | None = None
    try:
        wait_for_path(readiness)
        application_pid = json.loads(readiness.read_text(encoding="utf-8"))["pid"]
        monitor_pid = os.getpgid(application_pid)
        verifier.send_signal(signal.SIGTERM)
        assert verifier.wait(timeout=5) == 130
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["cancelled"] is True
        assert receipt["checks"]["clean_shutdown"]["passed"] is True
        assert_process_is_gone(application_pid)
        assert_process_is_gone(monitor_pid)
    finally:
        if verifier.poll() is None:
            verifier.kill()
            verifier.wait(timeout=2)
        if monitor_pid is not None:
            try:
                os.killpg(monitor_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_monitor_script_bounds_post_sigkill_cleanup() -> None:
    assert "post_kill_deadline = time.monotonic() + 1" in smoke._MONITOR_SCRIPT
    assert "if time.monotonic() >= post_kill_deadline:" in smoke._MONITOR_SCRIPT
    assert '"event": "cleanup_failed"' in smoke._MONITOR_SCRIPT


def test_hard_verifier_exit_reaps_a_stubborn_owned_descendant(tmp_path: Path) -> None:
    application_path = tmp_path / "application.json"
    stubborn_child_path = tmp_path / "stubborn-child.pid"
    monitor_path = tmp_path / "monitor.json"
    application = (
        "import json, os, pathlib, signal, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(60)']); "
        "pathlib.Path(sys.argv[2]).write_text(str(child.pid), encoding='utf-8'); "
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid()}), "
        "encoding='utf-8'); time.sleep(60)"
    )
    verifier = (
        "import json, os, pathlib, sys, time\n"
        "from desktop.build import package_smoke as smoke\n"
        "monitor, application_pid = smoke.launch_monitored_process(\n"
        "    [sys.executable, '-c', sys.argv[1], sys.argv[2], sys.argv[3]], dict(os.environ), 2\n"
        ")\n"
        "pathlib.Path(sys.argv[4]).write_text(json.dumps({'monitor':monitor.pid, "
        "'application':application_pid}), encoding='utf-8')\n"
        "deadline = time.monotonic() + 2\n"
        "while not pathlib.Path(sys.argv[3]).exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
        "os._exit(0)\n"
    )
    verifier_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            verifier,
            application,
            str(application_path),
            str(stubborn_child_path),
            str(monitor_path),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    assert verifier_process.wait(timeout=5) == 0
    wait_for_path(monitor_path)
    identities = json.loads(monitor_path.read_text(encoding="utf-8"))
    monitor_pid = identities["monitor"]
    application_pid = identities["application"]
    wait_for_path(stubborn_child_path)
    stubborn_child_pid = int(stubborn_child_path.read_text(encoding="utf-8"))
    try:
        assert_process_is_gone(application_pid)
        assert_process_is_gone(stubborn_child_pid)
        assert_process_is_gone(monitor_pid)
    finally:
        try:
            os.killpg(monitor_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_dynamic_smoke_records_feature_mismatch_and_cleans_up(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    stopped: list[object] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            if self.url.endswith("/readyz"):
                return b'{"status":"ready"}'
            if self.url.endswith("/api/features"):
                return b'{"features":{"sourceVisuals":false}}'
            return b"__next_f"

    class Opener:
        def open(self, url: str, **_kwargs):
            response = Response()
            response.url = url
            return response

    class Process:
        pid = 4321

        def poll(self):
            return None

    def launch(*_args, **_kwargs):
        readiness.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "pid": 4321,
                    "api_url": "http://127.0.0.1:62000",
                    "frontend_url": "http://127.0.0.1:62001/",
                }
            ),
            encoding="utf-8",
        )
        return Process(), Process.pid

    monkeypatch.setattr(smoke._LOCAL_OPENER.__class__, "open", Opener().open)
    monkeypatch.setattr(smoke, "launch_monitored_process", launch)
    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--readiness-file",
            str(readiness),
            "--expected-feature",
            "sourceVisuals=true",
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            "1",
        ],
    )

    assert smoke.main() == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert "feature mismatch" in receipt["error"]
    assert receipt["feature_results"]["sourceVisuals"] == {
        "expected": True,
        "actual": False,
        "passed": False,
    }
    assert receipt["checks"]["runtime_features"]["passed"] is False
    assert stopped


def test_stop_process_terminates_and_reaps_only_its_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []
    waits: list[float] = []

    class Process:
        pid = 9876

        def poll(self):
            return None

        def wait(self, *, timeout):
            waits.append(timeout)
            return 0

    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    smoke.stop_process(Process(), 3)

    assert signals == [(9876, signal.SIGTERM)]
    assert waits == [3]


def test_stop_process_uses_the_captured_group_after_its_leader_exits(
    monkeypatch,
) -> None:
    signals: list[tuple[int, int]] = []
    waits: list[float] = []

    class Process:
        pid = 9876

        def poll(self):
            return 17

        def wait(self, *, timeout):
            waits.append(timeout)
            return 17

    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(
        os,
        "getpgid",
        lambda _pid: (_ for _ in ()).throw(AssertionError("must use captured pgid")),
    )

    smoke.stop_process(Process(), 3, owned_process_group=5432)

    assert signals == [(5432, signal.SIGTERM)]
    assert waits == [3]


def test_stop_process_fails_closed_if_its_retained_monitor_exited(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []
    read_descriptor, write_descriptor = os.pipe()
    os.close(write_descriptor)

    class Process:
        pid = 5432
        returncode = None

    process = Process()
    setattr(process, "_package_smoke_retained_monitor", True)
    setattr(process, "_package_smoke_monitor_liveness_fd", read_descriptor)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    try:
        smoke.stop_process(process, 1)
    except smoke.SmokeFailure as error:
        assert "monitor exited" in str(error)
    else:
        raise AssertionError("expected liveness proof to fail closed")
    finally:
        os.close(read_descriptor)

    assert signals == []


def test_stop_process_escalates_and_reaps_a_stubborn_owned_descendant(
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "stubborn-child.pid"
    child_pid: int | None = None
    monitor, application_pid = smoke.launch_monitored_process(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, signal, subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(60)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')"
            ),
            str(child_pid_path),
        ],
        dict(os.environ),
        2,
    )
    stopped = False
    try:
        deadline = time.monotonic() + 2
        while not child_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert child_pid_path.exists(), "leader did not record its child PID"
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        while time.monotonic() < deadline:
            status = subprocess.run(
                ["ps", "-p", str(application_pid), "-o", "stat="],
                capture_output=True,
                check=False,
                text=True,
            )
            if status.returncode != 0 or "Z" in status.stdout:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("application leader did not exit before cleanup")
        assert os.getpgid(monitor.pid) == monitor.pid
        assert os.getpgid(child_pid) == monitor.pid

        smoke.stop_process(monitor, 0.1)
        stopped = True

        assert monitor.returncode is not None
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("stubborn owned descendant survived cleanup")
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not stopped:
            try:
                smoke.stop_process(monitor, 1)
            except (OSError, smoke.SmokeFailure, subprocess.TimeoutExpired):
                try:
                    os.killpg(monitor.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                monitor.wait(timeout=2)


def test_readiness_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    readiness = tmp_path / "desktop-readiness.fifo"
    os.mkfifo(readiness)
    probe = (
        "from pathlib import Path\n"
        "import sys\n"
        "from desktop.build import package_smoke as smoke\n"
        "try:\n"
        "    smoke.read_regular_readiness_file(Path(sys.argv[1]))\n"
        "except smoke.SmokeFailure as error:\n"
        "    print(error)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe, str(readiness)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert "regular file" in result.stdout


def test_readiness_rejects_oversized_json_before_parsing(tmp_path: Path) -> None:
    readiness = tmp_path / "desktop-readiness.json"
    readiness.write_bytes(b"x" * (smoke.MAX_READINESS_BYTES + 1))

    try:
        smoke.read_regular_readiness_file(readiness)
    except smoke.SmokeFailure as error:
        assert "maximum size" in str(error)
    else:
        raise AssertionError("expected oversized readiness rejection")


def test_make_inputs_preserve_a_spaced_environment_value(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMOKE_EXECUTABLE", "/tmp/deeper-notebook")
    monkeypatch.setenv("SMOKE_READINESS_FILE", "/tmp/desktop-readiness.json")
    monkeypatch.setenv("SMOKE_ARTIFACT", "/tmp/deeper-notebook.dmg")
    monkeypatch.setenv("SMOKE_RECEIPT", "/tmp/package-smoke-receipt.json")
    environment_file = tmp_path / "smoke-environment.txt"
    environment_file.write_text(
        "DEEPER_NOTEBOOK_TITLE=local smoke value", encoding="utf-8"
    )
    monkeypatch.setenv("SMOKE_ENVIRONMENT_FILE", str(environment_file))

    args = smoke.parse_args(["--make-smoke-inputs"])
    smoke.apply_make_smoke_inputs(args)

    assert args.environment == ["DEEPER_NOTEBOOK_TITLE=local smoke value"]


def test_make_inputs_reject_unsafe_environment_files(
    monkeypatch, tmp_path: Path
) -> None:
    for name, value in {
        "SMOKE_EXECUTABLE": "/tmp/deeper-notebook",
        "SMOKE_READINESS_FILE": "/tmp/desktop-readiness.json",
        "SMOKE_ARTIFACT": "/tmp/deeper-notebook.dmg",
        "SMOKE_RECEIPT": "/tmp/package-smoke-receipt.json",
    }.items():
        monkeypatch.setenv(name, value)

    regular_file = tmp_path / "regular-environment.txt"
    regular_file.write_text("DEEPER_NOTEBOOK_TITLE=local smoke", encoding="utf-8")
    symlink = tmp_path / "environment-link"
    symlink.symlink_to(regular_file)
    fifo = tmp_path / "environment.fifo"
    os.mkfifo(fifo)
    oversized = tmp_path / "oversized-environment.txt"
    oversized.write_bytes(b"X" * (smoke.MAX_MAKE_ENVIRONMENT_BYTES + 1))
    malformed = tmp_path / "malformed-environment.txt"
    malformed.write_text("missing-separator", encoding="utf-8")

    for environment_file in (symlink, fifo, Path("/dev/null"), oversized, malformed):
        monkeypatch.setenv("SMOKE_ENVIRONMENT_FILE", str(environment_file))
        args = smoke.parse_args(["--make-smoke-inputs"])
        try:
            smoke.apply_make_smoke_inputs(args)
        except smoke.SmokeFailure:
            continue
        raise AssertionError(
            f"expected unsafe environment rejection: {environment_file}"
        )


def test_make_inputs_reject_environment_file_swapped_before_descriptor_open(
    monkeypatch, tmp_path: Path
) -> None:
    for name, value in {
        "SMOKE_EXECUTABLE": "/tmp/deeper-notebook",
        "SMOKE_READINESS_FILE": "/tmp/desktop-readiness.json",
        "SMOKE_ARTIFACT": "/tmp/deeper-notebook.dmg",
        "SMOKE_RECEIPT": "/tmp/package-smoke-receipt.json",
    }.items():
        monkeypatch.setenv(name, value)
    environment_file = tmp_path / "smoke-environment.txt"
    environment_file.write_text("DEEPER_NOTEBOOK_TITLE=original", encoding="utf-8")
    monkeypatch.setenv("SMOKE_ENVIRONMENT_FILE", str(environment_file))
    real_open = os.open

    def swap_then_open(path: str | Path, flags: int, *args: int) -> int:
        replacement = tmp_path / "replacement-environment.txt"
        replacement.write_text("DEEPER_NOTEBOOK_TITLE=swapped", encoding="utf-8")
        os.replace(replacement, environment_file)
        return real_open(path, flags, *args)

    monkeypatch.setattr(os, "open", swap_then_open)
    args = smoke.parse_args(["--make-smoke-inputs"])

    try:
        smoke.apply_make_smoke_inputs(args)
    except smoke.SmokeFailure as error:
        assert "changed" in str(error)
    else:
        raise AssertionError("expected swapped environment file rejection")


def run_make_smoke_inputs(
    *, environment_file: Path, receipt_path: Path
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "SMOKE_EXECUTABLE": sys.executable,
        "SMOKE_READINESS_FILE": "/tmp/desktop-readiness.json",
        "SMOKE_ARTIFACT": "/tmp/deeper-notebook.dmg",
        "SMOKE_RECEIPT": str(receipt_path),
        "SMOKE_ENVIRONMENT_FILE": str(environment_file),
    }
    return subprocess.run(
        [sys.executable, str(PACKAGE_SMOKE_SCRIPT), "--make-smoke-inputs"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def assert_make_input_failure_receipt(
    result: subprocess.CompletedProcess[str], receipt_path: Path, error: str
) -> None:
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["status"] == "failed"
    assert receipt["checks"] == {}
    assert "executable" not in receipt
    assert error in receipt["error"]
    assert error in result.stderr
    assert list(receipt_path.parent.glob(f".{receipt_path.name}.*.tmp")) == []


def test_make_inputs_write_a_receipt_for_an_overlong_environment_path(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.json"
    result = run_make_smoke_inputs(
        environment_file=tmp_path / ("x" * 300), receipt_path=receipt_path
    )

    assert_make_input_failure_receipt(
        result,
        receipt_path,
        "SMOKE_ENVIRONMENT_FILE could not be inspected: File name too long",
    )


def test_make_inputs_write_a_receipt_for_an_unreadable_environment_parent(
    tmp_path: Path,
) -> None:
    protected_directory = tmp_path / "unreadable"
    protected_directory.mkdir()
    environment_file = protected_directory / "smoke-environment.txt"
    environment_file.write_text("PROBE=blocked", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    protected_directory.chmod(0)
    try:
        result = run_make_smoke_inputs(
            environment_file=environment_file, receipt_path=receipt_path
        )
    finally:
        protected_directory.chmod(0o700)

    assert_make_input_failure_receipt(
        result,
        receipt_path,
        "SMOKE_ENVIRONMENT_FILE could not be inspected: Permission denied",
    )


def test_dynamic_smoke_writes_bounded_receipts_for_invalid_loopback_urls(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    stopped: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )

    for index, invalid_api_url in enumerate(
        (
            "http://127.0.0.1:not-a-port",
            "http://127.0.0.1:65536",
            "http://user:password@127.0.0.1:62000",
            "http://[::1",
        )
    ):
        readiness = tmp_path / f"desktop-readiness-{index}.json"
        receipt_path = tmp_path / f"receipt-{index}.json"

        def launch(*_args, readiness=readiness, **_kwargs):
            readiness.write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "pid": 4321,
                        "api_url": invalid_api_url,
                        "frontend_url": "http://127.0.0.1:62001/",
                    }
                ),
                encoding="utf-8",
            )
            return Process(), Process.pid

        monkeypatch.setattr(smoke, "launch_monitored_process", launch)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "package_smoke.py",
                "--executable",
                sys.executable,
                "--readiness-file",
                str(readiness),
                "--artifact",
                str(artifact),
                "--receipt",
                str(receipt_path),
                "--timeout-seconds",
                "0.01",
            ],
        )

        assert smoke.main() == 1
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert "loopback URL" in receipt["error"]

    assert len(stopped) == 4


def test_readiness_mode_forbids_static_urls(tmp_path: Path) -> None:
    result = run_smoke(
        "--executable",
        sys.executable,
        "--readiness-file",
        str(tmp_path / "readiness.json"),
        "--api-url",
        "http://127.0.0.1:5055",
        "--frontend-url",
        "http://127.0.0.1:5055",
        "--receipt",
        str(tmp_path / "receipt.json"),
    )

    assert result.returncode != 0
    assert "forbidden" in result.stderr


def test_cli_validation_failures_write_a_supplied_receipt(tmp_path: Path) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")

    for timeout_value in ("0", "not-a-number", "301"):
        receipt_path = tmp_path / f"timeout-{timeout_value}.json"
        result = run_smoke(
            "--executable",
            sys.executable,
            "--api-url",
            "http://127.0.0.1:9/healthz",
            "--frontend-url",
            "http://127.0.0.1:9/notebooks",
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout-seconds",
            timeout_value,
        )

        assert result.returncode != 0
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["status"] == "failed"
        assert "timeout-seconds" in receipt["error"]

    argument_receipt = tmp_path / "argument-error.json"
    argument_error = run_smoke(
        "--receipt",
        str(argument_receipt),
        "--unknown-option",
    )
    assert argument_error.returncode != 0
    assert (
        json.loads(argument_receipt.read_text(encoding="utf-8"))["status"] == "failed"
    )


def test_keyboard_interrupt_writes_a_cancelled_receipt_and_cleans_up(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    receipt_path = tmp_path / "receipt.json"
    stopped: list[object] = []

    class Process:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(
        smoke,
        "launch_monitored_process",
        lambda *_args, **_kwargs: (Process(), Process.pid),
    )
    monkeypatch.setattr(
        smoke, "stop_process", lambda process, _timeout: stopped.append(process)
    )
    monkeypatch.setattr(
        smoke,
        "wait_for_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_smoke.py",
            "--executable",
            sys.executable,
            "--api-url",
            "http://127.0.0.1:5055/healthz",
            "--frontend-url",
            "http://127.0.0.1:5055/notebooks",
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
        ],
    )

    try:
        result = smoke.main()
    except KeyboardInterrupt:
        result = None
    assert result == 130
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["cancelled"] is True
    assert "cancelled" in receipt["error"]
    assert receipt["checks"]["clean_shutdown"]["passed"] is True
    assert stopped


def test_smoke_records_failed_artifact_signature_in_its_receipt(tmp_path: Path) -> None:
    artifact = tmp_path / "Open-Notebook-Plus-fixture"
    receipt_path = tmp_path / "package-smoke-receipt.json"
    artifact.write_bytes(b"fixture artifact")

    result = run_smoke(
        "--executable",
        sys.executable,
        "--api-url",
        "http://127.0.0.1:9/healthz",
        "--frontend-url",
        "http://127.0.0.1:9/notebooks",
        "--artifact",
        str(artifact),
        "--expected-artifact-sha256",
        f"{artifact}={'0' * 64}",
        "--receipt",
        str(receipt_path),
    )

    assert result.returncode != 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["status"] == "failed"
    assert receipt["checks"]["artifact_signatures"]["passed"] is False
    assert "sha256 mismatch" in receipt["error"]


def test_smoke_requires_an_artifact_to_sign(tmp_path: Path) -> None:
    receipt_path = tmp_path / "package-smoke-receipt.json"

    result = run_smoke(
        "--executable",
        sys.executable,
        "--api-url",
        "http://127.0.0.1:9/healthz",
        "--frontend-url",
        "http://127.0.0.1:9/notebooks",
        "--receipt",
        str(receipt_path),
        "--timeout-seconds",
        "0.01",
    )

    assert result.returncode != 0
    assert "at least one artifact is required" in receipt_path.read_text(
        encoding="utf-8"
    )
