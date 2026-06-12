# 11 — Build & Deployment Pipeline

Recreation reference for how Open Notebook Plus is built, packaged, launched,
and supervised. Two deployment targets exist today: the **native macOS .app/.dmg**
(the documented Plus target) and the **Docker images** (upstream's server
deployment). A **Windows path is scaffolded but not wired into a one-shot
build** (see §8).

All paths repo-relative to `/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`.

> **Secrets note:** SurrealDB credentials are generated per-install
> (`secrets.token_urlsafe`) and never hardcoded; codesign identities,
> registry tokens, and `.env` values are placeholders (`<...>`) here.

---

## 1. Architecture of the desktop bundle

The build pivoted to a **frozen-launcher + user-venv** design (documented at the
top of `desktop/build/pyinstaller.spec`):

- The **frozen launcher** (PyInstaller) bundles only its own light deps:
  `pywebview`, `aiohttp`, `httpx`, stdlib. It does **not** freeze FastAPI /
  LangChain / SurrealDB / llama-cpp.
- Upstream Python (`api/`, `open_notebook/`, `commands/`, `prompts/`) ships as
  **data files** under `<MEIPASS>/upstream/…` and is executed by a
  **user-provisioned venv** at `~/.open-notebook-plus/venv`.
- A bundled **uv** binary + a **python-build-standalone** tarball let the
  launcher create that venv on first launch.
- `desktop/requirements.lock` is bundled so bootstrap knows exactly what to
  install.

This keeps the .app small, lets the heavy native deps (llama-cpp-python with
Metal) install correctly for the user's machine, and avoids re-freezing on every
dependency bump.

---

## 2. macOS build: `make build-mac`

`Makefile` defines a staged pipeline. The top-level target chains six stages
plus a precondition:

```makefile
build-mac: build-mac-test build-mac-lock build-mac-venv \
           build-mac-frontend build-mac-runtimes \
           build-mac-pyinstaller build-mac-dmg
```

Order: **test → lock → venv → frontend → runtimes → pyinstaller → dmg**.

Key variables:

```makefile
BUILD_PYTHON ?= python3.12
BUILD_VENV   := .build-venv          # separate from .venv (tests) and .venv-py312 (runtime)
BUILD_ARCH   := $(shell uname -m)    # arm64 vs x86_64 → drives DMG filename
ONP_CODESIGN_IDENTITY ?= -           # ad-hoc by default; stable identity avoids TCC resets
```

### Stage 0 — `build-mac-test` (precondition)

Runs the fast suites first so a 15-minute build is never DOA. Critically it does
**not** pipe pytest to `tail` (a piped recipe's exit status is `tail`'s, always
0 — which once made the gate toothless):

```makefile
build-mac-test:
	@/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q
	@uv run pytest tests/ -q --ignore=tests/integration
```

The desktop suite uses the `.venv` (py3.14) interpreter; the backend suite uses
the repo venv via `uv run` (py3.12). Integration tests are excluded.

### Stage 0.5 — `build-mac-lock`

Regenerates `desktop/requirements.lock` from **both** `pyproject.toml` and
`desktop/requirements.txt` so no dependency declared in only one of them is
silently dropped from the bundle (the historical `prometheus-client` and
`llama-cpp-python` casualties):

```makefile
build-mac-lock:
	@uv pip compile pyproject.toml desktop/requirements.txt --python-version 3.12 \
		-o desktop/requirements.lock --quiet
```

### Stage 1 — `build-mac-venv`

Creates the isolated `.build-venv` with `BUILD_PYTHON`, installs
`desktop/requirements.txt`, and `pip install -e .`.

### Stage 2 — `build-mac-frontend`

`npm ci` (if needed) then `npm run build`. Next.js produces the **standalone**
output (`frontend/.next/standalone` + `.next/static`) consumed by the
PyInstaller spec.

### Stage 3 — `build-mac-runtimes`

