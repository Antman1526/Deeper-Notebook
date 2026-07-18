# 13 — Performance Optimization & Caching

> Recreation reference for the performance layer of Open Notebook Plus: frontend
> render batching + virtualization, TanStack Query caching, backend search +
> embedding batching, context/token sizing, and long-context model selection.
> Frontend: Next.js 16 / React 19, TanStack Query + `@tanstack/react-virtual`.
> Backend: SurrealDB vector/text search, tiktoken `o200k_base` sizing.

The performance work targets one reality: **the desktop fork often runs a local
16k-context LLM in a WKWebView**, so both "don't overflow the model" and "don't jank the
WebView" are first-class concerns.

---

## 1. Frontend: rAF token-batching

**Where:** `frontend/src/lib/hooks/useNotebookChat.ts` (also `useSourceChat.ts`,
`use-ask.ts`, `components/source/ChatPanel.tsx`).

Streamed tokens are buffered and flushed once per animation frame instead of one
`setMessages()` per token. At 50–150 tok/s the per-token version re-rendered and
re-laid-out the whole message list 50–100×/sec — visibly janky in WKWebView (v0.8.70).

```typescript
// v0.8.70 — batch streamed tokens with requestAnimationFrame
let tokenBuffer = ''
let rafId: number | null = null
const flushTokens = () => {
  rafId = null
  if (!tokenBuffer || !mountedRef.current) { tokenBuffer = ''; return }
  const chunk = tokenBuffer; tokenBuffer = ''
  setMessages(prev => prev.map(m =>
    m.id === streamingAiId ? { ...m, content: m.content + chunk } : m))
}
const scheduleFlush = () => { if (rafId == null) rafId = requestAnimationFrame(flushTokens) }

for await (const event of chatApi.streamMessage({...}, controller.signal)) {
  if (!mountedRef.current) break                  // v0.7.50 — bail on unmount
  if (event.type === 'token') { tokenBuffer += event.content; scheduleFlush() }
  else if (event.type === 'mcp_tool_calls') { pendingMcpCalls = event.calls }
  else if (event.type === 'done') { /* canonical message list wins */ }
}
```

rAF coalesces to ≤1 render per paint frame. The `mountedRef` guard prevents
setState-on-dead-component after unmount, and the loop uses an `AbortController` signal
so navigating away cancels the fetch (which lets the backend `is_disconnected()` fire).

---

## 2. Frontend: list virtualization (`VirtualizedList` / `VirtualizedListAuto`)

**Where:** `frontend/src/components/ui/virtualized-list.tsx` (v0.7.39), built on
`@tanstack/react-virtual`.

Two flavors:

- `<VirtualizedList>` — **fixed-size** rows (cheap; preferred).
- `<VirtualizedListAuto>` — **dynamic-size** rows via `measureElement` round-trip.

Both render only viewport rows + a small overscan (default `overscan = 5`). A 5000-source
list that previously mounted 5000 row components on every parent state change drops to
~30. Accessibility preserved: wrapper `role="rowgroup"`, each row `role="row"`;
`containerAs` allows `'tbody'` for tables.

```tsx
export function VirtualizedList<T>({ items, estimateSize, renderItem, overscan = 5, ... }) {
  'use no memo'
  const parentRef = useRef(null)
  const virtualizer = useVirtualizer({ count: items.length, getScrollElement: () => parentRef.current,
                                       estimateSize: () => estimateSize, overscan })
  // renders virtualizer.getVirtualItems() only
}
```

**Break-even guidance (in the source docstring):** below ~100 rows the virtualizer's
overhead (scroll math, listeners) isn't worth it — callers gate on
`items.length >= threshold` themselves, keeping the choice explicit. The scroll container
must have a height constraint (`h-[60vh]`, `flex-1`).

### Skeletons

Loading states render skeleton placeholders (Radix/CVA UI primitives) rather than layout
that shifts when data arrives, avoiding CLS while queries resolve.

---

## 3. TanStack Query cache keys, invalidation & prefetch

**Where:** `frontend/src/lib/api/query-client.ts` (`QUERY_KEYS`), hooks in
`frontend/src/lib/hooks/`.

- **Hierarchical keys**: `QUERY_KEYS.notebook(id)`, `QUERY_KEYS.sources(notebookId)`,
  credential keys `['credentials', ...]`, model keys `['models', ...]`.
