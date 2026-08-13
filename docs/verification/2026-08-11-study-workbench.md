# Study Workbench release-proof receipt

## Scope and boundary

- Date: 2026-08-13
- Repository: `Deeper-Notebook`
- Worktree: `codex/study-workbench`
- Scope: Task 18 isolated source-to-study proof, restart parity, authoritative
  regression gates, and the default-on Study Workbench boundary.
- Rollback: set `DEEPER_NOTEBOOK_STUDY_WORKBENCH=0` for the backend or
  `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0` for the frontend. Unset values are now
  enabled by default.
- The proof used only deterministic local PDF/video fixtures, a loopback model
  fixture, a disposable Surreal namespace/database, and exact task-owned
  processes. No user vault, credential, document, external source, or hosted
  provider was used.

## Task 19 feature-build recovery repair — 2026-08-13

The strict pre-edit RED was the stale-wrapper ownership race. The former
`readLock` → stage delete → lock unlink → `open(..., "wx")` sequence allowed a
contender that had read one stale record to delete or replace a successor, and
the named lock file was written directly so a reader could observe empty or
partial JSON. The pre-edit focused wrapper run was `4 passed, 1 failed`; the
failure was the existing parent-SIGKILL process-group probe, while direct
source inspection identified the unlink/reacquire race. The caller's
`frontend/node_modules` symlink was never renamed or mutated.

The wrapper now uses an atomic lock directory acquired by `mkdir`. Its
`owner.json` is written to a nonce-named temporary file, fsynced, and atomically
renamed, so readers see either no record or complete metadata. The v4 owner
binds a random nonce, helper PID, macOS `ps` start token, command/argv hash,
PGID, exact nonce-derived stage, and state. The detached helper remains the
process-group leader and all rsync/Next children inherit that group.

Stale recovery first proves the recorded PID/start/argv identity and every
member of the recorded PGID are gone, then wins a sibling nonce recovery claim
with atomic `mkdir` before renaming the stale lock directory to a unique
quarantine. A contender that loses the claim re-reads current ownership and
never renames or removes a successor. Cleanup applies the same exact nonce,
identity, and atomic-quarantine checks; stage removal is bounded to the
validated exact stage and unlinks nested symlinks without following them.
Malformed, partial, ambiguous, stale-claim, zombie, EPERM, PID-reuse, and
lock/stage/owner symlink states fail closed. Parent SIGKILL leaves the live
helper/group refusing recovery; a stale no-child lock recovers only after the
group is absent.

Fresh evidence: `uv run pytest -q tests/test_feature_build_contract_wrapper.py`
passed `13`; the same wrapper matrix passed ten consecutive runs (`130/130`).
The deterministic regressions cover two simultaneous stale recoverers (one
owner/one refusal), successor-preserving cleanup, complete-metadata readers,
PID start/argv mismatch with and without a live group, parent SIGKILL/live
helper refusal, stale no-child recovery, malformed and symlinked lock/owner/
stage state, and unchanged caller symlink identity. The exact
`NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract` command returned
RC0 with the production Turbopack build and verifier. Test Ruff passed; frontend
lint returned RC0 with the two pre-existing `_stream`/`_options` warnings;
`git diff --check`, the rebrand audit (unexpected `0`, stale `0`), and the
diff-pipe gitleaks scan all passed. No Stage0-specific subset was present.
No package/install, desktop build, listener, app, or user-data mutation was
performed. This repair is source/test scope only; Task 19 native packaging
and installation remain open.

## Review repair correction — 2026-08-13

The fresh Task 18 review findings are closed by the repair slice. The verifier
now persists and re-reads syllabus version, artifact IDs, card/Anki download
and publish receipts, and exact Source Guide/Practice Coach invocation,
session, and response IDs. Only `awaiting_restart` receipts with exact source
hash keys, non-empty owned process identities, and required parity fields are
accepted. Source citations use the authoritative full-text SHA-256 and the
returned Unicode-codepoint bounds; hash, quote, ID, or offset mismatches fail
closed. The production source detail endpoint normalizes Surreal aggregate
rows so the authoritative read remains available.

The real repair proof used a fresh mode-0700 disposable root with namespace
`study_ns_repair20260813d` / database `study_db_repair20260813d` and ports
`47171`–`47174`: prepare exited `5`, verify exited `0`, and the sanitized
report was `PASSED`/`none`. Cleanup proved `owned_processes=0`, `ports=0`,
`container_removed=true`, `root_removed=true`; the task root and all four
listeners were gone, while the external sentinel remained unchanged.

Card version creation and owner linking now share one Surreal transaction;
real concurrent races prove one current/due snapshot, complete links, and no
card/link on an ambiguous owner. The canonical
`NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract` command now
returns `0` through a bounded wrapper that stages a disposable project and
hard-link dependency tree outside the worktree when Turbopack sees the shared
symlink. It does not rename or mutate the caller's `node_modules`, disable
Turbopack, or skip the feature-environment verifier; stale stage/lock pairs
from a crashed invocation are recovered only after the recorded owner is gone.

