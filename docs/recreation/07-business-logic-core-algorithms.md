# 07 — Business Logic & Core Algorithms

Exhaustive recreation reference for the core algorithmic surface of **Open Notebook
Plus** (a privacy-first NotebookLM alternative: FastAPI + LangGraph + SurrealDB +
Esperanto multi-provider AI + podcast-creator + local llama.cpp). All file paths are
relative to the repo root unless noted. Secrets are redacted with `<REDACTED>`
placeholders.

Key library versions (`pyproject.toml`):

| Library | Constraint |
|---|---|
| `langgraph` | `>=1.0.10` |
| `langgraph-checkpoint-sqlite` | `>=3.0.1` |
| `langchain` | `>=1.2.0` (`langchain-core>=1.3.3`) |
| `esperanto` | `>=2.20.0,<3` |
| `content-core` | `>=1.14.1,<2` |
| `podcast-creator` | `>=0.12.0,<1` |
| `surreal-commands` | `>=1.3.1,<2` |
| `surrealdb` | `>=1.0.4` |
| `mcp` | `>=1.0.0` |
| `pydantic` | `>=2.9.2` |
| `fastapi` | `>=0.104.0` |

---

## 1. LangGraph Workflows (`open_notebook/graphs/`)

Every node provisions its model through `provision_langchain_model()` /
`provision_langchain_chat_model()` (see §2) and wraps raw provider exceptions with
`classify_error()` (`open_notebook/utils/error_classifier.py`) so they re-raise as
typed `OpenNotebookError` subclasses. `clean_thinking_content()` strips
`<think>…</think>` spans from every LLM response.

### 1.1 `chat.py` — conversational agent (48 KB, the largest graph)

**State** (`ThreadState`, `TypedDict`):

```python
class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]   # append-only reducer
    notebook: Optional[Notebook]
    context: Optional[str]
    context_config: Optional[dict]
    model_override: Optional[str]
    selected_provider: Optional[str]          # "local"/"cloud" routing result
    selected_model_id: Optional[str]
    privacy_gated: Optional[bool]             # gate rerouted cloud→local
    privacy_categories: Optional[list]        # category LABELS only, never values
    agent_state: Optional[str]                # FSM terminal: complete/clarify/truncated
    mcp_tool_calls: Optional[list]            # per-turn citation captures
    disabled_mcp_servers: Optional[list[str]] # per-request tool picker
    bypass_privacy_gate: Optional[bool]       # explicit user "send to cloud anyway"
```

**Graph shape:** single async node `call_model_with_messages` (no LangGraph
`ToolNode`; the tool loop runs *inside* the node). Checkpointed to SQLite via
`SqliteSaver` (sync read path) + `AsyncSqliteSaver` (async write path) over the same
file `LANGGRAPH_CHECKPOINT_FILE` (`{DATA_FOLDER}/sqlite-db/checkpoints.sqlite`). The
dual-saver split exists because newer langgraph raises `NotImplementedError` when the
sync saver's `aget_tuple()` is called during `astream_events`/`ainvoke`.

**Algorithm of `call_model_with_messages`:**

1. **Memory recall** — find the last human message; call
   `recall_memory(query=last_user_text)` (see §7), render to a `memory_block`, inject
   into the `chat/system` Jinja prompt via `ai_prompter.Prompter`.
2. **History trim** — `_trim_message_history()` → `trim_message_history(messages,
   env_var_name="ONP_CHAT_HISTORY_CHAR_CAP", default_char_cap=12_000)`. The
   `add_messages` reducer is append-only, so without trimming every prior turn would
   concatenate into the prompt.
3. **Context sizing** — joins only `extract_text_content(m.content)` per message (NOT
   `str(payload)`, which over-counts ~80–120 chars/message of LangChain repr
   boilerplate and prematurely trips the 105k large-context cutoff — fix v0.7.65).
4. **Model provisioning** — if a `model_id` override is present →
   `provision_langchain_model(..., "chat")`; otherwise →
   `provision_langchain_chat_model(...)` (smart router). `selection_out` and
   `offline_fallback_out` dicts capture the routing/offline decisions for the HTTP
   response. `privacy_gate_bypass=bool(state.get("bypass_privacy_gate"))`.
