# 10 — Testing Strategy & Test Cases

Exhaustive recreation reference for the Open Notebook Plus test suites.
All file paths are repo-relative to `/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`.

> **Secrets note:** every `<...>` placeholder below stands in for a value
> that must never be committed (API keys, passwords, encryption keys). The
> real suite reads these from `.env` and immediately strips/neutralizes the
> network-sensitive ones (see `conftest.py`).

---

## 1. Layers at a glance

| Layer | Tool | Location | Count (approx) | Runner |
|-------|------|----------|----------------|--------|
| Backend hermetic | pytest | `tests/` (minus `tests/integration/`) | ~1,668 test fns across 207 files | `uv run pytest tests/ --ignore=tests/integration` |
| Backend integration | pytest | `tests/integration/` | 2 modules (lifecycle, memory recall) | `SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -m integration_surreal` |
| Desktop launcher/bootstrap | pytest | `desktop/tests/`, `desktop/memory/tests/` | 43 modules | `.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q` |
| Frontend unit/component | vitest | `frontend/src/**/*.test.ts(x)` | 36 files, 203 tests | `npm test -- --run` (`vitest run --pool=forks --maxWorkers=1`) |
| Frontend type-check | Next.js build | `frontend/` | n/a | `npm run build` runs the TypeScript step |

Tool/runtime versions (from `pyproject.toml`, `frontend/package.json`,
`desktop/requirements.txt`):

```
# pyproject.toml
requires-python = ">=3.11,<3.13"
pytest>=9.0.3
pytest-asyncio>=1.2.0
fastapi>=0.136.3
starlette>=1.2.1
pydantic>=2.9.2
langgraph>=1.0.10
surrealdb>=1.0.4
surreal-commands>=1.3.1,<2
esperanto>=2.20.0,<3
loguru>=0.7.2

# frontend/package.json
next ^16.2.3   react ^19.2.3   typescript ^5   vitest ^4.1.8

# desktop/requirements.txt
pywebview==5.4   pyinstaller>=6.13.0,<7   aiohttp>=3.11.18,<4
llama-cpp-python[server]>=0.3.16,<0.4
```

Note the **three distinct Python interpreters** in play, which matters for
running the suites consistently:

- **Repo `.venv` (project tooling, py3.12)** — used by `make test` via `uv run`.
- **`.venv-py312`** — the runtime venv referenced in the build/precondition
  flows: `.venv-py312/bin/python -m pytest tests/ --ignore=tests/integration`.
- **`.venv` desktop test interpreter** — `make build-mac-test` runs
  `desktop/tests/` with `/Users/Antman/Desktop/OpenNotebook/.venv/bin/python`.

---

## 2. How the backend suite runs

### 2.1 Make target (`Makefile`)

```makefile
test:
	uv run pytest tests/ -v --ignore=tests/integration

test-integration:
	@echo "Running integration tests against SurrealDB at $${SURREAL_URL:-ws://localhost:8000/rpc}..."
	@echo "Tests use a throwaway namespace; your real data is not touched."
	SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal
```

The hermetic suite is the default and **must not need external services** —
no live SurrealDB, no network, no real provider keys. The `--ignore=tests/integration`
flag (and, redundantly, the collection-time skip gate in
`tests/integration/conftest.py`) keeps the SurrealDB-backed tests out unless
explicitly opted in.

### 2.2 Root `conftest.py` (`tests/conftest.py`)

Three responsibilities, all executed before any test imports run:

1. **Disable password auth** so middleware is a no-op during tests:

```python
# tests/conftest.py:17
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""
```

2. **Load `.env`** for DB URLs / encryption keys, then add the project root
   to `sys.path` so `api` and `open_notebook` import cleanly.

3. **Two autouse fixtures that make the suite deterministic regardless of the
   developer's `.env` and the machine's actual connectivity:**

