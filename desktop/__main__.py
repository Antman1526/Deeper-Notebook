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


def _pick_default_gguf(provider) -> str:
    """Choose a sensible default GGUF from the user's model dir.

    Preference order (first match wins):
      1. Hermes-3 family (best chat-tuned model in the user's typical set)
      2. Mistral-7B-Instruct (reliable baseline)
      3. Qwen2.5-7B-Instruct
      4. The first GGUF in the 3-8 GB range (medium-size, fits in most RAM)
      5. Any GGUF at all
    Returns "" if no usable GGUF exists.
    """
    try:
        models = provider.list_models()
    except Exception:
        return ""
    if not models:
        return ""
    by_name = {m.lower(): m for m in models}
    # Substring preference passes
    for hint in ("hermes-3", "mistral-7b-instruct", "qwen2.5-7b-instruct",
                 "llama-3.2-3b", "phi-3.5-mini"):
        for k, original in by_name.items():
            if hint in k:
                return original
    # Fallback: first one that has a "reasonable" filename length (avoids picking
    # a stub or weird custom name); list_models already filters out <1 MB files.
    return models[0]


def main() -> int:
    from desktop.config import default_config_path, load_or_create
    from desktop.launcher import Supervisor
    from desktop.providers.llamacpp import LlamaCppProvider
    from desktop.providers.ollama import OllamaProvider
    from desktop.window import open_window

    cfg_path = default_config_path()
    first_run = not cfg_path.exists()

    # Set up log directory and ProgressBus BEFORE the wizard runs.
    log_dir = (
        __import__("pathlib").Path.home() / ".open-notebook-plus" / "logs"
    )
    log_dir.mkdir(parents=True, exist_ok=True)

    from desktop.progress import ProgressBus
    progress_bus = ProgressBus(log_path=log_dir / "progress.jsonl")
    progress_bus.publish("startup", "running", "Launcher starting…")

    if first_run:
        from desktop.first_run.server import run_wizard_blocking
        run_wizard_blocking(cfg_path, progress_bus=progress_bus)

    cfg = load_or_create(cfg_path)
    arch = host_arch()
    bin_dir = repo_root() / "desktop" / "bin"

    # Bootstrap: ensure ~/.open-notebook-plus/venv is provisioned with upstream
    # deps. Progress messages go to the bootstrap log file.
    from desktop import bootstrap

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

    # Auto-download embedding + voice models if not present.
    # Non-fatal: failures are logged to downloads.log and skipped.
    import logging as _logging
    _dl_log_path = log_dir / "downloads.log"
    _dl_handler = _logging.FileHandler(_dl_log_path)
    _dl_handler.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logging.getLogger("desktop.model_downloads").addHandler(_dl_handler)

    try:
        from desktop.model_downloads import (
            ensure_embedding_model, ensure_tts_model,
            ensure_secondary_tts_voice, ensure_stt_model,
        )
        _model_dir = Path(cfg.model_dir)
        ensure_embedding_model(_model_dir, progress=_bootstrap_progress)
        ensure_tts_model(_model_dir, progress=_bootstrap_progress)
        ensure_secondary_tts_voice(_model_dir, progress=_bootstrap_progress)
        ensure_stt_model(_model_dir, progress=_bootstrap_progress)
    except Exception:
        import traceback
        _bootstrap_progress("Warning: voice model downloads failed: "
                            + traceback.format_exc())

    extra_env: dict[str, str] = {}
    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")
    elif cfg.provider == "llamacpp":
        lc = LlamaCppProvider(model_dir=cfg.model_dir, python_executable=venv_py)
        # If the user picked "llamacpp" in the wizard but didn't choose a
        # specific model, auto-pick one so a server actually runs and
        # auto_register has a live endpoint to attach credentials to.
        chosen_model = cfg.default_model or _pick_default_gguf(lc)
        if chosen_model:
            try:
                extra_env = lc.start(chosen_model)
            except Exception:
                import traceback
                _log_dir = Path.home() / ".open-notebook-plus" / "logs"
                _log_dir.mkdir(parents=True, exist_ok=True)
                (_log_dir / "llamacpp.log").write_text(
                    f"Failed to auto-start llama.cpp for {chosen_model!r}:\n"
                    f"{traceback.format_exc()}\n"
                )

    voice_model_dir = Path(cfg.model_dir)
    whisper_path = voice_model_dir / "STT" / "ggml-base.en.bin"
    amy_path = voice_model_dir / "TTS" / "en_US-amy-medium.onnx"
    ryan_path = voice_model_dir / "TTS" / "en_US-ryan-high.onnx"
    nomic_path = voice_model_dir / "GGUF" / "nomic-embed-text-v1.5.f16.gguf"
    piper_voices: dict[str, Path] = {}
    if amy_path.exists():
        piper_voices["alex"] = amy_path
    if ryan_path.exists():
        piper_voices["sam"] = ryan_path

    sv = Supervisor(
        cfg=cfg, repo_root=repo_root(), bin_dir=bin_dir,
        surreal_arch=arch, node_arch=arch,
        extra_env=extra_env, debug_mode=True,
        venv_python=venv_py, upstream_root=upstream_dir(),
        whisper_model_path=whisper_path if whisper_path.exists() else None,
        piper_voices=piper_voices,
        nomic_embed_path=nomic_path if nomic_path.exists() else None,
        progress=progress_bus,
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

    # Auto-register local models so the user opens the app with a populated
    # picker instead of a "Missing required models" warning.
    try:
        from desktop.auto_register import auto_register
        api_base = sv.session_env["INTERNAL_API_URL"]
        llamacpp_port = None
        if cfg.provider == "llamacpp" and cfg.default_model:
            # LlamaCppProvider.start() emitted OPENAI_COMPATIBLE_BASE_URL — extract port
            url = extra_env.get("OPENAI_COMPATIBLE_BASE_URL", "")
            if url:
                import urllib.parse
                llamacpp_port = urllib.parse.urlparse(url).port
        auto_register(
            api_base_url=api_base, cfg=cfg, llamacpp_port=llamacpp_port,
            whisper_port=getattr(sv, "whisper_port", None) or None,
            piper_port=getattr(sv, "piper_port", None) or None,
            embed_port=getattr(sv, "embed_port", None) or None,
        )
    except Exception:
        import traceback
        log_dir = Path.home() / ".open-notebook-plus" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "auto_register.log").write_text(traceback.format_exc())

    progress_bus.publish("ready", "done", "Main window opening…")

    try:
        open_window(sv.frontend_url, on_close=sv.stop_all, theme=cfg.theme)
    finally:
        sv.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
