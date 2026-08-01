# Research Core Lab — Task 9 Verification Record

Recorded: 2026-08-01T10:10:38Z (UTC)

Baseline commit: `bc8646461f9bc97d90efc675ee3442e49bac071f`
Worktree: `codex/research-core-lab-phase-1`

## Scope and safety boundary

- Registered stable `knowledge.mode.read`, `.write`, `.ask`, `.search`,
  `.graph`, and `.podcast` commands as app-owned workspace actions. None
  declares `external-write`; a disabled command is never substituted with a
  different mode.
- The verifier creates a fresh, sentinel-owned temporary fixture only. Its
  proof contains aggregate hashes rather than paths, source text, model paths,
  credentials, or provider responses.
- No model-library, external vault, watcher, provider, or native application
  state was modified. The worktree-local untracked `node_modules/` directory
  remains excluded from this task's commit.

## Environment

- Python `3.12.13`; Ruff `0.14.13`
- Node `v24.17.0`; npm `11.13.0`; Next.js `16.2.12`; Playwright CLI `1.62.1`
- Current native command collection: `npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime --list` collected **4 tests**.

## Recorded artifact hashes

```text
1276c176a72b1d0df6626bc103336bb6e57d4c70df77ab95d8137e0c00627e14  frontend/e2e/research-core-lab.spec.ts
6c005557ba7b1def22844831f172c0529a3008dd5f4f01e857de89ba9123b131  scripts/verify_research_core_lab.py
72c7267c38317a8e594b555c0a850c097acdbb9e851281392caddcb19caab3fb  tests/test_verify_research_core_lab.py
eed20f040cea2aa0772028ca791dc006294b7cb23e797571274a00ec5d67388e  frontend/playwright.config.ts
```

## Passing gates

```sh
PYTHONPATH="$PWD" .venv/bin/python -m pytest -q \
  tests/test_knowledge_workspace_persistence.py \
  tests/test_knowledge_workspace_api.py \
  tests/test_local_model_planner.py \
  tests/test_local_model_settings.py \
  tests/test_research_core_local_models_api.py \
  tests/test_verify_research_core_lab.py \
  desktop/tests/test_config.py desktop/tests/test_launcher.py
# 135 passed, 8 existing dependency warnings

(cd frontend && npx vitest run src/components/vault src/components/local-models \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  src/lib/commands/command-registry.test.ts \
  src/components/common/CommandPalette.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
# 41 files, 401 tests passed; TypeScript passed

.venv/bin/ruff check deeper_notebook/local_models deeper_notebook/workspace \
  api/routers/local_models.py desktop/config.py desktop/launcher.py \
  tests/test_local_model_planner.py tests/test_local_model_settings.py \
  tests/test_research_core_local_models_api.py tests/test_verify_research_core_lab.py \
  scripts/verify_research_core_lab.py
# All checks passed

PYTHONPATH="$PWD" .venv/bin/python -m pytest -q tests/test_verify_research_core_lab.py
# 4 passed

PYTHONPATH="$PWD" .venv/bin/python scripts/verify_research_core_lab.py --native-url http://localhost:65060
# exit 2: synthetic checks pass; report remains blocked without a caller-launched native runtime,
# Playwright native proof, and a production-build result.

git diff --check
# passed
```

## Remaining native-only and production-build gates

`npm run build` and the exact Playwright execution below could not start the
web server. Next.js Turbopack rejects the existing worktree
`frontend/node_modules` symlink because it points outside the filesystem root.
The error happens before application compilation or browser test execution.

```sh
(cd frontend && npm run build)
(cd frontend && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime)
# failed before collection/execution server startup:
# TurbopackInternalError: Symlink [project]/node_modules is invalid,
# it points out of the filesystem root
```

The configuration now explicitly includes the mandated Task 9 file in the
`native-runtime` project, so the command collects four tests when the build
surface is repaired. A persistent native app on `http://localhost:65060` was
not supplied for this run; the verifier records that separately and does not
claim mocked browser coverage as native-app proof.

