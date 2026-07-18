"""Contracts for dependencies installed by a fresh packaged desktop runtime."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from desktop.bootstrap import _verify_critical_imports

ROOT = Path(__file__).resolve().parents[2]


def _locked_version(package: str) -> str:
    match = re.search(
        rf"^{re.escape(package)}==([^\s]+)$",
        (ROOT / "desktop" / "requirements.lock").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match, f"{package} must be present in desktop/requirements.lock"
    return match.group(1)


def test_office_export_dependencies_are_direct_and_locked() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desktop = (ROOT / "desktop" / "requirements.txt").read_text(encoding="utf-8")

    assert '"python-docx>=1.2.0,<2.0"' in project
    assert '"openpyxl>=3.1.5,<4.0"' in project
    assert "python-docx>=1.2.0,<2.0" in desktop
    assert "openpyxl>=3.1.5,<4.0" in desktop
    assert _locked_version("python-docx") == "1.2.0"
    assert _locked_version("openpyxl") == "3.1.5"


def test_locked_office_dependencies_import_in_the_runtime_environment() -> None:
    # This uses the same one-shot import mechanism first launch uses after it
    # installs desktop/requirements.lock into its isolated virtual environment.
    missing = _verify_critical_imports(
        Path(importlib.import_module("sys").executable), ["docx", "openpyxl"]
    )

    assert missing == []


def test_capture_watcher_dependency_is_direct_locked_and_importable() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desktop = (ROOT / "desktop" / "requirements.txt").read_text(encoding="utf-8")

    assert '"watchdog>=6.0.0,<7.0"' in project
    assert "watchdog>=6.0.0,<7.0" in desktop
    assert _locked_version("watchdog").startswith("6.")
    assert (
        _verify_critical_imports(
            Path(importlib.import_module("sys").executable), ["watchdog"]
        )
        == []
    )


def test_study_scheduler_dependency_is_direct_locked_and_importable() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desktop = (ROOT / "desktop" / "requirements.txt").read_text(encoding="utf-8")

    assert '"fsrs>=6.3.1,<7.0"' in project
    assert "fsrs>=6.3.1,<7.0" in desktop
    assert _locked_version("fsrs").startswith("6.")
    assert (
        _verify_critical_imports(
            Path(importlib.import_module("sys").executable), ["fsrs"]
        )
        == []
    )


def test_ffmpeg_runtime_dependency_is_direct_locked_and_importable() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    desktop = (ROOT / "desktop" / "requirements.txt").read_text(encoding="utf-8")

    assert '"imageio-ffmpeg>=0.6.0,<1.0"' in project
    assert "imageio-ffmpeg>=0.6.0,<1.0" in desktop
    assert _locked_version("imageio-ffmpeg").startswith("0.6.")
    assert (
        _verify_critical_imports(
            Path(importlib.import_module("sys").executable), ["imageio_ffmpeg"]
        )
        == []
    )
