# Reliability Experience Task Context

## Objective

Implement six approved Deeper Notebook improvements: measurable startup
acceleration; local Recovery Center; runtime trust dashboard; verified,
notify-only updates; Focus mode; and visible local backup/provenance receipts.

## Required reads

- `/Users/Antman/.codex/context.md`
- `docs/superpowers/specs/2026-08-10-deeper-notebook-reliability-experience-design.md`
- `docs/superpowers/plans/2026-08-10-deeper-notebook-reliability-experience.md`

## Invariants

- No telemetry, automatic update installation, model download, mount, scan,
  import, repair, or write to external source vaults.
- Obsidian/Logseq stay `external_read_only`; never expose absolute vault paths,
  source text, credentials, environment values, or raw exception strings.
- Preserve the established update opt-out, legacy compatibility identities, and
  Luminous Folio one-release rollback flag.
- TDD is mandatory: each behavior test must be observed red before product code.
- Keep source/test commits atomic and preserve existing untracked user files.

## Baseline

- Branch: `agent/documentation-reconstruction`.
- HEAD: `2b39fa11` before the reliability-experience docs.
- Installed app root cause was repaired in `3cf2ec69`: `/api/readyz` alias and
  strict wire guard prevent the generic React error screen when a readiness
  route is missing or malformed.
- Observed startup bottleneck: chat GGUF directory scan can wait 20 seconds
  before degrading local chat; current UI/API/DB can otherwise operate.

## First bounded task

Task 1 only: add an atomic, root-bounded startup receipt/model selection cache
and exact tests. Do not alter the model provider, source vault behavior, or
launch optional services. Record a concise result and all verification output
below before returning.

## Task 1 result — 2026-08-10

- Implemented only `desktop/startup_receipts.py`, its focused tests, and the
  app/model-scan test plus wiring in `desktop/app.py`. Receipt writes are
  schema-validated, bounded, atomic/fsynced, best-effort 0600, and root/path
  safe; stages cap at 16 and elapsed values at 24 hours. Matching GGUF size /
  mtime metadata bypasses the existing bounded chooser; stale/out-of-root or
  malformed data fails closed and falls back to the chooser.
- TDD RED occurred before source (`desktop.startup_receipts` missing). GREEN:
  focused receipt/scan 12/12 plus app migration compatibility 29/29. Ruff,
  compileall, and diff-check pass. Exact brief pytest needed `PYTHONPATH=.`
  because root `uv run pytest` currently omits the repository root from
  `sys.path` for desktop tests.
- Open: atomic commit and parent review; later Reliability Experience tasks,
  native/package/release proof, and full regression remain pending. No
  provider, vault, API, update, UI, network, or optional-service behavior was
  changed.

## Task 1 review repair — 2026-08-10

- Added behavior-level RED coverage for launcher-start, validated cache-hit,
  normal/retry `core_ready`, Supervisor failure preservation, and cache-write
  failure. RED was `1 failed, 16 passed` before source edits; the failing case
  exposed a broad best-effort block that skipped `chat_model_scan` recording
  after cache metadata write failure.
- Split cache metadata refresh from scan-outcome receipt recording in
  `desktop/app.py`. GREEN is `46 passed` across receipt/scan and app migration
  tests under `PYTHONPATH=.`; scoped Ruff, compileall, and diff check pass.
- Open: parent review and atomic repair commit; full desktop/native/package/
  release proof remains outside Task 1.

## Task 1 review repair commit — 2026-08-10

- Committed the two-file repair as `93d7c84e` (`fix(desktop): preserve startup
  receipt milestones`). Unrelated untracked work remains unstaged. Parent
  review is the next gate; no additional open implementation items.

## Task 1 second review repair — 2026-08-10

