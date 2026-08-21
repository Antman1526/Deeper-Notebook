# Final Local Release Task 6 — bounded defect audit

Date: 2026-08-21

## Result

Status: docs-only closeout. No deterministic defect in a supported product
surface reproduced, so no implementation or regression-test repair was
authorized by the bounded brief. The explicitly unavailable surfaces remain
unimplemented and fail closed.

Base before this Task 6 commit: `a85699b8045664096e11bf8697bc8c575e57a4b7`
on `codex/today-productization`.

## Exact bounded verification

```text
uv run pytest -q tests/test_v0_8_107_runtime_features.py tests/test_source_visual_*.py tests/test_search_quality_*.py tests/test_chat_history_cap.py tests/test_source_chat_history_cap.py
336 passed, 7 warnings in 18.92s

cd frontend
pnpm vitest run src/lib/features.test.ts src/lib/hooks/use-runtime-features.test.tsx src/lib/hooks/use-source-visuals.test.tsx src/components/deeper-notebook/ThemeGallery.test.tsx src/components/deeper-notebook/source-gallery/*.test.tsx
8 files passed, 67 tests passed in 4.69s
```

The warning output is limited to dependency deprecations; no supported
contract failed. The existing unavailable-surface component matrix also
passed **7 files / 53 tests** in 4.62s:

```text
pnpm vitest run src/components/vault/KnowledgeAskPane.test.tsx src/components/study/StudyWorkbench.test.tsx src/components/study/StudyPlanWorkspace.test.tsx src/components/podcasts/PodcastLibrary.test.tsx src/components/podcasts/EpisodeLab.test.tsx src/components/podcasts/OutlineStoryboard.test.tsx src/lib/knowledge/research-modes.test.ts
```

The required unavailable-surface search returned these intentional boundaries:

- Knowledge Ask says selection-aware chat is unavailable and keeps `Ask
  selected knowledge` disabled. Its tests prove opening or clicking it does
  not call the chat sender; the visible route-plan metadata is not chat
  execution.
- Study plan package import is disabled with a later-release explanation and
  has no import handler.
- Podcast evidence filters, citation-to-claim mapping, and verification are
  disabled or status-only with Phase 3 copy; unsupported citation IDs produce
  a local notice rather than a callback/request.
- The search fusion module documents the reranker leg as deliberately absent;
  the current path is rank-only RRF and no reranker is invoked.

No selection-aware Ask, study import, podcast Phase 3, or reranker feature was
implemented.

## Documentation reconciliation

- `docs/TODO.md` now calls the v0.8.114 bundle a staged verified artifact,
  records its executable and DMG hashes, records the read-only current
  installed hash mismatch, and defers install/hash-equality proof to Task 8.
- The obsolete five-frontend-failure note was removed; this report claims only
  the fresh bounded selectors, not a broad release gate.
- `docs/5-CONFIGURATION/onp-env-reference.md` and
  `docs/7-DEVELOPMENT/phase-5-advanced-memory.md` now document Agent FSM as
  default-on with explicit `0`/`false`/`off` rollback; the compatibility alias
  remains supported where applicable.

## External limitations and remaining gates

- `/Applications/Deeper Notebook.app` was not changed. The staged executable
  is `911d75c3f425b839e244b9e613195b3313394c8a7e1307676d580e6af0ec439e`,
  while the current installed executable is
  `1ccaadaa54320b4e605e0f614a889a10954be9e9872f058e41ba2c263f9c7c91`.
  Task 8 must perform the authorized install, prove equality, and rerun
  installed smoke before this is called installed.
- The package is locally signed, not Developer ID signed or notarized;
  Windows packaging and public-release authority remain open. The optional
  source-visuals-off package smoke stopped before readiness on a
  package-index timeout and needs a reliable index connection for a rerun.
- The MoviePy/Pillow resolver boundary, optional summary/key-topic failure and
  cost/browser proof, and a configured local reranker remain outside this
  bounded task. Historical secret/PR-ref cleanup and release/merge authority
  remain owner-controlled external gates.
- The required `scripts/rebrand_audit.py --check` is an explicit zero-finding
  gate for this branch; compatible persisted aliases remain reviewed through
  the pinned selector inventory.

No package install, process signal, credential entry, remote mutation, or
publication occurred.

## Rebrand audit repair

- The bounded audit now passes with no unexpected active identities and no
  stale selector approvals. Its metadata delta is exactly 28 digest-identical
  pin relocations, one reviewed obsolete-pin removal, two restored reviewed
  rationale strings, one selector-inventory digest, and three affected coverage
  digests.
- The package receipt restores its exact bundle identifier composition and the
  release plan restores an executable escaped checkout locator. The Theme
  Gallery write-order assertion derives the established compatibility key from
  bounded fragments, preserving the exact storage-key and ordering proof
  without introducing a fresh visible literal.

