# Local release smoke verification — 2026-08-21

This document records the read-only, caller-owned proof surface for the
already-built Deeper Notebook `0.8.114` arm64 package. The Make targets invoke
`desktop/build/package_release_smoke.py`, which runs default and
`source-visuals-off` serially, verifies the artifact before launch, and writes
bounded JSON receipts. It does not build, copy, remove, install, notarize, or
publish an application.

## Commands

Run from the exact checkout below with a fresh, nonexistent output root for
each invocation. The UV cache and Playwright module must already exist; the
workflow is offline and does not download models or contact providers.

```bash
REPO=/Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.worktrees/today-productization
cd "$REPO"

make smoke-release-mac-app \
  RELEASE_SMOKE_EXECUTABLE="$REPO/dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook" \
  RELEASE_SMOKE_ARTIFACT="$REPO/dist/Deeper-Notebook-mac-arm64.dmg" \
  RELEASE_SMOKE_OUTPUT_ROOT=/private/tmp/deeper-notebook-release-smoke-staged \
  RELEASE_SMOKE_UV_CACHE_DIR="$REPO/.uv-cache" \
  RELEASE_SMOKE_PLAYWRIGHT_MODULE="$REPO/frontend/node_modules/playwright-core/index.js" \
  RELEASE_SMOKE_EXPECTED_ARTIFACT_SHA256=92ab2bf32c783bce103c12cb1d81030b8e3da73784a77264afa3ce5dad98678a

make smoke-release-installed-mac-app \
  RELEASE_SMOKE_EXECUTABLE="/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook" \
  RELEASE_SMOKE_ARTIFACT="$REPO/dist/Deeper-Notebook-mac-arm64.dmg" \
  RELEASE_SMOKE_OUTPUT_ROOT=/private/tmp/deeper-notebook-release-smoke-installed \
  RELEASE_SMOKE_UV_CACHE_DIR="$REPO/.uv-cache" \
  RELEASE_SMOKE_PLAYWRIGHT_MODULE="$REPO/frontend/node_modules/playwright-core/index.js" \
  RELEASE_SMOKE_EXPECTED_ARTIFACT_SHA256=92ab2bf32c783bce103c12cb1d81030b8e3da73784a77264afa3ce5dad98678a
```

Each output root contains `default.json`, `source-visuals-off.json`,
`summary.json`, and private fixture roots. The installed target reads the
named `/Applications/Deeper Notebook.app` executable only; it does not change
that bundle or its backup. The runner owns and reaps only the process group it
started. If a mode fails, it records a bounded failed receipt and does not
start the second mode.

## Current verified evidence

- App executable, both staged and installed: SHA-256
  `e06d908649762446fb08cc6de28ce8470b4ba711296650fdfcca6937fc136475`.
- Bundled `surreal-darwin-arm64`, both staged and installed: SHA-256
  `30babdd7fe6d84187cd2196a01df7c623aa1700dc24e5d229b2703c718315b26`.
- DMG: SHA-256
  `92ab2bf32c783bce103c12cb1d81030b8e3da73784a77264afa3ce5dad98678a`.
- The preserved Task 8 package receipts are
  `/private/tmp/deeper-notebook-task8-20260821T082218Z/staged-corrected-default.json`,
  `staged-corrected-off.json`, `installed-corrected-default.json`, and
  `installed-corrected-off.json`; all four passed.
- The preserved browser receipts are
  `installed-browser-default-allowlist.json` and
  `installed-browser-off-fresh.json`. They prove default Gemini Forward plus
  six enabled features, and off-mode Sources usability, `sourceVisuals=false`,
  GET-only traffic, and no source-visual mutation.

The earlier `staged-default.json` failed cleanly before readiness because its
isolated configuration was absent and the first-run wizard blocked startup;
it is retained as diagnostic history. It was superseded by the corrected
provider-none/offline-cache receipts above, not deleted or rewritten.

## Preservation and rollback

The smoke commands require fresh caller-owned output roots and preserve the
application, package, user data, credentials, and Task 8 receipt/log root.
The readable rollback bundle remains at
`/Applications/Deeper Notebook.app.backup-20260821T085744Z`. A failed proof is
recovered from its receipt and owned-process cleanup; no `/Applications`
replacement is part of this workflow. Do not remove the backup or Task 8 root
as part of smoke cleanup. Any later removal of newly created disposable output
roots requires a separately scoped cleanup decision.

## External and owner gates

Still open and intentionally separate from local smoke proof:

- Apple Developer ID signing, notarization, Gatekeeper clean-machine first
  launch, and signed updater/public-distribution proof.
- Windows packaging and Authenticode/clean-machine proof.
- Credential-owner confirmation/rotation and GitHub Support's cached
  pull-request-ref purge; no credential entry occurred here.
- Push, publication, remote-history mutation, and local-main merge authority.

The local ad-hoc signature, offline package receipts, and read-only browser
receipts do not imply any of those external gates.
