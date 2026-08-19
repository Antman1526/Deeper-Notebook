# Deeper Notebook — Architectural Review Context

**Audience:** an AI system asked to critique this codebase and propose concrete
optimisations, refactors, better patterns, or architectural improvements.
**Version:** desktop `0.8.100` · **Written:** 2026-08-17 · measured at `822d6fd3`

Every snippet below is **real code** from the repository, annotated for intent. Where I am
uncertain about an approach, it is marked **⚠️ UNCERTAIN** — those are the places I most
want challenged.

---

# 1. Project overview

**What it is.** A local-first, source-grounded research and knowledge workspace shipped as
a native macOS app. Hard fork of `lfnovo/open-notebook`, now independently versioned.
Recent additions: **ExamLab** (deterministic timed exams over quiz artifacts, snapshot-graded,
offline), **Debate mode** (a per-turn chat toggle that swaps in a steelman/concede/cite
prompt template), and **Cornell Notes** (a seeded transformation) — all sourced from the
`Study workbench` / `Evidence Studio` surfaces described in §3.4 and §4.9.

**The governing constraint** — everything else follows from it:

> The entire product must work with the network cable unplugged. Inference, embeddings,
> STT, TTS, database, and web server all run as local processes. Cloud is an accelerant,
> never a prerequisite.

**Stack.** Python 3.12.14 · FastAPI · LangGraph · SurrealDB 2.x · Next.js 16.2.12 ·
React 19.2.3 · PyWebView 5.4 · PyInstaller · uv.

**Scale.** 876 Python files (`git ls-files '*.py'`, tests included), 738 TS/TSX files,
4,929 backend tests, 807 desktop tests, ~1,775 frontend tests (not re-collected this pass),
96 DB migrations (48 up/down pairs), ~76 tables, 298 API routes. Earlier snapshots of this
document used a narrower file-count method (source only, no tests); the jump in file counts
reflects that methodology change, not new code written this pass — the test and route counts
are the real deltas, and they *are* new: two features (ExamLab, migration 48) and one bug fix
landed since the prior snapshot.

**Runtime topology.** A PyWebView shell hosts a local Next.js server, which proxies to a
local FastAPI backend, which talks to a bundled SurrealDB. A supervisor
(`desktop/launcher.py`) manages 9+ child processes on dynamically allocated ports.

---

# 2. Key code walkthrough

## 2.1 The chat tool loop — fail-soft binding

`deeper_notebook/graphs/chat.py`. Both chat surfaces share this. The single most
important behaviour is that **binding tools is allowed to fail**:

```python
# 3. Bind tools to the model — fail-soft for local providers that don't
# implement tool calling (v0.8.0 / v0.8.35f). If bind fails the model can't
# call ANY tool this turn, so reset the lookup to empty.
try:
    if mcp_tools:
        model = model.bind_tools(mcp_tools)
except Exception as bind_exc:
    _logger.debug("tool bind failed (degrading to no-tools): {}", bind_exc)
    mcp_tools = []      # ← must reset, or later dispatch looks up a tool that isn't bound
```

Tool assembly is deliberately split into independent `try` blocks. Originally MCP
resolution and native web-search binding shared one block, so a DB hiccup while listing
MCP servers also dropped the **DB-independent** web-search tool:

```python
# 2. Native env-keyed web_search tool — INDEPENDENT of MCP/DB (v0.8.64).
try:
    from deeper_notebook.tools.web_search import (
        WEB_SEARCH_TOOL_NAME, build_web_search_tool, web_search_enabled)
    _excluded_names = {(n or "").strip().lower() for n in (exclude_server_names or []) if n}
    if web_search_enabled() and WEB_SEARCH_TOOL_NAME not in _excluded_names:
        mcp_tools = list(mcp_tools) + [build_web_search_tool(mcp_captures)]
except Exception as ws_exc:
    _logger.debug("web_search tool build failed (skipping): {}", ws_exc)
```

**⚠️ UNCERTAIN.** This is five near-identical `try` blocks (MCP, web_search,
scholarly_search, opencode, add_web_source), each re-deriving `_excluded_names`. It is
explicit and independently failing — but it is also copy-paste. A registry of
`(predicate, builder, name)` tuples iterated once would be DRY-er. **Is the duplication
buying enough isolation clarity to justify itself, or is a registry strictly better?**

