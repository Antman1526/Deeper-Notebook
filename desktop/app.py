"""Top-level application orchestration for the Deeper Notebook desktop launcher.

Exposes a single public entry point:

    from desktop.app import run
    sys.exit(run())

The boot sequence is broken into named phases, each operating on an AppContext
dataclass that carries state forward without 50 nested local variables.

Phase order
-----------
1. _phase_detect_data_root_recovery — stop on divergent canonical/legacy roots
2. _phase_load_config      — locate & load config.toml; set up log dir + progress bus
3. _phase_wizard_if_first_run — run the first-run wizard on first launch
4. _phase_bootstrap_runtime   — provision the venv (bootstrap.ensure_venv)
5. _phase_download_models     — auto-download embedding + voice models
6. _phase_select_provider     — start Ollama or llama.cpp server; populate extra_env
7. _phase_start_supervisor    — build & start the Supervisor process tree
8. _phase_auto_register       — register discovered models with the upstream API
9. _phase_start_model_manager — start the aiohttp model-manager window server
10. _phase_install_tray       — set up the system tray icon + menu
11. _phase_open_window        — open the PyWebView main window (blocks until closed)
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import platform
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from deeper_notebook.environment import resolve_env
from desktop.data_root import (
    active_data_root,
    resolve_data_root,
    write_conflict_recovery_evidence,
)

if TYPE_CHECKING:
    from desktop.app_migration import AppRecoveryController
    from desktop.config import Config
    from desktop.data_root import DataRootDecision
    from desktop.launcher import Supervisor
    from desktop.progress import ProgressBus
    from desktop.providers import ModelProvider
    from desktop.startup_receipts import StartupReceiptStore

log = logging.getLogger(__name__)


def _scan_chat_llm_with_timeout(gguf_dir):
    """v0.8.67f — time-bound the chat-GGUF directory scan so a stalling model
    folder can't hang the whole app launch.

    `pick_chat_llm_file` runs `os.scandir(gguf_dir)` on the boot's main thread.
    If that directory stalls — an iCloud-evicted / TCC-gated path, a sleeping
    external drive — the underlying `open()` can block UNINTERRUPTIBLY and hang
    the ENTIRE launch (the exact boot wedge seen when models lived on the iCloud
    Desktop: `sample` showed the main thread stuck in scandir → open$NOCANCEL).
    Run the scan in a daemon thread and give up after DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT
    seconds: the app boots (local chat degraded, with a clear warning) instead of
    hanging forever. A wedged scan thread leaks, but it's a daemon so it never
    blocks process exit."""
    import threading

    from desktop.auto_register.assigner import pick_chat_llm_file
    try:
        timeout = float(resolve_env("DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT", "20") or 20)
    except ValueError:
        timeout = 20.0
    if timeout <= 0:
        timeout = 20.0
    result = [None]

    def _run():
        try:
            result[0] = pick_chat_llm_file(gguf_dir)
        except Exception as exc:  # never let the scan thread take down the boot
            log.warning("chat-GGUF scan raised: %s", exc)

    t = threading.Thread(target=_run, name="chat-gguf-scan", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log.error(
            "chat-GGUF scan of %s timed out after %ss (stalled filesystem?) — "
            "starting WITHOUT a local chat model. Move models off iCloud/Desktop, "
            "or raise DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT.", gguf_dir, timeout,
        )
        return None
    return result[0]


def _select_chat_llm_path(
    model_dir: Path,
    receipt_store: "StartupReceiptStore | None" = None,
) -> Path | None:
    """Use a validated local selection before running the bounded chooser."""
    started = time.monotonic()
    if receipt_store is not None:
        try:
            cached = receipt_store.load_chat_model(model_dir)
        except Exception:
            cached = None
        if cached is not None:
            try:
                receipt_store.record(
                    "chat_model_cache_hit",
                    int((time.monotonic() - started) * 1000),
                )
            except Exception:
                pass
            return cached

    selected = _scan_chat_llm_with_timeout(model_dir / "GGUF")
    if selected is not None:
        selected = Path(selected)
    if receipt_store is not None:
        try:
            if selected is not None:
                receipt_store.cache_chat_model(selected, root=model_dir)
            else:
                receipt_store.clear_chat_model()
        except Exception:
            pass
        try:
            receipt_store.record(
                "chat_model_scan",
                int((time.monotonic() - started) * 1000),
            )
        except Exception:
            pass
    return selected


def _supervisor_stage_recorder(ctx: "AppContext"):
    """Return a bounded stage sink for the Supervisor, or None.

    v0.8.99 — `core_ready` reported one number for the whole of start_all().
    These milestones say whether the time went to SurrealDB, the API, the
    worker, or the Next server. Failures are swallowed: instrumentation must
    never be able to fail a launch.
    """
    receipt_store = getattr(ctx, "startup_receipts", None)
    if receipt_store is None:
        return None

    def _record(stage: str, elapsed_ms: int) -> None:
        try:
            receipt_store.record(stage, elapsed_ms)
        except Exception:
            pass

    return _record


def _record_core_ready(ctx: "AppContext") -> None:
    receipt_store = getattr(ctx, "startup_receipts", None)
    if receipt_store is None:
        return
    try:
        receipt_store.record(
            "core_ready",
            int((time.monotonic() - ctx.startup_started_at) * 1000),
        )
    except Exception:
        pass

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
    """Bundled source root with canonical and compatibility packages."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "upstream"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def _bundled_python_tarball(arch: str) -> Path:
    """Path to the python-build-standalone tarball shipped in the bundle."""
    if getattr(sys, "frozen", False):
        bin_dir = Path(sys._MEIPASS) / "desktop" / "bin"  # type: ignore[attr-defined]
    else:
        bin_dir = repo_root() / "desktop" / "bin"
    # v0.8.66 (audit H7) — python-build-standalone's `install_only` artifact is
    # a gzip tarball on EVERY platform (incl. windows-x86_64), so the bundled
    # file is always python-{arch}.tar.gz. The previous Windows `.zip` name
    # mislabeled gzip-tar bytes → bootstrap raised BadZipFile on first launch.
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
    model_provider_runtime: "ModelProvider | None" = None
    sv: "Supervisor | None" = None
    mm_port: int = 0
    # v0.4 memory additions
    openchronicle_available: bool = False
    commands_dst: "Path | None" = None
    memory_dashboard_port: int = 0
    app_recovery: "AppRecoveryController | None" = None
    data_root_decision: "DataRootDecision | None" = None
    data_root_recovery_root: Path | None = None
    data_root_recovery_payload: dict[str, object] | None = None
    startup_receipts: "StartupReceiptStore | None" = None
    startup_started_at: float = dataclasses.field(default_factory=time.monotonic)
    _cleanup_lock: threading.Lock = dataclasses.field(
        default_factory=threading.Lock, repr=False, compare=False
    )
    _cleanup_complete: threading.Event = dataclasses.field(
        default_factory=threading.Event, repr=False, compare=False
    )
    _cleanup_started: bool = dataclasses.field(
        default=False, repr=False, compare=False
    )
    _cleanup_owner_thread_id: int | None = dataclasses.field(
        default=None, repr=False, compare=False
    )


