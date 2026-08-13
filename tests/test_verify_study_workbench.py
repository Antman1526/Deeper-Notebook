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
        AssistantReceipt,
        ProcessIdentity,
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
        previous_processes=(
            ProcessIdentity("api", 1001, "start-a", "a" * 64, 43121),
            ProcessIdentity("worker", 1002, "start-w", "e" * 64, None),
            ProcessIdentity("frontend", 1003, "start-f", "f" * 64, 43122),
            ProcessIdentity("model", 1004, "start-m", "1" * 64, 43124),
        ),
        source_ids=("source:pdf", "source:video"),
        plan_id="study_plan:fixture",
        syllabus_version=1,
        artifact_ids=("study_artifact:fixture",),
        card_id="study_card:fixture",
        anki_job_id="study_anki_import:fixture",
        anki_receipt_id="study_anki_export:fixture",
        frontend_port=43122,
        surreal_port=43123,
        model_port=43124,
        surreal_container_name="dn-study-aaaaaaaaaaaa",
        surreal_container_id="a" * 12,
        anki_download_id="study_anki_download:fixture",
        anki_publish_receipt_id="study_anki_import:published",
        assistant_receipts=(
            AssistantReceipt(
                role="source_guide",
                invocation_id="study-proof-source-guide",
                session_id="study_assistant_session:source-guide",
                response_id="study_assistant_response:source-guide",
            ),
            AssistantReceipt(
                role="practice_coach",
                invocation_id="study-proof-practice-coach",
                session_id="study_assistant_session:practice-coach",
                response_id="study_assistant_response:practice-coach",
            ),
        ),
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