Repair gates: verifier/scheduler `29 passed`; source/detail API and aggregate
normalization `28 passed`; wrapper safety `2 passed`; real Study Plan/Progress
Surreal matrix `22 passed`; frontend config `3 passed`; canonical feature-build
contract `RC0`; Ruff, compileall, diff-check, lint, and TypeScript `RC0`.

## Final narrow repair — 2026-08-13

The final review's rebrand receipt was stale at `902fb89f`: a strict audit
reported four unexpected and four stale legacy compatibility aliases at the
single `frontend/package.json:12` script line. The exact four allowlist context
hashes, the `frontend-env-alias-v1` coverage digest, and the pinned selector
inventory digest were refreshed after the final line position. The fresh direct
audit is RC0 with compatibility `825`, historical `1749`, migration `584`,
unexpected `0`, upstream `99`, and stale `0`; product identity tests pass.

The verifier now performs a bounded worker process liveness/identity check
before workflow and at handoff, proves exact `api`, `worker`, `frontend`, and
`model` identities at the prepare receipt boundary, and proves exact listener
ownership for every applicable port. Verify requires fresh PID/start/argv
identity for every role and rejects any replacement that reuses another prior
role's identity. The strict handoff REDs cover dead worker, changed identity,
missing listener, reused replacement identity, and fresh all-role replacement.

Fresh two-phase proof after this repair used namespace/database
`study_ns_task18r` / `study_db_task18r` and ports `47321`–`47324`: prepare exited
`5` (`external_restart_required`), verify exited `0` (`PASSED`/`none`), PDF
SHA-256 `42dc1986c574ad8bfd6289eaf67440b58611d138d95552e97955bbba87d20b1d`,
video SHA-256
`b9ed66ed0da82b86c39ef04173cfaae8c573b3ab3cfea0d63a273923816f5c47`, and
external sentinel SHA-256
`eabb19967c401072f9705a861e318d0939699ba5aca184beab869bd79fa329f` unchanged.
Cleanup proved owned processes `0`, listeners `0`, container removed, task
root removed, and external writes `0`; all four replacement roles were fresh.

Final focused verifier/repository/scheduler/wrapper matrix is `73 passed,
7 warnings`; scoped Ruff and diff-check are RC0. No Task 19 or packaging work
was performed.

## Two-phase real proof (original Task 18 receipt)

The prepare and verify phases were separate process invocations over the same
task-owned database. The verifier-local supervisor launched the production API,
worker, frontend, Surreal, and model commands and recorded bounded PID/start
identity and argv digests. The desktop Supervisor was not used because it binds
canonical user state.

| Receipt | Result |
| --- | --- |
| Prepare phase | Exit `5` by design (`external_restart_required`); source-to-study workflow and restart receipt persisted. |
| Verify phase | Separate invocation, exit `0`; replacement process identities were new and durable parity passed. |
| API/frontend/Surreal/model ports | `47121` / `47122` / `47123` / `47124`; all free after cleanup. |
| Namespace/database | `study_ns_task18final` / `study_db_task18final`; disposable and removed with the owned stack. |
| PDF fixture SHA-256 | `c53cdfea5754c74335e25ce635dd34653a569fc79aabe17f2305cb6e863d1fe0` before and after. |
| Video fixture SHA-256 | `b9ed66ed0da82b86c39ef04173cfaae8c573b3ab3cfea0d63a273923816f5c47` before and after. |
| External sentinel SHA-256 | `72b6720b0bdcc14c91357f26dabb26b28bfaad91d587fe08d4fa6f5667db0e79` before and after. |
| External writes | `0`. |
| Final report | Sanitized report outcome `PASSED`, blocker `none`; no credentials, prompts, payloads, document contents, or raw home paths. |
| Cleanup | Task root removed; all four listeners free; no proof-labeled Docker containers; external sentinel retained. |

The workflow crossed the real HTTP/API boundaries for both sources, source
processing/readiness, plan and source links, syllabus proposal/edit/approval,
unit generation, Source Guide and Practice Coach, progress/review cards, Anki
export/preview/publish/import, and post-restart durable queries. The verifier
also checks receipt IDs, source/artifact/syllabus/Anki metadata, fixture hashes,
external write count, frontend Study marker, and exact-owned cleanup.

## Authoritative gates

