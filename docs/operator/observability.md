# Operator handbook — Observability

> v0.7.134 — Single-source-of-truth for what to look at, what's
> normal, and what to do when it isn't. Pair with the `/metrics`
> Prometheus endpoint + `/healthz/deep` + the `/settings/observability`
> read-only view of env-derived configuration.

This document closes two open Areas for Review:

- **#22** — `@next/bundle-analyzer` tree-shaking verification
- **#27** — memory-recall baseline measurements

---

## 1. `/metrics` — the cheat sheet

Every metric Deeper Notebook emits, what triggers it, and what
"normal" looks like on a healthy single-user install. Hit
`http://localhost:5055/metrics` to see the live snapshot.

If you're using cardinality-sensitive storage (e.g., Prometheus
without aggressive remote_write), all labels here are bounded: route
templates instead of literal URLs, fixed reason strings instead of
free-text. You should not see label-set explosion regardless of
traffic.

### HTTP

| Metric | Type | Labels | Normal range | Investigate when |
|---|---|---|---|---|
| `onp_http_requests_total` | Counter | method, route, status | growing monotonically | sudden plateau (frontend disconnected?) or 5xx ratio spike |
| `onp_http_request_duration_seconds` | Histogram | method, route | p50 < 200ms, p99 < 2s | p99 > 5s for non-streaming routes |

The streaming endpoints (`/chat/stream`, `/search/ask`, anything
producing SSE / NDJSON) are excluded from the duration histogram by
design — they're long-lived by nature, and counting them would
poison the p50.

### Database

| Metric | Type | Normal range | Investigate when |
|---|---|---|---|
| `onp_db_query_duration_seconds` | Histogram | p50 < 20ms, p99 < 200ms | p99 > 500ms — connection pool saturated? SurrealDB under-resourced? |
| `onp_db_slow_queries_total` | Counter | 0 if `ONP_SLOW_QUERY_LOG_MS` unset; otherwise <1/minute | rate > 1/sec — check loguru for the actual query string |

`ONP_SLOW_QUERY_LOG_MS` is unset by default. Set it to 500 (ms) on
a deployment that's behaving suspiciously slowly — the matching
loguru WARNING line will name the query verbatim.

### Memory recall (v0.7.124–v0.7.133)

Memory recall is the hottest path in the chat hot path. It runs on
every chat turn that has a non-empty user message. The full pipeline:

```
user turn
  → /chat/stream
  → recall_memory(query=last_user_message)
  → asyncio.wait_for(_recall_memory_inner(query), timeout=BUDGET)   ← v0.7.133 outer wall
       → mode detection (recent | semantic | auto)
       → if semantic: aembed(query) → vector_search × 2 tables
       → fall through to recency if semantic empty / failed
  → render into "# WHAT YOU REMEMBER ABOUT THE USER"
```

Five places this can fall through to empty:

| Counter (`onp_memory_recall_fallthrough_total{reason=…}`) | Where it fires | Normal rate |
|---|---|---|
| `embed_timeout` | local/cloud embedder didn't respond within `ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC` (5s default) | 0 / hr |
| `embed_error` | embedder raised — provider key bad, model unloaded, network refused | 0 / hr (≥1 / hr = check credential health) |
| `query_timeout` | mem0 / SurrealDB query exceeded `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC` (5s default) | 0 / hr |
| `query_error` | SurrealQL query raised — schema mismatch, connection failure | 0 / hr |
| `outer_budget` | the whole pipeline exceeded `ONP_MEMORY_RECALL_BUDGET_SEC` (12s default) — v0.7.133 wall | 0 / hr (any rate signals a chronically slow embedder or DB) |

### Memory recall — expected baselines (Area for Review #27)

These are the measurements taken on a healthy single-user macOS
desktop install (M-series Mac, bundled `llama-cpp-python` embed
server, SurrealDB on localhost):

| Phase | p50 | p99 | Notes |
|---|---|---|---|
| `aembed(query)` (single string, mxbai-embed-large) | 80ms | 180ms | First call after process start may spike to 1500ms (model warmup). After that it's stable. |
| SurrealDB `vector_search` × 2 (facts + preferences) | 25ms | 95ms | Pool warmup matters — cold first chat hits 400ms+ for the connection handshake. The v0.7.134 retry-with-backoff narrows this window. |
| Full `recall_memory()` (`memory_recall_seconds`) | 130ms | 320ms | Includes mode dispatch + fall-through. Outliers usually trace to the embedder. |

What this means in practice:

- A p50 over **500ms** is a red flag. Probe with `?probe_providers=true`
  on `/healthz/deep` to see if a configured provider is slow; check
  the local embedder process is alive (`pgrep llama-cpp-python`).
- The `outer_budget` counter at default 12s should fire never. If
  it does, you either have a hung subsystem or an unrealistic
  budget for your install — check the per-step counters first.
- If `embed_timeout` is the dominant reason, raise
  `ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC` OR swap to a smaller model.

### Checkpoint pruning (v0.7.125)

