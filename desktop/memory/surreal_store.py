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

# v0.8.50 — defensive mem0 import (mirrors desktop/memory/client.py). The
# worker venv has mem0 installed, so this resolves to the real abstract base
# in production. The dev/test venv does NOT ship mem0; falling back to `object`
# keeps this module importable there so the pure store logic (prune/count/
# query-shape) is unit-testable without standing up the whole mem0 stack.
try:
    from mem0.vector_stores.base import VectorStoreBase
except ImportError:  # pragma: no cover - exercised only in mem0-less envs
    VectorStoreBase = object  # type: ignore[assignment,misc]
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
            t = threading.Thread(
                target=loop.run_forever, name="surreal-async-loop", daemon=True
            )
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
            # v0.8.66 (audit C1) — read the keys mem0 ACTUALLY emits. With
            # infer=False (the writer's mode since v0.8.66), mem0's _create_memory
            # stores the verbatim message under the payload key `data` and FLATTENS
            # the caller's metadata (kind/scope/confidence/…) to the payload's top
            # level — there is no nested `metadata` sub-dict. The previous code read
            # `payload["text"]` (never set → every row stored text="") and
            # `payload["metadata"]["scope"]` (never set → every row stored
            # scope="user"), which silently inerted the entire memory subsystem.
            # Order: mem0's `data` first, then a legacy/top-level `text`, then "".
            _meta = payload.get("metadata", {}) or {}
            text_val = payload.get("data") or payload.get("text", "")
            scope_val = payload.get("scope") or _meta.get("scope", "user")
            confidence_val = payload.get("confidence", _meta.get("confidence", 1.0))
            # Preserve the non-bulky metadata for recall filters. Drop `data`
            # (held in `text`) and the raw embedding to avoid duplicating storage.
            stored_meta = {
                k: v
                for k, v in payload.items()
                if k not in ("data", "text", "embedding")
            }
            if _meta:
                # Back-compat: if a caller ever DID nest a metadata dict, fold it in.
                stored_meta = {**_meta, **stored_meta}
            row = {
                "text": text_val,
                "embedding": vec,
                "metadata": stored_meta,
                "scope": scope_val,
                "confidence": confidence_val,
                # v0.8.66 (audit H5) — store a NATIVE datetime object, not an
                # ISO string. Migration 15 defines these tables SCHEMAFULL with
                # `created_at TYPE datetime DEFAULT time::now()`. The surrealdb
                # client's CBOR encoder only tags a real `datetime` as a Surreal
                # datetime; a `str` is sent as CBOR text, which SurrealDB v2
                # strictly REJECTS for a TYPE datetime field — the CREATE then
                # hard-fails and the writer's broad except silently drops the
                # fact. A tz-aware datetime serializes correctly. (Omitting the
                # key entirely would also work via the schema DEFAULT, but an
                # explicit value is deterministic and unit-testable.)
                "created_at": datetime.now(timezone.utc),
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
                f"SELECT *, vector::similarity::cosine(embedding, $q) AS score "  # nosec B608
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
        rows = self._exec(f"SELECT * FROM {vid}")  # nosec B608
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
            rows = self._exec(f"SELECT * FROM {table} LIMIT $limit", {"limit": limit})  # nosec B608
            for row in rows or []:
                out.append(self._to_output(row))
        return out

    # ---------------------------------------------------------- retention (v0.8.50)

    def count(self, table: str) -> int:
        """v0.8.50 — row count for one memory table (cheap indexed
        aggregate). Used as the high-water gate before a full prune so the
        per-turn writer path doesn't pay a select-all every turn.

        v0.8.98 — this is the ONLY method here that interpolates a
        caller-supplied identifier; every other query builds its table name
        from the `_ALL_TABLES` / `_KIND_TO_TABLE` constants. Callers happen to
        pass whitelisted names today, but the repository's SurrealQL contract
        requires identifiers be validated by construction, not by convention —
        and the B608 suppression below asserts that. Enforce it here so the
        assertion is true no matter who calls this next.
        """
        if table not in _ALL_TABLES:
            raise ValueError(f"unknown memory table: {table!r}")
        self._ensure_connected()
        rows = self._exec(f"SELECT count() AS n FROM {table} GROUP ALL")  # nosec B608
        if rows and isinstance(rows[0], dict):
            return int(rows[0].get("n") or 0)
        return 0

    def prune(self, keep_per_table: int) -> dict[str, int]:
        """v0.8.50 — retention ceiling. For each memory table keep the
        newest `keep_per_table` rows (by `created_at`) and delete the rest.
        Returns {table: n_deleted}. Closes Finding #3 (the `memory_*`
        tables grew without bound — recall caps RESULTS, never ROWS).

        Query shape is deliberate and avoids two SurrealDB traps:
          * NOT `SELECT VALUE id … ORDER BY created_at` — the
            "missing order idiom" rejection that silently broke recall
            across v0.8.19→v0.8.29. The ORDER BY field MUST be in the
            projection, so we select `id, created_at`.
          * NOT a `WHERE id NOT IN (subquery)` complement — fragile when
            the keep-set is empty. We slice survivors off in Python and
            delete the remainder with the safe `DELETE … WHERE id IN $ids`
            idiom (same one the v0.7.184 notebook-delete cascade uses).
        """
        self._ensure_connected()
        keep = max(0, int(keep_per_table))
        deleted: dict[str, int] = {}
        for table in _ALL_TABLES:
            # v0.8.66 (audit MEM-2) — order by recency PRIMARY, confidence as the
            # tie-breaker, so the persisted confidence (v0.8.55) finally
            # influences eviction: among rows of the same age the higher-
            # confidence ones are kept. Recency stays primary (no behavior change
            # for distinct timestamps). `confidence` is added to the projection
            # because the ORDER BY field must be selected (the "missing order
            # idiom" trap noted above).
            rows = (
                self._exec(
                    f"SELECT id, created_at, confidence FROM {table} "  # nosec B608
                    "ORDER BY created_at DESC, confidence DESC"
                )
                or []
            )
            # rows[:keep] are the newest survivors; rows[keep:] are evicted.
            old_ids = [
                r["id"]
                for r in rows[keep:]
                if isinstance(r, dict) and r.get("id") is not None
            ]
            if old_ids:
                # Batch very large eviction lists so a first-run prune on a
                # huge table doesn't build a pathological IN clause.
                for i in range(0, len(old_ids), 1000):
                    self._exec(
                        f"DELETE {table} WHERE id IN $ids",
                        {"ids": old_ids[i : i + 1000]},
                    )
            deleted[table] = len(old_ids)
        return deleted

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
