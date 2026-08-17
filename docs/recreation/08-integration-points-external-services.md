# 08 — Integration Points & External Services

> Every integration is **optional**. The product must be fully usable with the network
> cable unplugged. Integrations are accelerants, and each one fails soft.

---

## 1. LLM providers (via LangChain + esperanto)

| Provider | Adapter | Env |
|---|---|---|
| OpenAI | `langchain-openai>=1.1.14` | `OPENAI_API_KEY` |
| Anthropic | `langchain-anthropic>=1.4.6` | `ANTHROPIC_API_KEY` |
| Google | `langchain-google-genai>=4.1.2` | `GOOGLE_API_KEY` |
| Groq | `langchain-groq>=1.1.1` | `GROQ_API_KEY` |
| Mistral | `langchain_mistralai>=1.1.1` | `MISTRAL_API_KEY` |
| DeepSeek | `langchain_deepseek>=1.0.0` | `DEEPSEEK_API_KEY` |
| Ollama | `langchain-ollama>=1.0.1` | `OLLAMA_BASE_URL` |
| OpenAI-compatible | generic | `OPENAI_COMPATIBLE_BASE_URL` + key |

Per-provider connection timeouts are a first-class setting family:
`DEEPER_NOTEBOOK_CONNECTION_TEST_TIMEOUT_SEC_{ANTHROPIC,AZURE,DASHSCOPE,DEEPSEEK,ELEVENLABS,GOOGLE,GROQ,MINIMAX,MISTRAL,OLLAMA,OPENAI,OPENAI_COMPATIBLE,OPENROUTER,VERTEX,VOYAGE,XAI}`.

Credentials are stored encrypted (doc 06) and tested via
`POST /api/credentials/{id}/test`.

## 2. Local inference (the default path)

| Runtime | Package | Role |
|---|---|---|
| llama.cpp | `llama-cpp-python[server]>=0.3.16` | GGUF chat + embeddings, OpenAI-compatible |
| MLX | `mlx-lm>=0.31,<0.32` | Apple-Silicon-optimised chat |
| Ollama | external service | User-managed model library |
| Osaurus | probed on :1337 | MLX server; auto-registered if running |
| faster-whisper | `>=1.1.0,<2` | Speech-to-text |
| piper-tts | `>=1.2.0,<2` | Text-to-speech |
| mem0ai | `>=2.0.18,<3` | Memory extraction/recall |

**MLX request contract:** mlx-lm 0.31 resolves the request's `model` field as a repo id.
Pass the **filesystem path**, not a friendly name, or it 404s against Hugging Face.

**MLX spawn** captures stderr to `~/.deeper-notebook/logs/mlx_server.log` — `DEVNULL`
hid a fatal `ValueError: Model type qwen3_5 not supported` for hours.

## 3. Web search providers

| Provider | Env | Free tier |
|---|---|---|
| Serper | `SERPER_API_KEY` | 2,500 credits |
| Tavily | `TAVILY_API_KEY` | 1,000 searches/mo |
| Brave | `BRAVE_API_KEY` | 2,000 queries/mo |
| SearXNG | `SEARXNG_BASE_URL` (comma-separated) | self-hosted |
| Wikipedia | — | **keyless, always available** |

```python
# Brave: token in a header, count in params, results under web.results
resp = await client.get(_BRAVE_ENDPOINT,
    params={"q": query, "count": n},
    headers={"X-Subscription-Token": _env("BRAVE_API_KEY"),
             "Accept": "application/json"}, timeout=timeout)
web = (data or {}).get("web")
return _normalise(web.get("results"), url_key="url", snippet_key="description", n=n)
```

Wikipedia language edition is configurable and **validated** — an unvalidated value would
build an arbitrary hostname:

```python
_WIKI_LANG_PATTERN = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")
def _wiki_lang() -> str:
    raw = _env("DEEPER_NOTEBOOK_WEB_SEARCH_WIKI_LANG").lower()
    return raw if raw and _WIKI_LANG_PATTERN.fullmatch(raw) else "en"
```

## 4. Scholarly APIs (keyless)

| Service | Endpoint | Notes |
|---|---|---|
| OpenAlex | `https://api.openalex.org/works` | ~250M works; `mailto` opts into the polite pool |
| arXiv | `http://export.arxiv.org/api/query` | Atom; size-bounded before parse |

```python
params = {"search": query, "per-page": n}
mailto = _env("DEEPER_NOTEBOOK_SCHOLARLY_MAILTO")
if mailto:
    params["mailto"] = mailto     # faster, more reliable pool; optional
```

## 5. MCP (Model Context Protocol)

`mcp>=1.28.1,<2` + `fastmcp>=3.0,<4`, streamable-HTTP transport. Servers are registry rows
(`mcp_server`); enabled servers' tools are resolved into the chat loop and can be
individually excluded per turn. `deeper_notebook/mcp/recommendations.py` curates
suggestions (SearXNG, Crawl4AI). `deeper_notebook/security/mcp_transport.py` validates
server URLs — with a **different, more permissive** policy than `outbound_url`, because a
localhost MCP server is legitimate.

## 6. OpenChronicle

Optional local memory/activity bridge, spawned only when detected. `OPENCHRONICLE_MCP_URL`
is honoured (default `http://127.0.0.1:8742/mcp`); a launcher bug that hardcoded the
default made the shim's env-var support dead code for a release.

## 7. Gmail

`gmail_integration` table + `api/routers/gmail.py`. OAuth-based read integration for
importing mail as sources. Fully optional; absent config means the surface is hidden.

## 8. Hugging Face

`huggingface-hub>=1.3.0` for managed model snapshot downloads
(`snapshot_download`). Model libraries live outside the app (e.g. `~/Desktop/MacBook AI
models/{GGUF,MLX,Ollama,...}`), configured by `DEEPER_NOTEBOOK_MODEL_DIR`.

## 9. Content extraction

`content-core>=1.14.1,<2` handles PDFs, Office, HTML, audio, video. Optional Crawl4AI
engine for JS-heavy pages — but the app fetches once through its own policy boundary and
hands Crawl4AI the checked response.

Document writers: `python-docx`, `python-pptx`, `openpyxl`.
Media: `imageio-ffmpeg` (package-managed FFmpeg — **no system FFmpeg is assumed**),
`podcast-creator>=0.12.0,<1` (which pins the `pillow<12` constraint).

## 10. Update check

```python
latest_version = await get_version_from_github_async(
    "https://github.com/Antman1526/Deeper-Notebook", "main"
)
has_update = compare_versions(current_version, latest_version) < 0
```

Fetches `pyproject.toml` from `raw.githubusercontent.com` and compares versions. It must
target **this fork** — pointing at upstream produced a permanent false "update available"
banner (upstream 1.14.x vs fork 1.8.5) linking to releases that did not exist.

## 11. Failure semantics (uniform)

| Integration | On failure |
|---|---|
| Cloud LLM | Offline gate substitutes a local model |
| Web search | Next provider; empty result; turn continues |
| Scholarly | arXiv fallback; empty result |
| MCP server | That server's tools are absent; others unaffected |
| OpenChronicle | Bridge not spawned |
| Gmail | Surface hidden |
| Local sidecar | Marked unhealthy; app degraded but usable |

No integration failure is permitted to abort a chat turn or the application launch.

---

*Continues in [09 — Configuration & Environment Variables](./09-configuration-environment-variables.md).*
