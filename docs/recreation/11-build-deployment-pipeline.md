# 11 — Build & Deployment Pipeline

Exhaustive recreation reference for how Open Notebook Plus is built, packaged, and
deployed. Two artifact tracks, versioned independently and intentionally:

| Artifact | Version source | Consumed by |
|---|---|---|
| **Desktop app** (`.app` / `.dmg` / `.zip`) | `desktop/__init__.py` → `__version__` (0.8.x fork line) | `pyinstaller.spec`, window title, `/api/version`, update notifier |
| **Server container** (Docker image) | `pyproject.toml` → `version = "1.8.5"` (upstream track) | `.github/workflows/build-and-release.yml`, `make docker-*` |

The `pyproject.toml` header explicitly warns: *"Do not reconcile the two — they
intentionally version different artifacts."*

All snippets below are transcribed from the repo at
`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus` (branch `desktop-app`).

---

## 1. Desktop build architecture (the "uv-bootstrap pivot")

The frozen PyInstaller launcher is **thin**. It bundles only its own light deps
(pywebview, aiohttp, httpx, stdlib). All heavy upstream Python (`api/`,
`open_notebook/`, `commands/`) ships as **data** and is executed by a
user-provisioned venv, not the frozen binary. This is stated at the top of
`desktop/build/pyinstaller.spec`:

> - The frozen launcher only bundles its OWN light deps ...
> - Upstream Python code (api/, open_notebook/, commands/) ships as DATA and is
>   run by the user-venv python, not the frozen binary.
> - uv binary + python-build-standalone are bundled in `desktop/bin/` so the
>   launcher can provision `~/.open-notebook-plus/venv` on first launch.
> - `requirements.lock` is bundled so bootstrap knows what to install.

On **first launch** the app: unpacks `python-<arch>.tar.gz`, uses the bundled
`uv` to create `~/.open-notebook-plus/venv`, `uv pip install`s from the bundled
`desktop/requirements.lock`, then spawns the bundled `surreal` binary, the API
(uvicorn), the surreal-commands worker, and the Next.js standalone server — all
as child processes behind a pywebview WKWebView window.

---

## 2. Makefile — desktop targets

### 2.1 The one-shot chain

```make
BUILD_PYTHON ?= python3.12
BUILD_VENV   := .build-venv
BUILD_PIP    := $(BUILD_VENV)/bin/pip
BUILD_PY     := $(BUILD_VENV)/bin/python
BUILD_PYINSTALLER := $(BUILD_VENV)/bin/pyinstaller
BUILD_ARCH := $(shell uname -m)           # drives the DMG filename (arm64 / x86_64)

# v0.8.67k — codesigning identity for the bundle re-seal. Defaults to '-'
# (ad-hoc). A STABLE identity fixes TCC-reset-on-rebuild:
#   bash scripts/create-signing-identity.sh
#   make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"
ONP_CODESIGN_IDENTITY ?= -

build-mac: build-mac-test build-mac-lock build-mac-venv build-mac-frontend build-mac-runtimes build-mac-pyinstaller build-mac-dmg
	@echo "✅ macOS build complete:"
	@echo "    dist/Open Notebook Plus.app"
	@echo "    dist/Open-Notebook-Plus-mac-$(BUILD_ARCH).dmg"
```

`make build-mac` runs seven stages **in order**; any failure aborts the build:

| Stage | Target | What it does |
|---|---|---|
| 0 | `build-mac-test` | Full unit-test gate (precondition — see doc 10 §10). Runs `desktop/tests/` + `desktop/memory/tests/` on the 3.14 test venv AND `uv run pytest tests/` on 3.12. |
| 0.5 | `build-mac-lock` | Regenerate `desktop/requirements.lock` from `pyproject.toml` + `desktop/requirements.txt`. |
| 1 | `build-mac-venv` | Create `.build-venv` (py3.12), install `desktop/requirements.txt` + editable `-e .`. |
| 2 | `build-mac-frontend` | `npm ci` (if needed) + `npm run build` (Next standalone). |
| 3 | `build-mac-runtimes` | `fetch_runtimes.py` — download surreal/node/uv/python-standalone into `desktop/bin/`. |
| 4 | `build-mac-pyinstaller` | Run the spec → `dist/Open Notebook Plus.app`, then re-seal with codesign. |
| 5 | `build-mac-dmg` | `post_build_mac.sh` → `.dmg`. |

