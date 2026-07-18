# 10 — Testing Strategy & Test Cases

Exhaustive recreation reference for the Open Notebook Plus test suite. Everything
here is transcribed from the real repository at
`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus` (branch `desktop-app`).
To rebuild the project from scratch you must reproduce this layout, these runners,
and these guard conventions — the build itself refuses to run if the suite is red
(see §9, "build-gate philosophy").

---

## 1. Runners, configuration & the golden commands

### 1.1 pytest configuration (`pyproject.toml`)

```toml
# pyproject.toml  [tool.pytest.ini_options]
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["desktop/tests", "tests"]
# v0.7.129 — Custom markers. Tests marked `integration_surreal` run
# against a real SurrealDB instance (started via docker compose by
# CI) and are SKIPPED by default in local pytest runs. Run them with
# `SURREAL_INTEGRATION=1 uv run pytest -m integration_surreal`.
markers = [
    "integration_surreal: requires a live SurrealDB (skipped unless SURREAL_INTEGRATION=1)",
]
```

Key facts a recreation must preserve:

- **`asyncio_mode = "auto"`** — this is why test files write `async def test_...`
  with **no** `@pytest.mark.asyncio` decorator and it still runs. `pytest-asyncio`
  (pinned `pytest-asyncio>=1.2.0` in the `dev` dependency group; `==0.24.0` in
  `desktop/requirements.txt` for the bundle venv) collects every bare coroutine
  test automatically. Some files still carry explicit `@pytest.mark.asyncio`
  (e.g. `test_suggested_questions.py`) — that is harmless and redundant under
  auto mode.
- **`testpaths = ["desktop/tests", "tests"]`** — two independent trees:
  - `tests/` — backend suite (API, domain, graphs, utils, meta/drift guards).
  - `desktop/tests/` — the PyInstaller launcher / sidecar / provider suite.
  - `desktop/memory/tests/` — the mem0-backed memory writer/store suite.
- **Python versions differ per venv.** The repo test venv runs Python 3.14
  (`/Users/Antman/Desktop/OpenNotebook/.venv`); the *build* venv is Python 3.12
  (`.build-venv`). `pyproject.toml` declares `requires-python = ">=3.11,<3.13"`
  for the **server/Docker** artifact, which is a separate track. Tests
  themselves run on whatever `uv` resolves.

### 1.2 How to run (exact commands)

```bash
# From repo root. PYTHONPATH=. makes `api`, `open_notebook`, `commands`,
# `desktop` importable without an editable install.
PYTHONPATH=. uv run pytest                       # full suite (both testpaths)
PYTHONPATH=. uv run pytest tests/ -v             # backend only, verbose
uv run pytest tests/ -v --ignore=tests/integration   # hermetic backend (what CI + Makefile run)

# Single file / single test
uv run pytest tests/test_citation_offsets.py -v
uv run pytest tests/test_domain.py::TestNotebookDomain::test_notebook_name_validation

# Release workflow backend gate: sorted non-integration files, 30 per batch,
# 900-second timeout per batch. This is cross-platform and gives CI a useful
# failing batch rather than one unbounded pytest process.
uv run python desktop/build/run_backend_tests.py

# Real-SurrealDB integration suite (opt-in, needs a live DB on :8000)
make database                                    # docker compose up -d surrealdb
SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal
```

`tests/test_release_test_runner.py` verifies discovery excludes `tests/integration/`,
batch ordering is deterministic, and a subprocess timeout becomes a clear release
failure. `tests/test_video_overview.py` and `tests/test_video_overview_router.py`
cover caption timing, FFmpeg output validation, route containment, and the refusal
to render an Audio Overview with no timestamped transcript.

Makefile aliases (from `Makefile`):

```make
test:
	uv run pytest tests/ -v --ignore=tests/integration

test-integration:
	@echo "Running integration tests against SurrealDB at $${SURREAL_URL:-ws://localhost:8000/rpc}..."
	@echo "Tests use a throwaway namespace; your real data is not touched."
	SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal
```

### 1.3 `tests/conftest.py` — the hermetic environment contract

