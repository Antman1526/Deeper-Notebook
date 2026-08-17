# 07 — Business Logic & Core Algorithms

> The algorithms that define product behaviour, with the real code and the failure that
> motivated each design.

---

## 1. The chat tool loop

`deeper_notebook/graphs/chat.py` — `bind_mcp_and_run_tool_loop`. Both the notebook chat
and source chat graphs are single-node (no LangGraph `ToolNode`) and share this helper.

```
1. Discover MCP tools via _resolve_chat_tools (cached)
2. Bind to the model with bind_tools (FAIL-SOFT for local providers)
3. Invoke the model
4. If the model emits tool_calls, execute each, feed ToolMessages back, re-invoke
5. Bounded at max_iterations re-invocations (default 4)
```

**Fail-soft binding is the load-bearing detail.** Many local models cannot tool-call at
all; a hard failure would kill the turn:

```python
try:
    if mcp_tools:
        model = model.bind_tools(mcp_tools)
except Exception as bind_exc:
    _logger.debug("tool bind failed (degrading to no-tools): {}", bind_exc)
    mcp_tools = []          # reset the lookup or later dispatch mismatches
```

Tool assembly is **independence-ordered**: MCP resolution, native `web_search`,
`scholarly_search`, `opencode`, and `add_web_source` are built in separate `try` blocks.
Originally MCP resolution and web-search binding shared one `try`, so a DB hiccup during
`list_enabled_servers` dropped the DB-independent web tool too.

