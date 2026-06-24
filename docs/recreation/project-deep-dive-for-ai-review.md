# Open Notebook Plus — Technical Deep-Dive for AI Review

> **Audience:** another AI agent that will reason about this codebase and propose
> optimizations/refactors. This document favors *density* over prose. Snippets are
> **real code** (lightly trimmed, never pseudocode), annotated with intent. Secrets
> are sanitized. Where I suspect a better approach exists, I flag it with
> **⚠️ REVIEW**.
>
> Refreshed 2026-06-24 against the `desktop-app` tree. File paths are
> absolute-from-repo-root unless noted. Version tags like `v0.8.68` are the repo's
> own per-commit changelog markers and double as inline code comments.

---

## 1. Project Overview

### Purpose

**Open Notebook Plus (ONP)** is a **privacy-first, local-first NotebookLM alternative**:
a desktop research assistant that ingests multi-modal sources (PDF/audio/video/web),
generates AI notes, does semantic + keyword search, lets you chat *grounded in your
own sources*, and produces multi-speaker podcasts — **with the option to run 100%
on-device** (llama.cpp / Ollama sidecars, local SurrealDB, local TTS/STT). It is a
**desktop fork** of upstream `lfnovo/open-notebook`, adding a native macOS/Windows
launcher, AI sidecars, an offline/online smart-switching layer, a privacy gate, and
a podcast/prompt-optimizer pipeline on top of the upstream three-tier core.

The Plus app **runs natively on the host** (`.dmg` / Windows local install) — never
in Docker (Docker remains a supported deployment target for the upstream server, but
the desktop experience is native PyInstaller + pywebview).

### Core functionality

- **Notebooks / Sources / Notes / Insights** — domain records in SurrealDB, related
  via graph edges.
- **Chat** (two surfaces): notebook-wide chat (`graphs/chat.py`) and source-scoped
  chat (`graphs/source_chat.py`), both single-node LangGraph state machines with MCP
  tool-calling, web search, and memory recall.
- **Ask** (`graphs/ask.py`) — multi-search-strategy retrieval + synthesis.
- **Source ingestion** (`graphs/source.py`) — extract → save → embed (fire-and-forget
  jobs) → transform.
- **Podcasts** — staged LangGraph generation (outline → transcript → audio → combine)
  with progress, cancel, and outline-review (`commands/podcast_staged.py`).
- **Prompt optimizer** — trains transformation prompts with Microsoft SkillOpt against
  real sources (`open_notebook/prompt_optimizer/`).
- **Evidence Studio / Course Pack** — turns uploaded files, links, and existing
  notebook sources into source-grounded reports, study guides, instructor-ready Course
  Packs, quizzes, data tables, mind maps, slide-deck outlines, podcast outlines, and
  research runs (`api/routers/studio.py`, `open_notebook/studio/artifact_generation.py`).
- **Memory** — mem0-style fact/preference/episode recall woven into the chat system
  prompt.
- **Offline gate + smart router** — instant local-model substitution when offline.

### Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 / React 19, TypeScript, Zustand, TanStack Query, Tailwind + shadcn/ui, port 3000 |
| API | FastAPI (Python 3.11+), LangGraph state machines, Loguru, Pydantic v2, port 5055 |
| DB | SurrealDB (graph + vector + full-text), async driver, auto-migrations on startup, port 8000 |
| AI abstraction | **Esperanto** — unified factory for 8+ providers (OpenAI, Anthropic, Google, Groq, Ollama, Mistral, DeepSeek, xAI, OpenRouter, Azure, Vertex, openai_compatible) |
| Job queue | **surreal-commands** — DB-backed async command queue (podcasts, embeddings, insights, prompt-opt) |
| Desktop | PyInstaller bundle, pywebview window, splash + python handoff controller, tray, singleton lock |
| Sidecars | llama.cpp chat server, MLX server, Ollama, faster-whisper STT, local TTS, memory dashboard, MCP servers |
| Podcasts | `podcast-creator` library (its compiled LangGraph is streamed directly) |
| Prompts | `ai-prompter` (Jinja2 templates referenced by path, e.g. `chat/system`) |
| Content | `content-core` (50+ file types), optional `crawl4ai` (Playwright) URL engine |

### High-level architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  DESKTOP LAUNCHER  (desktop/launcher.py, window.py, splash.py)         │
│  • PyInstaller bundle, pywebview window, singleton lock, tray          │
│  • spawns + health-gates: SurrealDB, FastAPI, Next.js, AI sidecars     │
│  • auto-registers sidecar ports into env (OPEN_NOTEBOOK_LOCAL_*),      │
│    auto-export backups, self-healing DB repair, RAM-aware n_ctx        │
└───────────────┬──────────────────────────────────────────────────────┘
   spawns/gates │                       ┌──────── AI SIDECARS (native) ───────┐
                │                       │ llama.cpp (openai_compatible) :PORT  │
┌───────────────▼─────────────┐  HTTP   │ Ollama  :11434                       │
│  FRONTEND  Next.js :3000     │◄───────►│ faster-whisper STT, local TTS        │
└───────────────┬─────────────┘  REST   │ memory dashboard, MCP servers        │
                │ HTTP REST              └──────────────────────────────────────┘
┌───────────────▼─────────────┐
│  API  FastAPI :5055          │  LangGraph workflows · surreal-commands jobs ·
│  api/ + open_notebook/       │  Esperanto provisioning · offline gate · privacy gate
└───────────────┬─────────────┘
                │ SurrealQL