def _new_context() -> AppContext:
    return AppContext()


def _phase_detect_data_root_recovery(
    ctx: AppContext,
    *,
    home: Path | None = None,
) -> None:
    """Resolve guarded migration or prepare read-only divergent-root recovery."""
    decision = resolve_data_root(home=home)
    ctx.data_root_decision = decision
    if (
        decision.state != "migration-conflict"
        or decision.reason_code != "non-equivalent-roots"
    ):
        return
    recovery_root, payload = write_conflict_recovery_evidence(
        decision,
        home=home,
    )
    ctx.data_root_recovery_root = recovery_root
    ctx.data_root_recovery_payload = payload


def _phase_detect_app_recovery(
    ctx: AppContext,
    *,
    applications_dir: Path = Path("/Applications"),
    data_root: Path | None = None,
    recycler=None,
) -> None:
    """Read-only startup detection for the renamed macOS application bundle."""
    if sys.platform != "darwin":
        return
    from desktop.app_migration import AppRecoveryController

    if data_root is None and ctx.data_root_recovery_root is not None:
        data_root = ctx.data_root_recovery_root
    ctx.app_recovery = AppRecoveryController.detect(
        applications_dir=applications_dir,
        data_root=data_root,
        recycler=recycler,
    )


def _phase_open_data_root_recovery(ctx: AppContext) -> None:
    """Block in the packaged recovery webview without starting app services."""
    from desktop.window import open_data_root_recovery_window

    assert ctx.data_root_recovery_payload is not None
    assert ctx.data_root_recovery_root is not None
    open_data_root_recovery_window(
        conflict_payload=ctx.data_root_recovery_payload,
        app_recovery=ctx.app_recovery,
        storage_root=ctx.data_root_recovery_root,
    )


_DESKTOP_READINESS_NAME = "desktop-readiness.json"


def _clear_desktop_readiness_marker(log_dir: Path) -> None:
    """Remove only this launcher's stale readiness marker."""
    (log_dir / _DESKTOP_READINESS_NAME).unlink(missing_ok=True)


