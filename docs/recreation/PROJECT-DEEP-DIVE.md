# Deeper Notebook — Technical Deep-Dive

> **Current identity note:** this packet is maintained for the Deeper Notebook
> checkout. Historical `Open Notebook Plus` names remain in code examples and
> migration notes where they are part of the compatibility contract.
>
> Repo: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook` (branch
> `main`). Fork of `lfnovo/open-notebook`. Verify exact version values from
> `desktop/__init__.py` and `pyproject.toml` before releasing because the two
> tracks are intentionally separate.

---

## 1. Project Overview

**Purpose.** Open Notebook Plus is a **local-first, privacy-focused desktop research assistant** — a self-hosted NotebookLM alternative. A user uploads multi-modal sources (PDFs, audio, video, web pages, pasted text), the app extracts + embeds them, generates AI insights/summaries, lets the user chat with their corpus (source-grounded, with citations), and produces studio artifacts and podcasts. The differentiating value versus upstream is that the Plus fork ships as a **native macOS/Windows desktop app** that supervises its own stack of sidecar processes and can run **fully offline** against local LLMs (llama.cpp GGUF, MLX, Ollama) with **opt-in cloud egress gated by key presence**.

**Tech stack (three-tier + desktop shell).**
- **Frontend:** Next.js 16 / React 19 / TypeScript; Zustand (client state) + TanStack Query v5 (server cache); Tailwind CSS v4 + Radix/shadcn-ui; i18next. Streaming chat over NDJSON via native `fetch` + `ReadableStream`.
- **API / backend:** FastAPI (`>=0.136.3`) + uvicorn, Python 3.11–3.12; LangGraph `>=1.0.10` state machines; Pydantic v2; Loguru. Business logic lives mostly in `api/routers/*` working directly against `open_notebook.domain.*` (the older per-resource `*_service.py` indirection was deleted in v0.7.21; only `chat_service`, `podcast_service`, `command_service`, `credentials_service` survive).
- **AI abstraction:** the **Esperanto** library (`>=2.20.0,<3`) unifies 8+ providers (OpenAI, Anthropic, Google, Groq, Ollama, Mistral, DeepSeek, xAI) behind one interface; LangChain provider packages back it.
- **Database:** **SurrealDB** (`>=1.0.4`) — a graph DB storing records + edges + vector embeddings, with a SurrealQL `fn::vector_search` for semantic retrieval. Schema migrations (`open_notebook/database/migrations/*.surrealql`) auto-run on API lifespan startup.
- **Async jobs:** **surreal-commands** (`>=1.3.1,<2`) — a SurrealDB-backed job queue; a separate worker process consumes commands (source ingest, embedding, transformations, podcasts).
- **Desktop packaging:** pywebview 5.4 (WKWebView on macOS) + PyInstaller (onedir `.app`/`.exe`), wrapped into a `.dmg`.

**High-level architecture.** In desktop mode, `desktop/launcher.py`'s `Supervisor` boots a full private stack on dynamic ports: SurrealDB → FastAPI (uvicorn) → surreal-commands worker → Next.js standalone server → optional local sidecars (llama.cpp chat + embed servers, faster-whisper STT, piper TTS, mem0 memory retriever, OpenChronicle bridge). Once the frontend returns healthy HTTP, `desktop/window.py` navigates the WKWebView to it. All of this is native — **never Docker** for the desktop app (Docker is the separate server/self-host track).

---

## 2. Key Code Walkthrough

### 2.1 Source ingest pipeline (`open_notebook/graphs/source.py` + `commands/source_commands.py`)

Ingest is a three-node LangGraph — `content_process → save_source → (fan-out) transform_content` — driven asynchronously by the `process_source` command so the HTTP request returns immediately.

`content_process` loads the **persisted** `ContentSettings` singleton (a real fix: it previously hardcoded literals, silently ignoring the user's Settings-page choices), then extracts via content-core, with a crawl4ai path and sentinel-failure detection:

```python
# open_notebook/graphs/source.py — content_process (excerpt)
content_settings = await ContentSettings.get_instance()   # v0.7.209 — honour user prefs
...
if content_state.get("url_engine") == "crawl4ai" and url:
    content = await extract_url_with_crawl4ai(url)         # v0.8.67u local scraper
...
if processed_state.title == "Error" and (processed_state.content or "").startswith(
    "Failed to extract content:"
):
    raise ValueError(...)   # content-core signals soft failure by SENTINEL, not exception →
                            # raise so the job is marked failed + source becomes retryable
```

`save_source` writes `full_text`, extraction provenance, preserves a user-set title, and fire-and-forget vectorizes. The **auto-summary / key-topics ingest hook** lives in the command wrapper — opt-in via `ContentSettings`, best-effort, never fatal:

```python
# commands/source_commands.py — process_source_command (excerpt)
if getattr(content_settings, "auto_summarize_on_ingest", False):
    summarize = await get_or_create_summarize_transformation()   # lazy get-or-create
    if not any(str(t.id) == str(summarize.id) for t in transformations):
        transformations.append(summarize)     # appended into the SAME transform fan-out
if getattr(content_settings, "auto_extract_topics_on_ingest", False):
    key_topics = await get_or_create_key_topics_transformation()
    ...  # after graph runs, parse the Key-Topics insight → processed_source.topics = topics
```

The command uses a **blocklist retry** (`stop_on=[ValueError, ConfigurationError]`, `max_attempts=15`, exponential jitter) so transient SurrealDB v2 transaction conflicts auto-retry but validation errors fail permanently — and on permanent failure it **cleans up the orphaned `"Processing..."` placeholder row** the API created up-front (only when title unchanged AND `full_text` empty, so a partially-processed source is never destroyed).

### 2.2 Chat: buildContext → graph → SSE

The chat context is assembled on the **frontend** from per-item inclusion levels, then sent to the backend. The type is a small union (`frontend/src/lib/types/notebook-context.ts`): `ContextMode = 'off' | 'insights' | 'full'` for sources, `'off' | 'full'` for notes. `useNotebookChat.ts` maps these to backend strings (`insights` / `full content` / `not in`) and streams the turn:

```typescript
// useNotebookChat.ts — streaming loop (excerpt)
for await (const event of chatApi.streamMessage({ session_id, message, context: built.context, ... },
                                                controller.signal)) {   // AbortController per send
  if (!mountedRef.current) break
  if (event.type === 'token') { tokenBuffer += event.content; scheduleFlush() }  // rAF-batched
  else if (event.type === 'done') { canonicalMessages = event.messages }
  else if (event.type === 'error') { streamError = event.detail; break }
}
```

`chat.ts` reads the NDJSON stream and — critically — **cancels before releasing the lock** (`await reader.cancel().catch(()=>{}); reader.releaseLock()`), the exact SSE-cleanup pattern the repo's audit rules mandate.

The backend chat graph (`open_notebook/graphs/chat.py`, ~1200 lines) is deliberately a **single-node `StateGraph`** with a SurrealDB-independent SQLite checkpointer for message history:

```python
# open_notebook/graphs/chat.py
agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_edge(START, "agent"); agent_state.add_edge("agent", END)
graph = agent_state.compile(checkpointer=memory)   # sync SqliteSaver (WAL-tuned shared conn)
# get_async_graph() lazily compiles a second graph with AsyncSqliteSaver for astream_events
```

`call_model_with_messages` is a native `async` node (v0.7.37 removed the fragile per-call `new_event_loop()` bridge). It recalls mem0 facts, renders the `chat/system` Jinja prompt, **trims history** to fit a small local context window, then sizes the payload against message *text* only (not `str(payload)` repr noise — a real overcount bug) before provisioning a model.

### 2.3 Smart model routing + privacy/offline gates (`open_notebook/ai/provision.py`, `router.py`, `privacy_gate.py`, `offline_gate.py`)

`provision_langchain_model()` is the funnel every graph uses. `pick_provider()` prefers the **local** llama.cpp chat sidecar when it is healthy and the context fits `OPEN_NOTEBOOK_LOCAL_N_CTX`, else routes to cloud. Health is TTL-cached (30 s) with a single-flight lock so N concurrent turns don't each pay a ~9 s probe. Two gates wrap this:
- **`offline_gate`** (v0.8.68): if the machine is offline (or Offline-mode toggled) and the candidate provider is cloud, substitute the best local model; fail-open on internal errors so the gate never breaks a turn.
- **`privacy_gate`** (Phase 5.2a): a fast structured-secret detector (API keys, SSN, cards, `secret=` assignments). If cloud was chosen and a secret is detected, **fail closed** — reroute local, or block with an actionable error rather than leak.

This is the concrete realization of "local-first, opt-in egress."

### 2.4 The desktop launcher supervising sidecars (`desktop/launcher.py`)

`Supervisor.start_all()` allocates 9 free ports, builds a shared `session_env`, then boots services in dependency order with **fail-fast readiness gates**. `_wait_tcp` / `_wait_http` take the child `Popen` and poll `proc.poll()` so a crashed child (bad binary, port collision) raises in ~100 ms instead of waiting the full (env-tunable) timeout:

```python
_wait_http(f"http://127.0.0.1:{api_port}/readyz",              # /readyz, not /health:
           timeout=_startup_timeout("ONP_API_READY_TIMEOUT", 300.0),  # only 200 after migrations
           proc=self._procs[-1])
```

Each child is spawned into its **own process group** (`start_new_session=True`) so `stop_all` can `os.killpg(pgid, SIGTERM)` the whole subtree (Next.js `next-server` grandchildren used to reparent to PID 1 and leak). A **singleton PID-lock + orphan reaper** prevents double-launch zombie stacks. Non-debug stderr is drained to a rolling 50-line `.tail` per sidecar so the API's `/healthz/sidecars/{kind}/log` can surface a crash cause; secrets are regex-redacted from all drained output.

### 2.5 The js_api relaunch bridge (`desktop/window.py`) + control plane (`desktop/launcher_control.py`)

pywebview exposes an `_OnpJsApi` object to the WKWebView; `window.pywebview.api.relaunch()` lets the UI restart the whole app after a config change (e.g. changing the model dir) that needs a full teardown:

```python
# desktop/window.py — _OnpJsApi.relaunch()
app_bundle = next((p for p in Path(sys.executable).parents if p.suffix == ".app"), None)
sh = (f"/bin/sleep 1; /bin/kill {pid} 2>/dev/null; "
      f"n=0; while /bin/kill -0 {pid} 2>/dev/null && [ $n -lt 20 ]; do /bin/sleep 0.3; n=$((n+1)); done; "
      f"/bin/kill -9 {pid} 2>/dev/null; /bin/sleep 0.5; "
      f'/usr/bin/open "{app_bundle}"')
subprocess.Popen(["/bin/sh", "-c", sh], start_new_session=True)   # detached: SIGTERM→SIGKILL→reopen
```

For **in-place** sidecar restarts (no full relaunch), the launcher runs a `ControlServer` — a stdlib `ThreadingHTTPServer` bound to `127.0.0.1:<random>` with a 32-byte bearer token (constant-time compared). Its URL + token are exported into the API subprocess env (`OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL/TOKEN`); the API POSTs `/restart_sidecar` or `/hot_swap_chat` to hot-swap a GGUF without quitting.

### 2.6 Citation locate_passage (`open_notebook/utils/citation_offsets.py`)

ONP citations are bare record IDs (`[source:ID]`) with no offsets. Rather than change the citation format (frontend parser + tests depend on it), the passage is located **on demand**: the frontend sends the sentence preceding a clicked citation as a query; a deterministic token-containment sliding-window matcher over the source's `full_text` returns `{start, end, score, snippet}` (stopword-filtered, embedding-free, unit-testable) so the viewer can scroll-and-highlight, returning `None` when there's no decent match.

### 2.7 Persistent WKWebView store (`desktop/window.py`)

```python
webview.start(private_mode=False, storage_path=str(data_home / "webview_data"))
```

pywebview defaults to an **ephemeral** `WKWebsiteDataStore` wiped on close, which broke the `wizard_completed` cookie (Setup Wizard re-fired every launch). Persisting to a stable path under `~/.open-notebook-plus`, combined with a **stable self-signed code-signing identity** (so the macOS data container survives rebuilds), makes the wizard/intro show exactly once.

### 2.8 Local Video Overview (`api/routers/video_overviews.py`)

Video Overview deliberately reuses two reviewed artifacts instead of asking a
model to invent a new audiovisual explanation: a completed typed `slide_deck`
and a completed podcast episode with persisted timestamped transcript segments.
The route accepts record IDs, renders the same deterministic slide images used
by the slide export, and calls the local FFmpeg composer in a worker thread.

```python
# api/routers/video_overviews.py — composition core (excerpt)
output = await asyncio.to_thread(
    compose_local_video_overview,
    VideoOverviewDocument(
        slide_image_paths=slides,            # renderer-owned PNGs, not client paths
        narration_audio_path=audio_path,     # resolved inside podcast output root
        narration_segments=narration_segments,
        caption_language=payload.caption_language,
    ),
    artifact_dir,                             # {DATA_FOLDER}/video-overviews/<artifact>/
)
artifact.export_paths = {
    **artifact.export_paths,
    "video_mp4": str(output.mp4_path),
    "video_captions": str(output.vtt_path),
}
await artifact.save()                         # UI refetches the owning slide deck
```

The composer writes to a temporary directory, runs a decode validation pass,
then promotes the MP4 and VTT atomically. Streaming routes reject any stored
path outside the Video Overview root. The trade-off is intentional: this is a
local composition capability, not a general arbitrary-file video editor; it
requires an Audio Overview with timestamps and does not synthesize narration.

---

## 3. Data Flow & Dependencies

**Add source → insights.** UI POSTs `/sources` → API creates a placeholder source row (`title="Processing..."`) and immediately RELATEs it to the notebook(s) for UI responsiveness, then submits `process_source` to surreal-commands (the sync `submit_command` is wrapped in `asyncio.to_thread` per the repo's async-safety rule). The worker runs `source_graph`: **content-core extract → save `full_text` + provenance → fire-and-forget `source.vectorize()` (chunk → batch-embed 50/turn → `source_embedding` rows) → fan-out transformations (each an LLM call → `source_insight` row, also embedded)**. Auto-summary/key-topics are appended into that same fan-out when enabled.

**Chat → context_config → graph → SSE.** Frontend `buildContext` walks per-item `ContextMode`, assembles the context string, and streams `POST /chat/stream` (NDJSON). The graph recalls memory, renders `chat/system`, trims history, sizes tokens, provisions a model through the offline/privacy gates + local-health router, and `astream_events` streams tokens back. Retrieval uses SurrealQL `fn::vector_search` over `source_embedding` + `source_insight`. Citations resolve to passages lazily via `locate_passage`.

**SurrealDB edge schema (highlights).** Three RELATION edge tables carry the graph, all pointing *into* the notebook:
```surql
DEFINE TABLE reference  TYPE RELATION FROM source        TO notebook;   -- source ↔ notebook
DEFINE TABLE artifact   TYPE RELATION FROM note          TO notebook;   -- note   ↔ notebook
DEFINE TABLE refers_to  TYPE RELATION FROM chat_session  TO notebook;   -- session ↔ notebook
```
`in` is the child (source/note/session), `out` is the notebook — trivially easy to invert, which the audit rules flag. The **mind map** deliberately reuses `reference`/`artifact` (no new schema): `Notebook` queries `select in as source from reference where out=$id` and `select in as note from artifact where out=$id` and emits `{source→id, kind:"reference"/"artifact"}` edges for `@xyflow/react`.

**External services.** All cloud AI providers (via Esperanto) are opt-in by key presence. Web search is opt-in too: `web_search` tool only exists when `SERPER_API_KEY` / `TAVILY_API_KEY` / `SEARXNG_BASE_URL` is set. MCP servers (`open_notebook/mcp/`) can add external tools. Local sidecars (llama.cpp, MLX, whisper, piper, mem0) are the offline defaults.

**Video Overview → local media.** The Artifact Rail fetches completed podcast
episodes only while a slide deck is open. It posts the selected episode ID and
slide-deck artifact ID to `/api/video-overviews`; the API never accepts a path
from the browser. It records relative media/caption URLs in the slide-deck
artifact, and the rail resolves those URLs through the API-base helper for the
HTML video and caption track.

---

## 4. Current Pain Points / Known Limitations

- **Dev-grade auth.** `PasswordAuthMiddleware` is a single global bearer-password check (`secrets.compare_digest`, timing-safe; default `open-notebook-change-me`). No users, no per-notebook permissions, no OAuth/JWT, no rate limiting, OpenAPI docs unauthenticated. Fine for a single-user local desktop app; unacceptable for any shared/networked deployment.
- **SurrealDB live-query corruption + repair-restart workaround.** The worker's `db.live("command")` bookkeeping can collide after an unclean SurrealDB shutdown (SIGKILL/Force-Quit/OOM/power-loss), crashing the next worker with *"The key being inserted already exists"* and bricking source processing. Mitigations are layered but treat the symptom: raised shutdown grace (`ONP_SHUTDOWN_GRACE_SECS=8`), a worker-log watcher that sets a one-shot `.needs_db_repair` flag, and a **boot-time backup-first, abort-safe export→move-aside→reimport** repair (`desktop/db_repair.py`) that runs before SurrealDB starts. Root cause in SurrealDB itself is unaddressed.
- **Broad TanStack cache invalidation.** Several mutations invalidate top-level keys (`['sources']`, `QUERY_KEYS.notebooks`, `['credentials']`) rather than scoped keys — e.g. an insight-polling loop invalidates *all* `['sources']` every ~2 s, and course-pack save fires ~5 sequential invalidations. Causes over-fetching across notebooks.
- **~25-min desktop build + codesign fragility.** CI (`build-desktop.yml`) runs PyInstaller on macos-14 (arm64) + macos-13 (x64) + windows; the local `make build-mac` chain (test→lock→venv→frontend→runtimes→pyinstaller→dmg) is long. PyInstaller's own signing can leave an invalid seal, so the Makefile does an explicit final `codesign --force --deep --sign "$ONP_CODESIGN_IDENTITY"` (default ad-hoc `-`) + verify. The `.dmg` is unsigned/un-notarized, so first launch needs a Gatekeeper bypass.
- **Lazy get-or-create transformation race.** `get_or_create_summarize_transformation` / `_key_topics` do a `SELECT … LIMIT 1` then create; a first-add race could create two rows (documented as "harmless cosmetic dup," not correctness).
- **LLM-dependent features unverifiable headlessly.** Chat, insights, podcasts, transcription, and smart routing all require live models/sidecars, so they can't be exercised in plain CI/pytest; `integration_surreal`-marked tests need a real SurrealDB (`SURREAL_INTEGRATION=1`).
- **Large single files.** `open_notebook/domain/notebook.py` is ~1520 lines (Notebook/Source/Note/SourceInsight + delete cascades + mind map + search). `open_notebook/graphs/chat.py` is ~48 KB. `ChatPanel.tsx` is 688 lines and `useNotebookChat.ts` 771 — monolithic components mixing streaming, scroll, MCP picker, sessions, and citation viewer.
- **Blocking graph invocations.** Chat/podcast graphs can run minutes with no HTTP-level timeout (transformations added an `ONP_TRANSFORMATION_TIMEOUT_SEC` bound; chat did not).
- **Video Overview is intentionally narrow.** It only composes an existing
  slide deck with an already-generated, timestamped Audio Overview. It does not
  yet create original B-roll, extract clips from source video, or offer an
  editable timeline. That preserves source fidelity and local safety, but is
  less flexible than a full video editor.

---

## 5. Design Decisions & Trade-offs

- **Local-first / privacy → opt-in egress by key presence.** No cloud call happens unless the user has configured a provider key/credential; web search, cloud LLMs, and MCP are all "default-off, key = opt-in." The privacy gate fails *closed* on detected secrets; the offline gate substitutes local models. Trade-off: routing/gate logic is complex and adds a probe cost (mitigated by TTL cache + single-flight).
- **Reuse existing edge tables for the mind map.** Rather than a new graph schema, the mind map projects the existing `reference`/`artifact` edges. Cheap and consistent; limits the mind map's expressiveness to what those two edges encode.
- **Insight-based summaries.** Summaries/key-topics are modeled as ordinary transformation *insights* (reusing embedding + citation machinery) rather than special-cased fields; key-topics additionally back-fills `source.topics`. Consistent and searchable; costs an extra LLM call per source on ingest.
- **Pin `react-resizable-panels@^2` (not v4).** Deliberate pin (`^2.1.9`) — v4 changed the API/behavior in ways that broke the resizable layout; staying on v2 trades newer features for stability.
- **PyInstaller onedir + BUNDLE.** `EXE(exclude_binaries=True)` + `COLLECT` + `BUNDLE` (bundle id `com.antman1526.open-notebook-plus`) produces a onedir `.app` (faster startup, patchable-in-place — the launcher rewrites the Next.js standalone's baked API port at boot) rather than a single opaque onefile.
- **Stable self-signed identity for a persistent WKWebView store.** A stable codesign identity keeps the macOS data container across rebuilds so `private_mode=False` persistence (wizard/intro cookies) actually survives updates.
- **Two version tracks.** Desktop app (`0.8.5`) vs upstream/Docker image (`1.8.5`) are intentionally not reconciled — they version different artifacts.
- **surreal-commands over an external broker (Celery/Redis).** Jobs live in the same SurrealDB, so the desktop app ships one datastore. Trade-off: it inherits SurrealDB's live-query fragility (see §4).

### Flagged uncertainties (a better approach may exist)
- Single-node chat `StateGraph` — the graph adds LangGraph overhead/checkpointer complexity for what is essentially one model call + history; a plain async function might be simpler, but the graph buys streaming + checkpoint persistence.
- SQLite checkpointer for history while everything else is SurrealDB — two datastores to back up/repair.
- The relaunch bridge shells out to `/bin/sh` with an interpolated PID — safe today (PID is an int), but shell-string construction is a smell.
- The DB-repair workaround is robust but treats a symptom; the real fix likely belongs in how the worker registers/tears down its live query, or a SurrealDB upgrade.

---

## Areas for Review

1. **Auth hardening.** Is the single global password + `compare_digest` acceptable for the desktop threat model (loopback-only), and what's the minimal path to real users/JWT for the Docker track without forking the middleware? Should the API bind refuse non-loopback by default?
2. **SurrealDB live-query corruption — root cause.** Is the "key already exists" crash fixable at the worker's `db.live("command")` registration/teardown (idempotent re-subscribe, explicit `kill`) or by a SurrealDB version bump, rather than the boot-time export/reimport repair? Can the repair ever race a partially-flushed RocksDB?
3. **Cache strategy.** Which broad `invalidateQueries(['sources'])` / `notebooks` / `credentials` calls can be scoped to notebook/source IDs? Is the ~2 s insight-polling invalidation causing measurable over-fetch, and should it move to targeted `setQueryData`?
4. **Build reliability & signing.** Can the ~25-min build be parallelized/cached (uv + PyInstaller warm cache), and should the `.dmg` be notarized to remove the first-launch Gatekeeper friction? Is the explicit final `codesign --deep` still needed on current PyInstaller?
5. **Test coverage of LLM paths.** How to meaningfully test chat/insights/podcast/routing without live models — recorded fixtures, a fake OpenAI-compatible sidecar, contract tests for the offline/privacy gates?
6. **Relaunch mechanism.** Is shelling to `/bin/sh` the right primitive vs `NSWorkspace`/`os.execv`? Does it correctly handle a `.app` moved/renamed mid-session, and non-`.app` (dev) invocations?
7. **File-size / refactor targets.** Prioritize splitting `domain/notebook.py` (Source vs Note vs mind map vs delete-cascade), `graphs/chat.py` (tool loop vs node vs provisioning), and `ChatPanel.tsx`/`useNotebookChat.ts` (streaming vs scroll vs pickers). Which split unlocks the most testability?
8. **Delete-cascade completeness.** Does `Notebook.delete()` cover every dependent (notes+artifacts, exclusive sources, `source_embedding`/`source_insight`, `refers_to` chat sessions, studio artifacts)? Any orphan edges after partial-failure `gather`?
9. **Edge-direction correctness.** Given `in`=child / `out`=notebook is easy to invert, are all `reference`/`artifact`/`refers_to` queries (mind map, delete preview, delete cascade) direction-consistent and covered by tests?
10. **SSE robustness.** Beyond `reader.cancel()` before `releaseLock`, does the backend `astream_events` handler check `request.is_disconnected()` and stop generating on client abort, or does an aborted chat keep burning tokens server-side?
11. **Blocking chat graph.** Should chat get the same `asyncio.wait_for` timeout treatment transformations got (`ONP_TRANSFORMATION_TIMEOUT_SEC`) to bound a hung local model?
12. **Token sizing vs local n_ctx.** Is text-only `token_count` an accurate enough proxy for the local/cloud routing cutoff, and does history-trim interact correctly with the sized payload (no double counting after trim)?
13. **Video Overview scope.** Should the next iteration add a local timeline
editor and source-video clip extraction, or keep the current slide-plus-audio
constraint so every rendered visual remains a reviewed, cited Studio artifact?