## 2.2 Provider failover with nested budgets

`deeper_notebook/tools/web_search.py`:

```python
deadline = time.monotonic() + _total_budget_sec()          # 25s across the WHOLE chain
for attempt_index, (provider, target) in enumerate(chain):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        break
    cap = (min(per_attempt_cap, _KEYLESS_TIMEOUT_SEC)      # keyless are cheap → 6s
           if provider in _KEYLESS_PROVIDERS else per_attempt_cap)
    attempt_timeout = min(cap, remaining)                  # later attempts shrink
    try:
        results = await _do_attempt(client, provider, target, query, n, attempt_timeout)
    except Exception as exc:
        logger.warning("web_search attempt via {}{} failed: {}",
                       provider, f" ({target})" if target else "", exc)
        continue                                            # error → next provider
    if results:
        _cache_put(cache_key, results, provider, attempt_index > 0)
        return results, provider, attempt_index > 0
    if provider == "searxng" or provider in _KEYLESS_PROVIDERS:
        continue          # FREE provider, empty answer → try next; costs nothing
    return results, provider, attempt_index > 0
    # ↑ PAID provider returning empty is a legitimate answer. Falling through would
    #   double the bill for no information. This asymmetry is intentional.
```

## 2.3 Pooled client with two correctness guards

```python
async def _acquire_client() -> tuple[object, bool]:
    """Return (client, pooled); the caller closes it only when not pooled."""
    factory = httpx.AsyncClient
    if (_pooled_client is not None
            and _pooled_client_loop is loop         # a client is bound to its creating loop
            and _pooled_client_factory is factory   # patched class in a test ⇒ rebuild
            and not getattr(_pooled_client, "is_closed", False)):
        return _pooled_client, True
    client = factory(limits=httpx.Limits(max_keepalive_connections=8, max_connections=16))
    ...
```

The `factory is factory` check is what lets tests monkeypatch `httpx.AsyncClient` without
one test's fake client leaking into the next. Measured: 513 ms → 341 ms.

**⚠️ UNCERTAIN.** Module-level mutable globals (`_pooled_client`, `_pooled_client_loop`,
`_pooled_client_factory`) with a `reset_web_search_caches()` for tests. **Would a small
class instance held on the FastAPI app state be cleaner, or does that just move the
global?** There is no clean owner today because tools are called from LangGraph nodes that
have no app context.

## 2.4 Health probing around upstream misbehaviour

`deeper_notebook/health/local_models.py` — two compensations for one dependency:

```python
if resp.status_code == 200:
    # mlx-lm 0.31's server answers GET /v1/models with HTTP 200 and an EMPTY
    # body (verified live: 0 bytes both before and after a successful chat
    # completion on the same server). A 200 proves the server is up, which is
    # what this probe measures — parse best-effort.
    try:
        data = resp.json()
    except ValueError:
        data = {}
```

```python
except httpx.TimeoutException:
    # The same endpoint stops completing after the first chat completion while
    # completions keep working. A read timeout does NOT mean the server is down.
    # Fall back to the question this probe actually asks.
    if _port_accepts_connection(base_url):
        return {"name": name, "status": "healthy",
                "detail": "endpoint reachable (models list timed out)", ...}
```

**⚠️ UNCERTAIN.** This is upstream-bug compensation living in our health layer. It is
honest and tested — but it will silently become dead weight when mlx-lm fixes `/v1/models`,
and nothing will tell us. **Should compensations like this carry an expiry/assertion that
fires when the upstream behaviour changes?**

## 2.5 Two-layer stamping for runtime propagation

`desktop/bootstrap.py`. A bundled-runtime bump used to ship in the `.app` and never reach
an existing install, because two independent caches both said "current":

```python
# Layer 1 — the extracted runtime is keyed to the tarball that produced it.
stamp_path   = runtime_dir / ".source-tarball.sha256"
tarball_hash = hashlib.sha256(tarball.read_bytes()).hexdigest()
if interpreter.exists():
    if stamp_path.exists() and stamp_path.read_text().strip() == tarball_hash:
        if _interpreter_is_healthy(interpreter):
            return interpreter                 # only skip when BOTH hold
        reason = "v0.7.212: detected partial/broken"
    else:
        reason = "v0.8.83: bundled runtime changed — stale"
    shutil.rmtree(runtime_dir, ignore_errors=True)
```