def _stop_app_runtime_once(ctx: AppContext) -> None:
    """Tear down owned processes once and wait for an in-flight owner."""
    caller_thread_id = threading.get_ident()
    owns_cleanup = False
    with ctx._cleanup_lock:
        if not ctx._cleanup_started:
            ctx._cleanup_started = True
            ctx._cleanup_owner_thread_id = caller_thread_id
            owns_cleanup = True
        elif ctx._cleanup_owner_thread_id == caller_thread_id:
            return

    if not owns_cleanup:
        ctx._cleanup_complete.wait()
        return

    try:
        if ctx.log_dir is not None:
            _clear_desktop_readiness_marker(ctx.log_dir)
        if ctx.sv is not None:
            ctx.sv.stop_all()
    finally:
        try:
            _stop_runtime(ctx)
        finally:
            ctx._cleanup_complete.set()


def _write_desktop_readiness_marker(
    log_dir: Path,
    *,
    api_url: str,
    frontend_url: str,
) -> Path:
    """Atomically prove that the packaged webview rendered the real app."""
    marker = log_dir / _DESKTOP_READINESS_NAME
    payload = {
        "schema_version": 1,
        "status": "ready",
        "pid": os.getpid(),
        "api_url": api_url,
        "frontend_url": frontend_url,
        "window_marker": "__next_f",
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=log_dir,
            prefix=f".{marker.name}.",
            suffix=".tmp",
            delete=False,
        ) as marker_file:
            temporary_path = Path(marker_file.name)
            json.dump(payload, marker_file, sort_keys=True)
            marker_file.write("\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
        os.replace(temporary_path, marker)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return marker


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------


def _phase_load_config(ctx: AppContext) -> None:
    """Locate config.toml; set up log dir, progress bus, and first-run flag."""
    from desktop.config import default_config_path, load_or_create
    from desktop.progress import ProgressBus
    from desktop.startup_receipts import StartupReceiptStore

    cfg_path = default_config_path()
    ctx._first_run = not cfg_path.exists()
    ctx._cfg_path = cfg_path

    log_dir = active_data_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _clear_desktop_readiness_marker(log_dir)
    ctx.log_dir = log_dir
    ctx.startup_receipts = StartupReceiptStore(active_data_root())
    try:
        ctx.startup_receipts.record("launcher_start", 0)
    except Exception:
        log.debug("startup receipt could not be recorded", exc_info=True)

    # v0.6.25 — wire `desktop.launcher`, `desktop.auto_register.*`,
    # `desktop.memory.*` etc. into launcher.log. Previously the file was
    # only written by a single .write_text() on supervisor crash (which
    # also OVERWROTE the file each time, losing history). Several
    # comments throughout the codebase promise that users can
    # `cat ~/.deeper-notebook/logs/launcher.log` to debug startup —
    # this makes that actually true. Append-mode + rotate-on-size keeps
    # the file bounded.
    _setup_launcher_log_handler(log_dir / "launcher.log")

    progress_bus = ProgressBus(log_path=log_dir / "progress.jsonl")
    progress_bus.publish("startup", "running", "Launcher starting…")
    ctx.progress_bus = progress_bus

    # Config is loaded after the wizard (if first run); stash the path.
    ctx._load_or_create = load_or_create


def _setup_launcher_log_handler(log_path: Path) -> None:
    """Add a single rotating FileHandler under `desktop` so all launcher-
    side modules (launcher, auto_register, memory, model_downloads, etc.)
    end up in launcher.log. Idempotent — safe to call from re-entrant
    code paths."""
    import logging as _logging
    from logging.handlers import RotatingFileHandler

    root = _logging.getLogger("desktop")
    # Idempotency guard — avoid duplicating the handler on relaunch within
    # the same process (e.g. unit tests re-importing the module).
    for h in root.handlers:
        if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_path):
            return

    # 2 MB × 3 backups = ~8 MB total cap. Plenty for a launcher log.
    handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3
    )
    handler.setFormatter(_logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    root.addHandler(handler)
    # Setting level on the parent ensures we capture INFO from children;
    # individual modules can still configure their own level.
    if root.level == _logging.NOTSET or root.level > _logging.INFO:
        root.setLevel(_logging.INFO)


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
        dest_parent=active_data_root(),
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
            ensure_embedding_model,
            ensure_secondary_tts_voice,
            ensure_stt_model,
            ensure_tts_model,
        )
        model_dir = Path(ctx.cfg.model_dir)
        ensure_embedding_model(model_dir, progress=_bp)
        ensure_tts_model(model_dir, progress=_bp)
        ensure_secondary_tts_voice(model_dir, progress=_bp)
        ensure_stt_model(model_dir, progress=_bp)
    except Exception:
        _bp("Warning: voice model downloads failed: " + traceback.format_exc())


