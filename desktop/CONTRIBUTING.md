# Contributing to `desktop/`

This document explains how the `desktop/` package is structured, the four
recurring patterns inside it, and how to add new functionality without
touching upstream files.

---

## What `desktop/` is

`desktop/` is a **light frozen launcher** — a minimal Python package that:

1. Runs a first-launch wizard (first_run/)
2. Bootstraps a separate venv with upstream deps (bootstrap.py)
3. Manages a set of child processes via a Supervisor (launcher.py)
4. Provides a local HTTP backend for each PyWebView UI window
5. Auto-registers local model providers with the upstream API (auto_register/)

**The upstream code** (`api/`, `open_notebook/`, `commands/`) lives one level
up at the repo root. `desktop/` must never modify upstream files — it only
wraps and orchestrates them.

---

## Directory map

```
desktop/
├── __main__.py          — thin entrypoint: imports and calls desktop.app.run()
├── app.py               — phased boot orchestration (_phase_* functions)
├── aiohttp_window.py    — shared helper: start an aiohttp server in a thread
├── auto_register/       — post-startup model registration with the upstream API
├── bootstrap.py         — venv provisioning (uv + python-build-standalone)
├── config.py            — Config dataclass + load/save helpers
├── desktop_shims/       — FastAPI wrappers around local libraries
├── first_run/           — first-launch wizard (aiohttp + PyWebView)
├── launcher.py          — Supervisor: spawns/monitors all child processes
├── model_downloads.py   — auto-download embedding + voice models
├── model_manager/       — model-manager window (aiohttp + PyWebView)
├── ports.py             — find_free_port() utility
├── progress.py          — ProgressBus: cross-thread SSE event bus
├── providers/           — model backend abstractions (Ollama, llama.cpp, …)
├── resources/           — bundled assets (icons, etc.)
├── tests/               — pytest unit tests (see below)
├── tray.py              — system-tray icon
└── window.py            — open_window() helper for PyWebView
```

---

## The four patterns

### 1. Providers — model backends

A **provider** abstracts a single model-serving backend.  It lives in
`providers/` and must implement:

```python
class SomeProvider:
    name: str = "some_name"

    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> ProviderEnv: ...
    def stop(self) -> None: ...
```

`ProviderEnv` is a typed dict (see `providers/__init__.py`) whose keys are
environment variables forwarded to the Supervisor's child processes. Use the
names the upstream provider actually reads: Ollama uses `OLLAMA_API_BASE`, while
local OpenAI-compatible servers such as llama.cpp and MLX use
`OPENAI_COMPATIBLE_BASE_URL` plus `OPENAI_COMPATIBLE_API_KEY`.

**Worked example:** `providers/ollama.py` — discovers a running Ollama daemon
and returns `OLLAMA_API_BASE` so the upstream API can talk to it.

**Worked examples:** `providers/llamacpp.py` and `providers/mlx.py` — discover
local model files, start a local OpenAI-compatible server, return
`OPENAI_COMPATIBLE_BASE_URL` + `OPENAI_COMPATIBLE_API_KEY`, and clean up the
owned process in `stop()`.

**How to add a new provider:**

1. Create `providers/myprovider.py` with the four methods above.
2. Add a test in `tests/test_myprovider_provider.py` — mock `subprocess.Popen`
   and the ready-probe, cover `is_available`, `start`, `stop`.
3. Wire it up in `app.py:_phase_select_provider`: add an `elif cfg.provider == "myprovider"` branch.
4. If the provider owns a process outside the Supervisor tree, store the provider
   on `AppContext` so app shutdown and startup failures call `stop()`.

---

### 2. Shims — FastAPI wrappers around local libraries

