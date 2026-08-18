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

## 7a. ExamLab — deterministic grading over a snapshot

`deeper_notebook/study/exams.py`. `build_attempt` snapshots the quiz artifact's questions
(prompt, options, `correct_option_id`, explanation, citations) into the attempt row at
creation time — grading later reads only that snapshot, never the live artifact, so editing
or regenerating the source quiz mid-attempt cannot corrupt or invalidate a grade in progress.

```python
# deeper_notebook/study/exams.py — grade_attempt
if attempt.submitted_at is not None:
    raise StudyExamConflict("attempt is already submitted")
submitted = now or datetime.now(UTC)
results: list[ExamQuestionResult] = []
correct_count = 0
for question in attempt.questions:
    selected = answers.get(str(question.index))
    valid_ids = {option.id for option in question.options}
    # An unknown option id (malformed client) counts as unanswered, not an
    # error — a bad request body must not make the whole attempt ungradable.
    answered = selected is not None and selected in valid_ids
    is_correct = answered and selected == question.correct_option_id
    if is_correct:
        correct_count += 1
    results.append(ExamQuestionResult(
        index=question.index, correct=is_correct, answered=answered,
        selected_option_id=selected if answered else None,
        correct_option_id=question.correct_option_id,
        explanation=question.explanation, citations=list(question.citations),
    ))
graded = attempt.model_copy(update={
    "submitted_at": submitted, "late": submitted > attempt.deadline,
    "answers": {str(k): str(v) for k, v in answers.items()},
    "results": results, "correct_count": correct_count,
    "score_percent": round(100.0 * correct_count / attempt.question_count, 1),
})
```

A late submission is graded and flagged (`late=True`), never rejected — the deadline is
informational, not a lockout, since ExamLab has no server-side clock enforcement to make
rejection meaningful. `missed_question_cards` builds FSRS cards only for indices not already
in `seeded_indices`, so calling the seed endpoint twice creates zero cards the second time —
an idempotent, not merely safe-to-retry, endpoint.

## 7b. Debate mode — a prompt swap, not a parallel code path

`deeper_notebook/graphs/chat.py`. Debate mode changes exactly one thing: which Jinja
template `call_model_with_messages` renders.

```python
# deeper_notebook/graphs/chat.py
# Debate mode swaps the whole system template rather than appending a stance
# instruction: an appended instruction fights the base template's "helpful
# assistant" framing and loses on smaller local models. The debate template
# carries its own copy of the grounding + citing contracts, so citations
# behave identically.
_template = (
    "chat/debate"
    if state.get("chat_mode") == "debate"
    else "chat/system"
)
system_prompt = Prompter(prompt_template=_template).render(data=prompt_data)
```

Everything downstream — tool binding, retrieval, citation formatting — is unchanged; the
prompt contracts the model to steelman the opposing position, concede when the sources
genuinely support the user's claim, and cite every assertion. **Design note:** because the
debate template duplicates the citation contract rather than extending the standard one,
the two prompts can drift out of sync if the citation rules change — there is no shared
partial. Acceptable for now given the surface area (two files), but worth a Jinja include if
a third mode is ever added.

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
