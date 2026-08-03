from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import verify_podcast_studio as verifier

_PROOF_REVISION = "a" * 40


def _write_native_playwright_report(
    report_path: Path,
    *,
    result_status: str = "passed",
    test_count: int = 5,
    revision: str | None = _PROOF_REVISION,
) -> None:
    report_path.write_text(
        json.dumps(
            {
                "config": {
                    "argv": ["playwright", "test", "e2e/podcast-intelligence-studio.spec.ts", "--project=native-runtime"],
                    "rootDir": "/synthetic/frontend/e2e",
                },
                "suites": [
                    {
                        "title": "podcast-intelligence-studio.spec.ts",
                        "file": "podcast-intelligence-studio.spec.ts",
                        "specs": [
                            {
                                "title": f"fixture case {index}",
                                "tests": [
                                    {
                                        "projectName": "native-runtime",
                                        "annotations": [] if revision is None else [{
                                            "type": "podcast_studio_runtime_revision",
                                            "description": revision,
                                        }],
                                        "results": [{"status": result_status}],
                                    }
                                ],
                            }
                            for index in range(test_count)
                        ],
                    }
                ],
                "errors": [],
                "stats": {"expected": test_count, "unexpected": 0, "skipped": 0},
            }
        ),
        encoding="utf-8",
    )


def test_health_exposes_only_a_valid_opt_in_proof_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api import main as api_main

    monkeypatch.delenv("DEEPER_NOTEBOOK_PROOF_REVISION", raising=False)
    assert "proof_revision" not in asyncio.run(api_main.health())

    monkeypatch.setenv("DEEPER_NOTEBOOK_PROOF_REVISION", _PROOF_REVISION)
    monkeypatch.setattr(api_main, "_checkout_head_revision", lambda: _PROOF_REVISION)
    assert asyncio.run(api_main.health())["proof_revision"] == _PROOF_REVISION

    monkeypatch.setattr(api_main, "_checkout_head_revision", lambda: "b" * 40)
    assert "proof_revision" not in asyncio.run(api_main.health())

    monkeypatch.setattr(api_main, "_checkout_head_revision", lambda: None)
    assert "proof_revision" not in asyncio.run(api_main.health())

    monkeypatch.setenv("DEEPER_NOTEBOOK_PROOF_REVISION", "not-a-revision")
    assert "proof_revision" not in asyncio.run(api_main.health())


def test_checkout_revision_ignores_ambient_git_routing_and_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api import main as api_main

    captured: dict[str, object] = {}

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0, f"{_PROOF_REVISION}\n", "")

    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    ):
        monkeypatch.setenv(key, "ambient-override")
    monkeypatch.setattr(api_main.subprocess, "run", fake_run)

    assert api_main._checkout_head_revision() == _PROOF_REVISION
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert all(key not in environment for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    ))
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"


def test_verifier_binds_live_health_and_every_playwright_case_to_expected_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path)
    monkeypatch.setattr(
        verifier,
        "_native_health",
        lambda _url: (True, 200, {"status": "healthy", "name": "Deeper Notebook", "proof_revision": _PROOF_REVISION}),
    )

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
        expected_revision=_PROOF_REVISION,
    )

    assert result.exit_code == 0
    assert result.report["gates"]["native_runtime"] == {  # type: ignore[index]
        "status": "passed",
        "route_status": 200,
        "proof_revision": _PROOF_REVISION,
        "reason": None,
    }
    assert result.report["gates"]["playwright_native"]["proof_revision"] == _PROOF_REVISION  # type: ignore[index]


def test_verifier_rejects_missing_or_unbound_revision_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path, revision=None)
    monkeypatch.setattr(
        verifier,
        "_native_health",
        lambda _url: (True, 200, {"status": "healthy", "name": "Deeper Notebook", "proof_revision": _PROOF_REVISION}),
    )

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
        expected_revision=_PROOF_REVISION,
    )

    assert result.exit_code == 2
    assert result.report["gates"]["playwright_native"]["status"] == "blocked"  # type: ignore[index]


def test_fixture_write_guard_rejects_create_and_delete_without_mutating_sources(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / verifier._FIXTURE_SENTINEL).write_text("synthetic fixture only\n", encoding="utf-8")
    verifier._create_fixture(fixture)
    before = verifier._hashes(fixture)

    with verifier.fixture_write_guard(fixture) as guard:
        with pytest.raises(PermissionError, match="synthetic fixture write blocked"):
            (fixture / "obsidian" / "Created.md").write_text("blocked", encoding="utf-8")
        with pytest.raises(PermissionError, match="synthetic fixture write blocked"):
            (fixture / "logseq" / "pages" / "Research.md").unlink()

    assert guard.write_attempts == 2
    assert verifier._hashes(fixture) == before


def test_fixture_write_guard_rejects_write_restore_attempt_without_mutating_sources(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / verifier._FIXTURE_SENTINEL).write_text("synthetic fixture only\n", encoding="utf-8")
    verifier._create_fixture(fixture)
    source = fixture / "obsidian" / "Plan.md"
    before = verifier._hashes(fixture)

    with verifier.fixture_write_guard(fixture) as guard:
        with pytest.raises(PermissionError, match="synthetic fixture write blocked"):
            source.write_text("temporary mutation", encoding="utf-8")
        with pytest.raises(PermissionError, match="synthetic fixture write blocked"):
            source.replace(fixture / "obsidian" / "Restored.md")

    assert guard.write_attempts == 2
    assert verifier._hashes(fixture) == before


