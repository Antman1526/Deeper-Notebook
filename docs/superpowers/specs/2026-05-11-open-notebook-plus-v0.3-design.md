# Open Notebook Plus v0.3 — design spec

**Date:** 2026-05-11
**Author:** Anthony Henry (with Claude Opus 4.7)
**Repo:** https://github.com/Antman1526/open-notebook-Plus
**Branch target:** `desktop-app` (or `v0.3-design` worktree)
**Status:** Draft — pending user review

## Goals (v0.3)

The v0.3 release turns Open Notebook Plus from "themed wrapper around upstream" into a **voice-first, fully-offline notebook** that meets or beats NotebookLM on its two most-marketed features (Audio Overviews + conversational chat). Five surface-area additions:

1. **Voice chat** — press-to-talk via Whisper STT + Piper TTS, fully local. Speak to your notebook; hear it speak back.
2. **Audio Overviews** — multi-voice podcast-style summaries of a notebook, rendered with local Piper TTS. NotebookLM's flagship feature, done offline.
3. **Local embedding endpoint** — second `llama.cpp` server running the already-downloaded `nomic-embed-text-v1.5.f16.gguf` so embeddings actually work (v0.2 left this as a registered-but-unserved model).
4. **In-app model manager** — separate PyWebView window for listing, downloading, deleting, and inspecting local models.
5. **Live wizard progress** — keep the wizard window visible during the 60–180 s startup window, streaming progress events so the user sees the app is alive.

## Non-goals

- **No cloud TTS / STT.** OpenAI's TTS/Whisper APIs remain optional if the user adds a key, but v0.3 ships **fully offline by default**.
- **No fork of upstream React components.** All frontend additions are JS injection into the loaded page (same mechanism v0.2 uses for theming). Brittle to upstream DOM changes; we pin to a specific upstream commit hash and bump deliberately.
- **No auto-update mechanism, codesigning, or branded icon work.** Those are explicitly v0.6 scope.
- **No mind-map, image input, OCR, MCP server, browser extension, or sync.** Those are explicitly v0.4 / v0.5 scope.
- **No multi-language voice support.** English voices only (Amy + Ryan); v0.3.1 can add the catalog.
- **No auto-speak-every-response and no silence-based auto-send.** Both require deeper hooks; users click mic to talk, click speaker to listen. v0.3.1 enhancement.

## Architecture

```
+---------------------------------------------------------------+
|  Open Notebook Plus.app                                       |
|                                                               |
|  PyWebView windows                                            |
|   ├─ wizard window (stays open through startup, NEW screen 6)|
|   ├─ main window  (injected: mic FAB + per-message speaker)  |
|   └─ model-manager window  (NEW, opened from tray + setting) |
|                                                               |
|  Launcher Supervisor (extended)                              |
|   ├── SurrealDB                  (existing)                  |
|   ├── FastAPI                    (existing)                  |
|   ├── Worker                     (existing)                  |
|   ├── Next.js                    (existing)                  |
|   ├── llama.cpp (chat)           (existing)                  |
|   ├── llama.cpp (embed)          NEW — nomic embed server   |
|   ├── Whisper STT shim           NEW — wraps whisper.cpp    |
|   └── Piper TTS shim             NEW — wraps piper CLI      |
|                                                               |
|  ProgressBus (NEW)                                           |
|   └─ publishes structured events to:                         |
|        - logs/progress.jsonl (persistent)                    |
|        - in-process SSE feed (wizard subscribes)             |
+---------------------------------------------------------------+

Voice flow (offline end-to-end):
  mic input → Web Audio API → POST audio blob →
    upstream API → Whisper shim → transcript →
      upstream chat flow → user's selected local LLM (Hermes-3, Qwen, etc.) →
        response text → Piper shim → WAV → HTMLAudioElement playback
```

The new pattern: **one new llama.cpp instance (embed)** + **two FastAPI shims (Whisper, Piper)**, all installed into the venv so they share the bootstrap path. Each shim translates upstream's expected OpenAI-style endpoints into the underlying library's native API. The supervisor now spawns up to 8 children instead of 4 (Surreal, API, worker, Next + chat LLM, embed LLM, STT shim, TTS shim). Each is swappable in isolation — swap Piper for Coqui later by replacing one shim.

