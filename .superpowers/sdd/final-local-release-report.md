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
