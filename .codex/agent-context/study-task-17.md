# Study Workbench Task 17 execution context

## Objective

Complete Task 17 from `.superpowers/sdd/task-17-brief.md`: make Study discoverable in sidebar and command navigation, localize every new Study string across all 14 locale catalogs, and prove the complete Study Workbench browser-state matrix in both default and exact rollback modes without weakening the existing all-screen audit.

## Required context

Read, in order:

1. `/Users/Antman/.codex/context.md`
2. this file
3. `.superpowers/sdd/task-17-brief.md`
4. `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
5. `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`
6. `.superpowers/sdd/task-16-report.md` if present, plus the current Task 16 diff/commit
7. repository/local `AGENTS.md` files and the TDD, verification, frontend, security, and git skill instructions supplied by Sol

## Ownership and boundaries

You own only Task 17 files unless a reproduced defect requires a narrowly justified adjacent regression fix:

- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/components/common/CommandPalette.tsx`
- `frontend/src/lib/locales/**`
- `frontend/e2e/study-workbench.spec.ts`
- `frontend/e2e/fixtures/study-workbench.ts`
- `frontend/e2e/all-screen-visual-audit.spec.ts`
- directly corresponding unit tests and a Task 17 report/context receipt

You are not alone in the repository. Preserve every unrelated edit and all supplied untracked `.codex/agent-context/*` files. Do not reset/revert, do not modify backend APIs, and do not redesign Tasks 1–16. Do not delegate.

## Required implementation sequence

1. Confirm exact worktree/branch/HEAD and clean tracked state after Task 16.
2. Add strict RED unit tests for translated sidebar Study and command-palette Study; run the named RED command before production edits.
3. Replace hard-coded Study labels with `t('navigation.study')`; add Study to command navigation using the existing icon/navigation conventions.
4. Inventory every Study UI localization key actually rendered. Add complete English copy and human-readable translations to every existing non-English catalog. Do not use English filler, placeholder text, machine annotations, or weaken catalog parity tests.
5. Build an explicit hermetic Study fixture. Route every expected request to an exact typed response and maintain an expected-call/request ledger. Never add a catch-all `{}` response or ignore unexpected external requests.
6. Add a focused Playwright matrix covering empty, loading, source-processing, syllabus-proposed, approved, generating, active, degraded-model, offline, error/retry, tutor, progress, Anki preview/import receipt, and exact flag-off rollback at 320/768/1024/1440. Assert one visible main/h1, keyboard access, focus return, reduced motion, bounded controls, no unexpected console/page errors, and zero unexpected external calls.
7. Extend the existing all-screen audit only when necessary and preserve its exact scoped horizontal-scroll exemption and clipping detection.
8. Run focused unit tests, full frontend unit/static/build/feature-contract gates, then default and exact rollback Playwright commands from the brief. Restore `frontend/test-results/.last-run.json` byte-for-byte to its HEAD baseline after browser runs.
9. Inspect the final diff, run diff-check and a staged sensitive scan, append concise durable results/open items to this file and `/Users/Antman/.codex/context.md`, write the Task 17 report, stage only owned files, and commit exactly `feat(study): complete accessible learning workspace`.

## Done criteria

- Study appears in sidebar and command palette under localized labels.
- All locale catalogs remain structurally complete and tests prove no fallback/placeholder keys.
- All named Study browser states are exercised at all four widths in default mode; exact Study/Folio rollback is exercised after an explicit rollback build.
- Feature-off is a real rollback with no Study navigation/API activity.
- Keyboard/focus/landmark/heading/target/clipping/reduced-motion/request-ledger/console assertions pass.
- Full Task 17 gates are green; any environmental limitation is reported exactly rather than waived.
- Atomic commit is created; tracked worktree is clean; supplied untracked contexts are preserved.

## Evidence log

Append RED receipt, implementation milestones, exact test totals/commands, browser/build results, commit hash, and open limitations here.

### 2026-08-12 execution receipt

- RED was captured at approved HEAD: the focused locale/sidebar/command suite
  reported 15 failures across 3 files (209 tests). Final focused navigation,
  workspace, locale, and Study page regression is 221/221.
