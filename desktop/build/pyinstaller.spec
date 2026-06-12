# desktop/build/pyinstaller.spec
# Run with: pyinstaller desktop/build/pyinstaller.spec
#
# Architecture after the uv-bootstrap pivot:
# - The frozen launcher only bundles its OWN light deps (pywebview, aiohttp,
#   httpx, stdlib). Upstream Python code (api/, open_notebook/, commands/)
#   ships as DATA and is run by the user-venv python, not the frozen binary.
# - uv binary + python-build-standalone are bundled in desktop/bin/ so the
#   launcher can provision ~/.open-notebook-plus/venv on first launch.
# - requirements.lock is bundled so bootstrap knows what to install.
import sys
from pathlib import Path

# SPECPATH is the directory holding this .spec file (i.e. desktop/build/).
# ROOT = desktop/
# PROJECT_ROOT = repo root
ROOT = Path(SPECPATH).resolve().parent
PROJECT_ROOT = ROOT.parent

is_mac = sys.platform == "darwin"
is_win = sys.platform == "win32"

import platform as _pl
_machine = _pl.machine().lower()
if is_mac:
    arch = "darwin-arm64" if _machine in ("arm64", "aarch64") else "darwin-x86_64"
elif is_win:
    arch = "windows-x86_64"
else:
    raise RuntimeError("unsupported platform")

bin_dir = ROOT / "bin"
node_dir = bin_dir / f"node-{arch}"
surreal_bin = bin_dir / (f"surreal-{arch}.exe" if is_win else f"surreal-{arch}")
uv_bin = bin_dir / ("uv.exe" if is_win else "uv")
# v0.8.66 (audit H7) — always .tar.gz; the install_only artifact is a gzip
# tarball on every platform (incl. Windows). The old Windows `.zip` name caused
# bootstrap to BadZipFile on first launch.
python_standalone_tarball = bin_dir / f"python-{arch}.tar.gz"
frontend_dir = PROJECT_ROOT / "frontend"

