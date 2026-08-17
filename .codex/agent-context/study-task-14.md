# Study Workbench Task 14 context

- Worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/study-workbench`
- Branch: `codex/study-workbench`
- Starting HEAD: `2e70147d` after independently approved Task 13.
- Global context: `/Users/Antman/.codex/context.md`
- Exact brief: `.superpowers/sdd/task-14-brief.md`
- Approved design: `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
- Approved plan: `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`

## Objective

Implement append-only Study progress receipts and deterministic mastery and
adaptation projections. Existing native Study cards and FSRS review history
remain authoritative; no duplicated scheduler or silent plan rewrite.

## Required boundaries

- Inspect migration 43 and Task 10 assistant progress repository before
  designing storage. Reuse a sound append-only table/contract if compatible;
  do not create competing `study_progress` authorities.
- Every receipt has strict frozen typed contracts, bounded UTF-8 text and
  collections, explicit aware timestamps, exact record/unit/concept IDs, and
  a stable request/idempotency ID. Copy/update paths must revalidate.
- Append-only means no update/delete mutation authority. Concurrent identical
  request IDs converge only when the full canonical payload matches; mismatch
  is a typed conflict. Bound pages to at most 50 and use fixed projections and
  bound parameters.
- Projection is pure and deterministic for explicit `now`. It may consume
  quiz/progress receipts and repository-projected existing native Study review
  receipts, but may not copy or rewrite FSRS scheduling state.
- Weighting, lapse/recency effects, statuses, pacing, proposals, and ordering
  must be explicit, bounded, stable, and tested for empty/malformed/out-of-order
  inputs. No permanent inferred memory is written.
- Adaptations are proposals only. Accept/dismiss is an explicit user action,
  must use an existing plan/syllabus mutation with optimistic revision where
  applicable, and append a decision receipt. If no existing mutation safely
  implements a proposal, render it unavailable instead of inventing authority.
- Feature-off behavior is uniform 404 before validation. Repository outages
  map to safe 503, stale/duplicate mismatches to typed 409, malformed requests
  to 422, missing plan to nondisclosing 404.
- Frontend uses a strict decoder, loading/empty/error/retry/populated states,
  keyboard-accessible proposal review, no mutation before confirmation, and
  targeted query invalidation.

## TDD and verification

1. Write the exact backend/frontend RED tests before production.
2. Implement only the eight brief-owned files unless a narrow migration or API
   client/hook file is demonstrably required; document any expansion first.
3. Run brief focused tests plus existing FSRS scheduler/review regressions,
   Ruff/compileall, frontend ESLint/TypeScript, flag-on build, diff checks.
4. Where persistence changes, run disposable real Surreal integration and
   migration symmetry/projection checks.
5. Stage exact scope, gitleaks staged/range, atomic commit
   `feat(study): project mastery and adaptations`; update report and contexts.

## Done criteria

- Deterministic projection and append-only idempotency are executable proof.
- Native FSRS authority is unchanged and adjoining review tests pass.
- No Critical/Important self-review concern remains.
- Return exact files, RED/GREEN/runtime/static/build/scan evidence, hash, and
  residual limits. Do not begin Task 15.

## Task 14 execution milestone and closeout — 2026-08-12

- RED was captured before production: missing `deeper_notebook.study.progress`
  and missing `StudyProgressPanel`; frontend tests use the existing `fireEvent`
  seam.
- Implemented strict bounded assessment/event codecs and deterministic mastery
  projection over Task 10 migration43 `study_progress` receipts plus native
  FSRS review receipts. Projection uses `islice`, latest-review-per-card due
  state, current AGAIN events for lapses, canonical request de-duplication, and
  no memory writes. Added fixed native review projection with typed card links.
- API exposes feature-gated projection and explicit decisions. Only
  `extra_practice` mutates existing plan preferences; two-phase intent/completion
  receipts reconcile both update crash windows and reject unrelated revisions.
  Dismiss is idempotent receipt-only; completion/intent validation remains strict
  after proposal time decay.
- Frontend decoder requires exact versioned shape, timezone-aware timestamps,
  bounded integer lapses, empty memory writes, and strict review keys. Radix
  Dialog confirmation awaits callbacks, retains error/retry state, and fails
  closed when a handler is absent.
- Narrow native FSRS persistence repair keeps datetime values in Python mode for
  Surreal schema fields; unit and disposable integration proof cover it.
- Focused backend/API/FSRS GREEN: `uv run pytest -q
  tests/test_study_progress.py tests/test_study_progress_repository.py
  tests/test_study_scheduler.py` = 28 passed; adjoining assistant/plans API =
  56 passed. Frontend Study Progress + Study Session = 7 passed and TypeScript
  passes. Real disposable Surreal combined integration = 16 passed (native
  review projection and concurrent append race included). Scoped Ruff,
  compileall, ESLint, diff-check, flag-on Next build, and staged gitleaks
  (~102 KB, 0 leaks) pass.