`desktop/build/fetch_runtimes.py` downloads the `surreal` binary, Node,
`uv`, and the python-build-standalone tarball into `desktop/bin/`. Idempotent —
skips files already present (config in `desktop/build/runtimes.toml`).

### Stage 4 — `build-mac-pyinstaller`

Runs the spec, then **re-seals** the bundle with codesign (see §3.3):

```makefile
build-mac-pyinstaller:
	@$(BUILD_PYINSTALLER) desktop/build/pyinstaller.spec --noconfirm
	@codesign --force --deep --sign "$(ONP_CODESIGN_IDENTITY)" "dist/Open Notebook Plus.app"
	@spctl -a -vvv "dist/Open Notebook Plus.app" ...
	@codesign -v "dist/Open Notebook Plus.app" ...
```

### Stage 5 — `build-mac-dmg`

`bash desktop/build/post_build_mac.sh` wraps the `.app` into
`dist/Open-Notebook-Plus-mac-<arch>.dmg` via `hdiutil`. Unsigned for
distribution → first launch needs right-click → Open or
`xattr -dr com.apple.quarantine`.

### Iterative + teardown targets

```
build-mac-venv / -frontend / -runtimes / -pyinstaller / -dmg   # re-run a stage
build-mac-clean         # remove dist/ build/ .build-venv/ (keeps fetched runtimes)
build-mac-distclean     # also wipe desktop/bin/ (~500 MB re-download)
build-mac-install       # quit running app, kill sidecars, cp .app → /Applications
```

`build-mac-install` is defensive: it `osascript` quits a running instance, waits
up to 20s, then `pkill -9`s stragglers (`surreal-darwin`, `llama_cpp.server`,
`surreal_commands.cli.worker`) before `cp -R` so the copy lands on a clean slate.

---

## 3. PyInstaller spec (`desktop/build/pyinstaller.spec`)

### 3.1 Inputs and data layout

Entry point: `desktop/__main__.py`. Arch resolves to `darwin-arm64`,
`darwin-x86_64`, or `windows-x86_64`.

`datas` ships upstream source + runtimes + frontend (abbreviated):

```python
datas = [
    (PROJECT_ROOT/"api",           "upstream/api"),
    (PROJECT_ROOT/"open_notebook", "upstream/open_notebook"),
    (PROJECT_ROOT/"commands",      "upstream/commands"),
    (PROJECT_ROOT/"prompts",       "upstream/prompts"),
    (PROJECT_ROOT/"pyproject.toml","upstream"),
    (ROOT/"requirements.lock",     "desktop"),             # bootstrap reads this
    (surreal_bin,                  "desktop/bin"),
    (node_dir,                     f"desktop/bin/node-{arch}"),
    (uv_bin,                       "desktop/bin"),
    (python_standalone_tarball,    "desktop/bin"),
    (frontend_dir/".next"/"standalone", "frontend"),
    (frontend_dir/".next"/"static",     "frontend/.next/static"),
    (frontend_dir/"public",             "frontend/public"),
    # desktop shims, model_manager catalog/static, memory pkg, etc.
]
```

A subtle correctness fix lives here: the python-build-standalone artifact is
**always `.tar.gz`** even on Windows (the old `.zip` name caused
`BadZipFile` on first launch).

### 3.2 Excludes — heavy deps NOT frozen

```python
excludes = [
    "fastapi","starlette","uvicorn",
    "langchain","langchain_core","langgraph","langgraph_checkpoint",
    "esperanto","content_core","ai_prompter","podcast_creator",
    "surreal_commands","surrealdb",
    "loguru","tiktoken","numpy","pydantic","pydantic_core",
    "llama_cpp",
    "streamlit","pytest","ipykernel",   # dev/test noise
]
```

These all install into the **user venv** instead. `hiddenimports` only hints the
launcher's own dynamic imports (pywebview backends, `desktop.singleton`,
`desktop.next_rewrites_patcher`).

