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

### Task 7 browser continuation — BLOCKED (2026-08-20)

- At `22cb63a4`, verification-only receipts passed for feature-build contract,
  Source Gallery budget, product identity (`142 passed`), rebrand zero/zero,
  diff-check, and staged/base-range Gitleaks.
- Visual V2 enabled stopped at `28 passed, 12 failed, 241 not run`; the exact
  fixture ledger failure is unexpected `GET /api/features (failed)` at
  `visual-system-matrix.spec.ts:956`. Targeted explicit rollback also failed
  `1/1` on the same request.
- Source Gallery enabled stopped at `9 passed, 3 failed, 23 not run`; source
  cells reported `net::ERR_FAILED` after proxy refusal at
  `localhost:5055/api/config`. The owned partial budget receipt said
  `passed:false`, `viewportCells:0/96` and was removed with its marked temp root.
- Per Sol stop instruction, Source Gallery explicit-off and all package/smoke
  gates were not run. Read-only check confirms user app PID 36562 and sidecar
  PID 36603 remain live and untouched. Open: repair browser fixture/mock gaps,
  rerun full matrices plus rollbacks, then reconsider package work.

### Release-gate repair fallback — 2026-08-20

- Sol-approved Terra fallback ran only after the recorded Luna non-response,
  at base `c1ed4ae7`; it preserved the running app, package artifacts, and all
  unrelated worktree dirt.
- Strict RED: `cd frontend && npm run build` failed because server-rendered
  login imported `useSyncExternalStore` from `src/lib/features.ts`; the exact
  real-Surreal migration-rewind target passed four bodies but raised two
  teardown errors after a failed down migration.
- `967cb266` moved reactive feature hooks to the new client-only
  `features-client.ts`, leaving `features.ts` React-free. `ad90637a` resets
  only a validated disposable `onp_test_<uuid>` database before rebuilding a
  failed-rewind fixture, preserving the test's exact schema/data authority.
- Green: frontend Vitest `243` files / `1809` tests, TypeScript, lint (four
  existing warnings), and production build; real Surreal integration `132
  passed, 10 warnings in 312.71s`; Ruff, format, compileall, diff-check, and
  staged/range Gitleaks passed. `22cb63a4` refreshes only shifted rebrand pins;
  its audit reports `unexpected_active_identity=0` and `stale_allowlist=[]`.
- Open outside this frozen repair: let the user app exit naturally before its
  package/browser/smoke gates; no package, push, installation, or remote action
  occurred.

## 2026-08-20 — today-productization final verification attempt (Terra fallback)

### Authority and preflight

- Authorized fallback scope: the recorded Task 7 Luna non-response and Sol
  approval in the supplied global/task context; source authority remained
  `c1ed4ae7c2d28fd445a5244c0f2fad9105b93241` on
  `codex/today-productization` throughout.
- Preflight index tree was `0155c081af3e973d1ae04166385d88ada427cb16` with
  2,247 tracked files and tracked-inventory SHA-256
  `7849ed065aa3d66c6efb3f4ba7bb4995234e751bc2b300d888d5e6a590de5b08`.
  The pre-existing Task 3 report, generated desktop bytecode, and untracked
  supplied context/plan were preserved.
- The only code-signing identity was local `Deeper Notebook Local`; no notary
  credentials/profile were available. Disk free space was 628 GiB. The
  installed `/Applications` app and its sidecar were already running and were
  never stopped, signalled, or otherwise touched.

### Gate receipts

```sh
cd frontend && npm test -- --run
# 243 files passed; 1,808 tests passed; 160.86s

cd frontend && npx tsc --noEmit
# passed

cd frontend && npm run lint
# exit 0; four existing unused-variable warnings

cd frontend && npm run build
# FAILED: frontend/src/lib/features.ts imports useSyncExternalStore through
# the server-rendered frontend/src/app/(auth)/login/page.tsx route.

make test-integration
# FAILED before collection: .env is absent.

SURREAL_INTEGRATION=1 SURREAL_URL=ws://127.0.0.1:8000/rpc \
  SURREAL_USER=root SURREAL_PASSWORD=root \
  uv run pytest tests/integration/ -v -m integration_surreal
# 132 test bodies passed; 2 teardown errors; 299.03s.
# Both errors are in tests/integration/test_migration_rewind.py schema/default
# data restoration after deliberate down-migration failure.
```

### Stop state and cleanup

- Root directed a stop after the two red source gates. Browser matrices,
  feature/rebrand/diff/security contracts, `make build-mac`, artifact checks,
  package smoke, Windows/GitHub inspection, and notarization were not run.
