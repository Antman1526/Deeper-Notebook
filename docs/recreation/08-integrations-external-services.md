# 08 — Integrations & External Services

Recreation reference for every external service, library, and provider Open Notebook
Plus integrates. For each: **role**, **config**, and **data exchange**. Secrets are
redacted with `<REDACTED>` placeholders — only env-var *names* appear here.

---

## 1. Esperanto — Multi-Provider AI Abstraction

**Role.** `esperanto>=2.20.0,<3` is the unified provider interface. `AIFactory.create_
language()/create_embedding()/create_speech_to_text()/create_text_to_speech()` build
provider-agnostic model objects; `.to_langchain()` adapts language models for LangGraph
nodes. The app never talks to a provider SDK directly — `ModelManager`
(`open_notebook/ai/models.py`) and `provision*` (`ai/provision.py`) go through
Esperanto.

**Supported providers** (per `pyproject.toml` langchain extras + `key_provider.py`):
OpenAI, Anthropic, Google (Gemini), Groq, Ollama, Mistral, DeepSeek, xAI, OpenRouter,
plus Azure OpenAI, Google Vertex, Voyage (embeddings), ElevenLabs (TTS), and generic
`openai_compatible` (the local llama.cpp sidecar registers here).

**Config & data exchange.** Two paths (`open_notebook/ai/CLAUDE.md`,
`ai/key_provider.py`):

1. **Credential-linked (preferred).** Each provider key is a `Credential` SurrealDB
   record (api_key as Pydantic `SecretStr`, Fernet-encrypted at rest). `Model.get_
   credential_obj()` → `credential.to_esperanto_config()` → passed directly to the
   `AIFactory.create_*` call. Supports multiple credentials per provider.
2. **Env-var fallback.** When a model has no linked credential,
   `provision_provider_keys(provider)` injects DB-stored keys into `os.environ`; then
   Esperanto reads them. Provider→env maps:

   | Provider | Env var |
   |---|---|
   | openai | `OPENAI_API_KEY` |
   | anthropic | `ANTHROPIC_API_KEY` |
   | google | `GOOGLE_API_KEY` (also `GEMINI_API_KEY`) |
   | groq | `GROQ_API_KEY` |
   | mistral | `MISTRAL_API_KEY` |
   | deepseek | `DEEPSEEK_API_KEY` |
   | xai | `XAI_API_KEY` |
   | openrouter | `OPENROUTER_API_KEY` |
   | voyage | `VOYAGE_API_KEY` |
   | elevenlabs | `ELEVENLABS_API_KEY` |
   | ollama | `OLLAMA_API_BASE` |
   | azure | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT` (+ `_ENDPOINT_LLM/_EMBEDDING/_STT/_TTS`) |
   | vertex | `VERTEX_PROJECT`, `VERTEX_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` |
   | openai_compatible | `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL` (+ `_LLM/_EMBEDDING/_STT/_TTS` variants) |

**Connection testing** (`ai/connection_tester.py`): `test_provider_connection()` makes
a minimal call per provider (`TEST_MODELS` map) and normalizes errors (401→"Invalid API
key", `rate limit`→success, `model not found`→success). URL providers (ollama via
`/api/tags`, openai_compatible via `/models`, Azure via `/openai/models`) are probed for
reachability. Timeout: `ONP_CONNECTION_TEST_TIMEOUT_SEC` (+ per-provider overrides like
`ONP_CONNECTION_TEST_TIMEOUT_SEC_OLLAMA`).

---

## 2. content-core — Content Extraction

**Role.** `content-core>=1.14.1,<2` extracts text + metadata from files (50+ types) and
URLs. Used by the source-ingestion graph: `source.py:content_process` calls
`await extract_content(content_state)` and consumes the resulting
`ProcessSourceState` / `ProcessSourceOutput`.

**Config.** Driven by the `ContentSettings` singleton (`open_notebook:content_settings`):
`default_content_processing_engine_doc` and `_url` (default `"auto"`),
`output_format="markdown"`, `auto_delete_files`, and `youtube_preferred_languages`
(`["en","pt","es","de","nl","en-GB","fr","hi","ja"]`). A configured speech-to-text
default model injects `audio_provider`/`audio_model` so content-core transcribes audio
via Esperanto.

**Data exchange.** Input `content_state` dict (`url`, `title`, engine fields); output
`processed_state.content` (markdown), `title`, `url`, `file_path`, `identified_type`.
Empty extraction raises a specific error (YouTube-no-transcript vs generic).

---

## 3. crawl4ai — Optional JS-Rendering Crawler

**Role.** Optional engine (`open_notebook/utils/crawler.py`, v0.8.67u) for
JavaScript-heavy pages. When `ContentSettings.url_engine == "crawl4ai"` and a URL is
present, `source.py` calls `extract_url_with_crawl4ai(url)` *before* the content-core
fallback.

**Config / data exchange.** `crawl4ai` is **dynamically imported** to avoid dependency
conflicts (e.g. lxml versions). On `ImportError` or any runtime error it logs at WARNING
and returns `None`, falling back to content-core — zero behavior change when absent.
Requires `playwright install` / `crawl4ai-setup` for browser binaries.

```python
async with AsyncWebCrawler(verbose=False) as crawler:
    result = await crawler.arun(url=url, bypass_cache=True)
    return result.markdown if getattr(result, "success", False) else None