```python
# tests/conftest.py — strip real web-search keys so the chat tool loop
# never silently binds web_search (network call + changed tool-loop tests).
_WEB_SEARCH_ENV_VARS = (
    "SERPER_API_KEY", "TAVILY_API_KEY", "SEARXNG_BASE_URL",
    "ONP_WEB_SEARCH_PROVIDER", "ONP_WEB_SEARCH_MAX_RESULTS",
    "ONP_WEB_SEARCH_TIMEOUT_SEC",
)

@pytest.fixture(autouse=True)
def _isolate_web_search_env(monkeypatch):
    for name in _WEB_SEARCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
```

```python
# v0.8.68 — PIN the network-state service to "online" for EVERY test so the
# suite is deterministic and never makes the real TCP probe.
@pytest.fixture(autouse=True)
def _pin_network_state_online(monkeypatch):
    from open_notebook.health import network
    network.reset_network_state_for_tests()
    monkeypatch.setattr(network, "_probe_once", lambda: True)
    yield
    network.reset_network_state_for_tests()
```

The **network probe pinned online** convention is the crux: offline-mode tests
opt out explicitly by monkeypatching `get_network_state_with_settings` /
`_probe_once` (see `tests/test_offline_gate.py`,
`tests/test_web_search_offline.py`).

### 2.3 SurrealDB mocking in hermetic tests

Hermetic tests never touch SurrealDB. They mock the repository layer
(`open_notebook.database.repository.repo_query`, `repo_create`, `repo_upsert`,
…) with `unittest.mock` / `AsyncMock`, or they exercise pure functions
(classifiers, chunkers, context builders, state-shape guards). The episode
schema-parity test (§6.1) is a good example of a DB-shape guard that reads the
migration `.surrealql` files statically rather than connecting.

### 2.4 pytest markers (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
markers = [
  "integration_surreal: requires a live SurrealDB (skipped unless SURREAL_INTEGRATION=1)",
]
```

---

## 3. The integration suite (`tests/integration/`)

Opt-in, real-SurrealDB tests. The conftest enforces three invariants
(`tests/integration/conftest.py`):

1. **Safe by default** — `pytest_collection_modifyitems` skips every item under
   `tests/integration/` at collection time unless `SURREAL_INTEGRATION` is
   truthy, so a plain `uv run pytest` never connects.

2. **Namespace isolation** — a per-session throwaway namespace/database
   `onp_test_<short-uuid>` is minted, env vars are patched **before** importing
   the repo pool, migrations run against it, and `REMOVE NAMESPACE IF EXISTS`
   cascades-cleans on teardown:

```python
# tests/integration/conftest.py:148
short = uuid.uuid4().hex[:8]
ns = f"onp_test_{short}"
db = f"onp_test_{short}"
...
os.environ["SURREAL_NAMESPACE"] = ns
os.environ["SURREAL_DATABASE"] = db
from open_notebook.database import repository as repo_mod
from open_notebook.database.async_migrate import AsyncMigrationManager
await repo_mod.close_pool()          # idempotent
...
manager = AsyncMigrationManager()
await manager.run_migration_up()     # same path as API startup
yield meta
...
await cleanup.query(f"REMOVE NAMESPACE IF EXISTS {ns};")
```

3. **Same hot path as production** — the fixture sets env vars and reuses the
   production `repository` pool, so any SurrealQL regression caught here is one
   production can hit too.

`clean_namespace` (function-scoped) truncates user-data tables between tests
via **dynamic table discovery** (`INFO FOR DB;`) rather than a stale hardcoded
list, protecting `_`-prefixed system tables (esp. `_sbl_migrations`):

```python
# tests/integration/conftest.py:263
_PROTECTED_TABLE_PREFIXES = ("_",)
_PROTECTED_TABLE_NAMES = frozenset({"_sbl_migrations"})
```

Connection defaults: `SURREAL_URL=ws://localhost:8000/rpc`,
`SURREAL_USER=root`, `SURREAL_PASSWORD=<root-or-env>`.

---

## 4. The version-anchored test convention (`test_v0_X_NN.py`)

