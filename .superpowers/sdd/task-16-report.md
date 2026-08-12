# Task 16 — Study Anki package portability

Date: 2026-08-12
Base: `d0e7d7c1`
Commit: `feat(study): add Anki package portability`

## Delivered

- Pinned `genanki==0.13.1` and regenerated the frozen `uv.lock` closure.
- Added deterministic-semantic Basic, reverse, and Cloze export with stable
  model/deck/note identities, escaped fields, Task 15 inspection, atomic
  application-root publication, opaque bounded downloads, and final-byte
  `package_sha256` receipts.
- Added strict feature-gated preview-only upload, explicit publish, status,
  replay/mismatch, safe errors, bounded streaming, private roots, cleanup, and
  symlink/root checks. Publish re-inspects the exact task-owned upload and binds
  `upload_id`, request ID, options, package hash, and a final plan revision
  re-read.
- Added strict frontend schemas/decoders, API adapters, plan-scoped query
  keys/hooks, retry/focus-safe package panel, and Study Plan workspace tab.
- Narrow Task 15 inspector compatibility remains exact: only native genanki
  index names/SQL and canonical numeric-string model/deck IDs are accepted;
  add-on indexes remain rejected.
- Task 15 imported reverse/Cloze cards retain a finite `anki_card:<kind>:`
  marker in the opaque `artifact_card_id`; Task 16 recovers only those exact
  markers (legacy cards remain Basic), so native import → export preserves
  card kind without a new table or scheduler authority.

## Evidence

- RED: missing router/export/component contract tests failed before production.
- Backend Task 16: `46 passed, 1 warning`.
- Adjoining Study unit/API suites: `121 passed, 2 warnings`.
- Disposable real-Surreal import integration: `3 passed`.
- Frontend targeted panel/workspace/decoder tests: `14 passed`; ESLint and
  TypeScript passed.
- `uv lock --check`, Ruff, compileall, Bandit, and `git diff --check` passed.
- Root independently verified flag-on and flag-off Next builds green.
- Dependency evidence: installed `genanki 0.13.1` reports MIT; transitive
  additions report cached-property BSD, chevron MIT, and frozendict LGPL-3.
- Normal frozen `uvx pip-audit --strict -r <uv export>` could not begin: its
  temporary venv `ensurepip` aborts with SIGABRT (captured in the audit log).
  Root's `--no-deps --disable-pip` fallback reported only the existing 25
  Pillow 11.3.0 advisories and zero genanki/cached-property/chevron/frozendict
  matches. This is environment-limited advisory evidence, not a clean full
  pip-audit pass.

## Open concerns

- `_load_export_plan` uses a bounded card-link projection followed by per-card
  repository reads (bounded N+1); a future repository projection/join can
  reduce round trips without changing authority.
- The HTTP router remains a larger combined boundary; behavior is covered, but
  export/helper extraction is a follow-up maintainability improvement.
- Export-specific real-Surreal integration was not available in the disposable
  fixture lane; import/replay/race integration remains green.

No deploy, external publication, migration mutation, or provider-side action
was performed.

## Task 16 repair review closure — 2026-08-12

- Strict RED before implementation: committed-HEAD baseline passed 46 Anki import/export/API tests; repair regressions failed on reverse/Cloze source identity and raw fields, compatibility persistence, migration 45, durable repository/root behavior, claim conflict, and restart status.
- Added additive migration 45 (`study_anki_card_compat`, `study_anki_job`, `study_anki_export`) with strict bounded fields and symmetric down migration. Original cleaned note fields/source note IDs/template ords are persisted as projection-only compatibility metadata; native StudyCard/FSRS remains the only scheduling authority. Reverse reconstruction groups by `(package_sha256, source_note_id)` and emits one reverse note; Cloze raw tokens/Extra are restored. Unsupported reverse subsets fail closed.
- Durable job/export repositories use fixed projections (no `SELECT *`), exact plan/job/download binding, owner-token leases with atomic same-request replay/different-request conflict, expired-owner reclaim, stale-owner fail/complete fencing, restart rehydration, canonical `DATA_FOLDER` roots, opaque validated file tokens, 256 active-row transaction caps, and two-phase same-root tombstone expiry cleanup with authority-aware bounded sweep. Process caches are non-authoritative and no longer unlink durable files.
- Native output is re-inspected after writing. Receipt card count now comes from actual native `cards` rows (reverse=2, multi-Cloze=2), while note GUID/model/deck identity is asserted against the generated package. Ordered projections and canonical card sorting stabilize semantic receipt identity.

