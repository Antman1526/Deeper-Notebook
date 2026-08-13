from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_study_workbench.py"


def _marked_root(path: Path, marker: str, value: str) -> Path:
    path.mkdir()
    (path / marker).write_text(value + "\n", encoding="utf-8")
    os.chmod(path, 0o700)
    return path


def test_verifier_requires_restart_and_preserves_external_fixture(tmp_path: Path):
    """The bounded fixture proves prepare/verify without touching user data."""
    from scripts.verify_study_workbench import run_verifier_fixture

    result = run_verifier_fixture(tmp_path)

    assert result.prepare_exit == 5
    assert result.verify_exit == 0
    assert result.source_hash_before == result.source_hash_after
    assert result.external_writes == 0
    assert result.cleanup.owned_processes == 0
    assert result.cleanup.ports == 0


def test_task_root_is_unique_mode_0700_and_non_symlink(tmp_path: Path):
    from scripts.verify_study_workbench import ProofRefusal, validate_task_root

    root = _marked_root(
        tmp_path / "task",
        ".deeper-notebook-study-proof-root",
        "study-workbench-proof-root-v1",
    )
    assert validate_task_root(root) == root.resolve()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700

    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ProofRefusal, match="symlink"):
        validate_task_root(alias)


def test_external_sentinel_is_disjoint_and_hash_is_stable(tmp_path: Path):
    from scripts.verify_study_workbench import (
        ProofRefusal,
        hash_tree,
        validate_external_root,
    )

    task = _marked_root(
        tmp_path / "task",
        ".deeper-notebook-study-proof-root",
        "study-workbench-proof-root-v1",
    )
    external = _marked_root(
        tmp_path / "external",
        ".deeper-notebook-study-external-sentinel",
        "study-workbench-external-sentinel-v1",
    )
    payload = external / "sentinel.txt"
    payload.write_text("immutable synthetic sentinel\n", encoding="utf-8")
    before = hash_tree(external)
    assert validate_external_root(external, task) == external.resolve()
    assert hash_tree(external) == before

    with pytest.raises(ProofRefusal, match="disjoint"):
        validate_external_root(task / "nested", task)


def test_explicit_loopback_url_rejects_credentials_and_non_loopback():
    from scripts.verify_study_workbench import ProofRefusal, validate_loopback_url

    assert validate_loopback_url("http://127.0.0.1:43121") == "http://127.0.0.1:43121"
    with pytest.raises(ProofRefusal):
        validate_loopback_url("http://user:pass@127.0.0.1:43121")
    with pytest.raises(ProofRefusal):
        validate_loopback_url("https://127.0.0.1:43121")
    with pytest.raises(ProofRefusal):
        validate_loopback_url("http://example.invalid:43121")


def test_receipt_rejects_stale_pid_nonce_and_source_hash(tmp_path: Path):
    from scripts.verify_study_workbench import (
        ProofRefusal,
        RestartReceipt,
        validate_restart_receipt,
    )

    receipt = RestartReceipt(
        version=1,
        phase="awaiting_restart",
        task_root_sha256=hashlib.sha256(str(tmp_path).encode()).hexdigest(),
        namespace="study_ns_abc",
        database="study_db_abc",
        previous_api_pid=1001,
        previous_api_start_token="start-a",
        previous_api_argv_sha256="a" * 64,
        previous_listener_port=43121,
        source_hashes={"pdf": "b" * 64, "video": "c" * 64},
        external_hashes={"sentinel.txt": "d" * 64},
        external_writes=0,
    )
    assert validate_restart_receipt(receipt, tmp_path) == receipt
    with pytest.raises(ProofRefusal, match="stale|mismatch"):
        validate_restart_receipt(
            receipt.__class__(
                **{
                    **receipt.__dict__,
                    "source_hashes": {"pdf": "0" * 64, "video": "c" * 64},
                }
            ),
            tmp_path,
        )


