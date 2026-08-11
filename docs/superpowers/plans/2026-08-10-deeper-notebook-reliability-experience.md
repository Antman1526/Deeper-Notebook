# Deeper Notebook Reliability Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver measured startup acceleration, Recovery Center, runtime trust dashboard, verified update UX, Focus mode, and local backup/provenance visibility.

**Architecture:** A narrow, read-only runtime snapshot composes existing readiness, desktop launch, update, backup, and knowledge evidence. Desktop writes only an allowlisted local startup/model-cache receipt. The frontend renders the snapshot in existing Luminous Folio surfaces and uses only explicit existing recovery actions.

**Tech Stack:** Python 3.12/FastAPI/Pydantic/SurrealDB, desktop PyWebView launcher, Next.js 16/React/TanStack Query/Zustand/Tailwind, Vitest/pytest/Playwright.

## Global Constraints

- Preserve local-first operation; no telemetry, automatic update install, cloud model call, mount, scan, import, repair, or source-vault write.
- Preserve external Obsidian/Logseq `external_read_only` authority and source-hash behavior.
- Keep existing update opt-out and legacy compatibility identifiers.
- New user-facing states must use accessible labels, keyboard interaction, reduced-motion behavior, and no raw paths/tokens/exceptions.
- Every production change starts with a focused failing test and lands in an atomic commit.

---

## File map

- `desktop/startup_receipts.py`: bounded, atomic startup timing/model-cache store.
- `desktop/app.py`: records core-ready milestones and consumes only validated cached model choice.
- `api/runtime_snapshot.py`: builds safe read-only snapshot from established services.
- `api/routers/runtime.py`: exposes the snapshot route under existing API auth.
- `api/updates_service.py`: validates canonical repository/version/artifact/checksum eligibility.
- `frontend/src/lib/api/runtime.ts`, `frontend/src/lib/hooks/use-runtime-snapshot.ts`: typed client/query boundary.
- `frontend/src/components/common/RecoveryCenter.tsx`: stable production fallback and explicit recovery actions.
- `frontend/src/components/deeper-notebook/runtime/*`: presentation-only status/backup/provenance components.
- `frontend/src/lib/stores/display-preferences-store.ts`, `frontend/src/components/deeper-notebook/shell/*`: Focus mode state, shortcut, and visual presentation.

## Task list

### Task 1: Establish startup measurements and safe model-cache primitives

**Files:**
- Create: `desktop/startup_receipts.py`
- Create: `desktop/tests/test_startup_receipts.py`
- Modify: `desktop/app.py`
- Modify: `desktop/tests/test_app_model_scan_timeout.py`

**Interfaces:**
- Produces `StartupReceiptStore.record(stage: str, elapsed_ms: int)` and
  `StartupReceiptStore.load_chat_model(root: Path) -> Path | None`.
- Consumes only `Config.model_dir` and the existing chat model chooser.

- [ ] Write failing tests for atomic receipt parsing, root-bounded model paths,
  matching metadata cache hits, stale metadata misses, and timing receipt caps.
- [ ] Run `uv run pytest -q desktop/tests/test_startup_receipts.py desktop/tests/test_app_model_scan_timeout.py` and observe each new assertion fail.
- [ ] Implement the store with JSON schema validation, 0600 permission best effort,
  atomic replace, path containment check, and fixed-size stage list.
- [ ] Update the app path so a matching cache avoids `pick_chat_llm_file`; an absent
  or invalid cache follows the existing bounded scan and records the outcome.
- [ ] Re-run the focused desktop tests and record before/after core-ready receipt
  behavior without changing model ownership or starting an additional sidecar.
- [ ] Commit: `feat(desktop): record startup receipts and cache model selection`.

### Task 2: Define the sanitized runtime snapshot

**Files:**
- Create: `api/runtime_snapshot.py`
- Create: `api/routers/runtime.py`
- Create: `tests/test_runtime_snapshot.py`
- Modify: `api/main.py`

**Interfaces:**
- Produces `GET /api/runtime/snapshot` and `RuntimeSnapshot` Pydantic model.
- Consumes readiness, active data root, startup receipts, update status, and
  read-only vault/knowledge summaries through injected providers.

- [ ] Write failing tests that assert ready/degraded/unknown states, reason-code
  allowlisting, absence of absolute paths/secrets/raw exception strings, and no
  invocation of scans/mounts/repairs.
- [ ] Run `uv run pytest -q tests/test_runtime_snapshot.py` and confirm RED.
- [ ] Implement a provider-injected snapshot builder, using only existing read APIs
  and bounded filesystem metadata for the known auto-export directory.
- [ ] Register the authenticated router and prove malformed optional inputs degrade
  to `unknown` rather than 500.
- [ ] Run focused tests plus `uv run ruff check api/runtime_snapshot.py api/routers/runtime.py tests/test_runtime_snapshot.py`.
- [ ] Commit: `feat(api): expose a safe runtime snapshot`.

### Task 3: Make update notices verifiable and still notify-only

**Files:**
- Modify: `api/updates_service.py`
- Modify: `api/routers/updates.py`
- Modify: `tests/test_updates_service.py`
- Modify: `frontend/src/lib/api/updates.ts`
- Modify: `frontend/src/lib/hooks/use-updates.ts`
- Modify: `frontend/src/app/(dashboard)/settings/components/UpdatesCard.tsx`

**Interfaces:**
- Extends `UpdateStatus` with `verification: 'verified' | 'unverified' | 'unknown'`
  and an optional public release URL.
