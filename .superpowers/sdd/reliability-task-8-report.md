# Reliability Experience Task 8 — Startup receipt projection parity

Date: 2026-08-11
Checkout: `Deeper-Notebook`

## Scope and claim boundary

This receipt covers the reproduced packaged/installed runtime-snapshot startup
mismatch only. It records local source, isolated packaged, and isolated
installed-app evidence. It does not claim manual GUI interaction,
clean-machine behavior, notarization, or a hosted release.

## Reproduction and root cause

The mismatch reproduced against the previously installed bundle using the
task-owned data root `/private/tmp/deeper-notebook-task8-installed.jAYcfH`.
The API child had the expected `DEEPER_NOTEBOOK_DATA_DIR` and HOME values, and
the on-disk `startup_receipt.json` contained valid `launcher_start`,
`chat_model_scan`, and `core_ready` stages. Nevertheless, the old packaged
`/api/runtime/snapshot` response projected `startup.state=unknown` with no
stages. An import probe from the bundled API working directory reported:

```
ModuleNotFoundError: No module named 'desktop.startup_receipts'
```

The packaged API's `_default_startup_receipts` caught that import failure and
returned `None`; this was a packaging/import-path mismatch, not an incorrect
data root, cache, or atomic-read timing issue.

## Minimal fix

`api/runtime_snapshot.py` now keeps the existing `StartupReceiptStore` path for
normal source execution and, when the desktop package is unavailable in a
frozen bundle, performs a bounded read-only projection of the exact
`startup_receipt.json` file. The fallback rejects symlinks, non-files, oversized
receipts, invalid JSON/schema/stage shapes, and any read/type/value error. It
returns only schema version and stage records; the existing normalizer remains
the allowlist/redaction boundary. No scan, mount, import, write, repair,
update, or database operation was added.

## TDD and source gates

- RED: the new packaged-reader regression failed because the simulated frozen
  import raised `ModuleNotFoundError` and the old reader returned `None`.
- GREEN: `PYTHONPATH=. uv run pytest tests/test_runtime_snapshot.py -q` —
  **19 passed**.
- `uv run ruff check api/runtime_snapshot.py tests/test_runtime_snapshot.py` —
  **pass**.
- `git diff --check` — **pass**.
- Desktop precondition during the package build — **806 passed, 2 skipped, 4
  warnings**.
- The full backend precondition reached **3947 passed, 1 skipped, 11
  warnings** before its separate rebrand-audit failure. That failure was two
  stale anchors in the already-committed Task 7 receipt; the receipt wording
  was reconciled without product changes in commit `670b1e2`, and the focused
  identity audit then passed (1 passed).

## Packaged and installed evidence

The downstream package stages completed after the unrelated precondition
failure. `verify_package_contents.py` passed, `codesign --verify --deep
--strict` passed for the app, and `hdiutil verify` reported a valid DMG. The
resulting DMG SHA-256 was:

```
f2adbdd8acd1737963abf05b39b5ec332df1bcd29e9e1ad97683ca3f45ee888a
```

Using the isolated task root, the rebuilt packaged app reached an on-disk
receipt with `launcher_start`, `chat_model_scan`, and `core_ready` (19.1 s).
Its authenticated runtime snapshot returned `startup.state=ready` with the
same three stages, readiness ready/database online/migrations applied, and no
absolute paths in the response.

The old installed bundle was moved to the recoverable backup
`/Applications/Deeper Notebook.backup-task8-20260811-021841.app` after staging
and deep-signature verification. The rebuilt app was installed and verified
with the same deep-signature check. Installed smoke returned a ready snapshot
with the same three stages and no absolute paths. All task-owned processes and
ports were stopped/clear, and all `/private/tmp/deeper-notebook-task8-*`
roots were removed.

## Remaining limits

The bundle is ad-hoc signed; `spctl`/notarization and clean-machine behavior
are not claimed. The source fix is intentionally read-only and bounded; no
additional startup operation or authority was introduced.