## Review repair — 2026-08-01T10:23:39Z

The browser spec now asserts every mode through both the launcher and command
palette, including compatible Read/Write activation, selected-tab mode labels,
a split containing Write and Search modes, keyboard open/close of both narrow
drawers, and returned Ask/Search route-plan reasons. External Write remains
disabled before the app-owned Overlay draft is created.

The verifier now records separate synthetic local-library before/after
fingerprints, an instrumented Strict Local transport boundary with zero calls,
and an observable one-heavyweight reservation/queue result. The transport
recorder is a synthetic planner-contract fixture only; it is not production
provider, native-runtime, or packaged-app request evidence. With
`--run-focused-gates`, it records command, exit status, error class, and an
output digest without persisting command output.

```sh
PYTHONPATH="$PWD" .venv/bin/python -m pytest -q tests/test_verify_research_core_lab.py
# 5 passed

PYTHONPATH="$PWD" .venv/bin/python scripts/verify_research_core_lab.py \
  --native-url http://localhost:65060 --fixture-root <owned-temp>/fixture \
  --output <owned-temp>/proof.json --run-focused-gates
# exit 2 (honest aggregate block)
# synthetic migration/Strict Local/heavyweight/local-library checks: passed
# focused tests: passed, exit 0
# focused build: failed, exit 1, error nonzero_exit, output digest recorded
# native runtime and native Playwright: blocked

(cd frontend && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime --list)
# 4 tests collected
```

The exact execution remains blocked before browser tests start by the same
Turbopack external-`node_modules` symlink error. This repair does not claim
native-runtime or packaged-app proof.

## Production-build repair — 2026-08-01

The worktree-local `frontend/node_modules` symlink intentionally points to
the repository checkout's existing dependency directory. `next.config.ts`
derives `turbopack.root` from the real `node_modules` target: the target's
`frontend` parent and then its checkout parent. This yields the right checkout
for both a nested worktree and a normal, non-symlink checkout without changing
the symlink or its target. If dependencies are absent, it falls back only to
the direct parent of the configured frontend directory.

The setup-wizard completion key is intentionally module-local: Next.js pages
may not export arbitrary named values. Its focused test retains the same
literal assertion value, while the wizard's localStorage, cookie, and routing
behavior are unchanged.

```sh
(cd frontend && npm run build)
# passed: Next.js 16.2.12 Turbopack production build

(cd frontend && npx next build --webpack)
# completed with exit 0 and Next page-module validation; emitted a nonfatal
# standalone trace-copy ENOENT for page_client-reference-manifest.js. This is
# not a clean standalone trace/package proof.

(cd frontend && npx vitest run 'src/app/(dashboard)/setup-wizard/page.test.tsx' \
  --pool=forks --maxWorkers=1)
# 1 file, 9 tests passed

(cd frontend && npx vitest run next.config.test.ts --pool=forks --maxWorkers=1)
# 1 file, 3 tests passed: current worktree, nested worktree, normal checkout

(cd frontend && npx tsc --noEmit)
# passed
```

The native-runtime and packaged-app gates remain separate and are not claimed
by this frontend build repair.

## Worktree standalone-start repair — 2026-08-01

The portable checkout root is now explicit for both `turbopack.root` and
`outputFileTracingRoot`. In a nested worktree, Next writes the standalone
server beneath `.next/standalone/<path-from-tracing-root>/server.js`. The
start helper reads its own `required-server-files.json`, verifies that its
`appDir` is the current frontend, derives that traced server path safely, and
uses it only when it exists. The direct nested and packaged flattened server
paths remain supported.

```sh
(cd frontend && npx vitest run start-server-utils.test.ts --pool=forks --maxWorkers=1)
# 1 file, 3 tests passed, including a nested tracing-root server

(cd frontend && npm run build)
# passed: Next.js 16.2.12 Turbopack production build

(cd frontend && PORT=8519 npm run start)
# resolved this worktree's .next/standalone/.worktrees/.../frontend/server.js
# server reported Ready; GET http://127.0.0.1:8519/ returned HTTP 307
```