┌───────────────▼─────────────┐
│  SurrealDB :8000             │  records + edge relations + vector (HNSW) + BM25 FTS
└──────────────────────────────┘
```

The launcher is the orchestration brain on the desktop: it decides ports, RAM tiers,
which sidecars to start, and writes their URLs into env vars (e.g.
`OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL`) that the API's smart router reads at request time.

Local model discovery is rooted at `~/Desktop/AI_Models` by default. GGUF models live
under `GGUF/`; complete Apple-Silicon MLX repos live under `MLX/` and are served by
`python -m mlx_lm.server`; Ollama is detected from the running service.

---

## 2. Key Code Walkthrough

### 2.1 The chat LangGraph (`open_notebook/graphs/chat.py`)

A **single-node** StateGraph (`agent` node) with a SQLite checkpointer for per-thread
message history. The state shape is a `TypedDict` with an `add_messages` reducer; note
the *append-only* reducer is exactly why message-history trimming is mandatory:

```python
class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]   # append-only reducer → grows forever
    notebook: Optional[Notebook]
    context: Optional[str]
    model_override: Optional[str]
    selected_provider: Optional[str]          # smart-router decision plumbed to HTTP resp
    privacy_gated: Optional[bool]             # gate rerouted cloud→local (labels only)
    agent_state: Optional[str]                # FSM terminal state: complete/clarify/truncated
    mcp_tool_calls: Optional[list]            # captures for citation-pill popovers
    disabled_mcp_servers: Optional[list[str]] # per-request "load only what I need"
    bypass_privacy_gate: Optional[bool]       # explicit per-turn "send to cloud anyway"
```

**Two checkpointers over one SQLite file.** LangGraph ≥0.6 split sync vs async
checkpointers; `astream_events`/`ainvoke` call `aget_tuple()` which the sync
`SqliteSaver` raises `NotImplementedError` on. The fix keeps both, lazily constructing
the async twin so module import doesn't need a running event loop:

```python
async def get_async_graph():
    """AsyncSqliteSaver-backed twin of `graph`, lazily constructed on first call.
    Both savers point at the SAME on-disk SQLite file — WAL mode keeps them
    consistent. Lazy because aiosqlite.connect() captures the current event loop
    in __init__, and at import time there's no loop yet."""
    global _async_graph, _async_aio_conn
    if _async_graph is not None:
        return _async_graph
    with _async_graph_lock:                    # threading.Lock, NOT asyncio.Lock
        if _async_graph is not None:           #   (asyncio.Lock needs a loop at construct)
            return _async_graph
        aio_conn = await aiosqlite.connect(LANGGRAPH_CHECKPOINT_FILE)
        _async_graph = agent_state.compile(checkpointer=AsyncSqliteSaver(aio_conn))
        _async_aio_conn = aio_conn
    return _async_graph
```

> ⚠️ **REVIEW:** two savers over one SQLite file relying on WAL for consistency is
> clever but fragile. The double-checked-locking with a `threading.Lock` guarding an
> `await` is correct here but unusual — worth confirming no second event loop can
> race it. Also: `close_async_graph()` swallows all exceptions on shutdown FD cleanup.

**The node itself** (`call_model_with_messages`) is natively async (a v0.7.37 rewrite
that removed a per-call `ThreadPoolExecutor`+`new_event_loop()` bridge that cost ~30ms
and killed httpx keepalive pools). Its flow:

1. Recall memory facts for the system prompt (orchestrator: recency < ~30 rows, else
   semantic).
2. Trim message history (`ONP_CHAT_HISTORY_CHAR_CAP`, default 12 000 chars).
3. **Size the context against actual message *content*, not `str(payload)`** — a real
   bug this codebase was bitten by:

```python
# v0.7.65 — size against the ACTUAL message text only. The previous version passed
# str(payload), i.e. the repr() of a list of LangChain Message objects, which adds
# ~80-120 chars of wrapper noise PER message (additional_kwargs={}, response_metadata={}).
# Over a 50-turn session that's ~5k phantom "tokens" → premature large_context routing.
content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)
```

4. Provision the model. If a `model_id` override exists → explicit path; else →
   `provision_langchain_chat_model` (smart router). Both receive `fallback_out` (the
   offline-gate channel) and `selection_out` (the router-decision channel).

5. Run the **shared MCP tool loop** (`bind_mcp_and_run_tool_loop`), reused by both chat
   surfaces. Key hardening lives here:

```python
# v0.8.66 (audit S-3/A-5) — fence external tool output as UNTRUSTED so the model
# treats it as DATA, not instructions. MCP/web-search results are attacker-influenceable
# and were previously injected verbatim — embedded "ignore previous instructions" could
# hijack the turn AND poison long-term memory via the fire-and-forget extractor.
tool_msgs.append(ToolMessage(
    content=_fence_untrusted_tool_output(name, str(result)),  # delimiter + directive
    tool_call_id=call_id,
))
```

```python
# v0.8.66 (audit A-4) — bound EACH model.ainvoke. /chat/stream has no outer route
# timeout (it only halts on client disconnect); a wedged sidecar that never streams
# would hang the turn forever. Default 300s, env-tunable, guarded parse.
ai_message = await asyncio.wait_for(model.ainvoke(payload), timeout=model_timeout)
```

6. **Mid-turn offline retry** — the captive-portal leg. If a cloud call fails with a
   *network-classified* error and we weren't already local, flip network state and
   retry ONCE on the gated (now-local) model:

```python
except Exception as e:
    error_class, _ = classify_error(e)
    already_local = bool(offline_fallback_out.get("offline_fallback"))
    if error_class is not NetworkError or already_local:
        raise                          # not a network error, or already local → propagate
    report_network_failure()           # passively flip the cache OFFLINE
    model = await provision_langchain_model(content_for_sizing, model_id, "chat",
                                            fallback_out=retry_fallback, max_tokens=8192)
    if not retry_fallback.get("offline_fallback"):
        raise                          # gate didn't substitute (no local model) → original error
    ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(model, payload, ...)
```

> ⚠️ **REVIEW:** the MCP tool loop has **three** env-tunable timeouts
> (`ONP_MCP_TOOL_TIMEOUT_SEC`, `ONP_CHAT_MODEL_TIMEOUT_SEC`, plus the iteration cap
> `ONP_AGENT_MAX_ITERATIONS`) and a JSON-Schema→Pydantic converter
> (`_json_schema_to_pydantic_model`) handcrafted inline. The converter only covers the
> common shapes; nested `$ref`/`oneOf`/`allOf` fall through to `Any`. Consider whether
> a maintained lib (e.g. `datamodel-code-generator` style) should own this.

### 2.2 Offline gate + smart router + network service

**Network service** (`open_notebook/health/network.py`) — a process-wide singleton with
a 20s TTL cache, single-flight probe lock, and passive flips from real call outcomes.
**Design invariant: "unknown" is treated as ONLINE** so a flaky probe can never block
cloud calls:

```python
@dataclass(frozen=True)
class NetworkState:
    status: Literal["online", "offline", "unknown"]
    forced_offline: bool
    checked_at: float                  # time.monotonic()
    source: Literal["probe", "call-failure", "call-success", "override", "init"]

