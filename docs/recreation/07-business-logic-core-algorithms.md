# 07 — Business Logic & Core Algorithms

> Exhaustive recreation reference for the core "brain" of **Open Notebook Plus**
> (branch `desktop-app`). Package version `1.8.5` (`pyproject.toml`), desktop
> shell version `0.8.5` (`desktop/__init__.py`). Python 3.11+, LangGraph
> `>=1.0.10`, Pydantic `>=2.9.2`, FastAPI `>=0.136.3`, SurrealDB driver
> `>=1.0.4`, Esperanto `>=2.20.0,<3`.

The application's business logic is split between:

- **LangGraph graphs** (`open_notebook/graphs/`) — deterministic state machines that
  orchestrate LLM calls (`source.py`, `chat.py`, `ask.py`, `transformation.py`,
  `source_chat.py`).
- **surreal-commands handlers** (`commands/`) — async, retriable job-queue workers
  that wrap the graphs plus embedding/insight/podcast work.
- **Domain models** (`open_notebook/domain/`) — SurrealDB-backed records that own
  their own fire-and-forget side-effects (embedding, insight creation).
- **Pure utilities** (`open_notebook/utils/`) — chunking, embedding, citation
  location, token sizing.

Everything is async-first; SurrealDB, graph invocation, and LLM calls are all `await`ed.

---

## 1. Source-ingest pipeline (`open_notebook/graphs/source.py`)

The ingest graph is a `StateGraph(SourceState)` with three nodes and one
conditional fan-out. Topology:

```
START → content_process → save_source → (trigger_transformations) → transform_content → END
```

### 1.1 State shape

```python
class SourceState(TypedDict):
    content_state: ProcessSourceState          # content-core input/output
    apply_transformations: list[Transformation]
    source_id: str
    notebook_ids: list[str]
    source: Source
    transformation: Annotated[list, operator.add]   # reducer: current + returned
    embed: bool
```

The `Annotated[list, operator.add]` reducer is load-bearing: every fan-out branch
returns a `{"transformation": [...]}` and LangGraph merges via `current + returned`.
A node that returns `None` here caused `[] + None → TypeError` and half-saved sources
(v0.7.61 fix — nodes must always return a list-shaped dict).

### 1.2 Node `content_process` — extract

Loads the **persisted** `ContentSettings` singleton (`open_notebook:content_settings`)
rather than hardcoding literals (v0.7.209 fix), then drives extraction:

```python
async def content_process(state: SourceState) -> dict:
    try:
        content_settings = await ContentSettings.get_instance()
    except Exception as exc:
        # cold cache / fresh install / transient pool error → safe defaults
        content_settings = ContentSettings(
            default_content_processing_engine_doc="auto",
            default_content_processing_engine_url="auto",
            default_embedding_option="ask",
            auto_delete_files="yes",
            youtube_preferred_languages=["en","pt","es","de","nl","en-GB","fr","hi","ja"],
        )
    content_state = state["content_state"]
    content_state["url_engine"]    = content_settings.default_content_processing_engine_url or "auto"
    content_state["document_engine"] = content_settings.default_content_processing_engine_doc or "auto"
    content_state["output_format"] = "markdown"
    # STT model injected from DefaultModels for audio/video sources
    ...
    if content_state.get("url_engine") == "crawl4ai" and url:
        content = await extract_url_with_crawl4ai(url)     # v0.8.67u
        ...
    if processed_state is None:
        processed_state = await extract_content(content_state)   # content-core
```

**Soft-failure detection** (content-core returns `title="Error"` + a body prefixed
`"Failed to extract content:"` instead of raising). The node converts that sentinel
into a `ValueError` so the job is marked *failed* and the source becomes retryable —
rather than saving an "error string" as the source body:

```python
    if processed_state.title == "Error" and (processed_state.content or "").startswith("Failed to extract content:"):
        raise ValueError("Could not extract content from this source. ...")
    if not processed_state.content or not processed_state.content.strip():
        if url and ("youtube.com" in url or "youtu.be" in url):
            raise ValueError("Could not extract content from this YouTube video. No transcript... Try configuring a Speech-to-Text model...")
        raise ValueError("Could not extract any text content from this source. ...")
    return {"content_state": processed_state}
```

`ValueError` is significant: the `process_source` command's retry config has
`stop_on=[ValueError, ConfigurationError]`, so these are **permanent** failures.