| Gate | Exact command/result |
| --- | --- |
| Backend non-integration | `PYTHONPATH=. uv run pytest tests/ -q --ignore=tests/integration` — **4386 passed, 1 skipped, 14 warnings**. |
| Ruff | `uv run ruff check .` — exit `0`. |
| Rebrand audit | `uv run python scripts/rebrand_audit.py --check` — RC0; compatibility `825`, historical `1749`, migration `584`, unexpected `0`, upstream `99`, stale `0`. |
| Desktop | `./.build-venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q` — **823 passed, 2 skipped, 3 warnings**. |
| Real Surreal | `SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py tests/integration/test_study_progress_repository.py -m integration_surreal` — **20 passed, 1 warning**. |
| Verifier unit | `uv run pytest -q tests/test_verify_study_workbench.py` — **28 passed, 6 warnings**. |
| Frontend unit | `npm test -- --run` — **229 files, 1624 tests passed**. |
| Frontend lint | `npm run lint` — exit `0`; two existing `_stream`/`_options` warnings in `StudyVoiceTutor.test.tsx`. |
| TypeScript | `npx tsc --noEmit` — exit `0`. |
| Frontend default-on build | `npm run build` — exit `0`; Study routes generated. |
| Frontend explicit-off build | `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build` — exit `0`. |
| Browser default-on | Study + all-screen mocked matrix with Study env unset — **22 passed, 1 skipped**, exit `0`. |
| Browser rollback | `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` same matrix — **8 passed, 15 skipped**, exit `0`; rollback test passed and Study matrix skipped. |
| Full mocked browser gate | `env -u NEXT_PUBLIC_DN_STUDY_WORKBENCH npm run test:e2e:mocked -- --workers=1` — **71 passed, 5 skipped**, exit `0`; six stale Luminous desktop baselines were refreshed against the current committed UI and the focused nine-test visual subset passed. |
| Feature flag contracts | Backend/frontend focused flag tests passed for default-on and explicit `0`. |

The canonical feature-build contract is now green in this worktree. Its
wrapper preserves the production Turbopack build and runs
`node scripts/verify-feature-env-build.mjs` after the build; only a temporary
project/hard-link materialization outside the worktree is used to keep the
shared `node_modules` symlink out of the Turbopack project boundary. The
caller symlink is never renamed or mutated.

The desktop exact gate required local-only build-environment remediation:
`httpx2`/`httpcore2` were removed from `.build-venv` after the regenerated lock
installed them, restoring the repository's expected `httpx` exception behavior.
No source or lockfile bypass was used; `.build-venv` is ignored local state.

## Review and limits

The implementation preserves the flag-off Study dashboard/review surface and
keeps all cleanup fail-closed. Source and artifact IDs are bounded to the
disposable proof namespace, and owner-link conflicts roll back the complete
atomic version/create/link transaction without exposing orphan due cards. Code Review Graph evidence was
unavailable because no graph artifact exists; direct source tracing and the
listed tests are the review evidence. This receipt does not claim native-device
browser, signed/notarized packaging, hosted CI, deployment, or public release.

## Second strict repair receipt — 2026-08-13

The second strict RED reproduced 9 failures in the focused verifier/repository/
wrapper matrix (`59 passed, 9 failed`) before production edits. The repair now
binds the exact Stack role set (`api`, `worker`, `frontend`, `model`), listener
ports, and assistant invocation IDs on prepare and restart; enforces the
preflight owner identity inside the same Surreal transaction; and keeps the
legacy no-owner path transactional with an explicit zero-owner guard. The
wrapper records its owned process group and child identity, proves both are
gone before stale-stage deletion, and fails closed for ambiguous recovery.
Listener probing distinguishes an empty `lsof` result from OSError, timeout,
nonzero, and malformed output. Timestamp-boundary coverage captures one UTC
instant for paired plan fields and passes the real ordering matrix.

Focused GREEN: `uv run pytest -q tests/test_verify_study_workbench.py
tests/test_study_scheduler.py tests/test_study_plan_repository.py
tests/test_feature_build_contract_wrapper.py` — **68 passed**; wrapper-only
regression — **3 passed**. Fresh real Surreal matrix runs twice, each
**26 passed, 1 warning**. Fresh two-phase proof used disposable mode-0700
state (namespace/database `study_ns_task18d6f0` / `study_db_task18d6f0`, ports
`47221`–`47224`): prepare RC5, verify RC0, report `PASSED`/`none`, owned
processes 0, listeners 0, container removed, task root removed, external
writes 0. The exact canonical feature command returned RC0. The earlier full
backend run was `4395 passed, 1 skipped, 14 warnings, 7 failed`; its only
failures were the wrapper stale-recovery regression and stale rebrand metadata.
The latter remained false at the subsequent review HEAD and is superseded by
the final narrow repair above, which refreshed the exact allowlist/coverage/
inventory and recorded a fresh RC0 audit. Remaining limits are native-device,
signed/notarized, hosted-CI, deployment/public-release, and unavailable Code
Review Graph proof; no Task 19 or packaging work was performed.
