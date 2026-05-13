"""Top-level application orchestration for Open Notebook Plus desktop launcher.

Exposes a single public entry point:

    from desktop.app import run
    sys.exit(run())

The boot sequence is broken into named phases, each operating on an AppContext
dataclass that carries state forward without 50 nested local variables.

Phase order
-----------
1. _phase_load_config      — locate & load config.toml; set up log dir + progress bus
2. _phase_wizard_if_first_run — run the first-run wizard on first launch
3. _phase_bootstrap_runtime   — provision the venv (bootstrap.ensure_venv)
4. _phase_download_models     — auto-download embedding + voice models
5. _phase_select_provider     — start Ollama or llama.cpp server; populate extra_env
6. _phase_start_supervisor    — build & start the Supervisor process tree
7. _phase_auto_register       — register discovered models with the upstream API
8. _phase_start_model_manager — start the aiohttp model-manager window server
9. _phase_install_tray        — set up the system tray icon + menu
10. _phase_open_window        — open the PyWebView main window (blocks until closed)
"""
from __future__ import annotations

import dataclasses
import logging
import platform
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.config import Config
    from desktop.launcher import Supervisor
    from desktop.progress import ProgressBus

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers (private, replicated from __main__.py)
# ---------------------------------------------------------------------------


def host_arch() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys.platform == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"unsupported platform {sys.platform}/{machine}")


def repo_root() -> Path:
    """Absolute path to the repository root (or PyInstaller bundle root)."""
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


# ---------------------------------------------------------------------------
# AppContext — shared state across phases
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AppContext:
    """Mutable state bag threaded through each boot phase."""

    cfg: "Config | None" = None
    arch: str = ""
    bin_dir: "Path | None" = None
    progress_bus: "ProgressBus | None" = None
    log_dir: "Path | None" = None
    venv_py: "Path | None" = None
    extra_env: dict[str, str] = dataclasses.field(default_factory=dict)
    sv: "Supervisor | None" = None
    mm_port: int = 0
    # v0.4 memory additions
    openchronicle_available: bool = False
    commands_dst: "Path | None" = None
    memory_dashboard_port: int = 0


def _new_context() -> AppContext:
    return AppContext()


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------


def _phase_load_config(ctx: AppContext) -> None:
    """Locate config.toml; set up log dir, progress bus, and first-run flag."""
    from desktop.config import default_config_path, load_or_create
    from desktop.progress import ProgressBus

    cfg_path = default_config_path()
    ctx._first_run = not cfg_path.exists()
    ctx._cfg_path = cfg_path

    log_dir = Path.home() / ".open-notebook-plus" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ctx.log_dir = log_dir

    progress_bus = ProgressBus(log_path=log_dir / "progress.jsonl")
    progress_bus.publish("startup", "running", "Launcher starting…")
    ctx.progress_bus = progress_bus

    # Config is loaded after the wizard (if first run); stash the path.
    ctx._load_or_create = load_or_create


def _phase_wizard_if_first_run(ctx: AppContext) -> None:
    """Run the first-run wizard if no config.toml exists yet."""
    if not ctx._first_run:  # type: ignore[attr-defined]
        # Load config immediately if wizard is not needed.
        ctx.cfg = ctx._load_or_create(ctx._cfg_path)  # type: ignore[attr-defined]
        return

    from desktop.first_run.server import run_wizard_blocking
    run_wizard_blocking(ctx._cfg_path, progress_bus=ctx.progress_bus)  # type: ignore[attr-defined]
    ctx.cfg = ctx._load_or_create(ctx._cfg_path)  # type: ignore[attr-defined]


def _phase_bootstrap_runtime(ctx: AppContext) -> None:
    """Provision the venv; set ctx.arch, ctx.bin_dir, ctx.venv_py."""
    from desktop import bootstrap

    assert ctx.cfg is not None
    assert ctx.log_dir is not None

    arch = host_arch()
    ctx.arch = arch
    ctx.bin_dir = repo_root() / "desktop" / "bin"

    bootstrap_log = ctx.log_dir / "bootstrap.log"

    def _bootstrap_progress(msg: str) -> None:
        with bootstrap_log.open("a") as f:
            f.write(msg + "\n")

    ctx._bootstrap_progress = _bootstrap_progress  # type: ignore[attr-defined]

    standalone_python = bootstrap.extract_python_runtime(
        tarball=_bundled_python_tarball(arch),
        dest_parent=Path.home() / ".open-notebook-plus",
    )

    ctx.venv_py = bootstrap.ensure_venv(
        standalone_python=standalone_python,
        uv_binary=_bundled_uv(arch),
        lock_path=_lock_path(),
        upstream_dir=upstream_dir(),
        progress=_bootstrap_progress,
    )


