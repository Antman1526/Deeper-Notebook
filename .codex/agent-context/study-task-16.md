# Study Workbench Task 16 context

## Scope

Implement deterministic Anki export plus feature-gated HTTP/UI workflows on top
of approved Task 15 commit `d0e7d7c1`. This task owns export, upload preview,
explicit publish, job/receipt status, opaque download, strict frontend decoders,
hooks, and the Study Plan Anki panel. It must not add a second card/scheduler,
silently publish an upload, expose filesystem paths, or alter Task 15 security.

## Approved contracts

- Read `.superpowers/sdd/task-16-brief.md` completely. The previously approved
  design and task brief are the implementation authority; no new design choice
  or user question is required.
- Pin `genanki==0.13.1` only after RED. Regenerate `uv.lock`; do not loosen other
  dependencies. Confirm MIT license and audit the frozen production closure.
- Preserve Task 15 `inspect_anki_package()` and `import_anki_package()` as the
  sole untrusted-package boundary and native publication adapter. Preview must
  inspect only; explicit publish must re-inspect the same task-owned upload and
  use a caller request ID. Upload alone never mutates cards/links/receipts.
- Export only the plan's native `study_plan_card` + current `StudyCard` data.
  Bind an approved/generating/active/completed plan and active syllabus. Use
  fixed bounded projections and stable IDs/GUIDs derived from canonical plan,
  card, version, and export schema. Do not export raw sources, credentials,
  assistant memory, or imported/native FSRS scheduling as Anki authority.
- Escape field content before `genanki`. Basic/reverse/Cloze round-trip must be
  deterministic at semantic identity level. ZIP byte-for-byte equality is not
  required if upstream ZIP timestamps differ; receipt/package semantic hash and
  stable note/model/deck/card identities are required. If byte determinism can
  be made safe without patching genanki internals, prefer it.
- Generate in a chmod-0700 task temp root, validate the completed archive with
  Task 15 inspector, then atomically move to a bounded application-controlled
  export root. Return only opaque IDs/receipts; download endpoint resolves and
  revalidates inside root with no traversal/symlink/path disclosure.
- Upload uses bounded streaming with `.apkg`/content checks and a private
  application-controlled import root. Use opaque upload/job IDs. Do not trust
  client paths/names. Delete/recover temp files on failure without broad cleanup.
- Feature-off must return uniform 404 before body/path/query validation. Strict
  request/response schemas forbid extras, trim IDs, bound uploads/options, and
  map invalid package 422, not-found 404, conflict 409, safe generic 503.
- Panel must be integrated into the Study Plan workspace/package tab under the
  existing Study flag; it handles loading, upload progress/processing, preview,
  transformed/skipped/rejected summary, explicit Import confirmation, export,
  download, retry, and safe error states. Keyboard/focus and 320px containment
  are required. No generic AI aesthetic; reuse current design system.
- Add strict frontend runtime decoders; third-party/backend responses are
  untrusted. React Query keys must be plan-scoped and targeted invalidation must
  refresh plan cards/progress after import.
- Preserve all unrelated/untracked context files. Do not commit this context.

## Proof and done criteria

- Exact RED for missing export/router/component before production.
- Backend unit/API includes feature-off malformed uniform 404, upload bounds,
  no mutation at preview, explicit publish, request replay/mismatch, export
  stable semantic IDs, Basic/reverse/Cloze round-trip, path/symlink/root safety,
  safe errors, cleanup, and download response headers/no path disclosure.
- Real disposable Surreal test for export native cards and import explicit
  publication/replay across actual API/repository if the existing fixture lane
  supports it.
- Frontend tests for preview-before-publish, transformed/skipped/rejected,
  loading/error/retry, stable request retry, explicit confirm, export/download,
  feature/lifecycle gating, decoder failure, keyboard/focus.
- Required gates from brief: import/export/API tests, relevant adjoining Study
  tests, Ruff, compileall, ESLint, tsc, flag-on/off Next builds, uv lock check,
  frozen pip-audit with only documented Pillow baseline, dependency license,
  diff-check, migration unaffected, staged/range gitleaks.