```python
# Layer 2 — the venv marker keys on interpreter identity + lock hash, not lock alone.
def _interpreter_stamp(standalone_python: Path) -> str:
    """OpenSSL is in the stamp on purpose: Wikimedia's edge 403s the OpenSSL 3.0
    TLS fingerprint, which is exactly the class of fix a runtime bump must deliver."""
    proc = subprocess.run([str(standalone_python), "-c",
        "import ssl,sys;print(sys.version.split()[0], ssl.OPENSSL_VERSION)"], ...)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown-interpreter"
```

## 2.6 The capability sentinel

The packaged rollback state is *client flags baked ON, backend flag off* — because
`NEXT_PUBLIC_*` is inlined by `next build`. In that state the client couldn't distinguish
"feature off" from "not extracted yet" (both `null`), so it offered buttons that 404'd.

```python
# api/routers/sources.py — the else branch is the entire fix
if source_visuals_enabled():
    projected = await project_source_visuals(result)
    ...
else:
    sentinel = disabled_visual_status()          # state="disabled"
    response_list = [item.model_copy(update={"visual_status": sentinel})
                     for item in response_list]
```

```tsx
const visualsDisabled = source.visual_status?.state === 'disabled'
{onRefresh && !visualsDisabled ? <button …/> : null}
```

Chosen over a capability endpoint because that would add one request per cover and break
the e2e suites' exact request ledgers.

**⚠️ UNCERTAIN.** A sentinel is stamped onto **every row** of every list response when the
feature is off — N identical objects for one boolean. **Is a top-level
`capabilities: {source_visuals: false}` on the response envelope the better shape?** It
would need a response-envelope change across three routers.

---

# 3. Data flow and dependencies

## 3.1 Source ingestion

```
User drops a PDF
  → POST /api/sources (multipart)
  → content-core extracts text
  → source row + source_embedding chunks (local embed sidecar)
  → RELATE notebook -> reference -> source
  → optional: source_visual extraction (bounded, cached WebP)
```

## 3.2 A grounded chat turn

```
UI  POST /api/chat (SSE)
  → LangGraph chat node
  → memory recall (cosine over memory_fact/preference/episode, budget-capped)
  → source context (vector search over source_embedding, char-capped)
  → offline gate: cloud candidate + offline ⇒ substitute local model
  → bind_tools (fail-soft)
  → model invoke → tool_calls? → execute → ToolMessage → re-invoke (≤4)
  → SSE stream to client; captures render as citation pills
```

## 3.3 Startup data flow

```
config.toml → phases → bootstrap (stamped runtime + venv)
  → supervisor spawns 9 sidecars on dynamic ports
  → auto_register REFRESHES every credential's base_url for this launch
  → phase1 health probes → runtime snapshot → UI
```

Ports change every launch, so credentials are rewritten each time. This is why a stale
`base_url` is a recurring class of bug and why `auto_register` runs before the UI opens.

## 3.4 Schema highlights

```sql
DEFINE FIELD IF NOT EXISTS created ON source
  DEFAULT time::now() VALUE $before OR time::now();   -- immutable created
DEFINE EVENT IF NOT EXISTS source_delete ON TABLE source WHEN ($after == NONE) THEN {
    delete source_embedding where source == $before.id;
    delete source_insight   where source == $before.id;
};
```

Counts come from graph traversal, not joins:
`count(<-reference.in) AS source_count`.

`study_exam_attempt` (migration 48) snapshots quiz questions at attempt start — editing or
regenerating the source artifact mid-attempt can never corrupt grading, since scoring reads
the snapshot, not the live artifact. `seeded_indices` prevents the FSRS-seeding endpoint from
double-creating a card for a miss that was already seeded on an earlier call.

## 3.5 External dependencies

Optional, all fail-soft: OpenAI/Anthropic/Google/Groq/Mistral/DeepSeek/Ollama (LLM),
Serper/Tavily/Brave/SearXNG/Wikipedia (search), OpenAlex/arXiv (scholarly), MCP servers,
Gmail, Hugging Face, OpenChronicle.

Local, expected-present: llama.cpp, MLX, faster-whisper, piper-tts, mem0, SurrealDB.

---

# 4. Pain points and known limitations

### 4.1 Source-shape tests are brittle — but they are NOT what blocks a formatter