5. **Notebook resolution** — from `thread_id` via
   `SELECT out FROM refers_to WHERE in = $session_id`.
6. **Tool loop** — `bind_mcp_and_run_tool_loop(...)` (below).
7. **Mid-turn offline retry (v0.8.68)** — if the call raises a `NetworkError` and the
   turn wasn't already local: `report_network_failure()`, re-provision via the offline
   gate, retry ONCE. Any non-network error or a second failure propagates.
8. **Return** cleaned message plus `selected_provider`, `selected_model_id`,
   `offline_fallback`, `privacy_gated`, `privacy_categories`, `agent_state`,
   `mcp_tool_calls`.

**`bind_mcp_and_run_tool_loop()`** — shared by `chat.py` and `source_chat.py`. Steps:

1. **MCP tools** — `_resolve_chat_tools()` discovers each enabled server's full tool
   surface (`list_tools_full()`), 30 s TTL-cached per server URL
   (`_TOOL_DISCOVERY_TTL_S`), wraps each as a `StructuredTool` named `mcp_<name>` with
   an args schema synthesized from the JSON Schema via
   `_json_schema_to_pydantic_model()` (handles nullable `["string","null"]` shapes).
   Binds tools from **all** enabled servers (v0.8.66), de-duping names by
   higher-priority server.
2. **Native tools, each independent / fail-soft:**
   - `web_search` — when `web_search_enabled()` (a provider key/URL is set) and not
     excluded (§ doc 08, `tools/web_search.py`).
   - `opencode_run` — when `opencode_enabled()` (the `opencode` CLI is on PATH).
   - `add_web_source_to_notebook` — when a `notebook_id` is in scope.
3. **`model.bind_tools(...)`** — fail-soft: local providers without tool-calling reset
   the tool list to empty rather than crash.
4. **Generate** — `await asyncio.wait_for(model.ainvoke(payload), timeout=
   _chat_model_timeout_sec())` (default 300 s, `ONP_CHAT_MODEL_TIMEOUT_SEC`).
5. **Tool execution loop** — while the model emits `tool_calls` and
   `tool_iters < max_iterations` (default 4, `ONP_AGENT_MAX_ITERATIONS`): execute each
   call with `asyncio.wait_for(tool.coroutine(**args),
   timeout=_mcp_tool_timeout_sec())` (default 30 s, `ONP_MCP_TOOL_TIMEOUT_SEC`); a
   timeout becomes a `ToolMessage` error string the model can adapt to.
6. **Prompt-injection fencing (v0.8.66)** — every tool result is wrapped by
   `_fence_untrusted_tool_output()` with `[BEGIN/END UNTRUSTED TOOL OUTPUT …]`
   delimiters (and forged end-delimiters are escaped) so external content is treated
   as DATA, not instructions.
7. **Agent-FSM (v0.8.60, `ONP_AGENT_FSM`)** — optionally append an instruction telling
   the model it MAY end with `<state>complete</state>` / `<state>clarify</state>`;
   classify the terminal state via `agent_fsm.parse_state()` and surface it. A loop
   that hits `max_iterations` while still requesting tools → `truncated`.

### 1.2 `source_chat.py` — source-grounded chat

Single async node `call_model_with_source_context` →
`_call_model_with_source_context_inner`. Builds context with
`ContextBuilder` (`utils/context_builder.py`) from the selected source's
`full_text` + insights, capped by:
`ONP_SOURCE_CHAT_SOURCE_CHAR_CAP` (4000), `ONP_SOURCE_CHAT_INSIGHT_CHAR_CAP` (1000),
`ONP_SOURCE_CHAT_MAX_INSIGHTS` (10), `ONP_SOURCE_CHAT_HISTORY_CHAR_CAP` (8000). Reuses
`bind_mcp_and_run_tool_loop`. Compiled with `checkpointer=memory`; an async variant is
lazily built via `get_async_source_chat_graph()`.

### 1.3 `ask.py` — multi-search synthesis (map-reduce)

**Graph:** `agent` → conditional fan-out `trigger_queries` → N× `provide_answer`
(parallel via `langgraph.types.Send`) → `write_final_answer` → END.