- Strengthened only `desktop/tests/test_app_model_scan_timeout.py`: failed
  Supervisor startup now uses a recording/fail-selected store to prove the
  original error is preserved and no `core_ready` attempt/emission occurs;
  successful startup uses a store failing only on `core_ready` to prove the
  supervisor remains successful and the attempt is observable.
- A reversible mutation removing the existing core-ready calls produced RED
  (3 failed, 9 deselected) for the intended missing milestone; restoring the
  committed source produced GREEN: 47 Task 1/app-migration tests. Ruff,
  compileall, and diff check pass. No production source change was needed.

## Task 1 commit — 2026-08-10

- Commit `eaa82c21` (`feat(desktop): record startup receipts and cache model
  selection`) contains only the four approved Task 1 files. The ignored report
  records the commit and verification; parent review is the next gate.

## Task 2 runtime snapshot — 2026-08-10

- Added a provider-injected `GET /api/runtime/snapshot` projection for the
  forthcoming system dashboard and Recovery Center. It uses existing read
  APIs only: readiness, startup receipts, locally cached update state,
  aggregate vault/knowledge summaries, and bounded auto-export metadata.
  It never triggers a scan, mount, import, repair, model operation, update
  check, or vault/source write.
- The response is a finite, redacted contract: allowlisted state/reason
  codes, counts, and ages only; no paths, source text/fingerprints, secrets,
  or raw exceptions. Malformed providers degrade to `unknown`; vault summary
  iteration is count-capped to prevent a response-model failure.
- TDD RED: snapshot imports were absent, then an oversized vault sequence
  produced the expected count-validation failure. GREEN: focused snapshot
  suite 8 passed; scoped Ruff and diff-check passed. Parent rebrand audit and
  independent review remain next.

## Task 2 rebrand anchor refresh — 2026-08-10

- The runtime-router import shifted the four existing `api/main.py` legacy
  selectors to lines 744 (`/api/onp` and `/onp/`), 1216, and 1251. Updated only
  those exact allowlist anchors plus the pinned selector and legacy-route
  coverage digests; the existing historic package-identity documentation
  entry remains migration documentation.
- Exact selector inventory passed 1 test; full product-identity suite passed
  141 tests; `scripts/rebrand_audit.py --check` exited 0 with unexpected/stale
  counts 0/0; scoped Ruff and diff-check passed. No runtime snapshot source or
  tests were changed by this audit repair. Open: parent review/package gates.

## Task 2 bounded-container repair — 2026-08-10

- Review repair stayed within `api/runtime_snapshot.py`,
  `api/routers/runtime.py`, and `tests/test_runtime_snapshot.py`. Added RED
  coverage for throwing mappings/sequences plus lazy oversized startup and
  vault summaries (`3 failed, 8 passed` before source edits).
- GREEN: normalizers fail closed to allowlisted unknown states; startup
  projection consumes at most 16 entries without requesting a 17th; the
  authenticated router projects at most 256 vault mounts without materializing
  the full iterable. Focused snapshot suite is 11/11; scoped Ruff, compileall,
  and diff-check pass.
- No scan/mount/import/repair/update-check/model-operation/vault-write behavior
  was introduced. Unrelated dirty/untracked state remains preserved. Atomic
  repair commit: `fe48d18d` (`fix(api): bound runtime snapshot projections`).

## Task 3 verified notify-only update notices — 2026-08-10

- Added finite `verified`/`unverified`/`unknown` update status and bounded
  canonical release-page projection. Verification requires a strict version,
  canonical `Antman1526/Deeper-Notebook` release URL, named macOS DMG asset,
  and checksum asset; unverified/unknown states expose no public URL.
- Settings and shell banner remain notify-only: verified candidates link only
  to the public release page and are marked manual; unverified, unknown,
  disabled, and failed checks render safe plain language with no download or
  install control. Existing opt-out, 6-hour cache, and sole GitHub check were
  preserved; no installer, asset download, checksum download, telemetry, or
  new network path was introduced.
