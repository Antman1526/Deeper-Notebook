"""Synthetic contracts for the read-only external vault verifier."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_read_only_vault.py"

pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="controlled proof requires POSIX descriptor-relative report writes",
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_read_only_vault", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture(root: Path) -> None:
    (root / "Obsidian Brain").mkdir(parents=True)
    (root / "Logseq Brain").mkdir()
    (root / "Obsidian Brain" / "note.md").write_text("# Safe fixture\n")
    (root / "Logseq Brain" / "page.md").write_text("- Safe fixture\n")
    manifest = root / "brain-engine" / "generated" / "deepercode-connector"
    manifest.mkdir(parents=True)
    documents = [
        {
            "id": f"source-{index}",
            "evidenceClass": "source",
            "sourcePath": "private-source-path",
            "contentPath": "private-content-path",
            "title": "private-title",
            "vaultRoot": "private-vault-root",
        }
        for index in range(1, 13)
    ] + [
        {
            "id": f"synthesis-{index}",
            "evidenceClass": "synthesis",
            "derivedFrom": [f"source-{index}", f"source-{index + 1}"],
        }
        for index in range(1, 10)
    ]
    (manifest / "manifest.json").write_text(
        json.dumps({"schemaVersion": {"major": 1}, "documents": documents})
    )


def _trust_records() -> list[dict[str, object]]:
    return [
        {
            "id": f"vault_trust_record:source-{index}",
            "manifest_id": f"source-{index}",
            "evidence_class": "source",
            "derived_from": [],
        }
        for index in range(1, 13)
    ] + [
        {
            "id": f"vault_trust_record:synthesis-{index}",
            "manifest_id": f"synthesis-{index}",
            "evidence_class": "synthesis",
            "derived_from": [f"source-{index}", f"source-{index + 1}"],
        }
        for index in range(1, 10)
    ]


def _api_responses(root: Path):
    mounts = iter(
        [
            {"id": "parent", "name": "2nd Brains"},
            {"id": "obsidian", "name": "Obsidian Brain"},
            {"id": "logseq", "name": "Logseq Brain"},
        ]
    )
    return {
        ("GET", ""): [],
        ("POST", ""): lambda _: next(mounts),
        ("GET", "/parent"): _mount_detail(
            root, "parent", "2nd Brains", "mixed", None, False
        ),
        ("GET", "/obsidian"): _mount_detail(
            root / "Obsidian Brain",
            "obsidian",
            "Obsidian Brain",
            "obsidian",
            "parent",
            True,
        ),
        ("GET", "/logseq"): _mount_detail(
            root / "Logseq Brain", "logseq", "Logseq Brain", "logseq", "parent", True
        ),
        ("POST", "/parent/trust/import"): {"changed": 0, "unchanged": 21},
        ("POST", "/obsidian/scan"): {"parsed": 0, "unchanged": 12},
        ("POST", "/logseq/scan"): {"parsed": 0, "unchanged": 9},
        ("GET", "/parent/trust"): _trust_records(),
        ("GET", "/parent/trust/summary"): {"total": 21},
        ("GET", "/parent/receipts"): [{"operation": "project"}],
    }


def _mount_detail(
    root: Path,
    mount_id: str,
    name: str,
    format_mode: str,
    parent_id: str | None,
    watch_enabled: bool,
):
    return {
        "id": mount_id,
        "name": name,
        "root_path": str(root),
        "format_mode": format_mode,
        "parent_vault_id": parent_id,
        "watch_enabled": watch_enabled,
    }


def test_check_only_never_calls_api_and_exports_only_aggregate_source_inventory(
    tmp_path, monkeypatch, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    calls = []
    monkeypatch.setattr(verifier, "_request_json", lambda *args: calls.append(args))

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 0
    )

    report = json.loads(output.read_text())
    assert calls == []
    assert report["mode"] == "check-only"
    assert report["source_files_changed"] == 0
    assert "source_hashes" not in report
    assert report["source_files_observed"] > 0
    assert len(report["source_inventory_digest"]) == 64
    assert str(Path.home()) not in output.read_text()
    assert "private-source-path" not in output.read_text()
    assert "private-content-path" not in output.read_text()
    assert "private-title" not in output.read_text()
    assert "private-vault-root" not in output.read_text()
    sensitive_relative_name = "Obsidian Brain/CLIENTS/TopSecret notes.md"
    (root / sensitive_relative_name).parent.mkdir(parents=True)
    sensitive_file = root / sensitive_relative_name
    sensitive_file.write_text("sensitive fixture")
    sensitive_hash = verifier._hash_file(sensitive_file)
    output.unlink()
    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    rendered = output.read_text() + captured.out + captured.err
    assert sensitive_relative_name not in rendered
    assert sensitive_hash not in rendered
    assert output.stat().st_mode & 0o777 == 0o600


def test_manifest_counts_accept_canonical_documents_and_preserve_only_digest(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)

    counts = verifier._manifest_counts(root, verifier._capture_root_identity(root))

    assert counts["expected_trust_records"] == 21
    assert counts["expected_synthesis_records"] == 9
    assert counts["expected_synthesis_with_derived_from"] == 9
    assert set(counts) == {
        "expected_trust_records",
        "expected_synthesis_records",
        "expected_synthesis_with_derived_from",
        "expected_derived_from",
        "expected_derived_from_digest",
    }


def test_manifest_counts_supports_legacy_records_only_when_unambiguous(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    manifest = (
        root / "brain-engine" / "generated" / "deepercode-connector" / "manifest.json"
    )
    manifest.write_text(
        json.dumps({"records": [{"id": "source-1", "evidenceClass": "source"}]})
    )

    counts = verifier._manifest_counts(root, verifier._capture_root_identity(root))

    assert counts["expected_trust_records"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"documents": "not-a-list"},
        {"documents": [{"id": "source-1", "evidenceClass": "source"}], "records": []},
        {
            "documents": [
                {"id": "source-1", "evidenceClass": "source"},
                {"id": "source-1", "evidenceClass": "source"},
            ]
        },
    ],
)
def test_manifest_counts_rejects_malformed_or_ambiguous_manifest(tmp_path, payload):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    manifest = (
        root / "brain-engine" / "generated" / "deepercode-connector" / "manifest.json"
    )
    manifest.write_text(json.dumps(payload))

    with pytest.raises(verifier.VerificationError):
        verifier._manifest_counts(root, verifier._capture_root_identity(root))


@pytest.mark.parametrize("records_key", ["documents", "records"])
@pytest.mark.parametrize("evidence_class", [None, "", "   "])
def test_manifest_counts_rejects_missing_or_blank_evidence_class(
    tmp_path, records_key, evidence_class
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    record = {"id": "source-1"}
    if evidence_class is not None:
        record["evidenceClass"] = evidence_class
    manifest = (
        root / "brain-engine" / "generated" / "deepercode-connector" / "manifest.json"
    )
    manifest.write_text(json.dumps({records_key: [record]}))

    with pytest.raises(
        verifier.VerificationError, match="^connector manifest has invalid records$"
    ) as exc_info:
        verifier._manifest_counts(root, verifier._capture_root_identity(root))

    assert str(root) not in str(exc_info.value)
    assert "source-1" not in str(exc_info.value)


def test_controlled_execution_proves_two_unchanged_scans_and_trust(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    requests = []

    def request(method, api, path, payload=None):
        requests.append((method, path, payload))
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 0
    )

    report = json.loads(output.read_text())
    assert report["source_files_changed"] == 0
    assert report["git_status_changed"] is False
    assert report["second_scan_changed_projections"] == 0
    assert report["trust_records"] == 21
    assert report["synthesis_records"] == 9
    assert report["synthesis_with_derived_from"] == 9
    assert (
        "POST",
        "/parent/trust/import",
        {
            "manifest_relative_path": "brain-engine/generated/deepercode-connector/manifest.json"
        },
    ) in requests
    assert sum(path.endswith("/scan") for _, path, _ in requests) == 4
    assert ("POST", "/parent/scan", None) not in requests
    assert ("POST", "/obsidian/scan", None) in requests
    assert ("POST", "/logseq/scan", None) in requests
    assert str(root) not in output.read_text()


def test_reconciliation_mismatch_is_nonzero_and_report_stays_sanitized(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    responses[("GET", "/parent/trust/summary")] = {"total": 99}
    monkeypatch.setattr(
        verifier,
        "_request_json",
        lambda method, api, path, payload=None: (
            responses[(method, path)](payload)
            if callable(responses[(method, path)])
            else responses[(method, path)]
        ),
    )

    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    report = json.loads(output.read_text())
    assert "trust_count_mismatch" in report["failures"]
    assert str(root) not in output.read_text()


def test_git_status_lock_is_recorded_without_repairing_it(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    lock = root / ".git" / "index.lock"
    lock.write_text("pre-existing lock")

    snapshot = verifier._snapshot(root, verifier._capture_root_identity(root))
    assert snapshot.git_status == "git_status_unavailable"
    assert snapshot.git_status_available is False
    assert lock.read_text() == "pre-existing lock"
    output = tmp_path / "report.json"
    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 0
    )
    report = json.loads(output.read_text())
    assert report["git_status"] == "git_status_unavailable"
    assert report["git_status_available"] is False


def test_rejects_root_before_api_or_output(tmp_path):
    verifier = _load_verifier()
    output = tmp_path / "report.json"
    assert (
        verifier.main(
            [
                "--root",
                "/",
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert not output.exists()


def test_rejects_home_before_api_or_output(tmp_path, monkeypatch):
    verifier = _load_verifier()
    home = tmp_path / "synthetic-home"
    home.mkdir()
    output = tmp_path / "report.json"
    monkeypatch.setattr(verifier.Path, "home", classmethod(lambda cls: home))
    assert (
        verifier.main(
            [
                "--root",
                str(home),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert not output.exists()


@pytest.mark.parametrize("output_name", [".", "report.json"])
def test_rejects_output_inside_or_equal_to_source_before_check_only_write(
    tmp_path, output_name
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = root if output_name == "." else root / output_name

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert not (root / "report.json").exists()


def test_rejects_output_symlink_resolved_inside_source_before_write(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    redirect = tmp_path / "redirect"
    redirect.symlink_to(root, target_is_directory=True)
    output = redirect / "report.json"

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert not (root / "report.json").exists()


def test_non_git_inventory_excludes_git_and_all_symlinks(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    (root / ".git").mkdir()
    (root / ".git" / "private").write_text("never report")
    (root / "regular.md").write_text("regular")
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (root / "linked.md").symlink_to(outside)
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "escaped.md").write_text("outside")
    (root / "linked-dir").symlink_to(outside_dir, target_is_directory=True)
    real_run = verifier.subprocess.run
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda command, **kwargs: (
            subprocess.CompletedProcess(command, 1, b"", b"")
            if command[3:5] == ["ls-files", "--cached"]
            else real_run(command, **kwargs)
        ),
    )

    files = [path.as_posix() for path in verifier._relative_files(root)]
    assert "regular.md" in files
    assert ".git/private" not in files
    assert "linked.md" not in files
    assert "linked-dir/escaped.md" not in files


def test_git_inventory_includes_ignored_regular_files_and_detects_their_mutation(
    tmp_path,
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("ignored-private.md\n")
    ignored = root / "ignored-private.md"
    ignored.write_text("before")

    identity = verifier._capture_root_identity(root)
    before = verifier._snapshot(root, identity)
    ignored.write_text("after")
    after = verifier._snapshot(root, identity)

    assert "ignored-private.md" in before.hashes
    assert verifier._snapshot_differences(before, after)[0] is True


def test_pre_request_source_mismatch_aborts_before_first_api_call(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("ignored-private.md\n")
    ignored = root / "ignored-private.md"
    ignored.write_text("before")
    output = tmp_path / "report.json"
    calls = []
    original_snapshot = verifier._snapshot
    snapshots = 0

    def snapshot_before_first_request(path, identity):
        nonlocal snapshots
        snapshots += 1
        if snapshots == 2:
            ignored.write_text("mutated before first request")
        return original_snapshot(path, identity)

    monkeypatch.setattr(verifier, "_snapshot", snapshot_before_first_request)
    monkeypatch.setattr(verifier, "_request_json", lambda *args: calls.append(args))

    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    assert calls == []
    report = json.loads(output.read_text())
    assert "source_hash_mismatch" in report["failures"]
    assert str(root) not in output.read_text()


@pytest.mark.parametrize("kind", ["missing", "file", "home_symlink"])
def test_rejects_malformed_roots_without_path_disclosure(
    tmp_path, monkeypatch, capsys, kind
):
    verifier = _load_verifier()
    home = tmp_path / "synthetic-home"
    home.mkdir()
    root = tmp_path / "candidate"
    if kind == "file":
        root.write_text("not a directory")
    elif kind == "home_symlink":
        root.symlink_to(home, target_is_directory=True)
    monkeypatch.setattr(verifier.Path, "home", classmethod(lambda cls: home))
    output = tmp_path / "report.json"

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert str(root) not in capsys.readouterr().err
    assert not output.exists()


def test_scan_stops_on_first_source_or_git_mutation_and_reports_mismatch(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    requests = []

    def request(method, api, path, payload=None):
        requests.append((method, path))
        if path == "/obsidian/scan":
            (root / "Obsidian Brain" / "note.md").write_text("mutated")
            return {"parsed": 0}
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    report = json.loads(output.read_text())
    assert "source_hash_mismatch" in report["failures"]
    assert report["git_status_changed"] is False
    assert ("POST", "/logseq/scan") not in requests
    assert ("POST", "/parent/scan") not in requests
    assert str(root) not in output.read_text()


def test_scan_stops_on_first_git_status_mutation_and_leaves_lock_untouched(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    requests = []
    lock = root / ".git" / "index.lock"

    def request(method, api, path, payload=None):
        requests.append((method, path))
        if path == "/obsidian/scan":
            lock.write_text("external writer lock")
            return {"parsed": 0}
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    report = json.loads(output.read_text())
    assert report["source_files_changed"] == 0
    assert report["git_status_changed"] is True
    assert report["git_status"] == "git_status_unavailable"
    assert report["git_status_available"] is False
    assert "git_status_mismatch" in report["failures"]
    assert ("POST", "/logseq/scan") not in requests
    assert ("POST", "/parent/scan") not in requests
    assert lock.read_text() == "external writer lock"


def test_trust_derived_from_arrays_must_match_manifest_by_record_id(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    responses[("GET", "/parent/trust")][12]["derived_from"] = [
        "different-but-not-empty"
    ]
    monkeypatch.setattr(
        verifier,
        "_request_json",
        lambda method, api, path, payload=None: (
            responses[(method, path)](payload)
            if callable(responses[(method, path)])
            else responses[(method, path)]
        ),
    )

    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    assert "derived_from_mismatch" in json.loads(output.read_text())["failures"]


def test_conflicting_existing_mount_is_rejected_before_scan_or_trust_import(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    calls = []

    def request(method, api, path, payload=None):
        calls.append((method, path))
        if (method, path) == ("GET", ""):
            return [{"id": "unrelated", "name": "2nd Brains"}]
        if (method, path) == ("GET", "/unrelated"):
            return _mount_detail(
                root / "wrong", "unrelated", "2nd Brains", "mixed", None, False
            )
        raise AssertionError(f"unexpected API request: {method} {path}")

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 2
    )
    assert calls == [("GET", ""), ("GET", "/unrelated")]
    report = json.loads(output.read_text())
    assert report["failures"] == ["verification_operation_failed"]
    assert str(root) not in output.read_text()


def test_existing_mount_is_reused_only_after_exact_detail_validation(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    existing = {
        "parent": _mount_detail(root, "parent", "2nd Brains", "mixed", None, False),
        "obsidian": _mount_detail(
            root / "Obsidian Brain",
            "obsidian",
            "Obsidian Brain",
            "obsidian",
            "parent",
            True,
        ),
        "logseq": _mount_detail(
            root / "Logseq Brain", "logseq", "Logseq Brain", "logseq", "parent", True
        ),
    }
    requests = []

    def request(method, api, path, payload=None):
        requests.append((method, path))
        if (method, path) == ("GET", ""):
            return [{"id": key, "name": item["name"]} for key, item in existing.items()]
        if method == "GET" and path[1:] in existing:
            return existing[path[1:]]
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 0
    )
    assert not any(method == "POST" and path == "" for method, path in requests)


def test_api_url_construction_and_errors_do_not_disclose_payload_or_paths(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    seen = []
    secret_path = tmp_path / "private source.md"

    def fail(request, timeout):
        seen.append(request.full_url)
        raise URLError(f"failed for {secret_path} with source content")

    monkeypatch.setattr(verifier, "urlopen", fail)
    with pytest.raises(verifier.VerificationError) as exc:
        verifier._request_json(
            "POST", "http://api/base/", "/mount/scan", {"path": str(secret_path)}
        )
    assert seen == ["http://api/base/vaults/mount/scan"]
    assert str(secret_path) not in str(exc.value)


def test_existing_output_hard_link_to_source_is_rejected_without_truncating_source(
    tmp_path, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    source = root / "Obsidian Brain" / "note.md"
    original = source.read_text()
    output = tmp_path / "report.json"
    os.link(source, output)

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    assert source.read_text() == original
    assert output.read_text() == original
    assert str(root) not in capsys.readouterr().err


def test_failed_scan_after_mutation_still_snapshots_and_writes_sanitized_report(
    tmp_path, monkeypatch, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses(root)

    def request(method, api, path, payload=None):
        if path == "/obsidian/scan":
            (root / "Obsidian Brain" / "note.md").write_text("mutated before timeout")
            raise verifier.VerificationError(f"secret path {root}")
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 2
    )
    report = json.loads(output.read_text())
    assert "source_hash_mismatch" in report["failures"]
    assert "scan_request_failed" in report["failures"]
    assert str(root) not in output.read_text()
    assert str(root) not in capsys.readouterr().err


def test_malformed_mount_list_and_new_mount_detail_fail_closed_before_import(
    tmp_path, monkeypatch
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    calls = []

    def malformed_list(method, api, path, payload=None):
        calls.append((method, path))
        return {"not": "a list"}

    monkeypatch.setattr(verifier, "_request_json", malformed_list)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 2
    )
    assert calls == [("GET", "")]

    output.unlink()
    calls.clear()

    def malformed_new_detail(method, api, path, payload=None):
        calls.append((method, path))
        if (method, path) == ("GET", ""):
            return []
        if (method, path) == ("POST", ""):
            return {"id": "parent"}
        if (method, path) == ("GET", "/parent"):
            return {"id": "parent", "name": "wrong"}
        raise AssertionError("trust import or scan must not happen")

    monkeypatch.setattr(verifier, "_request_json", malformed_new_detail)
    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 2
    )
    assert calls == [("GET", ""), ("POST", ""), ("GET", "/parent")]


def test_snapshot_failures_are_sanitized_and_do_not_traceback(
    tmp_path, monkeypatch, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"

    def bad_hash(path):
        raise PermissionError(f"cannot read {path}")

    monkeypatch.setattr(verifier, "_hash_file", bad_hash)
    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "Traceback" not in error
    assert str(root) not in error
    assert not output.exists()


def test_output_parent_swap_to_source_is_rejected_before_any_source_write(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    target = verifier._safe_output(str(report_dir / "report.json"), root)
    moved = tmp_path / "reports-moved"
    report_dir.rename(moved)
    report_dir.symlink_to(root, target_is_directory=True)

    with pytest.raises(verifier.VerificationError):
        verifier._write_report(
            target, verifier._capture_root_identity(root), {"failures": []}
        )
    assert not (root / "report.json").exists()


def test_root_rebind_during_api_request_fails_closed_without_report_in_rebound_root(
    tmp_path, monkeypatch, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "outside" / "report.json"
    output.parent.mkdir()
    moved_root = tmp_path / "original-root"
    responses = _api_responses(root)

    def request(method, api, path, payload=None):
        if (method, path) == ("GET", ""):
            root.rename(moved_root)
            root.symlink_to(output.parent, target_is_directory=True)
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)

    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 2
    )
    assert not output.exists()
    assert not (root / "report.json").exists()
    assert str(root) not in capsys.readouterr().err


def test_unchanged_root_identity_allows_check_only_report(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"

    assert (
        verifier.main(
            [
                "--root",
                str(root),
                "--api",
                "http://api",
                "--output",
                str(output),
                "--check-only",
            ]
        )
        == 0
    )
    assert output.exists()


def test_local_http_server_exercises_requests_mount_details_scan_failure_and_sanitization(
    tmp_path, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    records = []
    ids = {
        "2nd Brains": "parent",
        "Obsidian Brain": "obsidian",
        "Logseq Brain": "logseq",
    }
    details = {
        "parent": _mount_detail(root, "parent", "2nd Brains", "mixed", None, False),
        "obsidian": _mount_detail(
            root / "Obsidian Brain",
            "obsidian",
            "Obsidian Brain",
            "obsidian",
            "parent",
            True,
        ),
        "logseq": _mount_detail(
            root / "Logseq Brain", "logseq", "Logseq Brain", "logseq", "parent", True
        ),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, status, payload):
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            records.append(("GET", self.path, None))
            if self.path == "/api/deeper-notebook/vaults":
                return self._reply(200, [])
            return self._reply(200, details[self.path.rsplit("/", 1)[-1]])

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body or b"{}")
            records.append(("POST", self.path, payload))
            if self.path == "/api/deeper-notebook/vaults":
                return self._reply(200, {"id": ids[payload["name"]]})
            if self.path.endswith("/obsidian/scan"):
                (root / "Logseq Brain" / "page.md").write_text("mutated by server")
                return self._reply(500, {"private": str(root)})
            return self._reply(200, {"parsed": 0})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = f"http://127.0.0.1:{server.server_port}/api/deeper-notebook"
        assert (
            verifier.main(["--root", str(root), "--api", api, "--output", str(output)])
            == 2
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    report = json.loads(output.read_text())
    assert "source_hash_mismatch" in report["failures"]
    assert "scan_request_failed" in report["failures"]
    assert str(root) not in output.read_text()
    assert str(root) not in capsys.readouterr().err
    assert all(path.startswith("/api/deeper-notebook/vaults") for _, path, _ in records)
    assert any(
        payload and payload.get("path") == str(root)
        for method, _, payload in records
        if method == "POST"
    )


def test_local_http_server_exercises_successful_canonical_scan_flow(tmp_path):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    ids = {
        "2nd Brains": "parent",
        "Obsidian Brain": "obsidian",
        "Logseq Brain": "logseq",
    }
    details = {
        "parent": _mount_detail(root, "parent", "2nd Brains", "mixed", None, False),
        "obsidian": _mount_detail(
            root / "Obsidian Brain",
            "obsidian",
            "Obsidian Brain",
            "obsidian",
            "parent",
            True,
        ),
        "logseq": _mount_detail(
            root / "Logseq Brain", "logseq", "Logseq Brain", "logseq", "parent", True
        ),
    }
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, payload):
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            paths.append(self.path)
            if self.path == "/api/deeper-notebook/vaults":
                return self._reply([])
            if self.path.endswith("/trust"):
                return self._reply(_trust_records())
            if self.path.endswith("/trust/summary"):
                return self._reply({"total": 21})
            if self.path.endswith("/receipts"):
                return self._reply([])
            return self._reply(details[self.path.rsplit("/", 1)[-1]])

        def do_POST(self):
            paths.append(self.path)
            payload = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}"
            )
            if self.path == "/api/deeper-notebook/vaults":
                return self._reply({"id": ids[payload["name"]]})
            if self.path.endswith("/trust/import"):
                return self._reply({"changed": 0})
            return self._reply({"parsed": 0})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = f"http://127.0.0.1:{server.server_port}/api/deeper-notebook"
        assert (
            verifier.main(["--root", str(root), "--api", api, "--output", str(output)])
            == 0
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    report = json.loads(output.read_text())
    assert report["failures"] == []
    assert report["trust_records"] == 21
    assert all(path.startswith("/api/deeper-notebook/vaults") for path in paths)


@pytest.mark.parametrize(
    "mutation_point", ["mount", "trust", "summary", "malformed_scan"]
)
def test_http_api_operations_reconcile_source_mutations_before_failure(
    tmp_path, mutation_point
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / f"{mutation_point}.json"
    ids = {
        "2nd Brains": "parent",
        "Obsidian Brain": "obsidian",
        "Logseq Brain": "logseq",
    }
    details = {
        "parent": _mount_detail(root, "parent", "2nd Brains", "mixed", None, False),
        "obsidian": _mount_detail(
            root / "Obsidian Brain",
            "obsidian",
            "Obsidian Brain",
            "obsidian",
            "parent",
            True,
        ),
        "logseq": _mount_detail(
            root / "Logseq Brain", "logseq", "Logseq Brain", "logseq", "parent", True
        ),
    }

    def mutate():
        (root / "Obsidian Brain" / "note.md").write_text(f"mutated at {mutation_point}")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, payload):
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == "/api/deeper-notebook/vaults":
                return self._reply([])
            if self.path.endswith("/trust"):
                return self._reply(_trust_records())
            if self.path.endswith("/trust/summary"):
                if mutation_point == "summary":
                    mutate()
                return self._reply({"total": 21})
            if self.path.endswith("/receipts"):
                return self._reply([])
            return self._reply(details[self.path.rsplit("/", 1)[-1]])

        def do_POST(self):
            payload = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}"
            )
            if self.path == "/api/deeper-notebook/vaults":
                if mutation_point == "mount":
                    mutate()
                return self._reply({"id": ids[payload["name"]]})
            if self.path.endswith("/trust/import"):
                if mutation_point == "trust":
                    mutate()
                return self._reply({"changed": 0})
            if (
                self.path.endswith("/obsidian/scan")
                and mutation_point == "malformed_scan"
            ):
                mutate()
                return self._reply({"parsed": "not-an-int"})
            return self._reply({"parsed": 0})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = f"http://127.0.0.1:{server.server_port}/api/deeper-notebook"
        assert (
            verifier.main(["--root", str(root), "--api", api, "--output", str(output)])
            != 0
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    report = json.loads(output.read_text())
    assert report["source_files_changed"] == 1
    assert "source_hash_mismatch" in report["failures"]
    assert report["failures"] != []


def test_derived_from_values_are_never_disclosed_in_report_or_errors(
    tmp_path, monkeypatch, capsys
):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    secret = "/private/absolute/path/SECRET-derivation-token"
    manifest = (
        root / "brain-engine" / "generated" / "deepercode-connector" / "manifest.json"
    )
    payload = json.loads(manifest.read_text())
    payload["documents"][12]["derivedFrom"] = [secret]
    manifest.write_text(json.dumps(payload))
    output = tmp_path / "report.json"
    responses = _api_responses(root)
    responses[("GET", "/parent/trust")][1]["derived_from"] = ["different"]
    monkeypatch.setattr(
        verifier,
        "_request_json",
        lambda method, api, path, payload=None: (
            responses[(method, path)](payload)
            if callable(responses[(method, path)])
            else responses[(method, path)]
        ),
    )

    assert (
        verifier.main(
            ["--root", str(root), "--api", "http://api", "--output", str(output)]
        )
        == 1
    )
    captured = capsys.readouterr()
    rendered = output.read_text() + captured.out + captured.err
    assert secret not in rendered
    assert '"expected_derived_from":' not in rendered
    assert "derived_from_mismatch" in json.loads(output.read_text())["failures"]