- **`call_model_with_messages` (agent)** — renders `ask/entry` with a
  `PydanticOutputParser(Strategy)`. `Strategy` = `{reasoning, searches: list[Search]}`,
  up to five `Search{term, instructions}`. Provisions `"tools"` type,
  `structured=dict(type="json")`, `max_tokens=2000`. Parses cleaned JSON.
- **`trigger_queries`** — emits one `Send("provide_answer", {...})` per search term.
- **`provide_answer`** — `await vector_search(term, 10, True, True)`;
  `_truncate_ask_results()` caps to `ONP_ASK_MAX_RESULTS` (10) results, each `matches`
  field joined and truncated to `ONP_ASK_PER_RESULT_CHAR_CAP` (1500) chars with a
  truncation marker (protects 16k-context local models). Renders `ask/query_process`.
  `answers` accumulates via `Annotated[list, operator.add]`.
- **`write_final_answer`** — renders `ask/final_answer`. **Agent-FSM gate
  (v0.8.53):** when `ONP_AGENT_FSM` is on and no search produced grounded content,
  returns `_AGENT_FSM_CLARIFY_MESSAGE` + `agent_state=CLARIFY` instead of asking the
  LLM to synthesize from an empty context (the hallucination case for weak local
  models).
- **Per-node timeout** — every node call goes through `_ask_invoke()` →
  `asyncio.wait_for(model.ainvoke(payload), timeout=_ask_node_timeout_sec())`
  (default 120 s, `ONP_ASK_NODE_TIMEOUT_SEC`). `TimeoutError` → `ExternalServiceError`
  (HTTP 502) naming the failing node.

### 1.4 `source.py` — content ingestion pipeline

**Graph:** START → `content_process` → `save_source` → conditional fan-out
`trigger_transformations` → N× `transform_content` → END.

- **`content_process`** — loads the `ContentSettings` singleton
  (`open_notebook:content_settings`) for engine prefs (`default_content_processing_
  engine_doc/_url`, default `"auto"`), falling back to hardcoded defaults on DB error.
  Sets `output_format="markdown"`. If a default speech-to-text model is configured,
  injects `audio_provider`/`audio_model` for transcription. **crawl4ai branch
  (v0.8.67u):** if `url_engine == "crawl4ai"` and a URL is present, calls
  `extract_url_with_crawl4ai(url)`; otherwise `await extract_content(content_state)`
  from content-core. Raises a specific message for YouTube videos lacking
  transcripts.
- **`save_source`** — updates `Source.asset` + `full_text`; preserves a user-set title
  (only overwrites empty/`"Processing..."`); if `state["embed"]`, calls
  `source.vectorize()`.
- **`trigger_transformations`** — `Send("transform_content", {...})` per
  transformation; empty list short-circuits.
- **`transform_content`** — invokes the transformation graph; normalizes the
  ainvoke output via `result["output"] if isinstance(result, dict) else getattr(...)`
  (LangGraph state-shape dual-path guard, v0.7.165); returns
  `{"transformation": [{output, transformation_name}]}` (reducer
  `Annotated[list, operator.add]`; must return a list, never `None` — v0.7.61).

### 1.5 `transformation.py` — single-node transform executor

START → `agent` (`run_transformation`) → END. Builds the prompt from
`transformation.prompt` (+ optional `DefaultPrompts.transformation_instructions`) and
a `# INPUT` section, capping input via `_truncate_transformation_input()`
(`ONP_TRANSFORMATION_INPUT_CAP`, 12000 chars). Provisions `"transformation"` type,
`max_tokens=8192`. Bounded by `asyncio.wait_for(chain.ainvoke(payload),
timeout=_transform_node_timeout_sec())` (default 180 s,
`ONP_TRANSFORM_NODE_TIMEOUT_SEC`) → `ExternalServiceError` on timeout. On success,
`await source.add_insight(transformation.title, cleaned_content)`.

---

## 2. Offline / Online Smart-Switching

Three cooperating layers feed `provision_langchain_model()`, the funnel every
workflow uses.

### 2.1 Network-state service (`open_notebook/health/network.py`, v0.8.68)

```python
_DEFAULT_PROBE_TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 443)]
_PROBE_TIMEOUT_S = 2.0
_DEFAULT_TTL_S = 20.0
```