A **shim** is a self-contained FastAPI app that wraps a local Python library
(one not available through the upstream's venv) and exposes it over HTTP so the
upstream API can call it.  Shims live in `desktop_shims/` and are spawned as
child processes by `Supervisor`.

**Worked example:** `desktop_shims/whisper_shim.py` — wraps `faster-whisper`
and exposes `POST /v1/audio/transcriptions` compatible with the OpenAI STT API.

**How to add a new shim:**

1. Create `desktop_shims/myshim_shim.py` with a FastAPI `app` and a
   `if __name__ == "__main__": uvicorn.run(app, ...)` block.
2. Add a `_spawn_myshim(self, port: int)` method on `Supervisor` in
   `launcher.py` (see `_spawn_whisper` for a template).
3. Call `self._spawn_myshim(port)` from `Supervisor.start_all()`.
4. Expose `self.myshim_port` so `app.py` can pass it to `auto_register`.
5. Register the credential + model in `auto_register/voice.py` (or a new
   sub-module if it is a different concern).
6. Add tests in `tests/test_myshim_shim.py`.

---

### 3. Windows — aiohttp-backed PyWebView windows

A **window** is a small aiohttp web app served locally, then displayed inside a
PyWebView native window.  The pattern lives in `first_run/` and `model_manager/`.

Each window module provides:
- `build_app(...) -> aiohttp.web.Application` — constructs the app with routes
- A `static/` directory with the HTML/JS frontend
- An optional blocking `run_*_blocking(...)` function if the window needs to
  gate the boot sequence (like the wizard does)

The shared server-startup scaffolding is in `aiohttp_window.py`:

```python
from desktop.aiohttp_window import start_aiohttp_server_thread

port, thread, loop, runner = start_aiohttp_server_thread(lambda: build_app(...))
```

**Worked example:** `model_manager/` — a non-blocking window started in the
background so the tray menu can open it on demand.

**How to add a new window:**

1. Create `desktop/mywindow/` with `__init__.py`, `server.py`, and `static/`.
2. In `server.py`, write `build_app(...) -> web.Application` with your routes.
3. In `app.py`, add a `_phase_start_mywindow` phase that calls
   `start_aiohttp_server_thread(lambda: build_app(...))` and stores the port on
   `ctx`.
4. Insert the phase call in `run()` at the right point.
5. Add tests in `tests/test_mywindow_server.py` using
   `aiohttp.test_utils.AioHTTPTestCase`.

---

### 4. Supervisor children — persistent child processes

The **Supervisor** (in `launcher.py`) spawns and monitors long-running child
processes (SurrealDB, FastAPI API, Next.js frontend, llama.cpp embed server,
Whisper shim, Piper shim, …).  Each child is added via a `_spawn_*` method.

**Worked example:** `launcher.py:_spawn_whisper` — spawns the Whisper shim
using the venv Python, passing the model name and port as arguments.

**How to add a new supervisor child:**

1. Write `_spawn_myservice(self, port: int) -> None` in `launcher.py`.
   Use the existing `self._spawn(args, name="myservice")` helper.
2. Allocate a port in `Supervisor.start_all()`:
   ```python
   myservice_port = find_free_port()
   self._spawn_myservice(myservice_port)
   self.myservice_port = myservice_port
   ```
3. Expose the port attribute so `app.py:_phase_auto_register` can pass it
   to `auto_register`.
4. Add tests in `tests/test_launcher.py` — mock `subprocess.Popen` and verify
   the child is started with the right arguments.

---

## Tests

All unit tests live in `desktop/tests/`.  The test runner is pytest:

```sh
python -m pytest desktop/tests/
```

Naming convention: `test_<module_name>.py`.  If a module grows large, split
tests by concern: `test_auto_register_ollama.py`, `test_auto_register_voice.py`.

The test suite must stay green before every commit.  Tests must not require
network access, running processes, or the real venv.  Use `monkeypatch`,
`MagicMock`, and `tmp_path` liberally.

The `test_piper_shim.py` file currently requires `numpy` which is not in the
dev venv — skip it or install numpy separately when working on Piper.

---

## Commit message style

All commits touching `desktop/` use the `desktop:` prefix:

```
desktop: <imperative summary under 72 chars>
```

Examples:

- `desktop: move _pick_default_gguf to LlamaCppProvider.pick_default_model`
- `desktop: split auto_register.py into a package (ollama/llamacpp/voice/profile)`
- `desktop: fix whisper shim crashing on empty audio`

---

## The golden rule

> Never modify upstream files (`api/`, `open_notebook/`, `commands/`).

If you need upstream to behave differently, add a shim, a provider, or a
config option that the upstream already supports.  Upstream changes belong in a
separate PR against the upstream repository.