def _phase_select_provider(ctx: AppContext) -> None:
    """Start or connect to the configured model provider; populate ctx.extra_env."""
    from desktop.providers.ollama import OllamaProvider
    # v0.8.3 — LlamaCppProvider no longer needed in this phase since
    # we stopped calling .start() here (the Supervisor handles the
    # production spawn). Discovery helpers (is_available,
    # pick_default_model, list_models) can still be imported lazily
    # by any callsite that wants them.

    assert ctx.cfg is not None
    assert ctx.log_dir is not None

    extra_env: dict[str, str] = {}
    cfg = ctx.cfg

    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")

    elif cfg.provider == "llamacpp":
        # v0.8.3 — stop calling LlamaCppProvider.start() here. The
        # Supervisor's own _spawn_llamacpp_chat (launcher.py:905) is
        # the production llama.cpp launch path, since v0.7.193 wired
        # auto_register to prefer sv.chat_llm_port over the
        # OPENAI_COMPATIBLE_BASE_URL env var this branch used to set.
        # Continuing to call .start() here was a duplicate ~4GB
        # subprocess that no caller routed traffic to, plus 10-30s
        # of cold-mmap latency on every launch.
        #
        # Knock-on: v0.8.2 Item A (DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH /
        # DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT) was wired into
        # LlamaCppProvider — i.e. the dead path. The Supervisor spawn
        # now picks up those env vars directly (see launcher.py
        # _spawn_llamacpp_chat v0.8.3 block) so speculative decoding
        # works in production. No env var rename — operators who
        # set them per the v0.8.2 docs get the feature for the first
        # time without touching their .env.
        #
        # LlamaCppProvider stays in scope for discovery helpers
        # (is_available, pick_default_model, list_models) used by
        # other code paths; just no longer used to spawn.
        pass

    elif cfg.provider == "mlx":
        from desktop.providers.mlx import MlxProvider

        provider = MlxProvider(
            model_dir=Path(cfg.model_dir),
            python_executable=ctx.venv_py,
        )
        # A configured launch default is already the owner's explicit model
        # choice. Validate that exact repo in ``start`` rather than first
        # enumerating every MLX directory; model libraries on Desktop/iCloud
        # volumes can make that broad scan block the native app before its UI
        # opens.
        model = cfg.default_model or provider.pick_default_model()
        if model:
            configured_model = bool(cfg.default_model)
            try:
                extra_env = provider.start(
                    model,
                    validate=not configured_model,
                    # Keep the native knowledge app available even while an
                    # explicitly selected local model is still loading.
                    wait_for_ready=not configured_model,
                )
            except FileNotFoundError as exc:
                # v0.8.84 — a configured model deleted from disk must not
                # abort the launch (everything else still works), but it must
                # also not spawn a doomed server: before this, mlx_lm.server
                # died with stderr=DEVNULL and the only symptom was a
                # "Degraded" runtime card pointing at a dead port.
                log.error(
                    "MLX model provider disabled for this launch: %s", exc
                )
            else:
                # v0.8.97 — start() now reports the RESOLVED path it launched
                # mlx_lm.server with, which is the only string that server will
                # accept as a `model` field. Only fall back to the raw config
                # reference if a provider did not report one.
                extra_env.setdefault("DEEPER_NOTEBOOK_ACTIVE_MLX_MODEL", model)
                ctx.model_provider_runtime = provider

    ctx.extra_env = extra_env


