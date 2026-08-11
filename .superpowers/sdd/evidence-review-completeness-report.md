# Evidence Review Completeness Report

Date: 2026-08-11

## Outcome

The previously persisted evaluation data is now reachable from the two user
surfaces that own it: notebook AI messages and selected Studio artifacts. The
change is additive. Existing run-ID lookup and recheck request/response shapes
remain intact, no database schema changed, and Source Chat/Ask behavior is
unchanged.

## Changes and justification

- `api/routers/evaluations.py`: adds notebook-owned latest and bounded batch
  read endpoints, validates exactly one selector, deduplicates at most 100
  message IDs, preserves selectors during recheck, and projects the existing
  detail response shape. This closes the unreachable-data gap without changing
  the existing public routes.
- `deeper_notebook/evaluation/repository.py`: adds parameterized, projected
  latest-run queries and one batched verdict query. Each per-message branch is
  limited to one row, preventing N+1 database requests and unbounded history
  materialization.
- `frontend/src/lib/api/evaluations.ts` and
  `frontend/src/lib/hooks/use-evaluation.ts`: add typed latest/batch clients and
  1.5-second polling only while a run is pending or running. A 404 is treated as
  an honest no-review state and does not produce an error toast.
- `frontend/src/lib/hooks/useNotebookChat.ts`: marks each new canonical AI
  message for a bounded 15-second persistence-grace handoff before rendering
  it. An empty first lookup therefore retries while the server's advisory
  evaluation is being saved, without permanent polling for older messages.
- `frontend/src/components/evaluation/EvidenceReview.tsx`,
  `EvidenceQualityBadge.tsx`, and `ClaimReviewDrawer.tsx`: add accessible
  loading, unavailable, failed, empty, and completed evidence states with
  keyboard-openable review details.
- `frontend/src/components/source/ChatPanel.tsx`: mounts one shared, bounded
  batch lookup for the latest 100 persisted notebook AI messages. Temporary and
  streaming IDs are excluded; Source Chat remains unchanged.
- `frontend/src/components/deeper-notebook/ArtifactRail.tsx`: mounts the same
  evidence review presentation for the selected Studio artifact.
- `tests/test_evaluation_completeness.py`, the frontend completeness suites,
  and `frontend/e2e/evidence-review-completeness.spec.ts`: lock authorization,
  bounds, no-N+1 behavior, selector preservation, polling stop conditions,
  keyboard behavior, exact request payloads, console cleanliness, and unknown
  request detection. The browser fixture also disables guided tips and writes a
  temporary screenshot for rendered-state inspection.
- `scripts/rebrand-allowlist.json` and `scripts/rebrand_audit.py`: move only
  the six exact compatibility-fixture anchors shifted by the new ArtifactRail
  tests and refresh their contract/inventory digests; no broad rebrand sweep or
  identity change was made.

## Verification

- Backend evaluation, repository, router, schema, runner, auth, and adjoining
  family: 55 passed, 2 dependency deprecation warnings.
- Frontend evidence family: 6 files, 51 tests passed.
- Mocked browser: 1 passed (29.5s); Chat batch and Studio latest lookup,
  Enter/Space open, Escape close, exact request payloads, explicit background
  request fixtures, no unknown API traffic, and no console errors. The
  rendered notebook screenshot was inspected before closeout.
- Product identity/rebrand: 148 tests passed; `rebrand_audit.py --check`
  reports zero unexpected active identities and zero stale allowlist entries.
- Scoped Ruff and ESLint: passed.
- TypeScript `--noEmit`: passed.
- Next production build: passed, 23 routes generated.
- `git diff --check`: passed.

Fresh-context review found and the final patch fixed two pre-commit defects:
the persistence race above, and raw-list validation that rejected 101 duplicate
IDs before applying the documented 100-unique-ID limit. The server now accepts
that harmless duplicate case while retaining a separate 256-item raw-input cap.

## Remaining proof boundary

The nested SurrealDB batch query is parameterized and unit-contract tested,
including 100 requested IDs with one `LIMIT 1` per branch. Native database
execution is intentionally deferred to the final isolated SurrealDB release
gate so it can be proven together with the full runtime and source-integrity
checks. No production-release claim is made by this slice.
