"""Contract tests for the packaged desktop smoke receipt."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SMOKE_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "package_smoke.py"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def write_fixture_app(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            import http.server
            import sys

            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/healthz":
                        body = b'{"status":"ready"}'
                    elif self.path == "/notebooks":
                        body = b'<html><body><div id="__next_f">fixture</div></body></html>'
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    return

            http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def run_smoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACKAGE_SMOKE_SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke_writes_a_machine_readable_receipt_for_the_required_proofs(
    tmp_path: Path,
) -> None:
    port = free_port()
    fixture_app = tmp_path / "fixture_app.py"
    runtime_path = tmp_path / "bundled-runtime"
    artifact = tmp_path / "Open-Notebook-Plus-fixture"
    receipt_path = tmp_path / "package-smoke-receipt.json"
    write_fixture_app(fixture_app)
    runtime_path.mkdir()
    artifact.write_bytes(b"fixture artifact")

    result = run_smoke(
        "--executable",
        sys.executable,
        "--executable-arg",
        str(fixture_app),
        "--executable-arg",
        str(port),
        "--api-url",
        f"http://127.0.0.1:{port}/healthz",
        "--frontend-url",
        f"http://127.0.0.1:{port}/notebooks",
        "--required-runtime-path",
        str(runtime_path),
        "--artifact",
        str(artifact),
        "--expected-artifact-sha256",
        f"{artifact}={hashlib.sha256(artifact.read_bytes()).hexdigest()}",
        "--receipt",
        str(receipt_path),
        "--timeout-seconds",
        "15",
    )

    assert result.returncode == 0, (
        result.stderr
        + "\n"
        + (receipt_path.read_text(encoding="utf-8") if receipt_path.exists() else "")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 1
    assert receipt["status"] == "passed"
    assert receipt["executable"] == sys.executable
    assert receipt["checks"] == {
        "process_startup": {"passed": True},
        "api_readiness": {"passed": True, "url": f"http://127.0.0.1:{port}/healthz"},
        "bundled_runtime_paths": {"passed": True, "paths": [str(runtime_path)]},
        "frontend_route_load": {"passed": True, "url": f"http://127.0.0.1:{port}/notebooks"},
        "clean_shutdown": {"passed": True},
        "artifact_signatures": {
            "passed": True,
            "sha256": {str(artifact): hashlib.sha256(artifact.read_bytes()).hexdigest()},
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
    assert "at least one artifact is required" in receipt_path.read_text(encoding="utf-8")
