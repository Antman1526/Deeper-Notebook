# Study Workbench Task 18 execution context

## Objective

Complete Task 18 from `.superpowers/sdd/task-18-brief.md`: build a two-phase, isolated, restart-aware, end-to-end verifier for the real Study Workbench; run the authoritative backend/desktop/frontend/browser/real-Surreal gates; publish sanitized exact receipts; and change Study Workbench defaults from off to on only after every required proof is green while preserving explicit `0` rollback.

## Required reading

1. `/Users/Antman/.codex/context.md`
2. this file
3. `.superpowers/sdd/task-18-brief.md`
4. `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
5. `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`
6. Task 17 report/context and the current committed diff
7. existing verifier scripts/tests, Supervisor/bootstrap scripts, source upload/processing routes, authentication fixtures, desktop tests, feature-contract tests, and repository/local AGENTS instructions

## Ownership and safety boundaries

Primary owned files:

- `scripts/verify_study_workbench.py`
- `tests/test_verify_study_workbench.py`
- `docs/verification/2026-08-11-study-workbench.md`
- `frontend/src/lib/features.ts` and its flag tests
- `deeper_notebook/feature_flags.py` and its flag tests
- narrowly required verifier fixtures/adjacent regression tests

Preserve all unrelated work and supplied untracked `.codex/agent-context/*`. Do not touch user vaults, credentials, existing databases/namespaces, user ports, installed apps, or external fixtures. Never broaden cleanup from exact owned PIDs, listeners, temp roots, namespaces, and files. Do not delegate.

## Required design

- Start strict RED with the named verifier test before production edits.
- Use a unique realpath-validated, non-symlink, mode-0700 task root and unique Surreal namespace/database. Refuse unsafe/broad paths.
- Use task-only explicit ports after listener preflight; record PID/start nonce/command ownership; never kill unrelated processes.
- Generate bounded synthetic PDF and video fixtures locally. Record their hashes before and after. Never use user documents or outbound sources.
- Exercise real HTTP/API boundaries and real processing authority: authenticate, upload PDF/video, wait with deadlines/backoff, create/update plan, link sources, readiness, propose/edit/approve syllabus, generate one unit, invoke Source Guide and Practice Coach, progress/review cards, Anki export/import, and durable query receipts.
- Phase `prepare` must persist a sanitized receipt and exit exactly 5 to demand a real process restart. It must not self-claim restart proof.
- Phase `verify` must reject missing/stale/mismatched receipt/PID nonce/source hashes, verify that prior owned processes are gone and replacement identities are new, then prove durable parity after restart.
- Maintain an external read-only sentinel fixture outside the task root. Hash before/after and assert zero writes. Do not clean it.
- Sanitize report output: no credentials, tokens, full prompts, document contents, raw local home paths, database passwords, or provider payloads.
- Cleanup exact owned processes, ports, namespace/database, and task files on success/failure; assert ports free and no owned orphans. Preserve sanitized committed verification docs only.
- Do not flip feature defaults until all verifier and authoritative gates are green. Then default true in backend/frontend while explicit `0` remains false; prove both.

## Required verification

Run all commands named in the brief, including full non-integration backend, Ruff, rebrand audit, desktop tests, full frontend unit/lint/tsc/build/feature contract/mocked e2e, real Surreal integration, and real two-phase prepare/verify. Record exact counts and known pre-existing warnings separately. A skipped/failed authoritative lane blocks default-on unless Sol explicitly narrows the plan.

After final proof, run diff-check and staged sensitive scan, update this context and `/Users/Antman/.codex/context.md`, stage only owned files, and commit exactly `docs(study): close workbench release proof`.

## Done criteria

- Unit tests prove path/PID/nonce/restart/sentinel/hash/cleanup/failure behavior.
- Real prepare exits 5 and real verify exits 0 after an actual stack restart.
- End-to-end receipt covers PDF and video source-to-study flows, tutor, progress/cards, Anki export/import, and persistence.
- External sentinel hash unchanged; external writes 0; owned processes/ports/roots removed.
- All authoritative release gates green.
- Study defaults on only after proof; explicit `0` rollback green across backend/frontend/build contracts.
- Sanitized verification doc contains exact receipts and honest limits.
- Atomic commit created and tracked worktree clean.

## Evidence log

Append RED receipt, milestones, exact commands/counts, process/port/namespace receipts, prepare/verify exits, hashes, cleanup proof, commit hash, and open limitations here.

## Sol execution plan (2026-08-12)

Implement this as one bounded release-proof slice, without redesigning Study product contracts:

1. **Reconnaissance and RED.** Inspect the existing two-phase verifier safety code (`scripts/verify_overlay_foundation.py` and its tests), desktop `Supervisor`, source upload/status endpoints, model/credential defaults, Study API schemas, migration runner, and Task 17 browser receipts. Add strict verifier tests first and capture the named missing-verifier RED. Unit tests must cover unsafe/broad/symlink roots, mode 0700, explicit loopback URLs/ports, PID/start-nonce identity, exact prepare exit 5, stale/missing/tampered receipt rejection, source and external-sentinel hash preservation, sanitization, exact-owned cleanup, deadline bounds, and default flag precedence.
2. **Isolated runtime harness.** The verifier owns one realpath-validated temp root and a disjoint read-only sentinel root. Use unique explicit ports and a unique Surreal namespace/database. Reuse the production API, worker/source-processing authority, frontend build/server, migrations, and a real Surreal v2 process/container. Prefer the repository desktop `Supervisor` only when it can be bound entirely to the task root without touching canonical desktop state; otherwise implement a verifier-local process supervisor that launches the same production commands and call this limitation out honestly. Record each child PID, process start token/nonce, argv digest, and listener. Never use `pkill`, broad process matching, a user database, user credentials, or user source files.
3. **Synthetic local model boundary.** Launch a task-owned loopback OpenAI-compatible deterministic test provider and seed only the disposable namespace with a synthetic Credential, language Model, and default model assignments. It must be incapable of outbound access and return bounded schema-valid syllabus/assistant/artifact responses. Do not weaken production provider validation or inject test behavior into product source. If the production structured-generation protocol cannot be satisfied by a bounded local fixture, stop with an exact blocker instead of bypassing the real API.
4. **Prepare phase.** Generate deterministic bounded PDF and video fixtures under the owned root, hash them and the external sentinel, authenticate through the real local API boundary if auth is enabled, upload both through the actual source endpoint, wait with monotonic deadlines/backoff for processing, then use only HTTP APIs to create the plan, link both sources, check readiness, propose, edit, approve, generate one unit, invoke Source Guide and Practice Coach, project/record progress, create/review native cards, export an Anki package, preview and explicitly publish its import. Persist only bounded IDs, hashes, counts, lifecycle/revision receipts, child identities, namespace, and sanitised failure codes. Stop exact owned children but retain disposable database/root state required for restart. Exit exactly 5 and never run the verify phase in the same invocation.
5. **Verify phase.** Validate the receipt before launching anything; reject stale/mismatched arguments, roots, ports, namespace, sentinel/source hashes, or already-completed state. Prove every prior owned PID/start identity is gone, then launch a new production stack with new identities over the same task-owned database. Re-read plan/syllabus/artifact/assistant/progress/card/Anki receipts through real APIs and bounded direct parity queries where no read endpoint exists. Verify PDF/video hashes, external writes zero, frontend Study route 200/render marker, and durable parity. Mark the sanitized receipt complete, stop exact owned children, remove the unique namespace/container/task artifacts except the requested report, prove ports free/no owned orphans, and exit 0.
6. **Default-on boundary.** Do not change either default until RED/GREEN unit proof, real prepare/verify, required integration, and Task 17 flag-on/off browser gates are green. Then set backend and frontend default true while preserving explicit `0` as false, update exact flag tests, and rerun both default and explicit rollback builds/browser contracts. No legacy alias or unrelated flag changes.
7. **Authoritative gates and evidence.** Run every Task 18 command exactly. If the canonical feature-build command hits the already-proven worktree symlink/Turbopack boundary, record its exact non-code failure and run the repository-equivalent Webpack verifier, but do not silently label the canonical lane green; Sol will decide whether Task 19 packaging supplies the authoritative replacement. Any other failure must be fixed or reported as blocking. Commit the sanitized verification document with exact counts, hashes (never secrets/paths), cleanup receipt, known warnings, and honest limitations using the exact requested subject.

Done means the verifier proves a real two-invocation restart, full source-to-study durability for both PDF and video, exact-owned cleanup, zero external writes, authoritative regression gates, default-on plus explicit-zero rollback, an atomic commit, and a clean tracked worktree.

## Final execution receipt — 2026-08-13

- Fresh marked proof root: `/var/folders/7t/0h7852yd50v0kj5wrlw487980000gn/T/dn-study-task18-proof.w0phvsli` with task root and disjoint external sentinel root, all mode `0700`; namespace/database `study_ns_task18final` / `study_db_task18final`; ports `47121–47124`.
- Separate live invocations: prepare exit `5` (`external_restart_required`), then verify exit `0` (`PASSED`, blocker `none`). PDF SHA `c53cdfea...d1fe0`; video SHA `b9ed66ed...f5c47`; external sentinel SHA `72b6720b...0e79` unchanged; external writes `0`; task root removed; all listeners free; no proof-labeled containers.
- Default-on flag proof: backend/non-integration `4386 passed, 1 skipped, 14 warnings`; verifier unit `17 passed, 6 warnings`; real Surreal plan/progress `20 passed, 1 warning`; desktop `823 passed, 2 skipped, 3 warnings`; Ruff/rebrand RC0; frontend unit `229 files / 1624 tests`, lint RC0, `tsc` RC0, default/off builds RC0.
- Browser: default-unset Study + all-screen `22 passed/1 skipped`; explicit Study=0 + Luminous=0 rollback `8 passed/15 skipped`; exact `npm run test:e2e:mocked -- --workers=1` default-unset `71 passed/5 skipped` after refreshing exactly six stale Luminous desktop snapshots. Generated result dirs removed and `frontend/test-results/.last-run.json` restored byte-for-byte.
- Canonical feature-build contract remains blocked only by known Turbopack refusal of the worktree `frontend/node_modules` symlink; equivalent Webpack build + verifier RC0. Desktop `.build-venv` httpx2/httpcore2 removal was local build-env remediation only.
- Verification doc added at `docs/verification/2026-08-11-study-workbench.md`; exact requested commit `df54efbb` (`docs(study): close workbench release proof`) created after final scans. Tracked worktree is clean; supplied contexts remain intentionally untracked. Open limits: no native-device, signed/notarized, hosted CI, deployment, or public-release proof; Code Review Graph artifact unavailable.

## Review repair execution receipt — 2026-08-13

- Strict RED reproduced before edits: verifier/scheduler focused suite had 5
  failures for dropped restart parity, permissive completed/empty receipts,
  snippet citation authority, and cleanup assertions; the exact canonical
  feature-build contract failed Turbopack on the shared `node_modules`
  symlink. A long-source/nonzero-offset RED also proved snippet hash/offset
  authority was insufficient. The authoritative source-read RED was a real
  HTTP 500 (`int() argument ... not 'dict'`) when Surreal returned an aggregate
  object; the added normalization unit first failed with ImportError.
- Repair GREEN: `uv run pytest -q tests/test_verify_study_workbench.py tests/test_study_scheduler.py`
  — 29 passed; real
  `SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py tests/integration/test_study_progress_repository.py -m integration_surreal`
  — 22 passed; frontend config — 3 passed; exact canonical
  `cd frontend && NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract`
  — RC0. Scoped Ruff, compileall, lint, TypeScript, and diff-check are RC0.
- Fresh real proof used namespace/database `study_ns_repair20260813d` /
  `study_db_repair20260813d`, ports `47171–47174`: prepare RC5, verify RC0,
  sanitized report `PASSED`/`none`; cleanup receipt proved owned processes 0,
  listeners 0, container removed, task root removed, and external writes 0.
- Implemented strict receipt parity/assistant identity persistence, full-source
  citation fingerprints and bounds, exact teardown assertions, atomic
  card-version/owner/link transaction with real races, and a bounded
  canonical-build project staging wrapper that never renames the caller's
  `node_modules` symlink. The wrapper safety/crash-recovery test is 2 passed;
  `api/routers/sources.py` now normalizes Surreal aggregate count rows needed
  by the authoritative source read.
- Repair commit `60e4e365` has exact subject `fix(study): harden release proof`.
  Supplied untracked contexts remain preserved. Open limits remain native
  device, signed/notarized, hosted CI, deployment/public release, and missing
  Code Review Graph artifact; no Task 19 or packaging work.

## Second strict repair execution receipt — 2026-08-13

- Strict RED before production edits: focused verifier/repository/wrapper matrix
  `59 passed, 9 failed`, including role/port omissions, assistant invocation
  identity, owner races, parent-only build crash recovery, listener probe
  refusal, and timestamp precision/order coverage.
- GREEN focused matrix: `uv run pytest -q tests/test_verify_study_workbench.py
  tests/test_study_scheduler.py tests/test_study_plan_repository.py
  tests/test_feature_build_contract_wrapper.py` — `68 passed, 7 warnings`;
  wrapper-only regression `3 passed`. Assistant API focused tests were `22
  passed, 7 warnings`.
- Real Surreal matrix was run twice from fresh namespaces/databases; each run
  returned `26 passed, 1 warning`. Owner races cover zero, different, and
  disappearing owners; timestamp boundary uses explicit paired values and
  loaded ordering stays valid.
- Fresh two-phase verifier proof: disposable mode-0700 root, namespace/database
  `study_ns_task18d6f0` / `study_db_task18d6f0`, ports `47221`–`47224`; prepare
  RC5, verify RC0, sanitized `PASSED`/`none`, owned processes 0, listeners 0,
  container removed, root removed, external writes 0. Canonical feature-build
  command RC0; scoped Ruff, rebrand audit, and diff-check RC0.
- Full backend was run before final wrapper/rebrand corrections (`4395 passed,
  1 skipped, 14 warnings, 7 failed`); only wrapper stale recovery and stale
  rebrand metadata failed, and both are now corrected with focused GREEN proof.
- Files changed are the verifier, Study service/models/plans/repository,
  feature-build wrapper, integration/unit tests, rebrand metadata, and the
  sanitized verification report. Supplied untracked contexts and unrelated
  `desktop/build/__pycache__/` remain unstaged. Commit `902fb89f` has exact
  subject `fix(study): close restart and build races`.
- Open limits: native-device, signed/notarized, hosted-CI, deployment/public
  release, and Code Review Graph proof remain unclaimed; no Task 19 or packaging.

## Final narrow repair execution receipt — 2026-08-13

- Strict RED before source edits: five new handoff regressions failed with
  missing `assert_stack_handoff`/`assert_replacement_identities`; the direct
  rebrand audit was RC1 with exactly four unexpected and four stale
  `frontend/package.json:12` `ONP_` compatibility entries.
- Implemented a bounded worker poll/identity readiness check; final prepare
  handoff now snapshots live unchanged PID/start/argv identities for `api`,
  `worker`, `frontend`, and `model` and checks exact listener ownership for
  API/frontend/model. Verify rejects any reused prior role identity and proves
  all four replacements fresh before durable parity.
- Rebrand allowlist context hashes, `frontend-env-alias-v1` coverage digest, and
  pinned selector inventory digest were refreshed. Fresh audit RC0: compatibility
  `825`, historical `1749`, migration `584`, unexpected `0`, upstream `99`,
  stale `0`; product identity tests passed.
- Focused verifier/repository/scheduler/wrapper matrix: `73 passed, 7
  warnings`; verifier-only `28 passed, 6 warnings`; scoped Ruff and
  `git diff --check` RC0.
- Fresh real two-phase proof after the repair used namespace/database
  `study_ns_task18r` / `study_db_task18r`, ports `47321`–`47324`: prepare RC5
  (`external_restart_required`), verify RC0 (`PASSED`/`none`), PDF SHA
  `42dc1986...d20b1d`, video SHA `b9ed66ed...f5c47`, external sentinel SHA
  `eabb1996...fa329f` unchanged, external writes `0`; exact owned processes,
  listeners, container, and task root were removed.
- Final repair commit is pending exact subject `fix(study): verify complete
  restart handoff`; no Task 19 or packaging work. Open limits remain native
  device, signed/notarized, hosted-CI, deployment/public-release, and missing
  Code Review Graph proof.

## Final receipt wording repair — 2026-08-13

- The latest review found the tracked verification receipt's literal `ONP_`
  wording was itself scanned as an unexpected active selector, making its
  claimed rebrand RC0 false at `bfe05fba`.
- Reworded only that sentence to “legacy compatibility aliases”; no allowlist,
  coverage, or selector metadata changed because the source inventory remained
  unchanged. Product identity `uv run pytest -q tests/test_product_identity.py`
  passed `141`; `git diff --check` passed; staged patch gitleaks via
  `git diff --cached --binary | gitleaks detect --pipe --no-banner --redact`
  reported no leaks.
- A pre-context-edit direct audit already returned RC0 with summary
  compatibility `825`, historical `1749`, migration `584`, unexpected `0`,
  upstream `99`, stale `0`; final audit is rerun after this context update and
  before the exact docs-only commit. Open limits unchanged; no Task 19.

## Commit receipt — 2026-08-13

- Final direct audit after the context update returned RC0 with summary
  compatibility `825`, historical `1749`, migration `584`, unexpected `0`,
  upstream `99`, stale `0`.
- Exact docs-only commit `d66f7464` has subject
  `docs(study): correct rebrand proof receipt`. Commit-range gitleaks over
  `bfe05fba..HEAD` scanned one commit/76 bytes and found no leaks. The tracked
  worktree is clean; supplied `.codex/agent-context/*` remain untracked.

## Task 19 build-recovery handoff — 2026-08-13

- The feature-build wrapper's stale lock race is repaired in the Task 19
  source/test slice. The old per-child lock could write `child:null` after a
  child exit and before a parent crash, leaving recovery unable to prove the
  complete ownership set absent.
- A detached helper is now the recorded process-group leader. It writes
  PID/PGID/nonce/stage before creating any staging/build child; all children
  inherit that group. Recovery deletes only the exact validated stage once
  both helper PID and group are absent. Live groups, malformed locks,
  ambiguous state, and symlink stages fail closed; caller `node_modules`
  remains untouched.
- Wrapper tests are `5 passed` across five consecutive runs (`25/25`), and
  exact canonical `NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract`
  is RC0. No Task 18 verifier/source behavior changed. Task 19 package,
  installation, and installed-app smoke proof remain unperformed.
