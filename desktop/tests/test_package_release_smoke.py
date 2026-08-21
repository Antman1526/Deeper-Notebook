"""Contract tests for the serial release package smoke runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.build import package_release_smoke as release_smoke
from desktop.build import package_smoke as smoke
from desktop.build import package_smoke_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def arguments_for(tmp_path: Path) -> argparse.Namespace:
    artifact = tmp_path / "release.dmg"
    artifact.write_bytes(b"release artifact")
    executable = tmp_path / "Deeper Notebook"
    executable.write_bytes(b"executable fixture")
    playwright_module = tmp_path / "playwright"
    playwright_module.mkdir()
    return argparse.Namespace(
        executable=executable,
        artifact=artifact,
        output_root=tmp_path / "smoke-output",
        uv_cache_dir=tmp_path / "uv-cache",
        playwright_module=playwright_module,
        expected_artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        timeout_seconds=5.0,
    )


def test_release_smoke_runs_default_then_off_without_overlap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    def fake_run_mode(
        mode: str, *_args: object, **_kwargs: object
    ) -> dict[str, object]:
        events.append(mode)
        return {"status": "passed", "mode": mode}

    monkeypatch.setattr(release_smoke, "run_mode", fake_run_mode)

    assert release_smoke.run_release_smoke(arguments_for(tmp_path)) == 0
    assert events == ["default", "source-visuals-off"]
    assert (
        json.loads(
            (tmp_path / "smoke-output" / "summary.json").read_text(encoding="utf-8")
        )["status"]
        == "passed"
    )


def test_release_smoke_stops_default_before_launching_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    current_mode = ["unknown"]
    events: list[str] = []

    def fake_prepare(root, *, source_visuals, uv_cache_dir):
        current_mode[0] = "default" if source_visuals else "source-visuals-off"
        return package_smoke_fixture.SmokeFixture(
            root=root,
            home=root / "home",
            data_dir=root / "data",
            model_dir=root / "models",
            readiness_file=root / "data" / "logs" / "desktop-readiness.json",
            environment={"MODE": current_mode[0]},
        )

    process = SimpleNamespace(pid=900, returncode=None)
    monkeypatch.setattr(release_smoke, "prepare_smoke_fixture", fake_prepare)
    monkeypatch.setattr(
        release_smoke,
        "launch_monitored_process",
        lambda *_args, **_kwargs: (
            events.append(f"{current_mode[0]}:launch") or (process, 900)
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "wait_for_readiness",
        lambda *_args, **_kwargs: ("http://127.0.0.1:53001", "http://127.0.0.1:53002/"),
    )
    monkeypatch.setattr(
        release_smoke.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout='{"status":"passed"}', stderr=""
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "stop_process",
        lambda *_args, **_kwargs: events.append(f"{current_mode[0]}:stop"),
    )

    assert release_smoke.run_release_smoke(arguments) == 0
    assert events == [
        "default:launch",
        "default:stop",
        "source-visuals-off:launch",
        "source-visuals-off:stop",
    ]


def test_release_smoke_does_not_start_off_after_default_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    def fail_default(mode: str, *_args: object, **_kwargs: object) -> dict[str, object]:
        events.append(mode)
        raise smoke.SmokeFailure("default failed")

    monkeypatch.setattr(release_smoke, "run_mode", fail_default)

    assert release_smoke.run_release_smoke(arguments_for(tmp_path)) == 1
    assert events == ["default"]
    summary = json.loads(
        (tmp_path / "smoke-output" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "failed"
    assert summary["failed_mode"] == "default"


def test_release_smoke_refuses_non_empty_output_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    arguments.output_root.mkdir()
    sentinel = arguments.output_root / "preserve.txt"
    sentinel.write_text("keep", encoding="utf-8")
    started: list[str] = []
    monkeypatch.setattr(
        release_smoke,
        "run_mode",
        lambda mode, *_args, **_kwargs: started.append(mode),
    )

    assert release_smoke.run_release_smoke(arguments) == 1
    assert started == []
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_release_smoke_verifies_artifact_before_any_mode_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    arguments.expected_artifact_sha256 = "0" * 64
    started: list[str] = []
    monkeypatch.setattr(
        release_smoke,
        "run_mode",
        lambda mode, *_args, **_kwargs: started.append(mode),
    )

    assert release_smoke.run_release_smoke(arguments) == 1
    assert started == []
    summary = json.loads(
        (arguments.output_root / "summary.json").read_text(encoding="utf-8")
    )
    assert "sha256 mismatch" in summary["error"]


def test_run_mode_uses_all_feature_expectations_and_cleans_up_on_browser_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "0")
    fixture_root = tmp_path / "fixture"
    fixture = package_smoke_fixture.SmokeFixture(
        root=fixture_root,
        home=fixture_root / "home",
        data_dir=fixture_root / "data",
        model_dir=fixture_root / "models",
        readiness_file=fixture_root / "data" / "logs" / "desktop-readiness.json",
        environment={
            "HOME": str(fixture_root / "home"),
            "DEEPER_NOTEBOOK_DATA_DIR": str(fixture_root / "data"),
            "UV_CACHE_DIR": str(arguments.uv_cache_dir),
            "UV_OFFLINE": "1",
            "OPENCHRONICLE_MCP_URL": "http://[::1]:1/mcp",
        },
    )
    process = SimpleNamespace(pid=901, returncode=None)
    launched: list[tuple[list[str], dict[str, str]]] = []
    stopped: list[object] = []

    monkeypatch.setattr(
        release_smoke, "prepare_smoke_fixture", lambda *_a, **_k: fixture
    )

    def fake_launch(command, environment, _timeout):
        launched.append((command, environment))
        return process, process.pid

    monkeypatch.setattr(release_smoke, "launch_monitored_process", fake_launch)
    monkeypatch.setattr(
        release_smoke,
        "wait_for_readiness",
        lambda *_a, **_k: ("http://127.0.0.1:52001", "http://127.0.0.1:52002/"),
    )
    monkeypatch.setattr(
        release_smoke.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["node"], returncode=1, stdout="", stderr="browser failed"
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "stop_process",
        lambda process_arg, _timeout: stopped.append(process_arg),
    )

    result = release_smoke.run_mode("default", arguments)

    assert result["status"] == "failed"
    assert stopped == [process]
    assert launched[0][0] == [str(arguments.executable)]
    assert release_smoke.DEFAULT_EXPECTED_FEATURES == {
        "evidenceStudio": True,
        "modelFleet": True,
        "researchRuns": True,
        "sourceVisuals": True,
        "studyWorkbench": True,
        "visualRefresh": True,
    }
    assert "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED" not in launched[0][1]
    receipt = json.loads(
        (arguments.output_root / "default.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "failed"


def test_run_mode_cleans_up_after_child_readiness_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    fixture_root = tmp_path / "fixture-child-failure"
    fixture = package_smoke_fixture.SmokeFixture(
        root=fixture_root,
        home=fixture_root / "home",
        data_dir=fixture_root / "data",
        model_dir=fixture_root / "models",
        readiness_file=fixture_root / "data" / "logs" / "desktop-readiness.json",
        environment={"HOME": str(fixture_root / "home")},
    )
    process = SimpleNamespace(pid=903, returncode=None)
    stopped: list[object] = []
    monkeypatch.setattr(
        release_smoke, "prepare_smoke_fixture", lambda *_a, **_k: fixture
    )
    monkeypatch.setattr(
        release_smoke,
        "launch_monitored_process",
        lambda *_args, **_kwargs: (process, process.pid),
    )
    monkeypatch.setattr(
        release_smoke,
        "wait_for_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            smoke.SmokeFailure("child exited before readiness")
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "stop_process",
        lambda process_arg, _timeout: stopped.append(process_arg),
    )

    result = release_smoke.run_mode("default", arguments)

    assert result["status"] == "failed"
    assert stopped == [process]
    receipt = json.loads(
        (arguments.output_root / "default.json").read_text(encoding="utf-8")
    )
    assert receipt["checks"]["clean_shutdown"] == {"passed": True}


def test_run_mode_off_changes_only_source_visuals_and_parses_stdout_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = arguments_for(tmp_path)
    fixture_root = tmp_path / "fixture-off"
    fixture = package_smoke_fixture.SmokeFixture(
        root=fixture_root,
        home=fixture_root / "home",
        data_dir=fixture_root / "data",
        model_dir=fixture_root / "models",
        readiness_file=fixture_root / "data" / "logs" / "desktop-readiness.json",
        environment={
            "HOME": str(fixture_root / "home"),
            "DEEPER_NOTEBOOK_DATA_DIR": str(fixture_root / "data"),
            "UV_CACHE_DIR": str(arguments.uv_cache_dir),
            "UV_OFFLINE": "1",
            "OPENCHRONICLE_MCP_URL": "http://[::1]:1/mcp",
            "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED": "0",
        },
    )
    process = SimpleNamespace(pid=902, returncode=None)
    launched: list[dict[str, str]] = []
    commands: list[list[str]] = []
    stopped: list[object] = []
    browser_receipt = {"status": "passed", "mode": "off"}

    monkeypatch.setattr(
        release_smoke, "prepare_smoke_fixture", lambda *_a, **_k: fixture
    )
    monkeypatch.setattr(
        release_smoke,
        "launch_monitored_process",
        lambda command, environment, _timeout: (
            commands.append(command)
            or launched.append(environment)
            or (process, process.pid)
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "wait_for_readiness",
        lambda *_a, **_k: ("http://127.0.0.1:52003", "http://127.0.0.1:52004/"),
    )
    monkeypatch.setattr(
        release_smoke.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["node"],
            returncode=0,
            stdout=json.dumps(browser_receipt),
            stderr="ignored",
        ),
    )
    monkeypatch.setattr(
        release_smoke,
        "stop_process",
        lambda process_arg, _timeout: stopped.append(process_arg),
    )

    result = release_smoke.run_mode("source-visuals-off", arguments)

    assert result["status"] == "passed"
    assert stopped == [process]
    assert commands == [[str(arguments.executable)]]
    assert launched[0]["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED"] == "0"
    assert launched[0]["HOME"] == fixture.environment["HOME"]
    assert (
        launched[0]["DEEPER_NOTEBOOK_DATA_DIR"]
        == fixture.environment["DEEPER_NOTEBOOK_DATA_DIR"]
    )
    browser_command = result["browser_command"]
    assert browser_command[browser_command.index("--mode") + 1] == "off"
    assert result["browser"] == browser_receipt
