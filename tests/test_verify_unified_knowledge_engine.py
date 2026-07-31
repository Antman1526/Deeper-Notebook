from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_unified_knowledge_engine.py"


class _Handler(BaseHTTPRequestHandler):
    status_code = 200
    payload: object = {"passed": True, "differences": []}
    expected_token = "test-only-token"
    requests: list[tuple[str, str, str | None]] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )
        payload = (
            {"projected": 1, "unchanged": 0, "failed": 0}
            if self.path == "/api/deeper-notebook/knowledge-engine/status"
            else type(self).payload
        )
        body = json.dumps(payload).encode("utf-8")
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@contextmanager
def _server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _inputs(tmp_path: Path) -> dict[str, Path]:
    token = tmp_path / "token"
    token.write_text("test-only-token\n", encoding="utf-8")
    token.chmod(0o400)
    return {"token": token, "report": tmp_path / "report.json"}


def _command(inputs: dict[str, Path], api_url: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--api-url",
        api_url,
        "--auth-token-file",
        str(inputs["token"]),
        "--report-path",
        str(inputs["report"]),
        "--space-id",
        "knowledge_engine_space:fixture",
        "--exact-query",
        "research",
        "--require-shadow-enabled",
    ]


def test_verifier_writes_a_private_redacted_atomic_success_report(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    _Handler.status_code = 200
    _Handler.payload = {"passed": True, "differences": []}
    _Handler.requests = []

    with _server() as api_url:
        result = subprocess.run(
            _command(inputs, api_url), cwd=ROOT, text=True, capture_output=True, check=False
        )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(inputs["report"].stat().st_mode) == 0o600
    report = json.loads(inputs["report"].read_text(encoding="utf-8"))
    assert report == {"passed": True, "spaces": [{"passed": True, "space_id": "knowledge_engine_space:fixture"}]}
    assert "test-only-token" not in inputs["report"].read_text(encoding="utf-8")
    assert _Handler.requests == [
        (
            "GET",
            "/api/deeper-notebook/knowledge-engine/status",
            "Bearer test-only-token",
        ),
        (
            "GET",
            "/api/deeper-notebook/knowledge-engine/equivalence?space_id="
            "knowledge_engine_space%3Afixture&exact_query=research",
            "Bearer test-only-token",
        )
    ]


def test_verifier_returns_mismatch_without_copying_difference_values(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    _Handler.status_code = 200
    _Handler.payload = {
        "passed": False,
        "differences": [
            {
                "code": "document_hash_mismatch",
                "legacy_value": "private note text",
                "unified_value": "test-only-token",
            }
        ],
    }

    with _server() as api_url:
        result = subprocess.run(
            _command(inputs, api_url), cwd=ROOT, text=True, capture_output=True, check=False
        )

    assert result.returncode == 4
    contents = inputs["report"].read_text(encoding="utf-8")
    assert "private note text" not in contents
    assert "test-only-token" not in contents
    assert "document_hash_mismatch" in contents


def test_verifier_refuses_unsafe_path_and_disabled_engine(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    unsafe = dict(inputs)
    unsafe["report"] = unsafe["token"]
    result = subprocess.run(
        _command(unsafe, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert inputs["token"].read_text(encoding="utf-8") == "test-only-token\n"

    _Handler.status_code = 404
    _Handler.payload = {"detail": {"code": "knowledge_engine_disabled"}}
    with _server() as api_url:
        disabled = subprocess.run(
            _command(inputs, api_url), cwd=ROOT, text=True, capture_output=True, check=False
        )
    assert disabled.returncode == 3
    assert not inputs["report"].exists()


def test_verifier_refuses_report_inside_its_repository_source_root(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    inputs["report"] = ROOT / "unsafe-verifier-report.json"

    result = subprocess.run(
        _command(inputs, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert not inputs["report"].exists()


def test_verifier_maps_loopback_transport_failure_to_unavailable(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)

    result = subprocess.run(
        _command(inputs, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3
    assert result.stderr.strip() == "verification_unavailable"
    assert not inputs["report"].exists()
