# 13. Performance Optimization & Caching

This document is the exhaustive, code-grounded reference for every performance
and caching mechanism in **Open Notebook Plus**. Each section cites the real
source file and line range so the behavior can be recreated exactly.

> **Version baseline** (from `pyproject.toml`): app `v1.8.5`,
> `fastapi>=0.104.0`, `langgraph>=1.0.10`, `surrealdb>=1.0.4`,
> `pydantic>=2.9.2`, `esperanto>=2.20.0,<3`. Frontend (`frontend/package.json`):
> `next ^16.2.3`, `react ^19.2.3`, `@tanstack/react-query ^5.83.0`,
> `@tanstack/react-virtual ^3.13.24`.

---

## 13.1 SurrealDB HNSW Vector Indexes (Migrations)

Semantic search performance hinges on SurrealDB's built-in **HNSW**
(Hierarchical Navigable Small World) approximate-nearest-neighbor indexes. They
are created by `.surrealql` migrations under
`open_notebook/database/migrations/` and auto-applied on API startup.

### Embedding dimension: 768

Every embedding column is indexed at **`DIMENSION 768`** — the output size of
`nomic-embed-text-v1.5`, the default local embedder.

`open_notebook/database/migrations/21.surrealql` (lines 3-5) — the canonical
HNSW index definitions for the three searchable content tables:

```sql
-- Migration 21: Add HNSW vector indexes for source_embedding, source_insight,
-- and note tables, and update fn::vector_search to use the KNN operator.

DEFINE INDEX IF NOT EXISTS source_embedding_hnsw ON source_embedding FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX IF NOT EXISTS source_insight_hnsw   ON source_insight   FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX IF NOT EXISTS note_hnsw             ON note             FIELDS embedding HNSW DIMENSION 768;
```

The memory layer (`open_notebook/database/migrations/15.surrealql`, lines 13-50)
defines three more identically-shaped tables, each with its own HNSW index:

```sql
-- 15.surrealql — Open Notebook Plus v0.4 memory layer tables.
-- HNSW index DIMENSION 768 = nomic-embed-text-v1.5's output size.
-- v0.7.177 — Added IF NOT EXISTS to every DEFINE so this migration is re-run-safe.

DEFINE TABLE IF NOT EXISTS memory_fact SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS embedding  ON memory_fact TYPE array<float>;
DEFINE INDEX IF NOT EXISTS memory_fact_embedding ON memory_fact
    FIELDS embedding HNSW DIMENSION 768;
-- ... identical blocks for memory_preference and memory_episode
```

### Re-run safety

Every `DEFINE TABLE` / `DEFINE FIELD` / `DEFINE INDEX` uses `IF NOT EXISTS`
(the `v0.7.177` note in migration 15 explains the gap that was being closed).
This makes migrations idempotent: re-running a migration on a populated DB is a
no-op rather than a destructive rebuild.

### Migration discovery & application

`open_notebook/database/async_migrate.py` autodiscovers `*.surrealql` files
(`AsyncMigrationManager._discover_migrations`, lines ~110-186). It enforces
**contiguous numbering 1..N** — a missing `4.surrealql` raises rather than
silently skipping, which would corrupt the version counter:

```python
missing = [n for n in range(1, max_n + 1) if n not in ups_by_n]
# ... raises if any gap exists
ups   = [ups_by_n[n] for n in range(1, max_n + 1)]
downs = [downs_by_n.get(n) for n in range(1, max_n + 1)]
```

Migrations run automatically inside the FastAPI lifespan handler
(`api/main.py`, lines ~234-256):

```python
migration_manager = AsyncMigrationManager()
current_version = await migration_manager.get_current_version()
if await migration_manager.needs_migration():
    logger.warning("Database migrations are pending. Running migrations...")
    await migration_manager.run_migration_up()
```

---

## 13.2 The `fn::vector_search` Function

The HNSW indexes are queried by a stored SurrealQL function,
`fn::vector_search`, redefined in `21.surrealql` (lines 9-72). It runs three
independent KNN sub-queries (sources, source-insights, notes), unions them, and
collapses duplicates by max-similarity.