def _phase_download_models(ctx: AppContext) -> None:
    """Auto-download embedding + voice models. Non-fatal on failure."""
    import logging as _logging

    assert ctx.cfg is not None
    assert ctx.log_dir is not None

    _dl_log_path = ctx.log_dir / "downloads.log"
    _dl_handler = _logging.FileHandler(_dl_log_path)
    _dl_handler.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logging.getLogger("desktop.model_downloads").addHandler(_dl_handler)

    _bp = ctx._bootstrap_progress  # type: ignore[attr-defined]

    try:
        from desktop.model_downloads import (
            ensure_embedding_model, ensure_tts_model,
            ensure_secondary_tts_voice, ensure_stt_model,
        )
        model_dir = Path(ctx.cfg.model_dir)
        ensure_embedding_model(model_dir, progress=_bp)
        ensure_tts_model(model_dir, progress=_bp)
        ensure_secondary_tts_voice(model_dir, progress=_bp)
        ensure_stt_model(model_dir, progress=_bp)
    except Exception:
        _bp("Warning: voice model downloads failed: " + traceback.format_exc())


def _phase_select_provider(ctx: AppContext) -> None:
    """Start Ollama or llama.cpp server; populate ctx.extra_env."""
    from desktop.providers.llamacpp import LlamaCppProvider
    from desktop.providers.ollama import OllamaProvider

    assert ctx.cfg is not None
    assert ctx.log_dir is not None

    extra_env: dict[str, str] = {}
    cfg = ctx.cfg

    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")

    elif cfg.provider == "llamacpp":
        lc = LlamaCppProvider(model_dir=cfg.model_dir, python_executable=ctx.venv_py)
        chosen_model = cfg.default_model or lc.pick_default_model()
        if chosen_model:
            try:
                extra_env = lc.start(chosen_model)
            except Exception:
                _log_dir = ctx.log_dir
                (_log_dir / "llamacpp.log").write_text(
                    f"Failed to auto-start llama.cpp for {chosen_model!r}:\n"
                    f"{traceback.format_exc()}\n"
                )

    ctx.extra_env = extra_env


def _phase_detect_openchronicle(ctx: AppContext) -> None:
    """Probe the OpenChronicle MCP daemon. Best-effort — a missing daemon is
    the normal state for users who chose 'skip' in the wizard. MUST NEVER
    raise; OpenChronicle is purely optional.

    Two-stage check (P1-HIGH-04 audit fix):
      1. TCP connect — fast (~10 ms) reject for nothing-listening.
      2. JSON-RPC `initialize` POST — confirms whatever's listening actually
         speaks MCP, not a random dev server on the same port.

    Port + URL come from OPENCHRONICLE_MCP_URL env var if set, else default
    (P1-MED-10). The bridge shim reads the same env var.
    """
    import os
    import urllib.parse

    ctx.openchronicle_available = False
    mcp_url = (
        os.environ.get("OPENCHRONICLE_MCP_URL")
        or "http://127.0.0.1:8742/mcp"
    )
    try:
        parsed = urllib.parse.urlparse(mcp_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8742
    except Exception:
        host, port = "127.0.0.1", 8742

    # Stage 1 — quick TCP connect to filter "not running"
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect((host, port))
    except (OSError, socket.timeout):
        # No listener → normal "not installed" state, exit silently.
        if ctx.progress_bus is not None:
            try:
                ctx.progress_bus.publish(
                    "openchronicle.detect", "done", "available=False",
                )
            except Exception:
                pass
        return
    except BaseException as e:
        if ctx.log_dir is not None:
            try:
                ctx.log_dir.mkdir(parents=True, exist_ok=True)
                (ctx.log_dir / "openchronicle_detect.log").write_text(
                    f"tcp connect failed (non-fatal): {type(e).__name__}: {e}\n"
                )
            except Exception:
                pass
        return

    # Stage 2 — speak MCP. A genuine MCP server replies to `initialize` with
    # protocolVersion + serverInfo. Anything else (404, plain HTML, random
    # dev server) gets rejected. Short timeout so we don't block startup.
    try:
        import httpx
        r = httpx.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "open-notebook-plus", "version": "0.5"},
                },
            },
            headers={
                "Content-Type": "application/json",
                # MCP streamable-http requires this Accept header
                "Accept": "application/json, text/event-stream",
            },
            timeout=1.5,
        )
        # Streamable-http returns 200 (with SSE stream) or accepts and returns
        # JSON-RPC. Both indicate a real MCP server. 404/405/non-JSON = nope.
        if 200 <= r.status_code < 300:
            ctx.openchronicle_available = True
    except BaseException as e:
        if ctx.log_dir is not None:
            try:
                ctx.log_dir.mkdir(parents=True, exist_ok=True)
                (ctx.log_dir / "openchronicle_detect.log").write_text(
                    f"mcp handshake failed (non-fatal): {type(e).__name__}: {e}\n"
                )
            except Exception:
                pass

    if ctx.progress_bus is not None:
        try:
            ctx.progress_bus.publish(
                "openchronicle.detect", "done",
                f"available={ctx.openchronicle_available}",
            )
        except Exception:
            pass