- `get_network_state(forced_offline_lookup=…)` — forced-offline check (no probe) →
  20 s TTL cache (`ONP_NETWORK_STATE_TTL_SEC`) → single-flight probe under
  `_probe_lock`. The probe (`_probe_once`) opens a 2 s TCP connection to each target
  (override: `ONP_NET_PROBE_HOSTS`, `host:port` CSV) via
  `asyncio.to_thread()` so the event loop never blocks.
- **Passive updates** — `report_network_failure()` / `report_network_success()` flip
  the cache immediately when a real cloud call fails/succeeds (covers captive portals
  where the TCP probe lies).
- **`"unknown"`** (probe exception) is treated as ONLINE by consumers — a flaky probe
  must never block cloud access.
- `forced_offline_enabled()` reads `ContentSettings.offline_mode` (30 s cache,
  invalidated by the settings PUT handler). `get_network_state_with_settings()`
  combines both.

### 2.2 Offline gate (`open_notebook/ai/offline_gate.py`, v0.8.68)

```python
LOCAL_PROVIDERS = frozenset({"ollama", "openai_compatible"})  # never gated
```

`gate_language_model_id(candidate_id, fallback_out=…)`:

1. Load the `Model` record *before* consulting network state (local candidates pay
   zero probe cost).
2. Pass through if: no candidate, record missing, `type != "language"`, or provider is
   local.
3. `get_network_state_with_settings()`; if `status != "offline"` → pass through
   (online AND unknown both pass).
4. Else `find_local_language_model()` — prefer `DefaultModels.default_chat_model` when
   it's a local provider, else the first local language model name-sorted for
   determinism.
5. If no local model exists → raise `ConfigurationError` (fail fast with an actionable
   message instead of a 300 s provider-timeout hang). Otherwise substitute and record
   `{offline_fallback, from_model_id, to_model_id, to_model_name, reason}` into
   `fallback_out`. **Fail-open by design:** any internal error returns the original
   candidate.

### 2.3 Provisioning + router (`open_notebook/ai/provision.py`, `ai/router.py`)

`provision_langchain_model(content, model_id, default_type, fallback_out, **kwargs)`:

1. `tokens = token_count(content)`. If `tokens > 105_000` → `large_context` model;
   elif `model_id` → explicit; else default for `default_type`.
2. **Offline gate** — `candidate_id = await gate_language_model_id(candidate_id,
   fallback_out=fallback_out)`.
3. `model_manager.get_model(candidate_id, **kwargs)`; raise `ConfigurationError` if
   None or not a `LanguageModel`. Returns `model.to_langchain()`.

`provision_langchain_chat_model(...)` adds **smart routing**:

- Enabled when `OPEN_NOTEBOOK_AUTO_ROUTE_CHAT` is truthy (`1/true/yes/on`); if the env
  var is unset, falls back to `DefaultModels.auto_route_enabled` (UI toggle). Off →
  plain default-chat path.
- Reads `OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID`, `OPEN_NOTEBOOK_CLOUD_CHAT_MODEL_ID`
  (falls back to `DefaultModels.auto_route_cloud`, NOT `default_chat_model`), local
  `n_ctx` from `OPEN_NOTEBOOK_LOCAL_N_CTX` → `ONP_CHAT_LLM_CTX` → `32768`, and
  provider preference from `OPEN_NOTEBOOK_CHAT_PROVIDER` →
  `DefaultModels.auto_route_provider_pref` → `"auto"`.
- **Health probe** — `_local_chat_healthy_cached()` hits the sidecar's
  `{OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL}/models`, 30 s TTL
  (`_HEALTH_CACHE_TTL_S`), single-flight under `_health_cache_lock`, run on a worker
  thread (`asyncio.to_thread`) so the blocking httpx call never stalls the event loop.
- **Reply headroom (v0.8.66)** — reserves `ONP_LOCAL_REPLY_HEADROOM_TOKENS` (8192) +
  1024 for system prompt/tool schemas before deciding local fits.

**`router.pick_provider(...)`** — pure function, `ModelChoice(model_id, reason)`:

1. `default_provider=="cloud"` → cloud if configured.
2. `default_provider=="local"` → local if configured, else raise.
3. Auto: local **iff** `local_chat_healthy and local_model_id and content_tokens <=
   local_chat_n_ctx - reply_headroom_tokens`.
