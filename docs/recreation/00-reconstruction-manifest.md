# Open Notebook Plus Reconstruction Manifest

Generated: 2026-06-24
Repository: `https://github.com/Antman1526/open-notebook-Plus`
Primary branch: `desktop-app`
Local source root: `/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`

This manifest is the entry point for the Open Notebook Plus reconstruction packet. The goal is to give another AI system enough exact context to rebuild the application, reason about architectural trade-offs, identify bugs, and continue development without access to hidden conversation history.

## Scope

Open Notebook Plus is both:

1. A downstream desktop fork of `lfnovo/open-notebook`.
2. A local research brain that ingests project documents, web links, PDFs, audio, and video, then supports source-grounded chat, Ask search, podcasts, Evidence Studio artifacts, and Course Packs.

The desktop application runs natively on macOS and Windows. Docker remains useful for development and server deployment, but the Plus desktop pipeline assumes a host-native `.dmg` or Windows package, not a Dockerized app shell.

## Source-of-Truth Documents

Read these files in order:

| Order | File | Reconstruction purpose |
|---:|---|---|
| 1 | `README.md` | Product-level purpose, capabilities, architecture, installation, tests, and local model workflow |
| 2 | `docs/recreation/01-project-overview-architecture.md` | Full system map: frontend, API, database, desktop launcher, sidecars |
| 3 | `docs/recreation/02-environment-setup-dependencies.md` | Exact local setup, Python/Node/runtime dependencies, install steps |
| 4 | `docs/recreation/03-database-schema-data-models.md` | SurrealDB schema, relations, vector indexes, domain model behavior |
| 5 | `docs/recreation/04-backend-api-specifications.md` | FastAPI routes, payloads, response shapes, error behavior |
| 6 | `docs/recreation/05-frontend-architecture-components.md` | Next.js/React app structure, hooks, state, UI components |
| 7 | `docs/recreation/06-authentication-authorization.md` | Password gate, credential encryption, local/cloud permissions |
| 8 | `docs/recreation/07-business-logic-core-algorithms.md` | LangGraph workflows, routing, prompt optimization, Course Pack generation |
| 9 | `docs/recreation/08-integrations-external-services.md` | Providers, web search, MCP, local model sidecars, Hugging Face |
| 10 | `docs/recreation/09-configuration-environment-variables.md` | `.env`, feature flags, local model paths, ports, desktop config |
| 11 | `docs/recreation/10-testing-strategy-test-cases.md` | Unit, integration, frontend, desktop, smoke, and regression coverage |
| 12 | `docs/recreation/11-build-deployment-pipeline.md` | macOS `.dmg`, Windows package, Docker, CI/CD, signing and runtime bundling |
| 13 | `docs/recreation/12-error-handling-logging.md` | Error taxonomy, request IDs, desktop logs, debug paths |
| 14 | `docs/recreation/13-performance-optimization-caching.md` | Vector indexes, caches, streaming, sidecar health, context sizing |
| 15 | `docs/recreation/14-security-implementation.md` | Privacy gate, SSRF protections, encryption, prompt-injection defenses |
| 16 | `docs/recreation/15-file-structure-code-organization.md` | Directory map, module ownership, naming and dependency boundaries |
| 17 | `docs/recreation/project-deep-dive-for-ai-review.md` | Dense AI audit context with real code snippets and Areas for Review |
| 18 | `docs/recreation/technology-inventory.md` | Exhaustive technology, framework, tool, language, and service inventory |

## Current Product Pillars

- **Source-grounded notebooks:** ingest PDFs, documents, links, audio, video, pasted text, and generated notes into a SurrealDB-backed notebook graph.
- **Local-first AI:** run through local GGUF, Ollama, or Apple-Silicon MLX models under `~/Desktop/AI_Models`; cloud providers remain opt-in.
- **Evidence Studio:** generate reports, Course Packs, study guides, quizzes, data tables, mind maps, slide-deck outlines, podcast outlines, and research runs from selected sources.
- **Course Pack:** the richer replacement for the legacy `training_guide` artifact. It turns video/audio/docs/PDF/link bundles into instructor-ready modules with objectives, timed lesson blocks, exercises, handouts, knowledge checks, final assessments, and citations.
- **NotebookLM-class audio:** staged multi-speaker podcast generation with outline review, progress, retry, and cancel.
- **Operational hardening:** request IDs, Prometheus metrics, backup/restore, self-healing database repair, offline routing, privacy gate, MCP tool-output fencing, and upstream-safe fork boundaries.

## Local Model Layout

The default model root is:

```text
/Users/Antman/Desktop/AI_Models
```

Expected sub-layout:

```text
AI_Models/
├── GGUF/                 # llama.cpp chat/embed models, one or more *.gguf files
├── MLX/                  # complete MLX repos with config.json + *.safetensors
├── whisper/ or cache/    # optional local speech-to-text assets
└── piper/ or voices/     # optional local text-to-speech assets
```

Important implementation points:

- `desktop/config.py` resolves the default root to `~/Desktop/AI_Models`.
- `desktop/providers/llamacpp.py` scans GGUF models and launches `python -m llama_cpp.server`.
- `desktop/providers/mlx.py` scans complete MLX repos and launches `python -m mlx_lm.server`.
- `desktop/auto_register/*.py` registers local sidecars as OpenAI-compatible providers so the normal model stack can use them.
- Evidence Studio model routing uses `open_notebook/local_models/inventory.py` and `role_routing.py` to choose local models for source-synthesis tasks when possible.

## Build Artifacts

The macOS artifact is built locally:

```bash
make build-mac
```

Expected output:

```text
dist/Open Notebook Plus.app
dist/Open-Notebook-Plus-mac-arm64.dmg
```

The Windows artifact is built on a Windows runner:

```bash
gh workflow run build-windows.yml --ref desktop-app
```

Expected GitHub Actions artifact:

```text
Open-Notebook-Plus-windows-x64.zip
```

Inside the zip:

```text
Open Notebook Plus/
└── Open Notebook Plus.exe
```

PyInstaller is not a cross-compiler, so a real Windows `.exe` should be produced on Windows rather than from macOS.

## Verification Gates

Before calling the rebuild good:

```bash
uv run pytest tests/ -q --ignore=tests/integration
uv run pytest desktop/tests/ -q
cd frontend && npm test -- --run
cd frontend && npm run lint
npx tsc --noEmit
make build-mac
```

Recommended smoke checks:

- Start SurrealDB, API, worker, and frontend locally.
- Upload a text source, PDF, and link source.
- Confirm extraction-only ingestion succeeds even when no embedding model is configured.
- Generate at least one Evidence Studio Course Pack artifact.
- Confirm source-not-ready and oversized-file paths return structured errors.
- Confirm local model inventory sees `~/Desktop/AI_Models/GGUF` and `~/Desktop/AI_Models/MLX`.
- Run the Playwright visual smoke where available.

## Output Mirrors

The canonical repo docs live in `docs/recreation/`. Local export copies are mirrored to:

```text
/Users/Antman/Desktop/OpenNotebook/
/Users/Antman/Desktop/OpenNotebook/open-notebook-plus-docs/
```

Those Desktop copies are intended for direct import into Open Notebook Plus as source packs.