- Separate commit `feat(study): add Anki package portability`.
- Append concise milestones/results to this file and `/Users/Antman/.codex/context.md`.

## Milestones and durable receipts

- RED before production: missing `api.routers.study_anki`, export contracts,
  and `AnkiPackagePanel` tests failed; strict contract tests were then authored.
- GREEN backend: 46 Task16 tests passed (one pre-existing Starlette/httpx
  warning), including valid preview → explicit publish/replay/mismatch, upload
  413 bound, cleanup, symlink/root safety, stable export IDs, and Task15 exact
  index/numeric-ID regressions. Adjoining Study unit/API suites passed 121 and
  disposable real-Surreal import integration passed 3.
- GREEN frontend: 14 targeted workspace/panel/decoder tests, ESLint, and tsc;
  panel retry stores the selected file and reuses the same request ID for
  publish retries. Both flag-on and flag-off Next builds were independently
  verified by root.
- Audits: `uv lock --check`, Ruff, compileall, Bandit, and diff-check passed.
  `genanki==0.13.1` is MIT; cached-property BSD, chevron MIT, frozendict
  LGPL-3. Normal frozen pip-audit is environment-blocked by temporary-venv
  ensurepip SIGABRT. Root's no-deps/disable-pip fallback found only the known
  25 Pillow 11.3.0 advisories and no new genanki-closure matches.
- Open concerns recorded in `.superpowers/sdd/task-16-report.md`: bounded
  export N+1 repository reads, large combined HTTP router, and no disposable
  export-specific Surreal fixture. No deploy or external publication.
- RED exposed imported reverse/Cloze kind loss because Task 15 previously
  stored only transformed front/back. Narrowly added exact finite
  `anki_card:<kind>:` markers to Task 15's opaque `artifact_card_id` (Basic
  keeps legacy IDs); Task16 helper recovers only `reverse`/`cloze`, and unit plus
  real-Surreal import tests remain green. Export options are strict import
  selectors intentionally no-op for the one native Study Plan deck.

## Task 16 repair — RED/GREEN durable portability receipt (2026-08-12)

- Strict RED was recorded before production edits: baseline Task16 import/export/API was 46 passed; repair regressions initially failed on original note/template identity, Cloze tokens, compatibility persistence, migration 45, durable repositories, canonical roots, claim conflict, and restart status.
- Repair retains bounded original cleaned note fields/source note IDs/template ords in `AnkiCardPreview`, persists them in additive `study_anki_card_compat`, and reconstructs one reverse note per `(package_sha256, source_note_id)` with raw Cloze fields. Native StudyCard/FSRS remains sole scheduler authority. Export receipt count/model/deck/GUID identity is asserted against post-write native inspection.
- Migration 45 up/down adds strict compatibility, job, and export metadata tables. `AnkiJobRepository` uses durable fixed projections, owner-token/lease CAS claims, same-request replay/in-progress fencing, expired-owner reclaim, stale-owner fail/complete fencing, and bounded expiry cleanup. `AnkiExportRepository` rehydrates opaque downloads with hash/root checks. Production metadata is durable by default; in-memory mode is only a private unit-test injection seam. Caches no longer unlink durable files.
- Canonical storage derives from `deeper_notebook.config.DATA_FOLDER`, rejects broad/symlink/non-owned roots, and stores validated opaque tokens. Real disposable Surreal migration45 integration proved fresh repository status, concurrent same-request owner/replay, different-request conflict, expired reclaim/stale fencing, export metadata/download rehydration, and basic/reverse/Cloze import→native compatibility→export→inspect semantics: 6 passed. Focused repair + Task15/16 suites: 54 passed.
- Remaining verification is the full adjoining Study/frontend/security/tooling gate and commit. Preserve all untracked context files; do not stage this file.
- Follow-up RED/GREEN hardening: export inspection now counts native `cards`, so reverse receipts report 2 and multi-cloze receipts report one per native cloze ord; plan card/compat projections are ordered and export input is canonically sorted for stable receipt identity. TTL cleanup is two-phase with same-root tombstones, metadata delete fencing, authority-aware bounded tombstone sweep, and live-file preservation. Durable active metadata create has transactional 256-row cap with safe capacity error; real cap test fills 256 and rejects 257.
- Latest focused repair/API/import/export: 61 passed, 1 known Starlette/httpx warning. All Study unit tests: 347 passed, 7 existing warnings. Real Anki portability integration: 8 passed; existing import + portability: 10 passed. Frontend targeted Anki/workspace/decoder: 14 passed. Scoped Ruff/compileall/uv lock/diff-check clean. Bandit has only pre-existing low-confidence B608 SQL construction in Task15 repository (4 locations); no new repair B110/B608 findings.

