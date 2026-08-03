from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_podcast_studio as verifier


def _write_native_playwright_report(
    report_path: Path, *, result_status: str = "passed", test_count: int = 5
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


def test_verifier_requires_a_complete_passing_native_playwright_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path)
    monkeypatch.setattr(verifier, "_native_health", lambda _url: (True, 200))

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
    )

    assert result.exit_code == 0
    assert result.report["status"] == "passed"
    assert result.report["gates"]["playwright_native"] == {  # type: ignore[index]
        "status": "passed",
        "test_file": "e2e/podcast-intelligence-studio.spec.ts",
        "test_count": 5,
    }


def test_verifier_rejects_an_incomplete_or_failed_native_playwright_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "playwright.json"
    _write_native_playwright_report(report_path, result_status="failed", test_count=4)
    monkeypatch.setattr(verifier, "_native_health", lambda _url: (True, 200))

    result = verifier.run_verifier(
        native_url="http://127.0.0.1:65060",
        fixture_root=tmp_path / "fixture",
        output_path=tmp_path / "proof.json",
        playwright_report_path=report_path,
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
