# open-notebook-Plus — desktop app design

**Date:** 2026-05-09
**Author:** Anthony Henry (with Claude Opus 4.7)
**Repo:** https://github.com/Antman1526/open-notebook-Plus
**Upstream:** https://github.com/lfnovo/open-notebook
**Status:** Draft — pending user review

## Goals

1. Ship a clickable desktop app (Mac `.dmg`, Windows `.zip` with `.exe`) of open-notebook so the user does not need Docker, terminal, or manual SurrealDB setup.
2. Local-model-first: the app prefers local inference (Ollama, then llama.cpp) over cloud APIs.
3. Configurable model directory (default `~/Desktop/AI_Models` on macOS, `%USERPROFILE%\Desktop\AI_Models` on Windows) so the user can drop GGUF files in and have them appear in the model picker.
4. Fork stays close to upstream — additions live in a top-level `desktop/` directory; upstream merges remain mechanical.
5. Builds run on GitHub Actions (macos-14 + macos-13 + windows-latest runners) and attach artifacts to GitHub Releases.

## Non-goals

- Code signing / notarization. Builds are unsigned; Mac users right-click → Open the first time, Windows users see SmartScreen "Run anyway."
- Bundling a default GGUF model in the binary. Models live outside the app at the configurable directory; first-run wizard offers an optional download.
- Replacing or rewriting the upstream UI. We wrap upstream as-is.
- Mobile (iOS/Android) builds.
- Production-grade telemetry, crash reporting, or auto-update — out of scope for personal-use phase 1.

## Architecture

The app is a native window (PyWebView) pointed at the upstream Next.js frontend, served alongside the upstream FastAPI backend, SurrealDB, and a worker process. A Python *launcher* supervises all child processes.

```
┌──────────────────────────────────────────────────────────────┐
│  open-notebook-Plus.app / .exe                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  PyWebView native window (WebKit on Mac, WebView2 on    │ │
│  │  Windows). Loads http://127.0.0.1:<frontend_port>.      │ │
│  └────────────────────────┬────────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────▼────────────────────────────────┐ │
│  │  launcher.py  (Python supervisor)                       │ │
│  │  • spawn SurrealDB binary  (bundled, free port)         │ │
│  │  • spawn FastAPI uvicorn   (api/, free port)            │ │
│  │  • spawn worker            (surreal-commands, no port)  │ │
│  │  • spawn Next.js server    (node frontend/start-server) │ │
│  │  • spawn model backend     (Ollama discover OR          │ │
│  │                             llama-cpp-python server)    │ │
│  │  • open PyWebView window after frontend is healthy      │ │
│  │  • on quit: graceful SIGTERM → SIGKILL fallback         │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Bundled runtimes:                                           │
│   • Python 3.12 + open-notebook deps                         │
│   • Node.js 20 LTS portable (~80 MB)                         │
│   • SurrealDB binary v2.x for the build's arch (~25 MB)      │
│   • llama-cpp-python wheels (CPU + Metal on Mac, CPU on Win) │
└──────────────────────────────────────────────────────────────┘
```

**Approximate app size (no models):** ~250 MB.

### Process lifecycle

1. User double-clicks the app.
2. `launcher.py` runs first-run check (`~/.open-notebook-plus/config.toml` exists?). If not, opens the first-run wizard window via PyWebView, served by a tiny aiohttp server in `desktop/first_run/` (see "First-run flow"). The wizard is intentionally not Streamlit/Next.js — using static HTML keeps first launch snappy.
3. Launcher picks free localhost ports (SurrealDB, FastAPI, Next.js, llama-cpp-python). Persists them for child processes via env vars.
4. Launcher writes a per-session `.env` for upstream (DB credentials, port mapping, active model provider/model).
5. Launcher spawns SurrealDB → waits for ready → spawns FastAPI → waits for `/health` → spawns worker → spawns Next.js → waits for HTTP 200 on the root path.
6. Launcher opens PyWebView window pointed at the Next.js URL.
7. On window close: launcher sends SIGTERM to all children, waits 5 s, escalates to SIGKILL if still alive.

## Repository structure

