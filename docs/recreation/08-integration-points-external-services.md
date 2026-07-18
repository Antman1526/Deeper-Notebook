# 08 — Integration Points & External Services

> Recreation reference for **Open Notebook Plus** (`desktop-app` branch).
> This document covers every external-service integration: how it is wired,
> its configuration/env vars, and the data-exchange format. Local-first by
> design — most integrations are **opt-in by key/URL presence** and degrade
> gracefully to "not configured" rather than erroring.

Pinned versions (from `pyproject.toml`): `esperanto>=2.20.0,<3`,
`content-core>=1.14.1,<2`, `podcast-creator>=0.12.0,<1`,
`surreal-commands>=1.3.1,<2`, `langgraph>=1.0.10`,
`langgraph-checkpoint-sqlite>=3.0.1`, `surrealdb>=1.0.4`.

---

## 1. Esperanto — multi-provider AI abstraction

**What**: A single library (`esperanto`) that wraps 15+ AI providers behind
`AIFactory.create_language / create_embedding / create_speech_to_text /
create_text_to_speech`. Everything AI-facing (chat, ask, transformations,
embeddings, podcast LLM/TTS, connection tests) goes through it.

**Wiring** (`open_notebook/ai/models.py`):
```python
from esperanto import (AIFactory, EmbeddingModel, LanguageModel,
                       SpeechToTextModel, TextToSpeechModel)
ModelType = LanguageModel | EmbeddingModel | SpeechToTextModel | TextToSpeechModel
```
`ModelManager.get_model(model_id)` loads a `Model` DB record, and:
1. If the model has a linked `credential`, calls
   `credential.to_esperanto_config()` and passes the config dict directly to the
   matching `AIFactory.create_*` (based on `Model.type`).
2. Otherwise, calls `provision_provider_keys(model.provider)` (see §2) to push
   DB/env keys into `os.environ`, then lets Esperanto read them from env.

`provision_langchain_model(content, model_id, default_type, **kwargs)`
(`open_notebook/ai/provision.py`) is the LangGraph-facing factory: it upgrades to
`large_context_model` when the estimated token count exceeds ~105,000, else uses
the specified/default model, and returns a LangChain-compatible model via
`.to_langchain()`.

**Providers** (`credentials_service.PROVIDER_ENV_CONFIG` + `key_provider.PROVIDER_CONFIG`):
`openai, anthropic, google, groq, mistral, deepseek, xai, openrouter, voyage,
elevenlabs, deepgram, ollama, dashscope, minimax`, plus multi-field
`vertex, azure, openai_compatible`.

---

## 2. Credential system + key_provider provisioning

**What**: UI-managed, encrypted, per-provider credentials stored in the
`credential` SurrealDB table, replacing raw `.env` keys (which still work as
fallback).

**Encryption** (`open_notebook/utils/encryption.py`): API keys are Fernet-encrypted
(AES-128-CBC + HMAC-SHA256). The Fernet key is **derived via SHA-256** from
`OPEN_NOTEBOOK_ENCRYPTION_KEY` (any passphrase works). Rotation:
`OPEN_NOTEBOOK_ENCRYPTION_KEYS` (comma-separated, primary first) →
`MultiFernet` decrypts with any listed key, encrypts with the first. Both support
Docker-secret `_FILE` variants. `Credential._prepare_save_data()` encrypts on
write; `Credential.get()/get_all()` decrypt on read (a decryption failure yields a
placeholder credential with `decryption_error` set — never crashes the list).