**Measured 2026-08-19, and the result overturned the assumption.** `ruff format`
was applied to the whole repository (700 files reformatted, 422 already clean)
and the suite re-run: **5,625 passed, 6 failed.** All six were identity-audit
tests (`test_product_identity.py`, `test_persisted_queue_identifiers.py`). Not
one of the ~469 source-text assertions across 88 files broke.

So the formatter blocker is §4.2's allowlist, not these guards. `--regenerate`
after the reformat fails outright:

    ValueError: unclassified occurrence requires explicit review:
      {'path': 'desktop/tests/test_data_root_migration.py',
       'pattern': 'open_notebook', 'line': 839, ...}

Because entries are keyed on `(path, pattern, source, line, column,
context_sha256)`, a repo-wide reflow invalidates context hashes en masse, and
each new one demands manual classification. The formatting change was reverted;
adopting a formatter requires re-keying that allowlist on content or AST
identity first (§4.2), which is a project of its own.

The original brittleness note still stands on its own terms:
Tests that grep source text for exact literals. They caught real regressions, but a
`ruff --fix` import reflow and a 6-line insertion each broke one during this project.

```python
assert "from deeper_notebook.database.repository import repo_query" in src
```
The current workaround is a `# noqa: I001` block so isort won't merge two imports.
**This is a smell.** AST-based assertions would express the invariant without pinning
formatting.

### 4.2 The rebrand allowlist is line-pinned — and the re-key is harder than it looks

**Attempted 2026-08-19; reverted. The finding is worth more than the attempt.**

The approach was sound and got most of the way: hash whitespace-NORMALIZED line
content instead of the raw line, and fall back from the exact positional key to
`(path, pattern, source, digest)` when it misses. With a verifying migration of
all 2,616 approvals (plus the `_PINNED_SELECTOR_INVENTORY_SHA256` gate and 22 of
25 contract coverage digests recomputed), `--check` passed, and a repo-wide
`ruff format` went from *invalidating everything* to breaking **5 entries** —
each a line ruff genuinely re-split, which SHOULD be re-reviewed.

It was reverted because dropping `column` from the key is a real security
weakening, and the suite already proves it:
`test_exact_context_does_not_hide_distinct_same_line_active_occurrence` puts
`open_notebook` on one line **twice** — one occurrence approved, one not — and
asserts the unapproved one is still flagged. Ignoring `column` makes the
approval cover both. The authors anticipated exactly this relaxation.

So `column` is not incidental position; it carries intra-line occurrence
identity. Making that reformat-stable means replacing absolute column with an
**occurrence ordinal within the line** (1st vs 2nd match of that pattern) —
stable under reindentation, still distinguishing the two occurrences. That
ordinal has to be stored in the allowlist AND computed scanner-side, and
`classify_match` currently receives only the key, not the source line, so it
cannot derive it. Threading it through changes `_occurrence_key`'s arity, which
ripples across ~55 assertions in `tests/test_product_identity.py`.

That is the actual shape of the work: a scanner refactor, not a keying tweak.
Also note the hashing is **duplicated** in `scripts/persisted_queue_inventory.py`
(rebrand_audit imports it, so it cannot import back); when only one side
normalized, 30 compatibility entries silently resolved to a null contract.

### 4.2a The original note still stands
`scripts/rebrand-allowlist.json` keys entries on
`(path, pattern, source, line, column, context_sha256)` and loads its contracts *from
itself*. Any edit that shifts a pinned line breaks the audit; hand-repair fails validation;
`--regenerate` must be the last action after all edits. This cost three build failures in
one day. **⚠️ The design is defensible (it prevents silent identity drift) but the
line-coupling is accidental complexity.**

### 4.3 Frontend flags are frozen at build time
`NEXT_PUBLIC_*` inlining means a packaged app cannot roll back a UI feature. This produced
the dead-button defect (§2.6). Any future flag needs a backend counterpart to be
rollback-able.

### 4.4 79 → 0 B608 findings, mostly by annotation
One site was genuinely fixed (`ensure_record_id`); 78 were verified and tagged `# nosec`.
The underlying pattern — f-string SurrealQL with whitelisted identifiers — is safe *as
audited today* but relies on every future edit maintaining the discipline.
**A typed query builder would make this structural instead of procedural.**