- `make build-mac` remains fail-closed until the user-installed app and its
  sidecar have exited naturally; its precondition explicitly refuses to run
  while either is present. No package was created or installed.
- Removed only `/private/tmp/deeper-notebook-task7-bbVWeP` after verifying its
  exact `.owned-by-task7` marker, empty contents, zero-byte size, no open
  descriptors, and no matching process. No other temporary root, listener,
  process, user data, `/Applications` content, remote, CI, release, or
  notarization state was changed.

### Open items for Sol

1. Repair and re-review the Next client/server boundary before any package
   attempt.
2. Diagnose the migration-rewind teardown restoration errors in the disposable
   real-Surreal suite.
3. After those gates are green and the user app is no longer running, rerun
   the complete Task 7 brief from final gates through isolated smoke.

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

## 2026-08-20 — Browser fixture alignment (Terra fallback)

Commit `3d754a5e` (`test(ui): align runtime feature browser fixtures`) changes
only browser fixtures and their contracts:

- `frontend/e2e/fixtures/visual-system.ts`
- `frontend/e2e/fixtures/study-workbench.ts`
- `frontend/e2e/visual-system-matrix.spec.ts`
- `frontend/e2e/source-gallery.spec.ts`

The browser fixture now provides the exact six-key `/api/features` backend
schema on the same origin, with explicit dashboard route authority. It also
models the optional backend config field and records the exact
`GET /api/study/exams/attempts` empty summary-list response under the
independent Study ledger. The rollback ledger now retains the observed exact
local-model-health request rather than excluding it.

### RED / GREEN receipts

- Focused RED: two deterministic failures — missing `sourceUploadMaxBytes:
  null` in `/api/config`, and unhandled `GET /api/study/exams/attempts`.
- Focused GREEN: both contracts passed (`2/2`, 18.5s).
- Full Visual V2 enabled: `282 passed`, `1 skipped` (7.0m), including all
  twelve repaired `/study` theme/viewport cells.
- Dedicated Visual V2 rollback: `1 passed` (20.9s), proving the legacy
  login, root, and setup shells with V2 off.
- Full Source Gallery enabled: `36 passed`, `1 skipped` (1.5m). Its runtime
  receipt passed all `96/96` cells, `maximumCls=0.006388483705218826` against
  `0.05`, `252` exact delegated calls, and zero unexpected/external requests.
- Full Source Gallery explicit off: `12 passed`, `25` intended skips (35.4s).
  Its receipt passed all `20/20` rollback viewport cells with zero visual
  requests/mutations and zero unexpected/external requests.

### Static / security gates

```sh
cd frontend && npx tsc --noEmit
# passed

cd frontend && npx eslint e2e/fixtures/visual-system.ts e2e/fixtures/study-workbench.ts e2e/visual-system-matrix.spec.ts e2e/source-gallery.spec.ts
# passed

git diff --check
# passed

gitleaks protect --staged --redact
# no leaks found

gitleaks git --redact --log-opts='HEAD^..HEAD'
# 1 commit scanned; no leaks found
```

### Residual observation

The Source Gallery Next test server still logs refused server-side rewrite
attempts to `localhost:5055/api/config`. The browser-side same-origin config
contract returns the exact schema and every browser ledger is clean, so this
is not hidden by a wildcard or a passed-through browser request. No product
or Next rewrite behavior was changed in this fixture-only scope; package work
remains outside this repair.

## 2026-08-20 — cumulative productization review

- Open Code Review selected 34 reviewable files from the 57-file cumulative
  range. Code Review Graph was incrementally rebuilt at `3d754a5e` (1,000
  nodes / 13,483 edges) and classified the core lifecycle/default changes as
  high-impact. Native Sol review then inspected the feature authority, API
  lifespan, source-delete maintenance, source metadata, migration 51, and
  failed-rewind fixture paths directly.
- One Important edge case was confirmed: a later valid partial runtime-feature
  payload replaced the entire accepted override map, so it could erase an
  earlier `sourceVisuals: false` rollback and fall through to the default-on
  build flag. Strict RED was `1 failed / 19 passed` in
  `frontend/src/lib/features.test.ts`.
- Commit `2622ce0e` merges a fully validated bounded partial update into the
  last accepted authority. Unknown or non-boolean payloads are still rejected
  atomically; reset remains explicit. Focused GREEN passed 59/59 tests across
  feature predicates, the mounted source-visual runtime path, and Research Run
  controls; TypeScript and scoped ESLint passed. Staged Gitleaks found no leak.
