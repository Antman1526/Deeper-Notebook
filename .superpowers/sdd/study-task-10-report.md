# Study Workbench Task 10 report

Date: 2026-08-12
Base: `56ef9fc1a33e31afc899b179e4063045da416f48`

## Scope

Task 10 adds strict contracts and projection-only persistence for assistant
sessions, structured handoffs, plan-local memory, and progress receipts. The
Task 9 lease already owns migration 42, so this task uses additive migration
43/43_down and records that deviation here.

## TDD receipt

- RED before production: the requested focused command collected no tests and
  reported both assistant test modules missing.
- RED after tests: collection failed with missing `deeper_notebook.study.assistants`
  and `assistant_repository` imports.
- GREEN focused: 11 passed, no Task 10 test failures.

## Implementation

- `assistants.py`: twelve exact roles, four authority modes, frozen/extra-forbid
  bounded models, timezone-aware timestamps, immutable nested collections,
  network/syllabus authority guards, public response without raw provider or
  hidden reasoning fields, and confirmation-gated inferred memory.
- `assistant_repository.py`: fixed-field projections, table-bound parameterized
  RecordIDs, caps before materialization, non-disclosing typed errors, and
  idempotent/optimistic session, handoff, memory, and progress operations.
- `43.surrealql`/`43_down.surrealql`: schemafull bounded tables, effective
  array predicates, role/status/event allowlists, provenance/confirmation
  assertions, and plan/time/request indexes with symmetric rollback.

## Verification

- Focused contracts/repository: 11 passed.
- Full Task 3-10 backend selection: 196 passed, 7 warnings.
- Real disposable Surreal integration: 12 passed, 1 external warning.
- Ruff, compileall, and `git diff --check`: passed.
- Migration 43 applied in every disposable integration namespace; invalid
  inferred memory without confirmation was rejected by Surreal.
- Staged and post-commit-range gitleaks are required at final commit.

## Open items

No Task 10 implementation blockers. Task 11 assistant orchestration/API work
remains intentionally out of scope.

## Task 10 review repair — 2026-08-12

The review repair keeps assistant authority proposal-only and closes the three
receipt/idempotency and memory-boundary findings. `plan` invocations reject
direct syllabus edits and every source/card/schedule/syllabus mutation flag;
`create` remains non-mutating and requires explicit bounded network scope for
any network-enabled route. `assistant_inference` memory must remain inferred,
confirmation-required, and unconfirmed until the user decision; migration 43
mirrors the effective assertion for active/confirmed bypasses.

Session, handoff, and memory writes now persist SHA-256 hashes of their full
canonical request payloads (including effective request ID and memory expected
revision). Exact hash retries replay; a concurrent uniqueness winner with a
different hash raises `StudyAssistantConflictError` and never returns its
receipt. All assistant list projections cap and flatten at 50 before model
materialization, including memory/progress; the 43 down migration remains
table-symmetric.

Strict RED: 11 new failures / 13 existing passes. GREEN: focused contracts and
repository 24 passed; Task 3–10 selection 209 passed, 7 warnings; real
disposable Surreal integration 13 passed, 1 warning, including session,
handoff, and memory mismatched concurrent winners. Scoped Ruff, compileall,
diff-check, and migration invalid-write assertions passed.

Changed files: `assistants.py`, `assistant_repository.py`, `43.surrealql`,
focused assistant tests, and `tests/integration/test_study_plan_repository.py`.
No Task 11 work or external mutation. Final staged/range gitleaks and commit
receipts remain with the parent integration step.