- TDD RED: backend 8 failed/25 passed and frontend 6 failed/5 passed before
  source edits. GREEN: backend focused suite 33 passed; focused Vitest 2 files
  and 11 tests passed. Scoped Ruff, ESLint, frontend `tsc --noEmit`, and diff
  check passed.
- Atomic commit: `2f8e242a` (`feat(updates): distinguish verified release
  notices`) contains only the nine Task 3 source/test files. Hosted/package/
  live GitHub/clean-machine proof remain outside this task. Unrelated
  dirty/untracked files were preserved and unstaged.

## Task 3 review repair — 2026-08-10

- Added RED coverage for missing `tag_name` despite a valid display name,
  numeric release URLs, downgraded verified-cache URL retention, and
  unverified `published_at` canaries (`4 failed, 33 passed` before source).
- Fixed only `api/updates_service.py` and `tests/test_updates_service.py`:
  verification now requires the actual strict tag and tag-bound public URL;
  non-verified states clear both URL fields; `published_at` is projected only
  for verified timezone-aware ISO metadata. Opt-out/TTL/sole GitHub read and
  all frontend behavior remain unchanged.
- GREEN: backend focused 37 passed; frontend focused 2 files/11 tests;
  Ruff, scoped ESLint, frontend `tsc --noEmit`, and diff-check passed. Atomic
  repair commit: `320dc3c4` (`fix(updates): tighten release verification`).
  Unrelated dirty/untracked files remain preserved and unstaged.

## Task 4 runtime dashboard and Recovery Center — 2026-08-10

- Added a fail-closed typed client and one shared TanStack Query key for the
  read-only runtime snapshot. Horizon and Settings use the same redacted
  RuntimeStatusPanel; malformed/error data renders bounded `unknown` state.
- The default ErrorBoundary now uses RecoveryCenter with user-triggered Retry,
  Reload, diagnostic-code copy, and conditional existing `window.DN.relaunch`.
  It does not render or copy raw exceptions, paths, URLs, stacks, or tokens;
  custom fallback props remain unchanged.
- Final evidence: focused frontend Vitest 7 files/29 tests, scoped ESLint,
  frontend TypeScript, Next build, and `git diff --check` passed. The Horizon
  mocked browser visual path first REDed because its fixture only mocked the
  retired `/api/readyz`; adding its safe `/api/runtime/snapshot` fixture and
  refreshing the single inspected Horizon baseline produced GREEN 1/1.
- Open: native pywebview relaunch, packaged-app, broader responsive/browser,
  full frontend regression, and release proof remain out of scope.
- Atomic commit: `32539513` (`feat(ui): add runtime dashboard and recovery center`).

## Task 4 runtime decoder repair — 2026-08-10

- Reviewer finding reproduced RED in the frontend-local runtime API test:
  accepted payloads retained hostile top/nested extra fields, duplicate reasons,
  and unbounded reason/startup arrays (4 failed/7).
- `runtime.ts` now validates finite repeated fields, rejects malformed,
  oversized, or unknown entries to `UNKNOWN_RUNTIME_SNAPSHOT`, deduplicates
  allowlisted reasons, and returns a literal allowlist projection with no
  passthrough extras. GREEN: runtime 7/7 and Task 4 focused 7 files/34 tests;
  scoped ESLint, frontend TypeScript, Next build, and diff check passed.
- No query, panel, Recovery Center, API, launcher, or browser baseline change.
  Native/package/full-regression/release gates remain open.
- Atomic repair commit: `1ad738b3` (`fix(runtime): sanitize snapshot decoder`).

## Task 5 reversible Focus mode — 2026-08-10

- Added an allowlisted persisted `focusMode: boolean` with default false and
  malformed-value fail-closed behavior while preserving wallpaper, motion, and
  transparency fields. The pre-hydration theme script mirrors the value to
  `data-dn-focus-mode` without changing theme IDs.