def _stop_runtime(ctx: AppContext) -> None:
    """Stop any provider process owned outside the Supervisor tree."""
    provider = ctx.model_provider_runtime
    if provider is None:
        return
    try:
        provider.stop()
    except Exception as exc:
        log.debug("model provider runtime stop failed: %s", exc)
    finally:
        ctx.model_provider_runtime = None


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
                    "clientInfo": {"name": "deeper-notebook", "version": "0.5"},
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

    # v0.8.67p — the whisper shim (faster-whisper) loads either a model-name
    # string ("base.en", downloaded from HF on first use) OR a local CTranslate2
    # model directory. Prefer the model pre-downloaded by _phase_download_models
    # so first voice use never blocks on a HF fetch — but ONLY when EVERY
    # required file is present (an incomplete dir would make faster-whisper fail
    # to load, which is worse than the HF-download fallback).
    from desktop.model_downloads import (
        FASTER_WHISPER_STT_DIR,
        FASTER_WHISPER_STT_REQUIRED,
    )
    _local_whisper = voice_model_dir / FASTER_WHISPER_STT_DIR
    if all((_local_whisper / f).exists() for f in FASTER_WHISPER_STT_REQUIRED):
        whisper_model_name = _local_whisper
    else:
        whisper_model_name = Path("base.en")  # Path so Supervisor type is satisfied
    amy_path = voice_model_dir / "TTS" / "en_US-amy-medium.onnx"
    ryan_path = voice_model_dir / "TTS" / "en_US-ryan-high.onnx"
    nomic_path = voice_model_dir / "GGUF" / "nomic-embed-text-v1.5.f16.gguf"
    # v0.5.1 audit fix: capability-aware chat-LLM selection.
    # Replaces the v0.4 hardcoded Hermes-3*.gguf glob (which loaded the
    # 5 GB model regardless of machine size). Now picks the highest-scoring
    # `chat`-kind GGUF that fits within DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING (default 4 GB
    # — small + fast for the chat experience). Hermes-3 still wins the
    # `default_tools_model` assignment if downloaded, since that slot has a
    # different recipe.
    gguf_dir = voice_model_dir / "GGUF"
    # v0.8.67f — time-bounded so a stalling model dir can't hang the launch.
    chat_llm_path = _select_chat_llm_path(
        voice_model_dir,
        ctx.startup_receipts,
    )
    # v0.7.211 — Surface "no local chat GGUF found" as a visible
    # progress event AND a launch warning the frontend can render.
    # Pre-v0.7.211 path: pick_chat_llm_file returned None, the if
    # `chat_alive` guard later silently skipped llama-cpp startup,
    # auto_register saw no chat credential, and the user opened
    # the app to find their local chat model gone with no
    # explanation. Now the user sees a clear warning on the
    # launcher splash + can be shown a toast in the frontend.
    if chat_llm_path is None and ctx.cfg.provider == "llamacpp":
        if ctx.progress_bus is not None:
            ctx.progress_bus.publish(
                "provider.llamacpp",
                "warning",
                (
                    f"No chat GGUF found in {gguf_dir}. Local chat "
                    "will be disabled until you download a model "
                    "(use the Models dialog in Settings, or drop a "
                    "Hermes-3 / Qwen2.5 / Llama-3.2 *.gguf into the "
                    "folder above)."
                ),
            )
    if nomic_path.exists() is False and ctx.cfg.provider == "llamacpp":
        if ctx.progress_bus is not None:
            ctx.progress_bus.publish(
                "provider.embedding",
                "warning",
                (
                    f"No embedding GGUF found at {nomic_path}. Vector "
                    "search will be disabled. Download nomic-embed-text-"
                    "v1.5.f16.gguf to enable semantic search."
                ),
            )
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
        # v0.8.99 — break the opaque `core_ready` bucket into per-dependency
        # milestones so a slow launch says WHICH dependency was slow.
        stage_recorder=_supervisor_stage_recorder(ctx),
    )
    try:
        sv.start_all()
    except Exception as exc:
        # v0.7.143 — Special handling for AlreadyRunning. The v0.7.142
        # singleton raises this when a previous launcher is still
        # alive. Before the dialog handler below existed, the exception
        # just propagated to the generic catch and the user got a
        # cryptic stack trace in the splash window. Now we offer a
        # native macOS dialog with two buttons:
        #   - Quit & Relaunch: SIGTERM the other launcher, wait for it
        #     to exit, then retry start_all() in-place.
        #   - Cancel: exit cleanly without doing anything.
        # If the dialog itself fails (e.g., no display available — Tk
        # not on PATH in a headless context), we fall through to the
        # original "log + raise" path so the user at least sees the
        # underlying problem.
        from desktop.singleton import AlreadyRunning
        if isinstance(exc, AlreadyRunning):
            if _handle_already_running(exc, ctx):
                # User chose "Quit & Relaunch" and the cleanup worked.
                # Retry start_all() — note we DON'T reset sv; same
                # Supervisor instance is reusable per its design.
                try:
                    sv.start_all()
                    ctx.sv = sv
                    _record_core_ready(ctx)
                    return
                except Exception as retry_exc:
                    # Retry failed for a DIFFERENT reason. Fall through
                    # to the generic logging + raise path with the new
                    # exception, not the original AlreadyRunning.
                    exc = retry_exc
            else:
                # User chose Cancel. Exit cleanly — log + raise SystemExit
                # so atexit handlers (including the singleton release if
                # we somehow got that far) still fire.
                import sys
                sys.exit(0)

        # v0.6.25 — append, not overwrite. The old `.write_text(...)`
        # truncated launcher.log, wiping any prior failure traces and
        # the FileHandler's accumulated lines. Now we open in append
        # mode with a separator so multiple failures are preserved.
        import datetime as _dt
        try:
            with (ctx.log_dir / "launcher.log").open("a") as _log:
                _log.write(
                    f"\n===== Supervisor.start_all() failed at "
                    f"{_dt.datetime.now().isoformat()} =====\n"
                    f"{traceback.format_exc()}\n"
                )
        except Exception:
            pass  # if logging itself fails, don't mask the original error
        sv.stop_all()
        _stop_runtime(ctx)
        raise exc

    ctx.sv = sv
    _record_core_ready(ctx)


