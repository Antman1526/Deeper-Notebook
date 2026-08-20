"""Canonical and legacy Python import compatibility."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from desktop.build.package_layout import pyinstaller_upstream_package_datas

ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODULES = (
    (ROOT / "tests" / "fixtures" / "legacy_import_modules.txt")
    .read_text(encoding="utf-8")
    .splitlines()
)


def _install_optional_skillopt_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the import-alias test independent of the optional SkillOpt wheel."""
    if importlib.util.find_spec("skillopt") is not None:
        return

    packages = (
        "skillopt",
        "skillopt.datasets",
        "skillopt.envs",
        "skillopt.gradient",
    )
    for name in packages:
        module = ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, module)

    datasets_base = ModuleType("skillopt.datasets.base")
    datasets_base.BaseDataLoader = type("BaseDataLoader", (), {})
    monkeypatch.setitem(sys.modules, datasets_base.__name__, datasets_base)

    envs_base = ModuleType("skillopt.envs.base")
    envs_base.EnvAdapter = type("EnvAdapter", (), {})
    monkeypatch.setitem(sys.modules, envs_base.__name__, envs_base)

    reflect = ModuleType("skillopt.gradient.reflect")
    reflect.run_minibatch_reflect = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, reflect.__name__, reflect)

    model = ModuleType("skillopt.model")
    model.chat_optimizer = lambda **_kwargs: ("", {})
    model.chat_target = lambda **_kwargs: ("", {})
    monkeypatch.setitem(sys.modules, model.__name__, model)

    types_module = ModuleType("skillopt.types")
    types_module.BatchSpec = SimpleNamespace
    monkeypatch.setitem(sys.modules, types_module.__name__, types_module)


def test_canonical_import_is_primary():
    canonical = importlib.import_module("deeper_notebook.domain.notebook").Note
    legacy = importlib.import_module("open_notebook.domain.notebook").Note

    assert legacy is canonical


def test_legacy_config_module_is_same_object():
    canonical = importlib.import_module("deeper_notebook.config")
    legacy = importlib.import_module("open_notebook.config")

    assert legacy is canonical


@pytest.mark.parametrize("legacy_name", LEGACY_MODULES)
def test_every_pre_move_legacy_import_resolves_to_canonical_object(
    legacy_name,
    monkeypatch,
):
    canonical_name = legacy_name.replace("open_notebook", "deeper_notebook", 1)
    if canonical_name == "deeper_notebook.prompt_optimizer.adapter":
        _install_optional_skillopt_stubs(monkeypatch)

    assert importlib.import_module(legacy_name) is importlib.import_module(
        canonical_name
    )


def test_legacy_exception_name_is_an_alias_of_the_canonical_base():
    from deeper_notebook.exceptions import (
        DeeperNotebookError,
        OpenNotebookError,
    )

    assert OpenNotebookError is DeeperNotebookError


def test_legacy_first_import_resolves_to_canonical_module_object():
    script = """
import importlib
legacy = importlib.import_module("open_notebook.video.contracts")
canonical = importlib.import_module("deeper_notebook.video.contracts")
raise SystemExit(0 if legacy is canonical else 1)
"""

    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""


def test_installed_distribution_metadata_stays_canonical():
    metadata = importlib.metadata.metadata("deeper-notebook")

    assert metadata["Name"] == "deeper-notebook"
    assert metadata["Version"] == "1.8.5"


def test_distribution_packages_canonical_runtime_data():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["deeper_notebook"]

    assert {
        "ai/assets/*.mp3",
        "database/migrations/*.surrealql",
        "prompt_optimizer/*.yaml",
        "prompt_optimizer/skillopt_prompts/*.md",
    } <= set(package_data)


def test_fixture_preserves_all_pre_move_first_level_modules():
    assert {
        "open_notebook.ai",
        "open_notebook.analysis",
        "open_notebook.capture",
        "open_notebook.config",
        "open_notebook.database",
        "open_notebook.digest",
        "open_notebook.domain",
        "open_notebook.evaluation",
        "open_notebook.exceptions",
        "open_notebook.feature_flags",
        "open_notebook.graphs",
        "open_notebook.health",
        "open_notebook.local_models",
        "open_notebook.logging",
        "open_notebook.mcp",
        "open_notebook.podcasts",
        "open_notebook.prompt_optimizer",
        "open_notebook.research",
        "open_notebook.security",
        "open_notebook.studio",
        "open_notebook.study",
        "open_notebook.tools",
        "open_notebook.utils",
        "open_notebook.video",
    } <= set(LEGACY_MODULES)


def test_pyinstaller_packages_canonical_and_legacy_packages():
    datas = pyinstaller_upstream_package_datas(ROOT)

    assert datas == [
        (str(ROOT / "deeper_notebook"), "upstream/deeper_notebook"),
        (str(ROOT / "open_notebook"), "upstream/open_notebook"),
    ]