Every backend test runs under three global guarantees set up in
`tests/conftest.py`. A recreation MUST reproduce all three or the suite becomes
non-deterministic / makes live network calls.

1. **Auth disabled before imports.** `os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""`
   is set at the very top (before any import) so `PasswordAuthMiddleware` skips
   auth. It is set to empty string, *not* deleted, so a re-import can't resurrect it.
2. **`.env` loaded, project root on `sys.path`.**

```python
# tests/conftest.py
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""
from dotenv import load_dotenv
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
```

3. **Two autouse fixtures make the suite deterministic:**

```python
# v0.8.64 — strip web-search provider keys the developer's .env might carry,
# so the built-in web_search tool never silently binds (or makes network calls)
# during tool-loop tests. Tests that need it opt in explicitly.
_WEB_SEARCH_ENV_VARS = (
    "SERPER_API_KEY", "TAVILY_API_KEY", "SEARXNG_BASE_URL",
    "ONP_WEB_SEARCH_PROVIDER", "ONP_WEB_SEARCH_MAX_RESULTS", "ONP_WEB_SEARCH_TIMEOUT_SEC",
)

@pytest.fixture(autouse=True)
def _isolate_web_search_env(monkeypatch):
    for name in _WEB_SEARCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield

# v0.8.68 — pin network-state service to "online" so the offline gate /
# web_search short-circuit is deterministic regardless of the box's real
# connectivity and never makes a real TCP probe.
@pytest.fixture(autouse=True)
def _pin_network_state_online(monkeypatch):
    from open_notebook.health import network
    network.reset_network_state_for_tests()
    monkeypatch.setattr(network, "_probe_once", lambda: True)
    yield
    network.reset_network_state_for_tests()
```

### 1.4 The integration conftest (`tests/integration/conftest.py`)

Design goals, quoted from the file header:

- **Safe by default** — if `SURREAL_INTEGRATION` is unset, *every* test under
  `tests/integration/` is skipped at collection time.
- **Isolated** — never runs against `SURREAL_NAMESPACE=open_notebook` (real data).
  A throwaway namespace `onp_test_<short-uuid>` is minted per pytest session,
  migrated, then `REMOVE NAMESPACE`'d on teardown.
- **No new fixtures in the hot path** — it reuses the same
  `open_notebook.database.repository` pool production uses, so any SurrealQL
  regression these catch is one production can hit too.

Connection defaults: `SURREAL_URL=ws://localhost:8000/rpc`, `SURREAL_USER=root`,
`SURREAL_PASSWORD=root`. Integration files: `test_memory_recall.py`,
`test_notebook_lifecycle.py`.

---

## 2. Backend test inventory (`ls tests/`)

The `tests/` tree contains **~230 files**. There are two naming families:

- **Descriptive names** — one behaviour per file (`test_domain.py`,
  `test_graphs.py`, `test_citation_offsets.py`, `test_discover_sources.py`, …).
- **Versioned regression names** — `test_v0_7_NNN_*.py` / `test_v0_8_NN_*.py`.
  Each one pins a specific bug fix from that release so it can never regress. This
  mirrors the codebase's inline `# v0.7.NN — ...` comment convention. Examples:
  `test_v0_7_135_meta.py` (the reraise AST scanner, §7),
  `test_v0_7_140_makefile.py`, `test_v0_8_68_episode_schema_parity.py` (§8),
  `test_v0_8_39b_downloader.py`, `test_v0_8_64_web_search.py`.

Representative descriptive files, grouped by concern:

| Concern | Files |
|---|---|
| Domain models | `test_domain.py`, `test_notebook_delete_cascade.py`, `test_notebook_graph.py` |
| Models / provider API | `test_models_api.py`, `test_local_model_manifest.py`, `test_local_model_role_routing.py` |
| LangGraph workflows | `test_graphs.py`, `test_v0_7_165_state_shape_guards.py`, `test_v0_8_26_graph_node_timeouts.py` |
| Utils | `test_utils.py`, `test_chunking.py`, `test_embedding.py`, `test_citation_offsets.py` |
| Feature endpoints | `test_discover_sources.py`, `test_auto_summary.py`, `test_key_topics.py`, `test_suggested_questions.py`, `test_sources_api.py`, `test_studio_router.py`, `test_exports_router.py` |
| Podcasts | `test_podcast_length.py`, `test_podcast_path.py`, `test_podcast_suggest.py`, `test_podcast_audio_containment.py`, `test_v0_8_68_podcast_staged.py` |
| Security / encryption | `test_encryption_rotation.py`, `test_encryption_kdf_v0_7_123.py`, `test_url_validation.py`, `test_auth_timing.py`, `test_sources_path_containment_v0823.py` |
| Chat / streaming | `test_chat_stream.py`, `test_chat_history_cap.py`, `test_v0_8_65h_stream_thinking.py`, `test_source_chat_offline_fallback.py` |
| Memory (mem0) | `test_memory_recall.py`, `test_memory_writer_robustness.py`, `test_memory_batching.py`, `test_memory_retention.py`, `test_memory_confidence.py` |
| Meta / drift guards | `test_v0_7_135_meta.py`, `test_upstream_sync_guard.py`, `test_v0_8_68_episode_schema_parity.py`, `test_v0_7_140_makefile.py` |

`desktop/tests/` (launcher & sidecars, ~44 files): `test_launcher.py`,
`test_bootstrap.py`, `test_llamacpp_provider.py`, `test_mlx_provider.py`,
`test_ollama_provider.py`, `test_whisper_shim.py`, `test_piper_shim.py`,
`test_openchronicle_shim.py`, `test_next_rewrites_patcher.py`, `test_ports.py`,
`test_window_state.py`, `test_first_run.py`, `test_auto_register.py`, …

`desktop/memory/tests/`: `test_client.py`, `test_register.py`,
`test_register_guardrail.py`, `test_surreal_store.py`, `test_writer.py`.

---

## 3. Domain tests — `tests/test_domain.py`

Class-organized (`class TestNotebookDomain`, `TestSourceDomain`, `TestNoteDomain`,
`TestPodcastDomain`, `TestTransformationDomain`, `TestContentSettings`,
`TestEpisodeProfile`, `TestNoteSaveResilience`, `TestModelManager`,
`TestRecordModelSingleton`). Pydantic validation is tested without a database.

```python
class TestNotebookDomain:
    def test_notebook_name_validation(self):
        # Empty name → InvalidInputError
        with pytest.raises(InvalidInputError, match="Notebook name cannot be empty"):
            Notebook(name="", description="Test")
        # Whitespace-only name → InvalidInputError
        with pytest.raises(InvalidInputError, match="Notebook name cannot be empty"):
            Notebook(name="   ", description="Test")
        # Valid name works
        notebook = Notebook(name="Valid Name", description="Test")
        assert notebook.name == "Valid Name"

    def test_notebook_archived_flag(self):
        assert Notebook(name="Test", description="Test").archived is False
        assert Notebook(name="Test", description="Test", archived=True).archived is True
```

Delete-cascade / file-cleanup tests patch the ObjectModel base class so no DB is
touched, and monkeypatch `UPLOADS_FOLDER` to a tempdir to satisfy the path
containment check:

```python
@pytest.mark.asyncio
async def test_source_delete_cleans_up_file(self, monkeypatch):
    uploads_dir = Path(tempfile.mkdtemp())
    monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(uploads_dir))
    tmp_path = uploads_dir / "test.txt"
    tmp_path.write_bytes(b"Test content")
    source = Source(id="source:test_delete", title="Test Source",
                    asset=Asset(file_path=str(tmp_path)))
    with patch.object(Source.__bases__[0], "delete", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = True
        result = await source.delete()
        mock_delete.assert_called_once()
    assert not tmp_path.exists()          # file removed as part of cascade
```

Pattern to reproduce: **patch `Model.__bases__[0].delete`** to keep the test
hermetic while still exercising the subclass's cleanup override.

---

## 4. Domain graph test — `tests/test_notebook_graph.py`