def _phase_register_memory_commands(ctx: AppContext) -> None:
    """Copy commands/memory_commands.py into the bundled upstream's commands/
    directory so the surreal-commands worker discovers our new handlers on
    startup. No-op if the template hasn't been packaged (graceful)."""
    import shutil
    assert ctx.bin_dir is not None
    commands_dst = upstream_dir() / "commands"
    commands_dst.mkdir(parents=True, exist_ok=True)
    # Locate the template via the desktop.memory package.
    import desktop.memory as mem_pkg
    src = Path(mem_pkg.__file__).parent / "memory_commands.py"
    if src.exists():
        shutil.copyfile(src, commands_dst / "memory_commands.py")
    ctx.commands_dst = commands_dst
    if ctx.progress_bus is not None:
        ctx.progress_bus.publish(
            "memory.commands_registered", "done",
            str(commands_dst / "memory_commands.py"),
        )


def _phase_start_supervisor(ctx: AppContext) -> None:
    """Build and start the Supervisor process tree."""
    from desktop.launcher import Supervisor

    assert ctx.cfg is not None
    assert ctx.log_dir is not None
    assert ctx.bin_dir is not None

    cfg = ctx.cfg
    voice_model_dir = Path(cfg.model_dir)

    # faster-whisper uses model-name strings ("base.en"), not .bin file paths.
    whisper_model_name = Path("base.en")  # Path so Supervisor type is satisfied
    amy_path = voice_model_dir / "TTS" / "en_US-amy-medium.onnx"
    ryan_path = voice_model_dir / "TTS" / "en_US-ryan-high.onnx"
    nomic_path = voice_model_dir / "GGUF" / "nomic-embed-text-v1.5.f16.gguf"
    # v0.4: discover the chat LLM (Hermes 3) for mem0's memory writer.
    # We just pick the first Hermes-3*.gguf in the GGUF dir; users who chose
    # a different model in the wizard still get fact-extraction as long as a
    # Hermes-style GGUF is present.
    gguf_dir = voice_model_dir / "GGUF"
    chat_candidates = sorted(gguf_dir.glob("Hermes-3*.gguf")) if gguf_dir.exists() else []
    chat_llm_path = chat_candidates[0] if chat_candidates else None
    piper_voices: dict[str, Path] = {}
    if amy_path.exists():
        piper_voices["alex"] = amy_path
    if ryan_path.exists():
        piper_voices["sam"] = ryan_path

    sv = Supervisor(
        cfg=cfg, repo_root=repo_root(), bin_dir=ctx.bin_dir,
        surreal_arch=ctx.arch, node_arch=ctx.arch,
        extra_env=ctx.extra_env, debug_mode=True,
        venv_python=ctx.venv_py, upstream_root=upstream_dir(),
        whisper_model_path=whisper_model_name,
        piper_voices=piper_voices,
        nomic_embed_path=nomic_path if nomic_path.exists() else None,
        chat_llm_path=chat_llm_path,
        openchronicle_available=ctx.openchronicle_available,
        progress=ctx.progress_bus,
    )
    try:
        sv.start_all()
    except Exception:
        (_ctx_log := ctx.log_dir / "launcher.log").write_text(  # type: ignore[assignment]
            f"Supervisor.start_all() failed:\n{traceback.format_exc()}\n"
        )
        sv.stop_all()
        raise

    ctx.sv = sv


def _phase_auto_register(ctx: AppContext) -> None:
    """Register discovered models with the upstream API. Non-fatal."""
    assert ctx.cfg is not None
    assert ctx.sv is not None
    assert ctx.log_dir is not None

    try:
        from desktop.auto_register import auto_register
        import urllib.parse

        cfg = ctx.cfg
        sv = ctx.sv

        api_base = sv.session_env["INTERNAL_API_URL"]
        llamacpp_port = None
        if cfg.provider == "llamacpp" and cfg.default_model:
            url = ctx.extra_env.get("OPENAI_COMPATIBLE_BASE_URL", "")
            if url:
                llamacpp_port = urllib.parse.urlparse(url).port

        auto_register(
            api_base_url=api_base, cfg=cfg, llamacpp_port=llamacpp_port,
            whisper_port=getattr(sv, "whisper_port", None) or None,
            piper_port=getattr(sv, "piper_port", None) or None,
            embed_port=getattr(sv, "embed_port", None) or None,
            memory_port=getattr(sv, "memory_port", None) or None,
        )
    except Exception:
        (ctx.log_dir / "auto_register.log").write_text(traceback.format_exc())