def test_restart_receipt_is_awaiting_restart_and_has_exact_parity_identities(tmp_path: Path):
    from scripts.verify_study_workbench import (
        ProofRefusal,
        RestartReceipt,
        validate_restart_receipt,
    )

    receipt = RestartReceipt(
        version=1,
        phase="complete",
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
    with pytest.raises(ProofRefusal, match="invalid"):
        validate_restart_receipt(receipt, tmp_path)

    with pytest.raises(ProofRefusal, match="invalid"):
        validate_restart_receipt(
            receipt.__class__(**{**receipt.__dict__, "phase": "awaiting_restart"}),
            tmp_path,
        )


def test_restart_receipt_binds_exact_owned_roles_and_listener_ports(tmp_path: Path):
    from scripts.verify_study_workbench import (
        AssistantReceipt,
        ProcessIdentity,
        ProofRefusal,
        RestartReceipt,
        validate_restart_receipt,
    )

    def make_receipt(processes):
        return RestartReceipt(
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
            previous_processes=tuple(processes),
            source_ids=("source:pdf", "source:video"),
            plan_id="study_plan:fixture",
            syllabus_version=1,
            artifact_ids=("study_artifact:fixture",),
            card_id="study_card:fixture",
            anki_job_id="study_anki_import:fixture",
            anki_receipt_id="study_anki_export:fixture",
            frontend_port=43122,
            surreal_port=43123,
            model_port=43124,
            surreal_container_name="dn-study-aaaaaaaaaaaa",
            surreal_container_id="a" * 12,
            anki_download_id="study_anki_download:fixture",
            anki_publish_receipt_id="study_anki_import:published",
            assistant_receipts=(),
        )

    exact = (
        ProcessIdentity("api", 1001, "start-a", "a" * 64, 43121),
        ProcessIdentity("worker", 1002, "start-w", "b" * 64, None),
        ProcessIdentity("frontend", 1003, "start-f", "c" * 64, 43122),
        ProcessIdentity("model", 1004, "start-m", "d" * 64, 43124),
    )
    receipt = make_receipt(exact)
    # The unit receipt omits assistant calls; this assertion isolates stack
    # role/port validation from the assistant parity contract.
    with pytest.raises(ProofRefusal, match="assistant"):
        validate_restart_receipt(receipt, tmp_path)

    assistant_receipts = (
        AssistantReceipt(
            role="source_guide",
            invocation_id="study-proof-source-guide",
            session_id="study_assistant_session:source-guide",
            response_id="study_assistant_response:source-guide",
        ),
        AssistantReceipt(
            role="practice_coach",
            invocation_id="study-proof-practice-coach",
            session_id="study_assistant_session:practice-coach",
            response_id="study_assistant_response:practice-coach",
        ),
    )
    receipt = receipt.__class__(
        **{**receipt.__dict__, "assistant_receipts": assistant_receipts}
    )
    assert validate_restart_receipt(receipt, tmp_path) == receipt

    wrong_role = receipt.__class__(
        **{
            **receipt.__dict__,
            "previous_processes": exact[:-1]
            + (ProcessIdentity("surreal", 1004, "start-m", "d" * 64, 43123),),
        }
    )
    with pytest.raises(ProofRefusal, match="role|listener"):
        validate_restart_receipt(wrong_role, tmp_path)

    wrong_port = receipt.__class__(
        **{
            **receipt.__dict__,
            "previous_processes": exact[:-1]
            + (ProcessIdentity("model", 1004, "start-m", "d" * 64, 43123),),
        }
    )
    with pytest.raises(ProofRefusal, match="role|listener"):
        validate_restart_receipt(wrong_port, tmp_path)


def _handoff_children():
    from types import SimpleNamespace

    from scripts.verify_study_workbench import ProcessIdentity

    identities = {
        "api": ProcessIdentity("api", 1001, "api-start", "a" * 64, 43121),
        "worker": ProcessIdentity("worker", 1002, "worker-start", "b" * 64, None),
        "frontend": ProcessIdentity("frontend", 1003, "frontend-start", "c" * 64, 43122),
        "model": ProcessIdentity("model", 1004, "model-start", "d" * 64, 43124),
    }
    children = [
        SimpleNamespace(
            identity=identity,
            process=SimpleNamespace(poll=lambda: None),
        )
        for identity in identities.values()
    ]
    return identities, children


def test_handoff_rejects_dead_worker_before_receipt(monkeypatch):
    from scripts.verify_study_workbench import ProofRefusal, assert_stack_handoff

    _identities, children = _handoff_children()
    worker = next(item for item in children if item.identity.role == "worker")
    worker.process = type("DeadProcess", (), {"poll": lambda _self: 1})()
    monkeypatch.setattr(
        "scripts.verify_study_workbench.process_identity",
        lambda pid, role, listener_port=None: next(
            item.identity
            for item in children
            if item.identity.pid == pid and item.identity.role == role
        ),
    )
    monkeypatch.setattr(
        "scripts.verify_study_workbench._listener_pids",
        lambda port: {43121: {1001}, 43122: {1003}, 43124: {1004}}[port],
    )

    with pytest.raises(ProofRefusal, match="worker.*alive|worker.*dead|worker.*exit"):
        assert_stack_handoff(children, {"api": 43121, "frontend": 43122, "model": 43124})


def test_handoff_rejects_changed_identity(monkeypatch):
    from scripts.verify_study_workbench import (
        ProcessIdentity,
        ProofRefusal,
        assert_stack_handoff,
    )

    identities, children = _handoff_children()
    changed = ProcessIdentity("worker", 1002, "worker-replaced", "b" * 64, None)
    monkeypatch.setattr(
        "scripts.verify_study_workbench.process_identity",
        lambda pid, role, listener_port=None: changed
        if role == "worker"
        else identities[role],
    )
    monkeypatch.setattr(
        "scripts.verify_study_workbench._listener_pids",
        lambda port: {43121: {1001}, 43122: {1003}, 43124: {1004}}[port],
    )

    with pytest.raises(ProofRefusal, match="worker.*identity|identity.*worker"):
        assert_stack_handoff(children, {"api": 43121, "frontend": 43122, "model": 43124})


def test_handoff_rejects_missing_listener(monkeypatch):
    from scripts.verify_study_workbench import ProofRefusal, assert_stack_handoff

    identities, children = _handoff_children()
    monkeypatch.setattr(
        "scripts.verify_study_workbench.process_identity",
        lambda pid, role, listener_port=None: identities[role],
    )
    monkeypatch.setattr(
        "scripts.verify_study_workbench._listener_pids",
        lambda _port: set(),
    )

    with pytest.raises(ProofRefusal, match="listener"):
        assert_stack_handoff(children, {"api": 43121, "frontend": 43122, "model": 43124})


def test_replacement_reusing_any_old_role_identity_is_rejected():
    from scripts.verify_study_workbench import (
        ProcessIdentity,
        ProofRefusal,
        assert_replacement_identities,
    )

    previous = {
        role: identity
        for role, identity in _handoff_children()[0].items()
    }
    current = {
        role: ProcessIdentity(
            role,
            identity.pid + 100,
            identity.start_token + "-new",
            identity.argv_sha256,
            identity.listener_port,
        )
        for role, identity in previous.items()
    }
    current["model"] = previous["worker"]

    with pytest.raises(ProofRefusal, match="replacement|identity|model"):
        assert_replacement_identities(previous, current)


def test_fresh_replacement_identities_for_all_roles_are_accepted():
    from scripts.verify_study_workbench import (
        ProcessIdentity,
        assert_replacement_identities,
    )

    previous = _handoff_children()[0]
    current = {
        role: ProcessIdentity(
            role,
            identity.pid + 100,
            identity.start_token + "-new",
            identity.argv_sha256,
            identity.listener_port,
        )
        for role, identity in previous.items()
    }

    assert_replacement_identities(previous, current) is None


def test_listener_probe_distinguishes_empty_and_probe_failures(monkeypatch):
    from scripts.verify_study_workbench import ProofRefusal, _listener_pids

    class Result:
        stdout = ""
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", lambda *a, **k: Result())
    assert _listener_pids(43121) == set()

    class LsofEmpty:
        stdout = ""
        stderr = ""
        returncode = 1

    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", lambda *a, **k: LsofEmpty())
    assert _listener_pids(43121) == set()

    for failure in (
        OSError("lsof unavailable"),
        subprocess.TimeoutExpired("lsof", 3),
    ):
        def raise_failure(*_args, _failure=failure, **_kwargs):
            raise _failure

        monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", raise_failure)
        with pytest.raises(ProofRefusal, match="listener_probe"):
            _listener_pids(43121)

    class Nonzero:
        stdout = ""
        stderr = "permission denied"
        returncode = 1

    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", lambda *a, **k: Nonzero())
    with pytest.raises(ProofRefusal, match="listener_probe"):
        _listener_pids(43121)

    class Malformed:
        stdout = "not-a-pid\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", lambda *a, **k: Malformed())
    with pytest.raises(ProofRefusal, match="listener_probe"):
        _listener_pids(43121)

    class MacOSFraming:
        stdout = "p43121\nf3\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.verify_study_workbench.subprocess.run", lambda *a, **k: MacOSFraming())
    assert _listener_pids(43121) == {43121}