- No remaining Critical or Important source finding is known. Native package
  proof remains blocked by the running installed app, which was observed
  read-only and never signalled or modified.

## 2026-08-20 — Native macOS package proof RED (Terra fallback)

- Preflight at `6ff9863b` on `codex/today-productization` found the supplied
  untracked task context only, no installed `/Applications/Deeper Notebook.app`
  process, no real `surreal-darwin` sidecar, no prior `dist/`, arm64 hardware,
  and local `Deeper Notebook Local` signing identity. No Developer ID or
  notary profile is available.
- Ran the repository-authoritative command exactly once, without an install
  target or signing override: `make build-mac` (PID/PGID `37889`). It advanced
  through isolated build-venv creation and desktop dependencies into
  `build-mac-test`'s `uv run pytest tests/ -q --ignore=tests/integration` gate,
  then exited before frontend/package stages. `dist/` is absent.
- The detached command runner did not preserve its numeric exit status; the
  failed build is evidenced by its exited PID, absent declared artifacts, and
  current root pytest cache. That cache records twelve failures: one search
  benchmark, the chat/source-chat trim regressions, four source-delete command
  regressions, and five source-delete containment regressions. No retry,
  source repair, artifact smoke, install, process signal, or cleanup was run.
- The build regenerated the pre-existing nine tracked
  `desktop/build/__pycache__/*.cpython-312.pyc` files. They remain unrelated
  dirty state and were not staged, reverted, or otherwise modified by hand.

Open: Sol must decide whether the full backend gate failures are an existing
test-suite/reproducibility defect and authorize a focused diagnostic/repair.
Native package/artifact/smoke proof remains blocked; notarization and Windows
proof also remain outside available authority.

## 2026-08-20 — Native macOS package proof retry (Terra fallback)

- Sol-approved retry ran at exact `d043dd18aa8af1b34247c74a205deea374c836b4`
  on `codex/today-productization`, after a read-only preflight confirmed the
  installed `/Applications/Deeper Notebook.app` and real `surreal-darwin`
  sidecar were absent. Hardware is arm64; the only signing identity remains
  `Deeper Notebook Local`; no Developer ID or notary profile is available.
- The repository-authoritative `make build-mac` ran once, captured through an
  attached session, and exited `0`. Its desktop unit gate was `852 passed, 2
  skipped`; its backend gate first observed two timing failures, then Make's
  built-in documented retry passed `2 passed in 4.70s`. It then completed the
  frontend build, PyInstaller app, local signing, and DMG. Build receipt and
  complete output: `/private/tmp/deeper-notebook-task7-package-rOTVMN/`.
- Independent package evidence passed: `release_manifest.py` reports app
  executable `9252864` bytes / SHA-256
  `911d75c3f425b839e244b9e613195b3313394c8a7e1307676d580e6af0ec439e` and
  DMG `193636060` bytes / SHA-256
  `90ec59291a4bd6fb3e33f295b6134709eafdd6c341af851fc83748238b6a80c8`, both
  at git `d043`. The app's frozen desktop bundle identifier is
  `com.antman1526.` + `open-notebook` + `-plus`, version
  `0.8.114`, arm64 (including bundled Surreal); canonical contents and
  frozen-resource checks passed; `codesign --verify --deep --strict` passed;
  `hdiutil verify` and a read-only mounted-DMG recheck passed. `spctl` exits
  `3` with expected local-signing rejection, so this is not Developer-ID or
  notarization proof.
- Default isolated package smoke passed in an owned `/private/tmp` root:
  `/readyz` reported online DB and applied migrations; `/api/features` returned
  all six default-on booleans including `sourceVisuals: true`; `/login`
  contained the V2 marker and an independent real browser rendered the V2
  workspace. Its exact owned process group and listeners exited cleanly.
- The one permitted fresh-root rollback smoke with
  `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0` did not reach readiness. Its
  isolated `uv pip install` exited `1` after `jsonschema-path==0.4.6` timed out
  downloading from `files.pythonhosted.org` after three retries. No retry or
  source change was made. This is a network/bootstrap limitation of the
  optional runtime rollback proof, not evidence that the rollback path failed.
  Both exact smoke roots and generated Playwright snapshots were moved
  recoverably to Trash after process/listener checks; generated tracked pycs
  were restored. No package was installed and `/Applications` was untouched.

Open: native artifact and default-on package proof are green; rerun only the
isolated rollback smoke when a reliable package-index connection is available.
Developer ID/notarization, Windows, publish, and release remain out of scope.
