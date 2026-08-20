"""Contract tests for the packaged desktop smoke receipt."""

from __future__ import annotations

import hashlib
import json
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
    assert receipt["schema_version"] == 1
    assert receipt["status"] == "passed"
    assert receipt["executable"] == sys.executable
    assert receipt["checks"] == {
        "process_startup": {"passed": True},
        "api_readiness": {"passed": True, "url": "http://127.0.0.1:5055/healthz"},
        "bundled_runtime_paths": {"passed": True, "paths": [str(runtime_path)]},
        "frontend_route_load": {
            "passed": True,
            "url": "http://127.0.0.1:5055/notebooks",
        },
        "clean_shutdown": {"passed": True},
        "artifact_signatures": {
            "passed": True,
            "sha256": {
                str(artifact): hashlib.sha256(artifact.read_bytes()).hexdigest()
            },
        },
    }


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
    assert receipt["schema_version"] == 1
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