```sql
DEFINE FUNCTION IF NOT EXISTS fn::vector_search(
    $query: array<float>, $match_count: int,
    $sources: bool, $show_notes: bool, $min_similarity: float
) {
    let $source_embedding_search =
        IF $sources {(
            SELECT
                source.id as id, source.title as title, content,
                source.id as parent_id,
                vector::similarity::cosine(embedding, $query) as similarity
            FROM source_embedding
            WHERE embedding <|100|> $query                              -- KNN operator: top-100 ANN candidates
              AND embedding != none
              AND array::len(embedding) = array::len($query)            -- dimension guard
              AND vector::similarity::cosine(embedding, $query) >= $min_similarity
            ORDER BY similarity DESC
            LIMIT $match_count
        )} ELSE { [] };
    -- ... parallel blocks for source_insight and note ...

    let $all_results = array::union(
        array::union($source_embedding_search, $source_insight_search),
        $note_content_search
    );

    RETURN (
        SELECT id, parent_id, title,
               math::max(similarity) as similarity,
               array::flatten(content) as matches
        FROM $all_results WHERE id IS NOT None
        GROUP BY id, parent_id, title
        ORDER BY similarity DESC LIMIT $match_count
    );
};
```

Key performance details:

- **`<|100|>` KNN operator** — uses the HNSW index to return the 100 nearest
  approximate neighbors *before* the exact cosine re-rank, instead of a full
  table scan. This is the single largest search-latency win and the reason
  migration 21 exists (its header comment names it explicitly).
- **`$min_similarity` floor** — pushes the relevance threshold into the DB so
  irrelevant rows never cross the wire.
- **Dimension guard** (`array::len(embedding) = array::len($query)`) — skips
  rows whose embedding dimension doesn't match the query (e.g. left over from a
  previous embedder), avoiding runtime errors and silently-wrong distances.
- **`math::max` + `GROUP BY`** — a single source/note can contribute multiple
  chunk embeddings; the group collapses them to the best-matching chunk.

The function evolved across migrations 1 → 3 → 4 → 9 → 21 (each
`REMOVE FUNCTION IF EXISTS` then redefines); `21` is the live version.

---

## 13.3 Embedding Batching — `generate_embeddings` (batches of 50)

File: `open_notebook/utils/embedding.py`.

Embeddings are generated in **batches of 50 texts** to stay under provider
payload limits and to keep CPU-only local embedders responsive. The batch size
is environment-tunable but defaults to 50 (lines 24-47):

```python
def _get_embedding_batch_size() -> int:
    raw = os.getenv("OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE", "50").strip()
    try:
        value = int(raw)
        if value < 1:
            raise ValueError
        return value
    except ValueError:
        logger.warning("Invalid OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE='{}'; falling back to 50", raw)
        return 50

EMBEDDING_BATCH_SIZE = _get_embedding_batch_size()
EMBEDDING_MAX_RETRIES = 3
EMBEDDING_RETRY_DELAY = 2  # seconds
```

The batch loop (lines 171-206) computes a ceiling division for total batches and
retries each batch up to 3 times with a 2s delay on transient failures:

```python
total_batches = (len(texts) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
for batch_idx in range(total_batches):
    start = batch_idx * EMBEDDING_BATCH_SIZE
    end   = start + EMBEDDING_BATCH_SIZE
    batch = texts[start:end]
    for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
        try:
            batch_embeddings = await embedding_model.aembed(batch)
            all_embeddings.extend(batch_embeddings)
            break
        except Exception as e:
            if attempt < EMBEDDING_MAX_RETRIES:
                await asyncio.sleep(EMBEDDING_RETRY_DELAY)   # backoff between attempts
            else:
                raise RuntimeError(...) from e
```

### Large-content path: chunk → embed → mean-pool

`generate_embedding(text, ...)` (lines 209-274) handles arbitrarily large text
without exceeding the embedder's context window:

- **Short text** (`token_count(text) <= CHUNK_SIZE`, default 400 tokens):
  embed directly.
- **Long text**: `chunk_text()` splits it, all chunks are embedded *in batches*
  via `generate_embeddings()`, then combined with `mean_pool_embeddings()`.

`mean_pool_embeddings()` (lines 55-108) normalizes each vector to unit length,
takes the element-wise mean, and re-normalizes — preserving the unit-length
property of the input embeddings regardless of chunk count.

### Lazy, cost-free size metrics