async def get_network_state(*, forced_offline_lookup=None) -> NetworkState:
    # forced-offline (user toggle) short-circuits with NO probe
    if forced_offline_lookup is not None:
        try: forced = bool(forced_offline_lookup())
        except Exception: forced = False          # settings hiccup must never brick cloud
        if forced: return NetworkState("offline", True, time.monotonic(), "override")
    now = time.monotonic()
    if _state is not None and now - _state.checked_at < _ttl_s():
        return _state                              # TTL hit
    async with _get_probe_lock():                  # single-flight: concurrent misses share one probe
        ...                                        # re-check under lock, then asyncio.to_thread(_probe_once)
```

```python
def _probe_once() -> bool:
    # Blocking 2s TCP connect to 1.1.1.1:443 / 8.8.8.8:443 (override ONP_NET_PROBE_HOSTS).
    # Runs on a worker thread via asyncio.to_thread so the event loop never blocks.
    for host, port in _probe_targets():
        try:
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
                return True
        except OSError:
            continue
    return False
```

`report_network_failure()` / `report_network_success()` let real cloud-call outcomes
flip the cache instantly — this is what covers captive portals where the TCP probe
*lies* (port 443 connects but HTTP is intercepted).

> ⚠️ **REVIEW:** the probe targets are Cloudflare/Google DNS on :443 — a TCP connect,
> not a TLS/HTTP check. Behind a captive portal that transparently accepts :443, the
> probe returns "online" and only the *passive* call-failure path corrects it. Also
> the forced-offline boolean is cached **twice** (a 30s `_forced_cache` in `network.py`
> *and* the 20s state TTL) — two TTLs for one toggle is a latent staleness trap.

**Offline gate** (`open_notebook/ai/offline_gate.py`) sits in the *single funnel* every
workflow uses (`provision_langchain_model`). It is **fail-open by design** — the only
raise is the actionable "offline + no local model" case:

```python
LOCAL_PROVIDERS = frozenset({"ollama", "openai_compatible"})  # both are machine-local sidecars

async def gate_language_model_id(candidate_id, *, fallback_out=None):
    if not candidate_id: return candidate_id
    record = await _get_model_record(candidate_id)            # load BEFORE probing →
    if record is None: return candidate_id                    #   local candidates pay ZERO probe cost
    if getattr(record, "type", None) != "language": return candidate_id  # don't gate embed/TTS/STT
    if _is_local(getattr(record, "provider", None)): return candidate_id

    state = await get_network_state_with_settings()
    if state.status != "offline":   return candidate_id       # online AND unknown both pass

    fallback = await find_local_language_model()
    if fallback is None:
        raise ConfigurationError("You're offline and no local model is installed. ...")
    if fallback_out is not None:
        fallback_out.update({"offline_fallback": True, "from_model_id": candidate_id,
                             "to_model_id": fallback.id, "to_model_name": fallback.name,
                             "reason": "forced-offline" if state.forced_offline else "offline"})
    return fallback.id
```

**Smart router** (`provision_langchain_chat_model` in `ai/provision.py`) wraps
`provision_langchain_model` with a local/cloud decision when smart routing is enabled
(env var precedence, else the `auto_route_enabled` DefaultModels toggle). It probes
local sidecar health with a **30s TTL + single-flight lock** because the underlying
httpx probe can block up to 9s:

```python
async def _local_chat_healthy_cached(model_name="Local GGUF (llama.cpp)") -> bool:
    if _health_cache is not None and now - _health_cache[0] < _HEALTH_CACHE_TTL_S:
        return _health_cache[1].get(model_name, False)        # fast path: read OUTSIDE lock
    async with _get_health_cache_lock():                      # single-flight cache-miss
        ... # v0.8.20 — await asyncio.to_thread(probe_all_local_models, creds)
            #   the sync httpx.get blocks the WHOLE event loop otherwise (9s structured timeout)
```

The router also reserves **reply headroom** so a prompt that *fits* n_ctx doesn't
overflow once the 8192-token reply is reserved (a real llama.cpp HTTP 400 this was
bitten by — `v0.8.66 audit A-6/A-7`), and runs the **privacy gate** before labeling the
decision. Note the layered defenses: offline gate (inside `provision_langchain_model`),
privacy gate (here), smart router, *and* the mid-turn retry — four interacting layers
deciding which model runs.

> ⚠️ **REVIEW:** model selection is now spread across `provision_langchain_chat_model`
> (router + privacy gate + headroom), `provision_langchain_model` (size threshold +
> offline gate), `offline_gate.py`, `router.py`, and `privacy_gate.py`. The control
> flow is hard to follow and each layer reads `model_manager.get_defaults()`
> independently (multiple DB round-trips per turn). A single resolved "ModelDecision"
> object computed once would simplify and speed this up. The 105 000-token large-context
> threshold is hard-coded (not env-tunable).

### 2.3 Staged podcast runner (`commands/podcast_staged.py`)

`podcast-creator.create_podcast()` is a black box (one awaited call, no progress, no
cancel). But the library *exports* its compiled LangGraph with four named nodes, so ONP
**streams the graph** instead of calling the black box — unlocking progress, cancel, and
outline-review with zero forking:

```python
NODE_DONE_NEXT_STAGE = {            # when node X completes → run is now in stage Y
    "generate_outline":   STAGE_TRANSCRIPT,
    "generate_transcript": STAGE_AUDIO,
    "generate_all_audio":  STAGE_COMBINE,
    "combine_audio":       None,    # done — stage cleared by caller
}