def _phase_start_model_manager(ctx: AppContext) -> None:
    """Start the aiohttp model-manager window server; set ctx.mm_port."""
    assert ctx.cfg is not None

    from desktop.aiohttp_window import start_aiohttp_server_thread
    from desktop.model_manager.server import build_app as _mm_build_app

    model_dir = Path(ctx.cfg.model_dir)
    mm_port, _mm_thread, _mm_loop, _mm_runner = start_aiohttp_server_thread(
        lambda: _mm_build_app(model_dir)
    )
    ctx.mm_port = mm_port


def _phase_start_memory_dashboard(ctx: AppContext) -> None:
    """Start the aiohttp memory-dashboard window server; set ctx.memory_dashboard_port.

    The dashboard proxies to the Supervisor's memory retriever shim. If the
    retriever didn't start (sv.memory_port == 0), the dashboard still serves
    but every proxy request will return 502 — the UI displays an error state.
    """
    assert ctx.sv is not None

    from desktop.aiohttp_window import start_aiohttp_server_thread
    from desktop.memory_dashboard.server import build_app as _md_build_app

    memory_url = (f"http://127.0.0.1:{ctx.sv.memory_port}/"
                  if getattr(ctx.sv, "memory_port", 0) else "")
    # ONP v0.5 — wire the OpenChronicle bridge URL through so the dashboard
    # can power the Capture Inbox. Empty string when the bridge isn't running.
    oc_url = (f"http://127.0.0.1:{ctx.sv.openchronicle_port}/"
              if getattr(ctx.sv, "openchronicle_port", 0) else "")
    port, _t, _l, _r = start_aiohttp_server_thread(
        lambda: _md_build_app(
            memory_retriever_url=memory_url,
            openchronicle_bridge_url=oc_url,
        )
    )
    ctx.memory_dashboard_port = port


def _phase_install_tray(ctx: AppContext) -> None:
    """Install the system tray icon with Open Main / Model Manager / Memory / Quit actions."""
    import webview as _webview

    from desktop.tray import install_tray

    assert ctx.sv is not None

    sv = ctx.sv
    mm_port = ctx.mm_port
    md_port = ctx.memory_dashboard_port

    def _on_open_main() -> None:
        try:
            _webview.windows[0].show()
        except Exception:
            pass

    def _on_open_manager() -> None:
        try:
            _webview.create_window(
                "Models",
                f"http://127.0.0.1:{mm_port}/",
                width=920, height=640,
            )
        except Exception:
            pass

    def _on_open_memory() -> None:
        if not md_port:
            return
        try:
            _webview.create_window(
                "Memory",
                f"http://127.0.0.1:{md_port}/",
                width=900, height=640,
            )
        except Exception:
            pass

    def _on_quit() -> None:
        try:
            sv.stop_all()
        finally:
            try:
                _webview.windows[0].destroy()
            except Exception:
                pass

    install_tray(
        on_open_main=_on_open_main,
        on_open_manager=_on_open_manager,
        on_open_memory=_on_open_memory if md_port else None,
        on_quit=_on_quit,
    )


def _phase_open_window(ctx: AppContext) -> None:
    """Open the main PyWebView window. Blocks until the window is closed."""
    from desktop.window import open_window

    assert ctx.sv is not None
    assert ctx.cfg is not None
    assert ctx.progress_bus is not None

    ctx.progress_bus.publish("ready", "done", "Main window opening…")

    memory_url = (f"http://127.0.0.1:{ctx.memory_dashboard_port}/"
                  if ctx.memory_dashboard_port else None)
    remind = (not ctx.openchronicle_available
              and ctx.cfg.openchronicle_choice == "prompt")
    try:
        open_window(ctx.sv.frontend_url, on_close=ctx.sv.stop_all,
                    theme=ctx.cfg.theme,
                    memory_url=memory_url, remind_openchronicle=remind)
    finally:
        ctx.sv.stop_all()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run() -> int:
    """Top-level entry point — calls the phased orchestrators in order."""
    ctx = _new_context()
    _phase_load_config(ctx)
    _phase_wizard_if_first_run(ctx)
    _phase_bootstrap_runtime(ctx)
    _phase_download_models(ctx)
    _phase_select_provider(ctx)
    _phase_detect_openchronicle(ctx)
    _phase_register_memory_commands(ctx)
    _phase_start_supervisor(ctx)
    _phase_auto_register(ctx)
    _phase_start_model_manager(ctx)
    _phase_start_memory_dashboard(ctx)
    _phase_install_tray(ctx)
    _phase_open_window(ctx)
    return 0