**key_provider** (`open_notebook/ai/key_provider.py`) — DB-first → env fallback:
```python
PROVIDER_CONFIG = {
    "openai": {"env_var": "OPENAI_API_KEY"}, "anthropic": {"env_var": "ANTHROPIC_API_KEY"},
    "google": {"env_var": "GOOGLE_API_KEY"}, "groq": {"env_var": "GROQ_API_KEY"},
    "mistral": {"env_var": "MISTRAL_API_KEY"}, "deepseek": {"env_var": "DEEPSEEK_API_KEY"},
    "xai": {"env_var": "XAI_API_KEY"}, "openrouter": {"env_var": "OPENROUTER_API_KEY"},
    "voyage": {"env_var": "VOYAGE_API_KEY"}, "elevenlabs": {"env_var": "ELEVENLABS_API_KEY"},
    "deepgram": {"env_var": "DEEPGRAM_API_KEY"},
    "ollama": {"env_var": "OLLAMA_API_BASE"},          # URL-based
    "dashscope": {"env_var": "DASHSCOPE_API_KEY"}, "minimax": {"env_var": "MINIMAX_API_KEY"},
}
```
- `get_api_key(provider)` — Credential first, then env var.
- `provision_provider_keys(provider)` — sets `os.environ` from a DB credential
  (returns True if set). Dispatches to `_provision_vertex` (`VERTEX_PROJECT`,
  `VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS`), `_provision_azure`
  (`AZURE_OPENAI_API_KEY/ENDPOINT/API_VERSION` + per-mode endpoints),
  `_provision_openai_compatible` (`OPENAI_COMPATIBLE_API_KEY/BASE_URL`), or the
  simple single-var path.
- `provision_all_keys()` — startup bulk load (deprecated for request-time use).

**Connection testing** (`open_notebook/ai/connection_tester.py`): the
`POST /api/credentials/{id}/test` endpoint uses a `TEST_MODELS` map (cheapest
model per provider) and normalizes errors (401→"Invalid API key", rate-limit→
success, model-not-found→success). Special handlers probe Ollama `/api/tags`,
OpenAI-compatible `/models`, Azure `/openai/models`.

**Data exchange**: `Credential.to_esperanto_config()` returns
`{api_key, base_url?, endpoint?, api_version?, endpoint_llm/embedding/stt/tts?,
project?, location?, credentials_path?}` — exactly what `AIFactory.create_*`
accepts as `config`.

---

## 3. llama.cpp / Ollama local models

**What**: Local GGUF models run as **OpenAI-compatible sidecars** and are
presented to Esperanto as the `openai_compatible` (or `ollama`) provider — no
special code path in the AI layer.

**Wiring** (`api/routers/local_models.py`, `open_notebook/local_models/`,
`open_notebook/health/local_models.py`):
- The desktop launcher (`desktop/`) spawns llama.cpp servers via a supervisor
  (routes `supervisor.llamacpp_chat`, `supervisor.llamacpp_embed`) and points
  ONP at them via `openai_compatible` credentials (e.g. chat on `:8001/v1`,
  embed on `:8004/v1`); Piper TTS on `:8002`; Whisper STT similar.
- `GET /api/local-models/health` probes each sidecar's `/models` endpoint
  (OpenAI discovery). Localhost/private-IP URLs are treated as local sidecars.
- `GET /api/local-models/inventory` enumerates `.gguf` files in the model dir
  (`enumerate_models` + `parse_gguf_metadata` → context length, quant, arch).
- `GET /api/local-models/role-routing` recommends which GGUF fits chat/embed/tts.
- `POST /api/local-models/download` / `/benchmark` are async HuggingFace-download
  / benchmark jobs.

**Model directory**: the configured model dir must be the **parent** of the
`GGUF/` folder (e.g. `~/Desktop/AI_Models`), matching
`desktop/config.py:default_model_dir`. Config changes require a full app
quit + relaunch. Runtime venvs are on `llama-cpp-python 0.3.23`.

**To Esperanto**: register a `Credential` with `provider="openai_compatible"` (or
`"ollama"`) and `base_url` pointing at the sidecar; then create `Model` records
linked to it. Ollama default base is `http://localhost:11434` (via
`OLLAMA_API_BASE`); llama.cpp default via `OPENAI_COMPATIBLE_BASE_URL`.

---

## 4. content-core + crawl4ai extraction

**What**: `content-core` extracts text from files (PDF/DOCX/…, 50+ types) and
URLs; `crawl4ai` is an optional local JS-rendering crawler for URLs.