4. Else cloud if configured (reason names the size/health cause).
5. Else best-effort local (the llama.cpp server returns its own 400 on true overflow).
6. Else `ValueError("No model available")`.

A privacy gate (`ai/privacy_gate.py`, `ai/privacy_classifier.py`, `ONP_PRIVACY_GATE`)
can re-route a cloud pick back to local when structured PII is detected — labels only
are surfaced, never the matched values; `bypass_privacy_gate` skips it with logged
consent.

### 2.4 Local-model health probes (`open_notebook/health/local_models.py`)

`probe_local_model()` detects `:0` port placeholders → `not_configured`; for
`openai_compatible` kind, `_probe_openai_compatible()` GETs `{base_url}/models` with a
structured `httpx.Timeout(connect=2, read=5, write=2, pool=2)` and returns
`healthy/unhealthy` + latency + first 3 model ids. `probe_all_local_models(creds)`
probes sequentially.

---

## 3. Embedding / Chunking Pipeline

### 3.1 Chunking (`open_notebook/utils/chunking.py`)

- **Config** — `OPEN_NOTEBOOK_CHUNK_SIZE` (token-based, default **400**, min 100,
  warn >8192) and `OPEN_NOTEBOOK_CHUNK_OVERLAP` (default **15 %** of chunk size,
  clamped `0 <= overlap < chunk_size`). Computed once at import (`CHUNK_SIZE`,
  `CHUNK_OVERLAP`). The 400 default leaves ~20 % headroom below the 512-token ceiling
  of BERT-family embedders, absorbing the `o200k_base`-measured vs WordPiece tokenizer
  mismatch.
- **Content-type detection** — `detect_content_type(text, file_path)`: extension map
  is primary (`_EXTENSION_TO_CONTENT_TYPE`, HTML/Markdown/plain + code-as-plain);
  heuristics (`_calculate_html_score` / `_calculate_markdown_score`, scored 0–1 over
  the first 5000 chars) are the fallback and may override a `.txt`-style PLAIN
  extension only at `HIGH_CONFIDENCE_THRESHOLD = 0.8`.
- **`chunk_text()`** — text ≤ `CHUNK_SIZE` tokens returns `[text]`. Otherwise selects a
  LangChain splitter by type:
  - HTML → `HTMLHeaderTextSplitter` (h1/h2/h3)
  - Markdown → `MarkdownHeaderTextSplitter` (#/##/###, `strip_headers=False`)
  - Plain → `RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP, length_function=token_count,
    separators=["\n\n","\n",". ",", "," ",""])`
  HTML/Markdown outputs pass through `_apply_secondary_chunking()` (re-splits any chunk
  > `CHUNK_SIZE` tokens with the plain splitter). Empty chunks are filtered.

### 3.2 Embedding (`open_notebook/utils/embedding.py`)

- **Config** — `OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE` (default **50**),
  `EMBEDDING_MAX_RETRIES = 3`, `EMBEDDING_RETRY_DELAY = 2 s`.
- **`generate_embeddings(texts)`** — splits into batches of `EMBEDDING_BATCH_SIZE`;
  each batch `await embedding_model.aembed(batch)` with up to 3 retries
  (`asyncio.sleep(2)` between); final failure → `RuntimeError`. Model from
  `model_manager.get_embedding_model()`.
- **`generate_embedding(text, content_type, file_path)`** — text ≤ `CHUNK_SIZE`
  tokens → embed directly; otherwise `chunk_text()` → `generate_embeddings(chunks)` →
  `mean_pool_embeddings()`.
- **`mean_pool_embeddings(embeddings)`** — algorithm: normalize each vector to unit
  length (numpy, axis-1, divide-by-zero guarded) → element-wise mean → normalize the
  result to unit length. Single-vector input is just normalized.

These are driven by the fire-and-forget `embed_*` commands in
`commands/embedding_commands.py` (5 retries, exponential jitter 1–60 s; ValueError =
permanent).

---

## 4. Staged Podcast Generation (`commands/podcast_commands.py`, `podcast_staged.py`)

podcast-creator's `create_podcast()` is a black box, but it **exports its compiled
LangGraph** `podcast_graph` with four named nodes:
`generate_outline → generate_transcript → generate_all_audio → combine_audio`.
`podcast_staged.py` re-implements only the thin setup layer and streams the library's
own graph (`graph_obj.astream(..., stream_mode="updates")`), unlocking per-stage
progress, cancellation, stage-aware timeouts, and outline review — with zero forking.

**Stage constants** (`open_notebook/podcasts/models.py`):
`generating_outline`, `generating_transcript`, `generating_audio`, `combining_audio`,
`awaiting_review`, `cancelled`. `NODE_DONE_NEXT_STAGE` maps each completed node to the
next stage written onto the episode record.

### 4.1 `generate_podcast_command` (surreal-commands, `retry={"max_attempts": 1}`)

1. Load `EpisodeProfile` + `SpeakerProfile` by name; validate
   `outline_llm`/`transcript_llm`/`voice_model` are set.
2. Resolve provider/model/config triples (`resolve_outline_config`,
   `resolve_transcript_config`, `resolve_tts_config` → `_resolve_model_config`).
3. `_load_and_configure_all_profiles()` — resolves model-registry references for ALL
   profiles (podcast-creator validates the whole config), drops profiles that fail to
   resolve, fail-fasts if the SELECTED profiles didn't survive, then calls
   `configure("speakers_config"/"episode_config", …)`.
4. Build the briefing (`default_briefing` + optional `briefing_suffix`); thread
   `EpisodeProfile.language` (BCP 47) through.
5. Create + save the `PodcastEpisode` record (links to `command_id`); build a
   UUID-named output dir under `{DATA_FOLDER}/podcasts/episodes/`.
6. `build_state_and_config(...)` mirrors `create_podcast`'s setup (loads episode/speaker
   config, resolves language, builds `PodcastState`).
