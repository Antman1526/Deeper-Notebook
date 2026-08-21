# Final Release Cleanup Design

**Date:** 2026-08-21

**Repository/worktree:** `/Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.worktrees/today-productization`

**Branch:** `codex/today-productization`
**Current release:** Deeper Notebook `0.8.114`

## Goal

Close every remaining locally actionable release-cleanup item without changing
the installed application's product behavior: make package smoke proof
repeatable, correct stale release documentation, stop tracking generated Python
bytecode, resolve the remaining tracked Ruff import-order finding, verify the
whole result, and prepare the branch for a safe local merge.

## Scope and authority

This work may change repository source, tests, documentation, and local Git
history on the existing `codex/today-productization` branch. It may run local
tests and isolated smoke probes against the already-built staged and installed
applications. It must preserve the installed app, its backup, Task 8 receipts,
user data, credentials, and unrelated dirty files.

The following remain explicit external gates and are not represented as
completed by local code changes:

- confirm the historical Google API key's revoked/deleted state in its owning
  Google Cloud project;
- ask GitHub Support to purge the nine generated pull-request refs that normal
  Git pushes cannot rewrite;
- obtain a Developer ID certificate and notarization credentials for public
  macOS distribution;
- obtain a Windows packaged-runtime proof on Windows CI or a Windows host;
- push, publish, or create a public release.

Local merge into `main` is permitted only after all planned verification and a
fresh review pass. No remote push is included.

## Current-state problems

1. `docs/TODO.md` still describes the v0.8.114 install as deferred and records
   superseded staged hashes, although Task 8 proved staged/installed equality.
2. Twelve `desktop/build/__pycache__/*.pyc` files are tracked. Ten regenerate
   during normal tests and leave the worktree dirty even though `__pycache__/`
   is already ignored.
3. `api/routers/search.py` has one tracked Ruff import-order violation.
4. The safe low-level `desktop/build/package_smoke.py` verifier is checked in,
   but the successful release setup is not. Task 8 relied on temporary scripts
   to create a private provider-none config, size-valid sparse local-model
   placeholders, offline uv settings, exact loopback-origin browser guards, and
   serial default/off UI proof.
5. The release branch is ahead of local `main` and has not been merged.

## Design

### 1. Deterministic release-smoke fixture

Add a focused Python helper under `desktop/build/` that creates one fresh,
caller-owned smoke root per mode. It will:

- refuse an existing/non-empty target so it cannot overwrite user data;
- create owner-only HOME and data directories;
- create `config.toml` through the existing `desktop.config.Config` authority,
  using generated local-only secrets, `provider="none"`, no default model,
  Gemini Forward theme, strict-local execution, and OpenChronicle skip;
- create sparse placeholder files at the exact embedding, Piper, and
  faster-whisper paths using size floors derived from the current model-download
  constants;
- write a bounded, owner-only JSON manifest describing paths and non-secret
  environment values;
- expose `HOME`, `DEEPER_NOTEBOOK_DATA_DIR`, `UV_CACHE_DIR`, `UV_OFFLINE=1`, and
  the loopback-only OpenChronicle placeholder without printing secret values;
- add `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0` only for the off-mode fixture.

The fixture is release-test infrastructure. Placeholder files are never copied
into the application, user model library, or installed data directory.

### 2. Exact browser proof

Check in a Node browser probe and a Python orchestration wrapper under
`desktop/build/`. The wrapper will reuse the hardened process/readiness/cleanup
functions in `package_smoke.py`, launch default and off modes serially, and
always reap only its owned process group.

The browser probe will:

- derive the exact frontend and API origins from the readiness marker;
- allow HTTP(S) only to those two `127.0.0.1` origins;
- perform navigation and read-only GET requests only;
- in default mode, require a Gemini Forward theme, the Visual System V2 shell,
  and all six runtime features enabled;
- in off mode, require `sourceVisuals=false`, the usable Sources heading/main,
  a source-list GET, and zero source-visual mutation requests;
- emit a bounded machine-readable receipt for both success and failure.

No click, form submission, provider call, model download, external request,
installation, or application replacement is part of this workflow.

### 3. Make targets and documentation

Add explicit Make targets for staged and installed release smoke. Inputs remain
caller-owned and paths remain overrideable. Targets must not copy to or remove
from `/Applications`; the installed target only reads the named installed
bundle. The Make contract will run the default and off probes serially and
write receipts to a caller-supplied output root.

Document the exact commands, required offline uv cache, receipt locations,
limitations, and cleanup expectations. Update `docs/TODO.md` with the current
installed hash, DMG hash, successful default/off staged and installed proof,
backup path, and remaining notarization/Windows/publication gates.

### 4. Repository hygiene

Remove every tracked `desktop/build/__pycache__/*.pyc` entry from the Git index
and working tree. Keep the existing ignore rule and add a regression that fails
if tracked Python bytecode returns.

Fix only the import order in `api/routers/search.py`. Do not format or edit the
untracked vendored Node LLDB file.

### 5. Verification and integration

Use test-first development for every new smoke behavior. Required proof:

- focused fixture/orchestrator/browser/Make contract tests with observed RED
  before implementation and GREEN afterward;
- package-smoke and release-manifest suites;
- full backend non-integration and real-Surreal integration suites;
- full frontend Vitest, TypeScript, lint, and production build;
- serial Visual System and Source Gallery default/off browser matrices;
- Ruff check/format for tracked project files, compileall, product identity,
  rebrand audit, diff checks, and staged/range Gitleaks;
- one fresh-context code review of the final diff and evidence;
- optional rerun of staged/installed release smoke only if the new official
  workflow can reuse the already-verified artifacts without mutating the app.

After all gates pass, merge `codex/today-productization` into local `main` with
a normal non-force merge. Stop rather than resolve by guesswork if local `main`
has diverged, the worktree contains overlapping user changes, or the merge is
not fast-forward-safe. Never push automatically.

## Error handling and rollback

- Every smoke failure writes a receipt and reaps the owned process tree.
- Existing roots, readiness markers, non-loopback URLs, unsafe paths, malformed
  config, missing offline cache, and already-running packaged processes fail
  closed before launch.
- Each concern is committed separately so documentation, smoke tooling, bytecode
  removal, and import cleanup can be reverted independently.
- The installed app backup and all Task 8 receipts remain untouched.
- If the local merge is performed, rollback is the pre-merge `main` commit or a
  normal revert; no reset, force push, or history rewrite is used.

## Done criteria

The goal is complete when locally actionable items are implemented and reviewed,
all required gates have fresh successful receipts, tracked bytecode count is
zero, `docs/TODO.md` reflects installed reality, the official smoke workflow
proves default/off behavior or records an honest environmental blocker, and the
branch is merged into local `main` or stopped with a precise merge blocker.
External account, notarization, Windows, push, and publication items remain
listed with exact owners and are not mislabeled as complete.