The dominant naming pattern in `tests/` is `test_v0_<minor>_<patch>[ _slug ].py`.
Each file pins the behavior of the fix/feature that shipped in that exact
version, so a regression that re-breaks the old bug fails in a file whose name
points straight at the originating change. Examples present on disk:

```
tests/test_v0_7_141_bootstrap.py            # venv bootstrap lock-hash + critical-import guard
tests/test_v0_7_171_checkpoint_cleanup.py   # langgraph checkpoint prune on delete
tests/test_v0_7_188_desktop_reliability.py  # _wait_tcp/_wait_http early-exit on dead child
tests/test_v0_8_56_tool_loop_outcome.py     # chat tool-loop outcome shape
tests/test_v0_8_64_web_search.py            # opt-in web_search behavior
tests/test_v0_8_68_episode_schema_parity.py # SCHEMAFULL episode field parity
tests/test_v0_8_68_chat_session_delete_cascade.py  # delete cascade completeness
```

The convention coexists with **feature-named files** for cross-cutting concerns
(`test_domain.py`, `test_graphs.py`, `test_chunking.py`, `test_embedding.py`,
`test_memory_recall.py`, `test_chat_stream.py`, `test_encryption_rotation.py`,
…). New behavior gets a version-anchored file; new modules get a feature file.

There are also `_meta` / `_audit_sweep` files (`test_v0_7_135_meta.py`,
`test_v0_7_177_audit_sweep.py`, `test_v0_7_201_audit_sweep.py`, …) that scan the
source tree for anti-patterns the codebase has been bitten by (e.g. `str(e)`
leakage, silent exception swallowing, `NotFoundError` misuse) — these are
**static guard tests** described in §6.

---

## 5. Representative test examples per layer

### 5.1 Pure-function classifier (backend)

`open_notebook/utils/error_classifier.py` is tested by feeding raw exception
strings and asserting the `(ExceptionClass, user_message)` tuple. A faithful
recreation:

```python
import pytest
from open_notebook.exceptions import (
    AuthenticationError, RateLimitError, NetworkError, ExternalServiceError,
)
from open_notebook.utils.error_classifier import classify_error

@pytest.mark.parametrize("raw, exc_cls", [
    (Exception("Error 401: invalid_api_key"), AuthenticationError),
    (Exception("429 Too Many Requests"),      RateLimitError),
    (Exception("Connection refused"),         NetworkError),
    (Exception("model is loading, not ready"), ExternalServiceError),
    (Exception("context_length_exceeded"),    ExternalServiceError),
])
def test_classify_error_maps_keywords(raw, exc_cls):
    cls, msg = classify_error(raw)
    assert cls is exc_cls
    assert isinstance(msg, str) and msg
```

### 5.2 LangGraph state-shape guard (backend)

The codebase repeatedly hits LangGraph nodes returning either a `dict` or a
Pydantic object. Guards accept both via `getattr` fallback (see
`tests/test_v0_7_165_state_shape_guards.py`,
`tests/test_v0_7_199_search_ask_state_shape.py`). Pattern:

```python
def _msgs(output):
    # accept dict OR pydantic state
    return output["messages"] if isinstance(output, dict) \
        else getattr(output, "messages", [])

def test_chat_output_shape_is_tolerant():
    class PydState:  # simulate a pydantic state object
        messages = ["hi"]
    assert _msgs({"messages": ["hi"]}) == ["hi"]
    assert _msgs(PydState()) == ["hi"]
```

### 5.3 SSE stream disconnect (backend)

`tests/test_chat_stream.py` exercises the streaming generator in
`api/routers/chat.py`. The load-bearing behavior under test
(`api/routers/chat.py:1202`):

```python
async for event in _chat_graph_async.astream_events(...):
    if await fastapi_request.is_disconnected():
        logger.info("chat stream: client disconnected ... halting")
        # fire memory-extract only if the turn already completed
        if final_result and "messages" in final_result:
            ...
        return
```

