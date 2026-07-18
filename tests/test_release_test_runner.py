"""Regression coverage for bounded desktop-release backend test execution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from desktop.build.run_backend_tests import discover_tests, run_batches


def test_discovers_only_non_integration_test_files(tmp_path):
    tests_dir = tmp_path / "tests"
    integration = tests_dir / "integration"
    integration.mkdir(parents=True)
    (tests_dir / "test_alpha.py").write_text("", encoding="utf-8")
    (tests_dir / "helper.py").write_text("", encoding="utf-8")
    (integration / "test_external.py").write_text("", encoding="utf-8")

    assert discover_tests(tests_dir) == [tests_dir / "test_alpha.py"]


def test_runs_sorted_batches_with_timeout(monkeypatch, tmp_path):
    test_files = [tmp_path / f"test_{index}.py" for index in range(3)]
    report_dir = tmp_path / "test-results"
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_batches(
        test_files,
        project_root=tmp_path,
        batch_size=2,
        timeout_seconds=45,
        junit_output_dir=report_dir,
    )

    assert [call["command"] for call in calls] == [
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_files[0]),
            str(test_files[1]),
            "-q",
            f"--junitxml={report_dir / 'backend-001-002.xml'}",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_files[2]),
            "-q",
            f"--junitxml={report_dir / 'backend-003-003.xml'}",
        ],
    ]
    assert all(call["timeout"] == 45 for call in calls)
    assert report_dir.is_dir()


def test_turns_a_timed_out_batch_into_clear_release_failure(monkeypatch, tmp_path):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pytest", timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="exceeded 10s"):
        run_batches(
            [tmp_path / "test_stuck.py"],
            project_root=tmp_path,
            batch_size=1,
            timeout_seconds=10,
            junit_output_dir=tmp_path / "test-results",
        )