**Wiring** (`open_notebook/graphs/source.py` — the source-ingestion LangGraph):
```python
from content_core import extract_content
from content_core.common import ProcessSourceState
...
processed_state = None
url = content_state.get("url")
if content_state.get("url_engine") == "crawl4ai" and url:
    from content_core.common.state import ProcessSourceOutput
    from open_notebook.utils.crawler import extract_url_with_crawl4ai
    content = await extract_url_with_crawl4ai(url)       # returns markdown or None
    if content:
        processed_state = ProcessSourceOutput(
            title=..., content=content, url=url,
            source_type="url", identified_type="text")
if processed_state is None:
    processed_state = await extract_content(content_state)  # content-core fallback
```
`extract_url_with_crawl4ai` (`open_notebook/utils/crawler.py`) uses
`crawl4ai.AsyncWebCrawler(...).arun(url, bypass_cache=True)` and returns
`result.markdown`; missing package or failure → `None` (falls back to content-core;
needs `playwright install`).

**Engine selection** (`ContentSettings` singleton, doc 03 §2.13):
- Documents: `default_content_processing_engine_doc` ∈ `{auto, docling, simple}`.
- URLs: `default_content_processing_engine_url` ∈
  `{auto, crawl4ai, firecrawl, jina, simple}`.

**Soft-failure sentinel**: content-core signals failure by returning
`title="Error"` and content prefixed `"Failed to extract content:"` (it does not
raise). The graph detects this and raises `ValueError` so the source job is marked
**failed/retryable** rather than saved as "completed" with the error string as
its body. Empty extraction on a YouTube URL raises a specific "configure a
Speech-to-Text model" hint.

**Post-extraction**: `save_source` sets `source.full_text`, writes a
`provenance` dict (`content_source_type`, `identified_type`,
`extractor="content_core"`, `url`, `file_path`), then embedding is submitted via
`source.vectorize()` (fire-and-forget `embed_source` command). Output format is
markdown.

---

## 5. Podcast pipeline (podcast-creator + TTS / Piper)

**What**: Generate multi-speaker podcasts: **outline → transcript → TTS audio →
combine**, run as a background surreal-commands job.

**Wiring**:
- **Profiles** (`open_notebook/podcasts/models.py`, doc 03 §2.9–2.11):
  `EpisodeProfile` (`outline_llm`, `transcript_llm`, `language`, `num_segments`,
  `default_briefing`) and `SpeakerProfile` (`voice_model` + 1–4 speakers, each
  with per-speaker `voice_model` override). `resolve_outline_config()` /
  `resolve_transcript_config()` / `resolve_tts_config()` each call
  `_resolve_model_config(model_id)` → `(provider, model_name, config_dict)` by
  loading the `Model` record and its credential (or `provision_provider_keys`).
- **Submission** (`api/podcast_service.py`): `POST /api/podcasts/generate`
  builds the briefing (base + `briefing_suffix`), snapshots the profiles onto the
  `episode` row, then submits a surreal-commands job (`generate_podcast_command`)
  with **`retry={"max_attempts": 1}`** — no auto-retry, so a failure never creates
  duplicate episode records. Retry is user-initiated
  (`POST /api/podcasts/episodes/{id}/retry`, per-episode lock).
- **Execution**: the worker runs podcast-creator's LangGraph nodes, writing
  `generation_stage` (`generating_outline` → `generating_transcript` →
  `generating_audio` → `combining_audio`, plus `awaiting_review`/`cancelled`) to
  the `episode` row as it progresses. `cancel_requested` is polled cooperatively.
  `review_outline=True` stops at `awaiting_review` for
  `PUT …/outline` + `POST …/approve-outline`.

**TTS providers**:
- **Cloud** (OpenAI `gpt-4o-mini-tts`, ElevenLabs, etc.) via
  `AIFactory.create_text_to_speech()`.
- **Local Piper** runs as an OpenAI-compatible TTS server (e.g. `:8002`), so it is
  configured exactly like any other `openai_compatible` credential/model and
  referenced by a `SpeakerProfile.voice_model`. Health-probed via `/models`.

**Status**: `PodcastEpisode.get_job_status()` / `get_job_detail()` poll
surreal-commands (`get_command_status`). Failed episodes surface the provider
error; there is **no silent-audio fallback**.

**Env**: `ONP_PODCAST_MAX_CONTENT_TOKENS` (content budget). Offline gate blocks
cloud TTS/LLM when the device is offline (§9).

---

## 6. web_search providers (Serper / Tavily / SearXNG)

