# Phase 1 Task 7 report

## Scope

- Added owner-only, atomic, secret-free local-model settings persistence with
  explicit readable-directory validation and restart restoration.
- Extended the desktop config with backwards-compatible strict-local,
  balanced defaults for execution policy, compute profile, memory limit, role
  overrides, and trusted external roots.
- Added redacted `GET`/`PUT` settings endpoints and a pure route-plan endpoint.
  API responses never serialize SurrealDB credentials or the encryption key.
- Exported the selected model directory and execution facts to launcher child
  environments. The resource governor records reservations, permits one MLX
  heavyweight, queues incompatible swaps, and terminates a partially started
  provider if its injected health check fails.
- Strict Local route planning consumes redacted injected candidates only. Its
  transport recorder regression proves no non-loopback request is issued.

## TDD evidence

The initial focused red command failed at collection because
`desktop.launcher.ResourceGovernor` did not exist. The owner-only settings
tests also initially could not import the absent settings module. After the
minimal implementation, focused tests passed.

## Final verification

```sh
uv run --no-sync pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py
# 69 passed; one existing FastAPI/TestClient deprecation warning

uv run --no-sync ruff check deeper_notebook/local_models/settings.py desktop/config.py desktop/launcher.py api/routers/local_models.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py
# all checks passed

git diff --check
# passed
```

## Re-review repair — confirmed sidecar shutdown

### Red

The new restart regression held an old embed child live, made its graceful wait
time out, and made process-group SIGKILL lookup fail. The prior restart path
still dropped its tracker and reservation and attempted a replacement.

### Repair and verification

Restart now requires a successful wait or a confirmed dead poll result after
escalation before it removes the old child or releases its reservation. An
unconfirmed stop returns a failure without starting a replacement, preserving
the existing tracker and tight-limit reservation. The existing successful
embed and heavyweight replacement regressions remain green.

```sh
PYTHONPATH="$PWD" uv run --no-sync pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py
# 78 passed; one existing FastAPI/TestClient deprecation warning

PYTHONPATH="$PWD" uv run --no-sync ruff check deeper_notebook/local_models/settings.py desktop/config.py desktop/launcher.py api/routers/local_models.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py
# all checks passed

git diff --check
# passed
```

## Final review repair — restart reservation replacement

### Red

Two tight-limit restart regressions failed: one for a 1 GiB embed sidecar and
one for the 5 GiB heavyweight MLX chat reservation. `restart_sidecar` removed
the old process but left its governor reservation, so `_try_spawn` rejected
the replacement as over budget.

### Repair and verification

`restart_sidecar` now releases the stopped child's reservation immediately
before delegating replacement to `_try_spawn`. The new spawn acquires its own
reservation and the existing no-child/error paths release it if a healthy
replacement is not produced.

```sh
PYTHONPATH="$PWD" uv run --no-sync pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py
# 77 passed; one existing FastAPI/TestClient deprecation warning

PYTHONPATH="$PWD" uv run --no-sync ruff check deeper_notebook/local_models/settings.py desktop/config.py desktop/launcher.py api/routers/local_models.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py
# all checks passed

git diff --check
# passed
```

## Boundaries

- No provider, model library, model source root, manifest, or external brain
  was mounted, scanned, or mutated.
- The pre-existing worktree-local `node_modules/` remains untracked and is not
  part of this task's commit.

## 2026-08-02 — Research Core Guided Tips

### Delivered scope

- Added the approved local-only, versioned eleven-section Guided Tips catalog
  and the `dn-guided-tips-v1` Zustand persistence store.
- Added a non-modal anchored provider that clamps its fixed callout to a 16px
  viewport inset, updates on resize and capture-phase scroll, fails closed for
  missing anchors, and hides while modal or explicit suspension UI is present.
- Added one provider mount, stable sidebar anchors, and independent Settings
  controls that toggle enablement or clear only completion state.

### Verification

```sh
cd frontend && npm test -- src/lib/guided-tips/catalog.test.ts src/lib/stores/guided-tips-store.test.ts src/components/guided-tips/GuidedTipsProvider.test.tsx
# 3 files passed; 10 tests passed

cd frontend && npx eslint src/lib/guided-tips src/lib/stores/guided-tips-store.ts src/components/guided-tips src/components/layout/AppShell.tsx src/components/layout/AppSidebar.tsx 'src/app/(dashboard)/settings/page.tsx'
# passed
```

The plan's literal `npm run lint -- ...` invocation also runs its existing
repository-wide `eslint src/` prefix and remains blocked by ten unrelated
Podcast/Vault `no-explicit-any` errors. No unrelated files were changed.

## Review repair

### Red

- The first implementation left `ResourceGovernor` as a helper that was never
  consulted by the real `Supervisor._try_spawn` sidecar path.
- Settings PUT accepted `true` as a memory limit because Python treats bool as
  an int, and could serialize control-containing override/root values.
- The Strict Local recorder was injected into app state but never called.

### Repair and verification

- `_try_spawn` now reserves a measured sidecar budget before launch, queues a
  conflicting heavyweight MLX chat start, releases no-op reservations, and
  removes both a partial child and its reservation after spawn or post-spawn
  health failure. Focused integration regressions exercise this actual path.
- Settings validation rejects bool limits and control-containing strings before
  the atomic write. TOML strings use JSON-compatible escaping; invalid PUTs
  leave the existing config text unchanged and parseable.
- Route planning invokes an injected recorder only at the fixed loopback
  planning endpoint. The Strict Local regression now asserts the recorder saw
  the loopback request and no non-loopback request.

```sh
uv run --no-sync pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py
# 75 passed; one existing FastAPI/TestClient deprecation warning

uv run --no-sync ruff check deeper_notebook/local_models/settings.py desktop/config.py desktop/launcher.py api/routers/local_models.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py
# all checks passed

git diff --check
# passed
```
