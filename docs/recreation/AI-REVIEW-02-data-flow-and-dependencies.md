# AI Review Brief 2 - Data Flow And Dependencies

## Ingestion To Grounded Answer

```text
User upload / URL / pasted text / audio / video
  -> Sources router validates request and creates a command
  -> surreal_commands worker runs extraction
  -> content-core or optional crawl4ai yields normalized text and metadata
  -> domain Source persists the source and reference edge
  -> chunking splits full text; embedding client writes source_embedding records
  -> SurrealDB HNSW vector index makes the content retrievable
  -> Chat or Ask graph retrieves relevant passages
  -> provider generates a response constrained by the retrieved context
  -> API streams events; frontend renders content and citation controls
```

The crucial contract is that a source is not treated as ready merely because
its record exists. Long-running work is asynchronous. Evidence Studio and
Course Pack generation check source readiness and return a structured
`sources_not_ready` response rather than generating an artifact from partial
input.

## Storage Highlights

SurrealDB holds document records and directional relationship edges. Core
records include notebooks, sources, notes, insights, credentials,
transformations, chat sessions, podcasts, commands, studio artifacts, and
embedding records. The `reference`, `artifact`, and `refers_to` edge tables
express ownership and cross-links. Migrations in
`open_notebook/database/migrations/` are the schema authority; reconstruction
must apply them sequentially through `AsyncMigrationManager`.

Two persistence systems are deliberately present:

| Store | Owns | Reason |
| --- | --- | --- |
| SurrealDB | User-facing data, graph edges, vectors, jobs, credentials | Graph traversal and vector retrieval need one durable database. |
| SQLite LangGraph checkpoint file | Conversation graph checkpoints | LangGraph's checkpoint implementation expects SQLite semantics and WAL concurrency. |

Avoid merging them casually. Their failure, backup, concurrency, and retention
semantics differ.

## External And Local Dependencies

| Dependency | Direction | Failure behavior |
| --- | --- | --- |
| Local llama.cpp, MLX, or Ollama | App calls local OpenAI-compatible endpoints | Provider health determines availability; startup degrades rather than fabricating a model. |
| SurrealDB binary/service | API and worker connect over local WebSocket RPC | Launcher waits for readiness and includes backup-first repair for known corruption cases. |
| `content-core` / optional Crawl4AI | Worker extracts sources | Extraction errors are recorded against the command/source; optional crawler falls back to standard extraction. |
| Cloud LLM/TTS/search services | Esperanto or direct HTTP calls | Opt-in only; privacy/offline gates reroute local or block as configured. |
| MCP servers | Chat graph invokes tools | Tool outputs are untrusted and fenced before returning to the model context. |
| SearXNG / Serper / Tavily | Optional web search tool | Provider is enabled only by configuration; precedence is explicit and no configured provider means no network search. |

## Desktop Data Flow

At startup, `desktop/app.py` chooses an available local provider and places its
endpoint in `extra_env`. `desktop/launcher.py` turns that into the session
environment for FastAPI and sidecars. When MLX is active without a chat GGUF,
the MLX endpoint backs both app chat and the memory writer. This matters: a
memory service with an embedding model but no usable chat endpoint must no-op
gracefully rather than write invalid memory calls.

The Next standalone build contains compile-time rewrite manifests for an API
port. Desktop assigns ports dynamically, so `next_rewrites_patcher.py` patches
a per-user runtime copy before starting `node server.js`. This is a pragmatic
integration point, but it is version-sensitive to Next's generated manifest
layout. Treat it as a tested adapter, not a generic Next.js feature.

## Data Safety Rules

1. Never include raw `.env`, `config.toml`, `launcher.env`, logs, or database
   backups in documentation or source packages.
2. Treat browser/source text and MCP tool results as untrusted input.
3. Keep generated artifacts backward-compatible: structured Evidence Studio
   payloads maintain a canonical typed document plus rendered Markdown and the
   legacy `content` value.
4. Prefer local endpoints for private data. A cloud provider is a separately
   configured, consented boundary, not the default implementation detail.