### 1.3 Node `save_source` — save (+ fire-and-forget embed)

```python
async def save_source(state: SourceState) -> dict:
    content_state = state["content_state"]
    source = await Source.get(state["source_id"])
    if not source:
        raise ValueError(f"Source with ID {state['source_id']} not found")
    source.asset = Asset(url=content_state.url, file_path=content_state.file_path)
    source.full_text = content_state.content
    # extraction provenance recorded (source_type, identified_type, extractor, url, file_path, metadata)
    source.provenance = {**(getattr(source,"provenance",None) or {}), "extraction": extraction_provenance}
    # preserve user title; overwrite only placeholder/empty
    if content_state.title and (not source.title or source.title == "Processing..."):
        source.title = content_state.title
    await source.save()
    if state["embed"]:
        if source.full_text and source.full_text.strip():
            await source.vectorize()      # returns a command_id; NOT awaited (fire-and-forget)
    return {"source": source}
```

Notebook associations are intentionally **not** created here — the API creates them
immediately for UI responsiveness (avoids duplicate edges).

### 1.4 Fan-out `trigger_transformations` — parallel transforms

Uses LangGraph `Send` to fan out one `transform_content` invocation per transformation:

```python
def trigger_transformations(state, config) -> list[Send]:
    if len(state["apply_transformations"]) == 0:
        return []
    return [Send("transform_content", {"source": state["source"], "transformation": t})
            for t in state["apply_transformations"]]
```

### 1.5 Node `transform_content` → `SourceInsight`

Each branch runs the transformation sub-graph and records the result as an insight:

```python
async def transform_content(state: TransformationState) -> dict:
    source = state["source"]
    content = source.full_text
    if not content:
        return {"transformation": []}      # v0.7.61 — must be list-shaped, not None
    transformation = state["transformation"]
    result = await transform_graph.ainvoke(dict(input_text=content, transformation=transformation))
    # v0.7.165 — dual-path state-shape guard (dict subscript OR attr access)
    output_text = (result["output"] if isinstance(result, dict)
                   else (getattr(result, "output", "") or ""))
    await source.add_insight(transformation.title, output_text)   # fire-and-forget insight + embed
    return {"transformation": [{"output": output_text, "transformation_name": transformation.name}]}
```

### 1.6 Job wrapper `process_source_command` (`commands/source_commands.py`)

```python
@command("process_source", app="open_notebook", retry={
    "max_attempts": 15,                       # deep queues / SurrealDB v2 tx conflicts
    "wait_strategy": "exponential_jitter",
    "wait_min": 1, "wait_max": 120,
    "stop_on": [ValueError, ConfigurationError],   # validation/config = permanent
    "retry_log_level": "debug",
})
async def process_source_command(input_data: SourceProcessingInput) -> SourceProcessingOutput:
    transformations = [await Transformation.get(t) for t in input_data.transformations]
    # v0.8.88/v0.8.91 opt-in auto-summary + key-topics appended here (see §7)
    source = await Source.get(input_data.source_id)
    source.command = ensure_record_id(input_data.execution_context.command_id)
    await source.save()
    result = await source_graph.ainvoke({
        "content_state": input_data.content_state,
        "notebook_ids": input_data.notebook_ids,
        "apply_transformations": transformations,
        "embed": input_data.embed,
        "source_id": input_data.source_id,
    })
    insights_list = await result["source"].get_insights()
    # topics populated from Key Topics insight if enabled (see §7)
    return SourceProcessingOutput(success=True, source_id=..., insights_created=len(insights_list), ...)
```

Embedding counts cannot be returned here because embedding is a separate fire-and-forget
job that hasn't finished; `embed_source_command` logs the true count when done.

---

## 2. Chat graph (`open_notebook/graphs/chat.py`)

Single node graph, `StateGraph(ThreadState)`, node `agent` → `call_model_with_messages`.
It is checkpointed with SQLite (dual sync/async savers over one file).

### 2.1 Checkpointing (dual saver)

```python
conn = get_checkpoint_connection(LANGGRAPH_CHECKPOINT_FILE)  # WAL-tuned, integrity-checked
memory = SqliteSaver(conn)
graph = agent_state.compile(checkpointer=memory)             # SYNC — for get_state() reads

# async twin, lazily constructed (aiosqlite needs a running loop):
async def get_async_graph():   # AsyncSqliteSaver over the SAME file
    ...
```

