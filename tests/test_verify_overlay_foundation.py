from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_overlay_foundation.py"


def _proof_inputs(tmp_path: Path) -> dict[str, Path]:
    overlay_parent = tmp_path / "overlay-proof-parent"
    overlay_parent.mkdir()
    (overlay_parent / ".deeper-notebook-overlay-proof-parent").write_text(
        "disposable-overlay-proof-parent-v1\n",
        encoding="utf-8",
    )
    external = tmp_path / "synthetic-external-fixture"
    external.mkdir()
    (external / ".deeper-notebook-overlay-external-fixture").write_text(
        "synthetic-read-only-external-fixture-v1\n",
        encoding="utf-8",
    )
    (external / "evidence.md").write_text(
        "# Synthetic external evidence\n",
        encoding="utf-8",
    )
    token = tmp_path / "auth-token"
    token.write_text("test-only-token\n", encoding="utf-8")
    token.chmod(0o400)
    return {
        "overlay": overlay_parent,
        "external": external,
        "token": token,
        "report": tmp_path / "proof-report.md",
    }


def _command(inputs: dict[str, Path], api_url: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--api-url",
        api_url,
        "--auth-token-file",
        str(inputs["token"]),
        "--overlay-data-root",
        str(inputs["overlay"]),
        "--external-fixture-root",
        str(inputs["external"]),
        "--report-path",
        str(inputs["report"]),
    ]


