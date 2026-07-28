# Deeper Notebook - Root CLAUDE.md

This file provides architectural guidance for contributors working on Deeper Notebook at the project level.

## Project Overview

**Deeper Notebook** is an open-source, privacy-focused research assistant for multimodal sources, grounded notes, semantic search, AI chat, and podcasts—with complete control over data and model providers.

**Key Values**: Privacy-first, multi-provider AI support, fully self-hosted option, open-source transparency.

---

## Standing Workflow For Every Prompt

These instructions apply to **every** prompt this assistant receives in this repository, not just prompts that explicitly ask for testing, debugging, or refactoring. They are a baseline behavior; the user's specific request layers on top.

On every prompt, you must:

### 1. Test and find bugs/issues first

Before (or alongside) addressing the user's stated request, actively audit the code paths you are about to touch and the closely related ones:

- Read the files you intend to modify and the modules that consume or feed them.
- Run the relevant test suite (`uv run pytest tests/` for backend, `pnpm test --run` from `frontend/` for frontend) when changes could affect behavior. If running tests is impractical, reason through them in writing.
- Look for: real bugs (incorrect logic, wrong query direction, swallowed exceptions, race conditions), regressions, edge cases (None values, empty collections, multi-byte UTF-8, concurrency), broken behavior, dead code, security issues (unscoped queries, missing auth checks, leaked secrets), and reliability issues (event-loop blocks, missing timeouts, unhandled disconnects, resource leaks).
- Pay specific attention to recurring patterns this codebase has been bitten by: sync `surreal_commands.submit_command` called inside `async def` (must be wrapped in `asyncio.to_thread`); LangGraph state-shape variance (`isinstance(output, dict)` vs Pydantic — accept both via `getattr` fallback); SSE handlers missing `is_disconnected()` checks; readers released without `cancel()` first; SurrealDB edge tables (`reference`, `artifact`, `refers_to`) where `in`/`out` direction is easy to invert; missing delete cascades; and `str(payload)` overcounting when sizing LLM context.

### 2. Fix the issues you find

Resolve identified bugs as part of the current response, not as a deferred follow-up:

- Apply the fixes inline, in the same change set as the user's request.
- Each fix gets a clear inline code comment naming the version (e.g. `# v0.7.NN — ...`) and explaining what was broken and why the new code is correct. This convention matches the rest of the codebase.
- Add or update tests when the bug is testable without a live SurrealDB / running services. Run the suite afterward and confirm it passes.
- Update `desktop/CHANGELOG.md` ("Unreleased" section) with one bullet per logical fix.

### 3. Make improvements where warranted — with judgment

Apply targeted improvements that materially help the codebase:

- Good targets: readability, correctness, error handling, type safety, accessibility, security, observability, production-readiness, removing dead code, replacing string-typed magic with constants, breaking apart large files when you're already inside them.
- **Stay in scope.** Do not perform unrelated refactors or sweeping reformatting. If a file you're touching has problems outside the current request, surface them in the response and either (a) fix them only if they're tightly related and low-risk, or (b) explicitly defer them as a note. Sprawl is worse than progress.
- Match existing patterns. This codebase has established conventions for error classification, async/await, edge-table queries, fire-and-forget command submission, and frontend hook composition — follow them rather than inventing new ones.

### Reporting requirements

Every response that involves code changes must clearly call out, in plain language:

- **(a) Bugs / issues found** during the audit, with file:line references.
- **(b) Fixes applied**, with a short description of what each fix changes.
- **(c) Improvements made**, distinct from bug fixes, with rationale.
- **(d) Anything intentionally deferred** — issues you noticed but did not address this turn, with one line on why (out of scope, requires a migration, etc.). Never silently ignore something significant.

If the audit found nothing worth fixing, say so explicitly ("Audited X, Y, Z; no issues found") rather than omitting the section.

---

## Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Frontend (React/Next.js)                    │
│              frontend/ @ port 3000                       │
├─────────────────────────────────────────────────────────┤
│ - Notebooks, sources, notes, chat, podcasts, search UI  │
│ - Zustand state management, TanStack Query (React Query)│
│ - Shadcn/ui component library with Tailwind CSS         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP REST
┌────────────────────────▼────────────────────────────────┐
│              API (FastAPI)                              │
│              api/ @ port 5055                           │
├─────────────────────────────────────────────────────────┤
│ - REST endpoints for notebooks, sources, notes, chat    │
│ - LangGraph workflow orchestration                      │
│ - Job queue for async operations (podcasts)             │
│ - Multi-provider AI provisioning via Esperanto          │
└────────────────────────┬────────────────────────────────┘
                         │ SurrealQL
┌────────────────────────▼────────────────────────────────┐
│         Database (SurrealDB)                            │
│         Graph database @ port 8000                      │
├─────────────────────────────────────────────────────────┤
│ - Records: Notebook, Source, Note, ChatSession, Credential│
│ - Relationships: source-to-notebook, note-to-source     │
│ - Vector embeddings for semantic search                 │
└─────────────────────────────────────────────────────────┘
```

---

## Useful sources

User documentation is at @docs/

## Tech Stack

### Frontend (`frontend/`)
- **Framework**: Next.js 16 (React 19)
- **Language**: TypeScript
- **State Management**: Zustand
- **Data Fetching**: TanStack Query (React Query)
- **Styling**: Tailwind CSS + Shadcn/ui
- **Build Tool**: Webpack (via Next.js)
- **i18n compatible**: All front-end changes must also consider the translation keys

### API Backend (`api/` + `open_notebook/`)
- **Framework**: FastAPI 0.104+
- **Language**: Python 3.11+
- **Workflows**: LangGraph state machines
- **Database**: SurrealDB async driver
- **AI Providers**: Esperanto library (8+ providers: OpenAI, Anthropic, Google, Groq, Ollama, Mistral, DeepSeek, xAI)
- **Job Queue**: Surreal-Commands for async jobs (podcasts)
- **Logging**: Loguru
- **Validation**: Pydantic v2
- **Testing**: Pytest

### Database
- **SurrealDB**: Graph database with built-in embedding storage and vector search
- **Schema Migrations**: Automatic on API startup via AsyncMigrationManager

### Additional Services
- **Content Processing**: content-core library (file/URL extraction)
- **Prompts**: AI-Prompter with Jinja2 templating
- **Podcast Generation**: podcast-creator library
- **Embeddings**: Multi-provider via Esperanto

---

## Architecture Highlights

### 1. Async-First Design
- All database queries, graph invocations, and API calls are async (await)
- SurrealDB async driver with connection pooling
- FastAPI handles concurrent requests efficiently

### 2. LangGraph Workflows
- **source.py**: Content ingestion (extract → embed → save)
- **chat.py**: Conversational agent with message history
- **ask.py**: Search + synthesis (retrieve relevant sources → LLM)
- **transformation.py**: Custom transformations on sources
- All use `provision_langchain_model()` for smart model selection

### 3. Multi-Provider AI
- **Esperanto library**: Unified interface to 8+ AI providers
- **Credential system**: Individual encrypted credential records per provider; models link to credentials for direct config
- **ModelManager**: Factory pattern with fallback logic; uses credential config when available, env vars as fallback
- **Smart selection**: Detects large contexts, prefers long-context models
- **Override support**: Per-request model configuration

### 4. Database Schema
- **Automatic migrations**: AsyncMigrationManager runs on API startup
- **SurrealDB graph model**: Records with relationships and embeddings
- **Vector search**: Built-in semantic search across all content
- **Transactions**: Repo functions handle ACID operations

### 5. Authentication
- **Current**: Simple password middleware (insecure, dev-only)
- **Production**: Replace with OAuth/JWT (see CONFIGURATION.md)

---

## Important Quirks & Gotchas

### API Startup
- **Migrations run automatically** on startup; check logs for errors
- **Must start API before UI**: UI depends on API for all data
- **SurrealDB must be running**: API fails without database connection

### Frontend-Backend Communication
- **Base API URL**: Configured in `.env.local` (default: http://localhost:5055)
- **CORS enabled**: Configured in `api/main.py` (allow all origins in dev)
- **Rate limiting**: Not built-in; add at proxy layer for production

### LangGraph Workflows
- **Blocking operations**: Chat/podcast workflows may take minutes; no timeout
- **State persistence**: Uses SQLite checkpoint storage in `/data/sqlite-db/`
- **Model fallback**: If primary model fails, falls back to cheaper/smaller model

### Podcast Generation
- **Async job queue**: `podcast_service.py` submits jobs but doesn't wait
- **Track status**: Use `/commands/{command_id}` endpoint to poll status
- **TTS failures**: The episode is marked as failed with the provider error; retry via `POST /podcasts/episodes/{id}/retry` (there is no silent-audio fallback)

### Content Processing
- **File extraction**: Uses content-core library; supports 50+ file types
- **URL handling**: Extracts text + metadata from web pages
- **Large files**: Content processing is sync; may block API briefly

---

## Component References

See dedicated CLAUDE.md files for detailed guidance:

- **[frontend/CLAUDE.md](frontend/CLAUDE.md)**: React/Next.js architecture, state management, API integration
- **[api/CLAUDE.md](api/CLAUDE.md)**: FastAPI structure, service pattern, endpoint development
- **[open_notebook/CLAUDE.md](open_notebook/CLAUDE.md)**: Backend core, domain models, LangGraph workflows, AI provisioning
- **[open_notebook/domain/CLAUDE.md](open_notebook/domain/CLAUDE.md)**: Data models, repository pattern, search functions
- **[open_notebook/ai/CLAUDE.md](open_notebook/ai/CLAUDE.md)**: ModelManager, AI provider integration, Esperanto usage
- **[open_notebook/graphs/CLAUDE.md](open_notebook/graphs/CLAUDE.md)**: LangGraph workflow design, state machines
- **[open_notebook/database/CLAUDE.md](open_notebook/database/CLAUDE.md)**: SurrealDB operations, migrations, async patterns

---

## Documentation Map

- **[README.md](README.md)**: Project overview, features, quick start
- **[docs/index.md](docs/index.md)**: Complete user & deployment documentation
- **[CONFIGURATION.md](CONFIGURATION.md)**: Environment variables, model configuration
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: Contribution guidelines
- **[MAINTAINER_GUIDE.md](MAINTAINER_GUIDE.md)**: Release & maintenance procedures

---

## Testing Strategy

- **Unit tests**: `tests/test_domain.py`, `test_models_api.py`
- **Graph tests**: `tests/test_graphs.py` (workflow integration)
- **Utils tests**: `tests/test_utils.py`, `tests/test_chunking.py`, `tests/test_embedding.py`
- **Run all**: `uv run pytest tests/`
- **Coverage**: Check with `pytest --cov`

---

## Common Tasks

### Add a New API Endpoint
1. Create router in `api/routers/feature.py`
2. Create service in `api/feature_service.py`
3. Define schemas in `api/models.py`
4. Register router in `api/main.py`
5. Test via http://localhost:5055/docs

### Add a New LangGraph Workflow
1. Create `open_notebook/graphs/workflow_name.py`
2. Define StateDict and node functions
3. Build graph with `.add_node()` / `.add_edge()`
4. Invoke in service: `graph.ainvoke({"input": ...}, config={"..."})`
5. Test with sample data in `tests/`

### Add Database Migration
1. Create `migrations/XXX_description.surql`
2. Write SurrealQL schema changes
3. Create `migrations/XXX_description_down.surql` (optional rollback)
4. API auto-detects on startup; migration runs if newer than recorded version

### Deploy to Production
1. Review [CONFIGURATION.md](CONFIGURATION.md) for security settings
2. Use `make docker-release` for multi-platform image
3. Push to Docker Hub / GitHub Container Registry
4. Deploy `docker compose --profile multi up`
5. Verify migrations via API logs

### Run Autonomous Development Loop (Ralph Loop)
Run Claude Code, cursor, or opencode in an autonomous, self-correcting development loop:
1. Run the script:
   ```bash
   ./scripts/ralph.sh --tool claude 10
   ```
2. This will auto-initialize the `.ralph/` directory (with `prd.json`, `progress.txt`, `prompt.md`).
3. Customize `.ralph/prd.json` with your desired user stories/tasks, then run the script again.

---

## Support & Community

- **Documentation**: https://open-notebook.ai
- **Discord**: https://discord.gg/37XJPXfz2w
- **Issues**: https://github.com/lfnovo/open-notebook/issues
- **License**: MIT (see LICENSE)