Override the interpreter: `make build-mac BUILD_PYTHON=/opt/homebrew/bin/python3.12`.

### 2.2 Stage 0.5 — the lockfile regen (why it exists)

```make
build-mac-lock:
	@echo "🔒 Regenerating desktop/requirements.lock from pyproject.toml + desktop/requirements.txt..."
	@uv pip compile pyproject.toml desktop/requirements.txt --python-version 3.12 \
		-o desktop/requirements.lock --quiet
	@echo "   Lockfile: $$(wc -l < desktop/requirements.lock) pinned packages"
```

Recreation-critical history (from the Makefile comment): before v0.7.141 the
lockfile was hand-maintained, so any dep added to `pyproject.toml` was silently
dropped from the bundle. v0.7.124 added `prometheus-client` but the lock was never
refreshed → bundled venv installed without it → API crashed at import
(`ModuleNotFoundError: No module named 'prometheus_client'`) → launcher timed out
on `/readyz` → the `.app` opened, showed a splash, then silently quit after ~3
min. v0.7.154 added `desktop/requirements.txt` as a **second** compile input
because compiling from `pyproject.toml` alone dropped
`llama-cpp-python>=0.3.16,<0.4` (declared only in `requirements.txt`). Passing
BOTH files merges the dep sets exactly the way `pip install -r requirements.txt`
would at runtime.

### 2.3 Stage 1 — build venv (separate from test venv)

```make
build-mac-venv:
	@if [ ! -d "$(BUILD_VENV)" ]; then $(BUILD_PYTHON) -m venv $(BUILD_VENV); fi
	@$(BUILD_PIP) install --upgrade pip > /dev/null
	@$(BUILD_PIP) install -r desktop/requirements.txt
	@$(BUILD_PIP) install -e .
```

### 2.4 Stage 2 — frontend

```make
build-mac-frontend:
	@if [ ! -d "frontend/node_modules" ]; then cd frontend && npm ci; fi
	@cd frontend && npm run build
```

Produces `frontend/.next/standalone`, `frontend/.next/static`,
`frontend/public` — all three consumed by the spec's `datas`.

### 2.5 Stage 3 — runtimes (`fetch_runtimes.py` + `runtimes.toml`)

```make
build-mac-runtimes:
	@$(BUILD_PY) desktop/build/fetch_runtimes.py     # idempotent — skips files already present
```

Pinned versions (`desktop/build/runtimes.toml`):

| Runtime | Version | Purpose |
|---|---|---|
| SurrealDB | 2.1.0 | bundled DB binary (`surreal-<arch>`) |
| Node.js | 20.18.0 | runs the Next.js standalone server |
| uv | 0.5.11 | provisions the user venv on first launch |
| python-build-standalone | cpython 3.12.8 (20241206) | the interpreter that runs the user venv |

`fetch_runtimes.py` reads the toml, resolves `host_arch()` (`darwin-arm64` /
`darwin-x86_64` / `windows-x86_64`), downloads + extracts each into
`desktop/bin/`, and forces UTF-8 stdout so the `->` status arrows don't crash on
Windows cp1252 (v0.8.68).

### 2.6 Stage 4 — PyInstaller + codesign re-seal