# ---------------------------------------------------------------------------
# Hidden imports — only what the launcher's OWN modules need.
# PyInstaller auto-discovers most imports; only obscure/dynamic ones need hints.
# ---------------------------------------------------------------------------
hiddenimports = [
    # pywebview uses a platform-specific backend selected at runtime.
    "webview.platforms.cocoa",    # macOS
    "webview.platforms.winforms", # Windows
    "webview.platforms.gtk",      # Linux (future)
    # aiohttp optional speedups — may be imported conditionally.
    "aiohttp._helpers",
    "aiohttp._http_parser",
    # v0.7.146 — Launcher uses function-scoped imports for these two
    # modules (see desktop/launcher.py:148 + :246). PyInstaller's
    # modulegraph generally follows local imports, but the `from X
    # import (a, b, c)` tuple form has historically been missed in
    # some PyInstaller releases. Belt-and-suspenders explicit declaration
    # — without these modules the launcher raises ModuleNotFoundError
    # at start_all() and the .app exits before writing launcher.log,
    # producing the exact silent-crash symptom the user hit on rebuild.
    "desktop.singleton",
    "desktop.next_rewrites_patcher",
]

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
datas = [
    # Upstream Python source — shipped as data, executed by venv python.
    # Paths: <MEIPASS>/upstream/api, /upstream/open_notebook, etc.
    (str(PROJECT_ROOT / "api"),          "upstream/api"),
    (str(PROJECT_ROOT / "open_notebook"), "upstream/open_notebook"),
    (str(PROJECT_ROOT / "commands"),     "upstream/commands"),
    (str(PROJECT_ROOT / "prompts"),      "upstream/prompts"),
    (str(PROJECT_ROOT / "pyproject.toml"), "upstream"),

    # Pinned lockfile — bootstrap reads this to provision the venv.
    (str(ROOT / "requirements.lock"), "desktop"),

    # Wizard static assets.
    (str(ROOT / "first_run" / "static"), "desktop/first_run/static"),

    # Bundled runtime binaries.
    (str(surreal_bin),          "desktop/bin"),
    (str(node_dir),             f"desktop/bin/node-{arch}"),
    (str(uv_bin),               "desktop/bin"),
    (str(python_standalone_tarball), "desktop/bin"),

    # Frontend standalone build.
    (str(frontend_dir / ".next" / "standalone"), "frontend"),
    (str(frontend_dir / ".next" / "static"),     "frontend/.next/static"),
    (str(frontend_dir / "public"),               "frontend/public"),

    # v0.3 — shims, manager, voice JS
    (str(PROJECT_ROOT / "desktop" / "desktop_shims"), "upstream/desktop_shims"),
    (str(ROOT / "model_manager" / "static"), "desktop/model_manager/static"),
    (str(ROOT / "model_manager" / "catalog.json"), "desktop/model_manager"),
    (str(ROOT / "first_run" / "static" / "voice_injection.js"),
        "desktop/first_run/static"),

    # v0.4 — memory package (bundled into upstream/ so worker subprocess
    # imports `desktop.memory.*` cleanly from cwd=upstream_dir), and the
    # dashboard static UI (loaded by memory_dashboard/server.py via
    # __file__-relative path).
    (str(PROJECT_ROOT / "desktop" / "memory"), "upstream/desktop/memory"),
    (str(ROOT / "memory_dashboard" / "static"),
        "desktop/memory_dashboard/static"),
    # P2-MED-13 audit fix: ship an explicit `desktop/__init__.py` inside
    # upstream/ so `from desktop.memory.writer import ...` works in the worker
    # subprocess (cwd=upstream_dir). PEP 420 namespace packages cover the
    # case where this file is missing, but ONLY if no other directory with
    # an __init__.py shadows the search path. Belt-and-suspenders.
    (str(PROJECT_ROOT / "desktop" / "__init__.py"), "upstream/desktop"),
    # v0.5.7/8 audit-fix: bundle additional desktop modules that upstream
    # API routers import:
    #   - desktop.config           — used by /api/onp/theme (theme switcher)
    #   - desktop.auto_register.*  — used by /api/models/auto-assign-capability
    #   - desktop.launcher_prefs   — used by GET/PUT /api/launcher-prefs (v0.8.65g;
    #     was missing → ModuleNotFoundError → /launcher-prefs 500 in the built app)
    # Without these the imports raise ImportError → upstream surfaces HTTP 500.
    (str(PROJECT_ROOT / "desktop" / "config.py"), "upstream/desktop"),
    (str(PROJECT_ROOT / "desktop" / "launcher_prefs.py"), "upstream/desktop"),
    (str(PROJECT_ROOT / "desktop" / "auto_register"), "upstream/desktop/auto_register"),
    # Migration #15 ships inside upstream/open_notebook/database/migrations
    # (already covered by the upstream/open_notebook entry above).
    # memory_injection.js is included by the first_run/static directory
    # entry above — no separate line needed.
]

a = Analysis(
    [str(PROJECT_ROOT / "desktop" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Upstream heavy deps — installed into user venv, not frozen.
        "fastapi", "starlette", "uvicorn",
        "langchain", "langchain_core", "langchain_community",
        "langchain_openai", "langchain_anthropic", "langchain_ollama",
        "langchain_google_genai", "langchain_groq", "langchain_mistralai",
        "langchain_deepseek", "langgraph", "langgraph_checkpoint",
        "langgraph_checkpoint_sqlite",
        "esperanto", "content_core", "ai_prompter", "podcast_creator",
        "surreal_commands", "surrealdb",
        "loguru", "tiktoken", "numpy", "pydantic", "pydantic_core",
        "dotenv", "babel", "pycountry", "sqlalchemy",
        "tomli", "tomli_w", "tomlkit",
        "charset_normalizer", "click",
        "llama_cpp",
        # Dev / test noise.
        "streamlit", "pytest", "ipykernel",
    ],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Open Notebook Plus",
    console=False,
    icon=str(ROOT / "resources" / ("icon.icns" if is_mac else "icon.ico")),
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    name="Open Notebook Plus",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="Open Notebook Plus.app",
        icon=str(ROOT / "resources" / "icon.icns"),
        bundle_identifier="com.antman1526.open-notebook-plus",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            # v0.8.65f — user-facing display name. The .app filename + bundle
            # identifier stay (filesystem/identity), but Finder/Dock/menu bar
            # use these, so the app shows as "Open notebook+".
            "CFBundleName": "Open notebook+",
            "CFBundleDisplayName": "Open notebook+",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Open notebook+ uses your microphone for voice chat (Whisper STT, runs locally on this Mac).",
        },
    )