```
open-notebook-Plus/
├── (… upstream tree, untouched …)
│
├── desktop/                      ← all our additions
│   ├── launcher.py               ← supervisor
│   ├── window.py                 ← PyWebView window + splash
│   ├── first_run/                ← first-launch wizard
│   │   ├── server.py             ← tiny aiohttp server serving static HTML
│   │   └── static/               ← wizard HTML/CSS/JS
│   ├── config.py                 ← read/write ~/.open-notebook-plus/config.toml
│   ├── ports.py                  ← free-port discovery
│   ├── providers/                ← model backend abstraction
│   │   ├── __init__.py           ← Provider Protocol
│   │   ├── ollama.py             ← detect Ollama, list models
│   │   ├── llamacpp.py           ← spawn llama-cpp-python server, scan dir for *.gguf
│   │   ├── paperclip.py          ← Phase 2 stub (NotImplementedError + TODO)
│   │   └── hermes.py             ← Phase 2 stub
│   ├── resources/
│   │   ├── icon.icns             ← Mac app icon
│   │   ├── icon.ico              ← Windows app icon
│   │   └── splash.html           ← shown while backend boots
│   ├── bin/                      ← downloaded by build/fetch_runtimes.py
│   │   ├── surreal-darwin-arm64
│   │   ├── surreal-darwin-x86_64
│   │   ├── surreal-windows-x86_64.exe
│   │   ├── node-darwin-arm64/
│   │   ├── node-darwin-x86_64/
│   │   └── node-windows-x86_64/
│   ├── build/
│   │   ├── pyinstaller.spec      ← single spec, branches on sys.platform
│   │   ├── fetch_runtimes.py     ← downloads pinned SurrealDB + Node tarballs
│   │   ├── post_build_mac.sh     ← code-signless .app → .dmg
│   │   └── post_build_windows.ps1 ← .exe folder → .zip
│   ├── requirements.txt          ← desktop-specific deps (pywebview, pyinstaller)
│   ├── tests/
│   │   ├── test_ports.py
│   │   ├── test_config.py
│   │   └── test_providers.py
│   └── README.md                 ← desktop build internals
│
├── .github/
│   └── workflows/
│       └── build-desktop.yml     ← Mac arm64 + Mac x64 + Windows x64 jobs
│
├── docs/
│   └── superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md  ← this file
│
└── README.md                     ← updated for the fork
```

**Why this layout:** every file we add is under `desktop/`, `docs/`, `.github/`, or the README. No upstream Python/JS files are modified, so `git pull upstream main` should always merge cleanly. Whenever upstream changes the FastAPI routes or Next.js entry, only `launcher.py` needs adjusting.

## Local model handling

### Default directories

| Platform | Default model dir |
|---|---|
| macOS | `/Users/<user>/Desktop/AI_Models` |
| Windows | `%USERPROFILE%\Desktop\AI_Models` |

User-overridable in the first-run wizard and Settings page; persisted in `~/.open-notebook-plus/config.toml`.

