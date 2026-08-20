"""Contract for the locked, opt-in SkillOpt integration-test path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "desktop" / "build" / "run_skillopt_integration.py"


def _load_runner():
    assert RUNNER_PATH.is_file(), f"missing SkillOpt integration runner: {RUNNER_PATH}"
    spec = importlib.util.spec_from_file_location(
        "run_skillopt_integration",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skillopt_ci_runner_uses_exact_desktop_lock_and_19_test_contract():
    runner = _load_runner()

    assert (
        runner.locked_skillopt_requirement(ROOT / "desktop/requirements.lock")
        == "skillopt==0.1.0"
    )
    assert runner.expected_test_count() == 19


def test_desktop_ci_explicitly_runs_locked_skillopt_integration_when_installed():
    install_command = 'python -m pip install "skillopt==0.1.0"'
    command = "python desktop/build/run_skillopt_integration.py --require-installed"
    desktop_workflow = (ROOT / ".github/workflows/build-desktop.yml").read_text(
        encoding="utf-8"
    )
    windows_workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(
        encoding="utf-8"
    )

    assert desktop_workflow.count(install_command) == 3
    assert desktop_workflow.count(command) == 3
    assert install_command in windows_workflow
    assert command in windows_workflow
