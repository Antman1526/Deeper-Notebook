# Task 14 repair report — Study Workbench progress decisions

Date: 2026-08-12
Base: `1cdab5b1` (`feat(study): project mastery and adaptations`)
Repair commit: pending (`fix(study): connect bounded progress decisions`)

## Scope

This repair connects the existing Study Workbench progress projection to the
frontend workspace and hardens the bounded decision protocol. It preserves
Task 10's `StudyAssistantRepository`/migration-43 `study_progress` authority.
The only actionable acceptance remains `extra_practice`, implemented through
the existing plan preference update with the expected revision. Intent and
completion receipts contain bounded fingerprints and weekly minutes, never a
full preference object.

## RED captured before production changes

- `uv run pytest -q tests/test_study_progress.py tests/test_study_progress_repository.py`:
  22 passed, 3 expected failures for the unbounded intent payload and dismiss
  state/idempotency seams.
- `cd frontend && npx vitest run src/lib/api/study-plans.test.ts
  src/lib/hooks/use-study-plans.test.tsx src/lib/types/study-progress.test.ts
  src/components/study/StudyPlanWorkspace.test.tsx
  src/components/study/StudyProgressPanel.test.tsx`: expected module/API,
  hook, and workspace reachability failures before the new files/exports.

## Repair evidence

- `uv run pytest -q tests/test_study_progress.py
  tests/test_study_progress_repository.py tests/test_study_scheduler.py
  tests/test_study_plans_api.py`: **62 passed**.
- Focused frontend suite (API, hook, strict decoder, workspace, panel,
  StudySession): **6 files / 32 tests passed**.
- `SURREAL_INTEGRATION=1 uv run pytest -q
  tests/integration/test_study_progress_repository.py`: **2 passed**;
  native review projection and concurrent append race both ran against the
  disposable real SurrealDB namespace.
- `uv run ruff check` on changed Python/tests: passed; compileall and
  `git diff --check`: passed.
- Scoped ESLint and `npx tsc --noEmit`: passed.
- `NEXT_PUBLIC_DN_STUDY_WORKBENCH=enabled npm run build`: passed (Next.js
  production build, TypeScript, static generation).

The tests cover same-proposal future-dated decisions remaining proposed,
latest native review due-state projection, infinite iterable bounds, eight
near-limit HTTPS scopes fitting the receipt, accepted/dismissed replay and
state conflicts, both acceptance crash windows, post-append projections,
corrupt intent/completion conflicts, feature-off prevalidation, mounted progress hooks, strict decoder retry,
accessible title-bearing dismissal, and stable retry request IDs.

## Open items / residual limits

- Only `extra_practice` has a safe existing plan mutation; prerequisite and
  schedule proposals remain explicitly unavailable.
- Full repository-wide gates and staged gitleaks are run at closeout after
  staging the exact repair scope; supplied `.codex/agent-context` files remain
  untracked and are not part of the commit.