The temporary local smoke server was stopped after the response. This proves
the worktree-local standalone startup path only; it does not prove a native
app, Playwright execution, or packaged release.

## Native browser persistence repair — 2026-08-01

The exact browser project now executes successfully. The strict fixture
exercises the supported Overlay save path, then proves the saved app-owned
content and every V2 research mode survive both Current Session reload and a
named-workspace restore. The named target contract was extended additively for
content-free `ask` and `podcast` targets; Search and Graph retain their stable
target fields. No document ID is synthesized for non-document modes.

```sh
(cd frontend && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime)
# 4 passed

(cd frontend && npx vitest run src/components/vault/KnowledgeExplorer.test.tsx \
  --pool=forks --maxWorkers=1)
# 1 file, 48 tests passed

(cd frontend && npx tsc --noEmit)
# passed

uv run pytest tests/test_knowledge_navigation_contracts.py \
  tests/test_knowledge_navigation_service.py -q
# 47 passed

git diff --check
# passed
```

The `native-runtime` Playwright project is a browser/runtime acceptance
surface with synthetic API fixtures; it is not evidence of a packaged desktop
launch or a user-owned persistent native application. External vault writes,
provider execution, model-library mutation, and credentials remain out of
scope.

## P1 named-target contract repair — 2026-08-01

The named-workspace contract now accepts a document target in explicit
`read` or `write` mode (write requires source view), preserves an intentionally
empty Search query, and carries rootless Graph, Ask, and Podcast targets
without substituting document identities. Ask `thread_id` and Podcast
`production_id` are bounded opaque navigation identifiers, rejecting paths,
controls, and raw content. Restored content-free modes are marked app-owned,
not external read-only.

The strict browser fixture validates the named snapshot's target/mode pair
before storing it and returns `422` for invalid combinations, including unsafe
opaque IDs. It therefore cannot make the browser proof pass by accepting an
invalid client payload.

```sh
uv run pytest tests/test_knowledge_navigation_contracts.py \
  tests/test_knowledge_navigation_service.py -q
# 48 passed

(cd frontend && npx vitest run src/components/vault/KnowledgeExplorer.test.tsx \
  src/lib/api/knowledge-navigation.test.ts --pool=forks --maxWorkers=1 \
  && npx tsc --noEmit)
# 62 tests passed; TypeScript passed

(cd frontend && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime)
# 4 passed
```

This remains fixture-backed browser acceptance, not a packaged-app launch or
live persistence-server proof.

## P1 restore and authority hardening — 2026-08-01

Current Session V2 preserves a rootless Graph target as
`root_document_id: null`; neither parsing nor named-workspace restore replaces
that value with an empty string. Ask thread and Podcast production IDs use the
same path-free opaque identifier contract in the backend and browser schema.

Named document Write snapshots are now authorized at the service boundary:
the engine descriptor must report `app_owned` authority before create or
replace reaches the metadata repository. The restore plan also carries each
tab's explicit mode, so an app-owned Read tab remains Read instead of being
silently reclassified as Write. The strict fixture mirrors this authority and
mode validation, including mutable PATCH replacement state.

```sh
uv run pytest tests/test_knowledge_navigation_contracts.py \
  tests/test_knowledge_navigation_service.py \
  tests/test_knowledge_navigation_api.py \
  tests/test_knowledge_workspace_persistence.py -q
# 129 passed

(cd frontend && npx vitest run src/lib/api/knowledge-workspace.test.ts \
  src/lib/api/knowledge-navigation.test.ts \
  src/components/vault/KnowledgeExplorer.test.tsx --pool=forks --maxWorkers=1 \
  && npx tsc --noEmit)
# 100 tests passed; TypeScript passed

(cd frontend && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime)
# 4 passed
```

The browser result is fixture-bound acceptance only: it verifies the client
payload/restore boundary and does not prove a packaged desktop launch or a
live persistence server. The backend pytest result is the direct evidence for
the real contract and service authorization behavior.