```

---

## 4. podcast-creator — Podcast Generation

**Role.** `podcast-creator>=0.12.0,<1` generates multi-speaker podcasts. The fork does
NOT use the `create_podcast()` black box; instead it imports the library's exported
LangGraph `podcast_graph` and individual node functions and streams them
(`commands/podcast_staged.py`):

```python
from podcast_creator import (PodcastState, load_episode_config, load_speaker_config,
                             podcast_graph, resolve_language_name)
from podcast_creator.core import Outline
from podcast_creator.nodes import (combine_audio_node, generate_all_audio_node,
                                    generate_outline_node, generate_transcript_node,
                                    route_audio_generation)
```

Nodes: `generate_outline → generate_transcript → generate_all_audio → combine_audio`.

**Config.** `configure("speakers_config"/"episode_config", {"profiles": …})` is the
precondition for `load_*_config()`. Episode/Speaker profiles live in SurrealDB
(`episode_profile`, `speaker_profile` tables) and reference registry models
(`outline_llm`, `transcript_llm`, `voice_model`) resolved to provider/model/config
triples via `_resolve_model_config()` (which decrypts the linked Credential). Language
is BCP 47 (`EpisodeProfile.language`).

**Data exchange.** `PodcastState` carries `content`, `briefing`, `num_segments`,
`language`, `outline` (an `Outline` pydantic model — the user-reviewed outline drives
TTS on resume), `transcript`, `audio_clips`, `final_output_file_path`, `output_dir`,
`speaker_profile`. Output WAVs land under `{DATA_FOLDER}/podcasts/episodes/<uuid>/`.
Timeout `ONP_PODCAST_GENERATION_TIMEOUT_SEC` (1800 s); content cap
`ONP_PODCAST_MAX_CONTENT_TOKENS`. (See doc 07 §4 for the staged algorithm.)

---

## 5. MCP Servers (Model Context Protocol)

**Role.** `mcp>=1.0.0` connects the chat graph to external tool servers (web search,
fetch, scraping, browser). The chat tool loop discovers and binds their tools per turn
(see doc 07 §1.1).

**Client** (`open_notebook/mcp/client.py`). Wraps
`mcp.client.streamable_http.streamablehttp_client` + `ClientSession`. Each call opens a
fresh session (streamable-http keeps no session across requests). Methods:
`list_tool_names()`, `list_tools_full()` (name + description + input_schema),
`call_tool(name, args)`. Every RPC is bounded by `ONP_MCP_RPC_TIMEOUT_SEC` (30 s).
Optional auth header via `ONP_MCP_AUTH_HEADER="Authorization: Bearer <REDACTED>"`.

**Registry** (`open_notebook/mcp/registry.py`). `list_enabled_servers()` reads the
`mcp_server` SurrealDB table (migration 17):
`SELECT id, name, url, enabled, priority, created FROM mcp_server WHERE enabled = true
ORDER BY priority ASC, created ASC` — deterministic ordering so multi-server binding
and tie-breaks are stable (default priority 100, migration 19).

**Recommendations** (`open_notebook/mcp/recommendations.py`, v0.8.41). A read-only
curated list of known-good servers (web-search / browser / scraping) with `default_url`
+ `install_url`; the frontend renders cards whose "Connect" button POSTs to
`POST /api/mcp`. The app can't install MCP servers (they're external Docker/npm/Python
processes) — only pre-fill the form. Deliberately skips Mem0 (server-side memory writer
already integrated), Qdrant (SurrealDB native vectors), Context7 (research, not coding).

**Data exchange.** Per-turn: tools are bound as `mcp_<name>` StructuredTools; results
return `{text, blocks}`, captured into `mcp_tool_calls` for citation pills; output is
fenced as UNTRUSTED before re-feeding the model. Per-request the user can disable
servers via `disabled_mcp_servers`. Discovery is 30 s TTL-cached per server URL.

---

## 6. Web Search Tools (`open_notebook/tools/web_search.py`, v0.8.64/65)

**Role.** A native env-keyed `web_search` chat tool — no MCP server required. Bound to
the chat model only when `web_search_enabled()`.

**Config — key-presence is the opt-in** (no separate `ONP_*` flag):

| Env var | Provider | Endpoint |
|---|---|---|
| `SERPER_API_KEY` | Serper (Google Search) | `https://google.serper.dev/search` |
| `TAVILY_API_KEY` | Tavily | `https://api.tavily.com/search` |
| `SEARXNG_BASE_URL` | self-hosted SearXNG (keyless) | `<url>/search?format=json` |