The sync `SqliteSaver` backs `graph.get_state(...)` reads (wrapped in
`asyncio.to_thread`); `AsyncSqliteSaver` backs `astream_events`/`ainvoke` writes.
Both point at the same on-disk file — WAL keeps them consistent (v0.7.192).

### 2.2 Node flow

1. Extract the last human message, then `recall_memory(query=last_user_text)` and
   `render_memory_block(...)` — semantic-or-recency mem0 recall injected into the
   system prompt (`ONP_MEMORY_RECALL_MODE = recent|semantic|auto`).
2. Render `chat/system` prompt via `ai_prompter.Prompter`.
3. **Trim history** (`_trim_message_history` → `trim_message_history`, env
   `ONP_CHAT_HISTORY_CHAR_CAP`, default `12_000` chars ≈ 3k tokens) — the
   `add_messages` reducer is append-only, so untrimmed sessions would overflow a
   16k-context local server.
4. **Size against real text** (v0.7.65): `content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)` — never `str(payload)` (repr wrapper inflates the 105k large-context cutoff).
5. Provision the model. If `model_id` override present → `provision_langchain_model(...)`;
   else → `provision_langchain_chat_model(...)` (smart router, populates `selection_out`).
6. Run the MCP/tool loop via `bind_mcp_and_run_tool_loop`.
7. Clean `<think>` blocks (`clean_thinking_content`) and return the updated message
   plus routing/privacy/agent-FSM telemetry.

### 2.3 Tool loop `bind_mcp_and_run_tool_loop`

Both chat graphs share this helper (single-node graphs, no LangGraph `ToolNode`):

1. **MCP tools** — `_resolve_chat_tools` (TTL-cached discovery, 30s per server URL);
   fail-soft to `[]` on any registry/DB error.
2. **Native `web_search`** tool (env-keyed, DB-independent — see doc 14 §5).
3. **Native `opencode_run`**, **`add_web_source_to_notebook`** tools (opt-in).
4. `model.bind_tools(...)` — fail-soft for local providers lacking tool calling.
5. Invoke, bounded by `ONP_CHAT_MODEL_TIMEOUT_SEC` (default 300s).
6. While the model emits `tool_calls` and `tool_iters < max_iterations`
   (`ONP_AGENT_MAX_ITERATIONS`, default 4): execute each tool (per-call
   `ONP_MCP_TOOL_TIMEOUT_SEC`, default 30s), **fence output as untrusted**
   (`_fence_untrusted_tool_output` — prompt-injection defense, doc 14 §5), feed
   `ToolMessage`s back, re-invoke.
7. Emit `truncated`/`complete` outcome to metrics; classify agent-FSM `<state>` if
   `ONP_AGENT_FSM` is on.

### 2.4 Mid-turn offline retry

If the tool loop raises and `classify_error(e)` is `NetworkError` **and** the turn
wasn't already local, `report_network_failure()` flips network state and retries once
on the gated (now-local) model (v0.8.68).

---

## 3. Ask graph — strategy → search → synthesize (`open_notebook/graphs/ask.py`)

`StateGraph(ThreadState)`, three nodes:

```
START → agent (strategy) → (trigger_queries fan-out) → provide_answer → write_final_answer → END
```

### 3.1 Strategy node `call_model_with_messages`

Produces a structured `Strategy` (up to 5 `Search` terms) via a
`PydanticOutputParser` and the `ask/entry` prompt:

```python
class Search(BaseModel):
    term: str
    instructions: str = Field(description="Tell the answering LLM what info to extract")

class Strategy(BaseModel):
    reasoning: str
    searches: list[Search] = Field(default_factory=list, description="up to five searches")
```

Model provisioned with `structured=dict(type="json")`, `max_tokens=2000`. Every node
wraps `model.ainvoke` in `_ask_invoke(...)` which applies a **per-node timeout**
(`ONP_ASK_NODE_TIMEOUT_SEC`, default 120s) and converts `asyncio.TimeoutError` →
`ExternalServiceError` (HTTP 502) naming the node.

### 3.2 Fan-out and `provide_answer`