7. **Outline-review phase 1** — if `review_outline`: stage→`generating_outline`, run
   `generate_outline_only()` (the outline node alone), persist `episode.outline`,
   stage→`awaiting_review`, sweep the empty dir, return early.
8. **Full generation** — stage→`generating_outline`, then
   `run_graph_with_stages(get_full_graph(), state, config, episode=…, deadline=
   time.monotonic()+_podcast_timeout)`. Timeout `ONP_PODCAST_GENERATION_TIMEOUT_SEC`
   (default **1800 s**).
9. Persist `audio_file`, `transcript`, `outline` defensively (`.get()`, `result` may
   be `None`/partial). On `CancelledByUser` → stage `cancelled`; on `TimeoutError` →
   `RuntimeError` naming the hung stage; both sweep the empty output dir. GPT-5
   "Invalid json output" errors get an explanatory hint.

### 4.2 `resume_podcast_command` (phase 2 of outline review)

Requires the episode to be in `awaiting_review` with a non-empty outline. Re-resolves
profiles, resets `cancel_requested=False`, stage→`generating_transcript`, builds state
with the **user-reviewed outline**, and runs `get_resume_graph()` — a freshly compiled
`StateGraph(PodcastState)` that starts at `generate_transcript` (reusing the library's
own `generate_transcript_node`, `generate_all_audio_node`, `combine_audio_node`,
`route_audio_generation`).

### 4.3 `run_graph_with_stages()` — streaming/cancel/timeout driver

```python
async def _consume():
    async for update in graph_obj.astream(state, config=config, stream_mode="updates"):
        for node_name, node_out in update.items():
            if isinstance(node_out, dict):
                merged.update(node_out)
            next_stage = NODE_DONE_NEXT_STAGE.get(node_name)
            if next_stage and episode.generation_stage != next_stage:
                episode.generation_stage = next_stage
                await episode.save()
task = asyncio.create_task(_consume())
while True:
    done, _ = await asyncio.wait({task}, timeout=poll_interval)  # poll_interval=5.0
    if task in done: task.result(); break
    if time.monotonic() > deadline: task.cancel(); raise asyncio.TimeoutError()
    if await _cancel_requested(episode.id): task.cancel(); raise CancelledByUser()
```

`_cancel_requested()` polls `SELECT cancel_requested FROM ONLY $id` every 5 s and is
fail-open (a flaky read never aborts a 20-minute run). The audio node fans out one
event per dialogue line (via `Send`), so the stage transition is written only once.