def test_sanitized_receipts_do_not_leak_secrets_paths_or_payloads():
    from scripts.verify_study_workbench import sanitize_receipt

    rendered = sanitize_receipt(
        {
            "token": "super-secret",
            "password": "db-password",
            "prompt": "private source contents",
            "path": "/Users/Antman/Documents/private.pdf",
            "source_hash": "a" * 64,
            "status": "passed",
        }
    )
    assert "super-secret" not in rendered
    assert "db-password" not in rendered
    assert "private source contents" not in rendered
    assert "/Users/Antman" not in rendered
    assert "a" * 64 in rendered
    assert "passed" in rendered


def test_internal_blocker_allows_only_bounded_stage_codes():
    from scripts.verify_study_workbench import _internal_blocker

    assert _internal_blocker("anki_import_preview") == (
        "verification_internal_error:anki_import_preview"
    )
    assert _internal_blocker("secret/path?token=super-secret") == (
        "verification_internal_error:unknown"
    )


def test_http_request_accepts_binary_download_payload(monkeypatch):
    from scripts.verify_study_workbench import _http_request

    binary_package = b"\x80\x81synthetic-apkg"

    class Response:
        status = 200
        headers = {}

        def read(self, _limit: int) -> bytes:
            return binary_package

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    result = _http_request("http://127.0.0.1:43121", "GET", "/download")
    assert result.payload is None
    assert result.body == binary_package


def test_frontend_completion_cookie_is_exact_and_loopback_scoped():
    from scripts.verify_study_workbench import _frontend_request_headers

    assert _frontend_request_headers() == {"Cookie": "wizard_completed=1"}
    assert "Authorization" not in _frontend_request_headers()


def test_task_surreal_password_is_restart_stable_and_task_bound(tmp_path: Path):
    from types import SimpleNamespace

    from scripts.verify_study_workbench import _task_surreal_password

    inputs = SimpleNamespace(
        task_root=tmp_path / "task",
        namespace="study_ns_fixture000000",
        database="study_db_fixture000000",
    )
    first = _task_surreal_password(inputs)
    assert first == _task_surreal_password(inputs)
    assert len(first) == 32
    other = SimpleNamespace(
        task_root=tmp_path / "other",
        namespace=inputs.namespace,
        database=inputs.database,
    )
    assert _task_surreal_password(other) != first


def test_loopback_model_fixture_payloads_match_product_schemas():
    """Keep deterministic provider responses inside the real typed contracts."""
    from deeper_notebook.studio.schemas.documents import (
        FlashcardsDocument,
        GenericDocument,
    )
    from deeper_notebook.study.syllabus_service import StudySyllabusDocument

    guide = GenericDocument.model_validate(
        {
            "artifact_type": "study_guide",
            "title": "Synthetic evidence guide",
            "summary": "A bounded source-grounded guide.",
            "sections": [
                {
                    "heading": "Evidence",
                    "body": "Synthetic evidence is selected before study output.",
                    "citations": ["[S1]"],
                }
            ],
        }
    )
    cards = FlashcardsDocument.model_validate(
        {
            "artifact_type": "flashcards",
            "title": "Synthetic evidence cards",
            "cards": [
                {
                    "front": "What is durable?",
                    "back": "The source and study receipts are durable.",
                    "citations": ["[S1]"],
                }
            ],
        }
    )
    syllabus = StudySyllabusDocument.model_validate(
        {
            "artifact_type": "study_syllabus",
            "title": "Synthetic Study Syllabus",
            "units": [
                {
                    "unit_id": "foundations",
                    "title": "Synthetic evidence foundations",
                    "objectives": ["Explain source-grounded evidence"],
                    "prerequisite_unit_ids": [],
                    "estimated_minutes": 10,
                    "source_ids": ["source:pdf"],
                    "activities": [],
                }
            ],
            "knowledge_gaps": [],
        }
    )
    assert guide.sections[0].body
    assert cards.cards[0].citations == ["[S1]"]
    assert syllabus.units[0].source_ids == ["source:pdf"]


def test_loopback_model_fixture_preserves_canonical_surreal_source_ids():
    from scripts.verify_study_workbench import _MODEL_SERVER_SOURCE

    assert "source:(?:⟨[^⟩]{1,256}⟩|[A-Za-z0-9_-]{1,256})" in _MODEL_SERVER_SOURCE