def _handle_already_running(exc, ctx) -> bool:
    """v0.7.143 — Show a native dialog asking the user whether to
    kill the other launcher and continue, or cancel.

    Returns True if the user picked Quit & Relaunch AND the cleanup
    succeeded (caller should retry start_all). Returns False if the
    user cancelled OR the cleanup itself failed (caller should exit
    cleanly).

    We use Tk's messagebox (stdlib, no extra deps). On macOS Tk is
    bundled with the system Python; in the desktop bundle it's
    bundled via python-build-standalone. If for any reason Tk can't
    initialize (headless server, missing Tcl/Tk libs in some
    minimal Linux container), we log + return False so the caller
    falls through to the generic error path.
    """
    import signal
    import time

    log = logging.getLogger(__name__)
    log.warning(
        "AlreadyRunning detected: PID %d holds %s",
        exc.pid, exc.pid_file,
    )

    # Try Tk first. macOS's `osascript` fallback below covers the
    # case where Tk is broken in the bundled venv.
    user_chose_quit = False
    used_dialog = False
    try:
        import tkinter as tk
        from tkinter import messagebox as _mb

        # Create a root window we don't show (Tk requires a root for
        # any dialog to render). withdraw() hides it.
        root = tk.Tk()
        root.withdraw()
        # `askyesno` returns True for Yes, False for No.
        user_chose_quit = _mb.askyesno(
            title="Deeper Notebook is already running",
            message=(
                f"Another instance is already running (PID {exc.pid}).\n\n"
                "Do you want to quit the existing app and relaunch?"
            ),
            icon="question",
        )
        root.destroy()
        used_dialog = True
    except Exception as tk_exc:
        log.debug("Tk dialog unavailable (%s); trying osascript", tk_exc)
        # macOS fallback: use osascript to show a native AppKit dialog.
        # If THAT also fails (non-macOS, or osascript missing), the
        # `used_dialog` flag stays False and we return without
        # showing anything — caller's generic error path takes over.
        try:
            import subprocess
            script = (
                'display dialog '
                f'"Another Deeper Notebook instance is already running '
                f'(PID {exc.pid}).\\n\\nDo you want to quit the existing '
                f'app and relaunch?" '
                'buttons {"Cancel", "Quit & Relaunch"} '
                'default button "Quit & Relaunch" '
                'with title "Deeper Notebook is already running" '
                'with icon caution'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=120,
            )
            # osascript exits 1 when user clicks Cancel (or any
            # non-default button), 0 when they click the default.
            # The output contains "button returned:Quit & Relaunch"
            # or similar.
            user_chose_quit = (
                "Quit & Relaunch" in result.stdout
                and result.returncode == 0
            )
            used_dialog = True
        except Exception as osa_exc:
            log.debug("osascript fallback also failed: %s", osa_exc)

    if not used_dialog:
        # No dialog primitive worked. Be conservative: don't auto-kill.
        # Returning False sends the caller to the generic error path
        # which logs the exception + lets the user see "AlreadyRunning"
        # in the launcher log. They can manually `pkill` and relaunch.
        log.warning(
            "Could not show AlreadyRunning dialog; user must manually "
            "kill PID %d and relaunch.", exc.pid,
        )
        return False

    if not user_chose_quit:
        log.info("User cancelled AlreadyRunning dialog; exiting.")
        return False

    # User chose Quit & Relaunch. SIGTERM the other launcher and wait
    # for it to actually exit (up to 10s). Then retry start_all in the
    # caller. If the other process doesn't die within the wait window,
    # we return False rather than risk a port-collision race.
    log.info("User chose Quit & Relaunch; sending SIGTERM to PID %d", exc.pid)
    try:
        os.kill(exc.pid, signal.SIGTERM)
    except OSError as kill_exc:
        log.warning("SIGTERM to PID %d failed: %s", exc.pid, kill_exc)
        # If we couldn't even send the signal, the other process is
        # probably already dead — clean up the stale PID file ourselves
        # and let the caller retry.
        try:
            exc.pid_file.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    # Poll until dead, max 10 seconds.
    from desktop.singleton import _is_pid_alive
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not _is_pid_alive(exc.pid):
            log.info("Other launcher (PID %d) exited; proceeding to relaunch", exc.pid)
            # Clean up its stale PID file if it didn't get to release
            # cleanly (e.g., we forced it before it could atexit).
            try:
                exc.pid_file.unlink(missing_ok=True)
            except OSError:
                pass
            return True
        time.sleep(0.25)

    log.warning(
        "PID %d still alive 10s after SIGTERM; aborting relaunch attempt",
        exc.pid,
    )
    return False