### 3.3 Bundle + codesign

```python
exe  = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Open Notebook Plus",
           console=False, icon=...icon.icns)
coll = COLLECT(exe, a.binaries, a.datas, name="Open Notebook Plus")
app  = BUNDLE(coll, name="Open Notebook Plus.app",
              bundle_identifier="com.antman1526.open-notebook-plus",
              info_plist={
                  "CFBundleShortVersionString": "0.1.0",
                  "CFBundleName": "Open notebook+",
                  "CFBundleDisplayName": "Open notebook+",
                  "NSHighResolutionCapable": True,
                  "NSMicrophoneUsageDescription": "...Whisper STT, runs locally...",
              })
```

The Makefile's post-PyInstaller `codesign --force --deep --sign -` matters
because macOS auto-seals arm64 Mach-O binaries, and PyInstaller's multi-pass
writes invalidate that seal — a broken Gatekeeper seal kills the binary at
launch silently. A **stable** identity (vs ad-hoc `-`) also stops macOS resetting
TCC Files-&-Folders permissions on every rebuild.

---

## 4. Runtime venv bootstrap (`desktop/bootstrap.py`)

On first launch (or whenever the lock changes), the launcher provisions
`~/.open-notebook-plus/venv`.

### 4.1 Lock-hash currency check

```python
def _lock_hash(lock_path: Path) -> str:
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()

def is_venv_current(lock_path: Path) -> bool:
    if not venv_python().exists():       return False
    marker = venv_marker()               # ~/.open-notebook-plus/venv-marker
    if not marker.exists():              return False
    return marker.read_text().strip() == _lock_hash(lock_path)
```

If the marker hash matches the bundled lock, the existing venv is reused. Any
mismatch → wipe and reinstall.

### 4.2 Python runtime extraction with partial-extraction recovery

`extract_python_runtime()` unpacks the python-build-standalone tarball into
`~/.open-notebook-plus/python-runtime/`. If the interpreter exists it is
**health-checked** before reuse — a `python -c "import sys, encodings"` probe
with a 5s timeout — and the runtime dir is wiped + re-extracted if the probe
fails (recovers from interrupted extractions / Time Machine partials).

### 4.3 ensure_venv

```python
def ensure_venv(standalone_python, uv_binary, lock_path, upstream_dir, progress=None):
    if is_venv_current(lock_path):
        progress(f"Environment is up to date (delete {venv_dir()} to force reinstall…)")
        return venv_python()
    if venv_dir().exists():
        shutil.rmtree(venv_dir())                         # wipe partial state
    _run_logged([str(standalone_python), "-m", "venv", str(venv_dir())], "venv-create")
    _run_logged([str(uv_binary), "pip", "install",
                 "--python", str(venv_python()), "-r", str(lock_path)], "uv-install")
    # make upstream importable from the venv:
    (site_packages/"open_notebook_upstream.pth").write_text(str(upstream_dir) + "\n")
    # belt-and-suspenders: verify imports that would crash api.main at import time
    missing = _verify_critical_imports(venv_python(),
        ["prometheus_client","surrealdb","fastapi","langgraph","loguru","pydantic"])
    if missing:
        raise RuntimeError("...venv missing critical packages: ...recover with rm -rf ...")
    venv_marker().write_text(_lock_hash(lock_path))       # commit currency marker
    return venv_python()
```

### 4.4 Logged subprocesses (`_run_logged`)

Because Finder-launched apps have no terminal, every bootstrap subprocess is
captured to `~/.open-notebook-plus/logs/bootstrap-subprocess.log` (rotated at
5 MB), and a non-zero exit raises a `RuntimeError` carrying the **last 25 lines**
of that log. `shlex.join` writes a copy-pasteable command header; `os.fsync`
flushes before the tail is read.

---

## 5. Launcher orchestration

### 5.1 Boot phases (`desktop/app.py`)

