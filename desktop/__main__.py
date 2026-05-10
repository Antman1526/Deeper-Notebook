# desktop/__main__.py
"""`python -m desktop` — boots config → wizard if needed → supervisor → window.

When frozen by PyInstaller, `sys.executable` IS the bundled `Open Notebook Plus`
binary — not a Python interpreter. Spawning `[sys.executable, "-m", "uvicorn", …]`
re-runs the entire app and recurses. We avoid that with an internal dispatcher
that re-enters the bundled Python with a different code path when the binary is
invoked with our private `--onp-internal-*` flags.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path


def _dispatch_internal_subcommand() -> int | None:
    """If invoked as a subprocess child, dispatch to the right entry point.

    Returns an exit code (int) when handled and the caller should sys.exit().
    Returns None when this is a normal app launch.
    """
    if len(sys.argv) < 2:
        return None
    cmd = sys.argv[1]

    if cmd == "--onp-internal-uvicorn":
        # Args: --onp-internal-uvicorn <APP> --host H --port P
        # Re-shape sys.argv so uvicorn.main() parses correctly:
        #   sys.argv = ["uvicorn", "<APP>", "--host", "H", "--port", "P"]
        import uvicorn
        sys.argv = ["uvicorn"] + sys.argv[2:]
        uvicorn.main()
        return 0  # uvicorn.main() doesn't return on graceful shutdown

    if cmd == "--onp-internal-worker":
        # Args: --onp-internal-worker --import-modules <MODULE>
        from surreal_commands.cli.worker import main as worker_main
        sys.argv = ["surreal-commands-worker"] + sys.argv[2:]
        worker_main()
        return 0

    return None


# Run the dispatcher BEFORE importing anything else heavy — child subprocesses
# don't need Supervisor / PyWebView / the wizard.
_rc = _dispatch_internal_subcommand()
if _rc is not None:
    sys.exit(_rc)


# Normal app-launch path:
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

    # Until the app stably runs end-to-end, keep child stdout/stderr
    # captured to ~/.open-notebook-plus/logs/ so post-mortem is possible.
    # Disable once we trust the supervisor.
    sv = Supervisor(cfg=cfg, repo_root=repo_root(), bin_dir=bin_dir,
                    surreal_arch=arch, node_arch=arch, extra_env=extra_env,
                    debug_mode=True)
    try:
        sv.start_all()
    except Exception as e:
        # If a child probe times out, sv.frontend_url is empty and the
        # window won't open. Surface what we have and bail cleanly.
        import traceback
        from pathlib import Path as _P
        log_dir = _P.home() / ".open-notebook-plus" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "launcher.log").write_text(
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