- Added the keyboard-accessible FocusModeControl to both Luminous and legacy
  AppShell branches plus Settings display preferences. `Ctrl+Shift+F / ⌘⇧F`
  toggles only outside editable fields; Escape exits only active mode; the
  compact active exit control stays focusable. CSS hides only shell chrome and
  grows the editorial canvas; route content, dialogs, audio, status/query,
  navigation authority, and external-source authority remain mounted/unchanged.
- TDD RED was observed before source: missing FocusModeControl, store setter,
  persisted field, root prehydration, and shell/settings controls failed. GREEN
  focused Vitest is 6 files/32 tests; combined Task4 regression plus Task5 is
  13 files/66 tests. Rollback env (`NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`) is 3
  files/11 tests. Scoped ESLint (0 errors), frontend TypeScript, Next build
  (23 routes), responsive mocked Luminous parity (4 viewport tests), and diff
  check pass.
- Report: `.superpowers/sdd/reliability-task-5-report.md`. Open proof remains
  native pywebview, packaged/signed app, clean-machine, full regression, and
  release acceptance. Parent review/atomic commit remains next; unrelated
  dirty/untracked paths and root `node_modules` stay preserved.

## Task 5 review repair — 2026-08-11

- Replaced active Focus `display:none` chrome removal with compact,
  focus-reveal rails for Luminous navigator/context/dock and the real legacy
  `.app-sidebar` plus rollback aside; mobile active rails stay mounted and
  expand on focus/toggle. No route landmark is `aria-hidden` or removed.
- Added a minimal global CommandPalette Workspace item using the existing
  `toggleFocusMode` store action, with RED coverage for command execution,
  Luminous/legacy keyboard paths, and active browser behavior. New browser
  proof activates Focus at 320/768/1024/1440 and checks exit, route content,
  nav/utility focus, and no console errors.
- GREEN: focused Vitest 5 files/53 tests; browser 4/4; scoped ESLint,
  frontend `tsc --noEmit`, Next build (23 routes), and `git diff --check` pass.
  The tracked Playwright marker was restored. Open: native/package/clean
  machine/full regression/release proof. Repair commit remains next.

## Task 5 second review repair — 2026-08-11

- RED first: CSS contracts failed for the missing mobile legacy compact rail
  and missing higher-specificity Research Core Focus override; active Research
  Core browser lost its Notebook index; rollback browser measured the real
  `.app-sidebar` at 64px at both 320/768px.
- GREEN fix is limited to `shell.css` plus
  `shell-css.test.ts`, `focus-mode-rollback.spec.ts`, and
  `focus-mode-research-core.spec.ts`: mobile legacy `.app-sidebar`/aside is a
  focus-reveal rail with a flexible main, and Research Core Focus repeats the
  `:has()` specificity to keep the navigator mounted.
- Verification: focused Vitest 6 files/55 tests; active Focus browser 4/4;
  Research Core 1/1; rollback flag 2/2 at 320/768; scoped ESLint, frontend
  TypeScript, Next build (23 routes), and diff check passed. Playwright marker
  restored. Atomic repair commit remains next.
- Open proof: native pywebview, packaged/signed app, clean-machine, full
  regression, and release acceptance remain unclaimed.

## Task 6 local backup and provenance receipts — 2026-08-11

- RED first: backend Task6 additions failed 4/4 on missing bounded backup
  freshness/provenance fields; frontend panel suite failed at import because
  `BackupProvenancePanel` was absent.
- GREEN scope adds only read-only runtime projection and presentation:
  bounded auto-export valid/stale/unknown freshness, age, timestamp, size,
  explicit unknown integrity, aggregate mount/external-read-only counts, and
  fingerprint availability without hashes. Settings composes a semantic panel
  with no operation controls; malformed/legacy client payloads fail closed.