**What**: A built-in `web_search` StructuredTool the chat model can call, plus the
`POST /api/notebooks/{id}/discover-sources` endpoint. Fully implemented in
`open_notebook/tools/web_search.py`.

**Providers, precedence, opt-in**:
| Env var | Provider | Notes |
|---------|----------|-------|
| `SERPER_API_KEY` | Serper (Google Search API) | https://serper.dev |
| `TAVILY_API_KEY` | Tavily | https://tavily.com |
| `SEARXNG_BASE_URL` | self-hosted SearXNG | keyless; comma/space-separated fallback list |

**Opt-in by key presence** — no separate flag. If none configured,
`web_search_enabled()` is `False`, the tool is never bound → zero behavior change.
Precedence **Serper > Tavily > SearXNG**, overridable with
`ONP_WEB_SEARCH_PROVIDER=serper|tavily|searxng` (a stale override naming an
unconfigured provider is ignored). `run_web_search` is a **failover chain**: an
attempt that *errors* falls through to the next; a SearXNG 200-but-empty also
falls through; a paid provider's legitimate empty 2xx is accepted (no extra spend).

**Provider-selection logic** (`_provider_chain`):
```python
override = _env("ONP_WEB_SEARCH_PROVIDER").lower()
if override in available and available[override]:
    add(override)
else:
    add("serper"); add("tavily"); add("searxng")   # each SearXNG URL is its own attempt
```

**Request/response shapes** (`_do_attempt`, normalized to `{title,url,snippet}`):
- Serper — `POST https://google.serper.dev/search`, header `X-API-KEY`, body
  `{"q": query, "num": n}`; reads `data["organic"][*].{title,link,snippet}`.
- Tavily — `POST https://api.tavily.com/search`, body
  `{"api_key", "query", "max_results": n, "search_depth": "basic"}`; reads
  `data["results"][*].{title,url,content}`.
- SearXNG — `GET {base}/search?q=…&format=json`; reads
  `data["results"][*].{title,url,content}`.

**Budgets** (env-tunable, capped): `ONP_WEB_SEARCH_MAX_RESULTS` (5, ≤20),
`ONP_WEB_SEARCH_TIMEOUT_SEC` (10, ≤60) per attempt, `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC`
(25, ≤120) across the chain — kept under the chat loop's per-tool timeout. All I/O
uses `httpx.AsyncClient`; keys are never logged; **offline short-circuits** to `[]`.

**Returned to the LLM** (`format_results`): a numbered plain-text block so the
model can cite `[1]/[2]`. `build_web_search_tool(captures)` wraps it as a
LangChain `StructuredTool` (input `{query: str}`) and records a capture
`{index,name,args,text,blocks}` matching the MCP citation shape.

---

## 7. mem0 / memory layer

**What**: Open Notebook Plus v0.4 memory — durable user facts, preferences, and
per-session summaries, recalled into the chat system prompt. Three SurrealDB
tables `memory_fact` / `memory_preference` / `memory_episode` (identical shape,
`embedding array<float>` with `HNSW DIMENSION 768` = nomic-embed-text-v1.5).

**Write path** (surreal-commands, `commands/memory_commands.py`): the module is
**runtime-copied** into the `commands` package by
`desktop/app.py:_phase_register_memory_commands` at launcher startup, then the
worker registers two commands:
- `memory_extract_turn` — after a chat turn, extracts atomic facts/preferences
  (LLM), embeds them, and inserts `memory_fact` / `memory_preference` rows.
- `memory_summarize_session` — on chat-session delete, writes a `memory_episode`
  summary. (If the module isn't present yet — fresh install / no-memory build —
  submissions no-op gracefully.)

**Recall path** (`open_notebook/utils/memory_recall.py`):
- `recall_memory(query)` chooses **recency vs semantic** via
  `ONP_MEMORY_RECALL_MODE` (`auto` default): semantic once row count exceeds
  `_SEMANTIC_THRESHOLD = 30`, else recency. Any semantic failure falls back to
  recency.
- **Recency**: `SELECT text, created_at FROM memory_* ORDER BY created_at DESC
  LIMIT n` (facts 15, prefs 10, episodes 2).