> The `desktop/CHANGELOG.md` documents `max_attempts: 1` for podcast jobs (prevents
> duplicate episode records). TTS/provider failures mark the episode failed; retry via
> `POST /podcasts/episodes/{id}/retry` (no silent-audio fallback).

---

## 5. Evidence Studio Course Pack Generation

Evidence Studio uses `studio_artifact` and `studio_workflow_run` records to turn a
notebook's source bundle into durable markdown artifacts. The legacy
`training_guide` artifact type remains supported for backward compatibility, but the
product name and UI label are **Course Pack** because the output is broader than a
linear guide: it is intended for instructors, facilitators, and learners.

The main service boundary is `open_notebook/studio/artifact_generation.py`. The
Course Pack instruction is deliberately source-type aware:

```python
_ARTIFACT_TYPE_INSTRUCTIONS: dict[str, str] = {
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
    ),
    "training_guide": (
        "... This artifact type is a legacy alias for Course Pack."
    ),
}
```

Workflow steps are exposed to the frontend so a user can see where generation is
blocked:

```python
return [
    {"id": "context", "label": "Context built", "status": "completed"},
    {"id": "privacy_gate", "label": "Privacy gate", "status": approval_status},
    {"id": "model_route", "label": "Model route", "status": model_status},
    {"id": "artifact_generation", "label": _artifact_type_label(artifact.artifact_type), "status": model_status},
]
```

Before any Course Pack is generated, selected sources are checked for extraction
readiness. If an uploaded video, audio file, PDF, document, or link is still processing,
the API returns `409` with `code="sources_not_ready"` and a list of not-ready sources
instead of generating weak training material from partial context.

Automatic model selection is local-model aware. If no explicit model is set on the
artifact, the service enumerates `OPEN_NOTEBOOK_MODEL_DIR` (default
`~/Desktop/AI_Models`), recommends a model role such as `source_synthesis`, and matches
that local file/repo to a registered model. This is how Course Pack generation can use
local GGUF, Ollama, or MLX models without the user reselecting a provider each time.

Important edge cases:

- Thin transcripts should be called out in the generated output as source-readiness
  notes.
- The API keeps `training_guide` as an enum alias so older records still render.
- Long generation is submitted through `commands.studio_commands` so the UI can poll
  progress and preserve failure state.
- Generated content must include source markers; citations are stored with the artifact
  and can be revised/regenerated without replacing the original record.

---

## 6. SkillOpt Prompt Optimizer (`open_notebook/prompt_optimizer/`, v0.8.68)

Wraps **microsoft/SkillOpt** (MIT) to optimize a Transformation's prompt. The prompt
is SkillOpt's trainable "skill document": rollouts run it over example sources with a
TARGET model, an LLM judge scores outputs against user criteria, the OPTIMIZER model
proposes bounded add/delete/replace edits, and a validation gate accepts only edits
that improve the held-out score. `skillopt` is an **optional** dependency
(`skillopt_available()`); the API returns an actionable error when missing.

### 6.1 `runner.py`

- `resolve_backend(model_id)` — `_resolve_model_config(model_id)` →
  `{model_name, endpoint, api_key}`. Both target and optimizer are configured as
  OpenAI-compatible endpoints (covers local llama.cpp AND cloud OpenAI/Azure). Allowed
  providers: `{openai, openai_compatible, ollama, azure, deepseek, groq, mistral, xai,
  openrouter}`. Ollama endpoints get `/v1` appended.
- `ensure_skillopt_prompts()` — the skillopt 0.1.0 wheel ships the `prompts` package
  but not its `.md` files; this backfills the vendored copies in
  `prompt_optimizer/skillopt_prompts/` into the installed package (never overwriting),
  raising `PromptOptimizerError` if site-packages is read-only.
- `build_flat_config(...)` — loads the vendored `skillopt_base.yaml`, flattens it, and
  sets backends to `openai_chat` (`target_backend`/`optimizer_backend`), endpoints,
  api keys, `..._auth_mode="openai_compatible"`, `num_epochs`, `batch_size`,
  `edit_budget`, `env="transformation"`, `skill_init`, `out_root`. `_set()` fails
  LOUDLY if a config key vanishes in a skillopt upgrade.