def test_loopback_model_fixture_routes_assistant_schema_before_context_terms():
    from scripts.verify_study_workbench import _MODEL_SERVER_SOURCE

    assert (
        '"Return one JSON object with answer, citations, and proposed_actions."'
        in _MODEL_SERVER_SOURCE
    )
    assert _MODEL_SERVER_SOURCE.index("requested_schema") < _MODEL_SERVER_SOURCE.index(
        "schema_fields"
    )


def test_loopback_model_fixture_dispatches_by_requested_schema_not_context_keywords():
    from scripts.verify_study_workbench import _MODEL_SERVER_SOURCE

    assert "def _requested_schema(payload):" in _MODEL_SERVER_SOURCE
    assert 'schema.get("properties", {})' in _MODEL_SERVER_SOURCE
    assert '{"answer", "citations", "proposed_actions"}' in _MODEL_SERVER_SOURCE
    assert '{"artifact_type", "units", "knowledge_gaps"}' in _MODEL_SERVER_SOURCE
    assert "requested_schema" in _MODEL_SERVER_SOURCE


def test_interrupt_cleanup_stops_exact_stack_once_and_restores_handlers():
    import signal

    from scripts.verify_study_workbench import InterruptCleanup

    class FakeStack:
        def __init__(self):
            self.stop_calls = 0

        def stop(self):
            self.stop_calls += 1

    stack = FakeStack()
    cleanup = InterruptCleanup(lambda: stack)
    previous = signal.getsignal(signal.SIGTERM)
    cleanup.install()
    try:
        handler = signal.getsignal(signal.SIGTERM)
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGTERM, None)
        # Re-entrant delivery must not widen cleanup or stop a child twice.
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGTERM, None)
        assert stack.stop_calls == 1
    finally:
        cleanup.restore()
    assert signal.getsignal(signal.SIGTERM) is previous


def test_verifier_check_rejects_broad_roots_without_mutation(tmp_path: Path):
    task = _marked_root(
        tmp_path / "task",
        ".deeper-notebook-study-proof-root",
        "study-workbench-proof-root-v1",
    )
    external = _marked_root(
        tmp_path / "external",
        ".deeper-notebook-study-external-sentinel",
        "study-workbench-external-sentinel-v1",
    )
    command = [
        sys.executable,
        str(SCRIPT),
        "--proof-phase",
        "check",
        "--task-root",
        str(task),
        "--external-sentinel-root",
        str(external),
        "--api-url",
        "http://127.0.0.1:43121",
        "--frontend-url",
        "http://127.0.0.1:43122",
        "--api-port",
        "43121",
        "--frontend-port",
        "43122",
        "--namespace",
        "study_ns_check",
        "--database",
        "study_db_check",
    ]
    broad = list(command)
    broad[broad.index("--task-root") + 1] = str(Path.home())
    result = subprocess.run(
        command if False else broad,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "refused_root" in result.stderr
    assert not (task / ".study-workbench-restart.json").exists()


def test_previous_process_identity_check_does_not_spawn_probe_process(monkeypatch):
    from scripts.verify_study_workbench import (
        ProcessIdentity,
        RestartReceipt,
        previous_processes_are_gone,
    )

    receipt = RestartReceipt(
        1,
        "awaiting_restart",
        "a" * 64,
        "study_ns_check",
        "study_db_check",
        99999,
        "start-token",
        "b" * 64,
        43121,
        {"pdf": "c" * 64},
        {"sentinel.txt": "d" * 64},
        0,
        (ProcessIdentity("api", 99999, "start-token", "e" * 64, 43121),),
    )

    def fail(*_args, **_kwargs):
        raise AssertionError("probe must not spawn a process")

    # The identity matcher itself is the ownership probe.  Stub its platform
    # lookup so this regression test catches the old ``Popen(["true"])`` leak
    # without making ``ps`` subprocess details part of the contract.
    monkeypatch.setattr(
        "scripts.verify_study_workbench._process_matches", lambda _identity: False
    )
    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.Popen", fail)
    assert previous_processes_are_gone(receipt)