def _phase_auto_register(ctx: AppContext) -> None:
    """Register discovered models with the upstream API. Non-fatal."""
    assert ctx.cfg is not None
    assert ctx.sv is not None
    assert ctx.log_dir is not None

    try:
        import urllib.parse

        from desktop.auto_register import auto_register

        cfg = ctx.cfg
        sv = ctx.sv

        api_base = sv.session_env["INTERNAL_API_URL"]

        # v0.7.193 — llamacpp_port resolution. Was:
        #   if cfg.provider == "llamacpp" and cfg.default_model:
        #       url = ctx.extra_env.get("OPENAI_COMPATIBLE_BASE_URL", "")
        #       if url: llamacpp_port = urllib.parse.urlparse(url).port
        # That ONLY discovered the chat-LLM port when the user had
        # explicitly set OPENAI_COMPATIBLE_BASE_URL in .env. But the
        # desktop launcher spawns its OWN llamacpp_chat server on a
        # dynamic port (`sv.chat_llm_port`) every launch — that port
        # was being ignored, so auto_register would log "skipping
        # local-GGUF credential registration: no llama-cpp server port
        # supplied" and not wire up the chat model. The user could
        # still add the credential manually via the Setup Wizard, but
        # the dynamic port changes every launch so the manually-saved
        # credential pointed at the WRONG port on the next launch.
        #
        # The other four local servers (whisper, piper, embed, memory)
        # already read directly from the supervisor — `llamacpp_port`
        # was the lone holdout doing env-var-only resolution. Now
        # consistent with the rest.
        #
        # Priority:
        #   1. supervisor.chat_llm_port (always present in desktop mode)
        #   2. OPENAI_COMPATIBLE_BASE_URL env override (for users with
        #      an external llama.cpp / LM Studio instance they want to
        #      target instead of the bundled one)
        llamacpp_port = getattr(sv, "chat_llm_port", None) or None
        if llamacpp_port is None and cfg.provider == "llamacpp" and cfg.default_model:
            url = ctx.extra_env.get("OPENAI_COMPATIBLE_BASE_URL", "")
            if url:
                llamacpp_port = urllib.parse.urlparse(url).port

        mlx_base_url = None
        mlx_model_ref = None
        if cfg.provider == "mlx":
            mlx_base_url = ctx.extra_env.get("OPENAI_COMPATIBLE_BASE_URL")
            mlx_model_ref = (
                resolve_env(
                    "DEEPER_NOTEBOOK_ACTIVE_MLX_MODEL",
                    getter=ctx.extra_env.get,
                )
                or cfg.default_model
            )

        auto_register(
            api_base_url=api_base, cfg=cfg, llamacpp_port=llamacpp_port,
            mlx_base_url=mlx_base_url, mlx_model_ref=mlx_model_ref,
            whisper_port=getattr(sv, "whisper_port", None) or None,
            piper_port=getattr(sv, "piper_port", None) or None,
            embed_port=getattr(sv, "embed_port", None) or None,
            memory_port=getattr(sv, "memory_port", None) or None,
        )

        # Phase 1 — Active probe each local sidecar so the launcher.log
        # captures actual health (not just port-bind success). The
        # frontend's /api/local-models/health endpoint re-runs these on
        # demand from the badge component.
        try:
            from deeper_notebook.health.local_models import (
                probe_all_local_models,
            )
            creds_for_probe = []
            if getattr(sv, "chat_llm_port", 0):
                creds_for_probe.append({
                    "name": "Local GGUF (llama.cpp)",
                    "kind": "openai_compatible",
                    "base_url": f"http://127.0.0.1:{sv.chat_llm_port}/v1",
                })
            if getattr(sv, "embed_port", 0):
                creds_for_probe.append({
                    "name": "Local Embeddings (llama.cpp)",
                    "kind": "openai_compatible",
                    "base_url": f"http://127.0.0.1:{sv.embed_port}/v1",
                })
            if creds_for_probe:
                results = probe_all_local_models(creds_for_probe)
                for r in results:
                    log.info(
                        "phase1.health %s: %s (%s, %.0fms)",
                        r["name"], r["status"], r["detail"],
                        r.get("latency_ms") or 0,
                    )
        except Exception as exc:
            log.warning("phase1.health probe failed (non-fatal): %s", exc)
    except Exception:
        # v0.6.26 — append, not overwrite. Same fix as v0.6.25's
        # launcher.log: .write_text() truncated, wiping prior failure
        # traces. Now we append with a timestamp banner so repeated
        # auto-register failures are preserved (e.g. the API was slow to
        # come up on first launch + fast on second — without history the
        # only-on-first failure looks irreproducible).
        import datetime as _dt
        try:
            with (ctx.log_dir / "auto_register.log").open("a") as _log:
                _log.write(
                    f"\n===== auto_register failed at "
                    f"{_dt.datetime.now().isoformat()} =====\n"
                    f"{traceback.format_exc()}\n"
                )
        except Exception:
            pass  # logging failure must not propagate from a non-fatal phase


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
    # v0.5.4 — pass the upstream FastAPI URL so the dashboard can populate
    # its 'Active models' header (shows which model is in each role slot).
    upstream_api = ctx.sv.session_env.get("INTERNAL_API_URL", "")
    port, _t, _l, _r = start_aiohttp_server_thread(
        lambda: _md_build_app(
            memory_retriever_url=memory_url,
            openchronicle_bridge_url=oc_url,
            upstream_api_url=upstream_api,
        )
    )
    ctx.memory_dashboard_port = port


