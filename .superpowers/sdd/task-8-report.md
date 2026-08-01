# Phase 1 Task 8 report

## Scope

- Added strict Zod wire contracts for local settings, readiness, route plans,
  and redacted receipts. Non-inventory payloads fail closed if a `path` field
  appears anywhere in their response tree.
- Built the Local Models Settings surface for read-only library rescan,
  readiness/runtime groups, explicit route overrides, accepted measured tiers,
  settings-backed compute/memory policy, benchmark history, and route
  receipts. Inventory remains the sole path-disclosing view.
- Added contextual Local Preferred confirmation that requires a stage and
  content class. Cancelling leaves the selected policy and work unchanged;
  Strict Local visibly blocks cloud routes.
- Added redacted Research Chat and Embedding route disclosures to Ask/Search,
  plus Evidence, Storyboard, Script, Verification, and Voice disclosures to
  the Phase 1 Podcast landing surface. These queries only plan routes; they do
  not execute chat, search, or podcast work.
- Kept backend, model library, provider configuration, and source authority
  unchanged.

## TDD evidence

The initial focused red run was:

```sh
(cd frontend && npx vitest run src/components/local-models/LocalExecutionPolicyPanel.test.tsx src/components/local-models/ModelRoutePlanPanel.test.tsx src/components/local-models/ModelInventory.test.tsx --pool=forks --maxWorkers=1)
```

It failed because both new panel modules were absent, and the inventory lacked
the readiness/tier disclosure assertions. A second red run for Ask, Search,
and Podcast failed because no route-plan surfaces were rendered.

## Final verification

```sh
(cd frontend && npx vitest run src/app/'(dashboard)'/settings/local-models/page.test.tsx src/components/local-models/LocalExecutionPolicyPanel.test.tsx src/components/local-models/ModelRoutePlanPanel.test.tsx src/components/local-models/ModelInventory.test.tsx src/components/vault/ResearchCoreHeader.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
# 5 files, 12 tests passed; TypeScript passed

(cd frontend && npx vitest run src/components/vault/KnowledgeAskPane.test.tsx src/components/vault/KnowledgeSearchPane.test.tsx src/components/vault/KnowledgePodcastPane.test.tsx --pool=forks --maxWorkers=1)
# 3 files, 12 tests passed

git diff --check
# passed
```

## Remaining build gate

The exact `npm run build` reached a Next.js Turbopack panic before compiling
application code because the existing untracked `frontend/node_modules`
symlink points outside the worktree. The non-mutating webpack fallback
compiled this task successfully, then stopped at an unrelated existing page
type error: `src/app/(dashboard)/setup-wizard/page.tsx` exports
`WIZARD_COMPLETED_KEY`, which is not a valid Next.js Page export. This task
does not modify that page or the shared dependency symlink.

## Boundaries

The worktree-local `node_modules/` remains untracked and was not committed.

## Review repair — saved settings and pending cloud continuation

### Red

New focused regressions failed because Ask, Search, and Podcast submitted
hard-coded `strict_local` / `balanced` route-plan requests. The Local Preferred
dialog also appeared without an actual planner-proposed cloud fallback and
pre-filled its contextual fields. Parser coverage did not exercise nested
`path` leaks.

### Repair and verification

- Every route-plan surface now waits for the saved local settings query and
  forwards its execution policy, compute profile, and role-specific override.
- A cloud-continuation dialog is offered only when saved Local Preferred has a
  concrete `approval_required` route plan. It starts empty and requires an
  exact stage/content-class match; confirmation records only that continuation
  state and executes no work. Strict Local exposes no continuation control.
- The shared redacted parser now has nested path-leak regressions for route
  plans and settings, and rejects the leak before schema coercion.

```sh
(cd frontend && npx vitest run src/app/'(dashboard)'/settings/local-models/page.test.tsx src/components/local-models/LocalExecutionPolicyPanel.test.tsx src/components/local-models/ModelRoutePlanPanel.test.tsx src/components/local-models/ModelInventory.test.tsx src/components/vault/ResearchCoreHeader.test.tsx src/lib/api/local-models.test.ts src/components/vault/KnowledgeAskPane.test.tsx src/components/vault/KnowledgeSearchPane.test.tsx src/components/vault/KnowledgePodcastPane.test.tsx --pool=forks --maxWorkers=1)
# 9 files, 31 tests passed

(cd frontend && npx tsc --noEmit)
# passed after removing stale generated frontend/.next types from the prior failed build
```