- Added localized sidebar/command Study navigation, all 14 `navigation.study`
  catalog values, exact typed Study fixture/ledger, the complete 14-state x
  4-width browser matrix, keyboard/focus/reduced-motion/target/clipping and
  hermetic request assertions, and the semantic workspace h2 regression.
- Full frontend unit (before the final rollback gate): `npm test -- --run` =
  229 files / 1,599 tests passed. Final `npm run lint` has zero errors and two
  pre-existing StudyVoiceTutor unused-argument warnings; final `npx tsc
  --noEmit` passed.
- Final env=1 `npm run build` passed. Canonical feature-contract Turbopack
  invocation hit the worktree node_modules symlink boundary; identical env
  with `npx next build --webpack tests/build-contract` plus the verifier passed.
- Combined default browser command (explicit env=1): 21 passed, 1 expected
  feature-off skip. Exact env0/folio0 rollback: 8 passed, 14 enabled-state
  skips; rollback asserts one main/visible h1, no Study navigation, and zero
  `/api/study/` requests. The rollback required the narrowly scoped
  `useDueStudyCards(enabled)` gate, covered by the Study page unit regression.
- `.last-run.json` was restored after each browser run to blob
  `5fca3f84bc7b9240b2963858fe2f32f7c515a8d4` (SHA-256
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`).
- Open limits: canonical feature-contract Turbopack remains symlink-boundary
  limited; Webpack equivalent/verifier are green. Task 18 owns the next full
  frontend sweep after the final rollback-gate change.

### 2026-08-12 review-repair receipt

- Strict RED before edits: 2 flag-matrix failures plus 2 syllabus/dynamic-route
  failures. Added complete route rollback, feature-gated navigation, exact
  fixture methods/405 ledger, per-width request counts, 204 optional syllabus,
  substantive tutor/progress/Anki assertions, and no broad console-error allow.
- Narrow adjacent fixes required by the route-param browser proof: assistant
  and voice APIs normalize one/two encoded `study_plan` layers; Tutor citations
  expose a named region; progress action buttons wrap and retain min 32px
  height. All have focused tests or browser coverage.
- Evidence: focused repairs 8 files / 244 passed; env=1 Study+all-screen 22
  passed / 1 skip; env0+folio0 build and combined rollback 8 passed / 15
  enabled skips; env1 build passed. `.last-run.json` restored to HEAD blob.
- Open: canonical feature-contract Turbopack remains symlink-boundary limited;
  prior Webpack equivalent/verifier receipt remains valid.
- Commit `fadefc8a` (`fix(study): enforce complete workbench rollback`) created;
  tracked worktree clean and supplied untracked contexts preserved. Post-commit
  range gitleaks scanned one commit / 18.90 KB with zero leaks.

### 2026-08-12 voice synthesis route repair

- Review finding: `studyVoiceApi.synthesize` discarded the normalized encoded
  route ID and dispatched `%253A`; capability/transcribe already normalized.
- Strict RED: added encoded transcribe/synthesize path tests and malformed plus
  over-two-layer plan-ID rejection tests; `study-voice.test.ts` reported 7/8,
  failing only the expected synthesize `%253A` path.
- GREEN: synthesize now encodes the `validatePlanId` return. Focused voice API,
  StudyLearningSession, and StudyVoiceTutor tests pass 3 files / 17 tests;
  scoped ESLint, `npx tsc --noEmit`, and `git diff --check` pass.
- Commit `4f28a8cb` (`fix(study): normalize voice synthesis routes`) contains
  only the API fix and regressions. Staged gitleaks scanned ~2.42 KB with zero
  leaks. Supplied untracked contexts remain preserved.

### 2026-08-12 voice identifier hardening

- Fresh review found residual percent encodings and literal/encoded control
  characters could survive the two-layer route decoder and dispatch.
- Strict RED added a no-dispatch matrix across capability, transcribe, and
  synthesize: 8 of 18 voice API tests failed before production changes.
- The bounded normalizer now rejects any residual percent marker plus ASCII
  control characters after at most two successful decode passes. Literal,
  one-layer, and two-layer valid Study Plan IDs remain accepted.
- GREEN: voice API, StudyLearningSession, and StudyVoiceTutor = 3 files / 27
  tests passed; scoped ESLint has zero errors and only the two existing unused
  stub-argument warnings; TypeScript and diff-check pass.