Precedence Serper > Tavily > SearXNG; override via `ONP_WEB_SEARCH_PROVIDER`
(`serper|tavily|searxng`; a stale override naming an unconfigured provider is ignored).
`SEARXNG_BASE_URL` accepts comma/space-separated instances for per-instance failover.
Tuning: `ONP_WEB_SEARCH_MAX_RESULTS` (5, ceiling 20), `ONP_WEB_SEARCH_TIMEOUT_SEC` (10,
ceiling 60), `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC` (25, kept under the 30 s chat tool
timeout).

**Data exchange.** `run_web_search(query)` walks the provider failover chain via
`httpx.AsyncClient` (each request gets `min(per-attempt, remaining budget)`); an erroring
attempt falls through, a paid provider's legitimate empty 2xx is accepted as-is, a
SearXNG empty result falls through. **Offline short-circuit (v0.8.68):**
`get_network_state_with_settings()` → if offline, return `[]` immediately (avoids
burning the 25 s budget). Results normalized to `[{title, url, snippet}]` and rendered
by `format_results()` into a numbered block. The API key goes only to the provider's
HTTPS endpoint and is **never logged** (only provider name + error text).

---

## 7. opencode — Local Code Execution Tool (`open_notebook/tools/opencode.py`, v0.8.67r)

**Role.** Wraps the `opencode` CLI as the `opencode_run` chat tool for local/cloud
code-computer execution.

**Config.** Bound only when `opencode_enabled()` — `OPENCODE_BIN` env var, else
`shutil.which("opencode")`, else `/opt/homebrew/bin`, `/usr/local/bin`,
`~/.local/bin`.

**Data exchange.** `run_opencode(prompt, project, model, continue_session)` →
`asyncio.create_subprocess_exec(bin, "run", prompt, [--model …] [--continue], cwd=
project or cwd, env={…, NO_COLOR:1, TERM:dumb})`, 5-minute timeout. Returns stdout (or
`Error: <stderr>`); captured into `mcp_tool_calls`.

---

## 8. microsoft/SkillOpt — Prompt Optimizer

**Role.** `skillopt` (MIT, optional) optimizes Transformation prompts (full algorithm in
doc 07 §5). Both the target (runs the prompt) and optimizer (judges + edits) are
configured as **OpenAI-compatible** SkillOpt backends.

**Config.** Vendored `prompt_optimizer/skillopt_base.yaml` is loaded + flattened, then
`build_flat_config()` overrides backends to `openai_chat`, sets endpoints/keys from the
registry models (`resolve_backend()`), `..._auth_mode="openai_compatible"`,
`env="transformation"`, `num_epochs`, `batch_size`, `edit_budget`. The skillopt wheel's
missing prompt `.md` files are backfilled by `ensure_skillopt_prompts()` from
`prompt_optimizer/skillopt_prompts/`.

