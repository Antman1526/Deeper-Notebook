# 13 — Performance Optimization & Caching

> Every number here was **measured on the target hardware** (Apple M4 Max), not estimated.
> Where a figure is a budget rather than an observation, it says so.

---

## 1. Measured wins

| Optimisation | Before | After |
|---|---|---|
| Ollama store isolation | 10–15 s (some 500s) | **22 ms** |
| Pooled httpx client | 513 ms cold | **341 ms** warm |
| Web-search TTL cache | 513 ms | **0 ms** |
| Notebook list archived filter | full scan + Python filter | server-side `WHERE` |
| Gallery JS bundle delta | — | **−4 bytes** gzip (CSS 0) |
| Enabled-matrix max CLS | budget 0.05 | **0.0028** |

## 2. HTTP client pooling

Constructing `httpx.AsyncClient()` per call meant a fresh TLS handshake every search.

```python
async def _acquire_client() -> tuple[object, bool]:
    """Return (client, pooled); the caller closes it only when not pooled."""
    factory = httpx.AsyncClient
    if (
        _pooled_client is not None
        and _pooled_client_loop is loop  # bound to its creating loop
        and _pooled_client_factory is factory  # patched class ⇒ rebuild
        and not getattr(_pooled_client, "is_closed", False)
    ):
        return _pooled_client, True
    client = factory(
        limits=httpx.Limits(max_keepalive_connections=8, max_connections=16)
    )
    ...
```

Redirect policy is left at the httpx default (off) so paid and SearXNG attempts behave
exactly as before pooling; only the request that needs redirects opts in.

## 3. Bounded TTL caching

```python
_DEFAULT_CACHE_TTL_SEC = 300.0
_CACHE_TTL_CEILING_SEC = 3600.0
_CACHE_MAX_ENTRIES = 128
_cache: "OrderedDict[tuple[str, int], tuple[float, list[dict], str | None, bool]]"


def _cache_put(key, results, provider, degraded) -> None:
    if _cache_ttl_sec() <= 0 or not results:
        return  # NEVER cache empty
    _cache[key] = (time.monotonic(), list(results), provider, degraded)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)  # LRU eviction
```

Four properties worth copying: case-insensitive key (`query.casefold()`), monotonic clock
(immune to wall-clock jumps), **never cache empty**, bounded size with LRU eviction.

Scholarly search uses the same pattern with a 900 s TTL / 64 entries — literature moves
slower than news.

## 4. Query-level optimisation

Filtering moved from Python into SurrealDB (v0.7.166): previously every notebook row was
fetched *including* its per-row `source_count`/`note_count` subqueries and then filtered
in Python, so `?archived=false` paid for the whole archive scan.

```sql
SELECT *, count(<-reference.in) AS source_count, count(<-artifact.in) AS note_count
FROM notebook
WHERE archived = $archived
ORDER BY updated desc
```

Supporting mechanisms: connection pool (`DB_POOL_SIZE=4`, range 1–32), slow-query logging
above `SLOW_QUERY_LOG_MS`, and `LIMIT … START …` appended **only** when the caller asked.

## 5. Nested timeout budgets

Each inner budget sits strictly below its outer one, so slowness degrades instead of being
hard-killed mid-flight:

```
chat tool call      30 s  (MCP_TOOL_TIMEOUT_SEC)
└─ web search       25 s  (TOTAL_BUDGET_SEC)
   ├─ paid attempt  10 s  (TIMEOUT_SEC)
   └─ keyless       6 s   (_KEYLESS_TIMEOUT_SEC)
```

```python
attempt_timeout = min(cap, remaining)  # later attempts shrink as the budget drains
```

A slow early instance cannot starve a fast later one.

## 6. Probe budgets

```python
_PROBE_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0)
_OLLAMA_PROBE_TIMEOUT = httpx.Timeout(connect=2.0, read=20.0, write=2.0, pool=2.0)
_MAX_CONCURRENT_PROBES = 4
```

Ollama's `/api/tags` legitimately takes 10–15 s during a store inventory; the generic 5 s
read budget flapped its badge on every slow scan. Concurrency is capped so one wedged
sidecar can't stall the sweep.

## 7. Model-store layout is a performance decision

Ollama's blobs shared a directory tree with GGUF/MLX/LMStudio libraries. Every upgrade
re-inventoried **299 GB** of foreign files.

```
Before:  MacBook AI models/{blobs,manifests,GGUF,MLX,LMStudio,…}   → /api/tags 10–15 s
After:   MacBook AI models/Ollama/{blobs,manifests}                → /api/tags 22 ms
```

Same volume, so the move was an instant rename. Lesson: **give each runtime its own
store root**; shared trees make every scan pay for its neighbours.

## 8. Frontend

- **Standalone output** — Next builds a self-contained server for packaging.
- **Bundle budget** — the whole Source Visual Gallery landed at −4 bytes gzip.
- **CLS discipline** — `<img width height>` always emitted so layout reserves space;
  measured max CLS 0.0028 against a 0.05 budget across 96 cells.
- **Virtualisation** — `@tanstack/react-virtual` for long lists.
- **Query caching** — TanStack Query with targeted invalidation.
- **Motion is compositor-only** — transform/shadow/opacity, never geometry:

```css
.dn-workspace-shell .dn-visual-card { transition: transform .18s ease, box-shadow .18s ease; }
.dn-workspace-shell .dn-visual-card:hover { transform: translateY(-1px); }
@media (prefers-reduced-motion: reduce) {
  .dn-workspace-shell .dn-visual-card { transition: none; }
  .dn-workspace-shell .dn-visual-card:hover { transform: none; }
}
```

## 9. Startup

Measured stages from a real launch:

```
chat_model_scan     2,195 ms
core_ready         97,398 ms      ← dominated by model loading + first-run provisioning
```

Techniques: lazy imports (`import webview` inside the function so pure helpers are
testable without it), cached model scans keyed by path+mtime+size, non-blocking readiness
(`wait_for_ready=False` for an explicitly configured model so the shell opens while the
model loads), and generous-but-bounded gates that **log and proceed** on timeout rather
than aborting.

## 10. Visual extraction bounds

| Media | Candidates | Bytes | Time |
|---|---|---|---|
| PDF | 2 | 19,170 | < 60 s |
| Video | 3 | 5,736 | < 60 s |
| Audio | 1 | 1,950 | < 60 s |

Cache measured at 26,856 bytes against a **2 GiB** ceiling, with bounded eviction and
zero source-row mutation.

## 11. Known bottlenecks (not yet addressed)

| Bottleneck | Impact | Note |
|---|---|---|
| First-launch provisioning | ~90 s once | Downloads + venv; inherent |
| Large GGUF cold mmap | 10–60 s | Disk-bound; `SIDECAR_TCP_TIMEOUT` is tunable |
| Embedding rebuild | Minutes on large corpora | Batched but serial |
| Vault sync on huge vaults | Linear in file count | Watchdog incremental after first pass |
| `_authoritative_search_source_rows` | Extra query per search when visuals on | Could fold into the search projection |

---

*Continues in [14 — Security Implementation](./14-security-implementation.md).*