```python
async def trigger_queries(state, config):
    return [Send("provide_answer", {"question": state["question"],
                                    "instructions": s.instructions, "term": s.term})
            for s in state["strategy"].searches]

async def provide_answer(state, config) -> dict:
    results = await vector_search(state["term"], 10, True, True)   # hard-coded vector search
    if len(results) == 0:
        return {"answers": []}
    results = _truncate_ask_results(results)      # cap count + per-result chars
    payload["results"] = results; payload["ids"] = [r["id"] for r in results]
    system_prompt = Prompter(prompt_template="ask/query_process").render(data=payload)
    ai_message = await _ask_invoke(model, system_prompt, node="provide_answer")
    return {"answers": [clean_thinking_content(extract_text_content(ai_message.content))]}
```

`_truncate_ask_results` protects local 16k-context models: caps result count
(`ONP_ASK_MAX_RESULTS`, default 10) and joins/truncates each result's `matches`
(`ONP_ASK_PER_RESULT_CHAR_CAP`, default 1500 chars) with a `[...truncated for context budget...]`
marker. Only the large `matches` field is capped; ids/titles/similarity stay for citation.

### 3.3 Synthesis + grounding guardrail + CLARIFY

The `answers` field uses `Annotated[list, operator.add]`, so all sub-answers merge.
`write_final_answer` synthesizes them — **unless** the agent-FSM grounding gate fires:

```python
async def write_final_answer(state, config) -> dict:
    if _agent_fsm_enabled():                      # ONP_AGENT_FSM on/1/true/yes
        answers = state.get("answers") or []
        if not any(isinstance(a, str) and a.strip() for a in answers):
            # NO search produced grounded content → don't hallucinate from empty context
            return {"final_answer": _AGENT_FSM_CLARIFY_MESSAGE,
                    "agent_state": AgentState.CLARIFY.value}
    system_prompt = Prompter(prompt_template="ask/final_answer").render(data=state)
    ai_message = await _ask_invoke(model, system_prompt, node="write_final_answer")
    result = {"final_answer": clean_thinking_content(extract_text_content(ai_message.content))}
    if _agent_fsm_enabled():
        result["agent_state"] = AgentState.COMPLETE.value
    return result
```

`_AGENT_FSM_CLARIFY_MESSAGE` = *"I couldn't find anything relevant to that question in
your sources. Try rephrasing it, using different keywords, or adding sources..."* This
is the **grounding guardrail**: when the retrieval context is empty, the graph declares
`CLARIFY` rather than letting a weak local model confidently hallucinate. Default OFF →
behaviour unchanged. Streaming-safe: `search.py` captures `final_answer` from the node's
`on_chain_end` terminal event, so it is delivered even without token deltas.

---

## 4. Transformation execution → `SourceInsight` (`open_notebook/graphs/transformation.py`)

Single node graph, `StateGraph(TransformationState)`, node `agent` → `run_transformation`.

```python
async def run_transformation(state, config) -> dict:
    source = state.get("source") if isinstance(state.get("source"), Source) else None
    content = state.get("input_text")
    assert source or content, "No content to transform"       # accepts either
    transformation = state["transformation"]
    if not content:
        content = source.full_text                            # fall back to source body
    template = transformation.prompt
    if DefaultPrompts(...).transformation_instructions:
        template = f"{instructions}\n\n{template}"
    template = f"{template}\n\n# INPUT"
    system_prompt = Prompter(template_text=template).render(data=state)
    content_str = _truncate_transformation_input(str(content or ""))   # ONP_TRANSFORMATION_INPUT_CAP=12_000
    payload = [SystemMessage(content=system_prompt), HumanMessage(content=content_str)]
    content_for_sizing = "\n".join(extract_text_content(m.content) for m in payload)  # v0.7.75
    chain = await provision_langchain_model(content_for_sizing, config...model_id, "transformation", max_tokens=8192)
    # v0.8.26 per-node timeout ONP_TRANSFORM_NODE_TIMEOUT_SEC=180s → ExternalServiceError on hang
    response = await asyncio.wait_for(chain.ainvoke(payload), timeout=_transform_node_timeout_sec())
    cleaned = clean_thinking_content(extract_text_content(response.content))
    if source:
        await source.add_insight(transformation.title, cleaned)   # → create_insight_command
    return {"output": cleaned}
```

`Transformation` (domain): `name`, `title`, `description`, `prompt`, `apply_default`.
`Source.add_insight(insight_type, content)` submits `create_insight_command`
(fire-and-forget) which creates the `SourceInsight` DB record then submits
`embed_insight` — all non-blocking. `run_transformation_command`
(`commands/source_commands.py`, retry 5×/exp-jitter 1-60s) is the API-facing wrapper
for `POST /sources/{id}/insights`.