def test_verifier_rejects_a_retry_that_leaves_owned_audio_behind(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / verifier._FIXTURE_SENTINEL).write_text("synthetic fixture only\n", encoding="utf-8")
    verifier._create_fixture(fixture)
    original_unlink = Path.unlink

    def leave_owned_audio(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "episode.mp3":
            return None
        original_unlink(path, *args, **kwargs)

    with patch.object(Path, "unlink", new=leave_owned_audio):
        with pytest.raises(RuntimeError, match="synthetic retry left owned audio behind"):
            asyncio.run(verifier._execute_read_only_flow(fixture))


def test_verifier_requires_a_complete_passing_native_playwright_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path)
    monkeypatch.setattr(
        verifier,
        "_native_health",
        lambda _url: (True, 200, {"status": "healthy", "name": "Deeper Notebook", "proof_revision": _PROOF_REVISION}),
    )

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
        expected_revision=_PROOF_REVISION,
    )

    assert result.exit_code == 0
    assert result.report["status"] == "passed"
    assert result.report["gates"]["playwright_native"] == {  # type: ignore[index]
        "status": "passed",
        "test_file": "e2e/podcast-intelligence-studio.spec.ts",
        "test_count": 5,
        "proof_revision": _PROOF_REVISION,
    }


def test_verifier_rejects_an_incomplete_or_failed_native_playwright_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path, result_status="failed", test_count=4)
    monkeypatch.setattr(
        verifier,
        "_native_health",
        lambda _url: (True, 200, {"status": "healthy", "name": "Deeper Notebook", "proof_revision": _PROOF_REVISION}),
    )

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
        expected_revision=_PROOF_REVISION,
    )

    assert result.exit_code == 2
    assert result.report["status"] == "blocked"
    assert result.report["gates"]["playwright_native"]["status"] == "blocked"  # type: ignore[index]


def test_verifier_uses_a_new_owned_synthetic_vault_pair_only(tmp_path: Path) -> None:
    result = verifier.run_verifier(
        native_url="http://127.0.0.1:9",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
    )

    assert result.exit_code == 2
    assert result.report["status"] == "blocked"
    assert result.report["synthetic_passed"] is True
    assert result.report["source_hashes_unchanged"] is True
    assert result.report["external_writes"] == 0
    assert result.report["fixture"]["kind"] == "synthetic_obsidian_logseq"  # type: ignore[index]
    assert (tmp_path / "fixture" / verifier._FIXTURE_SENTINEL).is_file()


def test_verifier_report_is_aggregate_only_and_keeps_semantic_search_locked(tmp_path: Path) -> None:
    output = tmp_path / "proof.json"
    result = verifier.run_verifier(
        native_url="http://127.0.0.1:9",
        fixture_root=tmp_path / "fixture",
        output_path=output,
    )

    checks = result.report["checks"]  # type: ignore[assignment]
    assert checks["exact_text_selection"]["status"] == "passed"  # type: ignore[index]
    assert checks["semantic_selection"]["status"] == "blocked"  # type: ignore[index]
    assert checks["read_only_flow"]["external_write_receipts"] == 0  # type: ignore[index]
    report = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in report
    assert "Plan.md" not in report
    assert "private fixture content" not in report


def test_verifier_executes_selection_submission_retry_and_audio_inspection(tmp_path: Path) -> None:
    result = verifier.run_verifier(
        native_url="http://127.0.0.1:9",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
    )

    flow = result.report["checks"]["read_only_flow"]  # type: ignore[index]
    assert "operations" not in flow
    assert flow["status"] == "passed"
    assert flow["preview"]["included_count"] == 2
    assert flow["submission"]["fake_worker_job_count"] == 2
    assert flow["retry"]["job_id"] == "command:synthetic-2"
    assert flow["metadata_audio"]["old_audio_bytes"] > 0
    assert flow["external_write_receipts"] == 0


def test_verifier_does_not_use_a_literal_operation_claim_list() -> None:
    source = Path(verifier.__file__).read_text(encoding="utf-8")

    assert '"operations"' not in source


def test_verifier_rejects_existing_user_content_and_output_inside_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "personal.md").write_text("do not touch", encoding="utf-8")

    with pytest.raises(ValueError, match="temporary synthetic fixture root required"):
        verifier.verifier_config(fixture_root=fixture, output_path=tmp_path / "proof.json")

    owned = tmp_path / "owned"
    verifier.verifier_config(fixture_root=owned, output_path=tmp_path / "proof.json")
    with pytest.raises(ValueError, match="new proof output file required"):
        verifier.verifier_config(fixture_root=owned, output_path=owned / "proof.json")


def test_cli_runs_from_the_scripts_directory_without_pythonpath() -> None:
    script = Path(verifier.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=script.parent,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ModuleNotFoundError" not in result.stderr
