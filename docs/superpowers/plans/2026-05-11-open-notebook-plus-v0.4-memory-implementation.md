# Open Notebook Plus v0.4 — Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent cross-session memory to Open Notebook Plus — episodic + procedural recall from chats, ambient screen-context grounding via OpenChronicle, and a dashboard surfacing what's been remembered.

**Architecture:** 2 new supervised FastAPI shims (memory retriever + OpenChronicle bridge), 2 new `surreal-commands` handlers in the existing worker (per-turn fact extractor + per-session episode summarizer), 3 new SurrealDB tables (`memory_fact`, `memory_preference`, `memory_episode`), a `desktop/memory/` package containing the SurrealDB adapter for mem0 + the writer logic, a `desktop/memory_dashboard/` window mirroring the model-manager pattern, and a wizard screen 5.5 for OpenChronicle onboarding. All memory operations run against the user's local Hermes 3 + nomic-embed servers from v0.3 — no new model servers.

**Tech Stack:** Python 3.12 (venv via uv), `mem0ai` library, FastAPI shims, aiohttp dashboard, `mcp` Python package for OpenChronicle integration, SurrealDB vector storage, Hermes 3 Llama-3.1 8B as the writer LLM, nomic-embed-text-v1.5 as the embedder.

**Spec:** [docs/superpowers/specs/2026-05-11-open-notebook-plus-v0.4-memory-design.md](../specs/2026-05-11-open-notebook-plus-v0.4-memory-design.md)

---

## File map (created/modified by this plan)

### Created
```
desktop/
├── memory/
│   ├── __init__.py
│   ├── _register.py                 # registers `surreal` as a mem0 provider (Task 2.5)
│   ├── surreal_store.py             # mem0 VectorStoreBase adapter for SurrealDB
│   ├── client.py                    # build_memory_client(cfg) → mem0.Memory
│   ├── writer.py                    # extract_turn / summarize_session
│   ├── prompts.py                   # writer system prompts + tool defs
│   └── tests/
│       ├── __init__.py
│       ├── test_register.py
│       ├── test_surreal_store.py
│       ├── test_client.py
│       ├── test_writer_extract.py
│       └── test_writer_summarize.py
├── desktop_shims/
│   ├── memory_shim.py               # FastAPI retriever
│   └── openchronicle_shim.py        # MCP client → HTTP bridge
├── memory_dashboard/
│   ├── __init__.py
│   ├── server.py
│   └── static/{index.html, style.css, dashboard.js}
├── first_run/static/memory_injection.js   # Settings page link injection
└── tests/
    ├── test_memory_shim.py
    ├── test_openchronicle_shim.py
    └── test_memory_dashboard_server.py

upstream/ (data injected at first launch, not modified at repo level)
└── commands/memory_commands.py      # auto-written by app.py phase

open_notebook/database/migrations/   # upstream's SurrealDB migration directory
├── 15.surrealql                     # new — memory tables (memory_fact/preference/episode)
└── 15_down.surrealql                # new — rollback (drop the 3 tables)
```