---

## 5. Citation `locate_passage` — token-containment sliding window (`open_notebook/utils/citation_offsets.py`)

ONP citations are bare record IDs (`[source:ID]`) with no offsets. Rather than change
the citation format, the passage is located **on demand**: given the source's
`full_text` and the citing sentence, find the best-matching window's char range so the
frontend can scroll-to/highlight. Deterministic, no embeddings/LLM.

```python
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset("the a an of to in and or is are ... our".split())

def _content_tokens(s: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(s.lower()) if t not in _STOPWORDS and len(t) > 1}

def locate_passage(text, query, *, window=280, stride=120, min_score=0.2):
    if not text or not query: return None
    qset = _content_tokens(query)
    if not qset: return None
    n = len(text); best_start = -1; best_score = 0.0; i = 0
    while i < n:
        chunk = text[i:i+window]
        cset = _content_tokens(chunk)
        if cset:
            score = len(qset & cset) / len(qset)          # containment of query words
            if score > best_score:
                best_score, best_start = score, i
        if i + window >= n: break
        i += stride
    if best_start < 0 or best_score < min_score:
        return None
    start, end = best_start, min(best_start + window, n)
    while start > 0 and not text[start-1].isspace(): start -= 1   # snap outward
    while end < n and not text[end].isspace(): end += 1
    return PassageMatch(start=start, end=end, score=round(best_score,3), snippet=text[start:end].strip())
```

**Algorithm:** slide a 280-char window with stride 120 over `full_text`; score each
window by the fraction of the query's *content* tokens (stopwords removed, single-char
dropped) contained in it; keep the best; require `score >= 0.2` else return `None` (so
the caller opens the source at the top). Boundaries are snapped outward to whitespace so
highlights never split a word. Returns `{start, end, score, snippet}`.

---

## 6. Suggested-questions generation (`api/routers/notebooks.py`, `get_suggested_questions`)

`GET /notebooks/{notebook_id}/suggested-questions?limit=4` (`ge=1, le=8`). Best-effort:
any failure returns `{"questions": []}`; NotFound/InvalidInput still surface as 404/400.

```python
notebook = await Notebook.get(notebook_id)      # 4xx re-raised (meta-test convention)
sources = await notebook.get_sources()
if not sources: return {"questions": []}
# compact corpus digest: titles + topics, capped at 40 sources
lines = [f"- {title}" + (f" — {topics}" if topics else "") for s in sources[:40]]
corpus = f"Notebook: {notebook.name}\nDescription: {notebook.description}\n\nSources:\n" + "\n".join(lines)
system = _SUGGESTED_QUESTIONS_SYSTEM.format(n=limit)
chain = await provision_langchain_model(system + "\n" + corpus, None, "transformation", max_tokens=400)
response = await asyncio.wait_for(chain.ainvoke([SystemMessage(system), HumanMessage(corpus)]), timeout=30.0)
text = clean_thinking_content(extract_text_content(response.content))
# lines parsed into a list of questions
```

The corpus is a *digest* (titles + up to 6 `topics` each), not full text — keeps the
prompt small on large notebooks and reuses the key-topics output from ingest.

---

## 7. Auto-summary + key-topics on ingest (`parse_topics`)

Opt-in flags on `ContentSettings`: `auto_summarize_on_ingest`,
`auto_extract_topics_on_ingest`. In `process_source_command`, before running the graph,
the built-in transformations are appended (idempotent get-or-create, best-effort):

```python
if getattr(content_settings, "auto_summarize_on_ingest", False):
    summarize = await get_or_create_summarize_transformation()      # name="summarize", title="Summary"
    if not any(str(t.id) == str(summarize.id) for t in transformations):
        transformations.append(summarize)
if getattr(content_settings, "auto_extract_topics_on_ingest", False):
    key_topics = await get_or_create_key_topics_transformation()    # name="key_topics", title="Key Topics"
    if not any(str(t.id) == str(key_topics.id) for t in transformations):
        transformations.append(key_topics)
    extract_topics = True
```

Both transformations are seeded lazily in `open_notebook/domain/transformation.py`
(`get_or_create_*`, `SELECT ... WHERE name=$name LIMIT 1`, else create with a canned
prompt). After the graph runs, the Key Topics insight is parsed into `source.topics`:

```python
def parse_topics(text: Optional[str]) -> list[str]:
    if not text: return []
    topics, seen = [], set()
    for raw in str(text).splitlines():
        line = raw.strip()
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()   # strip bullet/number marker
        line = line.strip("*_`\"' ").strip()                           # strip md emphasis/quotes
        if not line or len(line) > 60:  # _MAX_TOPIC_LEN — drop over-long (model ignored format)
            continue
        key = line.lower()
        if key in seen: continue
        seen.add(key); topics.append(line)
        if len(topics) >= 8:            # _MAX_TOPICS
            break
    return topics
```

Post-graph, in `process_source_command`:

```python
if extract_topics:
    topic_insight = next((i for i in insights_list
                          if getattr(i,"insight_type",None) == KEY_TOPICS_TRANSFORMATION_TITLE), None)
    topics = parse_topics(topic_insight.content) if topic_insight else []
    if topics:
        processed_source.topics = topics
        await processed_source.save()
```

`parse_topics` is pure and unit-tested; the population step is best-effort (never fails ingest).

---

## 8. Mind-map graph build (`Notebook.get_graph`, `open_notebook/domain/notebook.py`)

Builds a hub-and-spoke graph grounded in existing edges (`reference` = source→notebook,
`artifact` = note→notebook) — no schema change:

```python
async def get_graph(self) -> dict[str, Any]:
    sources = await self.get_sources()
    notes = await self.get_notes()
    def _label(text, fallback):
        cleaned = (text or "").strip() or fallback
        return cleaned if len(cleaned) <= 80 else cleaned[:79] + "…"
    nodes = [{"id": str(self.id), "type": "notebook", "label": _label(self.name, "Notebook")}]
    edges = []
    for s in sources:
        nodes.append({"id": str(s.id), "type": "source", "label": _label(s.title, "Untitled source")})
        edges.append({"source": str(self.id), "target": str(s.id), "kind": "reference"})
    for n in notes:
        nodes.append({"id": str(n.id), "type": "note", "label": _label(n.title, "Untitled note")})
        edges.append({"source": str(self.id), "target": str(n.id), "kind": "artifact"})
    return {"nodes": nodes, "edges": edges}
```

Node ids are the raw record ids so the frontend can deep-link; labels are trimmed to
≤80 chars to keep the payload small.

---

## 9. Podcast outline/transcript staging + length→segments (`commands/podcast_staged.py`)

podcast-creator's `create_podcast()` is a black box; but the library **exports** its
compiled LangGraph (`podcast_graph`) with four named nodes:
`generate_outline → generate_transcript → generate_all_audio → combine_audio`. ONP
re-implements only the thin setup layer and **streams** the graph to get per-stage
progress, cooperative cancellation, stage-aware timeouts, and outline-review-before-TTS.

### 9.1 Length → segments

```python
_LENGTH_TO_SEGMENTS = {"short": 3, "medium": 5, "long": 8}

def segments_for_length(episode_length: Optional[str]) -> Optional[int]:
    if not episode_length: return None
    return _LENGTH_TO_SEGMENTS.get(episode_length.strip().lower())
```

Used in `build_state_and_config`: `num_segments = segments_for_length(episode_length) or episode_config.num_segments`.
Values stay within the profile validator's 3–20 range; unknown/None → profile default.

### 9.2 Stage streaming + cancellation

```python
NODE_DONE_NEXT_STAGE = {"generate_outline": STAGE_TRANSCRIPT, "generate_transcript": STAGE_AUDIO,
                        "generate_all_audio": STAGE_COMBINE, "combine_audio": None}

async def run_graph_with_stages(graph_obj, state, config, *, episode, deadline, poll_interval=5.0) -> dict:
    merged = {}
    async def _consume():
        async for update in graph_obj.astream(state, config=config, stream_mode="updates"):
            for node_name, node_out in update.items():
                if isinstance(node_out, dict): merged.update(node_out)
                next_stage = NODE_DONE_NEXT_STAGE.get(node_name)
                if next_stage and episode.generation_stage != next_stage:   # audio node fires per-line; write once
                    episode.generation_stage = next_stage
                    await episode.save()
    task = asyncio.create_task(_consume())
    while True:
        done, _ = await asyncio.wait({task}, timeout=poll_interval)
        if task in done: task.result(); break              # surface generation exception
        if time.monotonic() > deadline: task.cancel(); await asyncio.gather(task, return_exceptions=True); raise asyncio.TimeoutError()
        if await _cancel_requested(episode.id): task.cancel(); ...; raise CancelledByUser()
    return merged