async def run_graph_with_stages(graph_obj, state, config, *, episode, deadline, poll_interval=5.0):
    merged: dict = {}
    async def _consume():
        async for update in graph_obj.astream(state, config=config, stream_mode="updates"):
            for node_name, node_out in update.items():
                if isinstance(node_out, dict): merged.update(node_out)
                next_stage = NODE_DONE_NEXT_STAGE.get(node_name)
                # audio node fires once PER dialogue line (Send fan-out) → write stage once
                if next_stage and episode.generation_stage != next_stage:
                    episode.generation_stage = next_stage
                    try: await episode.save()
                    except Exception as exc: logger.warning(f"stage update save failed: {exc}")
    task = asyncio.create_task(_consume())
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll_interval)
            if task in done: task.result(); break          # surface generation exception
            if time.monotonic() > deadline:
                task.cancel(); await asyncio.gather(task, return_exceptions=True)
                raise asyncio.TimeoutError()                 # stage-named by the caller
            if await _cancel_requested(episode.id):          # poll DB cancel flag every ~5s
                task.cancel(); await asyncio.gather(task, return_exceptions=True)
                raise CancelledByUser()
    finally:
        if not task.done(): task.cancel()
```

`get_resume_graph()` recompiles a sub-graph starting at the transcript node (reusing the
library's own node functions + conditional routing) so an approved/edited outline
resumes from exactly the right place. **Upgrade guard:** tests pin the node names so a
library rename fails loudly instead of stages silently going dark.

> ⚠️ **REVIEW:** this depends on `podcast_creator.nodes.*` internal symbols
> (`generate_transcript_node`, `route_audio_generation`, …) — private-ish API surface.
> The cancel mechanism polls a DB flag every 5s (up to 5s latency + a DB read per tick).
> A 20-min generation against a single `deadline` has no per-stage timeout *budget*,
> only a global one. `_cancel_requested` is fail-open (a flaky read can't abort) — good,
> but means a transient DB outage delays cancel.

### 2.4 `ObjectModel` base + `save` / `_prepare_save_data` (`open_notebook/domain/base.py`)

The persistence contract for all mutable records. Two subtle behaviors drive real bugs:

```python
class ObjectModel(BaseModel):
    id: Optional[str] = None
    table_name: ClassVar[str] = ""
    nullable_fields: ClassVar[set[str]] = set()  # fields allowed to persist as None

    def _prepare_save_data(self) -> dict[str, Any]:
        data = self.model_dump()
        return {                                  # ⚠️ None values are DROPPED unless
            key: value                            #    the field is declared nullable
            for key, value in data.items()
            if value is not None or key in self.__class__.nullable_fields
        }
```

This `None`-drop is *the* foot-gun. In v0.8.68, clearing `generation_stage` to `None` on
podcast completion was a **silent no-op** — finished episodes stuck on
`"combining_audio"` — until `generation_stage` was added to `nullable_fields`. Combined
with the **SCHEMAFULL** episode table silently discarding undefined fields (migration 22
fix), this is a recurring two-headed bug class: *a model field needs BOTH a `DEFINE
FIELD` migration AND (if it can go None) a `nullable_fields` entry*, or saves vanish.

`save()` also now writes timezone-aware UTC ISO timestamps (a v0.7.187 fix — naive
local-time stamps broke cross-machine sync ordering and DST), and v0.8.66 added an
`id` coercion validator so a raw `RecordID` round-trips into the `id: Optional[str]`
contract for *every* subclass (previously only `Source` defended this).

```python
@field_validator("id", mode="before")
@classmethod
def _coerce_id_to_str(cls, value):   # v0.8.66 (audit D-6)
    if value is None or value == "": return None
    return str(value)               # RecordID → str for all 8 models uniformly