Tests `Notebook.get_graph()` (mind-map). Sources are monkeypatched with
`SimpleNamespace`; the notebook hub node is asserted first, edge `kind` is pinned
to the SurrealDB edge-table names (`reference` for sources, `artifact` for notes),
`None` titles fall back to `"Untitled source"`, and long labels truncate to 80
chars with `…`.

```python
async def test_get_graph_builds_hub_and_spokes(monkeypatch):
    monkeypatch.setattr(Notebook, "get_sources", fake_sources)
    monkeypatch.setattr(Notebook, "get_notes", fake_notes)
    graph = await _notebook().get_graph()
    assert graph["nodes"][0] == {"id": "notebook:abc", "type": "notebook", "label": "My Notebook"}
    edges = {(e["source"], e["target"]): e["kind"] for e in graph["edges"]}
    assert edges[("notebook:abc", "source:1")] == "reference"
    assert edges[("notebook:abc", "note:1")]   == "artifact"
    assert len(graph["nodes"]) == 4 and len(graph["edges"]) == 3
```

---

## 5. Utils test — `tests/test_citation_offsets.py`

Tests `open_notebook.utils.citation_offsets.locate_passage(text, query, ...)` —
a pure function that finds the best-matching passage window in a document and
returns `{start, end, snippet}` (char offsets that never split a word).

```python
from open_notebook.utils.citation_offsets import locate_passage

def test_locates_the_matching_passage():
    m = locate_passage(TEXT, "How do neural networks learn representations?")
    assert m is not None
    assert "neural networks" in m["snippet"]
    # Offsets point at real text and don't split words.
    assert TEXT[m["start"]:m["end"]].strip() == m["snippet"]
    assert m["start"] == 0 or TEXT[m["start"] - 1].isspace()
    assert m["end"]   == len(TEXT) or TEXT[m["end"]].isspace()

def test_discriminates_between_passages():
    rag = locate_passage(TEXT, "retrieval augmented generation retriever grounding documents", window=140, stride=60)
    dl  = locate_passage(TEXT, "deep learning neural networks representations", window=140, stride=60)
    assert abs(rag["start"] - dl["start"]) > 80      # land on different regions

def test_returns_none_when_no_decent_match():
    assert locate_passage(TEXT, "quarterly revenue forecast spreadsheet pivot") is None

def test_returns_none_on_empty_inputs():
    assert locate_passage("", "anything") is None
    assert locate_passage(TEXT, "") is None
    assert locate_passage(TEXT, "the of and to is") is None   # only stopwords → no signal
```

Edge cases pinned: empty text, empty query, stopword-only query, no-match →
`None`, and `0 <= start < end <= len(text)`.

---

## 6. Feature-endpoint tests (mock-and-monkeypatch pattern)

These four are the canonical "endpoint calls out to a service; assert it degrades
safely" tests. They import the router function **directly** (not via HTTP client)
and monkeypatch the collaborating module.

### 6.1 `tests/test_podcast_length.py`

Pure mapping in `commands.podcast_staged.segments_for_length`:

```python
from commands.podcast_staged import segments_for_length

def test_segments_for_length_presets():
    assert segments_for_length("short")  == 3
    assert segments_for_length("medium") == 5
    assert segments_for_length("long")   == 8

def test_segments_for_length_normalizes_input():
    assert segments_for_length(" Long ") == 8
    assert segments_for_length("MEDIUM") == 5

def test_segments_for_length_none_or_unknown_returns_none():
    # None → caller falls back to the profile's num_segments.
    assert segments_for_length(None) is None
    assert segments_for_length("") is None
    assert segments_for_length("epic") is None
```

### 6.2 `tests/test_discover_sources.py`

Guarded web search. Monkeypatches `open_notebook.tools.web_search` and calls the
router coroutine directly. Proves: disabled when no provider, results mapped and
url-less results dropped, empty query short-circuits (never calls the provider),
and provider errors degrade to `[]` (no 500).