```

- **Outline review workflow:** `generate_outline_only` runs just the outline node;
  `get_resume_graph()` builds a graph starting at `generate_transcript` (reusing the
  library's own node functions + `route_audio_generation`) so a user-edited outline can
  resume the tail.
- **Cancellation:** `_cancel_requested` polls `episode.cancel_requested`, fail-open on DB hiccup.
- **Node names pinned** by `tests/test_v0_8_68_podcast_staged.py` so a library upgrade
  that renames them fails loudly.

`generate_podcast_command` uses `max_attempts: 1` (no auto-retry) to prevent duplicate
episode records; TTS failure marks the episode failed → retry via
`POST /podcasts/episodes/{id}/retry` (no silent-audio fallback).

---

## 10. Embeddings & insights — fire-and-forget

### 10.1 Domain-level fire-and-forget

- `Source.vectorize()` → submits `embed_source` command, returns command_id, not awaited.
- `Source.add_insight(type, content)` → `create_insight_command` (DB insert + `embed_insight`), fire-and-forget.
- `Note.save()` → auto-submits `embed_note`.
- Submission uses `submit_command()`; when called from `async def` it must be wrapped in
  `asyncio.to_thread` (recurring codebase gotcha — `submit_command` is sync).

### 10.2 `embed_source_command` (`commands/embedding_commands.py`)

Retry 5×, exp-jitter 1–60s, `stop_on=[ValueError]`. Flow:

```python
source = await Source.get(input_data.source_id)
if not source.full_text or not source.full_text.strip(): raise ValueError(...)
await repo_query("DELETE source_embedding WHERE source = $source_id", ...)   # idempotency
content_type = detect_content_type(source.full_text, file_path)              # ext primary, heuristics fallback
chunks = chunk_text(source.full_text, content_type=content_type)
if total_chunks > MAX_CHUNKS_PER_SOURCE: raise ValueError(...)               # v0.7.178 OOM guard
embeddings = await generate_embeddings(chunks, command_id=cmd_id)            # batches of 50, per-batch retry
# bulk INSERT source_embedding {source, order, content, embedding}
```

### 10.3 `generate_embeddings` batching + mean-pool (`open_notebook/utils/embedding.py`)

- `EMBEDDING_BATCH_SIZE = _get_embedding_batch_size()` — env
  `OPEN_NOTEBOOK_EMBEDDING_BATCH_SIZE` (default **50**); batches split as
  `(len(texts)+50-1)//50`; each batch retried `EMBEDDING_MAX_RETRIES = 3` with
  `EMBEDDING_RETRY_DELAY = 2s` on failure.
- `generate_embedding(text)` — short text (≤ `CHUNK_SIZE` tokens) embeds directly;
  long text is chunked, batch-embedded, and combined via `mean_pool_embeddings`
  (normalize each → element-wise mean → normalize result, numpy).

Chunking config (`open_notebook/utils/chunking.py`): token-based
`OPEN_NOTEBOOK_CHUNK_SIZE` (default **400** tokens, conservative below the 512-token
BERT-family ceiling), `OPEN_NOTEBOOK_CHUNK_OVERLAP` (default 15% of size),
`OPEN_NOTEBOOK_MIN_CHUNK_SIZE` (default 5). `chunk_text` picks
HTML/Markdown/Recursive splitter by detected content type and applies
`_apply_secondary_chunking` when structural splitters overshoot.

---

## Key files

| Concern | Path |
|---|---|
| Source ingest graph | `open_notebook/graphs/source.py` |
| Chat graph + tool loop | `open_notebook/graphs/chat.py` |
| Ask graph + grounding gate | `open_notebook/graphs/ask.py` |
| Transformation graph | `open_notebook/graphs/transformation.py` |
| Citation passage locator | `open_notebook/utils/citation_offsets.py` |
| Suggested questions | `api/routers/notebooks.py` |
| Built-in transformations + `parse_topics` | `open_notebook/domain/transformation.py` |
| Auto-summary/topics wiring | `commands/source_commands.py` |
| Mind-map graph | `open_notebook/domain/notebook.py` (`Notebook.get_graph`) |
| Podcast staging | `commands/podcast_staged.py` |
| Embeddings/chunking | `open_notebook/utils/embedding.py`, `open_notebook/utils/chunking.py` |
| Model provisioning | `open_notebook/ai/provision.py` |