- `run_prompt_optimization(...)` — writes `skill_init.md`, builds the config + a
  `TransformationAdapter`, and runs `ReflACTTrainer(flat, adapter).train()` on a worker
  thread (`asyncio.to_thread`). Collects `best_skill.md` (deployment artifact) +
  `history.json`; returns `{optimized_prompt, changed, history, run_dir}`.

### 6.2 `adapter.py` — `TransformationAdapter(EnvAdapter)`

Modeled on skillopt's `searchqa` benchmark.

- `ExamplesDataLoader` — in-memory train/val split (`val_ratio=0.34`, seed 42).
  **`get_train_size()` is a REQUIRED override** (the `BaseDataLoader` default returns
  `None`, which aborts training with "Unable to determine train_size").
- `_run_one(item, skill_content, out_dir)` — `chat_target(system=skill_content,
  user=input_text, max_completion_tokens=4096)` produces the prediction; the judge
  (`chat_optimizer`, `_JUDGE_SYSTEM`) returns `{"score": float, "reason": str}`;
  `parse_judge_score()` regex-extracts and clamps the score to `[0,1]` (0.0 on
  garbage). `hard = 1 if soft >= judge_threshold (0.7) else 0`.
- `rollout()` — `ThreadPoolExecutor(max_workers=4)` over items.
- `reflect()` — delegates to the library's `run_minibatch_reflect(...)` (analyst
  workers 2, `minibatch_size`, `edit_budget`, patch update mode).

The worker command is `commands/prompt_optimizer_commands.py:optimize_prompt_command`
(surreal-commands, env-tunable `ONP_PROMPT_OPT_TIMEOUT_SEC`, ValueError = permanent,
offline gate for cloud models; `_MAX_EXAMPLES=10`, `_MAX_INPUT_CHARS=6000`).

---

## 7. Memory Writer / Recall

### 7.1 Writer (`desktop/memory/writer.py` — Hermes 3 agent)

Two entry points, both call `<llm>.complete(system_prompt, user_prompt)` and parse
`<tool_call>…</tool_call>` blocks (`_TOOL_CALL_RE`), dispatching each via
`apply_tool_call` to the mem0 client:

- `extract_turn()` — runs after each assistant response, extracts explicit
  facts/preferences. Inputs capped: `_MAX_TURN_CHARS = 4000` (truncated from the END
  to keep recent material).
- `summarize_session()` — runs on session end, produces one `episode` record.
  `_MAX_TRANSCRIPT_CHARS = 16_000`.

Storage routes by `kind` into SurrealDB tables `memory_fact`, `memory_preference`,
`memory_episode` (`desktop/memory/surreal_store.py`).

### 7.2 Recall (`open_notebook/utils/memory_recall.py`)

`recall_memory(query)` is a thin orchestrator with caps `_MAX_FACTS=15`,
`_MAX_PREFERENCES=10`, `_MAX_EPISODES=2`:

- **Mode** — `ONP_MEMORY_RECALL_MODE` ∈ `recent | semantic | auto` (default auto).
  Below `_SEMANTIC_THRESHOLD = 30` rows, uses recency (saves an embed round trip);
  above, `recall_relevant_memory(query)` does cosine similarity over the mem0-populated
  `embedding` column with `_MIN_SCORE = 0.30`. **Any** semantic failure falls through
  to recency so chat never breaks on a misconfigured embedder.
- **Episode recall** defaults ON (`ONP_MEMORY_RECALL_EPISODES`, set `0` to suppress) —
  episodes were previously WRITE-ONLY until v0.8.49 wired the read path.
- Returns `{text, scope, kind}` dicts the `chat/system` Jinja template iterates via
  `render_memory_block()`. Tolerant of missing tables (fresh DBs return empty).
  Recalled memory is flattened/fenced before prompt injection (v0.8.47) and embed calls
  are bounded by `ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC` /
  `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC` / `ONP_MEMORY_RECALL_BUDGET_SEC`.

> Several v0.8.19 → v0.8.30 fixes corrected a SurrealDB "Missing order idiom" parse
> error: `SELECT VALUE <field> … ORDER BY <other>` is rejected — the ORDER BY field
> must be in the projection — which had silently returned empty memory for many
> releases.