- **Broad invalidation** (deliberate trade-off): mutations invalidate the *parent* key —
  e.g. `queryClient.invalidateQueries(['sources'])` catches all source queries. Simpler
  than surgical invalidation; may over-fetch. The credentials hooks are the clearest
  example of the breadth policy:
  - create/update → invalidate `credentials.all` + `models.providers`.
  - delete → additionally `models.models` (linked models may vanish).
  - migrate → additionally `credentials.status` + `credentials.envStatus`.
- **`refetchOnWindowFocus: true`** on frequently-changing data (sources, notebooks) so
  returning to the tab shows fresh data.
- **Status polling**: `useSourceStatus` auto-refetches every **2s** while
  `status ∈ {new, queued, running}`, then stops — this is exactly why the stale-command
  reapers exist server-side (see doc 12 §8.1), so orphaned rows don't poll forever.
- **Prefetch-on-hover**: hover handlers call `queryClient.prefetchQuery(...)` so the
  detail view's data is warm by the time the user clicks. Optimistic updates add chat
  messages to local state before the server confirms (removed on error).

---

## 4. Backend search: SurrealDB vector/text + fallback

**Where:** `open_notebook/domain/notebook.py` (`vector_search`, `text_search`).

- `vector_search(term, results, ...)` — semantic search over `source_embedding` via
  SurrealDB's built-in vector index; default `minimum_score = 0.2`. This is the search
  used by the Ask graph (`await vector_search(state["term"], 10, True, True)`) — the ask
  graph is hard-coded to vector search (no text fallback there, despite a commented-out
  planned path).
- `text_search(term, ...)` — full-text keyword search using SurrealDB
  `search::highlight`. On a **"position overflow"** (large/multi-byte chunks break
  highlight offsets) it **falls back to `vector_search`**; if that also fails it raises
  `DatabaseOperationError` (never silently returns an empty list).

SurrealDB co-locates embeddings with records, so vector search is a DB query rather than
a separate vector store round-trip.

---

## 5. Embeddings batching (50) + chunking

**Where:** `open_notebook/utils/embedding.py`, `open_notebook/utils/chunking.py`,
`commands/embedding_commands.py`.

- **Batch size 50**: `generate_embeddings(texts)` splits into batches of
  `EMBEDDING_BATCH_SIZE` (env `OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE`, default **50**) to
  stay under provider payload limits; `total_batches = (len(texts)+50-1)//50`. Each batch
  retries `EMBEDDING_MAX_RETRIES = 3` with `EMBEDDING_RETRY_DELAY = 2s`, then raises
  `RuntimeError`.
- **Mean pooling for large single texts**: `generate_embedding(text)` embeds directly if
  `token_count(text) <= CHUNK_SIZE`; otherwise chunk → batch-embed → `mean_pool_embeddings`
  (normalize each → element-wise mean → normalize result, numpy).
- **Chunking** is token-based: `OPEN_NOTEBOOK_CHUNK_SIZE` (default **400** tokens — a
  conservative baseline leaving ~20% headroom below the 512-token ceiling of BERT-family
  embedders, absorbing tokenizer mismatch since we measure with `o200k_base`),
  `OPEN_NOTEBOOK_CHUNK_OVERLAP` (default 15% of size), `OPEN_NOTEBOOK_MIN_CHUNK_SIZE`
  (default 5). `chunk_text` selects HTML/Markdown/Recursive splitter by detected content
  type (extension primary, heuristics ≥0.8 override); `_apply_secondary_chunking`
  re-splits any oversized chunk the structural splitters emit.
- **Per-source chunk cap** (`MAX_CHUNKS_PER_SOURCE`, v0.7.178): `embed_source_command`
  raises `ValueError` (permanent, no retry) if a pathological input produces more chunks
  than the cap, preventing the worker from OOMing while holding chunks + 768-dim float
  vectors + record dicts simultaneously.

`embed_source_command` also DELETEs existing `source_embedding` rows before inserting, so
re-embedding is idempotent.

---

## 6. Context token sizing — never `str(payload)`

**Where:** `open_notebook/graphs/chat.py`, `transformation.py`; `token_utils.token_count`.

Context size is measured against the **actual message text**, joined per-message:

```python
content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)
```

