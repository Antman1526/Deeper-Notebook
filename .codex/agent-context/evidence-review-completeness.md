# Evidence Review Completeness

## Scope

Complete the already-approved Research Workbench evidence-review feature without
changing existing schemas, authority boundaries, or generation behavior.

## Reproduced gap

- Backend chat and Studio generation already schedule and persist immutable
  notebook-owned evaluation runs.
- `EvidenceQualityBadge`, `ClaimReviewDrawer`, `evaluationsApi`, and
  `useEvaluation` exist and have focused tests, but no production component
  imports or mounts them.
- The public GET endpoint requires a run ID that neither Chat nor Studio UI
  receives, so the feature is unreachable.
- Ask extracts claims best-effort but intentionally does not persist because it
  lacks durable notebook/source ownership. Preserve that safety boundary.
- Rechecks currently create a new run without the original artifact/message
  selector, which would make selector-based retrieval lose the newest result.

## Required behavior

1. Add notebook-scoped, read-only latest-evaluation lookup by exactly one
   selector (`artifact_id` or `message_id`). The endpoint must fail closed,
   validate/bound input, use parameterized queries, avoid cross-notebook
   disclosure, and preserve the existing run-ID API.
2. Add a bounded batch lookup for the visible chat message IDs so Chat does not
   issue one request per message. Deduplicate bounded identifiers and return a
   literal map keyed only by requested identifiers.
3. Preserve the original artifact/message selector on recheck runs.
4. Extend the typed frontend API/hooks without changing existing call sites.
5. Mount evidence status and the claim-review drawer on notebook AI messages
   and the selected Studio artifact. Render honest loading, unavailable,
   failed, empty, and completed states; a 404 means no evaluation and must not
   trigger an error toast.
6. Keep Source Chat and Ask behavior unchanged; no fabricated ownership or
   implicit source writes.
7. Add RED tests first for authorization, selector validation, latest ordering,
   batch bounds/deduplication, recheck association, frontend no-N+1 behavior,
   and keyboard-accessible drawer interactions.

## Performance and compatibility boundaries

- No schema rewrite. Additive indexes may be introduced only through a new
  forward/backward migration if measured query shape requires them.
- Batch inputs: at most 100 unique message IDs, each at most 512 characters.
- Result projection: at most one latest run per requested selector.
- Existing `/api/evaluations/{run_id}` and `/api/evaluations/recheck` payloads
  remain backward compatible.
- No polling after a run reaches completed/failed; pending/running retain the
  established 1.5-second polling cadence.

## Done gates

- Focused backend evaluation/repository/router tests and Ruff.
- Focused frontend API/hook/ChatPanel/ArtifactRail/evaluation tests, ESLint,
  TypeScript, and build.
- Mocked browser proof for Chat and Studio evidence states, keyboard open/close,
  and no unexpected requests/console errors.
- Full adjoining backend/frontend regression gates remain green.
- Atomic commits, task report, and this context updated with exact receipts.

## Execution receipts

- 2026-08-11 RED (before production edits):
  `uv run pytest -q tests/test_evaluation_completeness.py` = 6 failed. The
  failures reproduce the missing notebook-scoped latest lookup, missing bounded
  batch request/handler, and recheck selector association.
- 2026-08-11 frontend RED (before production edits):
  `npm exec vitest run src/lib/api/evaluations.completeness.test.ts
  src/lib/hooks/use-evaluation.completeness.test.tsx
  src/components/evaluation/EvidenceReview.test.tsx` = 5 failed and one
  missing-module suite. The failures reproduce absent typed latest/batch API,
  absent batch hook, and absent mounted review-state component.
- 2026-08-11 GREEN: backend evaluation family 34 passed (1 dependency
  deprecation warning); frontend evidence family 6 files/50 tests; scoped
  Ruff/ESLint and TypeScript passed; Next production build generated 23 routes.
- Mocked browser proof passed 1/1 with exact Chat batch and Studio latest
  request payloads, Enter/Space open, Escape close, zero unknown API traffic,
  and zero console errors. The tracked Playwright last-run marker was restored.
- Native SurrealDB syntax/execution proof is reserved for the final isolated
  runtime gate. No schema, Source Chat, Ask, authority, or write behavior changed.
- Fresh Sol review found an empty-first-read persistence race and validation
  before deduplication. RED regressions reproduced both. Final GREEN adds a
  canonical-message pending marker with bounded 15-second/1.5-second retry,
  removes it when the evaluation appears, accepts 101 duplicates as one unique
  ID, rejects over 100 unique IDs, and keeps a 256-item raw-input cap. Updated
  totals: backend 35 passed; frontend 6 files/51 tests; Ruff/ESLint/tsc passed.
