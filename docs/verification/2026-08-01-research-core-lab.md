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
- Native command collection: `npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime --list` collected **3 tests**.

## Recorded artifact hashes

```text
d4677bfd16b8f683bd430605233992b01202a281c258a1b9a24430d79c8320d7  frontend/e2e/research-core-lab.spec.ts
3a2a67ae13d866fe27b35f64f92ede81081a592e7f92dbbe23efc3b35b0f51de  scripts/verify_research_core_lab.py
ea940e1b85e9bfcfeeba914cccf48fd50b473a828d8894e3f0e28f68636fb82e  tests/test_verify_research_core_lab.py
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
`native-runtime` project, so the command collects three tests when the build
surface is repaired. A persistent native app on `http://localhost:65060` was
not supplied for this run; the verifier records that separately and does not
claim mocked browser coverage as native-app proof.
