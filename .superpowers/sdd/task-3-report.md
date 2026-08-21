# Phase 1 Task 3 report

## Scope

- Added `ResearchCoreHeader`, `KnowledgeModeLauncher`, and `KnowledgeIntelligenceRail` with focused component tests.
- Updated the workspace shell to use semantic `main`, mode-qualified tab names, an embedded connections inspector, and a collapsible utility rail.
- Preserved split resize, close/focus fallback, tab-to-panel `aria-controls`, and V2 active-tab fallback coverage.

## TDD evidence

Initial red command:

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1)
```

Result: the three new component suites failed to resolve their absent modules; the new `main` and mode-qualified-tab assertions also failed against the prior implementation.

Additional red checks:

- The mode-launcher roving-focus assertion failed until the launcher moved focus to the next toolbar button.
- The readiness disclosure test failed when a local path appeared in the readiness summary; the header now redacts POSIX and Windows local paths before rendering.

## Green verification

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
```

Result: `5` files passed, `25` tests passed, with zero TypeScript errors.

Additional adapter coverage:

```sh
(cd frontend && npx vitest run src/components/vault/KnowledgeUtilityRail.test.tsx src/components/vault/KnowledgeLinksInspector.test.tsx --pool=forks --maxWorkers=1)
```

Result: `2` files passed, `5` tests passed.

## Decisions and safeguards

- Header authority states are textual (`app-owned`, `external read-only`) rather than color-only. Its explicit local readiness state and readiness details disclose only model IDs and providers; configured local paths are redacted before display.
- The launcher exposes Read, Write, Ask, Search, Graph, and Podcast through a roving-tabindex toolbar and `Alt+1` through `Alt+6`. It activates a matching tab in the supplied active pane or requests a new mode tab; it has no replacement path for an unsaved Overlay draft.
- Intelligence panels stay unmounted when collapsed. Connections reuse `KnowledgeLinksInspector` in embedded form so the rail owns the sole semantic `aside`.
- Existing layout/strip behavior remains intact, with mode included in every tab accessible name and V2 workspace fixtures used for active-tab fallback after the Task 1 migration.

## Boundaries

No backend, provider, external-vault, model-library, or external-write behavior was changed. The worktree-local `node_modules/` symlink/cache remains untracked and was not committed.

## Review repair: live Explorer integration

- Mounted the header, launcher, and intelligence rail in `KnowledgeExplorer`, using the selected workspace tab, its authority, persisted panes, overlay-draft store, scan action, and local-model-health hook as the live data/action sources.
- The Explorer no longer supplies a separate links inspector. The intelligence rail opens on Connections in the Explorer so existing link navigation remains available, while the rail itself remains the sole `aside` landmark.
- Replaced the Explorer content `main` with a structural `div`; `KnowledgeWorkspaceLayout` remains the single live `main` landmark.
- Added the red-first Explorer integration assertion for the Research Core shell, one-main contract, and `Alt+4` Search tab creation. It initially failed because the components were not yet mounted in the Explorer.
- Updated an existing interaction assertion from `Write: Center` to `Graph: Center`, matching the fixture's actual graph-mode state without changing that flow's behavior.

Final verification:

```sh
(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx src/components/vault/KnowledgeExplorer.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)
```

Result: `6` files passed, `70` tests passed, with zero TypeScript errors. The dedicated Explorer suite also passed `45` tests.

## 2026-08-20 Today Productization Task 3 — truthful source embedding metadata

### Scope

- Updated only `api/routers/sources.py` and `tests/test_sources_api.py` for the
  source-list response contract.
- Preserved pagination, filtering, sorting, visual projection, command status,
  and the response shape. No schema, migration, feature-flag, or packaging
  changes.

### Strict TDD evidence

RED was captured before the router edit:

```sh
uv run pytest -q tests/test_sources_api.py::TestSourceListingEmbeddingMetrics
```

Result: `3 failed, 7 warnings`. Both non-zero projected-count cases returned
the old hard-coded `embedded_chunks=0`; the zero/missing-count case retained
the stale row `embedded=true` value.

GREEN after the minimal router change:

```sh
uv run pytest -q tests/test_sources_api.py::TestSourceListingEmbeddingMetrics
```

Result: `3 passed, 7 warnings`.

### Implementation

- Both source-list query branches now project one bounded aggregate count of
  related `source_embedding` rows as `embedded_chunks`.
