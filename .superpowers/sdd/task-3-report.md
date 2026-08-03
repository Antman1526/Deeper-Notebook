# Phase 1 Task 3 report

## Scope

- Added `ResearchCoreHeader`, `KnowledgeModeLauncher`, and `KnowledgeIntelligenceRail` with focused component tests.
- Updated the workspace shell to use semantic `main`, mode-qualified tab names, an embedded connections inspector, and a collapsible utility rail.
- Preserved split resize, close/focus fallback, tab-to-panel `aria-controls`, and V2 active-tab fallback coverage.

## TDD evidence

Initial red command:

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1)
```

Result: the three new component suites failed to resolve their absent modules; the new `main` and mode-qualified-tab assertions also failed against the prior implementation.

Additional red checks:

- The mode-launcher roving-focus assertion failed until the launcher moved focus to the next toolbar button.
- The readiness disclosure test failed when a local path appeared in the readiness summary; the header now redacts POSIX and Windows local paths before rendering.

## Green verification

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
```

Result: `5` files passed, `25` tests passed, with zero TypeScript errors.

Additional adapter coverage:

```sh
(cd frontend && npx vitest run src/components/vault/KnowledgeUtilityRail.test.tsx src/components/vault/KnowledgeLinksInspector.test.tsx --pool=forks --maxWorkers=1)
```

Result: `2` files passed, `5` tests passed.

## Decisions and safeguards

- Header authority states are textual (`app-owned`, `external read-only`) rather than color-only. Its explicit local readiness state and readiness details disclose only model IDs and providers; configured local paths are redacted before display.
- The launcher exposes Read, Write, Ask, Search, Graph, and Podcast through a roving-tabindex toolbar and `Alt+1` through `Alt+6`. It activates a matching tab in the supplied active pane or requests a new mode tab; it has no replacement path for an unsaved Overlay draft.
- Intelligence panels stay unmounted when collapsed. Connections reuse `KnowledgeLinksInspector` in embedded form so the rail owns the sole semantic `aside`.
- Existing layout/strip behavior remains intact, with mode included in every tab accessible name and V2 workspace fixtures used for active-tab fallback after the Task 1 migration.

## Boundaries

No backend, provider, external-vault, model-library, or external-write behavior was changed. The worktree-local `node_modules/` symlink/cache remains untracked and was not committed.

## Review repair: live Explorer integration

- Mounted the header, launcher, and intelligence rail in `KnowledgeExplorer`, using the selected workspace tab, its authority, persisted panes, overlay-draft store, scan action, and local-model-health hook as the live data/action sources.
- The Explorer no longer supplies a separate links inspector. The intelligence rail opens on Connections in the Explorer so existing link navigation remains available, while the rail itself remains the sole `aside` landmark.
- Replaced the Explorer content `main` with a structural `div`; `KnowledgeWorkspaceLayout` remains the single live `main` landmark.
- Added the red-first Explorer integration assertion for the Research Core shell, one-main contract, and `Alt+4` Search tab creation. It initially failed because the components were not yet mounted in the Explorer.
- Updated an existing interaction assertion from `Write: Center` to `Graph: Center`, matching the fixture's actual graph-mode state without changing that flow's behavior.

Final verification:

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx src/components/vault/KnowledgeExplorer.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
```

Result: `6` files passed, `70` tests passed, with zero TypeScript errors. The dedicated Explorer suite also passed `45` tests.