```

`RecordModel` (singletons like `DefaultModels`, `ContentSettings`) is a different beast:
it overrides `__new__` to return a per-`record_id` singleton instance. `get_instance()`
on `DefaultModels` *intentionally* re-loads from DB each call to pick up live config.

> ⚠️ **REVIEW:** the `RecordModel.__new__` singleton-by-class-var means
> `clear_instance()` is mandatory in tests and cross-test state leakage is easy. The
> `None`-drop semantics are an implicit contract that's easy to violate; a unit test now
> pins model-field ↔ migration parity (`test_v0_8_68_episode_schema_parity.py`), but
> only for episodes. Consider a generic schema-parity test across all SCHEMAFULL tables.

### 2.5 The surreal-commands job pattern (`commands/*.py`)

Long-running work is submitted as DB-backed jobs decorated with `@command`. Convention:
**`ValueError` = permanent (not retried); everything else auto-retries** via
`stop_on=[ValueError]`. Podcasts/prompt-opt use `max_attempts: 1` to avoid duplicate
episode records.

```python
@command("optimize_prompt", app="open_notebook", retry={"max_attempts": 1})
async def optimize_prompt_command(input_data: OptimizePromptInput) -> OptimizePromptOutput:
    try:
        ...
        await _gate_offline([target_id, optimizer_id])       # fail fast if offline + cloud model
        result = await asyncio.wait_for(run_prompt_optimization(...), timeout=timeout)
    except ValueError:
        raise                                                # permanent — surreal-commands won't retry
    except Exception as exc:
        logger.exception(exc); raise RuntimeError(str(exc)) from exc   # retryable
```

**Critical submit-side rule:** `surreal_commands.submit_command` is **synchronous** and
must be wrapped in `asyncio.to_thread` when called from `async def` — otherwise it blocks
the event loop. The chat router's memory extraction does this correctly:

```python
# api/routers/chat.py — fire-and-forget memory extraction
from surreal_commands import submit_command
await asyncio.to_thread(submit_command, "extract_memory", ...)   # sync submit off the loop
```

Two `@command`-module gotchas the changelog records as *live-caught 500s*:
- **No `from __future__ import annotations`** in a command module — it turns the
  handler's type hints into strings that LangChain's RunnableLambda input schema can't
  resolve ("...input is not fully defined"). A regression test now force-resolves every
  registered command's input schema.
- `generate_podcast` resolves **all** episode/speaker profiles before invoking
  podcast-creator (the library validates the whole config), dropping *unrelated*
  profiles that fail resolution, then fail-fasts if the *selected* profile didn't
  survive.

> ⚠️ **REVIEW:** "ValueError = don't retry" is a string-of-convention that's invisible
> at the raise site — a contributor raising `ValueError` for a transient condition would
> silently disable retries. The profile-resolution sweep is O(all profiles) on every
> podcast submit even though only two are used; bounded `LIMIT 1000` with a warning, but
> still loads every profile row.

### 2.6 SkillOpt integration (`open_notebook/prompt_optimizer/`)

Bridges ONP's model registry to SkillOpt's backend config: both the *target* (runs the
prompt) and *optimizer* (judges + proposes edits) are configured as **openai-compatible
endpoints**, which covers the local llama.cpp sidecar AND cloud OpenAI/Azure-style
providers — so the whole loop can run on-device. The runner (`runner.py`) does heavy
defensive work against the immature `skillopt 0.1.0` wheel:

```python
def ensure_skillopt_prompts(dest_dir=None) -> int:
    """The skillopt 0.1.0 wheel ships the prompts PACKAGE but NOT its *.md template
    files → load_prompt('analyst_success') raises FileNotFoundError mid-training.
    Backfill vendored upstream files (MIT) for any MISSING name; never overwrite, so a
    fixed upstream wheel automatically wins."""
    for src in sorted(_VENDORED_PROMPTS.glob("*.md")):
        dest = dest_dir / src.name
        if dest.exists(): continue
        dest.write_text(src.read_text())   # raises PromptOptimizerError on read-only site-packages
```

```python
def build_flat_config(...):
    cfg = load_config(str(_BASE_YAML)); flat = flatten_config(cfg)
    def _set(key, value):
        if key in flat: flat[key] = value; return
        dotted = [k for k in flat if k.endswith("." + key)]   # tolerate dotted variants
        if dotted: flat[dotted[0]] = value; return
        raise PromptOptimizerError(f"SkillOpt config key {key!r} not found — layout changed")
    _set("target_backend", "openai_chat"); _set("optimizer_backend", "openai_chat")
    _set("target_azure_openai_auth_mode", "openai_compatible")   # local llama.cpp via OpenAI shim
    ...
```

The blocking trainer runs on a worker thread (`await asyncio.to_thread(_train)`); the
command owns the timeout (`ONP_PROMPT_OPT_TIMEOUT_SEC`, default 30 min). Artifacts
(`best_skill.md`, `history.json`) are collected via rglob fallback.

> ⚠️ **REVIEW:** this integration carries a lot of *vendored-workaround debt* against a
> 0.1.0 dependency — missing prompt templates backfilled at runtime, a config-key
> shim, a `get_train_size()` override, and a `scripts/__init__.py` added because the
> wheel installs a top-level `scripts` package that shadows the repo's. Each is pinned
> by an upgrade-guard test, but the surface area is large; a fork or upstream PR may be
> cheaper long-term than maintaining the backfill.

### 2.7 Evidence Studio Course Pack generation (`api/routers/studio.py`, `open_notebook/studio/artifact_generation.py`)

Evidence Studio is the project-facing artifact workbench. It persists generated
outputs as `StudioArtifact` records and long-running work as `StudioWorkflowRun`
records, so reports and Course Packs can be revised instead of being throwaway LLM
text. The old `training_guide` enum remains as a compatibility alias, but the UI label
and prompt intent are **Course Pack**:

```python
def _artifact_type_label(artifact_type: str) -> str:
    if artifact_type in {"course_pack", "training_guide"}:
        return "Course Pack"
    return artifact_type.replace("_", " ").title()
```

The Course Pack prompt is deliberately more specific than a summary prompt. It tells
the model how to treat different source types and asks for instructor/learner assets:

```python
"course_pack": (
    "Create an instructor-ready Course Pack in markdown from the provided "
    "linked and uploaded source content. Include audience, learning outcomes, "
    "prerequisite knowledge, source readiness notes, a module roadmap, timed "
    "lesson blocks, hands-on exercises, facilitator notes, learner handouts, "
    "knowledge checks, a final assessment, source citations, and follow-up "
    "resources. Treat video and audio sources as lesson segments, PDFs and "
    "documents as readings or reference modules, and links as external "
    "resources or source-backed exercises. Warn when transcript/source text "
    "appears thin. Ground every substantive lesson point in citation markers."
)
```

Source readiness is checked before generation. This matters for video/audio because
thin or missing transcripts would otherwise create confident-looking but low-value
training output:

```python
def _sources_not_ready_exception(not_ready_sources):
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "sources_not_ready",
            "message": "One or more selected sources are still processing. ...",
            "not_ready_sources": not_ready_sources,
        },
    )
```

Auto-routing is local-model aware: if the artifact has no explicit `model_id`, the
service enumerates the configured model directory, recommends a role like
`source_synthesis`, and matches that recommendation to a registered model. On this
machine that directory is expected to be `~/Desktop/AI_Models`, with `GGUF/` for
llama.cpp and `MLX/` for Apple-Silicon repositories.

> ⚠️ **REVIEW:** Course Pack quality now depends on prompt shape, source-readiness
> checks, and local-model role routing. The next product leap is probably a structured
> intermediate plan (`modules[]`, `assessments[]`, `citations[]`) before markdown
> rendering, so the UI can edit modules, regenerate one lesson, and export SCORM/xAPI
> style packages later.

---

## 3. Data Flow & Dependencies

### 3.1 Chat request, end-to-end

```
Frontend (useChat / useSourceChat)
  └─ POST /chat/stream  (ExecuteChatRequest: message, session_id, model_override,
                         disabled_mcp_servers, bypass_privacy_gate)
       └─ api/routers/chat.py :: stream_chat → StreamingResponse(_stream_chat_events)
            ├─ asyncio.to_thread(graph.get_state, ...)        # read prior checkpoint (sync saver)
            ├─ _chat_graph_async = await get_async_graph()    # AsyncSqliteSaver twin
            └─ async for event in _chat_graph_async.astream_events(state, config):
                 ├─ if await fastapi_request.is_disconnected(): break   # SSE disconnect guard
                 └─ node call_model_with_messages:
                      ├─ recall_memory() → system prompt (mem0-style fact/pref recall)
                      ├─ _trim_message_history()  (ONP_CHAT_HISTORY_CHAR_CAP)
                      ├─ provision_langchain_chat_model()
                      │    ├─ smart router pick_provider(local health, n_ctx, headroom)
                      │    ├─ privacy gate (scan outbound for PII → maybe reroute local)
                      │    └─ provision_langchain_model() → offline gate → Esperanto .to_langchain()
                      ├─ bind_mcp_and_run_tool_loop()
                      │    ├─ _resolve_chat_tools() (TTL-cached MCP discovery + web_search + opencode)
                      │    ├─ model.ainvoke() [wait_for timeout]  → tool_calls?
                      │    └─ execute tools (per-tool timeout) → FENCE untrusted → re-invoke (≤ max_iters)
                      └─ mid-turn NetworkError? → flip OFFLINE, retry once on local
            (stream emits tokens + done-event: selected_provider, offline_fallback,
             privacy_gated, mcp_tool_calls)
       └─ after stream: asyncio.to_thread(submit_command, "extract_memory", ...)  # fire-and-forget
```

The SSE generator checks `fastapi_request.is_disconnected()` each event (the codebase's
documented disconnect-handling pattern), and history is persisted by the checkpointer.

### 3.2 Podcast generation request, end-to-end

```
POST /podcasts/episodes (generate)  → podcast_service
  ├─ submit-time guards: offline+cloud TTS/LLM → reject; content-token budget
  │   (ONP_PODCAST_MAX_CONTENT_TOKENS default 100k) → reject with count
  └─ asyncio.to_thread(submit_command, "generate_podcast", PodcastGenerationInput)
       └─ surreal-commands worker → generate_podcast_command (max_attempts: 1)
            ├─ load EpisodeProfile + SpeakerProfile by name from SurrealDB
            ├─ _load_and_configure_all_profiles(): resolve EVERY profile's model refs
            │    → _resolve_model_config(model_id) → provider/model/credential config
            │    → podcast_creator.configure("episode_config"/"speakers_config", ...)
            ├─ build_state_and_config() (briefing, num_segments, language, speaker_profile)
            └─ run_graph_with_stages(podcast_graph OR resume_graph):
                 outline → (review? stop at awaiting_review) → transcript → audio → combine
                 • writes episode.generation_stage as nodes finish
                 • polls episode.cancel_requested every 5s
                 • global deadline → TimeoutError names the hung stage
       (episode row carries generation_stage, briefing_suffix, cancel_requested;
        endpoints: /cancel, /outline (PUT), /approve-outline (POST), /retry)
Frontend polls /commands/{id} for job status + episode.generation_stage for stage UI.
```

### 3.3 External services & dependencies

- **Esperanto** — provider abstraction. `AIFactory.create_language/embedding/speech_*`.
  Model instances cached by Esperanto, not by ONP's stateless `ModelManager`.
- **Credentials** — per-provider encrypted `Credential` records (Fernet via
  `OPEN_NOTEBOOK_ENCRYPTION_KEY`, `SecretStr` masking). `to_esperanto_config()` is
  preferred; env-var injection (`key_provider.py`) is the fallback path.
- **podcast-creator** — its compiled LangGraph + node functions are imported directly.
- **MCP** — registry of enabled servers; tools discovered per-server (TTL-cached) and
  wrapped as `mcp_<name>` StructuredTools. Multi-server binding with name-collision
  dedup (first/higher-priority wins).
- **SurrealDB** — graph DB; auto-migrations on API startup (`AsyncMigrationManager`).
- **Sidecars** (desktop) — llama.cpp (registers as `openai_compatible`), Ollama,
  faster-whisper STT, local TTS, memory dashboard. Ports auto-registered into env.

### 3.4 Database schema highlights

**Edge tables (graph relations).** Direction matters and is easy to invert:

```surql
DEFINE TABLE reference TYPE RELATION FROM source TO notebook;   -- in=source, out=notebook
DEFINE TABLE artifact  TYPE RELATION FROM note   TO notebook;   -- in=note,   out=notebook
-- refers_to (chat session → notebook) used by chat.py:
--   SELECT out FROM refers_to WHERE in = $session_id   → notebook_id
```

A real query in `chat.py` resolves the notebook from the session via this edge —
inverting `in`/`out` silently returns nothing. `ChatSession.delete()` had to be patched
(v0.8.68) to sweep its `refers_to` edge first, mirroring the Source/Note cascade — a
**missing-delete-cascade** bug class. Source deletion is handled DB-side by an event:

```surql
DEFINE EVENT source_delete ON TABLE source WHEN ($after == NONE) THEN {
    delete source_embedding where source == $before.id;
    delete source_insight   where source == $before.id;
};
```

**Embeddings + vector search.** 768-dim (nomic-embed-text-v1.5) HNSW indexes (migration
21) turned vector search from brute-force scans into KNN:

```surql
DEFINE INDEX source_embedding_hnsw ON source_embedding FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX source_insight_hnsw   ON source_insight   FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX note_hnsw             ON note             FIELDS embedding HNSW DIMENSION 768;
-- fn::vector_search now uses: WHERE embedding <|100|> $query AND ...cosine >= $min_similarity
```

**Full-text** uses a snowball/lowercase analyzer with BM25 indexes; `fn::text_search`
unions title/full_text/insight/note BM25 scores. **SCHEMAFULL** tables (source, note,
notebook, episode, …) silently drop undefined fields — every new model field needs a
`DEFINE FIELD` migration.

> ⚠️ **REVIEW:** `fn::vector_search`'s `<|100|>` KNN operator is hard-coded to K=100
> regardless of the caller's `match_count`; the HNSW DIMENSION 768 is hard-coded to one
> embedding model — switching embedders silently breaks search (array-length guard
> rejects mismatched dims rather than erroring loudly). Edge-direction and
> delete-cascade correctness are entirely convention-enforced, not type-checked.

---

## 4. Current Pain Points / Known Limitations

Mined from `desktop/CHANGELOG.md` and the root `CLAUDE.md` "recurring patterns this
codebase has been bitten by" list. These are **real, specific** issues — many are fixed
but reveal fragile design, and several remain latent.

### Recurring bug classes (the codebase's own "bitten-by" list)
1. **Sync `submit_command` in `async def`** — must wrap in `asyncio.to_thread` or it
   blocks the event loop. Enforced by convention only; every new call site is a risk.
2. **LangGraph state-shape variance** — node output is sometimes a `dict`, sometimes a
   Pydantic object; code must accept both via `getattr` fallback / `isinstance` checks.
3. **SSE handlers missing `is_disconnected()`** — a client that closes the tab leaves a
   stream running; the disconnect check must be in every event loop.
4. **Readers released without `cancel()` first** — resource leak pattern.
5. **Edge-table direction inversion** (`reference`/`artifact`/`refers_to`) — `in`/`out`
   silently return nothing when swapped.
6. **Missing delete cascades** — dangling edges (ChatSession `refers_to` was the latest;
   only a full-notebook delete swept it).
7. **SCHEMAFULL field drops** — model fields without a `DEFINE FIELD` migration vanish on
   save (the staged-podcast fields were dead against a real DB; unit tests mock it so
   only the live smoke test caught it).
8. **`_prepare_save_data` drops `None`** unless the field is in `nullable_fields` — the
   stage-clear-on-completion was a no-op (episodes stuck on "combining_audio").
9. **`str(payload)` over-counting** when sizing LLM context — wrapper-repr noise inflated
   token counts and triggered premature large-context routing.

### Provisioning / routing fragility
- **300s hangs offline** (the entire motivation for v0.8.68's offline gate): a cloud call
  against an unreachable provider blocked the turn to the provider timeout. Fixed, but
  the fix added 4 interacting decision layers (offline gate, privacy gate, smart router,
  mid-turn retry) with overlapping responsibilities and **multiple independent
  `get_defaults()` DB reads per turn**.
- **n_ctx / context-window mismatches** — the router's assumed local n_ctx must match the
  launcher's actual `ONP_CHAT_LLM_CTX`; mismatch → llama.cpp HTTP 400
  `context_length_exceeded`. RAM-aware n_ctx defaults + reply-headroom reservation patch
  the symptoms; the root coupling (router guesses what the sidecar was launched with via
  env vars) remains.
- **Captive portals** — the TCP-:443 probe can't see HTTP interception; only passive
  call-failure flips correct it, so the *first* call after entering a captive portal
  pays a failure before the retry leg kicks in.

### Performance bottlenecks
- **Per-turn DB chatter** — memory recall, notebook-id edge query, `get_defaults()` (×N
  across routing layers), MCP registry lookup, local-health probe. TTL caches paper over
  most, but a cold turn is DB-heavy.
- **Blocking sync calls on the event loop** — the recurring `asyncio.to_thread` fixes
  (httpx local-health probe = 9s; content extraction is sync and "may block API
  briefly"; tiktoken catastrophic backtracking on long no-space strings, fixed in
  v0.8.67u after slowing tests 16×) show the async boundary is leaky.
- **`ObjectModel.get_all()` unbounded** historically loaded entire tables (every note
  with content) into one JSON response — now optionally paginated, but old callers keep
  unbounded semantics.
- **Podcast profile resolution** is O(all profiles) per submit.
- **`fn::vector_search` K=100 fixed** regardless of requested result count.

### Desktop / launcher debt (from the Plus changelog)
- **DB live-query corruption** after unclean shutdown (SIGKILL/force-quit/power-loss) →
  "The key being inserted already exists" → source processing bricked. Self-healing
  auto-repair (backup→export→reimport) now runs, but it's a *recovery* mechanism for a
  corruption that still happens.
- **Launch race** — pywebview navigates once; a probe of a just-bound socket could open
  the window onto Next.js's not-found page (which serves status 200 for valid routes
  while manifests lazy-load). Patched with a 3-success gate + python handoff controller +
  load-retry watchdog — a lot of machinery for a startup ordering problem.
- **Near-full disk** — episode UUID output dirs left behind on delete/retry slowly fill
  the disk (now cleaned up); auto-export retention prunes to newest 7.
- **TCC/codesign churn** — ad-hoc signing gives a new identity each rebuild → macOS
  resets Files-&-Folders grants → iCloud/Desktop scandir boot-wedge. Opt-in stable
  self-signed identity.
- **STT model mismatch** — pre-downloaded whisper.cpp `ggml` while the shim used
  faster-whisper (CTranslate2), so it silently re-downloaded from HF on first use.

### Maturity / dependency debt
- **skillopt 0.1.0** — missing prompt templates, config-key drift, `scripts` package
  shadowing, `get_train_size()` quirk — all worked around with vendored backfills + pins.
- **Auth is dev-only** — "Simple password middleware (insecure, dev-only)"; production
  needs OAuth/JWT. No built-in rate limiting (add at proxy).
- **No timeouts on some long workflows** (CLAUDE.md: "Chat/podcast workflows may take
  minutes; no timeout") — partially addressed by the per-call timeouts above.

---

## 5. Design Decisions & Trade-offs

- **Three-tier (Next.js / FastAPI / SurrealDB).** Clean separation; the API is reusable
  by both the desktop window and a server deployment. **Trade-off:** three processes to
  orchestrate, health-gate, and version together; "must start API before UI";
  cross-process failure modes (the launch race, DB-must-be-up).

- **Esperanto as the provider abstraction.** One interface for 8+ providers → adding a
  provider is config, not code; local sidecars masquerade as `openai_compatible`/`ollama`
  so the *same* code path runs local and cloud. **Trade-off:** ONP is blind to
  provider-specific features; token counting is an estimate (cl100k_base, ±5-10%);
  Esperanto owns instance caching, so ONP can't easily control it.

- **surreal-commands for async jobs.** Reuses SurrealDB as the queue (no Redis/Celery);
  durable, pollable, retry built-in. Fits the "one local DB, no extra infra" desktop
  story. **Trade-off:** sync `submit_command` forces `to_thread` discipline;
  `@command`-module annotation constraints (no `from __future__`); polling-based status.

- **Local-first / privacy-first.** Offline gate, privacy gate, local sidecars, on-device
  prompt-optimizer and podcasts, encrypted credentials. The product *differentiator* vs
  NotebookLM. **Trade-off:** enormous surface area — network probing, captive-portal
  handling, RAM-aware model sizing, sidecar lifecycle, model substitution — all of which
  is the bulk of the Plus-specific bug log.

- **PyInstaller + pywebview desktop.** Ships a native `.app`/`.exe` with bundled Python +
  sidecars; pywebview gives a real OS window over the Next.js UI. **Trade-off:** brittle
  packaging (runtime fetch, codesign/TCC, splash/handoff race, singleton lock, DB repair)
  — most launcher changelog entries are packaging/lifecycle fixes, not features.

- **Offline/online switching design.** A single network-state singleton with TTL +
  single-flight + passive flips; "unknown ⇒ online" so a flaky probe never blocks cloud;
  the gate fail-opens on every internal error and only raises the actionable
  offline-no-local case. The gate sits in the *one funnel* (`provision_langchain_model`)
  every workflow uses, so coverage is uniform. **Trade-off:** correctness depends on real
  call-failure classification (`classify_error` → `NetworkError`) being accurate; the
  decision is spread across 4 layers; two TTLs cache the forced-offline toggle.

- **Two SQLite checkpointers over one file (chat).** Necessary because LangGraph ≥0.6
  split sync/async savers and existing callers use the sync read path. **Trade-off:** WAL
  consistency between two savers; lazy async-graph init with a `threading.Lock` guarding
  `await`; explicit shutdown FD cleanup.

- **Stream podcast-creator's graph instead of forking it.** Gets progress/cancel/review
  for free off the library's exported graph. **Trade-off:** depends on the library's
  internal node names + node functions (pinned by tests, but private API).

---

## Areas for Review

Concrete questions for an AI reviewer, each tied to real files:

1. **Model-selection sprawl** (`ai/provision.py`, `ai/offline_gate.py`, `ai/router.py`,
   `ai/privacy_gate.py`): four layers each call `model_manager.get_defaults()`
   independently and decide which model runs. Should this collapse into one resolved
   `ModelDecision` computed once per turn? What's the correct precedence among smart
   router / privacy gate / offline gate / mid-turn retry, and is it currently
   well-defined or emergent?

2. **Captive-portal detection** (`health/network.py`): a 2s TCP connect to `:443` can't
   detect HTTP interception. Is the passive-failure-flip sufficient, or should the probe
   do a lightweight HTTP GET with a known-body check? Are the *two* TTLs (20s state, 30s
   forced-offline) a staleness hazard for the Offline-mode toggle?

3. **SCHEMAFULL + `nullable_fields` + migration parity** (`domain/base.py`,
   `migrations/22.surrealql`): the two-headed "field dropped" bug class only fully
   surfaces against a live DB (unit tests mock it). Should there be a *generic*
   model-field ↔ `DEFINE FIELD` ↔ `nullable_fields` parity test across all SCHEMAFULL
   tables, not just episodes?

4. **Edge-direction & delete-cascade safety** (`graphs/chat.py` `refers_to` query;
   `domain/notebook.py` cascades): direction and cascade completeness are
   convention-only. Could a typed edge-query helper or a DB-side cascade event (like
   `source_delete`) eliminate the recurring dangling-edge bugs?

5. **Event-loop blocking** (`ai/provision.py` health probe, content extraction,
   `submit_command`): the codebase repeatedly discovers a sync call blocking the loop and
   wraps it in `to_thread`. Is there a systematic way to find the remaining ones (an
   async-lint, a blocking-call detector in tests)?

6. **MCP JSON-Schema→Pydantic converter** (`graphs/chat.py`
   `_json_schema_to_pydantic_model`): hand-rolled, covers common shapes only
   (`$ref`/`oneOf`/`allOf`/nested objects fall to `Any`). Real-world MCP servers with
   rich schemas will degrade silently to loose typing — replace with a maintained
   converter?

7. **Prompt-injection fence robustness** (`graphs/chat.py`
   `_fence_untrusted_tool_output`): a text-delimiter fence around attacker-influenceable
   tool output. How strong is this against a model that's been told to ignore delimiters?
   Should fenced tool output also be excluded from the fire-and-forget memory extractor's
   input entirely, not just fenced?

8. **Podcast-creator private-API coupling** (`commands/podcast_staged.py`): depends on
   `podcast_creator.nodes.*` and exported graph internals, pinned by name-tests. Is the
   resume-graph reconstruction (re-wiring the library's node functions) maintainable, or
   should ONP request a public staged API upstream?

9. **skillopt 0.1.0 workaround debt** (`prompt_optimizer/runner.py`): runtime template
   backfill, config-key shim, `scripts/__init__.py` shadow-fix, `get_train_size`
   override. At what point does forking/upstreaming beat maintaining the backfills?

10. **Auth & rate limiting**: dev-only password middleware, no rate limiting, CORS allow-all
    in dev (`api/main.py`). For a desktop app this is partly mitigated by being
    loopback-only — but what's the exposure if a user binds the API to a LAN interface?

11. **Per-turn DB chatter & cold-turn latency**: memory recall + notebook-id edge query +
    N× `get_defaults()` + MCP registry + local-health probe per chat turn. TTL caches
    help warm turns; can the cold path be batched into fewer round-trips?

12. **DB live-query corruption recovery** (`desktop/db_repair.py`): the self-healing
    backup→reimport is a *recovery* for a corruption that still recurs after unclean
    shutdown. Is there a SurrealDB-config or shutdown-handling change that prevents the
    live-query state corruption at the source rather than repairing it after?

13. **Course Pack structure and export path** (`studio/artifact_generation.py`,
    `frontend/src/components/onp/ArtifactRail.tsx`): generation now produces rich
    markdown, but there is no structured module graph yet. Should Course Packs move to
    a typed intermediate schema so users can edit/reorder modules, regenerate individual
    lessons, and eventually export SCORM/xAPI/LMS packages?