Each tool honours a per-request exclude list (the UI's tool picker):

```python
_excluded_names = {(n or "").strip().lower() for n in (exclude_server_names or []) if n}
if web_search_enabled() and WEB_SEARCH_TOOL_NAME not in _excluded_names:
    mcp_tools = list(mcp_tools) + [build_web_search_tool(mcp_captures)]
```

`mcp_captures` accumulates `{index, name, args, text, blocks}` per turn so tool results
render as citation pills identical to MCP results.

## 2. Web search — failover chain with nested budgets

`deeper_notebook/tools/web_search.py`. Precedence:
**Serper → Tavily → Brave → SearXNG(×N) → Wikipedia**.

```python
chain = _provider_chain()
deadline = time.monotonic() + _total_budget_sec()      # 25s total
for attempt_index, (provider, target) in enumerate(chain):
    remaining = deadline - time.monotonic()
    if remaining <= 0: break
    cap = (min(per_attempt_cap, _KEYLESS_TIMEOUT_SEC)   # keyless get 6s
           if provider in _KEYLESS_PROVIDERS else per_attempt_cap)
    attempt_timeout = min(cap, remaining)
    try:
        results = await _do_attempt(client, provider, target, query, n, attempt_timeout)
    except Exception as exc:
        logger.warning("web_search attempt via {}{} failed: {}", provider,
                       f" ({target})" if target else "", exc)
        continue                                        # error → next provider
    if results:
        _cache_put(cache_key, results, provider, attempt_index > 0)
        return results, provider, attempt_index > 0
    if provider == "searxng" or provider in _KEYLESS_PROVIDERS:
        continue          # free provider returning empty → try the next; costs nothing
    return results, provider, attempt_index > 0   # PAID empty is a legitimate answer
```

The paid-vs-free asymmetry is deliberate: falling through on a paid provider's legitimate
empty result would double the bill for no information.

**Offline short-circuit** avoids burning the full budget when the machine is offline.
**Cache** is keyed `(query.casefold(), n)`, TTL 300s, bounded 128 entries, **never caches
empty** — a failed lookup must not poison five minutes.

**Client pooling** with two correctness guards:

```python
factory = httpx.AsyncClient
if (_pooled_client is not None
        and _pooled_client_loop is loop           # a client is bound to its loop
        and _pooled_client_factory is factory     # monkeypatched class ⇒ rebuild
        and not getattr(_pooled_client, "is_closed", False)):
    return _pooled_client, True
```

Measured: 513 ms cold → 341 ms warm pool → 0 ms cached.

> **Rejected provider, recorded so nobody re-tries it:** DuckDuckGo. Both the HTML
> endpoint and the official Instant Answer API return **HTTP 202 with an anti-bot
> challenge** to scripted clients. A parser was written, unit-tested, and deleted after a
> live check — shipping it would have looked configured while returning nothing.

## 3. Scholarly search — a separate tool on purpose

OpenAlex → arXiv, both keyless. It is *not* folded into `web_search` because Wikipedia
almost always returns something and would end the chain first; and on the rare query where
a research provider did fire, it would answer a question about prices with papers.

OpenAlex ships abstracts as an inverted index; reading order is reconstructed:

```python
def _reconstruct_abstract(inverted: dict | None) -> str:
    positions: list[tuple[int, str]] = []
    for word, spots in inverted.items():
        for spot in spots:
            if isinstance(spot, int):
                positions.append((spot, str(word)))
    positions.sort()
    return " ".join(word for _, word in positions)
```

arXiv XML is size-bounded before parsing (Bandit B314 — entity-expansion DoS):

```python
if xml_text and len(xml_text) > _MAX_ARXIV_BYTES:      # 5 MB
    logger.warning("arxiv feed exceeded {} bytes; discarded", _MAX_ARXIV_BYTES)
    return []
```

## 4. Offline gate — cloud→local substitution

`deeper_notebook/ai/offline_gate.py` sits in `provision_langchain_model`'s resolution path.

```python
LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai_compatible"})
```

When the machine is offline (probe or user toggle) and the candidate is a cloud provider,
substitute the best registered **local** model so the turn answers instantly instead of
hanging to a 300 s provider timeout.

**Fail-open by design.** Any internal error returns the original candidate — the gate must
never be the thing that breaks a chat turn. The only raise is `ConfigurationError` when
offline + cloud + no local model exists: that turn was going to fail anyway, so it fails
fast with an actionable message.

## 5. Source visuals — bounded extraction with a capability sentinel

Visuals are **presentation aids, never evidence**. Extraction is bounded (PDF 2
candidates/19,170 bytes; video 3/5,736; audio 1/1,950 — all under 60 s), cached as WebP
under a 2 GiB bound, and never mutates the source row.

Concurrency uses **claims with fencing**: 90-second stale takeover, exact command binding,
request replay/conflict detection, and a post-delete reacquisition fence. Refreshing a
visual for a source whose delete is queued must not write a ready row.

### The capability sentinel (v0.8.86)

The packaged rollback state is **client flags baked ON, backend flag off** — because
`NEXT_PUBLIC_*` is inlined at build time and only the backend flag is a live switch. In
that state the client saw `visual: null, visual_status: null` for *both* "feature off" and
"not extracted yet", so it rendered Refresh/Remove buttons that could only 404.

Fix, with **zero extra requests** (a status endpoint would have added one per cover and
broken the e2e request ledgers):

```python
# api/schemas/source_visuals.py
SourceVisualStatusState = Literal[
    "queued", "processing", "unavailable", "failed", "disabled"
]

def disabled_visual_status() -> "SourceVisualStatusResponse":
    """Stamped by list/detail projections when the backend flag is off."""
    return SourceVisualStatusResponse(
        state="disabled", command_id=None, error_code=None,
        updated_at=datetime.now(timezone.utc),
    )
```

```python
# api/routers/sources.py — the else branch is the whole fix
if source_visuals_enabled():
    projected = await project_source_visuals(result)
    ...
else:
    sentinel = disabled_visual_status()
    response_list = [item.model_copy(update={"visual_status": sentinel})
                     for item in response_list]
```

The client then distinguishes the two cases:

```tsx
const visualsDisabled = source.visual_status?.state === 'disabled'
// 'disabled' → "Visual covers are turned off", actions hidden
// null       → genuinely not extracted yet, Refresh is legitimate
```

## 6. Local model health probing

`deeper_notebook/health/local_models.py`. Concurrency-capped at 4 so a wedged sidecar
can't stall the sweep. Two upstream quirks are compensated:

```python
if resp.status_code == 200:
    # mlx-lm 0.31 answers GET /v1/models with 200 and an EMPTY body — verified
    # live, before AND after a successful completion on the same server.
    try:
        data = resp.json()
    except ValueError:
        data = {}
```

```python
except httpx.TimeoutException:
    # The same endpoint hangs indefinitely after the first completion while
    # completions keep working. A read timeout is NOT "server down" — fall back
    # to the question this probe actually asks.
    if _port_accepts_connection(base_url):
        return {"name": name, "status": "healthy",
                "detail": "endpoint reachable (models list timed out)", ...}
```

Ollama gets its own 20 s read budget (`_OLLAMA_PROBE_TIMEOUT`) because `/api/tags`
legitimately takes 10–15 s during a store inventory.

## 7. FSRS spaced repetition

`fsrs>=6.3.1` schedules reviews. `study_card` holds stability/difficulty/due; `study_review`
is the immutable log. Scheduling is evidence-grounded — cards link to `study_plan_source`
so every prompt is traceable to a source. Anki import/export via `genanki==0.13.1` pinned
exactly for deterministic model/note semantics.

## 8. Vault sync

Bidirectional Markdown sync with Obsidian/Logseq vaults. `vault_trust_record` gates
whether a mount may be written. `vault_revision` + `vault_sync_receipt` make sync
idempotent and replayable; conflicts resolve to `'conflict'` receipts rather than silent
overwrites. Parsing uses `markdown-it-py` + `pyyaml` front-matter.

## 9. Memory (mem0)

`memory_fact` / `memory_preference` / `memory_episode`, recalled by cosine similarity with
per-table caps (`_MAX_FACTS`, `_MAX_PREFERENCES`, `_MAX_EPISODES`) and a total recall
budget so memory never dominates the prompt.

---

*Continues in [08 — Integration Points & External Services](./08-integration-points-external-services.md).*
