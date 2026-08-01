# desktop/build/pyinstaller.spec
# Run with: pyinstaller desktop/build/pyinstaller.spec
#
# Architecture after the uv-bootstrap pivot:
# - The frozen launcher only bundles its OWN light deps (pywebview, aiohttp,
#   httpx, stdlib). Canonical Python code (api/, deeper_notebook/, commands/)
#   and the open_notebook compatibility shim ship as DATA and are run by the
#   user-venv python, not the frozen binary.
# - uv binary + python-build-standalone are bundled in desktop/bin/ so the
#   launcher can provision the canonical desktop data-root venv on first launch.
# - requirements.lock is bundled so bootstrap knows what to install.
import sys
from pathlib import Path

# SPECPATH is the directory holding this .spec file (i.e. desktop/build/).
# ROOT = desktop/
# PROJECT_ROOT = repo root
ROOT = Path(SPECPATH).resolve().parent
PROJECT_ROOT = ROOT.parent
# The PyInstaller console script starts with its own bin directory at
# ``sys.path[0]``.  Add the checked-out source root before importing the shared
# package-layout helper so builds do not depend on ``desktop`` being installed
# as a distribution package.
sys.path.insert(0, str(PROJECT_ROOT))

from desktop.build.package_layout import (
    pyinstaller_upstream_package_datas,
    standalone_frontend_root,
)

# v0.8.70 — derive the app version from desktop/__init__.py instead of the old
# hardcoded "0.1.0" in the Info.plist (which left every built .app reporting
# 0.1.0 in Finder regardless of the real build). Read the string directly
# rather than importing `desktop` so the spec interpreter doesn't need the
# package's runtime deps on sys.path.
import re as _re


def _read_app_version() -> str:
    try:
        txt = (ROOT / "__init__.py").read_text(encoding="utf-8")
        m = _re.search(r'__version__\s*=\s*"([^"]+)"', txt)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0"


APP_VERSION = _read_app_version()

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
standalone_frontend_dir = standalone_frontend_root(
    frontend_dir / ".next" / "standalone"
)

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
    # One-time renamed-bundle recovery card/action contract.
    "desktop.app_migration",
]

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
datas = [
    # Upstream Python source — shipped as data, executed by venv python.
    # Paths include <MEIPASS>/upstream/deeper_notebook (canonical) and
    # /upstream/open_notebook (compatibility shim).
    (str(PROJECT_ROOT / "api"),          "upstream/api"),
    *pyinstaller_upstream_package_datas(PROJECT_ROOT),
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
    (str(standalone_frontend_dir), "frontend"),
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
    (str(PROJECT_ROOT / "desktop" / "data_root.py"), "upstream/desktop"),
    (str(PROJECT_ROOT / "desktop" / "paths.py"), "upstream/desktop"),
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
    # Migrations ship inside upstream/deeper_notebook/database/migrations.
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

# v0.8.70 — Windows VERSIONINFO is intentionally NOT wired here yet. The .exe
# therefore has no FileVersion/ProductVersion resource (the build audit's M1).
# Adding it requires a PyInstaller VSVersionInfo/version file built from
# APP_VERSION and must be validated on a real Windows build host (the version
# struct + API can't be exercised from macOS), so it's deferred to avoid
# shipping unverifiable build code into the Windows job. When done, pass
# `version=<version_file>` to this EXE() under an `is_win` guard.
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Deeper Notebook",
    console=False,
    icon=str(ROOT / "resources" / ("icon.icns" if is_mac else "icon.ico")),
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    name="Deeper Notebook",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="Deeper Notebook.app",
        icon=str(ROOT / "resources" / "icon.icns"),
        # Compatibility identifier: intentionally pinned for this release.
        # A future bundle-ID change requires signed packaged-upgrade proof and
        # explicit macOS permission-migration notes.
        bundle_identifier="com.antman1526.open-notebook-plus",
        info_plist={
            # v0.8.70 — was hardcoded "0.1.0". Now tracks desktop/__init__.py.
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "CFBundleName": "Deeper Notebook",
            "CFBundleDisplayName": "Deeper Notebook",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Deeper Notebook uses your microphone for voice chat (Whisper STT, runs locally on this Mac).",
        },
    )