A recreation mocks `fastapi_request.is_disconnected` to flip True mid-stream
and asserts the generator returns early (no further tokens emitted, no
half-turn memory extraction).

### 5.4 surreal-commands retry semantics (backend)

`commands/*.py` declare retry policy on the `@command` decorator. The contract
under test: **`ValueError` (and `ConfigurationError`) are permanent** —
everything else retries.

```python
# commands/embedding_commands.py:138
@command(
    "embed_note", app="open_notebook",
    retry={
        "max_attempts": 5,
        "wait_strategy": "exponential_jitter",
        "stop_on": [ValueError, ConfigurationError],  # don't retry validation/config
    },
)

# commands/podcast_commands.py:199 — episodes use max_attempts=1 (no dup records)
@command("generate_podcast", app="open_notebook", retry={"max_attempts": 1})
```

Tests assert `stop_on` includes `ValueError`, and that podcast commands pin
`max_attempts: 1` (a timeout is re-raised as `asyncio.TimeoutError`, **not**
`ValueError`, precisely so it isn't treated as permanent —
`commands/podcast_commands.py:410`).

### 5.5 Frontend component test (vitest + jsdom)

Setup (`frontend/vitest.config.ts`):

```ts
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    alias: { '@': path.resolve(__dirname, './src') },
  },
})
```

Component tests mock hooks via `vi.fn()` and assert render + interaction.
Representative files: `ChatMessageProviderBadge.test.tsx`,
`NetworkStatusBadge.test.tsx`, `SidecarLogPopover.test.tsx`,
`McpToolPicker.test.tsx`, `DownloadPanel.test.tsx`.

### 5.6 Frontend static-guard test (vitest, no DOM)

`frontend/src/lib/utils/error-handler.test.ts` walks source files and pins an
invariant: no hook may pass the raw i18n **key** to a `description:` field.