def test_default_check_performs_no_network_or_mutation(tmp_path: Path):
    inputs = _proof_inputs(tmp_path)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = subprocess.run(
        _command(inputs, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result.returncode == 0, result.stderr
    assert "CHECK ONLY" in result.stdout
    assert before == after
    assert not inputs["report"].exists()
    assert not list(inputs["overlay"].glob("overlay-proof-*"))


def test_check_refuses_broad_or_private_roots_without_scanning(tmp_path: Path):
    inputs = _proof_inputs(tmp_path)
    command = _command(inputs, "http://127.0.0.1:9")
    command[command.index(str(inputs["overlay"]))] = str(Path.home() / "Documents")

    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refused_root" in result.stderr
    assert not inputs["report"].exists()


def test_check_refuses_report_aliasing_token_without_overwriting_it(tmp_path: Path):
    inputs = _proof_inputs(tmp_path)
    original_token = inputs["token"].read_bytes()
    inputs["report"] = inputs["token"]

    result = subprocess.run(
        _command(inputs, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "report_path_invalid"
    assert inputs["token"].read_bytes() == original_token


def test_check_refuses_group_or_world_readable_token(tmp_path: Path):
    inputs = _proof_inputs(tmp_path)
    inputs["token"].chmod(0o644)

    result = subprocess.run(
        _command(inputs, "http://127.0.0.1:9"),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "auth_token_file_invalid"
    assert not inputs["report"].exists()


class _NoNonceHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, str | None]] = []

    def do_GET(self):  # noqa: N802
        type(self).requests.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )
        payload = json.dumps({"version": "test-no-instance-nonce"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


class _ControlledProofHandler(BaseHTTPRequestHandler):
    expected_auth = "Bearer test-only-token"
    instance_nonce = "a" * 43
    instance_pid = os.getpid()
    overlay_root_sha256 = ""
    requests: list[tuple[str, str, str | None]] = []
    pages: dict[str, dict[str, object]] = {}
    unique_count = 0
    openapi_payload: object = {
        "paths": {
            "/api/deeper-notebook/vaults/{vault_id}/pages/{note_id}": {"get": {}}
        }
    }

    @classmethod
    def reset(cls, overlay_root: Path) -> None:
        cls.instance_nonce = "a" * 43
        cls.instance_pid = os.getpid()
        cls.overlay_root_sha256 = hashlib.sha256(
            str(overlay_root.resolve()).encode("utf-8")
        ).hexdigest()
        cls.requests = []
        cls.pages = {}
        cls.unique_count = 0
        cls.openapi_payload = {
            "paths": {
                "/api/deeper-notebook/vaults/{vault_id}/pages/{note_id}": {
                    "get": {}
                }
            }
        }

    def _record(self) -> None:
        type(self).requests.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == type(self).expected_auth:
            return True
        self._json(401, {"detail": "unauthorized"})
        return False

    @staticmethod
    def _page(
        note_id: str,
        relative_path: str,
        revision: int = 1,
        content_hash: str | None = None,
    ) -> dict[str, object]:
        digest = hashlib.sha256(f"{revision}:{note_id}".encode("utf-8")).hexdigest()
        return {
            "overlay": {
                "id": note_id,
                "relative_path": relative_path,
                "revision": revision,
                "content_hash": content_hash or digest,
            },
            "markdown": "# Synthetic controlled proof\n",
        }

    def do_GET(self):  # noqa: N802
        self._record()
        if not self._authorized():
            return
        if self.path == "/api/deeper-notebook/overlay/proof-identity":
            self._json(
                200,
                {
                    "instance_nonce": type(self).instance_nonce,
                    "overlay_root_sha256": type(self).overlay_root_sha256,
                    "instance_pid": type(self).instance_pid,
                },
            )
            return
        if self.path == "/openapi.json":
            self._json(200, type(self).openapi_payload)
            return
        note_prefix = "/api/deeper-notebook/overlay/notes/"
        if self.path.startswith(note_prefix):
            note_id = urllib.parse.unquote(self.path.removeprefix(note_prefix))
            page = type(self).pages.get(note_id)
            self._json(200 if page else 404, page or {"detail": "not found"})
            return
        self._json(404, {"detail": "unexpected"})

    def do_POST(self):  # noqa: N802
        self._record()
        if not self._authorized():
            return
        if self.path != "/api/deeper-notebook/overlay/notes/unique":
            self._json(404, {"detail": "unexpected"})
            return
        self._read_json()
        type(self).unique_count += 1
        suffix = "" if type(self).unique_count == 1 else "-2"
        note_id = f"overlay_note:unique{type(self).unique_count}"
        page = self._page(
            note_id,
            f"notes/20260730-1200 Controlled Proof{suffix}.md",
        )
        type(self).pages[note_id] = page
        self._json(201, page)

    def do_PUT(self):  # noqa: N802
        self._record()
        if not self._authorized():
            return
        daily_prefix = "/api/deeper-notebook/overlay/daily/"
        if self.path.startswith(daily_prefix):
            note_id = "overlay_note:daily"
            page = type(self).pages.setdefault(
                note_id,
                self._page(note_id, "daily/2026-07-30.md"),
            )
            self._json(200, page)
            return
        note_prefix = "/api/deeper-notebook/overlay/notes/"
        if self.path.startswith(note_prefix):
            payload = self._read_json()
            note_id = urllib.parse.unquote(self.path.removeprefix(note_prefix))
            current = type(self).pages.get(note_id)
            if current is None:
                self._json(404, {"detail": "not found"})
                return
            overlay = current["overlay"]
            assert isinstance(overlay, dict)
            if payload.get("expected_revision") != overlay["revision"]:
                self._json(409, {"detail": {"code": "overlay_revision_conflict"}})
                return
            updated = self._page(
                note_id,
                str(overlay["relative_path"]),
                int(overlay["revision"]) + 1,
            )
            type(self).pages[note_id] = updated
            self._json(200, updated)
            return
        self._json(404, {"detail": "unexpected"})

    def _read_json(self) -> dict[str, object]:
        size = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(size) or b"{}")

    def log_message(self, *_args):
        return


@contextmanager
def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_controlled_proof_fails_closed_when_api_has_no_instance_nonce(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    _NoNonceHandler.requests = []
    with _serve(_NoNonceHandler) as api_url:
        result = subprocess.run(
            [
                *_command(inputs, api_url),
                "--run-controlled-proof",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 3
    report = inputs["report"].read_text(encoding="utf-8")
    assert "instance_nonce_missing" in report
    assert "controlled proof: BLOCKED" in report
    assert str(inputs["external"]) not in report
    assert "test-only-token" not in report
    assert _NoNonceHandler.requests == [
        (
            "GET",
            "/api/deeper-notebook/overlay/proof-identity",
            "Bearer test-only-token",
        )
    ]
    assert not list(inputs["overlay"].glob("overlay-proof-*"))
    assert os.stat(inputs["token"]).st_mode & 0o222 == 0


def test_controlled_proof_refuses_root_digest_mismatch_before_mutation(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    _ControlledProofHandler.reset(inputs["overlay"])
    _ControlledProofHandler.overlay_root_sha256 = "0" * 64

    with _serve(_ControlledProofHandler) as api_url:
        result = subprocess.run(
            [*_command(inputs, api_url), "--run-controlled-proof"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 3
    report = inputs["report"].read_text(encoding="utf-8")
    assert "overlay_root_identity_mismatch" in report
    assert not [
        request
        for request in _ControlledProofHandler.requests
        if request[0] in {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert not list(inputs["overlay"].glob("overlay-proof-*"))
    assert not (
        inputs["overlay"] / ".deeper-notebook-overlay-proof-state.json"
    ).exists()


def test_controlled_proof_refuses_malformed_openapi_before_mutation(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    _ControlledProofHandler.reset(inputs["overlay"])
    _ControlledProofHandler.openapi_payload = {"unexpected": "shape"}

    with _serve(_ControlledProofHandler) as api_url:
        result = subprocess.run(
            [*_command(inputs, api_url), "--run-controlled-proof"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 5
    assert "openapi_route_audit_failed" in inputs["report"].read_text(
        encoding="utf-8"
    )
    assert not [
        request
        for request in _ControlledProofHandler.requests
        if request[0] in {"POST", "PUT", "PATCH", "DELETE"}
    ]


def test_controlled_proof_rejects_unapproved_post_vault_route_before_mutation(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    _ControlledProofHandler.reset(inputs["overlay"])
    _ControlledProofHandler.openapi_payload = {
        "paths": {
            "/api/deeper-notebook/vaults/{vault_id}/pages/{note_id}": {"get": {}},
            "/api/deeper-notebook/vaults/{vault_id}/write": {"post": {}},
        }
    }

    with _serve(_ControlledProofHandler) as api_url:
        result = subprocess.run(
            [*_command(inputs, api_url), "--run-controlled-proof"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 5
    report = inputs["report"].read_text(encoding="utf-8")
    assert "unsafe_external_vault_mutation_route" in report
    assert "POST /api/deeper-notebook/vaults/{vault_id}/write" in report
    assert not [
        request
        for request in _ControlledProofHandler.requests
        if request[0] in {"POST", "PUT", "PATCH", "DELETE"}
    ]


def test_controlled_proof_uses_exact_root_and_resumes_after_external_restart(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    _ControlledProofHandler.reset(inputs["overlay"])

    with _serve(_ControlledProofHandler) as api_url:
        first = subprocess.run(
            [*_command(inputs, api_url), "--run-controlled-proof"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        first_requests = list(_ControlledProofHandler.requests)

        assert first.returncode == 4, first.stderr
        first_report = inputs["report"].read_text(encoding="utf-8")
        assert "native_restart_requires_external_restart" in first_report
        assert "native_restart: `pending`" in first_report
        assert first_requests[0][1] == ("/api/deeper-notebook/overlay/proof-identity")
        assert first_requests[-1][1] == ("/api/deeper-notebook/overlay/proof-identity")
        assert all(auth == "Bearer test-only-token" for _, _, auth in first_requests)
        assert not list(inputs["overlay"].glob("overlay-proof-*"))

        state_path = inputs["overlay"] / ".deeper-notebook-overlay-proof-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        expected_root_digest = hashlib.sha256(
            str(inputs["overlay"].resolve()).encode("utf-8")
        ).hexdigest()
        assert state["overlay_root_sha256"] == expected_root_digest
        assert str(inputs["overlay"]) not in state_path.read_text(encoding="utf-8")
        assert str(inputs["external"]) not in state_path.read_text(encoding="utf-8")
        assert "test-only-token" not in state_path.read_text(encoding="utf-8")
        assert "Synthetic controlled proof" not in state_path.read_text(
            encoding="utf-8"
        )

        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        try:
            _ControlledProofHandler.instance_nonce = "b" * 43
            _ControlledProofHandler.instance_pid = sleeper.pid
            second_start = len(_ControlledProofHandler.requests)
            second = subprocess.run(
                [*_command(inputs, api_url), "--run-controlled-proof"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            second_requests = _ControlledProofHandler.requests[second_start:]
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)

    assert second.returncode == 0, second.stderr
    second_report = inputs["report"].read_text(encoding="utf-8")
    assert "controlled proof: PASSED" in second_report
    assert "native_restart: `passed`" in second_report
    assert second_requests[0][1] == ("/api/deeper-notebook/overlay/proof-identity")
    assert second_requests[-1][1] == ("/api/deeper-notebook/overlay/proof-identity")
    assert not [
        request
        for request in second_requests
        if request[0] in {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert str(inputs["overlay"]) not in second_report
    assert str(inputs["external"]) not in second_report
    assert "test-only-token" not in second_report


def test_controlled_proof_refuses_malformed_restart_state_without_network(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    state_path = inputs["overlay"] / ".deeper-notebook-overlay-proof-state.json"
    state_path.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [*_command(inputs, "http://127.0.0.1:9"), "--run-controlled-proof"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "restart_state_invalid"
    assert not inputs["report"].exists()


def test_controlled_proof_refuses_mismatched_restart_state_without_network(
    tmp_path: Path,
):
    inputs = _proof_inputs(tmp_path)
    state_path = inputs["overlay"] / ".deeper-notebook-overlay-proof-state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "phase": "awaiting_restart",
                "previous_instance_nonce_sha256": "1" * 64,
                "previous_instance_pid": os.getpid(),
                "overlay_root_sha256": "0" * 64,
                "external_fingerprints": {
                    "evidence.md": hashlib.sha256(
                        b"# Synthetic external evidence\n"
                    ).hexdigest()
                },
                "external_git_status": "2" * 64,
                "expected_pages": [
                    {
                        "id": "overlay_note:daily",
                        "relative_path": "daily/2026-07-30.md",
                        "revision": 1,
                        "content_hash": "3" * 64,
                    }
                ],
                "request_ids": ["overlay-proof-prior"],
                "completed_instance_nonce_sha256": None,
                "completed_instance_pid": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [*_command(inputs, "http://127.0.0.1:9"), "--run-controlled-proof"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "restart_state_root_mismatch"
    assert not inputs["report"].exists()