```make
build-mac-pyinstaller:
	@$(BUILD_PYINSTALLER) desktop/build/pyinstaller.spec --noconfirm
	@echo "🔏 Re-sealing bundle (codesign --force --deep --sign $(ONP_CODESIGN_IDENTITY))..."
	@codesign --force --deep --sign "$(ONP_CODESIGN_IDENTITY)" "dist/Open Notebook Plus.app"
	@spctl -a -vvv "dist/Open Notebook Plus.app" 2>&1 | sed 's/^/   /' || \
		echo "   ⚠️  spctl rejected the bundle (expected for ad-hoc on first-launch Gatekeeper);"
	@codesign -v "dist/Open Notebook Plus.app" 2>&1 | sed 's/^/   /' || true
```

**Why the explicit final re-seal (v0.7.146):** macOS auto-applies an ad-hoc
signature to arm64 Mach-O binaries on first write. PyInstaller writes the `.app`
in multiple phases (COLLECT then BUNDLE), and *any* later modification —
including Spotlight writing xattrs — invalidates the seal. A broken Gatekeeper
seal makes macOS **silently kill** the binary at launch (no dialog, no crash
report). The fix: one explicit `codesign` at the very end reflecting the bundle's
true final contents. `--deep` re-signs every nested Mach-O; `--force` overwrites;
`--sign -` is ad-hoc (no cert).

### 2.7 Stage 5 — dmg

```make
build-mac-dmg:
	@bash desktop/build/post_build_mac.sh
```

### 2.8 Convenience & teardown targets

```make
build-mac-install:      # copy dist/*.app → /Applications (quit running instance first, then cp + strip quarantine)
build-mac-clean:        # rm -rf dist build .build-venv  (keeps desktop/bin/ runtimes)
build-mac-distclean:    # build-mac-clean + rm -rf desktop/bin  (forces ~500 MB re-download)
```

`build-mac-install` is careful: it `osascript quit`s a running app, waits up to
20 s, then `pkill -9`s any straggler `surreal-darwin` / `llama_cpp.server` /
`surreal_commands.cli.worker` sidecars **before** `rm -rf`ing the old bundle —
because deleting the `.app` while running orphaned those sidecars and left zombie
Next.js servers on stale ports (v0.8.67e).

---

## 3. The PyInstaller spec (`desktop/build/pyinstaller.spec`)

### 3.1 Version derivation

```python
def _read_app_version() -> str:
    txt = (ROOT / "__init__.py").read_text(encoding="utf-8")   # ROOT = desktop/
    m = _re.search(r'__version__\s*=\s*"([^"]+)"', txt)
    return m.group(1) if m else "0.0.0"

APP_VERSION = _read_app_version()   # v0.8.70 — was hardcoded "0.1.0" in Info.plist
```

### 3.2 What it bundles as DATA (`datas`)

```python
datas = [
    # Upstream Python source — shipped as data, executed by venv python.
    (str(PROJECT_ROOT / "api"),           "upstream/api"),
    (str(PROJECT_ROOT / "open_notebook"), "upstream/open_notebook"),
    (str(PROJECT_ROOT / "commands"),      "upstream/commands"),
    (str(PROJECT_ROOT / "prompts"),       "upstream/prompts"),
    (str(PROJECT_ROOT / "pyproject.toml"), "upstream"),

    # Pinned lockfile — bootstrap reads this to provision the venv.
    (str(ROOT / "requirements.lock"), "desktop"),

    # Wizard static assets.
    (str(ROOT / "first_run" / "static"), "desktop/first_run/static"),

    # Bundled runtime binaries (from fetch_runtimes.py → desktop/bin/).
    (str(surreal_bin),               "desktop/bin"),
    (str(node_dir),                  f"desktop/bin/node-{arch}"),
    (str(uv_bin),                    "desktop/bin"),
    (str(python_standalone_tarball), "desktop/bin"),

    # Frontend standalone build.
    (str(frontend_dir / ".next" / "standalone"), "frontend"),
    (str(frontend_dir / ".next" / "static"),     "frontend/.next/static"),
    (str(frontend_dir / "public"),               "frontend/public"),

    # Shims, model manager, voice JS.
    (str(PROJECT_ROOT / "desktop" / "desktop_shims"), "upstream/desktop_shims"),
    (str(ROOT / "model_manager" / "static"),   "desktop/model_manager/static"),
    (str(ROOT / "model_manager" / "catalog.json"), "desktop/model_manager"),

    # Memory package + dashboard (bundled into upstream/ so the worker subprocess,
    # cwd=upstream_dir, imports `desktop.memory.*` cleanly).
    (str(PROJECT_ROOT / "desktop" / "memory"),      "upstream/desktop/memory"),
    (str(ROOT / "memory_dashboard" / "static"),     "desktop/memory_dashboard/static"),
    (str(PROJECT_ROOT / "desktop" / "__init__.py"), "upstream/desktop"),

    # Desktop modules upstream routers import (missing → HTTP 500 in the built app):
    (str(PROJECT_ROOT / "desktop" / "config.py"),         "upstream/desktop"),
    (str(PROJECT_ROOT / "desktop" / "launcher_prefs.py"), "upstream/desktop"),
    (str(PROJECT_ROOT / "desktop" / "auto_register"),     "upstream/desktop/auto_register"),
]
```