Embedding logging uses `logger.opt(lazy=True)` with deferred lambdas
(lines 149-169) so the expensive per-text `token_count` sweep only runs if the
`DEBUG` log level is actually active — zero cost in production.

---

## 13.4 Token-Budget Sizing for LLM Context

Two layers cooperate to keep prompts inside model context windows.

### Token counting — `token_utils.token_count`

File: `open_notebook/utils/token_utils.py` (lines 14-46). Uses tiktoken's
`o200k_base` encoding, with the cache redirected to `TIKTOKEN_CACHE_DIR` and a
graceful word-count fallback when tiktoken can't load (offline first launch):

```python
def token_count(input_string: str) -> int:
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(input_string))
    except (ImportError, OSError) as e:
        logger.warning("tiktoken unavailable, falling back to word-count estimation: {}", e)
        return int(len(input_string.split()) * 1.3)
```

### Context assembly with a hard token ceiling — `ContextBuilder`

File: `open_notebook/utils/context_builder.py`.

- Each `ContextItem` auto-computes its `token_count` in `__post_init__`
  (lines 28-34). A code comment (lines 42-46) flags the codebase-wide
  `str(payload)` over-counting bug — content text is summed correctly rather
  than stringifying whole payloads.
- `ContextConfig` carries `max_tokens` plus per-type priority weights
  (lines 72-82): `{"source": 100, "note": 50, "insight": 75}`.
