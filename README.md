# Open Notebook Plus

A desktop-app fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook)
focused on **local-first AI notebooks**.

## What's different from upstream

- Native desktop app: Mac `.dmg`, Windows `.zip` — no Docker, no terminal.
- Bundles SurrealDB and a portable Node.js runtime; no separate installs.
- **Local-model-first:** Ollama auto-detect + llama.cpp via a local GGUF directory.
- Cloud APIs are optional and off by default.
- Phase 2 (placeholder): Paperclip provider + Hermes-agents support.

## Install

- **Mac:** Download the `.dmg` from
  [Releases](https://github.com/Antman1526/open-notebook-Plus/releases), drag
  the app to **Applications**, then **right-click -> Open** the first time
  (unsigned build; macOS Gatekeeper).
- **Windows:** Download the `.zip` from Releases, extract anywhere, run
  `Open Notebook Plus.exe`. SmartScreen will warn — click **More info ->
  Run anyway** (unsigned build).

## First run

1. Pick a model directory (default: `~/Desktop/AI_Models` on Mac,
   `%USERPROFILE%\Desktop\AI_Models` on Windows).
2. Pick a starting model: download Llama 3.1 8B, use installed Ollama, or skip.
3. Done — the main UI opens.

## Adding more models

- Drop any `.gguf` file into your model directory (subdirectories are scanned
  too); it appears in the picker on next launch.
- `ollama pull <name>` — Ollama-installed models show up under the Ollama
  section in the picker.

## Voice features (preview)

Voice chat (Whisper STT + Piper TTS) is on the v0.3 roadmap. To pre-download
the required models so they're ready when the feature ships:

    python -m desktop.scripts.download_voice_models

This pulls ~170 MB into your model directory under `STT/` and `TTS/`.

## Building from source

```
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus
pip install -r desktop/requirements.txt
pip install -e .
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec --noconfirm
# Mac:    desktop/build/post_build_mac.sh
# Windows: pwsh desktop/build/post_build_windows.ps1
```

CI: tag `vX.Y.Z` -> GitHub Actions builds `.dmg` (arm64 + x86_64) and `.exe`
zip and attaches them to a Release.

## Architecture

```
+------------------------------------------------------+
|  Open Notebook Plus.app / .exe                       |
|                                                      |
|  PyWebView native window (loads frontend URL)        |
|                       |                              |
|  launcher.py supervisor                              |
|   |- SurrealDB (bundled binary)                      |
|   |- FastAPI uvicorn  (api/)                         |
|   |- open-notebook worker (surreal-commands)         |
|   |- Next.js frontend (bundled portable Node)        |
|   `- model backend (Ollama discover OR llama.cpp)    |
|                                                      |
|  Bundled: Python 3.12 . Node.js 20 LTS . SurrealDB v2|
|  Models live OUTSIDE the bundle, in your model dir.  |
+------------------------------------------------------+
```

Full design and implementation plan:
- [docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md](docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md)
- [docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md](docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md)

## Credits

Forked from [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) (MIT).
Upstream files remain unmodified; all wrapper code lives under `desktop/`.
Upstream README preserved at [README.upstream.md](README.upstream.md).