```ts
// frontend/src/lib/utils/error-handler.test.ts
const HOOKS_ROOT = join(__dirname, '..', 'hooks')
function walkTsFiles(dir, out = []) {
  for (const name of readdirSync(dir)) { /* recurse .ts/.tsx, skip *.test.* */ }
  return out
}
// asserts no `getApiErrorKey(` is used directly on a `description:` field
```

### 5.7 Desktop bootstrap test (pytest)

`desktop/tests/test_v0_7_141_bootstrap.py` and `desktop/tests/test_bootstrap.py`
cover the lock-hash / critical-import logic in `desktop/bootstrap.py`. Recreation:

```python
from pathlib import Path
from desktop import bootstrap

def test_is_venv_current_keys_off_lock_hash(tmp_path, monkeypatch):
    lock = tmp_path / "requirements.lock"
    lock.write_text("fastapi==0.136.3\n")
    # no venv → not current
    assert bootstrap.is_venv_current(lock) is False
    # marker matching the lock hash → current
    monkeypatch.setattr(bootstrap, "venv_python", lambda: _existing_python(tmp_path))
    bootstrap.venv_marker().write_text(bootstrap._lock_hash(lock))
    assert bootstrap.is_venv_current(lock) is True
```

The real suite also verifies `_verify_critical_imports` returns the missing-module
list (the `prometheus_client` / `llama_cpp` regressions) and that a non-zero
`uv pip install` raises with the tail of `bootstrap-subprocess.log`.

### 5.8 Desktop launcher reliability test (pytest)

`desktop/tests/test_launcher.py`, `test_launcher_startup_timeout.py`,
`test_v0_7_173_process_group.py`, `test_v0_8_68_launch_race.py`. They mock
`subprocess.Popen` (often `MagicMock(spec=Popen)`) and assert:

- `_wait_tcp` / `_wait_http` raise immediately when `proc.poll()` is non-None
  (dead-child early exit, `desktop/launcher.py:84` / `:119`).
- `_spawn` sets `start_new_session=True` (POSIX) so `stop_all` can `killpg` the
  whole subtree.
- `_wait_http(..., consecutive=N, follow_redirects=True)` requires N
  consecutive `<500` hits before returning (the launch-race fix).

---

## 6. Schema-parity / upgrade-guard test patterns

These static tests catch a whole class of "looks-saved-but-silently-dropped"
and "old-bug-reintroduced" regressions without a live DB.

### 6.1 SCHEMAFULL field parity (`tests/test_v0_8_68_episode_schema_parity.py`)

Because the `episode` table is SCHEMAFULL, SurrealDB drops any saved field that
lacks a `DEFINE FIELD`. The guard pins every `PodcastEpisode` model field to a
migration `DEFINE FIELD`:

```python
_DEFINE_RE = re.compile(
    r"DEFINE\s+FIELD\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON(?:\s+TABLE)?\s+episode\b",
    re.IGNORECASE,
)

def test_every_episode_model_field_has_a_migration_define_field():
    from open_notebook.podcasts.models import PodcastEpisode
    model_fields = set(PodcastEpisode.model_fields) - {"id", "created", "updated"}
    defined = _defined_episode_fields()         # scans *.surrealql, skips *_down
    missing = sorted(model_fields - defined)
    assert not missing, (
        f"PodcastEpisode fields {missing} have no DEFINE FIELD on the SCHEMAFULL "
        f"`episode` table — SurrealDB will silently drop them on save."
    )

def test_down_migration_removes_what_up_defines():
    up = (_MIG_DIR / "22.surrealql").read_text()
    down = (_MIG_DIR / "22_down.surrealql").read_text()
    up_fields = set(_DEFINE_RE.findall(up))
    down_fields = set(re.findall(
        r"REMOVE\s+FIELD\s+IF\s+EXISTS\s+(\w+)\s+ON\s+TABLE\s+episode", down, re.I))
    assert up_fields == down_fields   # up/down symmetry
```

This is the template for **any new SCHEMAFULL table**: parse `model_fields`,
parse the migration `DEFINE FIELD`s, assert the set difference is empty, and
assert up/down symmetry.

### 6.2 Migration discovery / idempotency

`tests/test_migration_discovery.py` and `tests/test_v0_7_176_migration_idempotency.py`
assert migrations are discovered in order, are forward-only, and that
`IF NOT EXISTS` / `IF EXISTS` guards make re-running a migration a no-op (the
integration conftest relies on this when reusing a session namespace).

### 6.3 Audit-sweep / upgrade-guard scans

`test_v0_7_168_no_str_e_leakage.py`, `test_v0_7_179_notfound_sweep.py`,
`test_v0_8_28_silent_swallow_sweep.py`, and the `*_audit_sweep.py` family grep
the source tree for forbidden patterns (raw `str(e)` in HTTP detail, bare
`except: pass` over critical paths, inverted edge-table direction) and fail with
file:line pointers. They are the codebase's enforcement of the standing
"find-and-fix" workflow.

### 6.4 Delete-cascade completeness

`tests/test_v0_8_68_chat_session_delete_cascade.py` and
`tests/test_v0_8_48_notebook_delete_checkpoint_cleanup.py` assert that deleting
a domain object also removes its edges (`reference`, `artifact`, `refers_to`)
and its LangGraph SQLite checkpoint rows — the recurring "missing delete
cascade" gotcha.

---

## 7. Running everything (recreation checklist)

```bash
# Backend hermetic (default; no services needed)
uv run pytest tests/ -v --ignore=tests/integration
# or with the runtime venv:
.venv-py312/bin/python -m pytest tests/ --ignore=tests/integration

# Backend integration (needs SurrealDB up: make database)
SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal

# Desktop launcher / bootstrap / memory
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q

# Frontend unit/component (203 tests) + production build/type-check
cd frontend && npm test -- --run      # vitest run --pool=forks --maxWorkers=1
cd frontend && npm run build          # Next.js compile + TypeScript step
```

The macOS build runs the desktop suite **and** the backend hermetic suite as a
Stage-0 precondition (`make build-mac-test`); see doc 11 §2.