### 4.5 Cold start is ~106 s; warm is ~13 s
Measured, decomposed, and root-caused this pass. `api_ready` accounts for 19 s; sidecar
*spawning* is 26 ms across all six sidecars (memory 10 ms, llamacpp_embed 6 ms, llamacpp_chat
3 ms, openchronicle 3 ms, whisper 2 ms, piper 2 ms) — negligible, not the cost. The remaining
~86 s is a single silent gap in `launcher.log` ending at "Local GGUF (llama.cpp): healthy" —
the `_wait_tcp` gate waiting for a 4.9 GB chat GGUF to cold-mmap. **This is not iCloud** (an
earlier note in this document's history wrongly attributed it to iCloud sync; verified
`~/Desktop` is a plain local directory, not synced). The model root
(`/Users/Antman/Desktop/MacBook AI models`) is 1.0 TB on an internal SSD that is 90% full —
APFS read latency degrading near capacity is the far more likely cause. Freeing space on that
volume, not moving files off iCloud, is the applicable fix. The shell opens before the model
is ready (`wait_for_ready=False`), which mitigates perception but not cost.

### 4.6a React `act()` warnings — diagnosed, deliberately not fixed

~100 warnings across 15+ components. Every test passes; these are noise, not
defects. Grouped by emitting component (2026-08-19):

    GuidedTipsProvider 16 · Tooltip 13 · ThemeProvider 12 · KnowledgeExplorer 12
    ThemeSwitcher 5 · StudyProgressPanel 4 · SourcesColumn 4 · Presence 4 · …

There is no single root cause — at least three:

1. **`MutationObserver` state updates.** `GuidedTipsProvider` repositions its
   callout from a `MutationObserver` callback, which fires in a microtask
   outside React's `act()` scope. The component is behaving correctly; the test
   simply cannot wrap a mutation it did not cause.
2. **Radix internals.** `Tooltip`, `PopperContent` and `Presence` (20 warnings)
   are third-party async state driven by hover/focus. Silencing them means
   changing how tests drive tooltips, not fixing our code.
3. **Assorted unawaited async state** in the remaining components — genuinely
   per-test work.

Not done on purpose. Quieting these means editing ~25 currently-passing test
files across three unrelated causes, immediately after v0.8.102 root-caused and
fixed this suite's non-determinism. Trading real flake risk in a suite that was
just made deterministic for quieter console output is a bad exchange. Worth
doing per-cluster, deliberately, when someone is already working in that area.

### 4.6 Five near-identical tool-binding blocks
See §2.1.

### 4.7 Test-isolation via env is unsafe
Product env normalization mirrors canonical names into legacy spellings; `monkeypatch`
cannot undo writes it did not make, so setting a flag via env leaks into later modules.
The fix (patch the predicate, or clear all spellings from the registry) is now documented,
but the underlying mirroring behaviour is a footgun.

### 4.8 Two version tracks
`pyproject.toml` = 1.8.5 (server/Docker), `desktop/__init__.py` = 0.8.100 (app). Correct,
deliberately unreconciled — and confusing every single time.

### 4.9 Auto-route hard-failed with no benchmark history (found and fixed this pass)
`provision_langchain_chat_model`'s local candidate comes from
`DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID` or, failing that, `_measured_local_chat_model_id()` —
which returns a model **only when benchmark history proves one**. A fresh install has none.
With no cloud credential either, both candidates were `None` and `pick_provider` raised its
step-5 "impossible state" on every chat turn, even though a valid `default_chat_model` sat
configured and unused. Fixed by delegating to the default path when both candidates are
`None` — routing between zero candidates was never real routing. The tempting one-liner
(assigning the default to `local_model_id`) was rejected: the privacy gate uses
`local_model_id` as its keep-on-device reroute target, so that would have let secrets leak to
cloud while reporting them kept local. **This is the kind of defect that only shows up
driving the real app** — every unit test in the routing suite passed throughout; the gap was
between the router (a correct pure function) and its caller (which handed it two `None`s
instead of degrading).

---