- Staged scope includes the 12 Task14 files plus narrow native datetime repair/
  test; supplied task contexts remain untracked and untouched. Commit is pending
  exact subject `feat(study): project mastery and adaptations`.

## Repair pass — 2026-08-12

- Fresh review repair started from `1cdab5b1`; original Task14 commit remains
  intact. Supplied `.codex/agent-context/study-task-13.md` and this file remain
  untracked and untouched.
- RED captured before repair production edits: backend progress/repository
  suite 22 passed with 3 expected failures (intent payload bound and dismiss
  replay/state); frontend API/hooks/types/workspace suite had expected missing
  module/reachability failures.
- Repair now exports strict progress types/decoder, API methods, targeted
  hooks/invalidation, mounted workspace progress tab, stable panel request IDs,
  awaited confirmation/retry/error states, and title-bearing dismiss labels.
- Backend repair stores only target weekly minutes plus bounded base/target
  fingerprints in the two-phase acceptance receipts; malformed/corrupt
  intent/completion is a typed conflict, base/base+1 reconciliation is exact,
  and dismiss replay is validated before proposal state. Decision projection
  ignores future receipts; `_projection_for_plan` exposes only proposed
  `extra_practice` actions. Decoder now explicitly allows the strict dismissed
  completion shape while rejecting malformed accepted intent/completion.
- GREEN evidence: focused backend/API/FSRS = 60 passed; frontend API/hooks/
  decoder/workspace/panel/StudySession = 6 files, 32 passed; real disposable
  Surreal native review projection + append race = 2 passed; scoped Ruff,
  compileall, diff-check, ESLint, TypeScript, and flag-on Next build passed.
- Closeout remains: run final diff/security checks, stage only exact repair
  files plus report, commit `fix(study): connect bounded progress decisions`,
  and return hash/evidence/open limits. Do not stage contexts or start Task15.

## Second repair execution receipt — 2026-08-12

- RED: 7 failures in progress/repository suites before claim, terminal, batch,
  and projection rehydration production changes.
- Implemented deterministic SHA-256 per-plan/proposal claim and terminal IDs,
  strict claim/terminal codecs, shared Accept/Dismiss claim contention, bounded
  exact request-ID batch reads, and terminal overlay before newest-page slicing.
  Task10 migration43 `study_progress` remains sole authority.
- Repaired existing PlanRepository preference mutation for real SurrealDB by
  using a complete parameterized MERGE patch carrying expected+1 revision and
  aware updated_at; removed invalid MERGE+SET syntax.
- GREEN: focused claim/projection 34 passed; scoped Study backend/API/FSRS 273
  passed; plan+focused 62 passed; frontend targeted 165 passed; real combined
  Surreal study integration 19 passed; Ruff/compileall/diff-check/tsc/ESLint
  (0 errors, 2 pre-existing warnings)/flag-on Next build passed.
- Full non-integration backend 4,275 passed/1 skipped with two pre-existing
  product-identity failures from stale api/main.py compatibility inventory;
  no Task14 changes touch that file. Generated desktop/build cache removed.
- Open: parent should review and commit exact Task14 repair files/report only;
  supplied `.codex` contexts remain untracked. Do not begin Task15.

## Receipt authority repair — 2026-08-12

- Starting repair HEAD: `955c05e8`. RED regressions were added before the
  production edit: 9 authority cases failed / 1 valid replay passed.
- Repaired `api/routers/study_plans.py` so all strict decision/claim/terminal
  validators bind `event`, exact plan/request envelope, aware receipt time at
  or before operation `now`, and strict details. Terminal replay requires a
  valid matching deterministic claim, exact claim/terminal fields, claim-first
  ordering, and no future receipt. Accept replay reloads the current plan and
  requires revision `base_revision + 1` plus exact target fingerprint; dismiss
  replay reloads current plan for its response. Normal terminal completion
  responses also reload current plan after append.
- Added API regressions and a real-Surreal orphan-terminal authority test.
- GREEN: new selector 14 passed; all Task 3–14 Study backend modules 287
  passed/7 warnings; combined real Study Surreal integration 20 passed/1
  warning; frontend Study/API/hooks/types 46 files/291 passed; focused
  workspace/progress/session 6 files/32 passed; Ruff, compileall,
  `git diff --check`, ESLint, TypeScript, and flag-on Next build passed.
- Repair commit is pending exact subject `fix(study): bind adaptation receipt
  authority`; stage only the three source/test files plus this report. Keep
  supplied Task 13/14/15 contexts untracked and do not begin Task 15.