## Task 7 source gate closure — 2026-08-21

The source-only release matrix is green after four strict browser regressions:
frontend Vitest `246 files / 1,832 tests`, TypeScript, ESLint (four existing
warnings), build, requested serial browser ports 4161–4164, backend
no-integration `4,905 passed / 1 skipped`, real Surreal `132 passed`, and
product identity `142 passed`. Rebrand is `unexpected=0, stale=0`; compileall
and diff-check pass. The canonical Playwright marker was restored and only
generated output plus a proven Task-7-owned stale 4161 server group were
removed.

The bounded source repair uses an initially rendered Settings theme control,
preserves action-label containment, lets only fallback source-card visuals
expand enough to expose their content, and skips two action tests only when the
feature-disabled build intentionally has no gallery controls. No package,
install, signing, deployment, credential, or release action occurred.

The whole-branch review's “unchanged baseline” wording for Ruff format was
incorrect: the exact base blobs were formatted, but the branch modified five
branch-owned tracked files. A bounded follow-up repaired only
`desktop/tests/test_package_smoke_contract.py`,
`desktop/tests/test_release_manifest.py`, `tests/test_product_identity.py`,
`tests/test_sources_api.py`, and `desktop/build/package_smoke.py`. The broad
tree still retains the genuinely scope-external `api/routers/search.py` I001
at pre-Task-7 `5d50049e` and an untracked vendored Node lldb file; neither was
altered.
Initial-scope and final-receipt staged Gitleaks scans, plus the required
`34ef47cd..HEAD` range scan, report zero leaks. Sol review is still required;
installed-artifact equality, notarization, Windows, optional rollback smoke,
and publication remain external gates.

## Task 7 format review repair — 2026-08-21

The strict four-file format RED reported all four owned tests would be
reformatted and exited 1. Ruff then reformatted only those four paths. The
affected focused selector passed `232 tests` with `7 dependency warnings`;
exact four-file `ruff format --check`, scoped `ruff check`, and affected
compileall all pass. The product-identity test retains its existing selector
line inventory with an inline formatter skip on the unchanged method-chain
layout, so no rebrand metadata was expanded. No implementation behavior,
package, install, or external action changed.

## Task 7 package-smoke format review repair — 2026-08-21

- Strict augmented full-tree RED used
  `uv run ruff format --check --no-cache api deeper_notebook desktop tests
  desktop/build/package_smoke.py` and exited `1`, reporting only the
  branch-owned `desktop/build/package_smoke.py` and the untouched vendored
  `desktop/bin/node-darwin-arm64/share/doc/node/lldb_commands.py`. Ruff
  formatted only `desktop/build/package_smoke.py`.
- The normalized module AST digest is identical before and after formatting:
  `ca8b03a725f9eff962bdb31cbcdda2537fa4b31d8ce8f25eed982c25d9c2c217`.
  The source-only delta is formatter layout (`20 insertions, 40 deletions`);
  no semantic delta was observed.
- The five branch-owned formatter repairs are now exactly
  `desktop/build/package_smoke.py`,
  `desktop/tests/test_package_smoke_contract.py`,
  `desktop/tests/test_release_manifest.py`, `tests/test_product_identity.py`,
  and `tests/test_sources_api.py`. Focused package/manifest pytest passed
  `65 tests` with `7 dependency warnings`; exact-five Ruff format, scoped
  package Ruff, package compileall, and diff-check passed.
- Post-repair full-tree format remains a known residual `1` only for the
  untouched vendored LLDB file. The separate `api/routers/search.py` I001 is
  an unchanged scope-external Ruff lint baseline; generated desktop pycs and
  the supplied task context remain preserved. No package, install, process,
  credential, remote, or publication action occurred. Staged and post-commit
  range Gitleaks are clean with zero leaks.

## Task 8 final local package and recoverable install — 2026-08-21

