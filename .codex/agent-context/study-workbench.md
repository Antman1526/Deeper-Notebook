# Study Workbench Task Context

## Approved product decisions

- Expand the existing `/study` surface; do not create a competing scheduler or source store.
- Support both evidence-first local plans and explicitly approved web-research plans.
- Propose an editable syllabus before downstream generation.
- Study Plans are independent workspaces that link multiple existing sources read-only.
- Native FSRS remains authoritative.
- Initial scope includes secure Anki `.apkg` import/export, not live synchronization.
- Provide a coordinated twelve-role AI Study Team with visible Ask/Coach/Plan/Create authority.

## Durable documents

- Design: `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
- Design commit: `e61e5d82`
- Implementation plan: `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`

## Existing boundaries to preserve

- `deeper_notebook/study/contracts.py`, `scheduler.py`, `repository.py`
- `api/routers/study.py`, `api/schemas/study.py`
- current `StudySession`, source ingestion, Evidence Studio generation, and source evidence contracts
- unrelated untracked task contexts, `graphify-out`, root `node_modules`, Playwright artifacts, and desktop build cache

## Planning evidence

- Both reference repositories are AGPL; no upstream implementation will be copied or embedded.
- Anki export will use audited MIT `genanki==0.13.1`; import remains a bounded native parser.
- Anki 25.09.4 published a security fix for untrusted package local-file access; the import plan includes a direct regression for that vulnerability class.
- Code Review Graph was unavailable because `graphify-out/graph.json` is absent; the plan uses direct source tracing.

## Execution rule

Implement tasks in order with RED -> GREEN, atomic commits, fresh review gates,
flag-off rollback preservation, and no default-on flip until full isolated
runtime proof passes.

## Task 1 receipt — 2026-08-11

- Commit `02b230db` (`feat(study): add reversible workbench boundary`) adds
  backend `study_workbench_enabled()` and frontend
  `isStudyWorkbenchEnabled()`, both default-off, plus the static frontend flag
  contract and explicit flag-off Study dashboard/session regression.
- The strict environment resolver initially REDed with an unknown-setting
  `KeyError`; the existing `STUDY_WORKBENCH` short-setting registration was
  added as the narrowly authorized plan-omission repair. No bespoke fallback.
- RED: backend missing function (1 failed/13 deselected); frontend missing
  function (1 failed/7 passed). GREEN: backend 3 passed/11 deselected and
  frontend 3 files/11 tests; ESLint, TypeScript, diff-check, and staged
  sensitive-string scan passed.
- Page enabled mode is only a local boundary marker; Task 7 owns replacement
  with the real `StudyWorkbench`. Flag-off review behavior remains the rollback
  surface. Report: `.superpowers/sdd/task-1-report.md`.

## Task 2 receipt — 2026-08-11

- Terra fallback executed the Sol-approved Task 2 escalation from clean
  `02b230db`; the prior Luna worker had produced no mutation or usable receipt.
  Commit `60b2161f` (`feat(study): define plan and syllabus contracts`) adds
  only `deeper_notebook/study/plans.py` and
  `tests/test_study_plan_contracts.py`.
- Contracts are frozen/extra-forbid and cover bounded activities, preferences,
  source links, versioned immutable syllabi, source-manifest and exact
  syllabus-version approval binding, timezone-aware timestamps, unique units/
  sources, optimistic revision checks, and the allowlisted plan lifecycle.
- TDD receipt: exact focused RED failed with the expected missing-module
  collection error; exact GREEN passed 7/7 and Ruff passed. Direct lifecycle
  probe, pre/post-commit diff checks, and staged sensitive-string scan passed.
  Report: `.superpowers/sdd/task-2-report.md`.
- Open: Task 3 persistence/migrations and all later API/UI/AI/Anki work remain
  intentionally unimplemented; StudyCard, StudyReview, and FSRS contracts were
  unchanged.

## Task 2 review repair receipt — 2026-08-11

- Review of `60b2161f` found shallow list mutability, no strict coercion,
  unbounded collection-element strings, `StudyPlan.model_copy` lifecycle/
  approval bypass, and a vacuous blank-goal test. The bounded same-file repair
  is commit `a4854431` (`fix(study): harden immutable plan contracts`).
- TDD RED: focused contract suite returned 3 failed / 7 passed, demonstrating
  all three fault classes. GREEN: focused suite returned 10/10 and exact Ruff
  passed. `git diff --check`, staged sensitive scan, post-commit diff check,
  and a direct immutable-storage/authority/strictness probe passed.
- Models now accept normal list inputs but persist tuples; strict Pydantic
  validation and element-length aliases bound objectives/prerequisites/source
  IDs; protected `model_copy` fields fail and allowed copies revalidate. Report
  evidence: `.superpowers/sdd/task-2-report.md`.

## Task 2 second review repair receipt — 2026-08-11

- Re-review found inherited unchecked `model_copy` on every contract other
  than `StudyPlan`. Commit `b35371e8` (`fix(study): validate all contract
  copies`) adds an internal strict/frozen `_FrozenContract` base whose copy
  path revalidates every update; it retains deep-copy semantics and normal
  list-to-tuple input support. StudyPlan preserves its extra protected-field
  gate before delegating permitted updates.
- TDD RED was 1 failed / 10 passed: an activity copy accepted zero minutes.
  The new regression covers Activity, Preferences, SourceLink, Unit, and
  Syllabus, while the existing plan test covers lifecycle authority. GREEN was
  11/11 with exact Ruff, diff checks, staged scan, and direct copy-authority
  probe all passing. Report evidence: `.superpowers/sdd/task-2-report.md`.

## Task 3 receipt — 2026-08-11

- Additive persistence is implemented in `41.surrealql`, `41_down.surrealql`,
  `deeper_notebook/study/plan_repository.py`, and focused unit/integration
  tests. Repository uses projection-only decoding, bounded pagination, safe
  domain errors, deterministic RecordIDs, unique read-only source links,
  immutable syllabus/unit versions, and optimistic revision/syllabus approval.
- RED: required unit command failed at collection with missing
  `deeper_notebook.study.plan_repository`. GREEN: focused unit suite 8 passed;
  exact Ruff passed; disposable fixture integration 2 passed against a
  throwaway namespace on the existing listener at `127.0.0.1:8000`.
- Runtime repairs found during integration: Surreal transaction result shape
  may return the syllabus row before the plan row, so approval re-reads the
  canonical plan; `array::remove` is index-based, so source removal uses a
  bounded filter. No source records are mutated/deleted.
- Report: `.superpowers/sdd/task-3-report.md`. Commit target/message:
  `feat(study): persist plans and syllabus versions`. Open: later API/UI/AI/
  Anki tasks remain intentionally unimplemented.

## Task 3 review repair receipt — 2026-08-12

- Commit `d90d77b9` (`fix(study): close persistence transaction guards`) is a
  separate repair after `26ca1507`; it changes only migration 41, the
  repository, and the two Task 3 test files. The down migration remains
  unchanged and is still the exact six-table inverse.
- TDD RED: repair tests initially reported 10 failed / 4 passed for approval
  and link zero-row guards, stale/missing syllabus rollback, Mapping candidate
  validation, and migration bounds/hash assertions. A disposable probe found
  Surreal `~ /.../` digest matching false; `string::matches` is verified. The
  live client returns `None` for a transaction trailing RETURN after COMMIT,
  so canonical post-state receipts are now checked.
- GREEN: unit 14 passed; disposable integration 5 passed in 16.47s; scoped
  Ruff passed. Integration covers missing/stale approval (including an
  already-approved version), stale/missing add/remove rollback, required
  save_syllabus no-orphan behavior, invalid Mapping updates with unchanged DB
  state, and a real source row surviving link removal. Migration static gate
  found six matching up/down tables and bounded element/activity fields;
  diff-check and staged sensitive scan were clean.
- Unique report: `.superpowers/sdd/study-task-3-report.md`. Later API/UI/AI/
  Anki work remains open.

## Task 3 migration contract repair — 2026-08-12

- Final review found a bounded migration gap: child `DEFINE FIELD ...*`
  assertions did not enforce array-element contracts in the running SurrealDB.
  Separate migration-only commit follows `d90d77b9`; repository logic is
  unchanged.
- TDD RED: migration contract test failed 1/2 before production migration
  edits. Migration 41 now uses trim-based nonblank assertions, exact
  `^[a-z0-9][a-z0-9_-]{0,63}$` unit/prerequisite/activity IDs, all nine
  `StudyActivity.kind` values, and parent `array::every` predicates for
  objectives, prerequisite IDs, source IDs, activities, and nested activity
  source IDs.
- Disposable fresh namespace/all-migration probe rejected 12/12 invalid
  writes (blank plan/source text, invalid unit fields, invalid activity fields)
  and left `study_unit` empty. `array::every` is runtime-effective; former
  child-field syntax is not. Unit suite 15 passed, Ruff passed, existing
  repository integration 5 passed in 13.67s, migration symmetry/diff-check/
  staged sensitive scan passed. Unique report updated at
  `.superpowers/sdd/study-task-3-report.md`.

## Deeper Notebook Study Workbench Task 4 API — 2026-08-12

- Terra fallback completed the Sol-approved Task 4 plan from base `0d41150a`,
  including the narrowly authorized Task 3 omission repair
  `StudyPlanRepository.get_syllabus`. The reader is projection-only, read-only,
  plan/version-bound, ordered/bounded to 64 units, returns `None` for missing,
  and immutable-contract decodes. A disposable integration regression proves
  Surreal needs `type::string(plan_id)` for the child-unit predicate.
- Added strict, flag-gated `/api/study/plans` create/list/get/patch,
  source-link, and syllabus read/save/approve APIs. They use only repository
  methods, preserve encoded IDs, reject unknown payloads, return flag-off 404
  before repository construction, non-disclosing not-found errors, conflict
  409s, and generic safe 503s. Existing card/FSRS contracts are untouched.
- TDD receipts: API route import absent RED; reader method absent RED. Final
  focused suite 31 passed (one existing TestClient deprecation warning),
  Surreal integration 6 passed, Ruff/OpenAPI/diff checks passed. Identity
  suite exited zero with 141 tests collected. Direct rebrand audit exited zero:
  unexpected identities 0 and stale allowlist empty. The audit repair is exact
  anchor/digest maintenance only, including 18 line shifts introduced by the
  existing Task 1 feature-flag patch.
- Ignored evidence: `.superpowers/sdd/study-task-4-report.md`. No Task 4 open
  implementation items remain.

## Task 4 API review repair — 2026-08-12

- Adversarial review found three boundary defects in `06868da8`: feature-off
  malformed requests returned 422 before the handler gate; whitespace and
  explicit-null patch values could escape HTTP validation; and router string
  matching could present generic database failures as 409 conflicts.
- TDD RED was 10 failed / 10 passed. The repair moves the gate to a router-level
  dependency, adds strict nonblank request strings and explicit-null rules
  (target date alone remains nullable to clear it), and introduces typed
  repository not-found/conflict errors. Only exact repository-owned Surreal
  guard markers are translated to conflicts; generic driver failures remain
  base repository errors and project to a safe 503.
- GREEN evidence: all focused Study contracts/repository/scheduler/API tests
  56 passed with one existing TestClient warning; disposable Surreal integration
  6 passed; scoped Ruff, diff-check, and six-path OpenAPI assertion passed.
  Review/commit receipt remains pending at this checkpoint.
- Fresh review of `0d41150a..43537c0d` found one remaining classification
  seam: a driver outage echoing the full transaction also contained dormant
  THROW markers. RED reproduced 2/3 failures for add-source/save-syllabus.
  Exact marker equality now distinguishes actual `repo_query` RuntimeError
  results from echoed SQL; targeted unit is 3/3, focused Study 56/56, and real
  Surreal integration 6/6. A separate follow-up commit/re-review follows.

## Task 5 source linking/readiness — 2026-08-12

- Implemented owned Task 5 files on `codex/study-workbench` at base
  `85c269f4`: read-only `StudySourceService`, bounded readiness schemas and
  flag-gated readiness route, source existence validation + link de-duplication,
  and responsive `StudySourcePicker` delegating uploads to the existing dialog
  callback. No source ingestion/path/body duplication.
- RED receipts: backend collection failed on missing `source_service`; frontend
  Vitest failed on missing picker. GREEN: 15 backend source/progress/upload
  tests passed; frontend focused Vitest 5 passed; ESLint, tsc, Ruff, and
  diff-check passed.
- Open: unchanged legacy `tests/test_study_plans_api.py` expects synthetic source
  links without mocking Source authority; its add-source assertion now sees safe
  source-authority 503 (and the repository-failure assertion cannot reach the
  repository until authority is available). New Task 5 tests cover 404-before-
  mutation and duplicate-link no-op behavior. Unique report:
  `.superpowers/sdd/study-task-5-report.md`.

## Task 5 adjoining API fixture repair — 2026-08-12

- Test-only repair in `tests/test_study_plans_api.py` patches the explicit
  `StudySourceService.validate_source` seam for the in-memory client fixture;
  production Source validation remains fail-closed and unchanged.
- RED was 2 failed/18 passed. GREEN exact API is 20 passed; full Task 4+5 unit
  suite is 71 passed; frontend focused 5 passed; ESLint, tsc, Ruff, and
  diff-check passed. Ignored receipt: `.superpowers/sdd/study-task-5-repair-report.md`.

## Task 5 boundary repair — 2026-08-12

- Repair from `826b80d2` replaces Source materialization with one fixed
  projection, classifies empty/error authority results directly, caps and
  dedupes inputs before any reads, and makes stale duplicate links no-op before
  revision/source checks.
- AddSourceDialog now forwards bounded IDs for single and batch creation while
  retaining zero-argument refresh callbacks. StudySourcePicker awaits links,
  prevents repeats, distinguishes loading/empty/fetch error with retry, and
  only emits post-link callbacks after success with unmount guards.
- RED review regressions were reproduced before implementation. GREEN: full
  Task 4+5 backend `77 passed, 7 warnings`; frontend picker/uploader/use-sources
  `11 passed`; ESLint, tsc, Ruff, and diff-check passed. Disposable integration
  selector is `6 skipped` because its marker/runtime is unavailable. Unique
  ignored receipt: `.superpowers/sdd/study-task-5-boundary-repair-report.md`.

## Task 5 authority and compatibility repair — 2026-08-12

- At base `8e053ec0`, strict RED reproduced four backend and three frontend
  regressions: invalid IDs reached repository construction, encoded IDs were
  double-bound or persisted raw, stale encoded duplicates conflicted, the
  legacy AddSourceDialog callback fired per ID, and the picker ignored the new
  batch callback.
- `normalize_source_id` now returns one canonical encoded string plus the exact
  bound `RecordID`; the router validates it before repository construction and
  before duplicate/revision checks, and valid stale duplicates remain no-op.
  AddSourceDialog restores once-per-operation zero-argument `onSourceCreated`
  and adds once-per-operation bounded `onSourcesCreated`; picker consumes both
  opener callback shapes and links each batch ID sequentially.
- GREEN: backend source `27/27`; full Task 4+5 backend `93/93` with 7
  existing warnings; frontend picker/AddSourceDialog/use-sources `13/13`;
  ESLint, tsc, Ruff, and diff-check passed. Disposable Surreal integration
  remains unavailable/skipped. Unique report:
  `.superpowers/sdd/study-task-5-authority-repair-report.md`.
- Commit `def5a103` (`fix(study): preserve source identity contracts`) is
  complete; post-commit gitleaks scanned one commit (~10.85 KB) with zero
  leaks, range diff-check passed, and the worktree is clean.

## Task 5 runtime repair — 2026-08-12

- Final bounded repair from `def5a103` guards `SOURCE_PROJECTION` optional
  `full_text` with Surreal 2.x `type::is::string` before string functions; a
  disposable real probe confirmed missing text returns `has_text=false` and
  nonblank text returns `has_text=true`.
- Readiness preserves valid items while projecting malformed/wrong-table
  legacy links as bounded `missing` items without wrong-table queries; API
  readiness remains a safe 200 envelope. New source/API regressions and a
  disposable integration test cover both paths.
- GREEN: full Task 4+5 backend selection `96 passed, 7 warnings`; real source
  integration `1 passed`; Ruff and diff-check passed. Frontend intentionally
  untouched. Commit target: `fix(study): handle optional and legacy source records`.

## Task 5 review repair — 2026-08-12

- From clean `7f8c7469`, commit `bc55e483` (`fix(study): require durable
  source links`) closes the final review defects. `normalize_source_id` now
  round-trip-validates bracketed RecordIDs and rejects unescaped interior
  closing brackets as bounded readiness `missing` values without querying or
  aliasing them; simple and correctly escaped canonical IDs retain identity.
  `StudySourcePicker` makes persistence explicit, fails closed if a malformed
  runtime caller omits it, and retains an earlier batch failure/retry action
  after later successes while keeping the source list mounted.
- Strict RED was backend `1 failed/30 passed` and frontend `2 failed/8 passed`.
  Post-commit GREEN: source/API `52 passed, 2 warnings`; full Task 4+5 backend
  `98 passed, 7 warnings`; disposable Surreal readiness integration `1
  passed`; frontend picker/AddSourceDialog/use-sources `15 passed`; ESLint,
  TypeScript, Ruff, diff-check, and staged/HEAD-range gitleaks (0 leaks) pass.
- Unique receipt: `.superpowers/sdd/study-task-5-review-repair-report.md`.
  Changed only `source_service.py`, its tests, `StudySourcePicker.tsx`, and
  its tests. Open items are limited to existing dependency deprecation
  warnings; Task 6 was not touched.

## Task 6 syllabus proposal/approval — 2026-08-12

- Implemented `deeper_notebook/study/syllabus_service.py`, strict propose
  request/API wiring, and service/API tests. Proposal verifies optimistic plan
  revision, every linked source readiness and nonblank evidence, computes a
  deterministic SHA-256 manifest over sorted canonical IDs and fingerprints,
  bounds prompt context, routes through existing `artifact_context` and local
  `study_fast` provisioning, invokes structured generation with a 120-second
  timeout and one repair maximum, and rejects malformed/duplicate/cyclic/
  out-of-bounds output. It saves only a new immutable unapproved version.
- Approval re-reads the exact version, verifies editing lifecycle/revision and
  current source manifest, rejects `sources_changed`, then delegates the
  explicit repository approval. Domain failures map to safe 404/409/422/503
  API responses. Existing Task 4/5 routes remain additive.
- RED: missing service collection failure. GREEN: focused service/structured/
  API 42 passed; full Task 4–6 backend selection 117 passed; Ruff, compileall,
  diff-check passed. Opt-in Surreal repository integration 4/6 passed and 2
  pre-existing Task 3 timestamp-precision failures remain outside scope.
- Report: `.superpowers/sdd/study-task-6-report.md`; commit target:
  `feat(study): gate generation on approved syllabi`. Atomic commit is
  `926b7ede`; post-commit full selection remains 117 passed, and HEAD range
  gitleaks scans ~41.95 KB with 0 leaks. Worktree is clean.

## Task 6 lifecycle repair — 2026-08-12

- Repair from `926b7ede` closes the review defects with an optional
  `lifecycle_action` on `StudyPlanRepository.save_syllabus`. Guarded
  `add_source` moves draft plans to `analyzing_sources`; `propose` atomically
  saves the immutable version and moves to `syllabus_proposed`; `edit` accepts
  `syllabus_proposed` or `editing`, saves the version, and moves/stays editing.
  Approval requires editing and updates state, active version, revision, and
  `source_manifest_sha256` directly from the exact guarded syllabus row in one
  transaction. Existing no-action repository saves retain compatibility.
- Service proposal and API edit routes pass explicit lifecycle actions. New
  unit/API/integration regressions cover strict state guards, stale rollback,
  no orphan records, and a manifest-less API-created plan completing the full
  lifecycle. Approval remains explicit and does not create downstream
  artifacts. Current source manifest is re-read before approval; later
  generation must re-check readiness/drift at its own boundary.
- Repair RED: 4 repository tests failed before production edits. GREEN:
  focused service/structured/API 43 passed; full Task 3–6 backend selection
  126 passed with 7 existing dependency warnings; disposable Surreal plan
  repository integration 7 passed; Ruff, compileall, diff-check, staged
  gitleaks (0 leaks), and post-commit HEAD-range gitleaks (0 leaks) pass.
- Repair commit `bf5c1fd8` (`fix(study): bind syllabus lifecycle atomically`)
  is atomic across the seven owned source/test files; the worktree is clean.

## Task 7 frontend plan home and draft wizard — 2026-08-12

- From `bf5c1fd8`, commit `1fac954c` (`feat(study): add plan home and creation wizard`)
  adds exact bounded Study Plan decoders/API/hooks, typed query keys and
  invalidation, the flag-on `/study` Home composition, and a server-authoritative
  draft wizard. The wizard retains only the created draft ID after save; no
  browser storage, source bodies, local paths, or import behavior were added.
  Existing flag-off StudyDashboard/StudySession and sidebar navigation remain.
- TDD evidence: strict RED was 3 missing-module suites/0 tests; focused GREEN
  was 4 files/9 tests; adjoining Study/page/sidebar/route-frame suite was 8
  files/28 tests. Scoped ESLint and TypeScript passed. Flag-off
  `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 npm run build` passed; staged/post-commit
  diff checks and gitleaks found no leaks.
- Task 7 report: `.superpowers/sdd/study-task-7-report.md`. Import remains
  visibly disabled pending Task 16. No Task 8 work started.

## Task 7 review repair — 2026-08-12

- Repair base `1fac954c` closes the upload callback and runtime request
  validation findings. `useCreateDialogs` forwards bounded source-ID batches
  while preserving the legacy zero-argument callback; the wizard forwards the
  batch callback into the existing AddSourceDialog and links IDs sequentially
  through `useAddStudyPlanSource` with monotonic expected revisions. Existing
  StudySourcePicker retry/partial-failure behavior remains the authority; no
  duplicate ingestion was added.
- `studyPlansApi` now rejects unknown/non-string/oversized/extra runtime
  arguments with exact `Invalid Study Plan request` before URL/string work.
- Repair RED: 3 failures in the 3-file/9-test suite (native TypeError,
  discarded upload callback, dropped batch IDs). GREEN: focused 3/9 and
  adjoining 11/39. Scoped ESLint, TypeScript, flag-off and flag-on builds,
  diff-check, staged gitleaks (23.99 KB/0 leaks), and post-commit gitleaks
  (11.68 KB/0 leaks) pass. Commit `2c0d0abb` (`fix(study): persist wizard
  source uploads`) is atomic across six owned files; worktree is clean.
- Files: `frontend/src/lib/api/study-plans.ts(.test.ts)`,
  `frontend/src/components/study/StudyPlanWizard.tsx(.test.tsx)`, and
  `frontend/src/lib/hooks/use-create-dialogs.tsx(.test.tsx)`. Import remains
  disabled for Task 16; no Task 8 work.

## Task 8 plan workspace and syllabus approval UI — 2026-08-12

- From `2c0d0abb`, added the semantic one-main plan route, URL-bounded nine-tab
  workspace, typed readiness hook/query key, and immutable SyllabusEditor.
  Proposal is enabled only for analyzed plans with every linked source ready,
  fingerprint-available, and represented; editing saves a new monotonic version
  with the guarded revision, while approval confirms and submits the exact
  displayed version. Processing/not-ready/drift/uncovered/dirty/wrong-state
  inputs block approval; 409 errors expose bounded refresh recovery. Existing
  review cards remain linked from Overview and no downstream artifacts were
  generated.
- Strict RED: 4 focused suites failed before production (3 missing modules plus
  missing readiness hook). A semantic audit also fixed the first-proposal 404
  path: `useStudySyllabus` maps only HTTP 404 to `null`, so the workspace can
  expose its proposal action while preserving other errors. GREEN: focused 4
  files/10 tests; adjoining 15 files/47 tests. ESLint, TypeScript, default and flag-off builds, mocked Playwright
  navigation 3/3, diff-check, and gitleaks are the final gates. Report:
  `.superpowers/sdd/study-task-8-report.md`.
- Open items are limited to intentionally reserved later-tab surfaces and the
  existing dependency-warning baseline; do not begin Task 9 in this checkout.

## Task 9 unit artifacts through Evidence Studio — 2026-08-12

- From `f0d910a4`, added `StudyArtifactService.generate_unit` and the bounded
  `study_unit_prompt` adapter. It requires exact approved syllabus/version and
  expected revision, verifies unit/activity source subset, rechecks all linked
  source readiness and fingerprints immediately before each artifact type, and
  recomputes the deterministic source manifest. It creates provisional
  `StudioArtifact` rows, delegates to the existing generation/evaluation path,
  scrubs failed/cancelled records, and links only completed artifacts.
- Supported kinds are exactly study_guide, course_pack, flashcards, quiz, and
  mind_map. API validation and responses are strict metadata-only receipts;
  typed errors map to safe 404/409/422/503. Existing Studio APIs and source
  authority remain unchanged. Repository `study_plan_artifact` methods use
  bounded projections, unique deterministic link records, and retry-safe
  re-reads; migration 41 already supplied the schema/index.
- RED: missing service collection failure. GREEN: focused service/API/Studio
  38 passed; with Evidence Studio API 56 passed; full Task 3–9 backend
  selection 177 passed; repository unit selection 66 passed; disposable real
  Surreal integration 8 passed. Ruff and diff-check pass. Report:
  `.superpowers/sdd/study-task-9-report.md`.
- Open: run compile/sensitive scans and make the atomic commit
  `feat(study): generate unit learning artifacts`; no Task 10 work.

## Task 9 final receipt — 2026-08-12

- Final focused/full gates stayed green after the semantic audit: Task 3–9
  backend selection 177 passed; focused service/API/Studio/Evidence selection
  113 passed; disposable real-Surreal repository integration 9 passed;
  Ruff, compileall, diff-check, and staged gitleaks (48.54 KB/0) passed.
- Atomic commit: `9d01d67` (`feat(study): generate unit learning artifacts`).
  Full-repository gitleaks reports 40 pre-existing baseline findings; staged
  Task 9 scan is clean. No Task 10 work started.

## Task 9 concurrency repair — 2026-08-12

- Fresh review of `f0d910a4..9d01d67` found random StudioArtifact IDs allowed
  concurrent duplicate generation/linking. Repair adds deterministic SHA-256
  identity over plan ID, approved syllabus version, source manifest, unit ID,
  and artifact kind; explicit-ID persistent CREATE; and conditional real
  Studio `pending` -> `running` claim. Local locks are only an optimization.
- Independent service instances with separate lock maps now converge on one
  artifact/link and one bounded in-progress conflict. Failed/cancelled records
  are retryable; completed records and mismatched identities fail closed.
- Strict RED reproduced two generation calls. GREEN: focused
  service/Studio/Evidence/API 88 passed; full Task 3-9 backend 180 passed;
  real disposable Surreal repository integration 10 passed; Ruff, compileall,
  and diff-check passed. The real integration includes independent concurrent
  Studio claim proof. Repair commit: `7d6a4a33` (`fix(study): serialize
  artifact generation retries`). Post-commit HEAD-range gitleaks found no
  leaks.
- Repair files: `deeper_notebook/study/artifact_service.py`,
  `tests/test_study_artifact_service.py`,
  `tests/integration/test_study_plan_repository.py`. No Task 10 work started.

## Task 9 lease and source-drift repair — 2026-08-12

- Second review RED: a source mutation after the durable claim still entered
  Evidence Studio, and running deterministic rows had no restart recovery
  metadata (`2 failed` regressions). Added additive migration 42/up+down and
  bounded `StudioArtifact` owner/start/lease fields. `CLAIM_LEASE_SECONDS=240`
  exceeds the current 180-second generation timeout with margin; owner tokens
  are capped at 128 characters and clock/owner factories are injectable.
- Service now atomically claims pending or expired-running real Studio rows,
  returns bounded `generation_in_progress` for active leases, fences stale
  owner mark/release/clear paths, and immediately rechecks all linked-source
  readiness + manifest after each claim. Drift releases the row to retryable
  pending before generator invocation. Failed/cancelled rows clear ownership.
- GREEN: focused Task9 + Studio/API 45 passed; full Task3–9 backend 184
  passed/7 warnings; disposable real-Surreal integration 11 passed/1 warning;
  Python Ruff, compileall, diff-check, and migration symmetry checks passed.
  Real integration proves two concurrent stale reclaimers converge on one owner
  and stale-owner failure is fenced. Patch gitleaks pipe scanned 35.54 KB
  clean; post-commit HEAD-range scan scanned one commit/24.22 KB clean.
- Commit: `f13af0da` (`fix(study): lease artifact generation claims`). Six
  implementation/test/migration paths are committed; worktree is clean. No
  Task 10 work started.

## Task 11 bounded AI tutor team — 2026-08-12

- Commit `a65f9c8c` (`feat(study): add bounded AI tutor team`) adds the
  feature-gated foreground endpoint and twelve-role local-first assistant
  policy. Remote model/network use requires persisted plan permission plus an
  exact request scope; actions remain inert finite proposals.
- Session creation/replay is deterministic, queued-to-running is a one-winner
  optimistic claim, and completion plus handoff publish atomically against the
  exact plan/syllabus/source-link/network authority and full-text SHA-256 of
  every selected Source. Real Surreal uses bound `RecordID` values for the
  digest guard and classifies its retryable write conflict as a typed 409.
- Source and Research Scout web evidence receive reserved prompt allocations;
  only evidence excerpts actually present in the model prompt are citable.
  Provider payloads, raw prompts, credentials, and hidden reasoning are not
  persisted or returned.
- Final evidence: focused assistant 53 passed/7 dependency warnings; broad
  Study/Studio/source 274 passed/7 warnings; disposable Surreal 14 passed/1
  warning; identity 141; rebrand RC0 unexpected=0/stale=[]; Ruff, compileall,
  Bandit high/high, diff-check, staged and commit-range gitleaks passed. Fresh
  Sol final review reran 65 focused + 14 Surreal tests and APPROVED. Worktree
  clean after commit. Next approved slice is Task 12.

## Task 12 authority-contract repair — 2026-08-12

- Repair started clean at `a30e273d`; RED was 5 files/24 tests with 7 expected
  failures. GREEN is 6 files/26 focused tests and 9 files/34 adjoining Study
  component tests, all passing.
- Frontend response prose and prompts now mirror backend nonblank/bounds for
  multiline text while IDs and action names remain strict. TutorDock
  emits a bounded request ID per new submit; hook retry keeps it stable and
  cancel retains the single-flight lock until an abort-ignoring transport
  settles. Role selection atomically chooses a compatible default mode for all
  twelve Task 11 roles. The final API regression covers multiline/tab prompt
  text.
- Persisted plan preferences now decode model/network/scope fields with the
  backend invariants; Learn projects approved scope only when network authority
  is persisted. Scoped ESLint, `tsc --noEmit`, both flag builds, and diff-check
  pass. Staged and commit-range gitleaks both scanned 14.23 KB with 0 leaks.
- Repair commit: `462aa5d4` (`fix(study): align tutor dock authority contracts`).
  Worktree clean; parent handoff is ready. No Task 13/backend work started.

## Task 12 approval-state gate repair — 2026-08-12

- Fresh RED against `462aa5d4`: the new lifecycle matrix failed 5/8 because
  Learn mounted TutorDock for `draft`, `analyzing_sources`,
  `syllabus_proposed`, `editing`, and `archived` plans. Authorized fixture is
  now `approved` with `approved_syllabus_version: 2`.
- Workspace gates TutorDock to exact Task 11 assistant states
  `approved|generating|active|completed` plus non-null approved syllabus
  version. Other states render an accessible Tutor-unavailable card and cannot
  mount controls or dispatch an invocation.
- GREEN: focused 6 files/32 tests; adjoining Study 9 files/39 tests; scoped
  ESLint, `tsc --noEmit`, flag-on build, and diff-check pass. Pending separate
  commit `fix(study): gate tutor by approved syllabus`.
