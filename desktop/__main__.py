# desktop/__main__.py
"""`python -m desktop` — boots config → wizard if needed → supervisor → window."""
from __future__ import annotations

import platform
import sys
from pathlib import Path

from desktop.config import default_config_path, load_or_create
from desktop.launcher import Supervisor
from desktop.providers.llamacpp import LlamaCppProvider
from desktop.providers.ollama import OllamaProvider
from desktop.window import open_window


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


def main() -> int:
    cfg_path = default_config_path()
    first_run = not cfg_path.exists()

    if first_run:
        from desktop.first_run.server import run_wizard_blocking
        run_wizard_blocking(cfg_path)

    cfg = load_or_create(cfg_path)
    arch = host_arch()
    bin_dir = repo_root() / "desktop" / "bin"

    extra_env: dict[str, str] = {}
    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")
    elif cfg.provider == "llamacpp":
        lc = LlamaCppProvider(model_dir=cfg.model_dir)
        if cfg.default_model:
            extra_env = lc.start(cfg.default_model)

    sv = Supervisor(cfg=cfg, repo_root=repo_root(), bin_dir=bin_dir,
                    surreal_arch=arch, node_arch=arch, extra_env=extra_env)
    sv.start_all()
    try:
        open_window(sv.frontend_url, on_close=sv.stop_all, theme=cfg.theme)
    finally:
        sv.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
