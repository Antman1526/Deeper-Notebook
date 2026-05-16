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
import re
from datetime import datetime, timezone
from typing import Any, Optional

from mem0.vector_stores.base import VectorStoreBase
from pydantic import BaseModel

# vector_id (mem0's `memory_id`) is interpolated into SurrealQL via f-strings
# in delete()/get()/update(). Surreal's record-id syntax (`table:thing`) doesn't
# accept naked $-parameters in `FROM`/`DELETE`/`UPDATE` positions in older
# Surreal versions, so we defend against injection by whitelisting the shape.
#
# The `id` portion accepts any character EXCEPT whitespace, quotes, semicolons,
# parentheses, and angle brackets — the actual SurrealQL injection vectors.
# This is deliberately broad enough to accept mem0-generated record IDs which
# can contain periods (timestamps like 01HF9G2K8M.x9z), hyphens (UUIDs), and
# unicode (P1-HIGH-06 audit fix — previous `[A-Za-z0-9_\-]+` rejected mem0's
# real IDs and broke .delete()/.update() in production).
_VALID_VECTOR_ID = re.compile(
    r"^(memory_fact|memory_preference|memory_episode):[^\s'\";(){}<>]+$"
)


def _validate_vector_id(vector_id: Any) -> str:
    """Return `vector_id` as str if it matches our record-id whitelist.

    Raises ValueError otherwise. Public so memory_shim/dashboard tests can
    exercise the same gate.
    """
    s = str(vector_id)
    if not _VALID_VECTOR_ID.match(s):
        raise ValueError(f"Invalid vector_id (must be memory_<kind>:<id>): {s!r}")
    return s

# ---------------------------------------------------------- sync/async bridge
#
# mem0's VectorStoreBase methods are sync, but surrealdb's Python client is
# async-only. Naive bridges break:
#   - `asyncio.get_event_loop().run_until_complete(...)` no longer auto-creates
#     a loop on Python 3.14's main thread.
#   - `asyncio.run(...)` raises RuntimeError if a loop is already running
#     in the caller's thread (which Task 8's FastAPI shim guarantees).
#
# We run a single daemon thread carrying its own loop for the lifetime of
# the process; sync callers submit coroutines to it.

import threading

_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_loop_lock = threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop
    with _bg_loop_lock:
        if _bg_loop is None or _bg_loop.is_closed():
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=loop.run_forever, name="surreal-async-loop",
                                 daemon=True)
            t.start()
            _bg_loop = loop
        return _bg_loop


def _run_async(coro):
    """Run a coroutine on the dedicated background loop and block on its result.

    Safe to call from both sync code AND from inside an existing event loop
    (e.g. a FastAPI handler) because the bg loop is in a different thread.
    """
    fut = asyncio.run_coroutine_threadsafe(coro, _get_bg_loop())
    return fut.result()


class OutputData(BaseModel):
    id: Optional[str]
    score: Optional[float]
    payload: Optional[dict]


from desktop.memory.constants import (
    ALL_MEMORY_TABLES as _ALL_TABLES,
)
from desktop.memory.constants import (
    KIND_TO_TABLE as _KIND_TO_TABLE,
)


class SurrealMemoryStore(VectorStoreBase):
    """mem0 vector-store adapter for SurrealDB.

    Constructed by mem0's `VectorStoreFactory` as
    `SurrealMemoryStore(**SurrealVectorStoreConfig.model_dump())`.
    For tests, use the `from_test_client` classmethod with a mock client.
    """

    def __init__(self, *,
                 collection_name: str = "memory",
                 embedding_model_dims: int = 768,
                 surreal_url: str,
                 namespace: str = "open_notebook",
                 database: str = "open_notebook",
                 user: str,
                 password: str):
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
        _run_async(self._client.signin({"user": user, "pass": password}))
        _run_async(self._client.use(ns, db))
        self._connected = True

    def _table(self, payload: dict) -> str:
        return _KIND_TO_TABLE.get(payload.get("kind", "fact"), "memory_fact")

    def _exec(self, sql: str, vars: dict | None = None):
        """Execute a SurrealQL query, supporting sync (mock) + async (real) clients."""
        result = self._client.query(sql, vars)
        if asyncio.iscoroutine(result):
            result = _run_async(result)
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

    def search(self, query: str, vectors, top_k: int = 5,
               filters: dict | None = None) -> list[OutputData]:
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
        vid = _validate_vector_id(vector_id)
        self._exec(f"DELETE {vid}")

    def update(self, vector_id, vector=None, payload=None):
        self._ensure_connected()
        vid = _validate_vector_id(vector_id)
        patch: dict[str, Any] = {}
        if payload is not None:
            for k in ("text", "confidence", "metadata"):
                if k in payload:
                    patch[k] = payload[k]
        if vector is not None:
            patch["embedding"] = vector
        if patch:
            self._exec(f"UPDATE {vid} MERGE $patch", {"patch": patch})

    def get(self, vector_id) -> OutputData | None:
        self._ensure_connected()
        vid = _validate_vector_id(vector_id)
        rows = self._exec(f"SELECT * FROM {vid}")
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

    def keyword_search(self, query: str, top_k: int = 5,
                       filters: dict | None = None):
        """BM25 / FTS not wired in v0.4. Returning None tells mem0 to skip
        hybrid scoring and rely on vector search alone."""
        return None