- Evidence: runtime snapshot 15/15; runtime + vault read-only regression 41;
  frontend focused 6 files/34 tests; mocked Settings proof 1/1 at 1280x800;
  Ruff, scoped ESLint, frontend TypeScript, Next build (23 routes), and diff
  check passed. Playwright marker restored. Report:
  `.superpowers/sdd/reliability-task-6-report.md`.
- Open proof: native/package/clean-machine/full regression, screenshot
  baseline review, and release acceptance. Atomic Task6 commit remains next.

## Task 6 review repair — 2026-08-11

- RED reproduced 2/2: unrelated files in an existing backup directory were
  reported ready, and `{}`/`root_path`-only provenance entries counted mounts.
- GREEN repair bounds backup readiness to a recognized auto-export file and
  provenance counts to recognized `status`/`write_policy` aggregate fields;
  malformed inputs now return unknown with zero counts and no raw details.
- Theme visual fixture gained only the deterministic read-only runtime route;
  the inspected archive-paper Settings capture was coherent and only its
  approved baseline was refreshed. Backend 43, frontend 34, Settings e2e 1,
  archive-paper visual 1, Ruff/ESLint/tsc/build/diff all pass. Playwright
  marker restored; native/package/clean-machine/full-regression/release proof
  remains open.
- Repair commit remains pending for parent reconciliation.

## Task 7 integrated proof — 2026-08-11

- Source evidence: backend 3946 passed/1 skipped/11 warnings; desktop
  `.build-venv` 806 passed/2 skipped/4 warnings (the shared `.venv` collection
  attempt lacks optional `mem0`); frontend 202 files/1452 tests, scoped lint,
  TypeScript, Next build (23 routes), and diff-check passed.
- Browser evidence: default mocked command 47 passed/2 rollback-configured
  failures/1 skipped; functional subset 32 passed/1 skipped; visual suite
  17/17; rollback flag (`NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`) 2/2. Exactly 14
  reviewed visual PNGs were committed as `2a2eefc0`.
- Native, bundled, and installed smoke passed with task-owned roots and
  unchanged external fixture SHA. DMG/package content, deep strict codesign,
  hdiutil verification, recoverable app swap, readiness markers, and ports
  cleanup were evidenced; task roots were removed and Playwright marker
  restored.
- Open proof: ad-hoc `spctl` rejection means no notarization/clean-machine or
  manual GUI claim. Packaged/installed snapshots showed startup unknown/empty
  while valid on-disk receipts existed, an unresolved early-snapshot timing or
  projection concern. Full receipt: `.superpowers/sdd/reliability-task-7-report.md`.

## Task 8 startup receipt projection parity — 2026-08-11

- Root cause reproduced in the prior installed bundle: task-owned data root and
  on-disk receipt were correct (`launcher_start`, `chat_model_scan`,
  `core_ready`), but the frozen API could not import `desktop.startup_receipts`
  and `_default_startup_receipts` returned `None`. This was a packaged import
  path mismatch, not root selection, cache, or read timing.
- RED added a frozen-import regression; GREEN adds a bounded direct JSON
  fallback in `api/runtime_snapshot.py` with schema/stage limits and existing
  redaction. Focused runtime suite 19/19, Ruff, and diff-check pass.
- Rebuilt package and DMG verified (package contents, deep codesign,
  `hdiutil verify`); isolated packaged and installed smoke both projected a
  ready startup with the same three receipt stages and no absolute paths.
  Installed swap retained `/Applications/Deeper Notebook.backup-task8-20260811-021841.app`.
- Full package precondition's only failure was two stale Task 7 receipt identity
  anchors; wording-only hygiene commit `670b1e2` reconciled them and the
  focused identity audit passed. Task-owned processes, ports, roots, and marker
  state are clean. Detailed receipt: `.superpowers/sdd/reliability-task-8-report.md`.
- Open: ad-hoc signing/notarization, clean-machine, and manual GUI evidence
  remain unclaimed. Task 8 source/test commit is pending final reconciliation.
