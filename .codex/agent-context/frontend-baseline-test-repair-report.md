# Frontend Baseline Test Repair Report

## Scope

- Worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/frontend-baseline-test-repair`
- Branch/base: `codex/frontend-baseline-test-repair` from `2e2cd92a0df13da7ebc977a79f406879658efd00`
- Changed tests and locale data only; no production hook, store, API, mount, model, or external-vault behavior changed.

## Root cause and repair

- Workspace synchronization tests mocked `knowledgeWorkspaceApi.get` with a camel-case V1 object even though the API contract now returns normalized internal V2 documents. The fixture now enters through `parseKnowledgeWorkspace` from a valid V1 wire payload.
- Canonical persistence expectations now assert V2. Same-revision and invalid-locator tests update the typed `target` authority rather than only stale mirror fields.
- Removed the nine keys proven unused by the repository detector from every locale: `knowledge.description` and the eight obsolete Podcast status-card title/description keys. Retained the separately scoped, still-used source-status translations.

## Verification

- RED: targeted workspace + locale run reproduced 12 failures (11 workspace, 1 unused-key detector).
- Workspace-only GREEN: 1 file, 17/17 tests passed.
- Targeted GREEN: 2 files, 173/173 tests passed.
- Full frontend Vitest JSON report: 340/340 suites, 1272/1272 tests, `success: true`.
- Frontend ESLint: exit 0, zero errors and zero warnings.
- Next.js production build completed; `.next/BUILD_ID` timestamp `2026-08-02T22:37:31`, 28 app-path manifest entries.
- `git diff --check`: exit 0.
- Locale audit: all 14 locales retain exactly the two used `statusCompletedDesc`/`statusFailedDesc` source-status keys and contain none of the retired Podcast status-card keys or `knowledge.description`.

## Open items

- None in this test/locale-only scope. Native protected-source and Podcast production proof remain separate product gates.
