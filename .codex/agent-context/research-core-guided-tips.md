# Research Core Guided Tips — Task Context

## Objective

Complete Task 7 of `docs/superpowers/plans/2026-08-01-research-core-os-theme-foundation.md`: add optional, local, versioned contextual tips for the eleven approved major sections, plus Settings controls to disable and replay them.

## Starting point

- Active worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/research-core-lab-phase-1`
- Branch: `codex/podcast-intelligence-studio-phase-2`
- Reviewed Task 6 head: `3b1d7c7d`
- Exact task brief: `.superpowers/sdd/task-7-brief.md`
- A prior interrupted worker created uncommitted test-first files under:
  - `frontend/src/lib/guided-tips/`
  - `frontend/src/lib/stores/guided-tips-store.ts`
  - `frontend/src/lib/stores/guided-tips-store.test.ts`
  - `frontend/src/components/guided-tips/GuidedTipsProvider.test.tsx`
- Preserve and finish those files; do not discard useful partial work.

## Approved behavior

- One small non-modal contextual message at a time.
- `Got it` and Escape complete only the current tip version.
- `Don't show again` disables all tips without mutating completion state.
- Settings has an On/Off switch and `Replay all tips`; replay clears completion only.
- Local persistence key is `dn-guided-tips-v1`.
- Tips are hidden while `[aria-modal="true"]` or `[data-guided-tips-suspend="true"]` exists.
- Missing anchors fail closed. No focus trap. Keyboard and screen-reader accessible.
- Tips never start a scan, model run, podcast, or other mutation.

## Exclusive implementation scope

- `frontend/src/lib/guided-tips/**`
- `frontend/src/lib/stores/guided-tips-store.ts`
- `frontend/src/lib/stores/guided-tips-store.test.ts`
- `frontend/src/components/guided-tips/**`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/app/(dashboard)/settings/page.tsx`
- `.superpowers/sdd/task-7-report.md` for a new dated Guided Tips section only; do not overwrite its older unrelated Phase 1 content.

Do not edit or stage `.superpowers/sdd/task-3-report.md`, `task-4-report.md`, `task-5-report.md`, `task-6-report.md`, `desktop/requirements.lock`, `frontend/test-results/.last-run.json`, `history.txt`, `desktop/build/__pycache__/`, or `node_modules/`.

## Done criteria

1. All eleven catalog routes and stable sidebar anchors match the brief.
2. Versioned Zustand persistence and Settings controls match the approved semantics.
3. The provider positions beside the anchor, clamps to a 16px viewport inset, updates on resize/capture-scroll, observes modal/suspension state, and cleans up all observers/listeners.
4. Focused catalog/store/provider tests pass, including modal suppression, missing-anchor fail-closed, Escape, disable, and no focus trap.
5. Targeted lint exits 0; `git diff --check` passes for owned files.
6. Commit only the authorized Guided Tips implementation with message `feat: add local contextual guided tips`.
7. Append concise milestones/results/open items to this file and append a concise durable result to `/Users/Antman/.codex/context.md` while keeping the global context compact.

## 2026-08-02 Terra fallback result

- Verified the recorded Sol approval and Luna message-transport receipt, then
  preserved the interrupted worker's catalog/store/tests and completed only
  the approved Guided Tips files.
- Added the anchored non-modal provider and public export; mounted it in the
  app shell; added brand/navigation anchors; and added Settings enable/replay
  controls. Tips remain local-only and do not start any mutation.
- Focused verification passed: 3 Vitest files / 10 tests; direct ESLint on all
  owned paths passed. `npm run lint -- ...` still runs its pre-existing broad
  `eslint src/` prefix and reports ten unrelated Podcast/Vault errors; no
  unrelated code was changed. Open item for Sol: retain that global-lint
  limitation in the handoff or repair it separately outside Task 7 scope.