Path layout inside the bundle: `<MEIPASS>/upstream/{api,open_notebook,commands,prompts}`,
`<MEIPASS>/desktop/bin/{surreal-<arch>, node-<arch>, uv, python-<arch>.tar.gz}`,
`<MEIPASS>/frontend/{standalone, .next/static, public}`.

The python-standalone tarball is **always `.tar.gz`** on every platform (v0.8.66,
audit H7) — the old Windows `.zip` name caused `BadZipFile` on first launch.

### 3.3 Hidden imports & excludes

```python
hiddenimports = [
    "webview.platforms.cocoa", "webview.platforms.winforms", "webview.platforms.gtk",
    "aiohttp._helpers", "aiohttp._http_parser",
    # v0.7.146 — launcher uses function-scoped tuple imports PyInstaller can miss.
    "desktop.singleton", "desktop.next_rewrites_patcher",
]

a = Analysis(
    [str(PROJECT_ROOT / "desktop" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    datas=datas, hiddenimports=hiddenimports,
    excludes=[
        # Upstream heavy deps — installed into the USER venv, not frozen.
        "fastapi", "starlette", "uvicorn",
        "langchain", "langchain_core", "langchain_community",
        "langchain_openai", "langchain_anthropic", "langchain_ollama",
        "langgraph", "langgraph_checkpoint", "langgraph_checkpoint_sqlite",
        "esperanto", "content_core", "ai_prompter", "podcast_creator",
        "surreal_commands", "surrealdb",
        "loguru", "tiktoken", "numpy", "pydantic", "pydantic_core",
        "llama_cpp",
        "streamlit", "pytest", "ipykernel",   # dev/test noise
    ],
)
```

Excluding the heavy deps is the whole point of the pivot: they live in the user
venv, so freezing them would double the bundle size and pin them.

### 3.4 EXE + BUNDLE (macOS)

```python
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="Open Notebook Plus", console=False,
          icon=str(ROOT / "resources" / ("icon.icns" if is_mac else "icon.ico")))

coll = COLLECT(exe, a.binaries, a.datas, name="Open Notebook Plus")

if is_mac:
    app = BUNDLE(coll,
        name="Open Notebook Plus.app",
        icon=str(ROOT / "resources" / "icon.icns"),
        bundle_identifier="com.antman1526.open-notebook-plus",
        info_plist={
            "CFBundleShortVersionString": APP_VERSION,   # tracks desktop/__init__.py
            "CFBundleVersion": APP_VERSION,
            "CFBundleName": "Open notebook+",            # Finder/Dock display name
            "CFBundleDisplayName": "Open notebook+",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription":
                "Open notebook+ uses your microphone for voice chat (Whisper STT, runs locally on this Mac).",
        })
```

Windows note (v0.8.70): the `.exe` intentionally has **no** VERSIONINFO resource
yet — wiring it needs a real Windows host to validate the version struct, so it's
deferred rather than shipping unverifiable code.