The boot sequence is broken into named phases operating on a shared `AppContext`
dataclass (docstring at `desktop/app.py:8`):

```
1.  _phase_load_config          locate config.toml; set log dir + ProgressBus
2.  _phase_wizard_if_first_run  run first-run wizard on first launch
3.  _phase_bootstrap_runtime    bootstrap.ensure_venv (provision the venv)
4.  _phase_download_models      auto-download embedding + voice models
5.  _phase_select_provider      start Ollama / llama.cpp; populate extra_env
6.  _phase_start_supervisor     build & start the Supervisor process tree
7.  _phase_auto_register        register discovered models with the API
8.  _phase_start_model_manager  start the aiohttp model-manager window server
9.  _phase_install_tray         system tray icon + menu
10. _phase_open_window          open PyWebView main window (blocks until closed)
```

Each phase publishes structured events to the `ProgressBus` so the splash/wizard
SSE feed and `progress.jsonl` reflect startup state.

### 5.2 Supervisor (`desktop/launcher.py`)

`Supervisor.start_all()` does, in order:

1. **Singleton enforcement** — `acquire_singleton(default_pid_file())` raises
   `AlreadyRunning` if a live instance holds the PID-file lock (the app shows a
   friendly dialog instead of spawning a second port-grabbing process tree).
2. **Orphan reap** — `reap_orphans(bundle_paths=[~/.open-notebook-plus/venv, bin_dir])`
   kills leftover children from a crashed prior launch, then sleeps 0.5s so the
   OS frees their ports.
3. **Merge `launcher.env`** into `os.environ` (env wins over file).
4. **Allocate dynamic ports** (§6).
5. Spawn children with health gates and per-kind progress events.

Child spawns (all via the venv python, `cwd=upstream_root`):

```python
# SurrealDB — Path.as_uri() for cross-platform file:// correctness
[surreal, "start", f"--user={user}", f"--pass={pass}",
 f"--bind=127.0.0.1:{port}", data_dir.as_uri()]

# API
[venv_python, "-m", "uvicorn", "api.main:app", "--host","127.0.0.1","--port",str(port)]

# Worker (surreal-commands) — concurrency pinned/tunable
[venv_python, "-m", "surreal_commands.cli.worker",
 "--import-modules", "commands", "--max-tasks", str(max_tasks)]  # ONP_WORKER_MAX_TASKS, default 5, clamp 1..32
```

Optional sidecars are spawned through `_try_spawn` (failures are logged + emitted
as a non-fatal progress event, never aborting the supervisor):
`llamacpp_embed`, `whisper`, `piper`, `llamacpp_chat`, `memory_retriever`,
`openchronicle`.

### 5.3 Sidecar supervision & health gates

- **Process groups** — every child is spawned with `start_new_session=True`
  (POSIX) / `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` (Windows) so
  `stop_all` can `os.killpg` the **whole subtree** (fixes orphaned `next-server`
  zombies).
- **Health gates** — `_wait_tcp` / `_wait_http` poll the child's port AND
  `proc.poll()`; a dead child raises immediately (rc in the message) instead of
  waiting out the full timeout. The frontend gate additionally requires
  `consecutive=N` `<500` hits with `follow_redirects=True` to defeat the
  launch-race "This page couldn't load".
- **Per-child logs** — in debug mode `_start_drainers` writes full
  `{name}.log`; in normal mode `_start_tail_drainer` keeps a
  `deque(maxlen=50)` of stderr and atomically rewrites `{name}.tail`. Both
  scrub secrets (`--pass=`, `password=`, `encryption_key=` → `[REDACTED]`).
  The API surfaces these via `GET /healthz/sidecars/{kind}/log`, with
  `classify_sidecar_error()` rendering a one-line hint above the raw tail.
- **Startup-timeout ceiling** — `_startup_timeout(env_key, default)` lets slow
  cold starts (first-run model load) extend the gate without a rebuild.