def test_assistant_response_must_echo_request_invocation_id():
    from scripts.verify_study_workbench import ProofRefusal, _assistant_receipt

    response = {
        "role": "source_guide",
        "invocation_id": "different-request",
        "session_id": "study_assistant_session:source-guide",
        "response_id": "study_assistant_response:source-guide",
        "answer": "Synthetic cited explanation.",
    }
    with pytest.raises(ProofRefusal, match="invocation"):
        _assistant_receipt("source_guide", "expected-request", response)


def test_authoritative_source_evidence_uses_full_hash_and_returned_offsets():
    from scripts.verify_study_workbench import (
        ProofRefusal,
        _authoritative_source_evidence,
    )

    full_text = "header " * 80 + "Authoritative evidence target." + " trailer" * 80
    start = full_text.index("Authoritative")
    match = {
        "match": {
            "start": start,
            "end": start + len("Authoritative evidence target."),
            "score": 1.0,
            "snippet": "Authoritative evidence target.",
        }
    }
    source = {
        "id": "source:long",
        "full_text": full_text,
        "provenance": {"content_fingerprint": hashlib.sha256(full_text.encode()).hexdigest()},
    }

    evidence = _authoritative_source_evidence(source, match)

    assert evidence.content_fingerprint == hashlib.sha256(full_text.encode()).hexdigest()
    assert evidence.start == start
    assert evidence.end == start + len("Authoritative evidence target.")
    assert evidence.quote == full_text[evidence.start:evidence.end]

    with pytest.raises(ProofRefusal, match="hash_mismatch"):
        _authoritative_source_evidence(
            source | {"provenance": {"content_fingerprint": "a" * 64}}, match
        )
    with pytest.raises(ProofRefusal, match="quote_mismatch"):
        _authoritative_source_evidence(
            source,
            {
                "match": {
                    **match["match"],
                    "snippet": "a different snippet",
                }
            },
        )


def test_stack_stop_runs_exact_cleanup_assertions(monkeypatch, tmp_path: Path):
    from types import SimpleNamespace

    from scripts.verify_study_workbench import Stack

    stack = object.__new__(Stack)
    stack.children = []
    stack.inputs = SimpleNamespace(
        api_port=43121,
        frontend_port=43122,
        surreal_port=43123,
        model_port=43124,
        task_root=tmp_path,
        namespace="study_ns_abc",
        database="study_db_abc",
    )
    stack.container_id = "a" * 12
    stack.container_removed = False
    called = {}

    def fake_cleanup(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        return SimpleNamespace(owned_processes=0, ports=0, roots=0)

    monkeypatch.setattr("scripts.verify_study_workbench.cleanup_owned", fake_cleanup)
    def fake_remove_surreal():
        stack.container_removed = True
        called["removed"] = True

    monkeypatch.setattr(stack, "_remove_surreal", fake_remove_surreal)

    stack.stop()

    assert called["removed"] is True
    assert called["kwargs"]["remove_root"] is False
    assert called["args"][1] == [43121, 43122, 43123, 43124]


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