# 5. Design decisions and trade-offs

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Database | SurrealDB | Postgres + pgvector | Documents + graph + vectors in one bundled binary; no user install |
| Desktop shell | PyWebView + Next | Electron / Tauri | Python backend already required; Electron doubles the runtime |
| Runtime | Bundled portable Python + user venv | Fully frozen | Heavy ML deps don't freeze cleanly; venv allows repair without reinstall |
| Keyless search | Wikipedia only | DDG scraping | DDG returns HTTP 202 anti-bot to scripted clients — verified live, parser written and deleted |
| Scholarly | Separate tool | Extra providers in `web_search` | Wikipedia ends the chain first; and papers are a bad answer to a price question |
| Feature rollback | Backend flag + sentinel | Capability endpoint | Zero extra requests; preserves exact e2e ledgers |
| Identity governance | Line-pinned self-validating registry | Pattern allowlist | Exactness prevents drift; costs line-fragility |
| Signing | Stable self-signed | Ad-hoc | Ad-hoc resets TCC every rebuild → silent launch wedge |
| Flake handling | Retry failed once | Loosen budgets | Loosening discards the signal the test exists for |

**Constraints that shaped everything:** no cloud requirement; no admin install; one user;
Apple Silicon first; and a fork relationship that must remain merge-friendly with upstream
while carrying its own identity.

---

# Areas for Review

Specific questions I want evaluated. Please be concrete and, where you disagree, say what
you would build instead.

1. **Tool binding (§2.1).** Five near-identical `try` blocks vs. a
   `(predicate, builder, name)` registry. Does the registry lose meaningful failure
   isolation? Is there a third shape that keeps per-tool isolation *and* removes the
   duplication?

2. **Global pooled client (§2.3).** Module-level mutables with a test-reset function. Is
   there a clean owner for per-process HTTP clients when the callers are LangGraph nodes
   with no app context? Would a context-var-scoped client be better?

3. **Capability sentinel shape (§2.6).** Stamping a sentinel on every row vs. a
   `capabilities` block on the response envelope. Which ages better as more features gain
   backend kill switches?

4. **Upstream-bug compensation (§2.4).** How should code that works around a dependency's
   defect signal that the workaround is now unnecessary? Is there a pattern for
   "assert the bug still exists" that isn't a flaky network test?

5. **Source-shape tests (§4.1).** What is the right way to pin an invariant like "this
   import must stay guarded by try/ImportError" without pinning formatting? Is an AST
   matcher worth the complexity over a text grep?

6. **SurrealQL safety (§4.4).** Is a typed/parameterised query builder worth the
   refactor across ~80 call sites, or is the whitelist-identifier + bound-value discipline
   plus Bandit enforcement sufficient? If a builder — what shape, given SurrealQL's graph
   traversal syntax has no ORM?

7. **The rebrand allowlist (§4.2).** Can this be redesigned to key on AST node identity
   or content hash *without* line numbers, while preserving exactness? Or is the line
   pinning load-bearing in a way I'm not seeing?

8. **Build-time frontend flags (§4.3).** Is there a way to keep Next's inlining benefits
   while allowing runtime rollback — a small runtime-config endpoint the client reads at
   boot, with the inlined value as the default?

9. **Startup latency (§4.5).** Decomposed this pass: sidecar spawning is 26 ms total,
   not the cost; ~86 s of the ~106 s cold start is a single GGUF cold-mmap gated by
   `_wait_tcp`, and the disk it's reading from is 90% full. Given the bottleneck is
   filesystem/hardware, not this codebase, is there anything left worth building here —
   a disk-space warning at first-run, `mmap` prefetch/readahead hints, or is "tell the
   operator to free space" the honest answer?

10. **Layering.** `deeper_notebook/` must not import `api/` or `desktop/`, and `domain/`
    must not import graphs. Are there violations implied by the descriptions above? Would
    a hexagonal/ports-and-adapters restructure pay for itself at this size, or is the
    current pragmatic layering appropriate?

11. **Test suite economics.** 4,929 backend + 807 desktop + ~1,775 frontend tests gate a
    25-minute build. Is there a defensible split — smoke gate on build, full suite on a
    schedule — that keeps the safety this project clearly depends on?

13. **Auto-route's fallback (§4.9).** The fix delegates to the default path when neither
    candidate resolves. Is silent degradation the right UX, or should the toggle surface
    "auto-route has nothing to route between yet — benchmark a model" instead of quietly
    behaving as if it were off?

12. **What would you delete?** This codebase has accreted defensively; nearly every guard
    traces to a real incident. Which guards now look redundant, and what evidence would
    justify removing them?
