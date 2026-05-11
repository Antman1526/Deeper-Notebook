# desktop/build/pyinstaller.spec
# Run with: pyinstaller desktop/build/pyinstaller.spec
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# SPECPATH is the directory holding this .spec file (i.e. desktop/build/).
# ROOT = desktop/   (used for ROOT/bin, ROOT/first_run, ROOT/resources)
# PROJECT_ROOT = repo root  (used for api/, frontend/, open_notebook/, etc.)
ROOT = Path(SPECPATH).resolve().parent
PROJECT_ROOT = ROOT.parent

# Make PROJECT_ROOT importable at spec-load time so collect_submodules() can
# discover the first-party `api`, `commands`, and `open_notebook` packages
# (they're not pip-installed — they live in the repo).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _walk_first_party(pkg_name: str) -> list[str]:
    """Return every dotted module name under PROJECT_ROOT/pkg_name/.

    Used as a fallback to collect_submodules for first-party packages that
    aren't pip-installed, so PyInstaller still bundles every .py inside them.
    """
    pkg_dir = PROJECT_ROOT / pkg_name
    if not pkg_dir.exists():
        return []
    out = {pkg_name}
    for py in pkg_dir.rglob("*.py"):
        rel = py.relative_to(PROJECT_ROOT)
        # __init__.py → parent dir = module; foo.py → stem
        if py.name == "__init__.py":
            parts = rel.parent.parts
        else:
            parts = rel.with_suffix("").parts
        if parts:
            out.add(".".join(parts))
    return sorted(out)

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

# Wholesale-collect every package the upstream API + worker import.
# Cherry-picking specific submodules misses things (fastapi.middleware.cors etc.).
# collect_submodules walks the package tree; collect_data_files grabs non-.py files
# (Jinja templates, .json configs, etc.) that the package needs at runtime.
_collect_packages = [
    # Upstream first-party packages — must be collected as Python (not data).
    "api", "open_notebook",
    # FastAPI / Starlette stack
    "fastapi", "starlette",
    # Langchain + provider integrations (upstream pyproject deps)
    "langchain", "langchain_core", "langchain_community", "langchain_text_splitters",
    "langchain_openai", "langchain_anthropic", "langchain_ollama",
    "langchain_google_genai", "langchain_groq", "langchain_mistralai",
    "langchain_deepseek",
    "langgraph", "langgraph_checkpoint", "langgraph_checkpoint_sqlite",
    # Esperanto (AI provider abstraction) + content / podcast / prompts libs
    "esperanto", "content_core", "ai_prompter", "podcast_creator",
    # Surreal commands runtime + the upstream `commands/` directory
    "surreal_commands", "commands",
    # Misc upstream runtime deps
    "surrealdb", "loguru", "tiktoken",
    # Server runtime
    "uvicorn", "llama_cpp",
]

hiddenimports = [
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.websockets.auto",
    "llama_cpp.server",
]
_collected_datas = []
for _pkg in _collect_packages:
    try:
        _submods = collect_submodules(_pkg)
        if _submods:
            hiddenimports.extend(_submods)
        else:
            # collect_submodules returned empty — typically because the package
            # isn't pip-installed. Fall back to a directory walk so first-party
            # packages (api, commands) are still bundled.
            _walked = _walk_first_party(_pkg)
            if _walked:
                print(f"[pyinstaller.spec] {_pkg}: collect_submodules empty; "
                      f"walking PROJECT_ROOT yielded {len(_walked)} modules")
                hiddenimports.extend(_walked)
            else:
                print(f"[pyinstaller.spec] WARNING: no modules found for {_pkg}")
    except Exception as _e:
        print(f"[pyinstaller.spec] WARNING: collect_submodules failed for {_pkg}: {_e}")
        _walked = _walk_first_party(_pkg)
        if _walked:
            hiddenimports.extend(_walked)
    try:
        _collected_datas.extend(collect_data_files(_pkg))
    except Exception as _e:
        print(f"[pyinstaller.spec] WARNING: collect_data_files failed for {_pkg}: {_e}")

datas = _collected_datas + [
    # Prompts directory — non-Python templates the upstream graphs/services load.
    (str(PROJECT_ROOT / "prompts"), "prompts"),
    # Frontend: only the standalone build + static assets (no full node_modules,
    # which is ~700 MB of symlinks PyInstaller can't traverse cleanly).
    # `next build` with output="standalone" produces .next/standalone/server.js
    # plus a deduplicated node_modules dir at .next/standalone/node_modules/.
    (str(frontend_dir / ".next" / "standalone"), "frontend"),
    (str(frontend_dir / ".next" / "static"), "frontend/.next/static"),
    (str(frontend_dir / "public"), "frontend/public"),
    # Wizard static assets
    (str(ROOT / "first_run" / "static"), "desktop/first_run/static"),
    # Bundled binaries
    (str(surreal_bin), "desktop/bin"),
    (str(node_dir), f"desktop/bin/node-{arch}"),
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
        },
    )
