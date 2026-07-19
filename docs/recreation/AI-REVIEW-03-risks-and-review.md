# AI Review Brief 3 - Risks, Trade-Offs, And Areas For Review

## Current Pain Points

| Area | Evidence in code | Risk | Recommended direction |
| --- | --- | --- | --- |
| Desktop startup | `desktop/app.py`, `desktop/launcher.py`, provider scans | Cold model folders and optional sidecars can lengthen time-to-window. | Keep all filesystem scans bounded; move non-critical registration and health detail after the window is useful. |
| Large modules | `desktop/launcher.py`, `open_notebook/graphs/chat.py`, notebook and studio router/domain modules | Changes are harder to isolate and test; review context is expensive. | Extract explicit seams around process lifecycle, streaming protocol, persistence, and UI state. |
| Next rewrite patching | `desktop/next_rewrites_patcher.py` | Generated Next output can change across framework upgrades. | Maintain a package-level contract test against the actual standalone build and fail with a clear desktop diagnostic. |
| Two version tracks | `pyproject.toml`, `desktop/__init__.py` | Contributors can incorrectly tag or compare server and desktop releases. | Preserve the split but surface both versions in release documentation and CI artifacts. |
| Provider matrix | Esperanto plus llama.cpp, MLX, Ollama, voice, embeddings, memory | Feature combinations create many startup and health states. | Expand fake OpenAI-compatible sidecar contract tests and test model-routing state transitions without real models. |
| Upstream synchronization | downstream `desktop-app` fork | Blind merges can overwrite Plus-only desktop and local-first behavior. | Maintain an explicit upstream integration branch, conflict map, and post-merge desktop acceptance suite. |

## Decisions And Trade-Offs

### Native desktop instead of Docker for the personal app

The desktop application is intentionally host-native. This provides native
PyWebView behavior, Apple Silicon MLX and Metal access, simpler file intake,
and a personal local-data model. The trade-off is packaging complexity:
runtime binaries, user virtualenv bootstrap, signing, Gatekeeper, and dynamic
port wiring all become product responsibilities.

### SurrealDB as graph and vector store

One database models notebook ownership edges, flexible document records,
semantic vectors, and commands. This reduces synchronization code compared to
separate relational, graph, queue, and vector services. The trade-off is that
schema migration, backup, and corruption recovery must be engineered around
SurrealDB's behavior rather than relying on the operational maturity of a
single-purpose managed database.

### OpenAI-compatible local provider boundary

Standardizing MLX and llama.cpp behind OpenAI-compatible HTTP minimizes
provider-specific logic above the launcher. The trade-off is a process
supervision layer and dynamic endpoint propagation. It is still the right
boundary because the same endpoint can serve app chat, structured generation,
and the memory writer.

### Structured artifacts with Markdown compatibility

Evidence Studio uses typed Pydantic documents, a schema-validation receipt,
and deterministic renderers, but retains a `content`/Markdown compatibility
field for historical artifacts. This lets clients evolve incrementally. The
trade-off is duplicated representations that must be revalidated and rendered
server-side whenever a structured edit is accepted.

## Areas For Review

Ask an AI reviewer to evaluate the following, using the numbered
reconstruction documents and actual source as evidence:

1. Does the launcher have a clean enough ownership model for child processes,
   ports, logs, and retries, or should it be decomposed into a lifecycle state
   machine with explicit interfaces?
2. Are the bounded daemon filesystem scans sufficient, especially when a
   model directory is a sleeping network volume or cloud-managed location?
   What cleanup or observability should accompany a timed-out scan?
3. Can API streaming, frontend stream parsing, and cancellation be expressed
   as a versioned protocol contract with tests that prove server work stops on
   client disconnect?
4. Which modules should be split first to reduce change risk without creating
   abstractions that merely rename existing complexity?
5. Are `reference`, `artifact`, and `refers_to` edge directions and cascade
   deletion semantics consistently verified across notebooks, sources, notes,
   chat sessions, and Evidence Studio artifacts?
6. Does every cloud-bound path cross the same privacy, offline, and secret
   redaction controls? Identify bypasses created by exports, web search,
   provider tests, or MCP tools.
7. Is the current upstream merge process explicit enough to protect Plus-only
   desktop behavior? Propose a repeatable merge-and-acceptance workflow.
8. What product capability would most improve source-grounded work beyond
   NotebookLM while preserving the local-first constraint: better evidence
   tracing, multi-document planning, richer review workflows, or model
   evaluation and routing transparency?
