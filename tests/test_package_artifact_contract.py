"""Built-artifact contracts for canonical and legacy Python packages."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = ROOT / "desktop" / "build" / "package_layout.py"
VERIFIER_PATH = ROOT / "desktop" / "build" / "verify_package_contents.py"


def _load_module(path: Path, name: str):
    assert path.is_file(), f"missing package contract module: {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_built_wheel_contains_canonical_runtime_data_and_exact_legacy_shim(
    tmp_path: Path,
) -> None:
    verifier = _load_module(VERIFIER_PATH, "verify_package_contents")
    wheel_dir = tmp_path / "wheel"
    result = subprocess.run(
        [*_WHEEL_BUILD_COMMAND, "--wheel-dir", str(wheel_dir), "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(wheel_dir.glob("deeper_notebook-*.whl"))
    manifest = verifier.inspect_wheel(wheel)
    assert manifest["legacy_shim"] == [
        "open_notebook/__init__.py",
        "open_notebook/_alias.py",
    ]
    assert {
        "deeper_notebook/domain/notebook.py",
        "deeper_notebook/database/migrations/1.surrealql",
        "deeper_notebook/prompt_optimizer/skillopt_base.yaml",
        "deeper_notebook/prompt_optimizer/skillopt_prompts/README.md",
        "deeper_notebook/ai/assets/test_speech.mp3",
    } <= set(manifest["canonical_runtime"])


def test_actual_frozen_source_stage_contains_both_package_trees(
    tmp_path: Path,
) -> None:
    layout = _load_module(LAYOUT_PATH, "package_layout")
    verifier = _load_module(VERIFIER_PATH, "verify_package_contents")
    frozen_root = layout.stage_upstream_packages(
        project_root=ROOT,
        stage_root=tmp_path / "frozen-stage",
    )

    manifest = verifier.inspect_frozen_root(frozen_root)
    assert manifest["package_roots"] == [
        "upstream/deeper_notebook",
        "upstream/open_notebook",
    ]
    assert manifest["legacy_shim"] == [
        "upstream/open_notebook/__init__.py",
        "upstream/open_notebook/_alias.py",
    ]
    assert (
        frozen_root / "upstream/deeper_notebook/database/migrations/1.surrealql"
    ).is_file()


def test_standalone_frontend_root_handles_workspace_relative_build_output(
    tmp_path: Path,
) -> None:
    layout = _load_module(LAYOUT_PATH, "package_layout")
    standalone = tmp_path / "standalone"
    frontend = standalone / ".worktrees" / "branch" / "frontend"
    (frontend / ".next").mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "server.js").write_text("// app", encoding="utf-8")
    (standalone / "unrelated" / "server.js").parent.mkdir(parents=True)
    (standalone / "unrelated" / "server.js").write_text("// ignored", encoding="utf-8")

    assert layout.standalone_frontend_root(standalone) == frontend


def test_ci_inspects_the_actual_pyinstaller_output() -> None:
    workflow = (ROOT / ".github/workflows/build-desktop.yml").read_text(
        encoding="utf-8"
    )
    windows_workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(
        encoding="utf-8"
    )
    verification_command = (
        "python desktop/build/verify_package_contents.py --frozen-root "
        '"dist/Deeper Notebook"'
    )

    assert workflow.count(verification_command) == 3
    assert verification_command in windows_workflow


_WHEEL_BUILD_COMMAND = (sys.executable, "-m", "pip", "wheel", "--no-deps")