## Task 16 final repair closeout (2026-08-12)

- RED receipt: before production edits, c3 Cloze ordinals failed the old 0/1 validation, partial multi-Cloze export expanded a one-ordinal import to all raw tokens, and a simulated native publish followed by durable `complete()` failure left replay metadata `publishing` without a receipt binding.
- Production GREEN: Cloze-only ordinals are bounded 0..999 while Basic/reverse remain <=1; partial multi-Cloze subsets fail closed with typed 409; same-request receipt replay repairs durable job metadata under owner fencing, preserving different-request conflicts and stale-owner rejection. Migration 45 mirrors the model-aware bound.
- Evidence: focused 64 passed (1 known Starlette/httpx warning), all Study 351 passed (7 existing warnings), real-Surreal 11 passed, frontend targeted 14 passed, Ruff/compileall/uv lock/diff-check clean. Bandit has only pre-existing low-confidence B608 findings. Frozen pip-audit strict mode hit temporary-venv `ensurepip` SIGABRT; no-deps/disable-pip fallback found only the existing 25 Pillow advisories and no new genanki closure.
- Closeout remains: stage only the six owned implementation/test files, run staged/range gitleaks, commit `fix(study): preserve exact Anki card semantics`, and preserve all untracked context files.

## Task 16 replay/package-authority repair (2026-08-12)

- Fresh review RED at `46df5196`: same plan/request/options replay could bind a
  receipt from another package and complete the wrong job; terminal `complete`
  and `fail` lacked a `status = 'publishing'` CAS. New endpoint/unit/real-
  Surreal regressions failed before production edits.
- Repair adds exact replay binding across receipt package hash, current job
  package hash, claim package hash, request ID, and options hash. Mismatches
  return typed 409 before metadata mutation, including already-published
  replay. Durable terminal writes now require exact job package/claim package,
  request/options/owner/lease, and `status = 'publishing'`.
- GREEN: focused Anki import/export/API/repair 67 passed (one known
  Starlette/httpx warning); all Study unit 354 passed (7 existing warnings);
  real-Surreal portability 9 passed; frontend targeted 14 passed; Ruff,
  compileall, lock, migration, Bandit, and diff-check passed.
- Open: staged/range gitleaks, report/context update, and exact repair commit.

## Canonical payload authority fallback closeout — 2026-08-12

- Terra fallback executed the frozen, Sol-approved payload-authority repair
  after the recorded Luna unresponsive receipt. Strict RED: both durable
  crash-repair and already-published same package/request/different options
  cross-bound; repository claim/terminal interfaces lacked a payload hash; the
  real-Surreal calls failed their missing payload contract.
- Added migration-45/model/projection field `claim_payload_sha256`, atomic
  claim/replay/CAS binding, and repository-owned canonical payload helper.
  Router hashes full inspection/options through this helper before claiming;
  it canonicalizes raw `study_plan:<id>` identically to the publisher.
- `_assert_replay_authority` now requires receipt/current claim payload equality
  alongside package/request/options; published and crash-repair fail closed.
  Fresh returned receipts are compared before durable complete, so a divergent
  publisher receipt receives 409 without terminal completion.
- Evidence: focused 73 passed; all Study 360 passed; real-Surreal combined 12
  passed; frontend targeted 14, ESLint and tsc passed; Ruff/compileall/lock/
  migration/diff-check passed. Bandit unchanged: four existing low-confidence
  B608 findings. Remaining closeout: staged/range gitleaks and exact commit.
