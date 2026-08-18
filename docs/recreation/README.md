# Deeper Notebook reconstruction packet

> **Snapshot:** regenerated 2026-08-17 · desktop `0.8.100` · server track `1.8.5`.
> Counts and measurements were read from the tree at `822d6fd3`. Every version, count, and measurement in this packet was read
> from the tree or a tool run at that commit — none are estimates.

This directory is the source-controlled reconstruction packet for the current
Deeper Notebook checkout. It is intentionally written for a second AI system
or senior engineer who has the repository but needs the architecture, exact
contracts, implementation patterns, and known uncertainty areas explained
without relying on tribal knowledge.

## Contents

| Document | Coverage |
|---|---|
| `01-project-overview-architecture.md` | Purpose, system boundaries, stack, and component relationships |
| `02-environment-setup-dependencies.md` | Python/Node/uv setup, pinned runtime inputs, and local launch |
| `03-database-schema-data-models.md` | SurrealDB tables, fields, migrations, relations, and vector indexes |
| `04-backend-api-specifications.md` | FastAPI routers, endpoints, payload contracts, streams, and errors |
| `05-frontend-architecture-components.md` | Next.js routes, React component families, state, and rendering |
| `06-authentication-authorization.md` | Password gate, encrypted credentials, local control plane, and limits |
| `07-business-logic-core-algorithms.md` | Ingestion, retrieval, routing, evidence, podcasts, and artifacts |
| `08-integration-points-external-services.md` | Model providers, search, MCP, Hugging Face, Gmail, and local sidecars |
| `09-configuration-environment-variables.md` | Canonical variables, aliases, defaults, and sanitized deployment config |
| `10-testing-strategy-test-cases.md` | Backend, frontend, desktop, native SurrealDB, and browser gates |
| `11-build-deployment-pipeline.md` | Docker, desktop PyInstaller/DMG, CI, manifests, and rollback |
| `12-error-handling-logging.md` | Exception mapping, request IDs, structured logs, and diagnostics |
| `13-performance-optimization-caching.md` | Pools, HNSW search, token budgets, UI batching, and bottlenecks |
| `14-security-implementation.md` | SSRF controls, encryption, privacy/offline gates, path safety, and threat model |
| `15-file-structure-code-organization.md` | Directory map, ownership, naming, and dependency direction |
| `PROJECT-DEEP-DIVE.md` | Dense walkthrough with real code patterns, data flow, trade-offs, and Areas for Review |
| `TECHNOLOGY-AUDIT.md` | Technology inventory with the specific role of each tool in this codebase |

## How to use this packet

1. Read `01` and `15` to establish architecture and ownership boundaries.
2. Read `02`, `09`, and `11` before attempting a local or packaged build.
3. Read `03`, `04`, and `07` before changing persistence or API behavior.
4. Read `06`, `08`, and `14` before adding a provider, network call, or file path.
5. Read `10` and run the named gates before claiming a change is complete.
6. Use the final **Areas for Review** section in `PROJECT-DEEP-DIVE.md` as the
   starting prompt for refactoring or optimization analysis.

## Snapshot and limitations

The packet is generated from source and configuration, not from secrets or
private model files. Secret values are intentionally omitted. Version ranges
and generated lockfiles are authoritative over prose when they differ. The
native desktop artifact is macOS-arm64-specific unless a separate Windows or
Intel build is produced on its native CI host. Compatibility aliases and the
historical bundle identifier are deliberate migration contracts and must not
be removed as a cosmetic rename.