---

## 4. Codesign flow & the stable self-signed identity

Default builds re-seal ad-hoc (`--sign -`), which gives the app a **new
cryptographic identity every rebuild**. macOS ties TCC grants (Files & Folders /
Automation) and the WKWebView persistent store to that identity, so every ad-hoc
rebuild **resets** those grants — the root cause of the iCloud/Desktop
`os.scandir` boot-wedge and the loss of Full Disk Access across rebuilds.

`scripts/create-signing-identity.sh` (run once) fixes this by adding a stable
self-signed code-signing cert to the login keychain:

```bash
bash scripts/create-signing-identity.sh                       # default identity "Open Notebook Plus Local"
make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"
```

Properties (from the script header):

- **Idempotent** — no-op if `security find-identity` already lists the identity.
- **Safe** — only ADDS a self-signed cert to *your* login keychain; touches
  nothing else.
- Generates an RSA-2048 x509 cert (10-year validity, `codeSigning` EKU) via the
  **system** `/usr/bin/openssl` (LibreSSL) — Homebrew's OpenSSL 3 exports a
  PKCS#12 whose MAC Apple's `security import` can't verify (v0.8.70).
- This is **local-dev convenience, NOT notarization.** The app is still
  un-notarized; first launch may need right-click → Open.

With a stable identity, TCC grants and the WKWebView store **persist across
rebuilds** — the whole reason it exists.

---

## 5. DMG creation — `desktop/build/post_build_mac.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
APP_NAME="Open Notebook Plus"
APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="dist/Open-Notebook-Plus-mac-$(uname -m).dmg"

# v0.8.67k — detach any stale mount of a prior ONP .dmg (else `hdiutil create`
# fails "Resource busy" even though the .app is already complete).
for _dev in $(hdiutil info 2>/dev/null | grep -iE 'Open Notebook' | grep -oE '/dev/disk[0-9]+' | sort -u); do
  hdiutil detach "${_dev}" -force >/dev/null 2>&1 || true
done
rm -f "${DMG_PATH}"

# v0.8.70 — stage the .app next to an /Applications symlink so the mounted DMG
# shows a "drag to Applications" target. Guides users to install onto the local
# SSD (cached Gatekeeper assessment) instead of running off the slow, compressed,
# read-only UDZO mount (every bundled dylib decompresses on read + re-scans).
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
cp -R "${APP_PATH}" "${STAGE}/"
ln -s /Applications "${STAGE}/Applications"

hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGE}" -ov -format UDZO "${DMG_PATH}"
echo "Built ${DMG_PATH} (with /Applications drag target)"
```

Output: `dist/Open-Notebook-Plus-mac-arm64.dmg` (or `-x86_64`). UDZO = compressed,
read-only. Unsigned/un-notarized: first launch needs right-click → Open or
`xattr -dr com.apple.quarantine`.

Windows equivalent: `desktop/build/post_build_windows.ps1` → `.zip`
(`Open-Notebook-Plus-windows-x64.zip`).

---

## 6. CI workflows (`.github/workflows/`)

Seven workflow files:

| File | Trigger | Purpose |
|---|---|---|
| `test.yml` | push/PR to `main`,`desktop-app` | backend + integration-surreal + frontend gates (see doc 10 §9) |
| `build-desktop.yml` | push to `main`/`desktop-app`, tags `v*`, manual | full mac(arm64+x86_64)+windows build → release on tag |
| `build-windows.yml` | `workflow_dispatch` only | fast Windows-only `.zip` build |
| `build-and-release.yml` | release published / manual | Docker multi-platform image → GHCR + Docker Hub |
| `build-dev.yml` | (dev image builds) | dev Docker images |
| `claude.yml` | `@claude` in issue/PR comments | Claude Code agent |
| `claude-code-review.yml` | PR opened/synchronized | automated Claude PR review |

### 6.1 `build-desktop.yml` — the desktop matrix

Three parallel jobs, then a tag-gated release. Each mirrors the Makefile stages
using plain `pip`/`pyinstaller` (CI installs on top of the upstream pyproject):

```yaml
on:
  push: { branches: [main, desktop-app], tags: ['v*'] }
  workflow_dispatch:            # v0.8.68 — manual full builds