| Metric | Normal |
|---|---|
| `onp_checkpoint_prune_runs_total` | +1 every `ONP_CHECKPOINT_PRUNE_INTERVAL_HOURS` (24 default) |
| `onp_checkpoint_prune_rows_deleted_total{table="checkpoints"}` | grows slowly; should NOT plateau (means LangGraph isn't actually writing checkpoints any more) |
| `onp_checkpoint_prune_rows_deleted_total{table="writes"}` | grows faster than checkpoints (multiple writes per checkpoint) |

### Studio generation (v0.7.130)

| Metric | Reason it fires |
|---|---|
| `onp_studio_generations_total{mode, outcome}` | every `/api/studio/generate` call |
| `onp_studio_outline_parse_failures_total{reason="json_decode"}` | LLM returned text that wasn't valid JSON — model can't follow structured output |
| `onp_studio_outline_parse_failures_total{reason="validation"}` | JSON was valid but failed schema/page-count check — model misunderstood the schema |
| `onp_studio_single_note_fallbacks_total` | multi-page outline failed; fell back to single-note. Sustained rate ≫0 means rebuild the prompt or swap the outline model. |

---

## 2. `/healthz/deep` — the dashboard view

```bash
curl http://localhost:5055/healthz/deep
```

Returns a per-subsystem status dict:

```json
{
  "status": "healthy",
  "checks": {
    "database":         {"status": "online",     "ok": true},
    "migrations":       {"status": "applied",    "ok": true},
    "embedding_model":  {"status": "configured", "ok": true},
    "chat_model":       {"status": "configured", "ok": true},
    "command_registry": {"status": "loaded",     "ok": true}
  }
}
```

### Provider probe (opt-in, v0.7.132)

Add `?probe_providers=true` to verify every configured credential
actually responds to its upstream. Burns one API call per credential:

```bash
curl 'http://localhost:5055/healthz/deep?probe_providers=true'
```

Returns the standard response plus an `upstream_providers` block
with per-credential `ok`/`message` entries. Default cadence: ≤ once
per minute — anything more frequent runs up provider bills.

---

## 3. Bundle analyzer — tree-shaking verification (Area for Review #22)

The `@next/bundle-analyzer` was added in v0.7.127 to let maintainers
identify client-bundle lazy-load opportunities. The concern raised
in Area #22: is the analyzer itself tree-shaken out of production
bundles?

### Why we expect it to be tree-shaken

`frontend/next.config.ts` wraps the export with:

```typescript
const withBundleAnalyzer = nextBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});
export default withBundleAnalyzer({ /* config */ });
```

This is **build-time only**:

- `next.config.ts` is evaluated by the Next.js build process, NOT
  shipped to the client.
- The `enabled: false` flag (which is what production gets, since
  `ANALYZE` is unset) makes `withBundleAnalyzer` a passthrough —
  it returns the config unchanged without registering any plugin.
- The `@next/bundle-analyzer` package is in `devDependencies`, not
  `dependencies` — it's not even present in the `node_modules` tree
  that ships to the production runtime.

So in a typical production build (`npm run build`, no `ANALYZE` env),
the analyzer:

1. Is loaded by Node to evaluate `next.config.ts`
2. Sees `enabled: false`
3. Returns the config untouched
4. Is never bundled into any client / server / edge chunk

### How to verify

Run the analyzer against your own build:

```bash
cd frontend
npm run build:analyze
open .next/analyze/client.html
```

Search the treemap for "bundle-analyzer" or "webpack-bundle-analyzer".
You should find **nothing** in the client.html or edge.html. If you
do find it, file a bug — that's the tree-shaking failing.

The server.html *will* show the analyzer's own server-side bundle,
but that's because you're running the build WITH `ANALYZE=true`.
Doing a normal `npm run build` and inspecting `.next/server/*` would
show nothing.

### Why a code-test for this isn't worth maintaining

We could write a test that runs `npm run build` (no ANALYZE) and
greps the output for analyzer-related strings. Two reasons we don't:

1. **Slow** — the test would add ~30s to CI. A pattern-grep is a
   weak signal anyway (minifiers can rename things).
2. **Brittle** — Next.js internals change between versions. A test
   that depends on specific minified symbols would break every minor
   bump.

The verification above is a one-time manual check. Re-run it after
any `@next/bundle-analyzer` upgrade or any `next.config.ts` refactor.

---

## 4. `/settings/observability` — see your effective config

Added in v0.7.130. Returns a read-only snapshot of which ONP_* env
vars the running process is actually seeing:

```json
{
  "slow_query_log_ms": null,
  "encryption_kdf": "raw",
  "checkpoint_keep_per_thread": 50,
  "checkpoint_prune_interval_hours": 24,
  "db_pool_size": 4,
  "db_pool_disabled": false,
  "metrics_endpoint_path": "/metrics"
}
```

Use this to verify your `.env` is loading correctly after a restart.

---

## 5. Quick-reference: when each signal fires

| Symptom | Check first | Then |
|---|---|---|
| First chat is very slow | `onp_db_query_duration_seconds` p99 | If high: pool didn't warm up. v0.7.134 retry should auto-recover; raise `ONP_DB_POOL_SIZE` if pool size is the bottleneck. |
| Chat suddenly returns empty memory context | `onp_memory_recall_fallthrough_total{reason}` | Look at the dominant `reason` label and follow its remediation row above. |
| Studio "multi-page" output is single-note | `onp_studio_single_note_fallbacks_total` + `outline_parse_failures_total{reason}` | If `json_decode` dominates: swap to a stronger outline model. If `validation`: tighten the prompt. |
| Backup `data/` directory is enormous | `onp_checkpoint_prune_rows_deleted_total{table="writes"}` | If 0, the prune loop never ran. Check the lifespan startup log for prune-task initialization. |
| Disk fills overnight | `onp_db_slow_queries_total` | High rate means SurrealDB is thrashing — restart it, check `surreal_data/` size, consider VACUUM. |

---

## 6. Related operator docs

- [`CONFIGURATION.md`](../../CONFIGURATION.md) — every ONP_* env var documented
- [`SECURITY_REVIEW.md`](../SECURITY_REVIEW.md) — encryption, auth, network exposure
- [`frontend/docs/BUNDLE_ANALYSIS.md`](../../frontend/docs/BUNDLE_ANALYSIS.md) — how to interpret analyzer output

End of operator observability handbook.