Using `str(payload)` (Python's repr of a list of LangChain `Message` objects) added
~80–120 chars of wrapper boilerplate per message; a 50-turn chat accrued ~5k phantom
"tokens", which prematurely tripped the 105k large-context cutoff and re-routed the chat
to a bigger model for cosmetic reasons (v0.7.65 / v0.7.75). `token_count` uses tiktoken
`o200k_base`, with a coarse fallback estimate if tiktoken is unavailable.

Related input caps (all env-tunable, all to protect local 16k-context servers):

| Cap | Env | Default |
|---|---|---|
| Chat history | `ONP_CHAT_HISTORY_CHAR_CAP` | 12_000 chars |
| Transformation input | `ONP_TRANSFORMATION_INPUT_CAP` | 12_000 chars |
| Ask per-result content | `ONP_ASK_PER_RESULT_CHAR_CAP` | 1500 chars |
| Ask max results | `ONP_ASK_MAX_RESULTS` | 10 |

---

## 7. LLM long-context model selection (`open_notebook/ai/provision.py`)

`provision_langchain_model(content, model_id, default_type, ...)` picks a model in two
phases (id, then instance):

```python
tokens = token_count(content)
if tokens > 105_000:
    candidate_id = await model_manager.get_default_model_id("large_context")   # auto-upgrade
elif model_id:
    candidate_id = model_id                                                    # explicit override
else:
    candidate_id = await model_manager.get_default_model_id(default_type)      # default for type
candidate_id = await gate_language_model_id(candidate_id, fallback_out=fallback_out)  # offline gate (doc 14)
model = await model_manager.get_model(candidate_id, **kwargs)                  # instantiate
```

- **105,000-token threshold** (hard-coded) upgrades to the configured `large_context`
  model — critical because the accurate `content_for_sizing` (see §6) means the upgrade
  fires only when a prompt genuinely warrants it.
- Explicit `model_id` overrides bypass the smart chat router entirely.
- Missing model → `ConfigurationError` (HTTP 422) with a "go to Settings → Models" hint,
  not a bare provider timeout.

### Smart chat routing (`provision_langchain_chat_model`)

When no explicit override, the chat node uses the router which calls `pick_provider(...)`
with `content_tokens`, `local_chat_healthy` (30s TTL-cached health probe —
`_local_chat_healthy_cached`), local `n_ctx`, and reply headroom, then records the
local/cloud decision into `selection_out` for the UI pill. Per-node LLM timeouts bound
every call: ask nodes `ONP_ASK_NODE_TIMEOUT_SEC` (120s), transformation
`ONP_TRANSFORM_NODE_TIMEOUT_SEC` (180s), chat `ONP_CHAT_MODEL_TIMEOUT_SEC` (300s).

### MCP discovery cache

`_resolve_chat_tools` caches each MCP server's tool surface for 30s
(`_TOOL_DISCOVERY_TTL_S`, keyed by URL, with a negative cache) to avoid a
handshake+`list_tools` round-trip (~50–500ms) on every chat turn.

---

## 8. Startup / connection warmup (`api/main.py`)

- **DB pool pre-warm**: the lifespan acquires up to 2 connections
  (`min(2, _db_pool_size())`) so the first chat doesn't pay the ~150–300ms SurrealDB WS
  handshake; each acquire retries with exp backoff (0.5/1.0/2.0s) and a 10s per-attempt
  `asyncio.wait_for`, then degrades to lazy init.
- **Gmail TTL-cache pre-warm**, **checkpoint pruning** (keeps N latest checkpoints per
  thread, `ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS`, default 24), and reapers run as anchored
  background tasks.
- **Selective GZip**: bodies ≥1000 bytes compress, except streaming endpoints
  (`SelectiveGZipMiddleware`) so token deltas flush in real time.

---

## Key files

| Optimization | Path |
|---|---|
| rAF token batching | `frontend/src/lib/hooks/useNotebookChat.ts`, `useSourceChat.ts`, `use-ask.ts` |
| Virtualized list | `frontend/src/components/ui/virtualized-list.tsx` |
| Query cache/invalidation | `frontend/src/lib/api/query-client.ts`, `frontend/src/lib/hooks/*` |
| Vector/text search + fallback | `open_notebook/domain/notebook.py` |
| Embedding batching + mean pool | `open_notebook/utils/embedding.py` |
| Chunking | `open_notebook/utils/chunking.py` |
| Chunk cap / re-embed idempotency | `commands/embedding_commands.py` |
| Token sizing | `open_notebook/utils/token_utils.py`, graph nodes |
| Long-context selection + routing | `open_notebook/ai/provision.py` |
| Warmup / GZip / prune | `api/main.py` |