```python
import open_notebook.tools.web_search as ws
from api.models import DiscoverSourcesRequest
from api.routers.notebooks import discover_sources

async def test_discover_disabled_when_no_provider(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: False)
    resp = await discover_sources("notebook:1", DiscoverSourcesRequest(query="ai"))
    assert resp.enabled is False and resp.provider is None and resp.results == []

async def test_discover_degrades_to_empty_on_provider_error(monkeypatch):
    monkeypatch.setattr(ws, "web_search_enabled", lambda: True)
    monkeypatch.setattr(ws, "active_provider", lambda: "searxng")
    async def explode(query, *, max_results=None):
        raise RuntimeError("provider down")
    monkeypatch.setattr(ws, "run_web_search", explode)
    resp = await discover_sources("notebook:1", DiscoverSourcesRequest(query="ai"))
    assert resp.enabled is True and resp.results == []   # best-effort, no 500
```

### 6.3 `tests/test_auto_summary.py`

Tests `api.routers.sources._summary_preview` (whitespace collapse, 140-char
truncate with `…`) **and** the opt-in default via Pydantic field introspection:

```python
from api.routers.sources import _summary_preview
from open_notebook.domain.content_settings import ContentSettings

def test_summary_preview_truncates_long_text():
    preview = _summary_preview("word " * 100)
    assert len(preview) <= 140 and preview.endswith("…")

def test_auto_summarize_defaults_off():
    field = ContentSettings.model_fields["auto_summarize_on_ingest"]
    assert field.default is False     # ingest hook must NOT summarize unless enabled
```

### 6.4 `tests/test_key_topics.py`

Tests `open_notebook.domain.transformation.parse_topics` (bullet/number/markdown
stripping, case-insensitive de-dupe, per-topic length cap, max 8) plus the same
default-off field guard:

```python
from open_notebook.domain.transformation import parse_topics

def test_parse_topics_strips_markdown_and_dedupes():
    text = "- **Vector search**\n- vector search\n- `Embeddings`"
    assert parse_topics(text) == ["Vector search", "Embeddings"]

def test_parse_topics_drops_overlong_lines_and_caps():
    long_line = "x" * 80
    many = "\n".join(f"Topic {i}" for i in range(20))
    out = parse_topics(f"- {long_line}\n{many}")
    assert long_line not in out and len(out) <= 8

def test_auto_extract_topics_defaults_off():
    assert ContentSettings.model_fields["auto_extract_topics_on_ingest"].default is False
```

### 6.5 `tests/test_suggested_questions.py`

Corpus-grounded starter questions. The LLM is mocked via
`AsyncMock` on `provision_langchain_model`; the endpoint must strip bullets /
numbering / quotes, drop non-questions, respect `limit`, and **degrade to `[]`**
on no-sources or LLM error (so it can never block opening a notebook):

```python
def _patch_model(content):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(return_value=_FakeResp(content))
    return patch("open_notebook.ai.provision.provision_langchain_model",
                 new=AsyncMock(return_value=chain))

async def test_degrades_to_empty_on_llm_error():
    with patch("api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=nb)), \
         patch("open_notebook.ai.provision.provision_langchain_model",
               new=AsyncMock(side_effect=RuntimeError("no model configured"))):
        out = await get_suggested_questions("notebook:x", limit=4)
    assert out == {"questions": []}
```

---

## 7. The meta reraise test — `tests/test_v0_7_135_meta.py`

The single most important structural test. It is an **AST scanner** that
enforces the HTTPException-reraise convention across `api/routers/*.py`. The bug
it prevents: a generic `except Exception: raise HTTPException(500, ...)` clobbers
a typed `HTTPException(404)` raised inside the `try:` into a misleading 500.

The rule: any router-function `try/except` chain whose `except Exception` body
raises `HTTPException` **must** have an `except HTTPException: raise` clause
*before* it. Whitelist by appending `# noqa: HTTP_RAISE` to the
`except Exception:` line.

Parametrized per router file so the failure names the exact file:

