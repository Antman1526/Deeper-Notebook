## 2026-08-01 — Task 4: Research Core Visual System, Responsive Rails, and Motion Safety

- Added the Research Core semantic deep-teal/cyan token family and responsive CSS hooks.
- Added labeled Sources and Intelligence drawers below 1024px, including explicit close controls and focus restoration to their triggers.
- Made the mode toolbar sticky below 720px with focus-safe scroll offsets and sequential surface layout.
- Added locale-complete drawer labels across all supported locale bundles.
- TDD evidence: the new visual-system and drawer interaction assertions first failed because the tokens, responsive hooks, and controls were absent; they pass after implementation.
- Verification passed: `(cd frontend && npx vitest run src/components/vault --pool=forks --maxWorkers=1 && npx tsc --noEmit)` — 32 files / 259 tests; TypeScript exited 0. Locale parity also passed: 13 checks across all 14 supported locales.
- Note: the broader locale test has one pre-existing unused-key failure for `knowledge.description`; it is unrelated to the new drawer labels, which are referenced by the Research Core shell.

### 2026-08-01 review repair

- Added a real `matchMedia('(max-width: 1023px)')` regression test: after the Sources drawer opens, collapsing the desktop rail still retains a reachable drawer close control and restores focus to the Sources trigger.
- The collapsed utility rail now renders its drawer close control alongside the existing desktop-rail restore action, preserving desktop collapse behavior while preventing the narrow drawer from trapping the user.

## 2026-08-20 Today Productization Task 4 — safe default enablement

### Scope

- Default-enabled only Research Runs and the Agent FSM/tool loop when their
  variables are unset. Canonical and legacy explicit-off values still win, and
  the existing runtime backend feature authority remains unchanged.
- Preserved auto-summary and key-topic enrichment as opt-in. No model was
  downloaded, no provider was called, and no ingestion/default/cost behavior
  changed for either enrichment.

### Strict TDD evidence

- RED before production edits: `frontend/src/lib/features.test.ts` had two
  expected Research Runs default-on failures; the backend feature-flag selector
  had two; chat FSM had two; and ask FSM had two. Every failure was the old
  unset/default `false` behavior.
- GREEN after the minimal default-resolution changes: the focused Research
  frontend/consumer suite passed `57/57`; the backend runtime feature and
  Agent FSM/chat/ask suite passed `89/89`.

### Failure-path coverage and enrichment decision

- Agent FSM coverage includes default-on and explicit-`0` rollback in both
  chat and ask, empty grounding, malformed terminal-state fallback, and the
  maximum-loop truncated outcome.
- Existing auto-summary/key-topic tests passed `9/9`, but they prove only
  defaults and parser/preview behavior. There is no focused proof for missing
  model, offline/provider failure, timeout, or the matching browser settings
  controls. `process_source_command` catches optional-transformation setup but
  runs selected transformations on the ingest path, so nonblocking isolation
  is not established. Both enrichments remain opt-in.

### Verification and open items

- `npm test -- --run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/ArtifactRail.test.tsx` — `57/57`.
- `uv run pytest -q tests/test_evidence_studio_foundation.py tests/test_v0_8_107_runtime_features.py tests/test_agent_fsm.py tests/test_v0_8_60_agent_fsm_tool_loop.py tests/test_agent_fsm_ask_gate.py tests/test_ask_result_caps.py tests/test_v0_8_66_chat_env_knobs.py` — `89/89`.
- `uv run pytest -q tests/test_auto_summary.py tests/test_key_topics.py` — `9/9`.
- `uv run python scripts/rebrand_audit.py --check` — zero unexpected active
  identities after splitting the four new test literals into deterministic
  runtime keys. The command remains nonzero for seven stale allowlist entries;
  a detached clean `dee95e06` worktree reports those same three
  `api/routers/sources.py` and four pre-existing `features.ts` entries. The
  authorized `make repair-rebrand-pins` attempt rewrote 66,276 metadata lines
  and still failed, so only its generated metadata files were restored; no
  unrelated rebrand policy was committed.
- Open: add focused missing-model, offline/provider-error, timeout, explicit-off,
  per-source-cost, and browser-settings evidence before reconsidering automatic
  ingest enrichment; resolve the pre-existing rebrand stale-allowlist workflow
  before its command can return green. Broader browser, database, package, and
  release gates remain outside Task 4.

### 2026-08-20 review repair — reactive Research Run runtime rollback

- Added `useResearchRunsEnabled()` through the existing runtime external-store
  authority and made `ArtifactRail` consume it. A mounted rail now removes the
  default-on Research run control when a later valid backend payload sets
  `researchRuns: false`.
- Strict RED: the real `applyRuntimeFeatures({ researchRuns: false })` path ran
  after mount and left the button visible (`1 failed / 35 passed`). GREEN:
  ArtifactRail/features/build-contract Vitest `58/58`, backend runtime-feature
  selector `62/62`, TypeScript, scoped ESLint, and diff checks passed. Existing
  malformed/unknown/mixed payload tests continue to prove atomic preservation
  of the prior runtime rollback.

## 2026-08-21 Final release cleanup Task 4 — repository hygiene

### Scope and TDD evidence

- Added only `tests/test_repository_hygiene.py`, moved the existing
  `reciprocal_rank_fusion` import in `api/routers/search.py` into Ruff order,
  and removed exactly the twelve tracked `desktop/build/__pycache__/*.pyc`
  paths. No untracked/generated bytecode or unrelated dirty file was removed.
- Strict RED was the required `uv run pytest -q
  tests/test_repository_hygiene.py`: `1 failed`, listing all twelve tracked
  bytecode paths.
- GREEN focused pytest is `1 passed`; `test -z "$(git ls-files '*.pyc')"`
  passes and the repository now tracks no Python bytecode.

### Verification and receipt

- `uv run ruff check api/routers/search.py tests/test_repository_hygiene.py` —
  pass.
- `uv run ruff format --check api/routers/search.py tests/test_repository_hygiene.py` —
  both files already formatted.
- `python3 -m compileall -q api/routers/search.py tests/test_repository_hygiene.py` — pass.
- `git diff --check` and staged `git diff --cached --check` — pass.
- `gitleaks protect --staged --redact` — scanned 436 bytes, no leaks.
- Atomic commit: `ede85d96` (`chore(repo): stop tracking Python bytecode`).

### Boundaries and open items

No app/browser/network/package/install/remote/credential/merge/release action
was performed. The pre-existing modified Task 3 report, supplied task
contexts, and generated untracked desktop bytecode remain outside the commit;
Sol owns cumulative release verification, fresh review, and local-main
integration.
