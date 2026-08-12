# Study Workbench Task 11 — bounded AI tutor team

Date: 2026-08-12
Base: `5b878786`
Status: independently approved

## Outcome

- Added one feature-gated foreground assistant endpoint for all twelve approved
  Study roles.
- Kept local measured models as the default. Cloud and Research Scout network
  use require the matching persisted plan permission and explicit request
  scope.
- Built context only from the approved syllabus, selected linked sources,
  bounded progress/reviews, confirmed memory, and at most twenty handoffs.
- Persisted metadata-only sessions plus replayable handoffs. Provider payloads,
  credentials, hidden reasoning, and raw prompts are not stored or returned.
- Bound completion atomically to the exact plan revision/state, approved
  syllabus version/timestamp/manifest, source-link set, and persisted
  model/network authority, plus the exact full-text digest of every selected
  Source used as evidence.

## Security and correctness closures

- Request replay hashes exclude server-generated timestamps; canonical replay
  keeps the originally persisted timestamp.
- Running retries cannot corrupt the winning invocation, and session completion
  plus its handoff publish in one guarded Surreal transaction.
- The queued-to-running transition is a one-winner optimistic claim. A
  concurrent identical retry receives a stable in-progress conflict and never
  invokes the model.
- Selected source markers and grounded excerpts receive reserved prompt budget
  ahead of optional memory/progress/handoff metadata, so maximum valid metadata
  cannot evict the evidence a Source Guide must cite.
- Research Scout receives a separate bounded evidence allocation. Only web
  result IDs whose grounded excerpts are present in that allocation are
  citable, and the prompt contract explicitly permits those evidence IDs.
- Whole-invocation work is capped at 120 seconds; best-effort terminal failure
  persistence receives a separate 10 ms ceiling.
- Research URLs require exact HTTPS host, port, and path boundaries, outbound
  public-address validation, and path-preserving discovery filters.
- Citations require selected evidence and grounded quotes. Proposed actions use
  finite exact allowlists and remain inert proposals.
- Assistants remain available in `approved`, `generating`, `active`, and
  `completed` states; archived and pre-approval plans fail closed.
- Changed payloads under a reused request ID return a stable conflict rather
  than an availability error.

## Verification

- Focused Task 11 service/repository/API gate: 53 passed, 7 dependency warnings.
- Broad Study/Studio/source regression selection: 274 passed, 7 dependency
  warnings.
- Real disposable SurrealDB integration: 14 passed, including active-plan
  atomic publication, exact Source-digest drift rollback with no handoff, and
  a one-winner concurrent running claim.
- Product identity: 141 passed.
- Rebrand audit: exit 0, unexpected active identity 0, stale allowlist empty.
- Scoped Ruff, compileall, high-severity/high-confidence Bandit, and
  `git diff --check`: passed.

The warnings are existing third-party deprecations. Code Review Graph evidence
was unavailable because no `graphify-out/graph.json` artifact exists; native
source review and fresh independent Sol review were used instead.

The final fresh Sol review reran 65 focused tests and all 14 disposable
SurrealDB tests, inspected all 13 product/test files, and returned `APPROVED`
with no blocking defect.