jobs:
  build-mac-arm64:              # runs-on: macos-14
    steps:
      - uses: actions/setup-python@v5   # python 3.12
      - uses: actions/setup-node@v5     # node 20
      - run: pip install -r desktop/requirements.txt
      - run: pip install -e .
      - run: cd frontend && npm ci && npm run build
      - run: python desktop/build/fetch_runtimes.py
      - run: pyinstaller desktop/build/pyinstaller.spec --noconfirm
      - run: bash desktop/build/post_build_mac.sh
      - uses: actions/upload-artifact@v5
        with: { name: Open-Notebook-Plus-mac-arm64, path: dist/Open-Notebook-Plus-mac-arm64.dmg }

  build-mac-x86_64:             # identical, runs-on: macos-13
  build-windows-x64:            # runs-on: windows-latest, PYTHONUTF8=1, post_build_windows.ps1 → .zip

  release:
    needs: [build-mac-arm64, build-mac-x86_64, build-windows-x64]
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/download-artifact@v5
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/Open-Notebook-Plus-mac-arm64/*.dmg
            dist/Open-Notebook-Plus-mac-x86_64/*.dmg
            dist/Open-Notebook-Plus-windows-x64/*.zip
```

Note CI does **not** run the codesign re-seal or the stable-identity flow — those
are local-dev only (the artifacts are ad-hoc/unsigned).

### 6.2 `build-and-release.yml` — Docker server image

`workflow_dispatch` (with a `push_latest` boolean input) or on `release:
published`. Extracts version from `pyproject.toml`, checks for Docker Hub
secrets, and builds/pushes multi-platform images to both `ghcr.io/lfnovo/open-notebook`
and `lfnovo/open_notebook`.

```yaml
env:
  GHCR_IMAGE: ghcr.io/lfnovo/open-notebook
  DOCKERHUB_IMAGE: lfnovo/open_notebook
jobs:
  extract-version:
    steps:
      - run: |
          VERSION=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
          echo "version=$VERSION" >> $GITHUB_OUTPUT
```

### 6.3 `test.yml` (summary; full detail in doc 10)

Three jobs on `ubuntu-latest`: **backend** (`uv sync` → `uv run pytest tests/ -v
--ignore=tests/integration`), **integration-surreal** (`docker run -d
surrealdb/surrealdb:v2 start --user root --pass root --log info memory`, poll
`/health`, then `uv run pytest tests/integration/ -v -m integration_surreal`),
and **frontend** (Node 22, `npm ci` → `npm test`). `paths-ignore` skips `**.md`,
`docs/**`, and the `claude*.yml` workflows.

### 6.4 Claude workflows

`claude.yml` fires when a comment/issue contains `@claude`; `claude-code-review.yml`
runs on every PR (fork PRs via `pull_request_target`, same-repo via
`pull_request`). Both grant `contents:read`, `pull-requests:write`, `issues:write`,
`id-token:write`.

---

## 7. Docker server deployment (non-desktop)

The desktop app never uses Docker. The server profile is a separate distribution.

### 7.1 `docker-compose.yml`

```yaml
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: start --log info --user ${SURREAL_USER:-root} --pass ${SURREAL_PASSWORD:-root} rocksdb:/mydata/mydatabase.db
    user: root
    ports: ["127.0.0.1:8000:8000"]
    volumes: ["./surreal_data:/mydata"]
    environment: [SURREAL_EXPERIMENTAL_GRAPHQL=true]
    restart: always
    pull_policy: always

  open_notebook:
    image: lfnovo/open_notebook:v1-latest
    ports: ["8502:8502", "5055:5055"]        # Web UI + REST API
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=change-me-to-a-secret-string   # encrypts API keys in DB
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - SURREAL_USER=${SURREAL_USER:-root}
      - SURREAL_PASSWORD=${SURREAL_PASSWORD:-root}
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
    volumes: ["./notebook_data:/app/data"]
    depends_on: [surrealdb]
    restart: always
    pull_policy: always
```

SurrealDB is bound to `127.0.0.1` (loopback only); credentials default to
`root:root` for zero-config local use and must be overridden via `.env` before
network exposure. The compose file uses `rocksdb:` persistence (the CI integration
runner uses `memory` for a clean per-run DB — a deliberate difference).

`deploy/searxng-private/` ships an optional self-hosted SearXNG (its own
`docker-compose.yml` + `searxng/settings.yml`) for private web-search backing the
Discover Sources / web_search tool.

### 7.2 Docker make targets

```make
VERSION := $(shell grep -m1 version pyproject.toml | cut -d'"' -f2)   # 1.8.5
DOCKERHUB_IMAGE := lfnovo/open_notebook
GHCR_IMAGE := ghcr.io/lfnovo/open-notebook
PLATFORMS := linux/amd64,linux/arm64

database:              # docker compose up -d surrealdb
docker-buildx-prepare: # create/use a docker-container buildx builder (multi-platform)
docker-buildx-clean:   # rm the builder + dangling buildkit containers
docker-buildx-reset:   # clean + prepare

docker-build-local:    # docker build -t $(DOCKERHUB_IMAGE):$(VERSION) -t :local (host platform, no push)
docker-push:           # buildx build --platform linux/amd64,linux/arm64 → version tags only (regular + -single), --push
docker-push-latest:    # also tag v1-latest / v1-latest-single
docker-release:        # docker-push-latest + "release complete"

dev:                   # docker compose -f docker-compose.yml up --build
full:                  # alias of dev (docker-compose.dev.yml / .full.yml never shipped — v0.7.140 note)
tag:                   # git tag v$(VERSION) + push
```

`docker-push` builds two images from two Dockerfiles — the regular multi-service
image (default `Dockerfile`) and a single-container image (`Dockerfile.single`,
tagged `<version>-single`) — for both registries.

### 7.3 Service management (local dev, no Docker for the app tier)

`make start-all` orchestrates the full local stack: brings up SurrealDB via
compose, **polls `http://localhost:8000/health` for up to 30 s** (not a flat
sleep — v0.7.140), then launches the API with `--env-file .env` (needed so
`run_api.py` sees `OPEN_NOTEBOOK_ENCRYPTION_KEY` + `SURREAL_*`), the
surreal-commands worker, and the Next.js dev server. `make stop-all` pkills each
tier and `docker compose down`. `make status` reports each tier's up/down.

Backup/restore: `make backup [OUT=...]`, `make verify-backup BUNDLE=...`,
`make restore BUNDLE=... [FORCE=1]` (refuses a non-empty data dir without
`FORCE=1`) — all honor `ONP_DATA_DIR` and shell out to
`scripts/backup_restore.py`.

---

## 8. Reproduction checklist (macOS desktop)

```bash
# One-time: stable signing identity (persistent TCC / WKWebView store across rebuilds)
bash scripts/create-signing-identity.sh

# Full build (runs the test gate first; ~15 min + ~500 MB runtime download on first run)
make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"
# → dist/Open Notebook Plus.app
# → dist/Open-Notebook-Plus-mac-arm64.dmg   (or -x86_64)

make build-mac-install        # copy to /Applications (quits running instance, strips quarantine)
open "/Applications/Open Notebook Plus.app"
tail -F ~/.open-notebook-plus/logs/*.log
```

Iterate on a single stage with `make build-mac-{lock,venv,frontend,runtimes,pyinstaller,dmg}`.
Tear down with `make build-mac-clean` (keeps runtimes) or `build-mac-distclean`
(wipes `desktop/bin/` too).
```