### Repair evidence

- Strict focused Anki repair/API/import/export: `61 passed, 1 warning` (known Starlette/httpx deprecation).
- All Study unit tests: `347 passed, 7 warnings` (existing dependency/deprecation warnings).
- Disposable real-Surreal import + portability: `11 passed`; portability includes migration-45 rehydration, concurrent claim owner/replay, conflict, expired reclaim/stale fencing, compatibility-native basic/reverse/Cloze round trips, export download/hash rehydration, expiry tombstones, and 256-row cap.
- Frontend targeted Anki/workspace/decoder tests: `14 passed`.
- Ruff, compileall, `uv lock --check`, and `git diff --check` passed. Scoped Bandit reports only pre-existing low-confidence B608 SQL-construction findings in `anki_repository.py` (and no new repair B110/B608 findings). Frozen pip-audit remains environment-blocked by known temporary-venv `ensurepip` SIGABRT; prior no-deps fallback found only the existing Pillow baseline.

Open maintainability concerns remain the bounded N+1 export projection and combined HTTP router; no deploy or external publication occurred.

## Task 16 final repair — 2026-08-12

- Strict RED was captured before production edits: c3 Cloze export was rejected by the old `template_ord <= 1` bound; a partial multi-Cloze import expanded the surviving ordinal back to all raw tokens; and a simulated native-publication/`complete()` crash left same-request replay metadata in `publishing` without a receipt binding.
- Minimal repair widens only Cloze compatibility ordinals to the exact bounded range 0..999, keeps Basic/reverse ordinals at 0..1, rejects partial multi-Cloze subsets with typed 409 rather than adding cards, and owner-fenced same-request replay reconciles an already-persisted receipt to durable `published` metadata. Different request/options remain conflicts and stale owners cannot complete.
- Final evidence: focused Task15/16 Anki import/export/API/repair `64 passed, 1 warning`; all Study unit `351 passed, 7 warnings`; real-Surreal import + portability `11 passed`; frontend targeted `14 passed`; Ruff, compileall, `uv lock --check`, and diff-check clean. Scoped Bandit reports only the existing low-confidence B608 SQL findings in `anki_repository.py`, with no new findings.
- Frozen strict pip-audit's temporary venv setup remains environment-limited by `ensurepip` SIGABRT. The documented no-deps/disable-pip fallback found only the existing 25 Pillow 11.3.0 advisories and no new genanki closure findings.

## Task 16 replay/package-authority repair — 2026-08-12

- Fresh review at `46df5196` found a high-severity replay binding gap: recovery
  searched receipts by plan/request and did not verify the receipt package
  against the current job and claim package. A same-request/different-package
  retry could therefore publish the wrong receipt. It also found that durable
  terminal writes lacked a publishing-state CAS.
- Strict RED was captured before production edits with endpoint regressions for
  publishing and already-published mismatches, a repository query/CAS unit
  regression, and a real-Surreal terminal overwrite regression.
- Repair scope: `api/routers/study_anki.py` now requires receipt/current/
  claim package equality plus exact request/options before replay or metadata
  repair; `deeper_notebook/study/anki_jobs.py` binds `complete`/`fail` to exact
  package and `status = 'publishing'`; tests cover no-mutation 409s and
  published/failed terminal preservation.
- Evidence: focused Anki 67 passed (one known Starlette/httpx warning), all
  Study unit 354 passed (7 existing warnings), real-Surreal portability 9
  passed, frontend targeted 14 passed, Ruff/compileall/`uv lock --check`,
  migration tests, Bandit (no new findings), and diff-check passed. Frozen
  pip-audit remains environment-blocked as previously documented.
- No deploy, migration mutation, external publication, or unrelated work was
  performed. Exact commit target: `fix(study): bind Anki replay package authority`.
