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
python_standalone_tarball = bin_dir / (
    f"python-{arch}.zip" if is_win else f"python-{arch}.tar.gz"
)
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
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Open Notebook Plus uses your microphone for voice chat (Whisper STT, runs locally on this Mac).",
        },
    )
