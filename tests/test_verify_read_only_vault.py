"""Synthetic contracts for the read-only external vault verifier."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_read_only_vault.py"


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
    (manifest / "manifest.json").write_text(
        json.dumps(
            {
                "records": [
                    {"id": "source-1", "evidenceClass": "source"},
                    {
                        "id": "synthesis-1",
                        "evidenceClass": "synthesis",
                        "derivedFrom": ["source-1"],
                    },
                ]
            }
        )
    )


def _api_responses():
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
        ("POST", "/parent/trust/import"): {"changed": 0, "unchanged": 2},
        ("POST", "/parent/scan"): {"parsed": 0, "unchanged": 2},
        ("POST", "/obsidian/scan"): {"parsed": 0, "unchanged": 1},
        ("POST", "/logseq/scan"): {"parsed": 0, "unchanged": 1},
        ("GET", "/parent/trust"): [
            {"id": "source-1", "evidence_class": "source", "derived_from": []},
            {
                "id": "synthesis-1",
                "evidence_class": "synthesis",
                "derived_from": ["source-1"],
            },
        ],
        ("GET", "/parent/trust/summary"): {"total": 2},
        ("GET", "/parent/receipts"): [{"operation": "project"}],
    }


def test_check_only_never_calls_api_and_reports_relative_paths(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    calls = []
    monkeypatch.setattr(verifier, "_request_json", lambda *args: calls.append(args))

    assert verifier.main(["--root", str(root), "--api", "http://api", "--output", str(output), "--check-only"]) == 0

    report = json.loads(output.read_text())
    assert calls == []
    assert report["mode"] == "check-only"
    assert report["source_files_changed"] == 0
    assert all(not Path(path).is_absolute() for path in report["source_hashes"])
    assert str(Path.home()) not in output.read_text()


def test_controlled_execution_proves_two_unchanged_scans_and_trust(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses()
    requests = []

    def request(method, api, path, payload=None):
        requests.append((method, path, payload))
        result = responses[(method, path)]
        return result(payload) if callable(result) else result

    monkeypatch.setattr(verifier, "_request_json", request)
    assert verifier.main(["--root", str(root), "--api", "http://api", "--output", str(output)]) == 0

    report = json.loads(output.read_text())
    assert report["source_files_changed"] == 0
    assert report["git_status_changed"] is False
    assert report["second_scan_changed_projections"] == 0
    assert report["trust_records"] == 2
    assert report["synthesis_records"] == 1
    assert report["synthesis_with_derived_from"] == 1
    assert ("POST", "/parent/trust/import", {"manifest_relative_path": "brain-engine/generated/deepercode-connector/manifest.json"}) in requests
    assert sum(path.endswith("/scan") for _, path, _ in requests) == 6
    assert str(root) not in output.read_text()


def test_reconciliation_mismatch_is_nonzero_and_report_stays_sanitized(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    output = tmp_path / "report.json"
    responses = _api_responses()
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

    assert verifier.main(["--root", str(root), "--api", "http://api", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert "trust_count_mismatch" in report["failures"]
    assert str(root) not in output.read_text()


def test_git_status_lock_is_recorded_without_repairing_it(tmp_path, monkeypatch):
    verifier = _load_verifier()
    root = tmp_path / "fixture"
    _fixture(root)
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 128, "", "index.lock"),
    )

    snapshot = verifier._snapshot(root)
    assert snapshot.git_status == "git_status_unavailable"
    assert snapshot.git_status_available is False


def test_rejects_root_before_api_or_output(tmp_path):
    verifier = _load_verifier()
    output = tmp_path / "report.json"
    assert verifier.main(["--root", "/", "--api", "http://api", "--output", str(output), "--check-only"]) == 2
    assert not output.exists()


def test_rejects_home_before_api_or_output(tmp_path, monkeypatch):
    verifier = _load_verifier()
    home = tmp_path / "synthetic-home"
    home.mkdir()
    output = tmp_path / "report.json"
    monkeypatch.setattr(verifier.Path, "home", classmethod(lambda cls: home))
    assert verifier.main(["--root", str(home), "--api", "http://api", "--output", str(output), "--check-only"]) == 2
    assert not output.exists()
