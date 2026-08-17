# Study Workbench Task 19 execution context

## Objective

Complete Task 19 from `.superpowers/sdd/task-19-brief.md`: establish exact checkout/package preconditions; build, verify, recoverably install, and smoke the macOS package in an isolated data root; obtain fresh-context whole-diff approval; and publish the final evidence-only acceptance report without overstating signing, notarization, hosted, or device proof.

## Required reading

1. `/Users/Antman/.codex/context.md`
2. this file
3. `.superpowers/sdd/task-19-brief.md`
4. `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
5. `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`
6. `docs/verification/2026-08-11-study-workbench.md`
7. Task 18 report/context and current HEAD
8. repository package/build/release documentation and scripts, desktop launcher/data-root tests, and applicable AGENTS/verification/security/git skills

## Ownership and authority

The final acceptance report is the planned committed file. Product source changes are forbidden unless a fresh Critical/Important defect is reproduced RED, repaired in its own atomic commit, and independently re-reviewed. Preserve unrelated processes, installed apps, backups, user data, secrets, and all supplied untracked contexts. Do not push, merge, publish, notarize, or deploy. Do not delegate.

## Precondition receipt

Before any package action record:

- exact absolute checkout, branch, HEAD, base `e61e5d82`, tracked tree hash, source inventory hash, submodule state if any;
- `git status --porcelain=v1`, preserving the exact allowed untracked inventory;
- existing `/Applications/Deeper Notebook.app` identity, codesign details, inode/mtime/size, recursive deterministic content hash, and whether it is running;
- relevant listeners/processes with PID/start/command ownership;
- free disk, architecture, macOS version, build tool versions, and package output destinations;
- exact rollback/backup path chosen.

Stop if tracked files are dirty, output would overwrite unrelated data, an installed-app backup target already exists, or any process/path ownership is ambiguous.

## Build and artifact proof

- Read and invoke the repository's exact `make build-mac` target with explicit PATH and `DEEPER_NOTEBOOK_CODESIGN_IDENTITY=-`; do not invent a bypass.
- Require its backend/desktop/frontend preconditions and package-content checks.
- Verify app and DMG identities/content, arm64 binaries, `codesign --verify --deep --strict`, `hdiutil verify`, Info.plist/bundle identity/version, absence of source secrets/dev artifacts, and deterministic hashes/inventory.
- Ad-hoc signing is local package evidence only. Record expected `spctl` rejection and never call it notarized or Gatekeeper-distributable.

## Recoverable install and isolated smoke

- Preserve an existing app by an atomic sibling rename to `/Applications/Deeper Notebook.app.backup-study-<timestamp>` after exact hash receipt. Never delete it.
- Stage/copy and independently verify the fresh app before atomic swap. On any failure, restore the backup and verify its hash.
- Launch only the fresh installed app with task-owned absolute `HOME`, `DEEPER_NOTEBOOK_DATA_DIR`, and non-conflicting ports. Record parent/child PIDs, start times, commands, and nonce. Never kill by broad name.
- Prove authenticated readiness and the installed Study route; run the bounded PDF/video plan, syllabus approval, tutor, progress/cards, Anki export/import, restart persistence, redaction, and external read-only sentinel checks using Task 18 verifier receipts where possible.
- Stop exact owned children, verify ports free, task-owned temporary roots cleaned, external sentinel hash unchanged, and installed app/backup states recorded.
- Leave the newly installed verified app only if all acceptance passes. Otherwise restore the prior app recoverably.

## Review and final report

After package proof, request a zero-history `sol_reviewer` with base `e61e5d82`, full diff, approved design/plan, global/task contexts, exact gates, dependency audit, browser/real-DB/verifier/native/package receipts, rollback commands, and known limitations. Any High/Important finding requires RED and a separate repair commit followed by re-review.

Then update only `docs/verification/2026-08-11-study-workbench.md` with every touched file and justification, exact counts/commands/exits/hashes, default-on and explicit rollback proof, feature inventory, package/install receipts, backup/restoration path, and residual limits. Run diff-check, rebrand audit, sensitive scan; commit exactly `docs(study): publish workbench acceptance`.

## Done criteria

- Clean tracked precondition and preserved untracked inventory.
- Exact build target succeeds; app/DMG verify; arm64/ad-hoc signing claims are exact.
- Recoverable installed-app swap and isolated real smoke/restart persistence pass, or prior app is fully restored with failure documented.
- No external fixture writes; no owned orphan processes/listeners/temp roots.
- Fresh whole-diff Sol reviewer APPROVES with no High/Important finding.
- Final evidence report is exact, sanitized, and committed separately.
- Worktree clean except preserved supplied untracked contexts; no push/merge/deploy.

## Evidence log

Append precondition receipt, build/package hashes, codesign/hdiutil/spctl results, install/backup hashes, smoke/restart/cleanup results, final review verdict, commit hash, and limitations here.

## Descendant-drain repair receipt — 2026-08-13

- Strict RED: the new lingering-descendant wrapper regression failed because a successful direct child left a background `sleep` alive after the wrapper deleted its lock/stage.
- Repaired only `frontend/scripts/run-feature-build-contract.mjs` and `tests/test_feature_build_contract_wrapper.py`. Each direct child close now drains and, if necessary, terminates exact non-helper members of the recorded helper PGID. `releaseLock` requires a clear helper group before quarantine/removal and preserves lock/stage when inspection or draining is ambiguous. The `ps` inspector itself is excluded from snapshots because it inherits the helper PGID.
- GREEN: focused wrapper suite `14 passed`; five consecutive full wrapper runs `14 passed` each; `node --check` RC0; `NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract` RC0; Ruff RC0; rebrand audit unexpected `0`, stale `0`; `git diff --check` RC0; working diff and `7ca83607^..HEAD` gitleaks scans RC0.
- No package/install/app/listener/user-data mutation. Exact commit `f3d27664`
  (`fix(study): drain feature build descendants`) contains the two owned tracked
  files; post-commit diff-check and commit-range gitleaks are RC0. Parent
  reconciliation remains pending.

## Task 19 blocker repair receipt — 2026-08-13

- Strict RED was the feature-build wrapper crash-recovery race: a dead parent
  could leave a lock with `child:null` during child registration, and the next
  wrapper invocation returned RC1 without proving that the complete build
  ownership set was absent.
- The bounded repair is limited to
  `frontend/scripts/run-feature-build-contract.mjs` and
  `tests/test_feature_build_contract_wrapper.py`. A detached helper becomes
  the process-group leader, records PID/PGID/nonce/stage before child launch,
  keeps all rsync/Next children in that group, and owns cleanup. Recovery
  accepts only a complete v3 lock whose exact helper PID and group are gone;
  malformed/ambiguous/symlinked state fails closed. The caller's
  `node_modules` symlink is never renamed or mutated.
- GREEN: wrapper matrix `5 passed`, repeated five times (`25/25`); exact
  `NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract` RC0;
  test Ruff RC0; frontend lint RC0 with two pre-existing warnings;
  `git diff --check` RC0; rebrand audit unexpected `0`, stale `0`; diff-pipe
  gitleaks no leaks. No Stage0-specific subset exists.
- No package/install/app/listener/user-data mutation was performed. Task 19
  native package, recoverable installation, and isolated installed-app smoke
  remain open. Commit and parent reconciliation are pending.

## Task 19 atomic lock serialization repair receipt — 2026-08-13

- Strict RED before source edits: the existing wrapper focused run was `4
  passed, 1 failed` (the parent-SIGKILL group probe hit EPERM), and direct
  inspection confirmed stale recovery performed non-atomic stage delete/lock
  unlink/reacquire plus direct named-file JSON writes. A 100-run concurrent
  stale probe had one owner/one refusal each run, but the sequence still had a
  successor-delete race and no metadata publication atomicity.
- Repaired only `frontend/scripts/run-feature-build-contract.mjs` and
  `tests/test_feature_build_contract_wrapper.py`. Lock ownership is now an
  atomic `mkdir` directory with v4 `owner.json` temp+fsync+rename metadata. The
  record binds nonce, helper PID, macOS `ps` start token, argv hash, PGID, exact
  nonce-derived stage, and state. Stale recovery proves PID/start/argv and
  complete PGID absence, wins a sibling nonce recovery claim before atomic
  quarantine rename, and never unlinks a successor. Cleanup requires exact
  current nonce/identity and uses atomic quarantine; stage removal is exact and
  never follows symlinks. EPERM, zombies, PID reuse, malformed/partial state,
  and lock/owner/stage symlinks fail closed; helper/group architecture and
  caller `node_modules` symlink remain unchanged.
- GREEN: wrapper suite `13 passed`; ten consecutive wrapper runs `130/130`;
  exact `NEXT_TELEMETRY_DISABLED=1 npm run test:feature-build-contract` RC0;
  test Ruff RC0; frontend lint RC0 with two pre-existing warnings; rebrand
  audit unexpected `0`, stale `0`; diff-check and diff-pipe gitleaks RC0.
- No package/install/app/listener/user-data mutation or full make build was
  performed. Exact separate commit `7ca83607` (`fix(study): serialize feature
  build recovery`) contains the three owned tracked files. Task 19 native
  package, recoverable installation, and installed app smoke remain open for
  the parent acceptance lane.

## Sol execution plan (prepared 2026-08-12)

Task 19 is evidence-led and may not begin package mutation until Task 18 is committed, reviewed, and the tracked tree is clean.

1. **Immutable preflight receipt.** Read the current Task 18 report first. Capture checkout realpath, branch, HEAD, base `e61e5d82`, `git write-tree`, deterministic tracked/source inventories, submodule status, preserved untracked list, disk/OS/architecture/tool versions, existing `dist` outputs, relevant listeners/processes, and `/Applications/Deeper Notebook.app` metadata/content hash/signature/running state. Use no broad process scan beyond bounded evidence. Choose a timestamped backup path and refuse if it exists. If tracked state is dirty or ownership is ambiguous, stop before build/install.
2. **Exact build.** Run `make build-mac` with an explicit PATH and `DEEPER_NOTEBOOK_CODESIGN_IDENTITY=-`; do not call lower-level targets as a substitute. Preserve a complete log and verify the target's tests/lock/frontend/runtime/PyInstaller/DMG stages. Independently inspect the app and DMG: bundle identifier/version, app inventory, forbidden secrets/dev artifacts, all shipped executable architectures, arm64 main binary, `codesign --verify --deep --strict`, `hdiutil verify`, deterministic SHA-256/content manifests, and expected ad-hoc `spctl` result. Mount read-only only when needed and detach the exact owned device.
3. **Recoverable install transaction.** If an installed app exists and is not running, atomically rename it to the preselected sibling backup and fsync/verify its hash. Stage the new app to a unique sibling, independently verify it matches `dist`, then atomically rename into place. Never delete the backup. If any later gate fails, stop exact owned processes, move the failed fresh app to a timestamped failed sibling, restore the prior app atomically, and verify the original hash.
4. **Isolated installed-app smoke.** Reuse the Task 18 verifier protocol but launch the executable from `/Applications/Deeper Notebook.app` with a unique task-owned HOME/data root and explicit environment. Do not use canonical user configuration or user model/provider state. Require authenticated ready/API/frontend route proof, PDF+video plan lifecycle, tutors, progress/native reviews, Anki export/import, process restart with new identities, durable parity, redaction, unchanged external sentinel, exact-owned cleanup, and free ports. Compare installed-app receipts to the Task 18 source-runtime contract. Leave the new app installed only when all gates pass; retain the prior backup for user rollback.
5. **Whole-diff review.** After native/package proof, give a zero-history `sol_reviewer` the approved design/plan, base `e61e5d82`, full diff through current HEAD, Task 9–18 contexts/reports, exact authoritative/backend/frontend/Surreal/verifier/package receipts, dependency and signing caveats, install rollback path, and known limitations. Require no Critical/Important findings. Any such finding gets a strict RED, a separate minimal repair commit, proportionate reruns, and re-review; no finding is fixed inside the evidence-only report commit.
6. **Final report.** Update only `docs/verification/2026-08-11-study-workbench.md` with a file-by-file justified inventory, exact test totals/commands/exits, hashes without private paths/secrets, feature inventory, default-on and explicit-zero rollback, package/install/backup/restore receipts, cleanup proof, fresh review verdict, rollback command, and residual limits (ad-hoc is not notarized; hosted/device scopes remain separate where unproved). Run final diff-check, rebrand audit, report-only sensitive scan, commit exactly `docs(study): publish workbench acceptance`, and leave tracked state clean with supplied contexts preserved.

Done means exact build success, independently valid app/DMG, recoverable install and isolated restart smoke, unchanged external sentinel, no owned orphans, approved whole diff, evidence-only final commit, and honest signing/release claims.

## Stage 3 runtime-fetch import repair — 2026-08-13

- Strict RED: exact `./.build-venv/bin/python desktop/build/fetch_runtimes.py`
  from this checkout exited `1` before any network attempt with
  `ModuleNotFoundError: No module named 'desktop'` at the archive-validation
  import (`/tmp/task19-fetch-runtimes-red.log`).
- Repaired only `desktop/build/fetch_runtimes.py` and
  `desktop/tests/test_runtime_supply_chain.py`. Direct `__main__` execution
  now resolves `__file__` to the real repository root and inserts only that
  absolute root before `desktop.*` imports; no cwd is trusted. The regression
  invokes the script from a different cwd with a stub platform so main exits
  before reading/opening runtime URLs.
- GREEN: direct regression `1 passed`; focused runtime-supply-chain suite
  `17 passed`; Ruff, `git diff --check`, rebrand audit (unexpected `0`, stale
  `0`), and working-diff gitleaks all passed. No network, package, install,
  app, listener, or runtime deletion/mutation was performed. Commit target:
  `fix(desktop): bootstrap runtime fetch imports`.
- Open: parent must review/record this atomic commit and continue the bounded
  Task 19 package acceptance; no full `make build-mac` was run here.

## Stage 3 import-precedence repair — 2026-08-13

- Strict RED added a foreign-cwd hostile `desktop` package plus
  `PYTHONPATH=<hostile>:<repo>`; the prior conditional insertion left the
  hostile package ahead of the repository and failed with
  `ModuleNotFoundError: No module named 'desktop.build'` after touching the
  hostile import marker.
- Repaired only `desktop/build/fetch_runtimes.py` and
  `desktop/tests/test_runtime_supply_chain.py`. Direct `__main__` bootstrap
  now removes every existing path entry that resolves to the exact
  `Path(__file__).resolve().parents[2]` (without resolving arbitrary missing
  entries), preserves empty cwd semantics behind it, and inserts the exact
  root at index 0. The regression asserts the hostile marker and network
  marker remain absent and the unsupported-platform failure occurs first.
- GREEN: focused runtime-supply-chain suite `17 passed`; Ruff, diff-check,
  rebrand audit (`unexpected 0`, `stale 0`), and working-diff gitleaks all
  passed. No package/install/app/listener/user-data mutation. Commit target is
  `fix(desktop): pin runtime fetch import root`; full `make build-mac` remains
  unrun in this narrow repair.

## Stage 4 resumed package/install receipt — 2026-08-13

- Exact checkout remained `codex/study-workbench` at `039e50391a191559bc3f4b5dd43059ac7c48fd33`; pre/post build tree `dbdd26d85feb5c1cab444747b1a7967a9f8f7ed5`, deterministic tracked source inventory `2041 / 93bf689b685015776d970ff1de69d09b4c34acbc321f1881be935ce4e3c5e265`. Supplied untracked contexts were preserved.
- Exact `PATH=... make build-mac` with `DEEPER_NOTEBOOK_CODESIGN_IDENTITY=-` completed green: desktop `824 passed, 2 skipped`; backend `4418 passed, 1 skipped`; frontend Next build/routes; runtime fetch/verification; arm64 PyInstaller; ad-hoc deep strict signing; DMG creation and `hdiutil verify` all passed. Build log `/tmp/dn-study-task19-build-20260813-063300.log`; nonfatal PyInstaller hidden-import warning was `aiohttp._helpers`.
- Independent artifacts: package-tree verifier passed on `Contents/Resources`; Info.plist `com.antman1526.open-notebook-plus`, `0.8.95`; main arm64 executable; app manifest `47244 / 5367 / 789`, `cb946067b3546564c92f36be02c826563af4d9f6aa48eea84cd807dbd7ae0a4c`; executable `5469fab17305ceceaaffc9257a4396ef143735d320c95a1ca060995902422cdf`; DMG `27161ae87e387a8a95031a80072331660358de64b676376538f84303f8ce09b6`; deep strict RC0, hdiutil RC0, expected ad-hoc `spctl` RC3. Read-only DMG mount identity/arm64 check passed and exact disk detached.
- Recoverable install/rollback: baseline moved atomically to `/Applications/Deeper Notebook.app.backup-study-20260813-063221` and verified unchanged (`7116 / 1559 / 117`, manifest `78c6784793373a4804c077fa41edabe5417108089cb64fe16291fc81272642a0`, executable `780f26e90d5f2c423bd5e2f2702bb56f905b5b417ebdf574b0d0257f4a312434`). Fresh stage matched dist, installed atomically, then after smoke blocker moved recoverably to `/Applications/Deeper Notebook.app.failed-study-20260813-063221`; backup restored atomically. Restored app again matched baseline manifest/inode/executable/deep signature. Preserved 5002/8189/11434 listeners unchanged.
- Installed readiness passed on non-symlink `/private/tmp` task root: desktop marker, `/readyz` 200, API dynamic ports, frontend `/study` 200 with wizard cookie. PDF/video uploads and source processing reached the task-owned data root. Full Task18 lifecycle blocked at `syllabus:propose` `503:model_unavailable`: bounded loopback model/credential seeds created language/STT API records and defaults, but no `study_fast` role route was available. Installed app's task model library/config had no local manifest/role override. Task18 `Stack.seed_model` is a separate source API/frontend/Surreal supervisor and cannot be reused in-place without additional runtime mutation; no such adaptation was performed. External sentinel remained unchanged (`07d512f700cb01a578ad5352d8b025d21b666d74c55185115ee51e6cf85972b6`).
- Exact app/model process groups were stopped; dynamic ports are free; no app process remains. Fresh failed bundle is retained for recovery; prior backup is restored. Generated `desktop/build/__pycache__` and disposable smoke roots are cleaned. No source edits or commit were made. Acceptance is `DONE_WITH_CONCERNS` due the packaged `study_fast` route blocker preventing installed lifecycle/restart proof.

## Task 19 seeded installed smoke and scope-pause rollback — 2026-08-13

- Recovered the installed smoke harness gap without source edits. Derived the
  launcher model directory from the real task-local `LauncherConfig`:
  `/private/tmp/deeper-notebook-task19-installed-20260813-123050-94729/home/Desktop/AI_Models`.
  Created the helper-shaped MLX `study-proof-local` config/bounded weights,
  loopback server, and fresh benchmark rows for `chat`, `source_synthesis`,
  and `study_fast`; after API readiness, supported credential/language/STT
  POSTs and defaults PUT returned language `model:7h9qxq12z6ruazgv44ni` and
  STT `model:yk620pwg9bjtp6xvq98m`. Packaged Python route probes selected the
  exact language model for `study_fast` with `forced_offline=True` and
  provider `openai_compatible`.
- Normal network bootstrap (after an intentionally closed-proxy preflight was
  stopped) completed the bundled 243-package lock and supported model
  downloads entirely inside the task root. Exact installed app reached its
  readiness marker and dynamic API/frontend/Surreal ports. Task18-style HTTP
  prepare workflow passed end-to-end: PDF/video source hashes/evidence,
  syllabus propose/edit/approve, study guide/flashcards, source-guide and
  practice-coach assistants, cards/review/progress, Anki export/download/import
  publish, and frontend study route. After stopping/restarting exact app/model
  identities with the same root, parity workflow passed with the same
  plan/source/artifact/card/Anki IDs.
- User scope then paused lifecycle. Exact task-owned app/model process trees and
  listeners were stopped; fresh installed bundle was moved to
  `/Applications/Deeper Notebook.app.failed-study-20260813-073415-fac20d` and
  the prior app backup was atomically restored. Current original is inode
  `212095397`, 7116 files/1559 dirs/117 symlinks, authoritative manifest
  `78c6784793373a4804c077fa41edabe5417108089cb64fe16291fc81272642a0`,
  executable `780f26e90d5f2c423bd5e2f2702bb56f905b5b417ebdf574b0d0257f4a312434`,
  deep codesign RC0, and not running. Prior failed sibling remains retained.
- Task/external roots were removed only after marker, process, listener, and
  sentinel checks. Bounded receipts (seed, route, prepare, parity, manifests,
  rollback) are archived at `/tmp/dn-study-task19-final-rollback-20260813-075020/`;
  rollback receipt SHA256 is `9c8bfa904e340033ae6921b5d470067d64ee93d9d30c451bc6a4fd4151c93c8d`.
  External sentinel archive hash is `b2d801b8d02bc571e3e72a4e5b71fe765117a49b0ccdaf84078b2af03d5e8451`.
- Open items: parent reconciliation and final acceptance/review remain. No
  source files, commits, or final docs were changed by this leaf.

## Task 19 deterministic receipt-clock repair — 2026-08-13

- Strict RED at `863917c2`: the focused receipt-authority test was `1 passed,
  1 failed`; the static `NOW + 1 day` terminal timestamp had elapsed, so the
  `terminal-in-future` case returned 200 instead of 409. Production
  `_receipt_envelope_matches` was not changed.
- Test-only repair in `tests/test_study_progress.py` computes timestamps from
  runtime `datetime.now(UTC)` offsets and gives both cases explicit IDs:
  `terminal-before-claim` and `terminal-in-future`. This keeps the authority
  boundary deterministic without adding a production clock seam.
- GREEN: focused test `2 passed`; full `tests/test_study_progress.py` `42
  passed, 2 warnings`; Ruff check, diff-check, rebrand audit (`unexpected_active_identity: 0`), staged gitleaks, and commit-range gitleaks passed. Ruff format check still reports pre-existing formatting outside this hunk. `desktop/build/__pycache__` was absent; no removal performed.
- Commit `e11f73a6` (`test(study): keep future receipt authority deterministic`)
  contains only the one test file. Supplied `.codex/agent-context/*` files
  remain untracked and preserved. No package/build/install/app mutation.

## Task 19 native package/install/smoke receipt — 2026-08-13

- Native lane completed from HEAD `e11f73a63c5437141759bd0ab5bebace58d5468c`; write-tree `62acf45647ceb9985c81ad4a778dee3680fdfdba`; source inventory SHA256 `96dc7f23736ec871ebc464509e760bfc6613ac9c7b1076d94108cdb21d406522`; tracked diff remained empty. Exact build log: `/tmp/dn-study-task19-build-20260813-091520-15972.log`; desktop `824 passed, 2 skipped`, backend `4418 passed, 1 skipped`, Next/standalone/PyInstaller/DMG stages RC0.
- Artifacts: executable SHA256 `82facfa927df78140f4f19cb952e34b02d8e7f8203f2b0542745ea94b7acf5ee`; DMG SHA256 `61e809a732cd98bf775649daae205cefe885f3e69921fd0fad9ff9840944b4f9`; bundle ID `com.antman1526.open-notebook-plus`, version `0.8.95`, arm64. Package verifier, `codesign --verify --deep --strict`, and `hdiutil verify` passed; expected ad-hoc `spctl` rejection recorded. Nonfatal PyInstaller hidden-import warning for `aiohttp._helpers` and packaged cpython caches remain documented.
- Recoverable install retained fresh app at `/Applications/Deeper Notebook.app` (manifest SHA256 `0347e61b2f28f3258a0f20736237483e9cc185fe03a9f8da17864c6524f3b133`, 47246 files/5367 dirs/789 symlinks, deep-sign RC0) and original baseline backup at `/Applications/Deeper Notebook.app.backup-study-20260813-091520-15972` (manifest SHA256 `6b0df777249abf4397bd3f3ed4c845800d8bca6046665cf70c8ae4c318390869`, 7116 files/1559 dirs/117 symlinks, executable SHA256 `780f26e90d5f2c423bd5e2f2702bb56f905b5b417ebdf574b0d0257f4a312434`, deep-sign RC0).
- Fresh mode-0700 task/external roots used a bounded loopback model/STT fixture and fresh PDF/video hashes `e168f2b633b05ae113c879693f25c19fdba435ef94fd8a844dc91057d797661e` / `b9ed66ed0da82b86c39ef04173cfaae8c573b3ab3cfea0d63a273923816f5c47`. Authenticated readiness, `/readyz` 200, `/study` 200, full PDF/video/source/evidence/plan/syllabus/artifact/Source Guide/Practice Coach/card/review/progress/Anki lifecycle, and exact app+model restart parity all passed. Durable IDs/hashes are in sanitized `prepare-workflow-state.json` and `parity-workflow-state.json`.
- Cleanup receipt `/tmp/dn-study-task19-native-final-20260813-091520-15972/cleanup-receipt.json`: owned processes/ports stopped/free, external writes `0`, sentinel unchanged, exact task/external roots removed, protected listeners 5002/8189/11434 unchanged, fresh app retained and backup preserved. Full sanitized archive is `/tmp/dn-study-task19-native-final-20260813-091520-15972`. No source/final acceptance doc edits or commit by this lane. Limitations: ad-hoc signature is not notarization/Gatekeeper approval; no hosted/network release claim.