```python
_ROUTERS_DIR = Path(__file__).resolve().parent.parent / "api" / "routers"

@pytest.mark.parametrize(
    "router_file",
    sorted(p for p in _ROUTERS_DIR.glob("*.py") if p.name not in _SKIP_BASENAMES),
    ids=lambda p: p.name,
)
def test_router_httpexception_reraise_enforced(router_file: Path):
    violations = _scan_file(router_file)
    if violations:
        pytest.fail(...)   # message lists file:line + fix instructions
```

Detection helpers walk the tree with `ast.walk`, matching bare `Exception`,
dotted `builtins.Exception`, tuple `except (Foo, Exception)`, and bare `except:`;
`_try_block_has_httpexception_before_generic` verifies clause ORDER (Python
matches top-to-bottom). The file also **smoke-tests its own walker** so a refactor
of the helpers can't silently disable enforcement:

```python
def test_walker_detects_synthetic_violation(tmp_path):
    src = '''
@router.get("/x")
async def buggy():
    try:
        await something()
    except Exception as e:
        raise HTTPException(500, detail=str(e))
'''
    f = tmp_path / "fake_router.py"; f.write_text(src)
    violations = _scan_file(f)
    assert len(violations) == 1 and "buggy" in violations[0][1]

def test_walker_accepts_correct_pattern(tmp_path): ...   # except HTTPException: raise first → 0
def test_walker_respects_noqa_whitelist(tmp_path): ...   # # noqa: HTTP_RAISE → 0
def test_walker_ignores_handlers_that_dont_raise_httpexception(tmp_path): ...
```

---

## 8. Drift-guard tests

Static tests that pin the code against silent, invisible drift — the class of bug
mocked unit tests structurally cannot catch.

### 8.1 `tests/test_v0_8_68_episode_schema_parity.py`

The `episode` table is **SCHEMAFULL**, so SurrealDB silently DROPS any saved model
field that lacks a `DEFINE FIELD`. This test statically pins every
`PodcastEpisode` model field to a `DEFINE FIELD` in a migration file:

```python
_MIG_DIR = _REPO / "open_notebook" / "database" / "migrations"
_BASE_FIELDS = {"id", "created", "updated"}
_DEFINE_RE = re.compile(
    r"DEFINE\s+FIELD\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON(?:\s+TABLE)?\s+episode\b",
    re.IGNORECASE)

def test_every_episode_model_field_has_a_migration_define_field():
    from open_notebook.podcasts.models import PodcastEpisode
    model_fields = set(PodcastEpisode.model_fields) - _BASE_FIELDS
    missing = sorted(model_fields - _defined_episode_fields())
    assert not missing, (f"PodcastEpisode fields {missing} have no DEFINE FIELD on the "
                         f"SCHEMAFULL `episode` table — SurrealDB will silently drop them.")

def test_down_migration_removes_what_up_defines():
    up   = (_MIG_DIR / "22.surrealql").read_text()
    down = (_MIG_DIR / "22_down.surrealql").read_text()
    assert set(_DEFINE_RE.findall(up)) == set(re.findall(
        r"REMOVE\s+FIELD\s+IF\s+EXISTS\s+(\w+)\s+ON\s+TABLE\s+episode", down, re.IGNORECASE))
```