- **Semantic**: embeds the query via `model_manager.get_embedding_model()`, then
  `SELECT text, vector::similarity::cosine(embedding,$q) AS score FROM memory_fact
  WHERE embedding <|n|> $q ORDER BY score DESC` and drops rows below
  `_MIN_SCORE = 0.30`.
- **Injection**: `render_memory_block(memory)` produces a markdown block
  (`## User preferences`, `## Recent facts learned about the user`,
  `## Earlier conversation summaries`); each line is flattened + capped at 600
  chars (`_sanitize_memory_text` — prompt-injection defense).

**Chat-graph hook** (`open_notebook/graphs/chat.py`):
```python
memory = await recall_memory(query=last_user_text)
memory_block = render_memory_block(memory)
prompt_data["memory_block"] = memory_block   # rendered into the system prompt
```

**Env**: `ONP_MEMORY_RECALL_MODE` (auto|recent|semantic),
`ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC` (5), `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC`
(5), `ONP_MEMORY_RECALL_BUDGET_SEC` (12), `ONP_MEMORY_RECALL_EPISODES` (1/on).

---

## 8. MCP servers

**What**: A DB-backed registry of external MCP endpoints whose tools the chat
graph can call (streamable-http MCP).

**Registry table** `mcp_server` (doc 03 §2.15): `name` (UNIQUE), `url`,
`enabled bool`, `priority int DEFAULT 100`. Enabled servers are listed
lowest-`priority`-first, then by `created`.

**Wiring**:
- **Registry/client** (`open_notebook/mcp/registry.py`, `open_notebook/mcp/client.py`):
  `list_enabled_servers()` reads the table; `MCPClient(url).list_tools_full()`
  returns `[{name, description, input_schema}]`; `MCPClient.call_tool(name, args)`
  returns `{ok, text, blocks}` (bounded by `ONP_MCP_RPC_TIMEOUT_SEC`, default 30s).
  Optional auth header via `ONP_MCP_AUTH_HEADER="Name: value"`.
- **Chat graph** (`open_notebook/graphs/chat.py`): `_resolve_chat_tools(...)`
  discovers enabled servers (with a short TTL cache), builds a LangChain
  `StructuredTool` per remote tool, and **excludes** any server whose name is in
  the session's `disabled_mcp_servers` (case-insensitive, whitespace-trimmed).
  `bind_mcp_and_run_tool_loop(model, payload, ...)` binds MCP tools **plus**
  `build_web_search_tool` (when enabled), runs the tool-call loop, and accumulates
  citation captures. Per-tool-call timeout `ONP_MCP_TOOL_TIMEOUT_SEC` (default 30s).
- **API** (`api/routers/mcp.py`): `GET/POST/PUT/DELETE /api/mcp`,
  `PATCH /api/mcp/{id}` (reorder priority), `POST /api/mcp/{id}/test`. All URL
  inputs go through the SSRF `validate_url` (§10).
- **Recommendations**: `open_notebook/mcp/recommendations.py` ships curated
  SearXNG / Crawl4AI MCP suggestions the user can one-click add.

**Data exchange**: JSON-RPC over streamable-http; tool results surface to the UI
as citation pills identical to `web_search` results.

---

## 9. Offline gate / network state

**What**: A device network-state service (`open_notebook/health/network.py`,
`get_network_state_with_settings()`) plus the `ContentSettings.offline_mode` flag.
When offline (or force-offline): cloud chat falls back to the local model, podcast
cloud TTS/LLM is blocked, `web_search` short-circuits to `[]`, and Gmail digests
defer. Local-provider models are never affected. `GET /api/system/network-status`
exposes online/offline/forced-offline. The privacy gate
(`open_notebook/ai/privacy_gate.py` + `privacy_classifier.py`) can additionally
keep sensitive turns on local models; `ExecuteChatRequest.bypass_privacy_gate`
overrides per-request.

---

## 10. SSRF `validate_url` guard

**What**: URL validation applied to every user-supplied URL field (credential
`base_url`/`endpoint`s, MCP server URLs) to prevent cloud-metadata SSRF while
**still allowing** the private/localhost endpoints self-hosted setups need.