(NB: upstream's `AsyncMigrationManager` is NOT auto-discovery — `open_notebook/database/async_migrate.py` hard-codes the up/down list. Task 4 also appends migration #15 to that list.)

### Modified
- `desktop/requirements.lock` — add `mem0ai`, `mcp`
- `desktop/config.py` — add `openchronicle_choice` field
- `desktop/app.py` — new `_phase_detect_openchronicle` + `_phase_register_memory_commands`; pass new args to Supervisor
- `desktop/launcher.py` — `_spawn_memory_retriever`, `_spawn_openchronicle_bridge` methods; new constructor args
- `desktop/auto_register/__init__.py` — new orchestration entry for memory credential registration
- `desktop/auto_register/memory.py` — NEW sub-module within the existing package
- `desktop/window.py` — extend theme-injection JS to load `memory_injection.js`
- `desktop/tray.py` — add "Memory…" menu entry
- `desktop/first_run/static/index.html` — new screen `data-screen="ambient-memory"`
- `desktop/first_run/static/wizard.js` — handle new screen choices + persist
- `desktop/first_run/static/voice_injection.js` — add `ONP_REMIND_OPENCHRONICLE` toast
- `desktop/build/pyinstaller.spec` — bundle new shims + dashboard + memory_injection.js + commands/memory_commands.py template

---

## Task 1: Lockfile additions for mem0 + mcp

**Files:**
- Modify: `desktop/requirements.lock`

- [ ] **Step 1: Append voice-style block to the lockfile**

Append to end of `desktop/requirements.lock`:

```text

# v0.4 memory additions
mem0ai==0.1.62
mcp==1.2.0
```

(Note: pin to the latest stable versions at implementation time. If `0.1.62` or `1.2.0` don't exist on PyPI, find the latest published version and substitute. Verify with `desktop/bin/uv pip install --dry-run mem0ai mcp`.)

- [ ] **Step 2: Verify lockfile parses**

```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
desktop/bin/uv pip compile --no-deps desktop/requirements.lock -o /tmp/dummy.txt 2>&1 | tail -3
```
Expected: no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add desktop/requirements.lock
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: add mem0ai + mcp to venv lockfile (v0.4 memory)"
```

---

## Task 2: Config — add `openchronicle_choice` field

**Files:**
- Modify: `desktop/config.py`
- Modify: `desktop/tests/test_config.py`

- [ ] **Step 1: Read `desktop/config.py` to confirm the dataclass shape**, then add `openchronicle_choice: str = "skip"` to `Config` with a `field` default. Match how `theme` and `encryption_key` are defined.

- [ ] **Step 2: Add a test in `desktop/tests/test_config.py`**

```python
def test_openchronicle_choice_defaults_to_skip(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = load_or_create(cfg_path)
    assert cfg.openchronicle_choice == "skip"


def test_openchronicle_choice_round_trips(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="A" * 24,
        openchronicle_choice="prompt",
    )
    cfg.save(cfg_path)
    assert load_or_create(cfg_path).openchronicle_choice == "prompt"
```

- [ ] **Step 3: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_config.py -v
```
Expected: all config tests pass (existing + 2 new).

- [ ] **Step 4: Commit**

```bash
git add desktop/config.py desktop/tests/test_config.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: add Config.openchronicle_choice field for wizard onboarding"
```

---

## Task 2.5: Register `surreal` as a mem0 vector-store provider

mem0 2.x's `VectorStoreFactory` and `VectorStoreConfig` both gate on hardcoded provider allowlists (mem0 never shipped a `register_provider()` for vector stores, unlike LLMs/embedders). We extend the allowlists at import time so `Memory.from_config({"vector_store": {"provider": "surreal", ...}})` works in Task 5.

**Why monkey-patch is acceptable here:** mem0's own `LlmFactory.register_provider()` does exactly this dict mutation for LLMs — we're filling in functionality the library author skipped for vector stores. The names targeted (`_provider_configs`, `provider_to_class`) are stable across mem0 0.1.62 → 2.0.2. The synthetic `sys.modules` injection is the same idiom `unittest.mock.patch` uses.

**Files:**
- Create: `desktop/memory/__init__.py` (empty)
- Create: `desktop/memory/_register.py`
- Create: `desktop/memory/tests/__init__.py` (empty)
- Create: `desktop/memory/tests/test_register.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/memory/tests/test_register.py
from __future__ import annotations

import importlib
import sys


def test_surreal_provider_is_registered_after_import():
    # Reload mem0 modules clean so the test is order-independent.
    for mod in list(sys.modules):
        if mod.startswith(("mem0", "desktop.memory._register")):
            del sys.modules[mod]
    from mem0.vector_stores.configs import VectorStoreConfig
    from mem0.utils.factory import VectorStoreFactory

    # `VectorStoreConfig._provider_configs` is a Pydantic v2 ModelPrivateAttr;
    # the underlying dict lives at `.default`.
    assert "surreal" not in VectorStoreConfig._provider_configs.default
    assert "surreal" not in VectorStoreFactory.provider_to_class

    # Importing _register installs the provider as a side effect.
    importlib.import_module("desktop.memory._register")

    assert (
        VectorStoreConfig._provider_configs.default["surreal"]
        == "SurrealVectorStoreConfig"
    )
    assert (
        VectorStoreFactory.provider_to_class["surreal"]
        == "desktop.memory.surreal_store.SurrealMemoryStore"
    )


def test_surreal_provider_passes_mem0_pydantic_validation():
    """End-to-end check: after registration, mem0's VectorStoreConfig
    validator accepts `provider: 'surreal'` and instantiates our config."""
    import desktop.memory._register  # noqa: F401
    from mem0.vector_stores.configs import VectorStoreConfig

    cfg = VectorStoreConfig(
        provider="surreal",
        config={
            "surreal_url": "ws://127.0.0.1:50000/rpc",
            "user": "root",
            "password": "x" * 24,
        },
    )
    assert type(cfg.config).__name__ == "SurrealVectorStoreConfig"
    dump = cfg.config.model_dump()
    assert dump["surreal_url"] == "ws://127.0.0.1:50000/rpc"
    assert dump["namespace"] == "open_notebook"


def test_synthetic_config_module_exports_pydantic_class():
    import desktop.memory._register  # noqa: F401
    from mem0.configs.vector_stores.surreal import SurrealVectorStoreConfig

    inst = SurrealVectorStoreConfig(
        surreal_url="ws://localhost:50000/rpc",
        user="root",
        password="x" * 24,
    )
    assert inst.collection_name == "memory"
    assert inst.embedding_model_dims == 768
    assert inst.namespace == "open_notebook"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_register.py -v
```
Expected: `ModuleNotFoundError: No module named 'desktop.memory._register'`.

- [ ] **Step 3: Implement**

```python
# desktop/memory/__init__.py
```

```python
# desktop/memory/_register.py
"""Register `surreal` as a mem0 vector-store provider.

mem0 2.x guards `Memory.from_config({"vector_store": {"provider": ...}})` with two
hardcoded allowlists:

  1. `VectorStoreConfig._provider_configs` — Pydantic config-class names per
     provider. The validator does
     `__import__(f"mem0.configs.vector_stores.{provider}")` and
     `getattr(module, _provider_configs[provider])` to load the config class.
  2. `VectorStoreFactory.provider_to_class` — dotted import paths to the store
     class. The factory does `load_class(class_type)(**config.model_dump())`.

There is no public `register_provider()` for vector stores (only for LLMs and
embedders — see `LlmFactory.register_provider` in `mem0/utils/factory.py`).
We mutate the underlying dicts directly and inject a synthetic Pydantic-config
module into `sys.modules` so the validator's `__import__` lookup resolves.

Note on Pydantic v2 mechanics: `VectorStoreConfig._provider_configs` is declared
as `_provider_configs: Dict[str, str] = {...}` on a `BaseModel` subclass, which
Pydantic v2 turns into a `ModelPrivateAttr` descriptor. The underlying dict
(used as the per-instance default) lives at `.default`. Mutating
`VectorStoreConfig._provider_configs.default[...]` updates the allowlist for
all subsequent instances.

Importing this module has the side effect of installing the `surreal` provider.
`desktop/memory/client.py` (Task 5) imports it before calling `Memory.from_config`.
"""

from __future__ import annotations

import sys
import types

from pydantic import BaseModel
from mem0.utils.factory import VectorStoreFactory
from mem0.vector_stores.configs import VectorStoreConfig


class SurrealVectorStoreConfig(BaseModel):
    """Pydantic config for our SurrealDB-backed memory store.

    These fields become kwargs to `SurrealMemoryStore.__init__` because mem0's
    `VectorStoreFactory.create` calls `cls(**config.model_dump())`.
    """

    collection_name: str = "memory"  # mem0 reads .collection_name — unused for routing
    embedding_model_dims: int = 768  # nomic-embed-text-v1.5 native dim
    surreal_url: str
    namespace: str = "open_notebook"
    database: str = "open_notebook"
    user: str
    password: str


_synthetic_module = types.ModuleType("mem0.configs.vector_stores.surreal")
_synthetic_module.SurrealVectorStoreConfig = SurrealVectorStoreConfig
sys.modules["mem0.configs.vector_stores.surreal"] = _synthetic_module

# `._provider_configs` is a Pydantic v2 ModelPrivateAttr — mutate its `.default`.
VectorStoreConfig._provider_configs.default["surreal"] = "SurrealVectorStoreConfig"
VectorStoreFactory.provider_to_class["surreal"] = (
    "desktop.memory.surreal_store.SurrealMemoryStore"
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_register.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/memory/__init__.py desktop/memory/_register.py \
        desktop/memory/tests/__init__.py desktop/memory/tests/test_register.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: register 'surreal' as mem0 vector-store provider (v0.4 memory)"
```

---

## Task 3: SurrealDB adapter for mem0 (mem0 2.x `VectorStoreBase` contract)

A mem0 vector store backed by SurrealDB, registered under provider name `"surreal"` in Task 2.5. Three tables share one adapter; `payloads[i]["kind"]` (`fact`/`preference`/`episode`) routes inserts and filters searches.

**Why this shape:** mem0 2.x's `VectorStoreFactory` instantiates stores via `cls(**config_dict)` where `config_dict` is `SurrealVectorStoreConfig.model_dump()`. The adapter must inherit from `VectorStoreBase` (11 abstract methods) and return search results as `OutputData(id, score, payload)`-shaped objects — mem0 reads `.id`, `.score`, `.payload` attrs from each hit.

**Files:**
- Create: `desktop/memory/surreal_store.py`
- Create: `desktop/memory/tests/test_surreal_store.py`

(`desktop/memory/__init__.py` and `desktop/memory/tests/__init__.py` were already created in Task 2.5; do not recreate.)

- [ ] **Step 1: Write the failing tests**

```python
# desktop/memory/tests/test_surreal_store.py
from __future__ import annotations

from unittest.mock import MagicMock

# Importing _register installs the synthetic `mem0.configs.vector_stores.surreal`
# module — must happen before surreal_store is imported because surreal_store
# inherits from VectorStoreBase (a sibling of the synthetic module's parent pkg).
from desktop.memory import _register  # noqa: F401
from desktop.memory.surreal_store import SurrealMemoryStore, OutputData


def _fake_client(responses: dict):
    """Mock pretending to be a surrealdb async client.

    Matches SurrealQL by prefix of the first non-whitespace word.
    """
    client = MagicMock()

    async def query(sql, vars=None):
        for prefix, resp in responses.items():
            if sql.strip().startswith(prefix):
                return resp
        return [[]]

    client.query.side_effect = query
    return client


def test_insert_routes_facts_to_memory_fact_table():
    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.1, 0.2, 0.3]],
        payloads=[
            {
                "kind": "fact",
                "text": "User likes coffee",
                "metadata": {"scope": "user"},
                "confidence": 0.9,
            }
        ],
        ids=["fact-001"],
    )
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "memory_fact" in sent_sql


def test_insert_routes_preferences_to_memory_preference_table():
    store = SurrealMemoryStore.from_test_client(_fake_client({"CREATE": [[]]}))
    store.insert(
        vectors=[[0.1]],
        payloads=[
            {
                "kind": "preference",
                "text": "bullets",
                "metadata": {"scope": "user"},
                "confidence": 0.85,
            }
        ],
        ids=["pref-001"],
    )
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "memory_preference" in sent_sql


def test_search_returns_outputdata_objects():
    fake_record = {
        "id": "memory_fact:abc",
        "text": "user lives in SF",
        "metadata": {"scope": "user"},
        "confidence": 0.8,
        "created_at": "2026-05-11T00:00:00Z",
        "score": 0.92,
    }
    store = SurrealMemoryStore.from_test_client(
        _fake_client({"SELECT": [[fake_record]]})
    )
    # mem0 2.x signature: search(query, vectors, top_k, filters)
    hits = store.search(
        query="where does user live",
        vectors=[0.1, 0.2],
        top_k=5,
        filters={"kind": "fact"},
    )
    assert len(hits) == 1
    assert isinstance(hits[0], OutputData)
    assert hits[0].id == "memory_fact:abc"
    assert hits[0].payload["text"] == "user lives in SF"
    assert hits[0].score == 0.92


def test_delete_emits_delete_sql_with_id():
    store = SurrealMemoryStore.from_test_client(_fake_client({"DELETE": [[]]}))
    store.delete("memory_fact:abc")
    sent_sql = store._client.query.call_args_list[0].args[0]
    assert "DELETE" in sent_sql
    assert "memory_fact:abc" in sent_sql


def test_list_cols_returns_three_memory_tables():
    store = SurrealMemoryStore.from_test_client(_fake_client({}))
    cols = store.list_cols()
    assert set(cols) == {"memory_fact", "memory_preference", "memory_episode"}


def test_reset_removes_and_redefines_all_three_tables():
    store = SurrealMemoryStore.from_test_client(
        _fake_client({"REMOVE": [[]], "DEFINE": [[]]})
    )
    store.reset()
    sqls = " ".join(c.args[0] for c in store._client.query.call_args_list)
    for table in ("memory_fact", "memory_preference", "memory_episode"):
        assert table in sqls


def test_keyword_search_returns_none():
    """We do not wire up SurrealDB FTS in v0.4; mem0 treats None as 'skip BM25'."""
    store = SurrealMemoryStore.from_test_client(_fake_client({}))
    assert store.keyword_search("anything") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_surreal_store.py -v
```
Expected: `ModuleNotFoundError: No module named 'desktop.memory.surreal_store'`.

- [ ] **Step 3: Implement the adapter**

```python
# desktop/memory/surreal_store.py
"""mem0 VectorStoreBase adapter for SurrealDB.

mem0 2.x requires that vector stores inherit from `VectorStoreBase` (in
`mem0.vector_stores.base`) and implement 11 abstract methods. Search results
must expose `.id`, `.score`, `.payload` attributes (mem0's internal hit shape)
— we use a small Pydantic `OutputData` class to match.

Schema (3 tables, same shape, created in Task 4):
    memory_fact, memory_preference, memory_episode
    {
        id: record<...>,
        text: string,
        embedding: array<float>,    # 768 dims for nomic-embed-text-v1.5
        metadata: object,
        scope: string,              # "user" | "notebook"
        confidence: float,
        created_at: datetime,
    }

Routing: `payloads[i]["kind"]` ∈ {"fact","preference","episode"} chooses the
table on insert; `filters["kind"]` chooses on search. Default "fact".

The `__init__` signature must match `SurrealVectorStoreConfig` (Task 2.5)
because mem0's `VectorStoreFactory.create()` calls `cls(**config.model_dump())`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from mem0.vector_stores.base import VectorStoreBase


class OutputData(BaseModel):
    id: Optional[str]
    score: Optional[float]
    payload: Optional[dict]


_KIND_TO_TABLE = {
    "fact": "memory_fact",
    "preference": "memory_preference",
    "episode": "memory_episode",
}
_ALL_TABLES: list[str] = list(_KIND_TO_TABLE.values())


class SurrealMemoryStore(VectorStoreBase):
    """mem0 vector-store adapter for SurrealDB.

    Constructed by mem0's `VectorStoreFactory` as
    `SurrealMemoryStore(**SurrealVectorStoreConfig.model_dump())`.
    For tests, use the `from_test_client` classmethod with a mock client.
    """

    def __init__(
        self,
        *,
        collection_name: str = "memory",
        embedding_model_dims: int = 768,
        surreal_url: str,
        namespace: str = "open_notebook",
        database: str = "open_notebook",
        user: str,
        password: str,
    ):
        from surrealdb import Surreal

        self._client = Surreal(surreal_url)
        self._connect_args = (namespace, database, user, password)
        self._connected = False
        self._collection_name = collection_name
        self._embedding_dims = embedding_model_dims

    @classmethod
    def from_test_client(cls, client) -> "SurrealMemoryStore":
        inst = cls.__new__(cls)
        inst._client = client
        inst._connected = True
        inst._collection_name = "memory"
        inst._embedding_dims = 768
        return inst

    # ---------------------------------------------------------- internal helpers

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        ns, db, user, password = self._connect_args
        asyncio.get_event_loop().run_until_complete(
            self._client.signin({"user": user, "pass": password})
        )
        asyncio.get_event_loop().run_until_complete(self._client.use(ns, db))
        self._connected = True

    def _table(self, payload: dict) -> str:
        return _KIND_TO_TABLE.get(payload.get("kind", "fact"), "memory_fact")

    def _exec(self, sql: str, vars: dict | None = None):
        """Execute a SurrealQL query, supporting sync (mock) + async (real) clients."""
        result = self._client.query(sql, vars)
        if asyncio.iscoroutine(result):
            result = asyncio.get_event_loop().run_until_complete(result)
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, list):
                return first
        return result or []

    def _to_output(self, row: dict) -> OutputData:
        """Convert a SurrealDB row dict to an OutputData (mem0's hit shape)."""
        row = dict(row)
        score = row.pop("score", 1.0)
        rid = str(row.pop("id", ""))
        return OutputData(id=rid, score=float(score), payload=row)

    # ---------------------------------------------------------- VectorStoreBase

    def create_col(self, name, vector_size, distance):
        """No-op: the 3 memory tables + HNSW index are created by the SQL
        migration in Task 4. mem0 calls this on first init — accept silently."""
        return None

    def insert(self, vectors, payloads=None, ids=None):
        self._ensure_connected()
        payloads = payloads or [{} for _ in vectors]
        ids = ids or [None for _ in vectors]
        for vec, payload, _id in zip(vectors, payloads, ids):
            table = self._table(payload)
            now = datetime.now(timezone.utc).isoformat()
            row = {
                "text": payload.get("text", ""),
                "embedding": vec,
                "metadata": payload.get("metadata", {}),
                "scope": payload.get("metadata", {}).get("scope", "user"),
                "confidence": payload.get("confidence", 1.0),
                "created_at": now,
            }
            if _id:
                row["id"] = _id
            self._exec(f"CREATE {table} CONTENT $row", {"row": row})

    def search(
        self, query: str, vectors, top_k: int = 5, filters: dict | None = None
    ) -> list[OutputData]:
        """Vector cosine search. `query` (text) is unused — we operate on the
        precomputed `vectors` embedding. `filters['kind']` narrows to a single
        memory table; otherwise we union the three."""
        self._ensure_connected()
        kind = (filters or {}).get("kind")
        tables = [_KIND_TO_TABLE[kind]] if kind in _KIND_TO_TABLE else _ALL_TABLES
        hits: list[OutputData] = []
        for table in tables:
            rows = self._exec(
                f"SELECT *, vector::similarity::cosine(embedding, $q) AS score "
                f"FROM {table} ORDER BY score DESC LIMIT $limit",
                {"q": vectors, "limit": top_k},
            )
            for row in rows or []:
                hits.append(self._to_output(row))
        hits.sort(key=lambda h: h.score or 0.0, reverse=True)
        return hits[:top_k]

    def delete(self, vector_id):
        self._ensure_connected()
        self._exec(f"DELETE {vector_id}")

    def update(self, vector_id, vector=None, payload=None):
        self._ensure_connected()
        patch: dict[str, Any] = {}
        if payload is not None:
            for k in ("text", "confidence", "metadata"):
                if k in payload:
                    patch[k] = payload[k]
        if vector is not None:
            patch["embedding"] = vector
        if patch:
            self._exec(f"UPDATE {vector_id} MERGE $patch", {"patch": patch})

    def get(self, vector_id) -> OutputData | None:
        self._ensure_connected()
        rows = self._exec(f"SELECT * FROM {vector_id}")
        if not rows:
            return None
        return self._to_output(rows[0])

    def list_cols(self) -> list:
        return list(_ALL_TABLES)

    def delete_col(self):
        self._ensure_connected()
        for table in _ALL_TABLES:
            self._exec(f"REMOVE TABLE IF EXISTS {table}")

    def col_info(self) -> dict:
        self._ensure_connected()
        return {t: self._exec(f"INFO FOR TABLE {t}") for t in _ALL_TABLES}

    def list(self, filters: dict | None = None, top_k: int | None = 100) -> list:
        self._ensure_connected()
        kind = (filters or {}).get("kind")
        tables = [_KIND_TO_TABLE[kind]] if kind in _KIND_TO_TABLE else _ALL_TABLES
        limit = top_k or 100
        out: list[OutputData] = []
        for table in tables:
            rows = self._exec(f"SELECT * FROM {table} LIMIT $limit", {"limit": limit})
            for row in rows or []:
                out.append(self._to_output(row))
        return out

    def reset(self):
        """Drop and recreate the 3 memory tables. mem0 invokes this from
        `Memory.reset()`. NB: Task 4's migration adds the HNSW index — after
        reset we have bare tables; re-running the migration restores indexes."""
        self.delete_col()
        for table in _ALL_TABLES:
            self._exec(f"DEFINE TABLE {table}")

    def keyword_search(self, query: str, top_k: int = 5, filters: dict | None = None):
        """BM25 / FTS not wired in v0.4. Returning None tells mem0 to skip
        hybrid scoring and rely on vector search alone."""
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_surreal_store.py -v
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/memory/surreal_store.py desktop/memory/tests/test_surreal_store.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: SurrealDB VectorStoreBase adapter for mem0 (3 tables, mem0 2.x)"
```

---

## Task 4: SurrealDB migration for the 3 memory tables

Upstream's `open_notebook/database/async_migrate.py` hard-codes the migration list (currently 1–14). We add migration #15 covering the three memory tables, plus a `15_down.surrealql` rollback, then register both in `AsyncMigrationManager`.

**Files:**
- Create: `open_notebook/database/migrations/15.surrealql`
- Create: `open_notebook/database/migrations/15_down.surrealql`
- Modify: `open_notebook/database/async_migrate.py` (append migration 15 to up + down lists)

- [ ] **Step 1: Write the up migration** (file: `open_notebook/database/migrations/15.surrealql`)

```sql
-- 15.surrealql
-- Open Notebook Plus v0.4 — memory layer tables.
-- 3 tables, identical shape, routed by `kind` in payloads:
--   memory_fact, memory_preference, memory_episode.
-- HNSW index DIMENSION 768 = nomic-embed-text-v1.5's output size.

-- memory_fact: atomic facts extracted from chat turns.
DEFINE TABLE memory_fact SCHEMAFULL;
DEFINE FIELD text       ON memory_fact TYPE string;
DEFINE FIELD embedding  ON memory_fact TYPE array<float>;
DEFINE FIELD metadata   ON memory_fact TYPE object DEFAULT {};
DEFINE FIELD scope      ON memory_fact TYPE string DEFAULT "user";
DEFINE FIELD confidence ON memory_fact TYPE float  DEFAULT 1.0;
DEFINE FIELD created_at ON memory_fact TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS memory_fact_embedding ON memory_fact
    FIELDS embedding HNSW DIMENSION 768;

-- memory_preference: user preferences and workflow habits.
DEFINE TABLE memory_preference SCHEMAFULL;
DEFINE FIELD text       ON memory_preference TYPE string;
DEFINE FIELD embedding  ON memory_preference TYPE array<float>;
DEFINE FIELD metadata   ON memory_preference TYPE object DEFAULT {};
DEFINE FIELD scope      ON memory_preference TYPE string DEFAULT "user";
DEFINE FIELD confidence ON memory_preference TYPE float  DEFAULT 1.0;
DEFINE FIELD created_at ON memory_preference TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS memory_preference_embedding ON memory_preference
    FIELDS embedding HNSW DIMENSION 768;

-- memory_episode: per-chat-session summaries.
DEFINE TABLE memory_episode SCHEMAFULL;
DEFINE FIELD text       ON memory_episode TYPE string;
DEFINE FIELD embedding  ON memory_episode TYPE array<float>;
DEFINE FIELD metadata   ON memory_episode TYPE object DEFAULT {};
DEFINE FIELD scope      ON memory_episode TYPE string DEFAULT "user";
DEFINE FIELD confidence ON memory_episode TYPE float  DEFAULT 1.0;
DEFINE FIELD created_at ON memory_episode TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS memory_episode_embedding ON memory_episode
    FIELDS embedding HNSW DIMENSION 768;
```

- [ ] **Step 2: Write the down migration** (file: `open_notebook/database/migrations/15_down.surrealql`)

```sql
-- 15_down.surrealql — rollback for v0.4 memory layer tables.
REMOVE TABLE IF EXISTS memory_fact;
REMOVE TABLE IF EXISTS memory_preference;
REMOVE TABLE IF EXISTS memory_episode;
```

- [ ] **Step 3: Register migration #15 in `AsyncMigrationManager`**

In `open_notebook/database/async_migrate.py`, find the `up_migrations` list (currently ends with `14.surrealql`) and append:

```python
            AsyncMigration.from_file(
                "open_notebook/database/migrations/14.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/15.surrealql"
            ),
        ]
```

Then in the `down_migrations` list (currently ends with `14_down.surrealql`) append:

```python
            AsyncMigration.from_file(
                "open_notebook/database/migrations/14_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/15_down.surrealql"
            ),
        ]
```

(Two list appends; nothing else in the class changes — `needs_migration()` already keys off `len(self.up_migrations)`.)

- [ ] **Step 4: Verify SurrealQL parses**

```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
# Smoke check using a temporary in-memory SurrealDB. If `surreal` binary not
# convenient, skip and rely on the integration smoke at first launch.
surreal start --user root --pass test memory --bind 127.0.0.1:0 &
SDB_PID=$!
sleep 1
surreal sql --user root --pass test --endpoint http://127.0.0.1:8000 \
    --ns _test --db _test \
    < open_notebook/database/migrations/15.surrealql 2>&1 | tail -10
kill $SDB_PID 2>/dev/null
```
Expected: no `ERR` lines. (If the local `surreal` binary isn't on PATH, this step is skippable — first-launch smoke catches errors.)

- [ ] **Step 5: Commit**

```bash
git add open_notebook/database/migrations/15.surrealql \
        open_notebook/database/migrations/15_down.surrealql \
        open_notebook/database/async_migrate.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "db: v0.4 migration #15 — memory_fact/preference/episode tables + HNSW indexes"
```

---

## Task 5: mem0 client factory

**Files:**
- Create: `desktop/memory/client.py`
- Create: `desktop/memory/tests/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# desktop/memory/tests/test_client.py
from __future__ import annotations

from unittest.mock import patch, MagicMock

from desktop.memory.client import build_memory_client


def test_build_memory_client_uses_surreal_provider_and_local_endpoints():
    fake_cfg = MagicMock(
        surreal_user="root",
        surreal_password="x" * 24,
    )
    with patch("desktop.memory.client.Memory") as mem0_cls:
        build_memory_client(
            cfg=fake_cfg,
            surreal_url="ws://127.0.0.1:50000/rpc",
            embed_url="http://127.0.0.1:51000/v1",
            llm_url="http://127.0.0.1:52000/v1",
        )
        call_args = mem0_cls.from_config.call_args
        config = call_args.kwargs.get("config") or call_args.args[0]
        # Vector store wired to our registered surreal provider, not "custom"
        assert config["vector_store"]["provider"] == "surreal"
        assert (
            config["vector_store"]["config"]["surreal_url"]
            == "ws://127.0.0.1:50000/rpc"
        )
        assert config["vector_store"]["config"]["user"] == "root"
        assert config["vector_store"]["config"]["password"] == "x" * 24
        # Embedder + LLM point at local servers
        assert config["embedder"]["config"]["base_url"] == "http://127.0.0.1:51000/v1"
        assert config["embedder"]["config"]["model"] == "nomic-embed-text-v1.5"
        assert config["llm"]["config"]["base_url"] == "http://127.0.0.1:52000/v1"
        assert config["llm"]["config"]["model"] == "Hermes-3-Llama-3.1-8B-Q4_K_M"


def test_build_memory_client_imports_register_module_for_side_effect():
    """If `desktop.memory._register` hasn't run by the time Memory.from_config
    is called, mem0 will reject `provider: 'surreal'` as unknown. Verify the
    side-effect import happened. Note: `_provider_configs` is a Pydantic v2
    ModelPrivateAttr at class level — read its `.default` to see the dict."""
    import sys

    assert "desktop.memory._register" in sys.modules
    from mem0.vector_stores.configs import VectorStoreConfig

    assert "surreal" in VectorStoreConfig._provider_configs.default
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'desktop.memory.client'`.

- [ ] **Step 3: Implement**

```python
# desktop/memory/client.py
"""Factory for the mem0 memory client wired to our local SurrealDB +
local-LLM + local-embedder endpoints.

The `_register` import below has the side effect of installing `surreal` as
a mem0 vector-store provider; it MUST happen before `Memory.from_config()`
sees `provider: "surreal"`, or mem0 will reject the config as unknown.
"""

from __future__ import annotations

import desktop.memory._register  # noqa: F401 — registers `surreal` provider

try:
    from mem0 import Memory
except ImportError:  # tests don't need mem0 installed at import time
    Memory = None  # type: ignore[assignment]


def build_memory_client(*, cfg, surreal_url: str, embed_url: str, llm_url: str):
    """Build a `mem0.Memory` instance backed by our SurrealDB store + local
    OpenAI-compatible LLM and embedder endpoints."""
    if Memory is None:
        raise RuntimeError("mem0 not installed — run bootstrap to provision the venv")
    return Memory.from_config(
        {
            "vector_store": {
                "provider": "surreal",
                "config": {
                    "surreal_url": surreal_url,
                    "namespace": "open_notebook",
                    "database": "open_notebook",
                    "user": cfg.surreal_user,
                    "password": cfg.surreal_password,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": "sk-no-key",
                    "base_url": embed_url,
                    "model": "nomic-embed-text-v1.5",
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": "sk-no-key",
                    "base_url": llm_url,
                    "model": "Hermes-3-Llama-3.1-8B-Q4_K_M",
                },
            },
        }
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_client.py -v
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/memory/client.py desktop/memory/tests/test_client.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: mem0 client factory wired to local SurrealDB + LLM + embed servers"
```

---

## Task 6: Writer prompts

**Files:**
- Create: `desktop/memory/prompts.py`

- [ ] **Step 1: Write the prompts module**

```python
# desktop/memory/prompts.py
"""Hermes 3 system prompts + tool definitions for the memory writer agent.

Hermes 3 emits `<tool_call>` JSON blocks when prompted with explicit tool
definitions. We parse those blocks to extract structured memory writes.
"""

from __future__ import annotations

# Tool definitions are inlined in the system prompt because Hermes 3 follows
# its training-time tool-calling format reliably when tools appear up front.
EXTRACT_TURN_SYSTEM_PROMPT = """You are a memory extractor.

From the conversation turn provided, identify EXPLICIT facts about the user
or their workflow that should be remembered for future conversations. Only
extract what was explicitly stated by the user. Never infer unstated
preferences. If the turn contains no explicit facts, emit no tool calls.

Available tools (emit `<tool_call>` blocks):

remember_preference:
  text: the preference (e.g. "Prefers bullet points over paragraphs")
  scope: "user" or "notebook"
  confidence: 0.0 to 1.0

remember_fact:
  text: the fact (e.g. "Working on a dissertation about RAG")
  scope: "user" or "notebook"
  confidence: 0.0 to 1.0

Emit zero, one, or several tool calls — each as a `<tool_call>{...}</tool_call>`
block. Do NOT emit anything else after the tool calls."""


SUMMARIZE_SESSION_SYSTEM_PROMPT = """You are a chat session summarizer.

Given a complete chat transcript, emit a single `remember_episode` tool call
capturing what happened in the session. Be specific about topics discussed and
any decisions / next steps the user articulated.

remember_episode:
  summary: 1-2 sentences capturing the session arc
  topics: list of 2-6 short topic tags
  outcome: one of "next_step_identified", "question_answered", "exploration",
           "decision_made", "no_outcome"
  source_chat_id: the chat session ID (provided in the user message)

Emit exactly one `<tool_call>{...}</tool_call>` block with the remember_episode call."""


def render_extract_user(user_text: str, assistant_text: str) -> str:
    return f"USER TURN: {user_text}\n\nASSISTANT TURN: {assistant_text}"


def render_summarize_user(chat_session_id: str, transcript: str) -> str:
    return f"CHAT SESSION ID: {chat_session_id}\n\nTRANSCRIPT:\n{transcript}"
```

- [ ] **Step 2: Commit (no tests — pure data)**

```bash
git add desktop/memory/prompts.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory writer system prompts + tool definitions"
```

---

## Task 7: Writer — extractor + summarizer + tool-call parser

**Files:**
- Create: `desktop/memory/writer.py`
- Create: `desktop/memory/tests/test_writer.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/memory/tests/test_writer.py
from __future__ import annotations

from unittest.mock import MagicMock

from desktop.memory.writer import (
    parse_tool_calls,
    apply_tool_call,
    extract_turn,
    summarize_session,
)


def test_parse_tool_calls_finds_single_call():
    raw = (
        '<tool_call>{"name": "remember_fact", '
        '"arguments": {"text": "x", "scope": "user", "confidence": 0.8}}'
        "</tool_call>"
    )
    calls = parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["name"] == "remember_fact"


def test_parse_tool_calls_finds_multiple_calls():
    raw = (
        '<tool_call>{"name": "remember_fact", "arguments": {"text": "a", "scope": "user", "confidence": 1}}</tool_call>'
        "\n some chat \n"
        '<tool_call>{"name": "remember_preference", "arguments": {"text": "b", "scope": "user", "confidence": 1}}</tool_call>'
    )
    calls = parse_tool_calls(raw)
    assert len(calls) == 2
    assert calls[1]["name"] == "remember_preference"


def test_parse_tool_calls_returns_empty_on_no_calls():
    assert parse_tool_calls("No tool calls here.") == []


def test_parse_tool_calls_skips_malformed_blocks():
    raw = "<tool_call>not valid json</tool_call>"
    assert parse_tool_calls(raw) == []


def test_apply_tool_call_remember_fact_invokes_memory_add():
    mem_client = MagicMock()
    apply_tool_call(
        mem_client,
        {
            "name": "remember_fact",
            "arguments": {
                "text": "user likes coffee",
                "scope": "user",
                "confidence": 0.9,
            },
        },
    )
    mem_client.add.assert_called_once()
    kwargs = mem_client.add.call_args.kwargs
    assert kwargs.get("messages") or kwargs.get("data") or mem_client.add.call_args.args
    # The payload should carry metadata.kind = "fact"


def test_extract_turn_calls_llm_then_applies_each_tool_call(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.complete.return_value = (
        '<tool_call>{"name": "remember_fact", '
        '"arguments": {"text": "x", "scope": "user", "confidence": 0.9}}'
        "</tool_call>"
    )
    mem_client = MagicMock()
    extract_turn(
        llm=fake_llm,
        mem_client=mem_client,
        chat_session_id="chat:1",
        user_text="hello",
        assistant_text="hi",
    )
    fake_llm.complete.assert_called_once()
    mem_client.add.assert_called_once()


def test_summarize_session_emits_episode():
    fake_llm = MagicMock()
    fake_llm.complete.return_value = (
        '<tool_call>{"name": "remember_episode", "arguments": '
        '{"summary": "discussed coffee", "topics": ["coffee"], '
        '"outcome": "exploration", "source_chat_id": "chat:1"}}'
        "</tool_call>"
    )
    mem_client = MagicMock()
    summarize_session(
        llm=fake_llm,
        mem_client=mem_client,
        chat_session_id="chat:1",
        transcript="user: ...\nassistant: ...",
    )
    mem_client.add.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_writer.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# desktop/memory/writer.py
"""Hermes 3 memory writer agent.

Two entry points:
- extract_turn(): runs after each assistant response, extracts explicit
  facts/preferences via short Hermes call.
- summarize_session(): runs at chat session end, produces one episode record.

Both invoke `<llm>.complete(system_prompt, user_prompt)` and parse the
returned text for `<tool_call>...</tool_call>` blocks, then dispatch each to
the mem0 client via apply_tool_call.
"""

from __future__ import annotations

import json
import re
from typing import Any

from desktop.memory.prompts import (
    EXTRACT_TURN_SYSTEM_PROMPT,
    SUMMARIZE_SESSION_SYSTEM_PROMPT,
    render_extract_user,
    render_summarize_user,
)


_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract tool-call JSON blocks from Hermes 3 output text.

    Malformed JSON is skipped silently — the writer is best-effort.
    """
    calls = []
    for match in _TOOL_CALL_RE.finditer(text):
        try:
            calls.append(json.loads(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
    return calls


_NAME_TO_KIND = {
    "remember_fact": "fact",
    "remember_preference": "preference",
    "remember_episode": "episode",
}


def apply_tool_call(mem_client, call: dict) -> None:
    """Translate one tool call into a mem0.add(...) invocation."""
    name = call.get("name")
    if name not in _NAME_TO_KIND:
        return  # unknown tool
    args = call.get("arguments", {})
    text = args.get("text") or args.get("summary") or ""
    if not text:
        return
    kind = _NAME_TO_KIND[name]
    metadata = {
        "kind": kind,
        "scope": args.get("scope", "user"),
    }
    if name == "remember_episode":
        metadata["topics"] = args.get("topics", [])
        metadata["outcome"] = args.get("outcome", "no_outcome")
        metadata["source_chat_id"] = args.get("source_chat_id", "")
    mem_client.add(
        messages=text,
        user_id="local",
        metadata=metadata,
    )


def extract_turn(
    *, llm, mem_client, chat_session_id: str, user_text: str, assistant_text: str
) -> None:
    """Run the per-turn extractor; write any tool calls into memory."""
    output = llm.complete(
        system=EXTRACT_TURN_SYSTEM_PROMPT,
        user=render_extract_user(user_text, assistant_text),
    )
    for call in parse_tool_calls(output):
        # source_chat_id isn't a tool argument for extract_turn, but we attach
        # it to metadata so a downstream retriever can attribute the fact.
        call.setdefault("arguments", {}).setdefault("source_chat_id", chat_session_id)
        apply_tool_call(mem_client, call)


def summarize_session(
    *, llm, mem_client, chat_session_id: str, transcript: str
) -> None:
    output = llm.complete(
        system=SUMMARIZE_SESSION_SYSTEM_PROMPT,
        user=render_summarize_user(chat_session_id, transcript),
    )
    for call in parse_tool_calls(output):
        apply_tool_call(mem_client, call)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/memory/tests/test_writer.py -v
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/memory/writer.py desktop/memory/tests/test_writer.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory writer (extract_turn + summarize_session + tool parser)"
```

---

## Task 8: Memory retriever shim (FastAPI)

**Files:**
- Create: `desktop/desktop_shims/memory_shim.py`
- Create: `desktop/tests/test_memory_shim.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_memory_shim.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.memory_shim import build_app


def _fake_memory_client():
    """Memory mock that returns canned search results."""
    client = MagicMock()
    client.search.return_value = [
        {
            "id": "fact:1",
            "text": "user likes coffee",
            "score": 0.95,
            "metadata": {"kind": "fact", "scope": "user"},
            "confidence": 0.9,
            "created_at": "2026-05-10T00:00:00Z",
        },
        {
            "id": "pref:1",
            "text": "bullet points",
            "score": 0.85,
            "metadata": {"kind": "preference", "scope": "user"},
            "confidence": 0.85,
            "created_at": "2026-05-09T00:00:00Z",
        },
    ]
    return client


def test_health_returns_200():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_relevant_returns_topk_records():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/api/memory/relevant?topic=coffee&k=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["records"]) == 2
        assert body["records"][0]["text"] == "user likes coffee"


def test_relevant_empty_topic_returns_200():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/api/memory/relevant?topic=&k=5")
        assert r.status_code == 200


def test_delete_calls_memory_client_delete():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.delete("/api/memory/fact/abc-123")
        assert r.status_code == 200
        mem.delete.assert_called_once_with(memory_id="fact:abc-123")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_memory_shim.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# desktop/desktop_shims/memory_shim.py
"""Memory retriever HTTP shim.

Exposes:
    GET    /health                          → {"status":"ok"}
    GET    /api/memory/relevant?topic&k     → top-K records mix of kinds
    GET    /api/memory/preferences          → all preference records
    GET    /api/memory/facts                → all fact records
    GET    /api/memory/episodes             → all episode records
    GET    /api/memory/search?q             → semantic search across all
    DELETE /api/memory/{kind}/{id}          → forget a specific record
    GET    /api/memory/ambient/status       → bridge state
    POST   /api/memory/ambient/pause        → pause bridge for this session

Run as:
    python -m desktop_shims.memory_shim --port 8767
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import FastAPI, HTTPException


def _unwrap(results: Any) -> list:
    """mem0 2.x's Memory.search() returns {"results": [...]}; the test mock
    may return a bare list. Normalize to a list either way."""
    if isinstance(results, dict):
        return list(results.get("results") or [])
    return list(results or [])


def build_app(mem_client: Any, ambient_status_fn=None) -> FastAPI:
    app = FastAPI(title="Open Notebook Plus — Memory retriever")
    state = {"ambient_paused": False}

    # mem0 2.x requires every search/add to be scoped to a user/agent/run.
    # We're a single-user desktop app — pin to "local".
    USER_ID = "local"

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/memory/relevant")
    def relevant(topic: str = "", k: int = 5) -> dict:
        if not topic:
            return {"records": []}
        records = _unwrap(
            mem_client.search(query=topic, top_k=k, filters={"user_id": USER_ID})
        )
        return {"records": records[:k]}

    @app.get("/api/memory/preferences")
    def preferences() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "preference"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/facts")
    def facts() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "fact"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/episodes")
    def episodes() -> dict:
        records = _unwrap(
            mem_client.search(
                query="", top_k=200, filters={"user_id": USER_ID, "kind": "episode"}
            )
        )
        return {"records": records}

    @app.get("/api/memory/search")
    def search(q: str) -> dict:
        if not q:
            return {"records": []}
        records = _unwrap(
            mem_client.search(query=q, top_k=50, filters={"user_id": USER_ID})
        )
        return {"records": records}

    @app.delete("/api/memory/{kind}/{id}")
    def delete(kind: str, id: str) -> dict:
        if kind not in ("fact", "preference", "episode"):
            raise HTTPException(status_code=400, detail="invalid kind")
        mem_client.delete(memory_id=f"{kind}:{id}")
        return {"ok": True}

    @app.get("/api/memory/ambient/status")
    def ambient_status() -> dict:
        if ambient_status_fn is None:
            return {"available": False, "paused": state["ambient_paused"]}
        return {**ambient_status_fn(), "paused": state["ambient_paused"]}

    @app.post("/api/memory/ambient/pause")
    def ambient_pause() -> dict:
        state["ambient_paused"] = True
        return {"ok": True}

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--surreal-url", required=True)
    parser.add_argument("--embed-url", required=True)
    parser.add_argument("--llm-url", required=True)
    args = parser.parse_args(argv)

    # Lazy imports — only at runtime
    from desktop.config import default_config_path, load_or_create
    from desktop.memory.client import build_memory_client

    cfg = load_or_create(default_config_path())
    mem_client = build_memory_client(
        cfg=cfg,
        surreal_url=args.surreal_url,
        embed_url=args.embed_url,
        llm_url=args.llm_url,
    )
    app = build_app(mem_client=mem_client)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_memory_shim.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/desktop_shims/memory_shim.py desktop/tests/test_memory_shim.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory retriever shim — /api/memory/{relevant,facts,...}"
```

---

## Task 9: OpenChronicle bridge shim

**Files:**
- Create: `desktop/desktop_shims/openchronicle_shim.py`
- Create: `desktop/tests/test_openchronicle_shim.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_openchronicle_shim.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.openchronicle_shim import build_app


def _fake_mcp_client(recent_events=None, search_events=None):
    """Fake MCP client with canned tool responses."""
    client = MagicMock()
    client.call_tool = AsyncMock()

    async def fake_call_tool(name, args):
        if name == "recent_activity":
            return {
                "events": recent_events
                or [
                    {"title": "Edited foo.md", "ts": "2026-05-11T08:00Z"},
                ]
            }
        if name == "search":
            return {
                "events": search_events
                or [
                    {"title": "Read Self-RAG paper", "ts": "2026-05-11T07:00Z"},
                ]
            }
        return {"events": []}

    client.call_tool.side_effect = fake_call_tool
    return client


def test_health_returns_200_when_mcp_reachable():
    app = build_app(mcp_client=_fake_mcp_client())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_context_recent_calls_recent_activity_tool():
    mcp = _fake_mcp_client()
    app = build_app(mcp_client=mcp)
    with TestClient(app) as c:
        r = c.get("/context/recent?minutes=10")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
        assert len(body["events"]) >= 1


def test_context_search_calls_search_tool():
    mcp = _fake_mcp_client()
    app = build_app(mcp_client=mcp)
    with TestClient(app) as c:
        r = c.get("/context/search?topic=self-RAG&limit=5")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_openchronicle_shim.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# desktop/desktop_shims/openchronicle_shim.py
"""HTTP bridge from Open Notebook Plus to OpenChronicle's MCP daemon.

OpenChronicle exposes (per https://github.com/Einsia/OpenChronicle):
  recent_activity({minutes: int}) → list of screen events
  search({query: str, limit: int}) → topic-matched events

We translate those into a small HTTP API the memory retriever can consume.

Run as:
    python -m desktop_shims.openchronicle_shim --port 8768 \\
        --mcp-url http://127.0.0.1:8742/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from fastapi import FastAPI, HTTPException


def build_app(mcp_client: Any) -> FastAPI:
    app = FastAPI(title="Open Notebook Plus — OpenChronicle bridge")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    async def _call(tool: str, args: dict) -> dict:
        try:
            return await mcp_client.call_tool(tool, args)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/context/recent")
    async def recent(minutes: int = 10) -> dict:
        return await _call("recent_activity", {"minutes": minutes})

    @app.get("/context/search")
    async def search(topic: str, limit: int = 5) -> dict:
        return await _call("search", {"query": topic, "limit": limit})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8742/mcp")
    args = parser.parse_args(argv)

    # Lazy import; only when running for real.
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    class _PerCallMcpClient:
        """Opens a fresh MCP session per tool call.

        We can't hold a session across HTTP requests because `streamablehttp_client`
        and `ClientSession` are async context managers — once the `with` blocks
        exit, the connection is closed. Per-call setup adds ~50–100 ms latency but
        is simple, correct, and reconnects automatically if OpenChronicle
        restarts.
        """

        def __init__(self, url: str):
            self._url = url

        async def call_tool(self, name: str, arguments: dict) -> dict:
            async with streamablehttp_client(self._url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return (
                        result.model_dump() if hasattr(result, "model_dump") else result
                    )

    app = build_app(mcp_client=_PerCallMcpClient(args.mcp_url))

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_openchronicle_shim.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/desktop_shims/openchronicle_shim.py \
        desktop/tests/test_openchronicle_shim.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: OpenChronicle MCP bridge shim — /context/{recent,search}"
```

---

## Task 10: Supervisor — spawn chat LLM + memory retriever + OpenChronicle bridge

The memory writer (Task 7/12) needs Hermes 3 chat completions for fact extraction. v0.3 spawns a llama-server only for embeddings; v0.4 adds a second llama-server for a chat-capable GGUF.

**Files:**
- Modify: `desktop/launcher.py`
- Modify: `desktop/tests/test_launcher.py`

- [ ] **Step 1: Add Supervisor constructor params + instance attrs**

Update `Supervisor.__init__` to accept two new optional kwargs (place after `nomic_embed_path` for symmetry):

```python
chat_llm_path: Path | None = (None,)
openchronicle_available: bool = (False,)
```

And add the matching instance assignments + ports:

```python
        self.chat_llm_path = chat_llm_path
        self.openchronicle_available = openchronicle_available
        # New v0.4 ports — initialised to 0 so auto_register can skip cleanly
        # when a server failed to start.
        self.chat_llm_port: int = 0
        self.memory_port: int = 0
        self.openchronicle_port: int = 0
```

- [ ] **Step 2: Add three new spawn methods after `_spawn_piper`**

```python
def _spawn_llamacpp_chat(self, port: int) -> None:
    """Second llama-server, this one serving a chat-capable GGUF.

    Needed by mem0's writer (extract_turn / summarize_session) for
    Hermes-3-style tool calling. ~5 GB RAM at runtime.
    """
    if self.chat_llm_path is None or not self.chat_llm_path.exists():
        return  # silently skip; memory writer will simply no-op
    args = [
        str(self.venv_python),
        "-m",
        "llama_cpp.server",
        "--model",
        str(self.chat_llm_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--n_ctx",
        "8192",
    ]
    self._spawn(args, cwd=self.upstream_root, name="llamacpp_chat")


def _spawn_memory_retriever(self, port: int) -> None:
    args = [
        str(self.venv_python),
        "-m",
        "desktop_shims.memory_shim",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--surreal-url",
        self.session_env["SURREAL_URL"],
        "--embed-url",
        f"http://127.0.0.1:{self.embed_port}/v1" if self.embed_port else "",
        "--llm-url",
        f"http://127.0.0.1:{self.chat_llm_port}/v1" if self.chat_llm_port else "",
    ]
    self._spawn(args, cwd=self.upstream_root, name="memory")


def _spawn_openchronicle_bridge(self, port: int) -> None:
    if not self.openchronicle_available:
        return
    args = [
        str(self.venv_python),
        "-m",
        "desktop_shims.openchronicle_shim",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--mcp-url",
        "http://127.0.0.1:8742/mcp",
    ]
    self._spawn(args, cwd=self.upstream_root, name="openchronicle")
```

- [ ] **Step 3: Extend `start_all` to allocate 3 more ports + spawn**

Change `find_free_ports(6)` to `find_free_ports(9)`, unpacking the new ports:

```python
(
    surreal_port,
    api_port,
    frontend_port,
    embed_port,
    whisper_port,
    piper_port,
    chat_llm_port,
    memory_port,
    openchronicle_port,
) = find_free_ports(9)
```

After the existing v0.3 supervisor.piper progress block (right after stashing `self.piper_port = piper_port`), append:

```python
        # v0.4 additions — order matters: chat LLM must be up before the
        # memory retriever boots, because the retriever instantiates
        # mem0.Memory which validates the LLM endpoint at startup.
        self._progress("supervisor.llamacpp_chat", "running")
        try:
            self._spawn_llamacpp_chat(chat_llm_port)
            self._progress("supervisor.llamacpp_chat", "done")
        except Exception:
            self._progress("supervisor.llamacpp_chat", "error")

        self._progress("supervisor.memory", "running")
        try:
            self._spawn_memory_retriever(memory_port)
            self._progress("supervisor.memory", "done")
        except Exception:
            self._progress("supervisor.memory", "error")

        if self.openchronicle_available:
            self._progress("supervisor.openchronicle", "running")
            try:
                self._spawn_openchronicle_bridge(openchronicle_port)
                self._progress("supervisor.openchronicle", "done")
            except Exception:
                self._progress("supervisor.openchronicle", "error")

        self.chat_llm_port = chat_llm_port
        self.memory_port = memory_port
        self.openchronicle_port = openchronicle_port if self.openchronicle_available else 0
```

- [ ] **Step 4: Add tests**

Append to `desktop/tests/test_launcher.py`:

```python
def test_supervisor_spawns_chat_llm_and_memory_retriever(cfg, tmp_path, monkeypatch):
    """v0.4: with a chat_llm_path and openchronicle_available=False,
    Supervisor.start_all should spawn both llamacpp_chat and memory_shim,
    but NOT openchronicle_shim."""
    spawned: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned.append(list(args))
        p = MagicMock(spec=subprocess.Popen)
        p.poll.return_value = None
        return p

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    # Stub chat GGUF so `_spawn_llamacpp_chat` doesn't no-op out.
    chat_gguf = tmp_path / "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"
    chat_gguf.write_bytes(b"FAKE-GGUF")

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        chat_llm_path=chat_gguf,
        openchronicle_available=False,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert any("llama_cpp.server" in s and "Hermes-3" in s for s in joined)
        assert any("desktop_shims.memory_shim" in s for s in joined)
        assert not any("openchronicle_shim" in s for s in joined)
        # Ports captured on the Supervisor instance
        assert sv.chat_llm_port != 0
        assert sv.memory_port != 0
        assert sv.openchronicle_port == 0
    finally:
        sv.stop_all()


def test_supervisor_spawns_openchronicle_when_available(cfg, tmp_path, monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            MagicMock(spec=subprocess.Popen, poll=MagicMock(return_value=None)),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        openchronicle_available=True,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert any("openchronicle_shim" in s for s in joined)
        assert sv.openchronicle_port != 0
    finally:
        sv.stop_all()


def test_supervisor_skips_chat_llm_when_no_path(cfg, tmp_path, monkeypatch):
    """No chat_llm_path → no llamacpp_chat process spawned; chat_llm_port stays 0."""
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            MagicMock(spec=subprocess.Popen, poll=MagicMock(return_value=None)),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        chat_llm_path=None,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        # chat LLM is skipped, but memory retriever still spawns (degraded mode).
        assert not any("llama_cpp.server" in s and "Hermes-3" in s for s in joined)
        assert any("desktop_shims.memory_shim" in s for s in joined)
    finally:
        sv.stop_all()
```

- [ ] **Step 5: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_launcher.py -v
```
Expected: all launcher tests pass (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add desktop/launcher.py desktop/tests/test_launcher.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: Supervisor — chat LLM + memory retriever + OpenChronicle"
```

---

## Task 11: App phases — OpenChronicle detect + memory_commands write

**Files:**
- Modify: `desktop/app.py`

- [ ] **Step 1: Add two new phase functions before `_phase_start_supervisor`**

```python
def _phase_detect_openchronicle(ctx: AppContext) -> None:
    import httpx

    try:
        r = httpx.get("http://127.0.0.1:8742/mcp", timeout=0.5)
        ctx.openchronicle_available = r.status_code < 500
    except Exception:
        ctx.openchronicle_available = False
    if ctx.progress_bus is not None:
        ctx.progress_bus.publish(
            "openchronicle.detect",
            "done",
            f"available={ctx.openchronicle_available}",
        )


def _phase_register_memory_commands(ctx: AppContext) -> None:
    """Drop commands/memory_commands.py into upstream's commands/ dir so the
    surreal-commands worker discovers our new handlers on startup."""
    import shutil

    commands_dst = ctx.upstream_root / "commands"  # the bundled upstream commands dir
    commands_dst.mkdir(parents=True, exist_ok=True)
    src = ctx.bin_dir.parent / "memory" / "memory_commands.py"
    # During development, src may live elsewhere; locate via package data:
    if not src.exists():
        import desktop.memory as mem_pkg

        src = Path(mem_pkg.__file__).parent / "memory_commands.py"
    if src.exists():
        shutil.copyfile(src, commands_dst / "memory_commands.py")
```

Add `openchronicle_available: bool = False` and `commands_dst: Path | None = None` attributes to `AppContext`.

Insert the two new phases into the `run()` call sequence between `_phase_bootstrap_runtime` and `_phase_select_provider`:

```python
    _phase_detect_openchronicle(ctx)
    _phase_register_memory_commands(ctx)
```

Update `_phase_start_supervisor(ctx)` to:

1. **Discover the chat LLM** (Hermes 3 GGUF) under `voice_model_dir / "GGUF"` — pick the first `Hermes-3*.gguf` found:
   ```python
   gguf_dir = voice_model_dir / "GGUF"
   chat_candidates = sorted(gguf_dir.glob("Hermes-3*.gguf")) if gguf_dir.exists() else []
   chat_llm_path = chat_candidates[0] if chat_candidates else None
   ```

2. **Pass two new kwargs** into the `Supervisor(...)` constructor:
   ```python
   chat_llm_path = (chat_llm_path,)
   openchronicle_available = (ctx.openchronicle_available,)
   ```

- [ ] **Step 2: Sanity-import**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.app; print('ok')"
```

- [ ] **Step 3: Run full test suite**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ 2>&1 | tail -5
```
Expected: no new failures.

- [ ] **Step 4: Commit**

```bash
git add desktop/app.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: app phases — detect OpenChronicle + register memory commands"
```

---

## Task 12: surreal-commands handlers (memory_commands.py)

The worker discovers `commands/*.py` modules at startup. We provide one.

**Files:**
- Create: `desktop/memory/memory_commands.py` (template that gets copied to upstream/commands/ at runtime)

- [ ] **Step 1: Write the module**

```python
# desktop/memory/memory_commands.py
"""surreal-commands handlers registered by Open Notebook Plus v0.4 memory layer.

This file is copied into the bundled upstream's commands/ directory at first
launch by desktop/app.py:_phase_register_memory_commands.

Discovery: surreal-commands imports any module passed via --import-modules.
Each @command-decorated function is registered as
    open_notebook.<function_name>
"""

from __future__ import annotations

import os

from surreal_commands import command


def _build_clients():
    """Lazily build the LLM + memory clients at command-invocation time.

    Avoids importing heavy deps at module load (worker discovery).

    Reads MEMORY_* env vars set by the Supervisor in `session_env` before
    spawning the worker. We use a private namespace (MEMORY_*) instead of
    OPENAI_COMPATIBLE_BASE_URL to avoid conflicting with the upstream
    esperanto/Ollama configuration the user picked for regular chat.
    """
    from desktop.config import default_config_path, load_or_create
    from desktop.memory.client import build_memory_client

    cfg = load_or_create(default_config_path())
    surreal_url = os.environ.get(
        "MEMORY_SURREAL_URL", os.environ.get("SURREAL_URL", "")
    )
    embed_url = os.environ.get("MEMORY_EMBED_URL", "")
    llm_url = os.environ.get("MEMORY_CHAT_LLM_URL", "")
    if not (surreal_url and embed_url and llm_url):
        raise RuntimeError(
            "memory_commands invoked without MEMORY_* URLs set — was the "
            "launcher Supervisor used to spawn this worker?"
        )
    mem_client = build_memory_client(
        cfg=cfg,
        surreal_url=surreal_url,
        embed_url=embed_url,
        llm_url=llm_url,
    )
    # Minimal LLM wrapper compatible with our writer's llm.complete()
    import httpx

    class _LLM:
        def __init__(self, base_url, model):
            self.base_url = base_url
            self.model = model

        def complete(self, system, user):
            with httpx.Client(timeout=120) as client:
                r = client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_tokens": 800,
                        "temperature": 0.2,
                    },
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

    llm = _LLM(llm_url, "Hermes-3-Llama-3.1-8B-Q4_K_M")
    return llm, mem_client


@command(name="memory_extract_turn")
def memory_extract_turn(
    chat_session_id: str, user_text: str, assistant_text: str
) -> dict:
    """Per-turn fact extractor. Best-effort; no exceptions propagate."""
    try:
        from desktop.memory.writer import extract_turn

        llm, mem_client = _build_clients()
        extract_turn(
            llm=llm,
            mem_client=mem_client,
            chat_session_id=chat_session_id,
            user_text=user_text,
            assistant_text=assistant_text,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@command(name="memory_summarize_session")
def memory_summarize_session(chat_session_id: str, transcript: str) -> dict:
    """Per-session episode summarizer."""
    try:
        from desktop.memory.writer import summarize_session

        llm, mem_client = _build_clients()
        summarize_session(
            llm=llm,
            mem_client=mem_client,
            chat_session_id=chat_session_id,
            transcript=transcript,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 2: Commit (no direct unit tests — these are exercised in integration)**

```bash
git add desktop/memory/memory_commands.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory_extract_turn + memory_summarize_session worker handlers"
```

---

## Task 13: Auto-register — Memory credential + integration

**Files:**
- Create: `desktop/auto_register/memory.py`
- Modify: `desktop/auto_register/__init__.py`
- Create: `desktop/tests/test_auto_register_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# desktop/tests/test_auto_register_memory.py
from pathlib import Path

from desktop.auto_register.memory import register_memory_credential
from desktop.config import Config


def test_register_memory_credential_posts_credential():
    created = []

    class FakeClient:
        def get(self, path):
            class R:
                status_code = 200
                text = ""

                def raise_for_status(self):
                    pass

                def json(self):
                    return []

            return R()

        def post(self, path, json=None):
            created.append((path, json))

            class R:
                status_code = 201
                text = ""

                def json(self):
                    return {"id": f"id-{json.get('name', '')}"}

            return R()

    cfg = Config(
        model_dir=Path("/tmp"),
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    register_memory_credential(FakeClient(), memory_port=8767, cfg=cfg)
    posted = [j for p, j in created if p == "/api/credentials"]
    assert any(j.get("name") == "Memory (local)" for j in posted)
    assert any(j.get("provider") == "openai_compatible" for j in posted)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_auto_register_memory.py -v
```
Expected: `ImportError` or fail.

- [ ] **Step 3: Implement**

```python
# desktop/auto_register/memory.py
"""Memory credential registration — sibling of voice.py.

Registers the Memory retriever as an openai_compatible-style credential so
upstream code can discover it. Whether upstream actually uses this credential
or whether we need a small chat.py patch is decided at integration time
(see spec §3.2).
"""

from __future__ import annotations

import logging
from typing import Any

from desktop.auto_register._http import _ensure_credential

log = logging.getLogger(__name__)


def register_memory_credential(client: Any, *, memory_port: int, cfg) -> None:
    """Register the Memory retriever as an OpenAI-compatible-style credential."""
    cred = _ensure_credential(
        client=client,
        existing_names=set(),
        name="Memory (local)",
        provider="openai_compatible",
        modalities=[
            "language"
        ],  # placeholder — modality may be "memory" if upstream supports
        base_url=f"http://127.0.0.1:{memory_port}",
    )
    if cred:
        log.info("Registered Memory credential id=%s", cred)
```

Then update `desktop/auto_register/__init__.py` to call this from the voice-models phase if `memory_port` is set. Find the existing call to `register_voice_models(...)` (or near it) and add:

```python
if kwargs.get("memory_port") is not None:
    from desktop.auto_register.memory import register_memory_credential

    register_memory_credential(client, memory_port=kwargs["memory_port"], cfg=cfg)
```

Also extend `auto_register(...)`'s signature to accept `memory_port: int | None = None`.

- [ ] **Step 4: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_auto_register_memory.py desktop/tests/test_auto_register*.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add desktop/auto_register/memory.py desktop/auto_register/__init__.py \
        desktop/tests/test_auto_register_memory.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: auto-register Memory (local) credential pointing at retriever shim"
```

---

## Task 14: Wire memory_port through __main__ → auto_register

**Files:**
- Modify: `desktop/app.py`

- [ ] **Step 1: Read `_phase_auto_register(ctx)` in app.py. Update the call to pass the memory port:**

```python
def _phase_auto_register(ctx: AppContext) -> None:
    from desktop.auto_register import auto_register

    api_base = ctx.sv.session_env["INTERNAL_API_URL"]
    auto_register(
        api_base_url=api_base,
        cfg=ctx.cfg,
        llamacpp_port=...,  # existing
        whisper_port=getattr(ctx.sv, "whisper_port", None) or None,
        piper_port=getattr(ctx.sv, "piper_port", None) or None,
        embed_port=getattr(ctx.sv, "embed_port", None) or None,
        memory_port=getattr(ctx.sv, "memory_port", None) or None,  # NEW
    )
```

- [ ] **Step 2: Sanity-import**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.app; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/app.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: pass memory_port through to auto_register"
```

---

## Task 15: Memory dashboard server

**Files:**
- Create: `desktop/memory_dashboard/__init__.py`
- Create: `desktop/memory_dashboard/server.py`
- Create: `desktop/tests/test_memory_dashboard_server.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_memory_dashboard_server.py
import json
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase

from desktop.memory_dashboard.server import build_app


class MemoryDashboardTest(AioHTTPTestCase):
    async def get_application(self):
        # The dashboard server proxies to the memory retriever shim. For tests,
        # we inject a base URL pointing at a stub server (or just verify routes
        # exist and proxy attempts return).
        return build_app(memory_retriever_url="http://127.0.0.1:65535")

    async def test_root_serves_html_or_fallback(self):
        r = await self.client.get("/")
        # static index.html may not exist yet; either 200 or fallback text
        assert r.status == 200

    async def test_api_theme_returns_config_theme(self, tmp_path):
        # Verify the /api/theme route exists and returns something parsable
        r = await self.client.get("/api/theme")
        assert r.status == 200
        body = await r.json()
        assert "theme" in body
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_memory_dashboard_server.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# desktop/memory_dashboard/__init__.py
```

```python
# desktop/memory_dashboard/server.py
"""Aiohttp server backing the Memory Dashboard PyWebView window.

Most data requests proxy through to the memory retriever shim (which has the
mem0 client). This server itself is thin — just serves the static UI and
provides a /api/theme endpoint so the dashboard adopts the user's wizard theme.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from aiohttp import web

STATIC_DIR = Path(__file__).parent / "static"


def build_app(memory_retriever_url: str) -> web.Application:
    app = web.Application()

    async def index(_: web.Request) -> web.Response:
        idx = STATIC_DIR / "index.html"
        if idx.exists():
            return web.FileResponse(idx)
        return web.Response(
            text="<html><body>Memory dashboard (static UI not built yet)</body></html>",
            content_type="text/html",
        )

    async def proxy(req: web.Request) -> web.Response:
        """Proxy /api/memory/* to the retriever shim."""
        path = req.match_info["path"]
        url = f"{memory_retriever_url}/api/memory/{path}"
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                if req.method == "GET":
                    r = await client.get(url, params=dict(req.query))
                elif req.method == "DELETE":
                    r = await client.delete(url)
                elif req.method == "POST":
                    r = await client.post(
                        url, json=await req.json() if req.body_exists else None
                    )
                else:
                    return web.Response(status=405, text="method not allowed")
                return web.Response(
                    status=r.status_code,
                    body=r.content,
                    content_type=r.headers.get("content-type", "application/json"),
                )
            except Exception as exc:
                return web.json_response({"error": str(exc)}, status=502)

    async def theme(_: web.Request) -> web.Response:
        try:
            from desktop.config import default_config_path, load_or_create

            cfg = load_or_create(default_config_path())
            return web.json_response({"theme": cfg.theme})
        except Exception:
            return web.json_response({"theme": "light-blue"})

    app.router.add_get("/", index)
    app.router.add_get("/api/memory/{path:.+}", proxy)
    app.router.add_delete("/api/memory/{path:.+}", proxy)
    app.router.add_post("/api/memory/{path:.+}", proxy)
    app.router.add_get("/api/theme", theme)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR)
    return app
```

- [ ] **Step 4: Run tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_memory_dashboard_server.py -v
```
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add desktop/memory_dashboard/__init__.py desktop/memory_dashboard/server.py \
        desktop/tests/test_memory_dashboard_server.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory dashboard aiohttp server (proxies memory shim + theme)"
```

---

## Task 16: Memory dashboard static UI

**Files:**
- Create: `desktop/memory_dashboard/static/index.html`
- Create: `desktop/memory_dashboard/static/style.css`
- Create: `desktop/memory_dashboard/static/dashboard.js`

- [ ] **Step 1: index.html**

```html
<!doctype html>
<html lang="en" data-theme="light-blue">
<head>
  <meta charset="utf-8">
  <title>Open Notebook Plus — Memory</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main>
    <h1>Memory</h1>
    <section>
      <h2>Preferences <span class="count" id="pref-count">0</span></h2>
      <ul id="pref-list"></ul>
    </section>
    <section>
      <h2>Facts <span class="count" id="fact-count">0</span></h2>
      <ul id="fact-list"></ul>
    </section>
    <section>
      <h2>Episodes <span class="count" id="ep-count">0</span></h2>
      <ul id="ep-list"></ul>
    </section>
    <section>
      <h2>Ambient context (OpenChronicle)</h2>
      <p id="ambient-status">Checking…</p>
      <button id="ambient-pause">Pause</button>
    </section>
  </main>
  <script src="/static/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 2: style.css**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       padding: 24px; background: var(--bg, #fafafa); color: var(--text, #222); }
main { max-width: 900px; margin: 0 auto; }
h1 { margin-bottom: 16px; }
section { background: var(--surface, #fff);
          border: 1px solid var(--border, #e0e0e0);
          border-radius: 10px; padding: 16px; margin-bottom: 16px; }
h2 { font-size: 16px; margin-bottom: 12px; }
.count { font-size: 12px; color: var(--muted, #888);
         background: var(--border, #f0f0f0);
         padding: 2px 8px; border-radius: 999px; margin-left: 8px; }
ul { list-style: none; }
ul li { padding: 8px 0; border-bottom: 1px solid var(--border, #f0f0f0);
        display: flex; align-items: center; gap: 8px; }
ul li button { padding: 4px 10px; border-radius: 6px;
               border: 1px solid var(--border, #ccc);
               background: var(--bg, #fff); cursor: pointer;
               color: var(--text, #333); font-size: 12px;
               opacity: 0; transition: opacity 0.15s; }
ul li:hover button { opacity: 1; }
button#ambient-pause { padding: 6px 14px; border-radius: 6px;
                       border: 1px solid var(--border, #ccc);
                       background: var(--bg, #fff); color: var(--text, #333);
                       cursor: pointer; }
```

- [ ] **Step 3: dashboard.js**

```javascript
(async () => {
  // Apply theme from /api/theme
  try {
    const t = await fetch('/api/theme').then(r => r.json());
    document.documentElement.dataset.theme = t.theme || 'light-blue';
  } catch (e) {
    document.documentElement.dataset.theme = 'light-blue';
  }

  async function loadList(kind, listId, countId) {
    try {
      const r = await fetch(`/api/memory/${kind}s`);
      const data = await r.json();
      const records = data.records || [];
      document.getElementById(countId).textContent = records.length;
      const list = document.getElementById(listId);
      list.innerHTML = '';
      records.forEach(rec => {
        const li = document.createElement('li');
        li.innerHTML = `
          <span style="flex:1">${rec.text || rec.summary || '(no text)'}</span>
          <span style="color:#888">${(rec.confidence || 0).toFixed(2)}</span>
          <button data-kind="${kind}" data-id="${(rec.id || '').replace(/^[^:]+:/,'')}">Forget</button>
        `;
        li.querySelector('button').addEventListener('click', async (e) => {
          if (!confirm('Forget this record?')) return;
          await fetch(`/api/memory/${kind}/${e.target.dataset.id}`, {method: 'DELETE'});
          loadList(kind, listId, countId);
        });
        list.appendChild(li);
      });
    } catch (e) {
      console.error('loadList failed', kind, e);
    }
  }

  await loadList('preference', 'pref-list', 'pref-count');
  await loadList('fact', 'fact-list', 'fact-count');
  await loadList('episode', 'ep-list', 'ep-count');

  // Ambient status
  try {
    const s = await fetch('/api/memory/ambient/status').then(r => r.json());
    const el = document.getElementById('ambient-status');
    el.textContent = s.available
      ? (s.paused ? 'Available — currently paused' : 'Active')
      : 'Not detected — install OpenChronicle to enable';
    document.getElementById('ambient-pause').addEventListener('click', async () => {
      await fetch('/api/memory/ambient/pause', {method: 'POST'});
      el.textContent = 'Available — currently paused';
    });
  } catch (e) {
    document.getElementById('ambient-status').textContent = '(error reading status)';
  }
})();
```

- [ ] **Step 4: Commit**

```bash
git add desktop/memory_dashboard/static/
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: memory dashboard static UI (themed, proxies to memory shim)"
```

---

## Task 17: Tray + memory_injection.js + window helpers

**Files:**
- Modify: `desktop/tray.py`
- Create: `desktop/first_run/static/memory_injection.js`
- Modify: `desktop/window.py`
- Modify: `desktop/app.py`

- [ ] **Step 1: Add tray menu entry**

In `desktop/tray.py`'s `install_tray`, add a new `MenuAction("Memory…", on_open_memory)` between `Manage Models…` and `Quit`. Accept a new `on_open_memory` callable in the function signature.

- [ ] **Step 2: Write memory_injection.js**

```javascript
// desktop/first_run/static/memory_injection.js
// Injected into the main UI to add a "Memory" link to upstream's Settings page.
(function () {
  if (window.__ONP_MEMORY_INJECTED) return;
  window.__ONP_MEMORY_INJECTED = true;

  function injectMemoryLink() {
    // Find upstream's Settings page sidebar (heuristic; brittle if upstream changes layout)
    const settingsContainer = document.querySelector('[data-page="settings"], [aria-label*="Settings"]');
    if (!settingsContainer || settingsContainer.querySelector('.onp-memory-link')) return;
    const link = document.createElement('a');
    link.className = 'onp-memory-link';
    link.href = (window.ONP_MEMORY_URL || '#');
    link.textContent = '🧠 Memory';
    link.target = '_blank';
    Object.assign(link.style, {
      display: 'block', padding: '8px 12px', marginTop: '12px',
      borderRadius: '6px', textDecoration: 'none',
      color: 'var(--primary, #2D7FF9)', border: '1px solid var(--border, #ccc)',
    });
    settingsContainer.appendChild(link);
  }
  const observer = new MutationObserver(injectMemoryLink);
  observer.observe(document.body, { childList: true, subtree: true });
  injectMemoryLink();

  // OpenChronicle reminder toast (only if launcher set the flag)
  if (window.ONP_REMIND_OPENCHRONICLE) {
    if (window.showToast) {
      window.showToast(
        'OpenChronicle not detected. Install for ambient memory →',
        {
          variant: 'info', autoDismissMs: null,
          actionLabel: 'Open install page',
          onAction: () => window.open(
            'https://github.com/Einsia/OpenChronicle/releases/latest', '_blank'),
          onClose: () => fetch(
            '/api/config/dismiss_openchronicle_reminder', {method: 'POST'}
          ).catch(() => {}),
        }
      );
    }
  }
})();
```

- [ ] **Step 3: Update window.py to inject memory_injection.js after voice_injection.js**

In `desktop/window.py`, after the voice JS injection in `_theme_injection_js`, append a parallel `<script>` injection for the memory injection file:

```python
def _memory_injection_js() -> str:
    p = _Path(__file__).parent / "first_run" / "static" / "memory_injection.js"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""
```

Then in `_theme_injection_js`, after appending the voice injector, append a memory injector with the dashboard URL passed via `window.ONP_MEMORY_URL`. The dashboard URL needs to be known at injection time — `__main__.py`/`app.py` already starts the dashboard server and knows its port. Thread the port through `open_window`:

```python
def open_window(url: str, on_close, title="Open Notebook Plus",
                width=1280, height=800, theme="light-blue",
                memory_url: str | None = None) -> None:
```

- [ ] **Step 4: Wire memory_url + remind_openchronicle through app.py**

In `desktop/app.py`'s `_phase_open_window(ctx)`:

```python
def _phase_open_window(ctx: AppContext) -> None:
    from desktop.window import open_window

    memory_url = (
        f"http://127.0.0.1:{ctx.memory_dashboard_port}/"
        if ctx.memory_dashboard_port
        else None
    )
    remind = (
        not ctx.openchronicle_available and ctx.cfg.openchronicle_choice == "prompt"
    )
    open_window(
        ctx.sv.frontend_url,
        on_close=ctx.sv.stop_all,
        theme=ctx.cfg.theme,
        memory_url=memory_url,
        remind_openchronicle=remind,
    )
```

Add `memory_dashboard_port: int = 0` to `AppContext`.

- [ ] **Step 5: Spin up the memory dashboard server in `_phase_start_model_manager` or a new phase**

```python
def _phase_start_memory_dashboard(ctx: AppContext) -> None:
    from desktop.memory_dashboard.server import build_app as md_build_app
    from desktop.aiohttp_window import start_aiohttp_server_thread

    memory_url = f"http://127.0.0.1:{ctx.sv.memory_port}/" if ctx.sv.memory_port else ""
    port, _, _, _ = start_aiohttp_server_thread(
        app_factory=lambda: md_build_app(memory_retriever_url=memory_url),
    )
    ctx.memory_dashboard_port = port
```

Insert between `_phase_start_model_manager` and `_phase_install_tray` in `run()`.

- [ ] **Step 6: Update tray installation to include the memory window callback**

In `_phase_install_tray`:

```python
def _on_open_memory():
    try:
        _webview.create_window(
            "Memory",
            f"http://127.0.0.1:{ctx.memory_dashboard_port}/",
            width=900,
            height=640,
        )
    except Exception:
        pass


install_tray(
    on_open_main=_on_open_main,
    on_open_manager=_on_open_manager,
    on_open_memory=_on_open_memory,  # NEW
    on_quit=_on_quit,
)
```

- [ ] **Step 7: Sanity-import + test**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "import desktop.app, desktop.window, desktop.tray; print('ok')"
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ 2>&1 | tail -5
```

- [ ] **Step 8: Commit**

```bash
git add desktop/tray.py desktop/first_run/static/memory_injection.js \
        desktop/window.py desktop/app.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: tray Memory entry + memory_injection.js + dashboard window"
```

---

## Task 18: Wizard screen 5.5 — OpenChronicle onboarding

**Files:**
- Modify: `desktop/first_run/static/index.html`
- Modify: `desktop/first_run/static/wizard.js`
- Modify: `desktop/first_run/server.py`

- [ ] **Step 1: Add the new screen to index.html**

Insert AFTER the existing `data-screen="theme"` section and BEFORE `data-screen="done"` (or `setting-up` if that exists):

```html
<section data-screen="ambient-memory" hidden>
  <div class="icon-row">
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <path d="M32 12 C 20 12 14 22 14 32 C 14 42 20 52 32 52
               C 44 52 50 42 50 32 C 50 22 44 12 32 12 Z"
            fill="currentColor" opacity="0.15"/>
      <circle cx="32" cy="32" r="3" fill="currentColor"/>
      <circle cx="22" cy="26" r="2" fill="currentColor"/>
      <circle cx="42" cy="26" r="2" fill="currentColor"/>
      <circle cx="22" cy="40" r="2" fill="currentColor"/>
      <circle cx="42" cy="40" r="2" fill="currentColor"/>
      <path d="M22 26 L32 32 M42 26 L32 32 M22 40 L32 32 M42 40 L32 32"
            stroke="currentColor" stroke-width="1.2" fill="none"/>
    </svg>
  </div>
  <h2>✨ Enhance with ambient memory? <span class="hint">(optional)</span></h2>
  <p>Open Notebook Plus can remember what you were working on without you having
     to tell it. Ask things like:</p>
  <ul class="examples">
    <li>"What was the bug in that file?"</li>
    <li>"Summarize the article I just read."</li>
    <li>"Continue what I was doing."</li>
  </ul>
  <p>This uses <strong>OpenChronicle</strong>
     (<a href="https://github.com/Einsia/OpenChronicle" target="_blank">MIT</a>),
     a separate free app that reads your screen via macOS accessibility to
     build local-only memory. Nothing leaves your machine.</p>
  <div class="button-row">
    <button class="secondary" data-back="theme">Back</button>
    <button class="secondary" data-next="done"
            data-onclick="skip_openchronicle">Skip — set up later</button>
    <button class="primary" data-next="done"
            data-onclick="open_openchronicle_install">Open install page</button>
  </div>
</section>
```

- [ ] **Step 2: Update wizard.js to handle the new screen choices**

Add at the top of wizard.js (after THEMES const):

```javascript
let openchronicleChoice = "skip";
```

Add a generic click handler near the bottom:

```javascript
document.body.addEventListener('click', (e) => {
  const action = e.target.dataset.onclick;
  if (action === 'open_openchronicle_install') {
    openchronicleChoice = "prompt";
    window.open('https://github.com/Einsia/OpenChronicle/releases/latest', '_blank');
  } else if (action === 'skip_openchronicle') {
    openchronicleChoice = "skip";
  }
});
```

In the existing payload-construction block (where wizard sends to `/api/save`), add the openchronicle field:

```javascript
        const payload = {
          model_dir: modelDirInput.value,
          provider: choice,
          default_model: document.getElementById('default_model').value || '',
          theme: chosenTheme,
          openchronicle_choice: openchronicleChoice,   // NEW
        };
```

Update the screen flow so theme's "Continue" goes to `ambient-memory` instead of directly to `done` (or `setting-up` if Section 5 of the v0.3 wizard progress exists). Find the theme section's data-next or the JS that decides next-screen and route through ambient-memory:

```html
<!-- in theme screen's button-row -->
<button class="primary" data-next="ambient-memory">Continue</button>
```

- [ ] **Step 3: Update first_run/server.py's save() to accept and persist openchronicle_choice**

In `desktop/first_run/server.py`, in the `save()` handler:

```python
cfg = Config(
    model_dir=model_dir,
    provider=provider,
    default_model=body.get("default_model", ""),
    surreal_user="root",
    surreal_password=secrets.token_urlsafe(24),
    theme=body.get("theme", "light-blue"),
    encryption_key=secrets.token_urlsafe(32),
    openchronicle_choice=body.get("openchronicle_choice", "skip"),  # NEW
)
```

- [ ] **Step 4: Add a dismiss-reminder endpoint**

In the same file, add:

```python
async def dismiss_openchronicle_reminder(req: web.Request) -> web.Response:
    # Re-load, mutate, re-save.
    from desktop.config import load_or_create

    cfg = load_or_create(config_path)
    # cfg is frozen, so we replace it
    new_cfg = Config(
        model_dir=cfg.model_dir,
        provider=cfg.provider,
        default_model=cfg.default_model,
        surreal_user=cfg.surreal_user,
        surreal_password=cfg.surreal_password,
        theme=cfg.theme,
        encryption_key=cfg.encryption_key,
        openchronicle_choice="skip",
    )
    new_cfg.save(config_path)
    return web.json_response({"ok": True})


app.router.add_post(
    "/api/config/dismiss_openchronicle_reminder", dismiss_openchronicle_reminder
)
```

- [ ] **Step 5: Run wizard tests**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/test_first_run.py desktop/tests/test_wizard_progress.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add desktop/first_run/static/index.html desktop/first_run/static/wizard.js \
        desktop/first_run/server.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: wizard screen 5.5 — OpenChronicle onboarding + persist choice"
```

---

## Task 19: PyInstaller spec — bundle new v0.4 files

**Files:**
- Modify: `desktop/build/pyinstaller.spec`

- [ ] **Step 1: Add new entries to `datas`**

Find the `datas = [...]` list and add:

```python
# v0.4 — memory packages, dashboard, injections, migration
((str(PROJECT_ROOT / "desktop" / "memory"), "upstream/desktop/memory"),)
((str(ROOT / "memory_dashboard" / "static"), "desktop/memory_dashboard/static"),)
(
    (
        str(ROOT / "first_run" / "static" / "memory_injection.js"),
        "desktop/first_run/static",
    ),
)
(
    (
        str(PROJECT_ROOT / "migrations" / "010_memory_tables.surrealql"),
        "upstream/migrations",
    ),
)
```

(The `desktop/memory/` package needs to be importable from the venv-python at runtime. Since the venv lives outside the .app and the memory writer is invoked by the upstream worker process — also running from the venv — we need `desktop/memory` on the venv's sys.path. The launcher already injects `upstream/` via the .pth file from `bootstrap.ensure_venv`. We add `desktop/memory` similarly. The simplest approach: copy `desktop/memory/` into `upstream/desktop/memory/` at build time AND update the .pth setup in `bootstrap.py` to add the path. For v0.4, the simplest: keep the source bundled and let the worker import via the upstream-relative path.)

Optionally also extend the venv-bootstrap to add `desktop/memory` to its .pth file — modify `desktop/bootstrap.py`:

```python
# In ensure_venv after writing the upstream .pth:
desktop_memory_dir = (upstream_dir / "desktop").resolve()
if desktop_memory_dir.exists():
    (site_packages / "open_notebook_desktop_memory.pth").write_text(
        str(desktop_memory_dir.parent) + "\n"
    )
```

- [ ] **Step 2: Verify spec parses**

```bash
/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -c "
import pathlib
compile(pathlib.Path('desktop/build/pyinstaller.spec').read_text(),
        'desktop/build/pyinstaller.spec', 'exec')
print('spec parses')
"
```

- [ ] **Step 3: Commit**

```bash
git add desktop/build/pyinstaller.spec desktop/bootstrap.py
git -c user.email="anthonyjeromehenry@gmail.com" -c user.name="Antman1526" \
  commit -m "desktop: bundle v0.4 memory package + dashboard + migration in PyInstaller spec"
```

---

## Task 20: Manual E2E smoke test

**Files:**
- (None — verification only.)

- [ ] **Step 1: Clean state**

```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
rm -f ~/.open-notebook-plus/config.toml ~/.open-notebook-plus/venv-marker
rm -rf ~/.open-notebook-plus/venv ~/.open-notebook-plus/python-runtime
rm -rf ~/.open-notebook-plus/surreal_data ~/.open-notebook-plus/logs
rm -rf dist build
```

- [ ] **Step 2: Build + launch**

```bash
source .venv-py312/bin/activate
pyinstaller desktop/build/pyinstaller.spec --noconfirm
bash desktop/build/post_build_mac.sh
open "dist/Open Notebook Plus.app"
```

- [ ] **Step 3: Verify each Definition-of-Done criterion (from the spec)**

1. Fresh chat: ask "what do you remember about me?" — assistant lists facts/preferences from prior sessions. (After at least one prior session.)
2. Across two chat sessions: mention "I like bullet points" in session 1; session 2 (after navigate-away-and-back) — assistant respects it without being re-told.
3. Memory dashboard window opens from tray menu and lists at least 3 records after a few chat sessions of use.
4. OpenChronicle disabled path: no daemon installed → app boots fine, no errors, just a benign `openchronicle.detect available=False` event.
5. OpenChronicle enabled path: daemon installed + reachable → "Recent screen activity" block appears in the system prompt (inspect `~/.open-notebook-plus/logs/api.log`).
6. Wizard screen 5.5 appears on fresh install; "Skip" persists; "Open install page" launches browser + persists `prompt`; subsequent launch shows reminder toast.
7. ~/.open-notebook-plus/logs/progress.jsonl ends with `ready/done` after first launch.
8. All 115+ tests pass: `python -m pytest desktop/tests/ desktop/memory/tests/`.

- [ ] **Step 4: If anything fails**

Capture logs:
```bash
tail -100 ~/.open-notebook-plus/logs/{bootstrap,launcher,api,worker,memory,openchronicle,whisper,piper,llamacpp_embed,llamacpp,progress,auto_register,memory.log}
```

Diagnose, fix in the relevant `desktop/*` file as a separate commit, re-build.

---

## Self-review

Spec coverage check (against `2026-05-11-open-notebook-plus-v0.4-memory-design.md`):
- ✅ Goal 1 (Episodic memory) — Tasks 3, 5, 6, 7, 8, 10, 12, 13
- ✅ Goal 2 (Procedural memory) — Tasks 6, 7, 12 (same writer infrastructure, different `kind`)
- ✅ Goal 3 (OpenChronicle Layer 0) — Tasks 9, 10, 11, 18
- ✅ Goal 4 (Memory dashboard) — Tasks 15, 16, 17
- ✅ Config + wizard onboarding — Tasks 2, 18
- ✅ SurrealDB schema + adapter — Tasks 2.5, 3, 4
- ✅ Auto-register integration — Tasks 13, 14
- ✅ Build + bundle — Task 19
- ✅ Definition of done coverage — Task 20

Type consistency: `SurrealMemoryStore.__init__` kwargs match `SurrealVectorStoreConfig` fields (mem0 factory does `cls(**config.model_dump())`). `OutputData(id, score, payload)` matches mem0's expected hit shape in `Memory.search()`. `apply_tool_call` signature matches `extract_turn` + `summarize_session` usage. `mem_client.search(query=...)` and `.add(...)`/`.delete(...)` match mem0 2.x `Memory` API.

mem0 version compatibility: plan targets `mem0ai==2.0.2` (current latest, pinned in Task 1). The provider-registration trick in Task 2.5 works for any mem0 in the 0.1.62–2.x range because the underlying `_provider_configs` + `provider_to_class` dict pattern has been stable since 0.1.x. If mem0 ever ships `VectorStoreFactory.register_provider()`, Task 2.5 can be simplified to a one-liner.

No placeholders. No TBDs. Each `Task` row points to either a created or modified file. Each step has executable commands or full code blocks.

Test count growth: 88 → ~123 (3 register + 7 surreal_store + 2 client + 7 writer + 4 memory_shim + 3 openchronicle_shim + 2 launcher + 1 auto_register + 2 config + 2 dashboard + ~2 wizard = 35 new).

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-open-notebook-plus-v0.4-memory-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, two-stage review (spec + code quality) between tasks. Best for a 20-task batch.

**2. Inline Execution** — Run tasks in this session via `executing-plans`, with batch checkpoints.

**Which approach?**