def _phase_install_tray(ctx: AppContext) -> None:
    """Install the system tray icon with Open Main / Model Manager / Memory / Quit actions."""
    import webview as _webview

    from desktop.tray import install_tray

    assert ctx.sv is not None

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
            _webview.windows[0].destroy()
        except Exception:
            _stop_app_runtime_once(ctx)

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

    # v0.7.152 — Resolve STT + TTS shim URLs from the launcher's
    # dynamically-allocated ports so the voice-injection JS targets the
    # real shim processes instead of the non-existent /api/transcribe
    # route on the main API (which was the cause of the recurring
    # "STT failed: HTTP 404" toast). When a shim failed to start
    # (whisper_port=0 means _spawn_whisper didn't run, e.g. no whisper
    # model file present), we pass None and voice_injection.js falls
    # back to its built-in `/api/transcribe` default — still broken,
    # but no worse than today.
    whisper_port = getattr(ctx.sv, "whisper_port", 0)
    piper_port = getattr(ctx.sv, "piper_port", 0)
    stt_url = (
        f"http://127.0.0.1:{whisper_port}/v1/audio/transcriptions"
        if whisper_port else None
    )
    tts_url = (
        f"http://127.0.0.1:{piper_port}/v1/audio/speech"
        if piper_port else None
    )

    try:
        def _window_ready() -> None:
            assert ctx.log_dir is not None
            _write_desktop_readiness_marker(
                ctx.log_dir,
                api_url=ctx.sv.session_env["INTERNAL_API_URL"],
                frontend_url=ctx.sv.frontend_url,
            )
            ctx.progress_bus.publish(
                "window.ready", "done", ctx.sv.frontend_url
            )

        open_window(ctx.sv.frontend_url, on_close=lambda: _stop_app_runtime_once(ctx),
                    theme=ctx.cfg.theme,
                    memory_url=memory_url, remind_openchronicle=remind,
                    stt_url=stt_url, tts_url=tts_url,
                    app_recovery=ctx.app_recovery,
                    on_ready=_window_ready)
    finally:
        _stop_app_runtime_once(ctx)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run() -> int:
    """Top-level entry point — calls the phased orchestrators in order.

    v0.6.26 — wraps the post-supervisor phases in try/finally so that an
    exception in _phase_start_model_manager, _phase_start_memory_dashboard,
    or _phase_install_tray cleanly tears down the supervisor children
    before propagating. Before this guard, a failure in any of those
    phases would orphan SurrealDB / FastAPI / uvicorn / Next.js processes —
    they'd happily keep running after the launcher died, requiring manual
    `lsof -i` + `kill -9` to free their ports on a subsequent relaunch.

    _phase_open_window has its own finally and is OK; the new guard
    covers everything between supervisor.start_all() and that finally.
    """
    ctx = _new_context()
    _phase_detect_data_root_recovery(ctx)
    _phase_detect_app_recovery(ctx)
    if ctx.data_root_recovery_payload is not None:
        _phase_open_data_root_recovery(ctx)
        return 0
    _phase_load_config(ctx)
    _phase_wizard_if_first_run(ctx)
    _phase_bootstrap_runtime(ctx)
    _phase_download_models(ctx)
    _phase_select_provider(ctx)
    _phase_detect_openchronicle(ctx)
    _phase_register_memory_commands(ctx)
    _phase_start_supervisor(ctx)
    # From here on the supervisor owns child processes. Any uncaught
    # exception in the remaining phases MUST clean them up before
    # propagating, or the user's machine is left with orphaned binaries
    # holding ports.
    try:
        _phase_auto_register(ctx)
        _phase_start_model_manager(ctx)
        _phase_start_memory_dashboard(ctx)
        _phase_install_tray(ctx)
        _phase_open_window(ctx)
    except BaseException:
        try:
            _stop_app_runtime_once(ctx)
        except Exception:
            pass  # don't mask the original error
        raise
    return 0
