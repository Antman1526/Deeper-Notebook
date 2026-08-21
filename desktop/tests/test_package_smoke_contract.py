"""Contract tests for the packaged desktop smoke receipt."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
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


def test_parse_environment_accepts_key_value_pairs() -> None:
    assert smoke.parse_environment(
        ["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0"]
    ) == {"DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED": "0"}


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
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *_args, **_kwargs: Process())
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

    def launch(command, *, env, start_new_session, text):
        observed["command"] = command
        observed["env"] = env
        observed["start_new_session"] = start_new_session
        observed["text"] = text
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
        return Process()

    monkeypatch.setenv("PACKAGE_SMOKE_PARENT", "preserved")
    monkeypatch.setattr(smoke, "_LOCAL_OPENER", Opener())
    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
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
    assert observed["start_new_session"] is True
    assert observed["text"] is True
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
        return Process()

    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: stopped.append(process))
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
        return Process()

    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
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
        return Process()

    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: stopped.append(process))
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
        return Process()

    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
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
        return Process()

    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: stopped.append(process))
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


def test_dynamic_smoke_reports_child_exit_before_readiness(
    monkeypatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "fixture.dmg"
    artifact.write_bytes(b"fixture artifact")
    readiness = tmp_path / "desktop-readiness.json"
    receipt_path = tmp_path / "receipt.json"
    poll_results = iter((None, 17, 17))
    waited: list[object] = []

    class Process:
        pid = 4321
        returncode = 17

        def poll(self):
            return next(poll_results)

        def wait(self, **_kwargs):
            waited.append(self)
            return 17

    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *_args, **_kwargs: Process())
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
    assert "before readiness" in receipt["error"]
    assert waited


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
        return Process()

    monkeypatch.setattr(smoke._LOCAL_OPENER.__class__, "open", Opener().open)
    monkeypatch.setattr(smoke.subprocess, "Popen", launch)
    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: stopped.append(process))
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

    monkeypatch.setattr(smoke, "stop_process", lambda process, _timeout: stopped.append(process))

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
            return Process()

        monkeypatch.setattr(smoke.subprocess, "Popen", launch)
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
    assert json.loads(argument_receipt.read_text(encoding="utf-8"))["status"] == "failed"


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