It also checks that `generation_stage=None` survives `_prepare_save_data()` (so
clearing the stage on completion isn't a silent no-op).

### 8.2 `tests/test_upstream_sync_guard.py`

Smoke-tests `scripts/upstream_sync_guard.sh` — the tool that merges upstream
`lfnovo/open-notebook` into the Plus fork while flagging changes to
Plus-protected paths (`api/routers/studio.py`,
`open_notebook/database/migrations/*.surrealql`, `frontend/src/lib/api/sources.ts`).
It builds a throwaway git fixture with a bare "upstream" remote and asserts the
guard writes a snapshot (patch + status) *before* any remote failure, and emits a
`protected-plus-path-changes.txt` report on a real merge.

### 8.3 `tests/test_v0_7_140_makefile.py`

Guards the `make` targets against the "compose file didn't exist" class of bug
documented in the Makefile (`dev`/`full` once pointed at
`docker-compose.dev.yml` which never shipped).

---

## 9. Frontend tests — vitest

### 9.1 Config & runner

`frontend/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

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

Scripts (`frontend/package.json`):

```json
"test": "vitest run --pool=forks --maxWorkers=1",
"test:watch": "vitest",
"test:ui": "vitest --ui"
```

Commands: `npx vitest run` (ad-hoc) or `npm test` (the CI/pinned form,
forks pool, single worker — deterministic). CI runs it on **Node 22**
(`.github/workflows/test.yml`).

### 9.2 Global setup (`frontend/src/test/setup.ts`)

Loaded before every test. It imports `@testing-library/jest-dom` and installs the
mocks that virtually every component depends on: `next/navigation`
(`useRouter`/`usePathname`/`useSearchParams`), `window.matchMedia`, and the app
hooks `use-translation` (identity `t`), `use-auth`, `sidebar-store`,
`use-create-dialogs`.

```ts
import '@testing-library/jest-dom'
import { vi } from 'vitest'
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '', useSearchParams: () => new URLSearchParams(),
}))
vi.mock('../lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key, language: 'en-US', setLanguage: vi.fn() }),
}))
```

The identity `t: key => key` mock is why component tests assert on the raw i18n
key string (e.g. `screen.getByText(/chat\.citations\.sourceLabel/)`).

### 9.3 Locale-parity tests (`frontend/src/lib/locales/index.test.ts`)

Two describe blocks:

1. **Locale Parity** — flattens `en-US` to leaf keys, then for every *other*
   locale (`pt-BR`, `zh-CN`, `zh-TW`, `ja-JP`, `ru-RU`, `bn-IN`) asserts the key
   set is exactly equal — no missing, no extra:

```ts
const enKeys = getKeys(enUS)
const locales = Object.entries(resources).filter(([code]) => code !== 'en-US')
it.each(locales)('%s should have the same keys as en-US', (code, resource) => {
  const localeKeys = getKeys(resource.translation)
  expect(enKeys.filter(k => !localeKeys.includes(k)), `Missing in ${code}`).toEqual([])
  expect(localeKeys.filter(k => !enKeys.includes(k)), `Extra in ${code}`).toEqual([])
})
```

2. **Unused Key Detection** — walks every `.ts`/`.tsx` under `src/` (skipping
   `.next`, `node_modules`, locale files, test files), normalizes optional
   chaining (`t?.common?.key` → `t.common.key`), and asserts every `en-US` leaf
   key appears somewhere in the source corpus. Timeout bumped to **120 s**
   (`120_000`) for the file walk on cold-cache CI.

### 9.4 Component test pattern (`frontend/src/components/chat/CitationPill.test.tsx`)

The canonical component test. It demonstrates every convention a recreation
should follow:

- **`QueryClientProvider` wrapper factory** so hooks that read the TanStack cache
  work, and so a test can pre-seed the cache:

```tsx
function makeWrapper(queryClient?: QueryClient) {
  const qc = queryClient ?? new QueryClient()
  const Wrapper = ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  Wrapper.displayName = 'TestWrapper'
  return Wrapper
}
```

- **Mock Radix Popover** so portal+animation-gated content always renders in
  jsdom:

```tsx
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }) => React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverContent: ({ children }) => React.createElement('div', { 'data-testid': 'popover-content' }, children),
  // ...
}))
```

- **Mock the lazy-fetch hooks** (`use-sources`, `use-notes`, `use-insights`) to
  return fixed shapes so no network happens.
- **Seed the query cache** to test cache-driven rendering:

```tsx
const qc = new QueryClient()
qc.setQueryData(['mcp', 'tool-calls', 'msg-test-123'], calls)
render(<CitationPill kind="mcp" value="1" messageId="msg-test-123" />, { wrapper: makeWrapper(qc) })
expect(screen.getByText(/web_search/)).toBeInTheDocument()
```

### 9.5 Frontend test inventory (`find frontend -name '*.test.ts*'`, non-node_modules)

56 files. Highlights:

- **Components:** `chat/CitationPill.test.tsx`, `chat/McpToolPicker.test.tsx`,
  `chat/LocalModelHealthBadges.test.tsx`, `chat/SidecarLogPopover.test.tsx`,
  `chat/MessageCopyEditActions.test.tsx`,
  `chat/ChatMessage{AgentStateBadge,PrivacyBadge,ProviderBadge}.test.tsx`,
  `source/ChatPanel.cancel-run.test.tsx`, `source/ChatPanel.mcp-picker.test.tsx`,
  `source/ChatPanel.scroll.test.ts`, `source/SourceDetailContent.test.tsx`,
  `sources/SourceCard.test.tsx`, `onp/{ArtifactRail,CitationCoverageBadge,ModelFleetBadge,RunTimeline,SourceHealthPill}.test.tsx`,
  `layout/{AppSidebar,NetworkStatusBadge,SetupBanner,UpdateBanner}.test.tsx`,
  `notebooks/DirectoryPicker.test.tsx`, `common/ConfirmDialog.test.tsx`,
  `ui/virtualized-list.test.tsx`.
- **Pages:** `notebooks/components/{BulkVectorizeButton,ChatColumn,ExportNotebookDialog,ImportNotebookDialog}.test.tsx`,
  `settings/local-models/{page,DownloadPanel}.test.tsx`,
  `settings/mcp/{page,RecommendationsPanel}.test.tsx`,
  `settings/launcher-prefs/page.test.tsx`, `setup-wizard/page.test.tsx`.
- **lib:** `api/{query-client,query-client.prune,sources,studio}.test.ts`,
  `hooks/{chat-race-guard,use-deep-health,use-modal-manager,use-sources,use-studio,use-translation}.test.*`,
  `utils/{citations,error-handler,source-context}.test.ts`,
  `{config,features}.test.ts`, `locales/index.test.ts`.
- **Root:** `frontend/start-server-utils.test.ts`.

### 9.6 Type/build gates

Separate from vitest, the CI + local gate also requires:

```bash
npx tsc --noEmit     # type gate (no emit, pure check)
npm run build        # Next.js production build (webpack) — see doc 11
```

---

## 10. Build-gate philosophy — tests are a precondition for `build-mac`

The desktop build refuses to start unless the entire test gate is green. From the
`Makefile`, `build-mac` runs `build-mac-test` as its **very first** dependency
(Stage 0):

```make
build-mac: build-mac-test build-mac-lock build-mac-venv build-mac-frontend build-mac-runtimes build-mac-pyinstaller build-mac-dmg