The configured directory is scanned recursively for `*.gguf` files (so a `GGUF/` subdir works — matching the user's existing layout).

### Provider order at startup

1. **Ollama** — if `127.0.0.1:11434` accepts a connection, the launcher queries `/api/tags` and surfaces every Ollama-installed model in the picker. If Ollama is not running, the launcher does not attempt to start it; it shows a "Download Ollama" link in the wizard.
2. **llama.cpp** — the launcher scans the configured model directory recursively and lists every `*.gguf` file. When the user selects one, the launcher spawns `llama-cpp-python` in server mode (`python -m llama_cpp.server --model <path> --host 127.0.0.1 --port <free>`), exposing an OpenAI-compatible endpoint. Only one llama.cpp model is loaded at a time; switching kills and restarts.
3. **Cloud APIs** (OpenAI / Anthropic / Google / Groq / Mistral / DeepSeek) — these are already wired into upstream via `langchain-*` packages. Disabled by default; enabled by adding a key in Settings.

### Wiring into upstream

Upstream open-notebook reads provider config from environment variables (per `.env.example`). The launcher writes a per-session `.env` before spawning FastAPI:

```
OLLAMA_BASE_URL=http://127.0.0.1:11434          # if Ollama active
OPENAI_API_BASE=http://127.0.0.1:<llamacpp_port>  # if llama.cpp active
OPENAI_API_KEY=sk-no-key                          # placeholder for llama.cpp
DEFAULT_MODEL=<user_selected>
SURREAL_URL=ws://127.0.0.1:<surreal_port>/rpc
SURREAL_USER=root
SURREAL_PASSWORD=<random_per_session>
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
```

llama.cpp's OpenAI-compatible endpoint is fed in via `OPENAI_API_BASE` so upstream's existing `langchain-openai` integration "just works" without patches.

### Provider interface

```python
# desktop/providers/__init__.py
from typing import Protocol

class ModelProvider(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> dict: ...   # returns env vars to inject
    def stop(self) -> None: ...
```

Phase 2 stubs (`paperclip.py`, `hermes.py`) implement this interface and `raise NotImplementedError("Phase 2 — see TODO in this file.")` so the picker can list them as "coming soon" without crashing.

## First-run flow

Triggered when `~/.open-notebook-plus/config.toml` does not exist.

The wizard is its own tiny aiohttp server in `desktop/first_run/` serving static HTML; PyWebView opens the wizard window first, then the wizard hands off to the main app once config is written. Using static HTML rather than full Streamlit/Next.js keeps first-run snappy (no waiting for upstream's full stack).

Four screens:

1. **Welcome.** "open-notebook-Plus, local-first AI notebooks." [Continue]
2. **Model directory.** Text field pre-filled with platform default. [Browse…] button opens native folder picker. Created if missing.
3. **Pick a starting model.**
   - **(A) Download Llama 3.1 8B Q4** (~4.5 GB) — recommended; downloads from `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` into the model directory with a progress bar.
   - **(B) Use Ollama** — shown only if Ollama is detected. Lists installed Ollama models.
   - **(C) Skip** — close wizard; user picks later from Settings.
4. **Done.** Wizard writes `config.toml`, starts the main app stack.

After first run, every subsequent launch goes straight to the main window. Boot time on a warm SSD: ~3-5 s to first paint (covered by splash).

## Build pipeline

`.github/workflows/build-desktop.yml` triggers on:

- `push` to `main` → builds and uploads as workflow artifacts (no release).
- Tag matching `v*` → builds and attaches assets to a GitHub Release.

Three parallel jobs:

| Job | Runner | Output |
|---|---|---|
| `build-mac-arm64` | `macos-14` | `open-notebook-Plus-mac-arm64.dmg` |
| `build-mac-x86_64` | `macos-13` | `open-notebook-Plus-mac-x86_64.dmg` |
| `build-windows-x64` | `windows-latest` | `open-notebook-Plus-windows-x64.zip` |

Each job:

1. `actions/checkout@v4`
2. `actions/setup-python@v5` (Python 3.12)
3. `actions/setup-node@v4` (Node 20)
4. `cd frontend && npm ci && npm run build` (Next.js production build)
5. `pip install -r desktop/requirements.txt`
6. `python desktop/build/fetch_runtimes.py` (downloads pinned SurrealDB + portable Node into `desktop/bin/`)
7. `pyinstaller desktop/build/pyinstaller.spec`
8. Mac jobs: `desktop/build/post_build_mac.sh` → `.dmg`. Windows job: `desktop/build/post_build_windows.ps1` → `.zip`.
9. `actions/upload-artifact@v4` and (on tag) `softprops/action-gh-release@v2`.

**Pinned versions** (in `desktop/build/runtimes.toml`):
- SurrealDB: `2.1.0` (matches upstream `docker-compose.yml: surrealdb/surrealdb:v2`)
- Node: `20.18.0` LTS
- Python: `3.12.x` (CI runner default)

## Phase 2 — Paperclip and Hermes integrations

Out of scope for the first ship; design preserves clean integration points.

### Paperclip

`desktop/providers/paperclip.py` will implement the `ModelProvider` interface against Paperclip's HTTP API:
- `is_available()` → ping Paperclip's `/health` (URL configured in Settings).
- `list_models()` → list Paperclip-hired agents matching role/skill filters.
- `start(model)` → no local process; just returns env vars pointing FastAPI's request handler at Paperclip's chat endpoint.

Implementation is gated on reading Paperclip's API docs and confirming an OpenAI-compatible chat endpoint exists.

### Hermes

`desktop/providers/hermes.py` will be a thin extension over `llamacpp.py` — it knows the canonical Hermes 3 Llama-3.1 8B repo on HuggingFace, can auto-download to the model dir, and registers the model under the "Hermes Agents" label in the picker. If the v2026.5.7 release is an agent runtime rather than just weights, it'll instead spawn that runtime as a separate provider and route via its OpenAI-compatible bridge.

Both providers are stubs in phase 1: they appear in the model picker as "Coming soon" with a tooltip linking to the integration ticket.

## README content (top-level)

```
# open-notebook-Plus

A desktop-app fork of [lfnovo/open-notebook] focused on local-first AI notebooks.

## What's different from upstream
- Native desktop app: Mac .dmg, Windows .zip — no Docker, no terminal.
- Bundles SurrealDB; no separate database install.
- Local-model-first: Ollama auto-detect + llama.cpp via local GGUF directory.
- Cloud APIs are optional, off by default.
- (Phase 2) Paperclip provider + Hermes-agents support.

## Install
- **Mac**: download `.dmg` from [Releases] → drag to Applications →
  right-click → Open (unsigned, first launch only).
- **Windows**: download `.zip` from [Releases] → extract → run
  `open-notebook-Plus.exe` → SmartScreen → "Run anyway."

## First run
1. Pick a model directory (default: Desktop/AI_Models).
2. Pick a starting model: download Llama 3.1 8B, use installed Ollama, or skip.
3. Done — main UI opens.

## Adding more models
Drop any GGUF into your model directory; it appears in the picker.
Or `ollama pull <name>` and it shows up under the Ollama section.

## Building from source
- Mac/Windows local build:
    git clone https://github.com/Antman1526/open-notebook-Plus
    cd open-notebook-Plus
    pip install -r desktop/requirements.txt
    cd frontend && npm ci && npm run build && cd ..
    python desktop/build/fetch_runtimes.py
    pyinstaller desktop/build/pyinstaller.spec
- CI: push a tag `vX.Y.Z` → GitHub Actions builds .dmg + .exe and
  attaches to a Release.

## Architecture
[ASCII diagram from this spec, Architecture section]

## Credits
Forked from [lfnovo/open-notebook] (MIT). Upstream changes are merged
regularly; all upstream files remain unmodified.
```

A separate `desktop/README.md` documents internals: how `launcher.py` supervises children, how `pyinstaller.spec` works, how to add a new provider.

## Open questions and risks

These are tracked in the implementation plan, not blockers for this spec:

1. **Streamlit references in `pyproject.toml` lint config** suggest some legacy code paths. Need to verify nothing in the runtime imports Streamlit; if it does, we drop the dep before bundling.
2. **`langchain-ollama` is already in upstream deps** — the launcher's Ollama provider may be partially redundant with upstream's existing Ollama integration. Plan: launcher does *discovery* (is Ollama reachable, what models are installed) and *config injection*; upstream handles the actual API calls. No duplication.
3. **PyWebView on Windows uses Edge WebView2** — preinstalled on Windows 11, may need a runtime install on Windows 10. README will note the (free) WebView2 evergreen runtime download URL.
4. **Next.js custom server (`start-server.js`)** may have hard-coded ports. Launcher needs to either pass `PORT` env var (Next.js convention) or patch the start command. Verified during implementation.
5. **First-run model download** uses HuggingFace Hub. If gated (it isn't for the bartowski mirror), wizard prompts for a token. Default `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` is non-gated.
6. **App is unsigned.** Windows SmartScreen will warn on every install for the first ~3000 users. Mac Gatekeeper requires right-click-Open the first time. Acceptable for personal use.
7. **macOS deep-link / file-open events** not handled in phase 1.
8. **Auto-update** not handled — users re-download on each release.

## Definition of done (phase 1)

- [ ] User can double-click `open-notebook-Plus.app` on macOS arm64 → first-run wizard appears → finishes wizard → main UI opens → can chat with a local Ollama model.
- [ ] Same flow works for `open-notebook-Plus.exe` on Windows 11 x64.
- [ ] User can drop a `.gguf` file into the model directory and it appears in the picker without restart.
- [ ] App quits cleanly: no orphaned SurrealDB/uvicorn/node processes after window close.
- [ ] GitHub Actions tag-driven release produces all 3 artifacts unattended.
- [ ] README's "Install" and "First run" sections suffice for someone unfamiliar with the project to get to a chat reply.
- [ ] Paperclip and Hermes providers visible in picker as "Coming soon" without crashing the app.