**Data exchange.** Writes `skill_init.md` (the current prompt), runs
`ReflACTTrainer(flat, TransformationAdapter).train()` on a worker thread, harvests
`best_skill.md` + `history.json`. Worker command:
`commands/prompt_optimizer_commands.py:optimize_prompt_command`
(`ONP_PROMPT_OPT_TIMEOUT_SEC`, offline gate for cloud models). No data leaves the machine
when local models are chosen.

---

## 9. Gmail Digest Integration (`open_notebook/domain/gmail.py`)

**Role.** Single-user OAuth + digest config; the digest scheduler emails a periodic
summary built from sources/memory.

**Config.** Fixed singleton record `gmail_integration:singleton`. OAuth tokens are
encrypted with the same Fernet key as Credentials (`OPEN_NOTEBOOK_ENCRYPTION_KEY`) so a
raw DB dump never exposes them. Google access tokens (~1 h) are refreshed proactively
~5 min before expiry (`needs_refresh()`). A 30 s process-level TTL cache + single-flight
lock (`_CACHE`, `_CACHE_LOCK`) front the slow singleton query; `save()` /
`clear_credentials()` / disconnect invalidate it.

**Data exchange.** `is_connected()`, `needs_refresh()`; the frontend polls
`/api/onp/gmail/status` (~60 s). **Offline deferral (v0.8.68):** when the device is
offline the digest scheduler defers rather than failing the outbound Gmail API call.

---

## 10. surreal-commands — Async Job Queue

**Role.** `surreal-commands>=1.3.1,<2` is the SurrealDB-backed async job queue for
long-running work (embeddings, source processing, transformations, podcasts, prompt
optimization). Commands are decorated `@command(name, app="open_notebook",
retry={...})` and use `CommandInput`/`CommandOutput` Pydantic subclasses.

**Config — retry policy** (`commands/*.py`):

| Command | Retry |
|---|---|
| `process_source` | max 15, exponential_jitter 1–120 s, `stop_on:[ValueError]` |
| `embed_*`, `create_insight`, `run_transformation` | max 5, exponential_jitter 1–60 s |
| `generate_podcast`, `resume_podcast` | `max_attempts: 1` (no duplicate episodes) |
| `optimize_prompt` | per-command timeout, ValueError = permanent |

`stop_on:[ValueError]` is a blocklist (retry everything *except* ValueError), so new
exception types auto-retry.

**Data exchange.** Domain models submit jobs fire-and-forget via `submit_command()`
(must be wrapped in `asyncio.to_thread` when called from `async def` — a recurring bug
class). `source.vectorize()` and `Source.add_insight()` return a `command_id`; status is
polled via `/commands/{command_id}`. `ONP_SUBMIT_COMMAND_TIMEOUT_SEC` and
`ONP_WORKER_MAX_TASKS` tune submission/worker behavior.

---

## 11. Local llama.cpp / Ollama Sidecars

**Role.** The desktop launcher (`desktop/launcher.py`) spawns local model sidecars: a
llama-cpp-python chat server (registers as `openai_compatible`), plus STT/TTS/embedding
shims and the mem0 memory service. These are the providers the offline gate and smart
router treat as local (`LOCAL_PROVIDERS = {"ollama", "openai_compatible"}`).

**Config.** Launcher writes env at spawn time:
`OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL` (health-probe target),
`OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID`, `ONP_CHAT_LLM_CTX` (n_ctx, default 32768),
`ONP_CHAT_LLM_GGUF`, `ONP_CHAT_LLM_N_GPU_LAYERS`, `ONP_EMBED_N_GPU_LAYERS`,
`ONP_MEMORY_URL`, `ONP_STT_URL`, `ONP_TTS_URL`. `config.toml` `provider` field is
`ollama | llamacpp | none`.

**Data exchange.** OpenAI-compatible `/models` + `/chat/completions`. Health is probed
via `health/local_models.py` (30 s TTL-cached in `provision.py`). See doc 07 §2.

---

## 12. OpenChronicle MCP (optional)

Referenced via `OPENCHRONICLE_MCP_URL` / `ONP_REMIND_OPENCHRONICLE` — an optional
external MCP shim the launcher can wire in (skippable via the first-run wizard's
`openchronicle_choice`, default `skip`).