# Stage 0: precondition — fast unit suite. Catches regressions before we
# spend 15+ min on a build that's going to be DOA.
build-mac-test:
	@echo "🧪 Running unit tests (precondition for build-mac)…"
	# v0.8.66 (audit I-M1) — DON'T pipe to `tail`: a piped recipe's exit status
	# is the LAST command's (tail, always 0), so a failing suite could NOT fail
	# the build. Run pytest directly so its non-zero exit aborts `build-mac`.
	@/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q
	@echo "🧪 Running backend tests (precondition for build-mac)…"
	@uv run pytest tests/ -q --ignore=tests/integration
```

Two hard-won lessons encoded here (both are recreation-critical):

1. **Never pipe pytest to `tail`.** A piped recipe's exit status is the *last*
   command's — `tail` always exits 0 — so a failing suite would not fail the
   build. The "Stage 0 precondition" was toothless until this was fixed
   (v0.8.66, audit I-M1). Run pytest directly.
2. **Gate BOTH trees.** Originally only `desktop/tests/` ran, so a regression in
   `api/` or `open_notebook/` could ship in a build with zero coverage. Since
   v0.8.67k the backend suite (`uv run pytest tests/`) is also a precondition.
   Integration tests stay excluded (they need a live SurrealDB).

The desktop-launcher suite runs under the **test venv** (Python 3.14), and the
backend suite runs via `uv run` (Python 3.12), matching how `make test` runs.
Result: if any unit test fails, the ~15-minute PyInstaller build never starts.
CI enforces the same signal separately via `.github/workflows/test.yml` (backend,
integration-surreal, frontend jobs) on every push/PR to `main` and `desktop-app`.
```
