# Reliability Experience Task 7 — Integrated proof receipt

Date: 2026-08-11
Checkout: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook`
Visual evidence commit: `2a2eefc0` (`test(visual): refresh reliability experience evidence`)

## Scope and claim boundary

This receipt records the current-HEAD acceptance evidence for the six
Reliability Experience slices. It records local source, mocked-browser,
native, packaged, and installed-app evidence only. It does not claim manual
GUI interaction, clean-machine behavior, notarization, or a hosted release.
No product source was changed for Task 7; the only product-adjacent change in
this proof pass was the separately committed, reviewed visual evidence update
(`2a2eefc0`, exactly 14 approved PNGs).

## Requirement matrix

| Requirement | Evidence | Result / limit |
| --- | --- | --- |
| Backend/API gates | `PYTHONPATH=. uv run pytest tests/ -q --ignore=tests/integration` | **PASS** — 3946 passed, 1 skipped, 11 warnings, exit 0. |
| Desktop gates | `.build-venv/bin/pytest desktop/tests/ desktop/memory/tests/ -q` | **PASS** — 806 passed, 2 skipped, 4 warnings. The shared `.venv` attempt was collection-blocked by missing optional `mem0`; no dependency or source change was made. |
| Frontend unit/regression | `npm test -- --run` | **PASS** — 202 files, 1452 tests. |
| Frontend lint/type/build | `npm run lint`; `npx tsc --noEmit`; `npm run build` | **PASS** — scoped lint, TypeScript, and Next 16.2.12 build (23 routes). A broader exploratory `eslint src e2e scripts` remains red on the pre-existing `researchWorkbench` hook naming rule; package-owned `npm run lint` is the authoritative scoped gate. |
| Mocked browser behavior | `PLAYWRIGHT_PORT=3117 npm run test:e2e:mocked` | **47 passed, 2 failed, 1 skipped**. Both failures are the rollback-only tests run without `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`; they cannot see `.dn-legacy-shell` under the Luminous default. The same rollback tests pass 2/2 with the required flag. Functional mocked subset excluding visual/rollback: 32 passed, 1 skipped. |
| Mocked visual baselines | `PLAYWRIGHT_PORT=3117 npx playwright test --project=mocked-browser e2e/luminous-folio-visual.spec.ts e2e/theme-gallery-visual.spec.ts` | **PASS** — 17 passed after manual review and refresh of exactly 14 coherent PNGs. Deltas were the approved Focus hint and Task 6 Runtime/Backup/Provenance panels. |
| Rollback Focus proof | `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 PLAYWRIGHT_PORT=3117 npx playwright test --project=mocked-browser e2e/focus-mode-rollback.spec.ts` | **PASS** — 2 passed at phone and tablet widths. |
| Native API/Surreal/Supervisor smoke | Task-owned data root `/private/tmp/deeper-notebook-task7-native.3tXa9a`; ports 51395/5055/51397–51403 | **PASS** — `/livez`, `/readyz`, authenticated `runtime-snapshot-v1`, dashboard/settings routes, redaction checks, Focus/backup/provenance browser assertions, startup receipt, and unchanged external fixture SHA. All child processes terminated cleanly. |
| Package contents and DMG | `verify_package_contents.py`; `codesign --verify --deep --strict`; `hdiutil verify` | **PASS** — canonical `upstream/deeper_notebook` runtime plus exact `open_notebook` shim; deep strict signature verification passed; DMG checksum valid. DMG SHA-256: `a823fda3997ab219e58136e091399f4f3a3322e60e2f1999cc112ca3d5a82035`. |
| Packaged app smoke | Task-owned package root and readiness marker | **PASS** — bundled app reached API/frontend readiness, `/livez`, `/readyz`, snapshot/settings, `__next_f`, redaction, backup/provenance, and unchanged external SHA; SIGTERM returned 143. |
| Recoverable installed swap | `/Applications/Deeper Notebook.backup-20260811-014426.app` retained while staged app moved into `/Applications/Deeper Notebook.app` | **PASS** — pre/post deep codesign verification passed; timestamped prior app backup remains available. |
| Installed app smoke | Current installed bundle with task-owned HOME/data root; API 57042, frontend 57043 | **PASS** — readiness marker matched the current PID, API/frontend/settings/snapshot all returned 200, `__next_f` and redaction checks passed, external SHA stayed unchanged, SIGTERM returned 143. |
| Cleanup and runner state | Explicit task roots removed; ports checked; tracked Playwright marker restored | **PASS** — task data roots and services are gone; ports 5055, 51395, 51397, 55663, 55664, 57042, 57043, and 3117 are clear; `frontend/test-results/.last-run.json` is restored. |

## Safety and privacy observations

- Native, packaged, and installed snapshots returned bounded states only:
  backup was `unknown`/`file_count: 0` in the isolated roots, provenance had
  zero mounts and an unknown source-fingerprint state, and no absolute paths,
  raw errors, source contents, or user-content hashes were exposed.
- The external fixture SHA-256 was identical before and after each native,
  packaged, and installed smoke. No mount, scan, repair, import, backup, or
  update operation was requested by the proof harness.
- `codesign --verify --deep --strict` passed. `spctl -a -vvv` rejected the
  ad-hoc signed bundle as expected; this is not notarization evidence. The
  PyInstaller build also logged non-fatal warnings for broken/excluded
  tkinter, hidden `aiohttp._helpers`, and unresolved sharp `libvips` rpath;
  these were not silently converted into a clean-release claim.

## Open proof limits and timing concern

1. No manual GUI interaction, PyWebView visual inspection, clean-machine
   install, notarization, hosted distribution, or platform approval proof was
   performed. The readiness marker's `window_marker: "__next_f"` proves the
   local frontend rendered far enough for the harness, not human GUI success.
2. The package and installed-app snapshot requests observed
   `startup: {state: "unknown", stages: []}` while the task-owned
   `startup_receipt.json` on disk contained valid `launcher_start`,
   `chat_model_scan`, and `core_ready` stages (the native run projected the
   ready stages). This is an early/in-flight snapshot timing or projection
   concern and remains unresolved; no product change was made to hide it.
3. The default full mocked command includes rollback tests that require the
   explicit rollback feature flag. Those two expected configuration failures
   are reported above rather than folded into a false all-green total; the
   dedicated rollback run is green.

## Decision

The six slices have evidence-backed local source, mocked, native, package,
and installed smoke coverage sufficient for a **conditional integrated-proof
completion**. A final public/release-ready or manually accepted claim is not
justified until the proof limits above, especially the startup projection
timing, are resolved or explicitly accepted by the owner.