- `build()` (line 131) assembles items, and when `max_tokens` is set calls
  `truncate_to_fit(max_tokens)` (lines 158-159, 346+) which **drops whole
  lower-priority items** once the running total exceeds the budget (not
  prorated — it's a hard stop after sorting by priority descending).

### Model selection by content size — 105,000-token threshold

File: `open_notebook/ai/provision.py`, `provision_langchain_model`
(lines 360-396):

```python
tokens = token_count(content)
if tokens > 105_000:
    selection_reason = f"large_context (content has {tokens} tokens)"
    candidate_id = await model_manager.get_default_model_id("large_context")
elif model_id:
    candidate_id = model_id
else:
    candidate_id = await model_manager.get_default_model_id(default_type)
```

Above 105k tokens the request is upgraded to the configured
`large_context_model` automatically.

---

## 13.5 TanStack Query Caching + Invalidation Strategy

File: `frontend/src/lib/api/query-client.ts`.

### Global cache defaults

```typescript
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,   // 5 minutes — data considered fresh, no refetch
      gcTime: 10 * 60 * 1000,     // 10 minutes — unused cache eviction (was cacheTime)
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 1 },
  },
})
```

### Hierarchical query keys

`QUERY_KEYS` (lines 17-40) defines a structured key namespace so invalidation
can be broad or narrow:

```typescript
notebooks: ['notebooks'],
notebook: (id) => ['notebooks', id],
sources: (notebookId?) => ['sources', notebookId],
source: (id) => ['sources', id],
// observability config kept on its own key so writable-settings
// invalidation doesn't clobber env-derived read-only config (v0.7.136):
observabilitySettings: ['settings', 'observability'],
```

### Invalidation pattern

Per `frontend/src/CLAUDE.md` and `lib/hooks/CLAUDE.md`, mutations invalidate by
prefix after success — e.g. `queryClient.invalidateQueries(['sources'])` after a
source create/upload — which transparently refetches the sources list, notebook,
etc. The documented trade-off is **breadth vs. precision**: broad
prefix-invalidation is simpler and is accepted here over surgical key updates.

### Bounded cache growth for per-message chat data (v0.8.66 audit F-2)

Chat turns stash ad-hoc per-message badge/citation payloads under
3-element keys. Two such families exist:

```typescript
const MESSAGE_SCOPED_QUERY_PREFIXES = [
  ['mcp', 'tool-calls'],          // CitationPill MCP popover payloads
  ['chat', 'selected-provider'],  // provider + privacy + agent-state badge
] as const

export function pruneMessageScopedQueries(): void {
  for (const prefix of MESSAGE_SCOPED_QUERY_PREFIXES) {
    queryClient.removeQueries({ queryKey: [...prefix] })
  }
}
```

These accumulate one entry per message id and are never refetched, so
`pruneMessageScopedQueries()` is called on chat-view unmount to cap memory.
The 3-element prefixes can't collide with the non-ephemeral
`['mcp','web-search']` status query or the session-list keys.

The Axios client (`lib/api/client.ts`) carries a **10-minute timeout** for slow
LLM operations and does not auto-retry (retries are explicit, e.g. podcast
episode retry).

---

## 13.6 The Network-State TTL Cache

File: `open_notebook/health/network.py` (`v0.8.68`).

A process-wide service answering "does this machine have internet right now?"
for the offline gate, the web-search tool, the Gmail digest scheduler, and
`GET /api/system/network-status`. It is built to **never block the event loop**
and **never add a DB read or probe to the hot path** unnecessarily.

### TTL + single-flight probe

```python
_DEFAULT_PROBE_TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 443)]
_PROBE_TIMEOUT_S = 2.0
_DEFAULT_TTL_S   = 20.0   # ONP_NETWORK_STATE_TTL_SEC override

async def get_network_state(*, forced_offline_lookup=None) -> NetworkState:
    # forced-offline check first (no probe at all)
    now = time.monotonic()
    if _state is not None and now - _state.checked_at < _ttl_s():
        return _state                                   # TTL cache hit
    async with _get_probe_lock():                       # single-flight
        now = time.monotonic()
        if _state is not None and now - _state.checked_at < _ttl_s():
            return _state                               # double-checked
        up = await asyncio.to_thread(_probe_once)       # blocking TCP probe off-loop
        ...
```

- **20s TTL** cache so back-to-back provisioning calls don't each probe.
- **Single-flight `asyncio.Lock`** with double-checked locking — concurrent
  cache-misses share one probe (same pattern as `provision.py`'s
  `_health_cache_lock`).
- **`asyncio.to_thread(_probe_once)`** — the blocking `socket.create_connection`
  runs on a worker thread; the event loop is never blocked.
- **Lazy lock init** (`_get_probe_lock`) keeps imports side-effect-free with no
  event loop required at import time.

### Passive immediate updates

`report_network_failure()` / `report_network_success()` (lines 99-115) flip the
cached state instantly when a real cloud call fails or succeeds — this also
catches captive portals where the TCP probe would lie.

### Probe-error = ONLINE bias

A probe exception yields `status="unknown"`, and consumers treat `unknown` as
online (offline-gate line 113: `if state.status != "offline": return candidate_id`).
The design rule is "a flaky probe must never block cloud calls — real failures
correct it."

### Second, coarser cache: forced-offline boolean (30s)

The user's Offline-mode toggle lives in SurrealDB. To avoid a DB read on every
provisioning call, `forced_offline_enabled()` (lines 170-191) caches the boolean
for **30s**, invalidated explicitly by the settings PUT handler via
`invalidate_forced_offline_cache()`. Any DB hiccup fails *open* (returns
`False`) so a settings outage can never brick cloud access.

---

## 13.7 Async-First Design + `asyncio.to_thread` for Blocking Calls

Every DB query, graph invocation, and provider call is `async`. The critical
rule (root `CLAUDE.md`, "Standing Workflow") is that **blocking or sync calls
inside `async def` must be wrapped in `asyncio.to_thread`**. Concrete instances:

- **Network probe** — `await asyncio.to_thread(_probe_once)`
  (`health/network.py:151`).
- **SSRF URL validation** — `await asyncio.to_thread(validate_url, body.url, "mcp")`
  (`api/routers/mcp.py:128`); `validate_url` does blocking DNS resolution.
- **`surreal_commands.submit_command`** — the sync job-submit primitive is
  documented as a recurring footgun: it must be wrapped in `asyncio.to_thread`
  when called from `async def` (root `CLAUDE.md`).

Embedding generation, mean pooling, and the retry/backoff loop are all `async`
(`embedding.py`), so batched embedding of a large source never blocks request
handling.

---

## 13.8 The Auto-Route Smart Router (Local vs Cloud by Context Size)

File: `open_notebook/ai/router.py` — `pick_provider()`, a **pure function**
(no I/O, no state) so it is trivially testable and callable from any node.

```python
def pick_provider(*, content_tokens, local_chat_healthy, local_chat_n_ctx,
                  cloud_model_id, local_model_id,
                  default_provider="auto", reply_headroom_tokens=1000) -> ModelChoice:
    # 1. Explicit user override (cloud/local) wins.
    if default_provider == "cloud" and cloud_model_id:
        return ModelChoice(cloud_model_id, "user-forced cloud")
    if default_provider == "local" and local_model_id:
        return ModelChoice(local_model_id, "user-forced local")

    # 2. Auto: prefer local if healthy AND it fits with reply headroom.
    if (local_chat_healthy and local_model_id
            and content_tokens <= local_chat_n_ctx - reply_headroom_tokens):
        return ModelChoice(local_model_id, "local: healthy + fits in n_ctx")

    # 3. Cloud fallback — oversized content or local unhealthy.
    if cloud_model_id:
        reason = (f"cloud: content {content_tokens}t exceeds n_ctx {local_chat_n_ctx}t"
                  if local_chat_healthy else "cloud: local unavailable")
        return ModelChoice(cloud_model_id, reason)

    # 4. Best-effort local even when too big (llama.cpp returns its own 400).
    if local_model_id:
        return ModelChoice(local_model_id, "local fallback (no cloud configured)")

    raise ValueError("No model available — neither local nor cloud")
```

### Reply-headroom correctness (v0.8.66 audit A-6/A-7)

`reply_headroom_tokens` (lines 76-88) reserves room for the reply + system
prompt + tool schemas that `content_tokens` (content only) omits. Before this
fix it was a flat 1000, so a ~(n_ctx − 1k) prompt routed local then overflowed
once an 8192-token reply was reserved → llama.cpp `400 context_length_exceeded`.
The chat caller now passes the real reservation (its `max_tokens`, default 8192).

### Wiring

`provision_langchain_chat_model` in `provision.py` (lines 131-160) wraps
`provision_langchain_model` with `pick_provider` when smart routing is on. The
master switch is `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` (env, explicit wins) falling
back to `DefaultModels.auto_route_enabled` (Settings, default `False`). The cloud
target is the dedicated `auto_route_cloud` field (`models.py:174`), provider
preference from `auto_route_provider_pref` (default `"auto"`).

The offline gate (`open_notebook/ai/offline_gate.py`, §14.6) sits in the same
resolution funnel and is itself a performance feature: when offline it
substitutes a local model **before** the provider call, so the turn answers
instantly instead of hanging to a 300s cloud timeout.

---

## 13.9 Connection-Per-Operation Tradeoffs (and the Pool)

File: `open_notebook/database/repository.py`.

The original design (documented in `database/CLAUDE.md`) was
**connection-per-operation**: each `repo_*` call opened, used, and closed a
SurrealDB WebSocket. Simple and request-scoped, but it paid a handshake per
query.

`v0.7.18` replaced this with a **connection pool** behind the same
`db_connection()` context-manager interface (lines 346-393) — no call site
changed, but connections are now reused, eliminating per-query handshake
overhead. `ONP_DB_POOL_DISABLED=1` falls back to the old open/use/close path for
debugging.

### Pool health hardening

```python
async def db_connection():
    conn = await _acquire()
    broken = False
    try:
        yield conn
    except BaseException:                # v0.8.65g — MUST be BaseException
        broken = True                    # asyncio.CancelledError is a BaseException
        raise
    finally:
        await _release(conn, broken=broken)
```

- **`except BaseException` (v0.8.65g)** — `asyncio.CancelledError` is a
  `BaseException`, so the old `except Exception` missed cancellations
  (chat-stream disconnect, `wait_for` timeout). A cancelled query left a pending
  in-flight request on the socket; the connection was wrongly returned as
  healthy, and the next acquirer collided with the stale response
  (`KeyError(<uuid>)` in the driver) — "the chatbot stopped working until
  restart." Marking the connection broken on *any* abnormal exit closes and
  drops it.
- **Retriable-connection heuristic** (`_is_retriable_conn_error`, lines 396-412)
  — conservatively detects idle-reaped/dead WebSockets (connection
  reset/closed/"going away"/broken pipe) and retries **read-only** queries only.

**Tradeoff summary:** connection-per-operation maximizes isolation and
simplicity but is inefficient for bulk workloads (e.g. embedding hundreds of
chunks); the pool restores throughput while the broken-connection accounting
preserves the per-operation safety guarantees.