## Feature 1 — Voice chat (press-to-talk + per-message TTS playback)

### 1.1 — Whisper STT subprocess

- **Binary**: `whisper-cpp-python` Python package (or, if that's unmaintained, `pywhispercpp`) added to `desktop/requirements.lock` so it installs into the venv during bootstrap.
- **Server shim**: new file `upstream/desktop_shims/whisper_shim.py` — a ~80 LOC FastAPI app that:
  - Loads the Whisper model from `cfg.model_dir / "STT" / "ggml-base.en.bin"` on startup.
  - Exposes `POST /v1/audio/transcriptions` with multipart/form-data audio input (matches OpenAI's STT API).
  - Returns `{"text": "..."}` on success.
- **Supervisor**: a new `_spawn_whisper(port)` method spawns `python -m desktop_shims.whisper_shim --port <port> --model <path>` via the venv's Python, cwd at the `upstream/` dir so the shim can `from desktop_shims.whisper_shim import app`. Wait-http with `/health`.
- **Auto-register** posts a credential `Whisper (local)` (provider `openai_compatible`, modalities `["speech_to_text"]`, base_url = shim URL) and a model `whisper-base-en` (type `speech_to_text`).

### 1.2 — Piper TTS subprocess

- **Binary**: `piper-tts` Python package (uses ONNX runtime; pure-Python install).
- **Server shim**: new file `upstream/desktop_shims/piper_shim.py` — a FastAPI app that:
  - Pre-loads two voices on startup: `en_US-amy-medium` and `en_US-ryan-high` (paths in `cfg.model_dir / "TTS"`).
  - Exposes `POST /v1/audio/speech` matching OpenAI's TTS API (input: `{"input": "text", "voice": "alex|sam", ...}`). Returns `audio/wav` body.
  - Maps `voice="alex"` → Amy voice; `voice="sam"` → Ryan. Default = Amy.
- **Supervisor**: a new `_spawn_piper(port)` method, same pattern as Whisper.
- **Auto-register** posts a credential `Piper (local)` (provider `openai_compatible`, modalities `["text_to_speech"]`) plus two models: `piper-amy-en` and `piper-ryan-en`.

### 1.3 — Embedding server

- Same llama.cpp Python module already in the venv (`llama-cpp-python`); just instantiated with `--embedding` flag pointed at the bundled `nomic-embed-text-v1.5.f16.gguf`.
- Supervisor gains an `_spawn_llamacpp_embed(port)` method. It only starts if `cfg.model_dir / "GGUF" / "nomic-embed-text-v1.5.f16.gguf"` exists (skipped silently otherwise).
- Auto-register updates the existing `nomic-embed-text-v1.5` model record to point at the live embed-server URL.

### 1.4 — Frontend injection (mic + speaker controls)

`desktop/window.py`'s `_theme_injection_js` is extended to inject (in addition to theme CSS) a JS bundle that:

- Adds a **floating microphone button** in the bottom-right of every page. Mousedown → starts recording via `navigator.mediaDevices.getUserMedia({audio: true})` + `MediaRecorder`. Mouseup → stops, POSTs blob to `/api/transcribe` (upstream's transcription endpoint, which routes to the registered STT credential). On success, the returned text is pasted into the visible chat input element (located via querySelector for the upstream component's known data-attr) and submitted.
- Adds a **speaker icon next to each rendered assistant message** via `MutationObserver` on the chat container. Click → POST message text to upstream's TTS endpoint (`/api/audio/speech`). Returned `audio/wav` blob is played via `new Audio(URL.createObjectURL(blob)).play()`.
- Both injections are isolated in `desktop/first_run/static/voice_injection.js` (loaded by the launcher and string-interpolated into the theme-injection JS).

Browser-permission flows:
- macOS will prompt for microphone permission the first time the user holds the mic button. The .app's `Info.plist` will include `NSMicrophoneUsageDescription`.
- Windows shows a similar prompt; no Info.plist needed.

### 1.5 — Honest limitations

- **DOM-injection brittleness**: if upstream restructures its chat component, mic/speaker injection breaks silently. Mitigation: pin to an upstream commit hash in `desktop/UPSTREAM_PINNED_AT` and document the upgrade procedure.
- **No streaming STT**: Whisper transcribes the full audio after release. No real-time partial transcripts. v0.3.1 can add Whisper streaming.
- **TTS is on-demand only**: no autoplay of every response. v0.3.1 can add an "auto-speak" toggle.

## Feature 2 — Audio Overviews

Upstream already implements the full pipeline (`open_notebook/podcasts/`, `commands/podcast_commands.py`, the `surreal-commands` worker command `generate_podcast`). v0.3 wires it for local use.

### 2.1 — Second Piper voice download

`desktop/model_downloads.py` gains `ensure_secondary_tts_voice()` which downloads `en_US-ryan-high.onnx` + `.onnx.json` into `cfg.model_dir / "TTS" /`. Called from `__main__.py` after the existing Amy download. Total v0.3 startup downloads: ~330 MB (embedding 273 + Amy 30 + Ryan 30 — all skipped on subsequent launches via existing idempotent download logic).

### 2.2 — Default Episode Profile

Upstream's first-launch migration tries to auto-create an Episode Profile against `gpt-5-mini` / `gpt-4o-mini-tts`, which don't exist locally — so it logs warnings and the user sees no default profile. v0.3 adds a step to `desktop/auto_register.py`:

After credentials + models are registered and defaults are auto-assigned, POST to upstream's `/api/episode_profiles`:

```json
{
  "name": "Open Notebook Plus Local",
  "description": "Two-voice podcast using local Piper TTS",
  "chat_model_id": "<resolved default chat model id>",
  "speakers": [
    {"name": "Alex", "role": "Host",     "tts_model_id": "<piper-amy-en id>"},
    {"name": "Sam",  "role": "Co-host",  "tts_model_id": "<piper-ryan-en id>"}
  ],
  "default_length_minutes": 5
}
```

Idempotent: skip if a profile with the same name already exists.

### 2.3 — End-to-end pipeline confirmation

After v0.3 ships, the user can: open a notebook → click "Generate Podcast" → pick the "Open Notebook Plus Local" profile (already selected as default) → wait ~3 minutes on Mac arm64. **No cloud calls. All script generation through the user's selected local chat model. All TTS through Piper.**

### 2.4 — Honest limitations

- **Voice quality**: Piper is naturalistic but less expressive than `gpt-4o-mini-tts`. Users can wire cloud TTS via an API key for higher quality.
- **Generation time**: ~30% of audio length on M-series for Piper alone, plus LLM script time. A 5-min podcast totals ~3 min.
- **No music / SFX**: Piper outputs pure speech; NotebookLM has subtle background bed music. v0.4 could add a stem-mixer.
- **English only for v0.3**: Piper supports 30+ languages; multi-language voice catalog is v0.3.1.

## Feature 3 — In-app model manager

A separate PyWebView window opened from a system tray menu entry and a "Manage Models" link injected into upstream's Settings page.

### 3.1 — Window layout

```
+--------------------------------------------------------+
|  Open Notebook Plus — Models                           |
|                                                        |
|  Installed                          ┌──────────────┐  |
|  ───────────                        │  Recommended │  |
|  ▣ Hermes-3-Llama-3.1-8B  4.6 GB    │  Chat        │  |
|     [Test]  [Set default]  [🗑]     │  ─ Llama 3.3 │  |
|                                     │  ─ Mistral   │  |
|  ▣ nomic-embed-text       273 MB    │              │  |
|     embedding · default     [🗑]    │  Embedding   │  |
|                                     │  ─ bge-small │  |
|  ▣ Whisper base.en        142 MB    │              │  |
|     STT · default           [🗑]    │  STT         │  |
|                                     │  ─ small.en  │  |
|  ▣ Piper Amy (en_US)       30 MB    │              │  |
|     TTS · voice 1           [🗑]    │  TTS         │  |
|                                     │  ─ Lessac    │  |
|  ▣ Piper Ryan (en_US)      30 MB    │  ─ Joe       │  |
|     TTS · voice 2           [🗑]    │              │  |
|                                     └──────────────┘  |
|  Total disk: 22.3 GB                                   |
+--------------------------------------------------------+
```

### 3.2 — Implementation

- New module `desktop/model_manager/` with the existing first-run pattern:
  - `server.py` — small aiohttp server.
  - `static/index.html` + `static/styles.css` + `static/script.js`.
- Opens in a second PyWebView window (`webview.create_window("Models", url, ...)`).
- **Right-hand "Recommended" column** reads from `desktop/model_manager/catalog.json`:
  ```json
  {
    "chat": [
      {"name": "Llama 3.3 8B", "size_mb": 4900, "url": "https://...", "dest": "GGUF/..."}
    ],
    "embedding": [...],
    "stt": [...],
    "tts": [...]
  }
  ```
  Clicking "[Get]" reuses `desktop/model_downloads._download_one`.
- **"Set default"** POSTs to upstream's `/api/models/defaults` API.
- **"Test"** calls a tiny local probe:
  - Chat → POST a test prompt through upstream `/api/chat`.
  - Embedding → POST to the live embed-server endpoint.
  - STT → record + transcribe a built-in 5-second clip.
  - TTS → render "Hello, this is a test." → play in-window.
- **"🗑 Delete"** removes the file from disk after confirming, then DELETEs the upstream model record.

### 3.3 — Tray menu entry

PyWebView supports tray icons. Add:
```
Open Notebook Plus ▼
  Open Main Window
  Manage Models…
  Settings…
  ───────────────
  Quit
```

Implementation: spawn the tray after Supervisor.start_all() returns. Tray actions just call `webview.windows[...].show()` or open new windows.

### 3.4 — Honest limitations

- **Ollama models are read-only** in the manager UI — they show up via `ollama list` (or `/api/tags`), but install/delete still requires the `ollama` CLI. v0.4 could embed Ollama management.
- **"Test" for STT/TTS** is rudimentary — just exercises a single roundtrip, doesn't benchmark.
- **No model search beyond the curated catalog**. HuggingFace search integration is a v0.4 enhancement.

## Feature 4 — Live wizard progress

### 4.1 — `ProgressBus`

New module `desktop/progress.py`:

```python
class ProgressBus:
    """Pub-sub progress channel for the launcher startup phase.

    Publishes structured events to:
      - ~/.open-notebook-plus/logs/progress.jsonl (persistent, tailable)
      - in-process subscribers (SSE handler in the wizard server)
    """
    def __init__(self, log_path: Path): ...
    def publish(self, step: str, status: str, message: str = "") -> None: ...
    def subscribe(self) -> Iterator[dict]: ...  # blocking generator for SSE
```

Each event:
```json
{"ts": "2026-05-11T12:34:56Z", "step": "supervisor.api", "status": "running", "message": "Running migrations…"}
```

Statuses: `running`, `done`, `error`. Steps follow a flat dotted naming convention: `bootstrap.extract_python`, `bootstrap.install_deps`, `download.embedding`, `download.tts_voices`, `supervisor.surreal`, `supervisor.api`, `supervisor.worker`, `supervisor.next`, `supervisor.llamacpp_chat`, `supervisor.llamacpp_embed`, `supervisor.whisper`, `supervisor.piper`, `auto_register`, `ready`.

### 4.2 — Wizard server stays alive

`desktop/first_run/server.py`:
- `/api/save` no longer signals "done and exit" — instead it transitions internal state to "waiting-for-launch".
- New `/api/progress` SSE endpoint streams events from the `ProgressBus`.
- New `/api/done` endpoint the launcher hits when the main window is open, triggering wizard auto-close (the JS receives a `{step: "ready"}` event and calls `window.close()`).

### 4.3 — Wizard screen 6

Added to `desktop/first_run/static/index.html`:

```html
<section data-screen="setting-up" hidden>
  <h2>🔧 Setting up Open Notebook Plus</h2>
  <ul id="progress-list"></ul>
  <p class="muted">Latest: <span id="progress-latest"></span></p>
  <p class="muted">Elapsed: <span id="progress-elapsed">0s</span></p>
</section>
```

JS in `desktop/first_run/static/wizard.js` opens `EventSource("/api/progress")` after the user clicks "Done" on screen 5, and updates the list as events arrive.

### 4.4 — Honest limitations

- **Long-blocking calls** in the launcher's main thread (notably `bootstrap.ensure_venv()` during a clean install) can briefly stall the SSE feed. Mitigation: pump events from a background thread so SSE stream is never blocked.
- **Errors during startup** aren't shown gracefully — the wizard's "Setting up…" screen just stops updating. v0.3.1 enhancement: display the failed step + log path + a "Retry" / "Reset" button.

## Tasks summary (informational; full plan via writing-plans)

Each row below maps to one or more implementation tasks in the `writing-plans` output:

| # | Task | New files | Modified files |
|---|------|-----------|---------------|
| 1 | Add `whisper-cpp-python` + `piper-tts` to `requirements.lock` | — | `desktop/requirements.lock` |
| 2 | Whisper STT shim | `desktop_shims/whisper_shim.py` | — |
| 3 | Piper TTS shim | `desktop_shims/piper_shim.py` | — |
| 4 | Supervisor: spawn embed server, Whisper, Piper | — | `desktop/launcher.py` |
| 5 | Auto-register STT/TTS credentials + models + Episode Profile | — | `desktop/auto_register.py` |
| 6 | Frontend voice injection (mic + speaker) | `desktop/first_run/static/voice_injection.js` | `desktop/window.py` |
| 7 | Mac `Info.plist` mic permission text | — | `desktop/build/pyinstaller.spec` |
| 8 | Secondary Piper voice download | — | `desktop/model_downloads.py`, `desktop/__main__.py` |
| 9 | `ProgressBus` module + integration | `desktop/progress.py` | `desktop/__main__.py`, `desktop/launcher.py`, `desktop/bootstrap.py`, `desktop/auto_register.py` |
| 10 | Wizard `/api/progress` SSE endpoint + screen 6 | — | `desktop/first_run/server.py`, `desktop/first_run/static/*` |
| 11 | Model-manager window | `desktop/model_manager/{server,static,catalog}.*` | `desktop/__main__.py` (open second window) |
| 12 | Tray icon | — | `desktop/__main__.py` |
| 13 | E2E smoke test (manual) | — | — |

Tests grow from 66 → ~85 with per-module coverage of: ProgressBus pub-sub, ensure_secondary_tts_voice, episode-profile registration idempotency, model-manager filesystem operations, and the two shims' health endpoints.

## Definition of done

- [ ] User opens a fresh notebook, clicks the mic button, asks "what are the main themes of this notebook?", hears Hermes-3's response spoken by Piper Amy. No cloud calls.
- [ ] User clicks Generate Podcast on a notebook with 3+ sources, picks the "Open Notebook Plus Local" profile (auto-selected), waits ~3 min, plays back a coherent two-voice dialogue. No cloud calls.
- [ ] First launch shows the wizard progress feed throughout the entire 60–180 s startup; user never sees a blank screen.
- [ ] Model-manager window opens from the tray menu and from a "Manage Models" link in upstream's Settings; user can download, delete, set-as-default, and test each model class.
- [ ] On clean install, `~/.open-notebook-plus/logs/progress.jsonl` is created and contains a `{step: "ready"}` event by the time the main window appears.
- [ ] All 85+ tests pass on the CI Mac arm64 + Windows x64 runners.

## Future scope (placeholders only, not specs)

- **v0.4** — Visual understanding: image upload, local VLM (Qwen2-VL ~5 GB), mind-map / knowledge-graph view, PDF OCR.
- **v0.5** — Ecosystem hub: MCP server mode (Claude Desktop / Cursor query the notebook), browser extension for one-click sources, multi-device sync via Tailscale / Syncthing.
- **v0.6** — Productization polish: auto-update, codesigning, branded icon, more CSS layout fixes for upstream.