**Defined in** `api/credentials_service.py`:
```python
def validate_url(url: str, provider: str) -> None:
    # allow: private IPs (10/172.16-31/192.168), localhost (Ollama/LM Studio)
    # block: non-http(s) scheme, malformed URL, link-local 169.254.x.x
    #        (incl. ::ffff:169.254.* IPv4-mapped) and hostnames that RESOLVE there
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme ... Only http and https are allowed.")
    hostname = parsed.hostname
    ...
    ip = ipaddress.ip_address(hostname)          # literal-IP path
    if ip.is_link_local: raise ValueError("Link-local addresses ... not allowed ...")
    if getattr(ip, "ipv4_mapped", None) and ip.ipv4_mapped.is_link_local: raise ...
    # hostname path: socket.getaddrinfo(hostname) → reject if any resolved IP is link-local
    # unresolvable hostnames are ALLOWED (internal DNS / Azure endpoints)
```
Key properties: only **link-local (169.254.x.x)** — the AWS/GCP/Azure metadata
range — is blocked (plus its IPv4-mapped-IPv6 form and hostnames that resolve to
it); private IPs and localhost are intentionally permitted; unresolvable hostnames
pass (internal DNS). Callers wrap it in `asyncio.to_thread` because
`socket.getaddrinfo` is blocking (`api/routers/credentials.py`;
`api/routers/mcp.py`).

---

## 11. Job queue (surreal-commands) — the async backbone

Most integrations above submit **fire-and-forget** jobs to `surreal-commands`
(`submit_command("open_notebook", "<cmd>", payload)`), always wrapped in
`asyncio.to_thread` because `submit_command` opens a **synchronous** SurrealDB
WebSocket (blocking the event loop otherwise). Registered commands
(`commands/__init__.py`): `embed_source_command`, `embed_note_command`,
`embed_insight_command`, `create_insight_command`, `generate_podcast_command`,
and (runtime-copied) `memory_extract_turn` / `memory_summarize_session`. Status is
polled via `get_command_status(command_id)` and surfaced through
`GET /api/commands/jobs/{id}` and the per-resource status endpoints. Podcast jobs
use `max_attempts: 1` to avoid duplicate episode records.

---

## 12. Environment-variable index (integration-relevant)

| Var | Purpose |
|-----|---------|
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` / `_KEYS` (+`_FILE`) | Fernet key(s) for credential encryption / rotation |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`, `VOYAGE_API_KEY`, `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`, `DASHSCOPE_API_KEY`, `MINIMAX_API_KEY` | provider keys (env fallback) |
| `OLLAMA_API_BASE`, `OPENAI_COMPATIBLE_API_KEY`/`_BASE_URL` | local/OpenAI-compatible sidecars |
| `VERTEX_PROJECT`/`VERTEX_LOCATION`/`GOOGLE_APPLICATION_CREDENTIALS` | Vertex |
| `AZURE_OPENAI_API_KEY`/`ENDPOINT`/`API_VERSION` (+ per-mode) | Azure |
| `SERPER_API_KEY`, `TAVILY_API_KEY`, `SEARXNG_BASE_URL` | web search providers |
| `ONP_WEB_SEARCH_PROVIDER`/`_MAX_RESULTS`/`_TIMEOUT_SEC`/`_TOTAL_BUDGET_SEC` | web search tuning |
| `ONP_MEMORY_RECALL_MODE`/`_EMBED_TIMEOUT_SEC`/`_QUERY_TIMEOUT_SEC`/`_BUDGET_SEC`/`_EPISODES` | memory recall |
| `ONP_MCP_RPC_TIMEOUT_SEC`, `ONP_MCP_TOOL_TIMEOUT_SEC`, `ONP_MCP_AUTH_HEADER` | MCP tuning/auth |
| `ONP_PODCAST_MAX_CONTENT_TOKENS` | podcast content budget |
| `ONP_VECTOR_MIN_SCORE` | semantic-search relevance floor (doc 03) |
| `SURREAL_URL`/`SURREAL_ADDRESS`/`SURREAL_PORT`/`SURREAL_PASSWORD`(`SURREAL_PASS`) | database connection |
| `OPEN_NOTEBOOK_PASSWORD`(`_FILE`), `OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN` | auth |

> No secret values appear in this document — only variable names and formats.
