from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_unified_knowledge_engine.py"


def _space_id(source_ref: str) -> str:
    return "knowledge_engine_space:" + hashlib.sha256(source_ref.encode()).hexdigest()


def _verifier_module():
    spec = importlib.util.spec_from_file_location(
        "verify_unified_knowledge_engine_test_module",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Handler(BaseHTTPRequestHandler):
    status_code = 200
    payload: object = {"passed": True, "differences": []}
    expected_token = "test-only-token"
    requests: list[tuple[str, str, str | None]] = []
    proof_identity: object = {
        "instance_nonce": "n" * 43,
        "instance_pid": 12345,
        "overlay_root_sha256": "a" * 64,
    }

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )
        payload = (
            {"projected": 1, "unchanged": 0, "failed": 0}
            if self.path == "/api/deeper-notebook/knowledge-engine/status"
            else type(self).proof_identity
            if self.path == "/api/deeper-notebook/overlay/proof-identity"
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
    return {
        "token": token,
        "report": tmp_path / "report.json",
        "state": tmp_path / "restart-state.json",
        "database": tmp_path / "synthetic.db",
    }


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


def _marked_manifest(tmp_path: Path, inputs: dict[str, Path]) -> Path:
    temporary = Path(tempfile.gettempdir()).resolve()
    root = temporary / f"unified-engine-proof-{uuid.uuid4().hex}"
    roots = {name: root / name for name in ("overlay", "parent", "child")}
    for path in roots.values():
        path.mkdir(parents=True)
        (path / ".deeper-notebook-synthetic-proof-v1").write_text(
            "synthetic-proof-v1\n", encoding="utf-8"
        )
    inputs["database"].mkdir()
    (inputs["database"] / ".deeper-notebook-synthetic-proof-v1").write_text(
        "synthetic-proof-v1\n", encoding="utf-8"
    )
    manifest = tmp_path / "synthetic-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "marker": ".deeper-notebook-synthetic-proof-v1",
                "roots": {name: str(path) for name, path in roots.items()},
                "paths": {
                    "database": str(inputs["database"]),
                    "state": str(inputs["state"]),
                    "report": str(inputs["report"]),
                    "token": str(inputs["token"]),
                },
                "expected": {
                    "overlay_note_id": "overlay_note:synthetic",
                    "overlay_revision": 1,
                    "overlay_title": "Synthetic proof",
                    "overlay_markdown": "# Synthetic proof\n",
                    "overlay_idempotency_key": "synthetic-proof-update",
                    "parent_vault_id": "vault_mount:parent",
                    "parent_name": "synthetic-parent",
                    "child_name": "synthetic-child",
                    "manifest_relative_path": "trust.json",
                    "minimum_parent_files": 1,
                    "minimum_child_files": 2,
                    "minimum_tasks": 1,
                    "minimum_graph_edges": 1,
                    "minimum_trust_records": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _proof_command(
    inputs: dict[str, Path], api_url: str, phase: str, manifest: Path
) -> list[str]:
    return _command(inputs, api_url) + [
        "--proof-phase",
        phase,
        "--synthetic-manifest",
        str(manifest),
        "--expected-prior-state",
        str(inputs["state"]),
    ]


def test_verifier_writes_a_private_redacted_atomic_success_report(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    _Handler.status_code = 200
    _Handler.payload = {"passed": True, "differences": []}
    _Handler.requests = []

    with _server() as api_url:
        result = subprocess.run(
            _command(inputs, api_url),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(inputs["report"].stat().st_mode) == 0o600
    report = json.loads(inputs["report"].read_text(encoding="utf-8"))
    assert report == {
        "passed": True,
        "spaces": [{"passed": True, "space_id": "knowledge_engine_space:fixture"}],
    }
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
        ),
    ]


def test_verifier_returns_mismatch_without_copying_difference_values(
    tmp_path: Path,
) -> None:
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
            _command(inputs, api_url),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 4
    contents = inputs["report"].read_text(encoding="utf-8")
    assert "private note text" not in contents
    assert "test-only-token" not in contents
    assert "document_hash_mismatch" in contents


@pytest.mark.parametrize(
    "code",
    [
        "unreviewed_private_difference",
        "document_hash_mismatch/private",
        "document_hash_mismatch-token",
        "document_hash_mismatch\x00",
    ],
)
def test_verifier_refuses_unknown_or_unsafe_difference_codes_without_writing_report(
    tmp_path: Path, code: str
) -> None:
    inputs = _inputs(tmp_path)
    _Handler.status_code = 200
    _Handler.payload = {
        "passed": False,
        "differences": [{"code": code}],
    }

    with _server() as api_url:
        result = subprocess.run(
            _command(inputs, api_url),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    assert result.returncode == 2
    assert not inputs["report"].exists()


@pytest.mark.parametrize(
    "space_id",
    [
        "knowledge_engine_space:fixture/path",
        "knowledge_engine_space:",
        "knowledge_engine_space:fixture.token",
    ],
)
def test_verifier_refuses_noncanonical_space_id_without_contacting_api(
    tmp_path: Path, space_id: str
) -> None:
    inputs = _inputs(tmp_path)
    command = _command(inputs, "http://127.0.0.1:9")
    command[command.index("knowledge_engine_space:fixture")] = space_id

    result = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )

    assert result.returncode == 2
    assert not inputs["report"].exists()


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
            _command(inputs, api_url),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    assert disabled.returncode == 3
    assert not inputs["report"].exists()


def test_verifier_refuses_report_inside_its_repository_source_root(
    tmp_path: Path,
) -> None:
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


def test_verifier_maps_loopback_transport_failure_to_unavailable(
    tmp_path: Path,
) -> None:
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


def test_controlled_prepare_refuses_unmarked_or_non_temporary_roots_before_api(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    manifest = _marked_manifest(tmp_path, inputs)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["roots"]["child"] = "/Users/Antman/Desktop/2nd Brains"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        _proof_command(inputs, "http://127.0.0.1:9", "prepare", manifest),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "synthetic_manifest_invalid"
    assert not inputs["report"].exists()


def test_controlled_verify_is_get_only_and_requires_a_changed_process_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = _inputs(tmp_path)
    manifest = _marked_manifest(tmp_path, inputs)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    projection_snapshot = {"counts": {"knowledge_documents": 3}}
    overlay_snapshot = {"id": "overlay_note:synthetic", "revision": 2}
    inputs["state"].write_text(
        json.dumps(
            {
                "state": "knowledge_engine_restart_required",
                "proof_identity": {
                    "instance_nonce": "o" * 43,
                    "instance_pid": 12344,
                    "overlay_root_sha256": "a" * 64,
                },
                "backfill_before_restart": [
                    {
                        "space_id": _space_id("overlay:default"),
                        "status": "completed",
                        "projected": 1,
                        "unchanged": 0,
                        "failed": 0,
                    },
                    {
                        "space_id": _space_id("vault_mount:parent"),
                        "status": "completed",
                        "projected": 1,
                        "unchanged": 0,
                        "failed": 0,
                    },
                ],
                "external_after": {
                    name: {"fingerprints": {}, "git_status_sha256": None}
                    for name in ("overlay", "parent", "child")
                },
                "parent_vault_id": "vault_mount:parent",
                "child_vault_id": "vault_mount:child",
                "projection_snapshot": projection_snapshot,
                "overlay_snapshot": overlay_snapshot,
                "trust_import_replay": {
                    "second": {
                        "changed": 0,
                        "unchanged": 1,
                        "resolved": 1,
                        "unresolved": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    parsed_inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=inputs["token"],
        report_path=inputs["report"],
        space_ids=("knowledge_engine_space:fixture",),
        exact_queries=("research",),
        require_shadow_enabled=True,
        proof_phase="verify",
        synthetic_manifest=manifest,
        expected_prior_state=inputs["state"],
    )
    current_identity = {
        "instance_nonce": "n" * 43,
        "instance_pid": 12345,
        "overlay_root_sha256": "a" * 64,
    }
    monkeypatch.setattr(module, "_proof_identity", lambda *_args: current_identity)
    monkeypatch.setattr(
        module,
        "_synthetic_fingerprints",
        lambda *_args: {},
    )
    monkeypatch.setattr(module, "_synthetic_git_digest", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "_capture_projection_snapshot",
        lambda *_args: projection_snapshot,
    )
    monkeypatch.setattr(
        module,
        "_overlay_evidence",
        lambda *_args: overlay_snapshot,
    )
    checkpoint_requests: list[tuple[str, ...]] = []

    def terminal_checkpoints(_inputs, _token, space_ids):
        checkpoint_requests.append(space_ids)
        return [
            {
                "space_id": space_id,
                "status": "completed",
                "projected": 0,
                "unchanged": 1,
                "failed": 0,
            }
            for space_id in sorted(space_ids)
        ]

    monkeypatch.setattr(module, "_wait_for_terminal_backfill", terminal_checkpoints)

    def read_only_run(run_inputs):
        module._write_report(
            run_inputs.report_path,
            {
                "passed": True,
                "spaces": [
                    {
                        "space_id": "knowledge_engine_space:fixture",
                        "passed": True,
                    }
                ],
            },
        )
        return 0

    monkeypatch.setattr(module, "run", read_only_run)
    monkeypatch.setattr(
        module,
        "_json_request",
        lambda *_args, **_kwargs: pytest.fail("verify must not mutate"),
    )

    result = module._controlled_verify(
        parsed_inputs,
        manifest_payload,
        "test-only-token",
    )

    assert result == 0
    report = json.loads(inputs["report"].read_text(encoding="utf-8"))
    assert report["controlled_proof"]["restart_verified"] is True
    assert report["controlled_proof"]["prior_instance_pid"] == 12344
    assert report["controlled_proof"]["current_instance_pid"] == 12345
    expected_child_space = (
        "knowledge_engine_space:"
        + hashlib.sha256(b"vault_mount:child").hexdigest()
    )
    assert checkpoint_requests == [
        tuple(
            sorted(
                (
                    _space_id("overlay:default"),
                    _space_id("vault_mount:parent"),
                    expected_child_space,
                )
            )
        )
    ]
    assert {
        item["space_id"]
        for item in report["controlled_proof"]["backfill_after_restart"]
    } == {
        _space_id("overlay:default"),
        _space_id("vault_mount:parent"),
        expected_child_space,
    }


def test_controlled_proof_refuses_aliasing_its_restart_state_and_report(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    manifest = _marked_manifest(tmp_path, inputs)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["paths"]["state"] = payload["paths"]["report"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        _proof_command(inputs, "http://127.0.0.1:9", "prepare", manifest),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "synthetic_manifest_invalid"


def test_controlled_manifest_accepts_the_argparse_path_object(tmp_path: Path) -> None:
    module = _verifier_module()
    inputs = _inputs(tmp_path)
    manifest = _marked_manifest(tmp_path, inputs)
    parsed_inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=inputs["token"].resolve(),
        report_path=inputs["report"],
        space_ids=("knowledge_engine_space:fixture",),
        exact_queries=("research",),
        require_shadow_enabled=True,
        proof_phase="prepare",
        synthetic_manifest=manifest,
        expected_prior_state=inputs["state"],
    )

    payload = module._proof_manifest(parsed_inputs)

    assert payload["schema_version"] == 1
    assert payload["expected"]["parent_vault_id"] == "vault_mount:parent"


def test_controlled_startup_checkpoint_ids_are_derived_from_actual_sources() -> None:
    module = _verifier_module()

    assert module._startup_checkpoint_space_ids("vault_mount:parent") == tuple(
        sorted(
            (
                _space_id("overlay:default"),
                _space_id("vault_mount:parent"),
            )
        )
    )


def test_controlled_manifest_rejects_supplied_startup_checkpoint_ids(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    manifest = _marked_manifest(tmp_path, inputs)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["expected"]["startup_checkpoint_space_ids"] = [
        "knowledge_engine_space:" + "0" * 64,
        "knowledge_engine_space:" + "1" * 64,
    ]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        _proof_command(inputs, "http://127.0.0.1:9", "prepare", manifest),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "synthetic_manifest_invalid"


def test_controlled_scan_runs_two_rounds_across_the_stabilization_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=tmp_path / "token",
        report_path=tmp_path / "report.json",
        space_ids=("knowledge_engine_space:fixture",),
        exact_queries=("research",),
        require_shadow_enabled=True,
    )
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_request(_inputs, _token, _method, path, _payload):
        calls.append(path)
        return 200, {
            "state": "ready-read-only",
            "observed": 1,
            "parsed": 0 if len(calls) <= 2 else 1,
            "unchanged": 0,
            "unsupported": 0,
            "invalid": 0,
            "missing": 0,
        }

    monkeypatch.setattr(module, "_json_request", fake_request)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    assert module._scan_vaults(
        inputs,
        "test-token",
        ("vault_mount:parent", "vault_mount:child"),
    )
    assert calls == [
        "/api/deeper-notebook/vaults/vault_mount:parent/scan",
        "/api/deeper-notebook/vaults/vault_mount:child/scan",
        "/api/deeper-notebook/vaults/vault_mount:parent/scan",
        "/api/deeper-notebook/vaults/vault_mount:child/scan",
    ]
    assert sleeps == [module.SCAN_STABILIZATION_SECONDS]


def test_controlled_proof_waits_for_every_persisted_checkpoint_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=tmp_path / "token",
        report_path=tmp_path / "report.json",
        space_ids=("knowledge_engine_space:overlay",),
        exact_queries=("research",),
        require_shadow_enabled=True,
    )
    expected_space_ids = (
        "knowledge_engine_space:overlay",
        "knowledge_engine_space:parent",
    )
    responses = iter(
        [
            (
                200,
                [
                    {
                        "space_id": "knowledge_engine_space:overlay",
                        "status": "running",
                        "projected": 1,
                        "unchanged": 0,
                        "failed": 0,
                    }
                ],
            ),
            (
                200,
                [
                    {
                        "space_id": "knowledge_engine_space:parent",
                        "status": "completed",
                        "projected": 1,
                        "unchanged": 0,
                        "failed": 0,
                    },
                    {
                        "space_id": "knowledge_engine_space:overlay",
                        "status": "completed",
                        "projected": 1,
                        "unchanged": 0,
                        "failed": 0,
                    },
                ],
            ),
        ]
    )
    paths: list[str] = []
    sleeps: list[float] = []

    def fake_get(_inputs, _token, path):
        paths.append(path)
        return next(responses)

    monotonic_values = iter((0.0, 0.1, 0.2))
    monkeypatch.setattr(module, "_get", fake_get)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    checkpoints = module._wait_for_terminal_backfill(
        inputs,
        "test-token",
        expected_space_ids,
    )

    assert [item["space_id"] for item in checkpoints] == sorted(expected_space_ids)
    assert all(item["status"] == "completed" for item in checkpoints)
    assert len(paths) == 2
    assert all(
        path.startswith(
            "/api/deeper-notebook/knowledge-engine/backfill-checkpoints?"
        )
        for path in paths
    )
    assert sleeps == [module.BACKFILL_POLL_SECONDS]


def test_controlled_prepare_never_mutates_when_backfill_is_not_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = _inputs(tmp_path)
    manifest_path = _marked_manifest(tmp_path, inputs)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parsed_inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=inputs["token"],
        report_path=inputs["report"],
        space_ids=("knowledge_engine_space:overlay",),
        exact_queries=("research",),
        require_shadow_enabled=True,
        proof_phase="prepare",
        synthetic_manifest=manifest_path,
        expected_prior_state=inputs["state"],
    )
    monkeypatch.setattr(
        module,
        "_synthetic_root_evidence",
        lambda *_args: {"fingerprints": {}, "git_status_sha256": None},
    )
    monkeypatch.setattr(
        module,
        "_proof_identity",
        lambda *_args: {
            "instance_nonce": "n" * 43,
            "instance_pid": 12345,
            "overlay_root_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        module,
        "_wait_for_terminal_backfill",
        lambda *_args: (_ for _ in ()).throw(
            module.VerificationUnavailable("backfill_not_terminal")
        ),
    )
    monkeypatch.setattr(
        module,
        "_json_request",
        lambda *_args, **_kwargs: pytest.fail(
            "prepare must not mutate before terminal backfill"
        ),
    )

    with pytest.raises(module.VerificationUnavailable, match="backfill_not_terminal"):
        module._controlled_prepare(parsed_inputs, manifest, "test-token")


def test_overlay_runtime_logs_are_excluded_from_source_fingerprints(
    tmp_path: Path,
) -> None:
    module = _verifier_module()
    marker = ".deeper-notebook-synthetic-proof-v1"
    overlay = tmp_path / "overlay"
    parent = tmp_path / "parent"
    for root in (overlay, parent):
        (root / "logs").mkdir(parents=True)
        (root / marker).write_text("synthetic-proof-v1\n", encoding="utf-8")
        (root / "Source.md").write_text("# Source\n", encoding="utf-8")
        (root / "logs" / "api.log").write_text("runtime log\n", encoding="utf-8")

    overlay_evidence = module._synthetic_root_evidence("overlay", overlay, marker)
    parent_evidence = module._synthetic_root_evidence("parent", parent, marker)

    assert set(overlay_evidence["fingerprints"]) == {"Source.md"}
    assert set(parent_evidence["fingerprints"]) == {"Source.md", "logs/api.log"}


def test_projection_capture_is_bounded_redacted_and_proves_required_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=tmp_path / "token",
        report_path=tmp_path / "report.json",
        space_ids=(
            "knowledge_engine_space:overlay",
            "knowledge_engine_space:parent",
            "knowledge_engine_space:child",
        ),
        exact_queries=("proof-needle",),
        require_shadow_enabled=True,
    )
    parent_id = "vault_mount:parent"
    child_id = "vault_mount:child"
    responses = {
        f"/api/deeper-notebook/vaults/{parent_id}": {
            "id": parent_id,
            "name": "synthetic-parent",
            "root_path": "/tmp/synthetic-parent",
            "format_mode": "markdown",
            "state": "ready-read-only",
            "parent_vault_id": None,
            "watch_enabled": False,
        },
        f"/api/deeper-notebook/vaults/{child_id}": {
            "id": child_id,
            "name": "synthetic-child",
            "root_path": "/tmp/synthetic-child",
            "format_mode": "markdown",
            "state": "ready-read-only",
            "parent_vault_id": parent_id,
            "watch_enabled": False,
        },
        f"/api/deeper-notebook/vaults/{parent_id}/files?limit=500&offset=0": [
            {
                "id": "vault_file:parent",
                "note_id": "note:parent",
                "vault_id": parent_id,
                "relative_path": "Parent.md",
                "file_kind": "markdown",
                "content_hash": "a" * 64,
                "parse_status": "parsed",
                "deleted_state": "present",
            },
            {
                "id": "vault_file:trust",
                "note_id": "note:trust",
                "vault_id": parent_id,
                "relative_path": "brain-engine/trust.json",
                "file_kind": "connector",
                "content_hash": "d" * 64,
                "parse_status": "unsupported",
                "deleted_state": "present",
            }
        ],
        f"/api/deeper-notebook/vaults/{child_id}/files?limit=500&offset=0": [
            {
                "id": "vault_file:child_a",
                "note_id": "note:child_a",
                "vault_id": child_id,
                "relative_path": "Child A.md",
                "file_kind": "markdown",
                "content_hash": "b" * 64,
                "parse_status": "parsed",
                "deleted_state": "present",
            },
            {
                "id": "vault_file:child_b",
                "note_id": "note:child_b",
                "vault_id": child_id,
                "relative_path": "Child B.md",
                "file_kind": "markdown",
                "content_hash": "c" * 64,
                "parse_status": "parsed",
                "deleted_state": "present",
            },
        ],
        f"/api/deeper-notebook/vaults/{parent_id}/pages/note:parent": {
            "file": {"id": "vault_file:parent"},
            "note": {"id": "note:parent", "content": "private-parent-body"},
            "blocks": [{"id": "note_block:parent", "markdown": "private block"}],
            "tasks": [],
            "outgoing_links": [],
            "backlinks": [],
        },
        f"/api/deeper-notebook/vaults/{child_id}/pages/note:child_a": {
            "file": {"id": "vault_file:child_a"},
            "note": {"id": "note:child_a", "content": "proof-needle private"},
            "blocks": [{"id": "note_block:child_a", "markdown": "private block"}],
            "tasks": [{"id": "knowledge_task:child_a", "status": "todo"}],
            "outgoing_links": [{"id": "note_link:child", "resolved": True}],
            "backlinks": [],
        },
        f"/api/deeper-notebook/vaults/{child_id}/pages/note:child_b": {
            "file": {"id": "vault_file:child_b"},
            "note": {"id": "note:child_b", "content": "private-child-body"},
            "blocks": [{"id": "note_block:child_b", "markdown": "private block"}],
            "tasks": [],
            "outgoing_links": [],
            "backlinks": [{"id": "note_link:child", "resolved": True}],
        },
        f"/api/deeper-notebook/vaults/{parent_id}/trust?limit=500&offset=0": [
            {
                "id": "vault_trust_record:one",
                "manifest_id": "synthetic-trust",
                "status": "approved",
                "resolution_state": "resolved",
                "content_hash": "d" * 64,
                "reviewer": "private-reviewer",
            }
        ],
        f"/api/deeper-notebook/vaults/{parent_id}/trust/summary": {
            "total": 1,
            "resolved": 1,
            "unresolved": 0,
        },
    }
    for vault_id, note_ids in (
        (parent_id, ("note:parent",)),
        (child_id, ("note:child_a", "note:child_b")),
    ):
        for note_id in note_ids:
            responses[
                f"/api/deeper-notebook/vaults/{vault_id}/pages/{note_id}/outgoing"
            ] = (
                [{"id": "note_link:child", "resolved": True}]
                if note_id == "note:child_a"
                else []
            )
            responses[
                f"/api/deeper-notebook/vaults/{vault_id}/pages/{note_id}/backlinks"
            ] = (
                [{"id": "note_link:child", "resolved": True}]
                if note_id == "note:child_b"
                else []
            )
            responses[
                f"/api/deeper-notebook/vaults/{vault_id}/graph?"
                + urllib.parse.urlencode(
                    {"center_note_id": note_id, "depth": 8, "limit": 500}
                )
            ] = {
                "nodes": [{"id": note_id}],
                "edges": ([{"id": "note_link:child"}] if vault_id == child_id else []),
            }
    for index, space_id in enumerate(inputs.space_ids):
        document_id = f"knowledge_engine_document:doc_{index}"
        responses[
            "/api/deeper-notebook/knowledge-engine/documents?"
            f"space_id={urllib.parse.quote(space_id, safe='')}&limit=500&offset=0"
        ] = [
            {
                "id": document_id,
                "space_id": space_id,
                "relative_locator": f"Private {index}.md",
                "source_hash": f"{index + 1:x}" * 64,
                "source_revision_id": f"knowledge_engine_source_revision:rev_{index}",
                "state": "current",
            }
        ]
        responses[f"/api/deeper-notebook/knowledge-engine/documents/{document_id}"] = {
            "id": document_id,
            "space_id": space_id,
            "relative_locator": f"Private {index}.md",
            "source_hash": f"{index + 1:x}" * 64,
            "source_revision_id": f"knowledge_engine_source_revision:rev_{index}",
            "state": "current",
            "normalized_body": (
                "proof-needle private body" if index == 2 else "private body"
            ),
        }

    def fake_get(_inputs, _token, path):
        assert path in responses, path
        return 200, responses[path]

    monkeypatch.setattr(module, "_get", fake_get)
    snapshot = module._capture_projection_snapshot(
        inputs,
        "test-token",
        {
            "roots": {
                "parent": "/tmp/synthetic-parent",
                "child": "/tmp/synthetic-child",
            },
            "expected": {
                "parent_name": "synthetic-parent",
                "child_name": "synthetic-child",
                "minimum_parent_files": 1,
                "minimum_child_files": 2,
                "minimum_tasks": 1,
                "minimum_graph_edges": 1,
                "minimum_trust_records": 1,
            },
        },
        parent_id,
        child_id,
    )

    rendered = json.dumps(snapshot, sort_keys=True)
    assert snapshot["counts"]["parent_files"] == 2
    assert {
        (item["file_kind"], item["parse_status"]) for item in snapshot["files"]
    } >= {("connector", "unsupported"), ("markdown", "parsed")}
    assert snapshot["counts"]["tasks"] == 1
    assert snapshot["counts"]["graph_edges"] >= 1
    assert snapshot["counts"]["trust_records"] == 1
    assert snapshot["exact_search_membership"][
        hashlib.sha256(b"proof-needle").hexdigest()
    ] == ["knowledge_engine_document:doc_2"]
    assert "private" not in rendered
    assert "proof-needle" not in rendered
    assert "/tmp/" not in rendered
    assert "reviewer" not in rendered


def test_projection_capture_rejects_unexpected_response_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verifier_module()
    inputs = module.Inputs(
        api_url="http://127.0.0.1:18181",
        token_path=tmp_path / "token",
        report_path=tmp_path / "report.json",
        space_ids=("knowledge_engine_space:fixture",),
        exact_queries=("needle",),
        require_shadow_enabled=True,
    )
    monkeypatch.setattr(
        module,
        "_get",
        lambda *_args: (200, {"id": "/absolute/private/path"}),
    )

    with pytest.raises(module.VerificationRefusal, match="api_response_invalid"):
        module._capture_projection_snapshot(
            inputs,
            "test-token",
            {
                "roots": {"parent": "/tmp/parent", "child": "/tmp/child"},
                "expected": {
                    "parent_name": "parent",
                    "child_name": "child",
                    "minimum_parent_files": 1,
                    "minimum_child_files": 1,
                    "minimum_tasks": 1,
                    "minimum_graph_edges": 1,
                    "minimum_trust_records": 1,
                },
            },
            "vault_mount:parent",
            "vault_mount:child",
        )