- **Package source authority:** reviewed frozen HEAD `225f42285e6cb009609ccb0d4cf0bd4f20a9f67b`. The sole authorized `make build-mac` had already passed there (desktop `889 passed / 2 skipped`, backend `4,905 passed / 1 skipped`); this closeout did not rebuild.
- **Independent staged artifacts:** frozen package content verifier, bundle ID `com.antman1526.open-notebook-plus`, version/build `0.8.114`, arm64 app and bundled Surreal, deep/strict local codesign, and DMG verify/read-only mount/detach passed. SHA-256: app executable `e06d908649762446fb08cc6de28ce8470b4ba711296650fdfcca6937fc136475`, bundled Surreal `30babdd7fe6d84187cd2196a01df7c623aa1700dc24e5d229b2703c718315b26`, and DMG `92ab2bf32c783bce103c12cb1d81030b8e3da73784a77264afa3ce5dad98678a`.
- **Smoke receipts:** corrected staged default `staged-corrected-default.json` and off `staged-corrected-off.json` passed; corrected installed default `installed-corrected-default.json` and off `installed-corrected-off.json` passed. Each is under `/private/tmp/deeper-notebook-task8-20260821T082218Z/`; default reports all six runtime features true and off reports only `sourceVisuals=false`.
- The original `staged-default.json` is preserved as a clean failed receipt: its isolated root lacked `config.toml`, so first-run wizard routing prevented readiness. Corrected roots used task-only provider-none config, local placeholder models, and offline uv cache; no product source changed.
- **Recoverable install:** the prior app is readable at `/Applications/Deeper Notebook.app.backup-20260821T085744Z` (old executable SHA-256 `1ccaadaa54320b4e605e0f614a889a10954be9e9872f058e41ba2c263f9c7c91`). The new bundle was copied with `ditto`; installed deep/strict codesign passes and its executable exactly matches the staged hash. No quarantine or restoration was required.
- **Installed browser proof:** `installed-browser-default-allowlist.json` proves the Gemini Forward Light root workspace shell and all six features with GET-only requests restricted to the advertised frontend/API loopback origins. `installed-browser-off-fresh.json` proves Sources main/heading and source-list GET are usable with `sourceVisuals=false`, zero visual mutation requests, and GET-only loopback traffic. Earlier task-local browser harness receipts are retained separately and are not product failures.
- **Final cleanup:** no owned app, Surreal, or smoke process/listener remains; no Deeper Notebook DMG is mounted. Task receipts/log roots and the backup app are deliberately preserved.
- **Limits/out-of-scope:** signing authority is local `Deeper Notebook Local` (no Team ID, Developer ID, or notarization); this is not public distribution proof. Windows packaging, publish/push, notarize, credentials, merge, and backup cleanup were not performed. The later documentation-only commit is not package source authority.

## Final productization rebuild, install, and release smoke — 2026-08-21

- **Build:** `make build-mac DEEPER_NOTEBOOK_CODESIGN_IDENTITY='Deeper Notebook Local'` passed from source authority `d5925e20`: desktop package tests `940 passed / 2 skipped`, backend `4,906 passed / 1 skipped`, Next.js production build `23/23` pages, PyInstaller packaging, deep/strict local codesign, and DMG verification.
- **Artifacts:** bundle ID `com.antman1526.open-notebook-plus`, version/build `0.8.114`, arm64 app and bundled Surreal. SHA-256: app executable `17898d9aae8f731b713fd127ea58ac0fa8539c5ee6a44f5e0f57dc66760d89c1`, bundled Surreal `5254514010b188724fa45c2af411c9ea5015f04ba30f7c9e83a647502f1ed6e4`, DMG `73f868cd45eb2475a3eea471f2e95434f83745174ef79feae8e9b0255d3256ee`.
- **Recoverable install:** the prior app was moved to `/Applications/Deeper Notebook.app.backup-20260821T193853Z`; the staged bundle was copied with `ditto`. Installed/staged executable and Surreal hashes match, and installed deep/strict codesign passes. The older Task 8 backup and pre-final `dist` moved to Downloads remain preserved.
- **Final release smoke:** the hardened runner through `cbf03876` passed staged receipts at `/private/tmp/deeper-notebook-final-staged-20260821T193701Z/` and installed receipts at `/private/tmp/deeper-notebook-final-installed-20260821T193853Z/`. Default proves all six features and the Gemini Forward Light/V2 shell. Explicit off proves the usable Sources page with only `sourceVisuals=false`. Both use GET-only loopback traffic, emit no visual mutation request, and shut down cleanly with no process left behind.
- **Final verification:** backend excluding integration `4,906 passed / 1 skipped`; real SurrealDB `132 passed`; frontend Vitest `1,832 passed`, TypeScript and Next.js production build passed; enabled visual matrix `283 passed / 1 skipped`; explicit rollback `1 passed`; Source Gallery enabled `38 passed / 1 skipped` with zero retries; Source Gallery off `12 passed / 27 skipped`; release/hygiene regression `130 passed`; product identity `142 passed`; rebrand audit `unexpected=0/stale=0`; Ruff, format, diff, compile, and cumulative secret scans passed. Fresh cumulative review approved the implementation through `cbf03876` with no open Critical or Important finding.
- **Diagnostic preservation:** earlier Task 8 receipts and the three failed final staged-smoke roots remain intact. Each final failure exposed and drove a fail-closed runner repair: missing fixture parent, duplicate evidence overflow, then static-asset overflow. No failed receipt is represented as product proof.
- **External gates:** the local signing identity is not Developer ID and is not notarized. Apple clean-machine/updater/public distribution, Windows packaging/Authenticode, credential-owner confirmation, GitHub Support cached-ref removal, push/publication, and backup cleanup remain outside this local proof.