- Response construction normalizes missing/null counts to zero and derives
  `embedded` from `embedded_chunks > 0`.
- The branch-specific tests use non-zero projected counts and assert
  `Source.get_embedded_chunks()` is not called; a fallback regression covers
  null and missing counts.

### Verification

- `uv run pytest -q tests/test_sources_api.py` — `25 passed, 7 warnings`.
- `uv run ruff check api/routers/sources.py tests/test_sources_api.py` — pass.
- `uv run python -m compileall -q api/routers/sources.py tests/test_sources_api.py` — pass.
- `git diff --check` — pass.
- Scoped Gitleaks on each owned file with `--redact` — no leaks.
- No real-Surreal source-list/projection selector exists under
  `tests/integration`; the existing `Notebook.get_sources()` edge test does
  not exercise this API projection and was not reported as equivalent proof.

### Commit and open items

- Commit `dee95e06` (`fix(sources): report embedded chunk counts`).
- Existing tracked desktop build bytecode modifications and supplied
  untracked plan/task context remain untouched.
- The repository-wide real-Surreal, package, browser, and release gates remain
  outside this bounded task.

## 2026-08-21 Final release cleanup Task 3 — local release proof targets

### Scope and TDD evidence

- Added only the two read-only release Make targets, their static contract tests,
  the current packaged-release truth in `docs/TODO.md`, and the verification
  note `docs/verification/2026-08-21-local-release-smoke.md`.
- Strict RED was `2 failed, 29 deselected`: the release target block was absent
  and section 0.3 still contained the stale install-deferred truth.
- GREEN focused release-manifest coverage is `2/2`; the full release-manifest
  file is `31/31`. Ruff check/format, compileall, Make dry-runs, and
  `git diff --check` pass.

### Implementation and receipt

- `smoke-release-mac-app` and `smoke-release-installed-mac-app` pass only
  caller-owned executable/artifact/output/cache/Playwright paths to
  `desktop/build/package_release_smoke.py`; the installed default path is an
  input and no target recipe contains copy, removal, kill, xattr, or install
  operations.
- Section 0.3 now records exact app, bundled Surreal, and DMG hashes, the
  preserved Task 8 backup and corrected staged/installed default/off receipts,
  browser receipts, and separate Developer ID/notary, Windows,
  credential/Support, and push/publication gates.
- Staged Gitleaks scanned `11.52 KB` with zero leaks. Atomic commit:
  `e65b967b` (`docs(release): productize local package proof`).

### Boundaries and open items

No app/browser/network/package/install/`/Applications`/remote/credential action
was performed. Existing dirty/generated desktop bytecode and supplied
untracked contexts remain preserved. Sol still owns cumulative full gates,
fresh review, later repository hygiene, and local-main integration; external
signing/notarization, Windows, credential/Support, push/publication, and backup
cleanup remain open.

## 2026-08-21 Task 3 review repair — smoke prerequisites

- Strict RED was `1 failed, 3 passed, 29 deselected`: the new verification
  contract found both commands still named missing `$REPO/.uv-cache`; the
  declaration-graph regression also proves that a synthetic direct
  `smoke-release-installed-mac-app: build-mac-install` and an indirect named
  install prerequisite fail the contract.
- Repair commit `e4c339b5` (`fix(release): verify smoke prerequisites`) changes
  exactly `desktop/tests/test_release_manifest.py` and
  `docs/verification/2026-08-21-local-release-smoke.md`. The guide now names
  verified existing caller-owned `/Users/Antman/.cache/uv` in both offline
  commands; tests parse continued named Make declarations and traverse both
  release-smoke prerequisite graphs for install/mutation targets.
- Final GREEN: focused release-manifest `4 passed`; full manifest `33 passed`;
  Ruff check/format, compileall, both Make dry-runs with the verified cache,
  `git diff --check`, and post-commit Gitleaks all pass. Staged Gitleaks scanned
  `3.86 KB` with zero leaks. No app/browser/network/package/install/
  `/Applications`/remote/credential mutation.
- Preserve existing dirty/generated desktop bytecode, supplied contexts, and
  this report. Sol still owns cumulative full release gates, fresh review,
  hygiene/local-main integration, and external Developer ID/notary, Windows,
  credential/Support, push/publication, and backup-cleanup gates.
