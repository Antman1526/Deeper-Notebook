# desktop/__main__.py
"""`python -m desktop` — boots config → wizard if needed → bootstrap → supervisor → window.

On first launch (after the wizard), bootstrap.ensure_venv() uses the bundled
uv binary and python-build-standalone interpreter to create
~/.open-notebook-plus/venv and install upstream deps (~30-60s). Subsequent
launches skip bootstrapping when requirements.lock hasn't changed.

The supervisor spawns FastAPI/worker/llama-cpp using the venv's Python
interpreter rather than the frozen launcher binary, so no internal dispatcher
tricks are needed.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path


def host_arch() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys.platform == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"unsupported platform {sys.platform}/{machine}")


def repo_root() -> Path:
    # When frozen by PyInstaller, sys._MEIPASS holds the bundle resource dir.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def upstream_dir() -> Path:
    """Location of bundled upstream source (api/, open_notebook/, commands/)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "upstream"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def _bundled_python_tarball(arch: str) -> Path:
    """Path to the python-build-standalone tarball shipped in the bundle."""
    if getattr(sys, "frozen", False):
        bin_dir = Path(sys._MEIPASS) / "desktop" / "bin"  # type: ignore[attr-defined]
    else:
        bin_dir = repo_root() / "desktop" / "bin"
    if sys.platform == "win32":
        return bin_dir / f"python-{arch}.zip"
    return bin_dir / f"python-{arch}.tar.gz"


def _bundled_uv(arch: str) -> Path:
    """Path to the bundled uv binary."""
    if getattr(sys, "frozen", False):
        bin_dir = Path(sys._MEIPASS) / "desktop" / "bin"  # type: ignore[attr-defined]
    else:
        bin_dir = repo_root() / "desktop" / "bin"
    if sys.platform == "win32":
        return bin_dir / "uv.exe"
    return bin_dir / "uv"


def _lock_path() -> Path:
    """Path to the pinned requirements.lock shipped with the bundle."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "desktop" / "requirements.lock"  # type: ignore[attr-defined]
    return repo_root() / "desktop" / "requirements.lock"


def main() -> int:
    from desktop.config import default_config_path, load_or_create
    from desktop.launcher import Supervisor
    from desktop.providers.llamacpp import LlamaCppProvider
    from desktop.providers.ollama import OllamaProvider
    from desktop.window import open_window

    cfg_path = default_config_path()
    first_run = not cfg_path.exists()

    if first_run:
        from desktop.first_run.server import run_wizard_blocking
        run_wizard_blocking(cfg_path)

    cfg = load_or_create(cfg_path)
    arch = host_arch()
    bin_dir = repo_root() / "desktop" / "bin"

    # Bootstrap: ensure ~/.open-notebook-plus/venv is provisioned with upstream
    # deps. Progress messages go to the bootstrap log file.
    from desktop import bootstrap

    log_dir = (
        __import__("pathlib").Path.home() / ".open-notebook-plus" / "logs"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_log = log_dir / "bootstrap.log"

    def _bootstrap_progress(msg: str) -> None:
        with bootstrap_log.open("a") as f:
            f.write(msg + "\n")

    standalone_python = bootstrap.extract_python_runtime(
        tarball=_bundled_python_tarball(arch),
        dest_parent=__import__("pathlib").Path.home() / ".open-notebook-plus",
    )

    venv_py = bootstrap.ensure_venv(
        standalone_python=standalone_python,
        uv_binary=_bundled_uv(arch),
        lock_path=_lock_path(),
        upstream_dir=upstream_dir(),
        progress=_bootstrap_progress,
    )

    extra_env: dict[str, str] = {}
    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")
    elif cfg.provider == "llamacpp":
        lc = LlamaCppProvider(model_dir=cfg.model_dir, python_executable=venv_py)
        if cfg.default_model:
            extra_env = lc.start(cfg.default_model)

    sv = Supervisor(
        cfg=cfg,
        repo_root=repo_root(),
        bin_dir=bin_dir,
        surreal_arch=arch,
        node_arch=arch,
        extra_env=extra_env,
        debug_mode=True,
        venv_python=venv_py,
    )
    try:
        sv.start_all()
    except Exception:
        import traceback
        from pathlib import Path as _P
        _log_dir = _P.home() / ".open-notebook-plus" / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        (_log_dir / "launcher.log").write_text(
            f"Supervisor.start_all() failed:\n{traceback.format_exc()}\n"
        )
        sv.stop_all()
        raise

    try:
        open_window(sv.frontend_url, on_close=sv.stop_all, theme=cfg.theme)
    finally:
        sv.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
