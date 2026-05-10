# desktop/build/pyinstaller.spec
# Run with: pyinstaller desktop/build/pyinstaller.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # SPECPATH = desktop/build
PROJECT_ROOT = ROOT.parent

is_mac = sys.platform == "darwin"
is_win = sys.platform == "win32"

# arch suffix used by fetch_runtimes.py
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
frontend_dir = PROJECT_ROOT / "frontend"

datas = [
    # Upstream Python source (FastAPI + worker + open_notebook package)
    (str(PROJECT_ROOT / "api"), "api"),
    (str(PROJECT_ROOT / "open_notebook"), "open_notebook"),
    (str(PROJECT_ROOT / "commands"), "commands"),
    (str(PROJECT_ROOT / "prompts"), "prompts"),
    # Frontend production build
    (str(frontend_dir / ".next"), "frontend/.next"),
    (str(frontend_dir / "public"), "frontend/public"),
    (str(frontend_dir / "package.json"), "frontend"),
    (str(frontend_dir / "start-server.js"), "frontend"),
    (str(frontend_dir / "next.config.ts"), "frontend"),
    (str(frontend_dir / "node_modules"), "frontend/node_modules"),
    # Wizard static assets
    (str(ROOT / "first_run" / "static"), "desktop/first_run/static"),
    # Bundled binaries
    (str(surreal_bin), "desktop/bin"),
    (str(node_dir), f"desktop/bin/node-{arch}"),
]

hiddenimports = [
    "uvicorn", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on",
    "uvicorn.loops.auto", "uvicorn.protocols.websockets.auto",
    "surreal_commands.worker", "llama_cpp.server",
    "langchain_openai", "langchain_anthropic", "langchain_ollama",
    "langchain_google_genai", "langchain_groq", "langchain_mistralai",
    "langchain_deepseek",
]

a = Analysis(
    [str(ROOT.parent / "desktop" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["streamlit"],  # upstream lint config mentions Streamlit; runtime doesn't need it
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="open-notebook-Plus",
    console=False,
    icon=str(ROOT / "resources" / ("icon.icns" if is_mac else "icon.ico")),
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    name="open-notebook-Plus",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="open-notebook-Plus.app",
        icon=str(ROOT / "resources" / "icon.icns"),
        bundle_identifier="com.antman1526.open-notebook-plus",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