- A candidate is actionable only with canonical repo metadata, a parseable version,
  a named macOS DMG asset, and a checksum asset; it never provides installer code.

- [ ] Write failing backend tests for wrong repo data, invalid tags, missing DMG,
  missing checksum, and a valid verified release.
- [ ] Write focused frontend tests for verified, unverified, disabled, and network
  unavailable cards; assert no install/download control is rendered.
- [ ] Run each focused suite to capture expected RED failures.
- [ ] Implement eligibility classification and the plain-language card state.
- [ ] Re-run focused backend/frontend tests, lint, and typecheck.
- [ ] Commit: `feat(updates): distinguish verified release notices`.

### Task 4: Render the system dashboard and Recovery Center

**Files:**
- Create: `frontend/src/lib/api/runtime.ts`
- Create: `frontend/src/lib/hooks/use-runtime-snapshot.ts`
- Create: `frontend/src/components/common/RecoveryCenter.tsx`
- Create: `frontend/src/components/deeper-notebook/runtime/RuntimeStatusPanel.tsx`
- Create: focused Vitest files beside each new component
- Modify: `frontend/src/components/common/ErrorBoundary.tsx`
- Modify: `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.tsx`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Consumes the Task 2 `RuntimeSnapshot`; accepts `unknown` values without throwing.
- Recovery Center owns only Retry, Reload, Copy diagnostic code, and conditional
  existing `window.pywebview.api.relaunch` invocation.

- [ ] Write RED tests for safe error fallback, keyboard actions, no production
  exception/path rendering, core-vs-optional wording, and manual refresh.
- [ ] Run focused Vitest and confirm missing components/fallback behavior fail.
- [ ] Implement presentational components with semantic landmarks, status/alert
  roles, and the established Folio tokens.
- [ ] Connect the Horizon summary and Settings detail without duplicating fetches.
- [ ] Re-run focused tests, ESLint, `npx tsc --noEmit`, and the relevant mocked
  browser path.
- [ ] Commit: `feat(ui): add runtime dashboard and recovery center`.

### Task 5: Add Focus mode without changing content authority

**Files:**
- Modify: `frontend/src/lib/stores/display-preferences-store.ts`
- Modify: `frontend/src/lib/stores/display-preferences-store.test.ts`
- Create: `frontend/src/components/deeper-notebook/shell/FocusModeControl.tsx`
- Modify: `frontend/src/components/deeper-notebook/shell/LuminousAppShell.tsx`
- Modify: `frontend/src/components/deeper-notebook/shell/shell.css`
- Modify: command registry/provider tests as required

**Interfaces:**
- Adds allowlisted `focusMode: boolean`, default `false`.
- Exposes `toggleFocusMode()` and handles Escape only while focus mode is active.

- [ ] Write RED store and shell tests for persistence, no legacy preference loss,
  Escape exit, command activation, reachable utilities, and reduced motion.
- [ ] Run focused Vitest and confirm failures precede product code.
- [ ] Implement root data attribute, accessible control, command registration, and
  CSS that changes chrome only; do not unmount main content or alter routes.
- [ ] Re-run focused tests at 320/768/1024/1440 widths and default/rollback Folio flags.
- [ ] Commit: `feat(ui): add a reversible focus mode`.

### Task 6: Show backup and provenance receipts

**Files:**
- Modify: `api/runtime_snapshot.py`
- Modify: `tests/test_runtime_snapshot.py`
- Create: `frontend/src/components/deeper-notebook/runtime/BackupProvenancePanel.tsx`
- Create: `frontend/src/components/deeper-notebook/runtime/BackupProvenancePanel.test.tsx`
- Modify: runtime status composition and Settings placement.

**Interfaces:**
- Extends Task 2 snapshot with timestamp/size/integrity of known local auto-export
  and aggregate read-only/source-fingerprint evidence only.

- [ ] Write RED tests for absent receipts, stale/valid timestamps, bounded size,
  no absolute path/source-content disclosure, and read-only mount wording.
- [ ] Run backend/frontend focus tests and capture RED failures.
- [ ] Implement display-only aggregation and keyboard-readable provenance panel.
- [ ] Re-run focused tests, lint, typecheck, and read-only vault regression suite.
- [ ] Commit: `feat(ui): surface local backup and provenance receipts`.

### Task 7: Prove the integrated experience and package it

**Files:**
- Create or update: focused Playwright proof under `frontend/e2e/native/`
- Update: `docs/verification/` release receipt only after gates are green.

- [ ] Run backend test suite, desktop tests, frontend unit/lint/type/build, mocked
  E2E, and runtime snapshot browser scenarios.
- [ ] Run an isolated native API/Surreal/app smoke with a task-owned data root;
  verify startup receipt, Recovery Center safe fallback, dashboard, Focus mode,
  and unchanged external source fingerprints.
- [ ] Rebuild the DMG, verify `hdiutil`, signing, artifact identity, and install
  through a recoverable backup swap.
- [ ] Run installed-app API/frontend proof and document anything GUI automation
  cannot prove as a manual gate rather than a pass.
- [ ] Request fresh code review before merge; commit release proof separately.

## Checkpoints

- After Tasks 1–3: desktop/API/update unit gates green; update remains notify-only.
- After Tasks 4–6: UI browser/accessibility/responsive proof green with no vault write.
- After Task 7: package/install/native proof reviewed requirement-by-requirement.