### 5.4 Launcher control plane

`launcher_control.py` registers callbacks (e.g. `restart_sidecar`) so the API
can hot-restart a specific sidecar Popen (tracked in
`self._sidecar_procs[kind]`) without quitting the app.

---

## 6. Dynamic ports (`desktop/ports.py`)

`start_all` allocates **nine** ports atomically up front:

```python
(surreal_port, api_port, frontend_port,
 embed_port, whisper_port, piper_port,
 chat_llm_port, memory_port, openchronicle_port) = find_free_ports(9)
```

`find_free_ports(n)` binds `n` probe sockets to `127.0.0.1:0` simultaneously
(holding them until return) so the OS hands out distinct ephemeral ports, sets
`SO_REUSEADDR` to shrink the close→bind race window, **de-duplicates** the
result, and re-probes up to `_MAX_REPROBE_ATTEMPTS = 5` times on the rare
allocator-quirk duplicate. The `api_url` is then `http://127.0.0.1:{api_port}`,
and `PORT` is only injected into the Next.js child's env (per-child `extra_env`)
so it doesn't leak into uvicorn-based sidecars and override their `--port`.

---

## 7. Docker (server deployment)

`make docker-release` is the full multi-platform release:

```makefile
PLATFORMS := linux/amd64,linux/arm64
DOCKERHUB_IMAGE := lfnovo/open_notebook
GHCR_IMAGE      := ghcr.io/lfnovo/open-notebook

docker-push:         # version tags only (no latest), both registries, both Dockerfiles
docker-push-latest:  # also moves v1-latest / v1-latest-single
docker-release: docker-push-latest
docker-build-local:  # single-platform local build, no push
```

Two image variants: the standard multi-container `Dockerfile`, and the
single-container `Dockerfile.single` (supervisord-managed). The single image's
`supervisord.single.conf` runs all tiers in one container with priorities:

```ini
[program:surrealdb]  priority=5   command=surreal start --log trace --user root --pass <pass> rocksdb:/mydata/...
[program:api]        priority=10  command=uv run uvicorn api.main:app --host 0.0.0.0 --port 5055
[program:worker]                  command=uv run surreal-commands-worker --import-modules commands
```

`make dev` / `make full` both alias `docker compose -f docker-compose.yml up --build`
(the `.dev`/`.full` compose variants referenced historically don't ship — this
was fixed to avoid the "no such file or directory" error). `make start-all`
polls SurrealDB `/health` for up to 30s before bringing up the API + worker +
frontend, and passes `--env-file .env` so encryption keys/credentials are
visible.

---

## 8. Windows path (currently missing)

The build is **scaffolded for Windows but not a one-shot target**:

- `pyinstaller.spec` handles `windows-x86_64` arch, `.exe` binary names, the
  `webview.platforms.winforms` backend, and `CREATE_NEW_PROCESS_GROUP |
  CREATE_NO_WINDOW`.
- `bootstrap.py` and `ports.py` have Windows branches
  (`Scripts/python.exe`, `SO_REUSEADDR` fallback, etc.).
- `desktop/build/post_build_windows.ps1` exists and wraps
  `dist/Open Notebook Plus` into `Open-Notebook-Plus-windows-x64.zip` via
  `Compress-Archive`.

What's **not** present:

- No `make build-win` chain mirroring `build-mac` (no Windows test/lock/venv/
  frontend/runtimes/pyinstaller orchestration target in the `Makefile`).
- `_spawn` notes Windows process-group teardown is "future-work"; only POSIX
  `killpg` subtree kill is exercised in the launcher today.
- No signed/notarized Windows installer (MSI/NSIS) — only the `.zip` wrapper.

Recreating Windows support means adding the `build-win` Make target chain,
fetching Windows runtimes in `fetch_runtimes.py`, verifying `stop_all` uses
`taskkill /T` against the process group, and producing an installer rather than
a bare zip.
