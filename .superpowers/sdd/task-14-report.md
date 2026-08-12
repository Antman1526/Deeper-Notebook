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

## Decision serialization repair — 2026-08-12

- RED before production: the progress and repository suites reported 7
  expected failures for missing deterministic claim/terminal IDs, contention
  and replay, corrupt receipt conflicts, terminal rehydration, and the missing
  bounded batch lookup.
- Added deterministic SHA-256 claim and terminal request IDs, strict claim and
  terminal codecs, one shared per-proposal claim for Accept/Dismiss, and
  deterministic terminal receipts. Retries validate the complete claim,
  intent, terminal, client request, proposal, and plan-authority tuple before
  resuming; no second weekly mutation is permitted.
- Added the fixed-projection, parameterized
  `StudyAssistantRepository.list_progress_by_requests` lookup capped at 100
  IDs. Projection computes the bounded newest-page baseline, then prepends
  exact terminal receipts so old decisions cannot age out. Task 10 migration43
  `study_progress` remains the sole persistence authority.
- Narrowly repaired `StudyPlanRepository.update`: SurrealDB does not accept
  `MERGE ... SET`; the validated patch now carries next revision and aware
  `updated_at` in one MERGE object while retaining the optimistic guard.
- GREEN: scoped Study backend/API/FSRS suite = 273 passed; focused claim suite
  = 34 passed; plan repository plus focused suite = 62 passed. Frontend
  targeted API/types/workspace/panel suite = 165 passed; ESLint has 0 errors
  and 2 pre-existing warnings; TypeScript and flag-on Next production build
  pass.
- Real Surreal combined study integration = 19 passed, including native review
  projection, append race, independent deterministic claim contention, bounded
  exact batch lookup, and real Accept preference mutation. Scoped Ruff,
  compileall, diff-check, and the invalid `MERGE $patch SET` search pass.
- Full non-integration backend run = 4,275 passed, 1 skipped, with two
  pre-existing product-identity failures caused by stale `api/main.py`
  compatibility-selector inventory (three extra `/api/onp`/`/onp/` selectors);
  no Task14 file touches that module. Generated caches were removed and the
  supplied task contexts remain untracked.

## Receipt authority repair — 2026-08-12

### Review findings and RED

The final serial review identified that decision recovery trusted valid detail
JSON in failed/cancelled/assessed envelopes, and that terminal replay did not
prove the deterministic claim, receipt ordering, or the current plan's exact
post-mutation revision/fingerprint. New regressions were written before the
production repair; the focused selector reached **9 failures / 1 valid replay
pass** against `955c05e8`.

### Repair

- `_strict_decision_details`, `_strict_claim_details`, and
  `_strict_terminal_details` now require `event="decision"`, exact plan and
  deterministic request IDs, aware `created_at <= now`, and strict decoded
  details.
- Accept and dismiss terminal replay now require a matching deterministic
  claim, exact client/proposal/decision binding, terminal-at-or-after-claim
  ordering, and no future receipt. Accepted replay reloads the current plan
  and requires `version == base_revision + 1` plus exact
  `_plan_fingerprint(plan) == target_plan_sha256`; dismiss replay reloads the
  plan for its response projection without claiming mutation authority.
- Normal post-terminal responses reload the current plan after persistence so
  a stale initial plan cannot authorize a stale projection. Terminal payloads
  retain only the fields needed to bind the claim and target mutation.

### Verification

- New API regressions: **14 passed** (event/envelope authority, orphan,
  unmutated/wrong revision/fingerprint, ordering/future, valid replay, and
  dismiss claim binding).
- Scoped Study backend/API/FSRS selection (all Task 3–14 Study test modules):
  **287 passed, 7 warnings**.
- Real combined Study Surreal selection (`test_study_plan_repository`,
  `test_study_progress_repository`, `test_study_source_readiness`): **20
  passed, 1 warning**, including a real orphan-terminal 409 authority test.
- Frontend Study/API/hooks/types regression: **46 files / 291 passed**;
  focused workspace/progress/session subset: **6 files / 32 passed**.
- Scoped Ruff, compileall, `git diff --check`, ESLint, and TypeScript passed;
  `NEXT_PUBLIC_DN_STUDY_WORKBENCH=enabled npm run build` passed with all Study
  routes generated.

Only `api/routers/study_plans.py`,
`tests/test_study_progress.py`, and
`tests/integration/test_study_progress_repository.py` are implementation/test
changes in this repair; supplied `.codex/agent-context` files remain
untracked and are not staged.
