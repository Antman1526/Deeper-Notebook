# Runtime Supply Chain and Performance Batch

**Date:** 2026-08-11
**Base:** `1c43691cb816c51fa5490de1d63d3cd9a2ba4132`

## Scope and outcome

This batch repairs only runtime asset integrity/layout validation, managed
Hugging Face snapshot provenance, and bounded in-memory local-model job
history. Existing public routes/response fields remain present; the snapshot
response gains the additive nullable `revision` field so the resolved commit is
observable. No live model download, model execution, user-data mutation, or
installed-app/package mutation was performed.

## Runtime supply-chain receipts

- Every `desktop/build/runtimes.toml` URL is absolute `https://` and has a
  64-character SHA-256 digest. Digests are retained from the official Node
  [`SHASUMS256.txt`](https://nodejs.org/dist/v20.18.0/SHASUMS256.txt), Astral
  uv sidecars such as
  [`uv-aarch64-apple-darwin.tar.gz.sha256`](https://github.com/astral-sh/uv/releases/download/0.5.11/uv-aarch64-apple-darwin.tar.gz.sha256),
  and Python-build-standalone sidecars such as
  [`cpython-3.12.8+20241206-aarch64-apple-darwin-install_only.tar.gz.sha256`](https://github.com/astral-sh/python-build-standalone/releases/download/20241206/cpython-3.12.8%2B20241206-aarch64-apple-darwin-install_only.tar.gz.sha256).
  SurrealDB v2.1.0 assets were downloaded from the exact
  pinned official release URLs into a disposable workspace and hashed:
  `darwin-arm64=3f9508f8…1109ce`, `darwin-x86_64=fe7d4a53…d91a0d`,
  `windows-x86_64=7f09401a…4233eb`.
- `fetch_runtimes.download` rejects non-HTTPS/credential-bearing URLs,
  requires a pinned digest, writes a unique task-owned sibling staging file,
  verifies the complete file, atomically replaces the destination only after
  verification, and removes only the staging file on failure. `urlopen` uses a
  60-second socket inactivity timeout (not a total wall-clock cap) for large
  archives.
- Tar/ZIP validation runs before extraction. It rejects absolute/traversal
  names, backslashes, duplicate normalized targets, devices/special files,
  hardlinks, escaping symlinks, overlong names/links, unexpected top-level
  roots, missing required members, and finite-budget violations. Python and
  Node relative in-tree symlinks remain allowed.
- Measured pinned tar layouts: Node `5,371` members / `157,481,719` declared
  bytes; Python `1,828` / `46,122,805`; uv `3` / `29,395,576`; Surreal `1` /
  `47,021,064`. Validation ceilings are `50,000` members, `4 GiB` declared
  bytes, and `4 KiB` member/link names. No pinned asset approaches a ceiling.

## Snapshot provenance

New managed downloads resolve `main` (or an explicitly requested ref) through
`HfApi.model_info`, require the returned lowercase 40-character commit SHA,
pass it as `revision=` to `snapshot_download`, and retain it in the in-flight
`.snapshot-install.meta`, `SnapshotInstallJob`, and API projection. Missing,
malformed, or unavailable resolution fails before model files are treated as a
successful download. Existing complete local snapshots retain the previous
local-first no-network skip behavior; they are not silently re-downloaded.

## Registry bounds and deterministic evidence

Downloader, snapshot-install, and benchmark registries each retain at most
`512` terminal jobs (completed/failed/cancelled) by insertion order while
never evicting queued/downloading/running jobs. Duplicate in-flight detection
and existing response shapes are unchanged. Focused tests lower the bound to
small deterministic values and prove active-job retention plus exact terminal
eviction; no broad application speedup is claimed.

## Verification

- RED: focused new runtime/performance tests failed before implementation.
- GREEN: `uv run pytest -q desktop/tests/test_runtime_supply_chain.py
  tests/test_runtime_supply_performance.py tests/test_local_model_snapshot_installer.py`
  — 40 passed, 1 warning.
- Adjoining: downloader/benchmark suites — 41 passed, 1 warning; desktop
  bootstrap suites — 35 passed.
- `uv run ruff check` on every touched Python path — passed.
- Real disposable archive validation — exact Surreal, Node, uv, and Python
  tar layouts passed; Python's nine legitimate relative symlinks and Node's
  three relative symlinks were accepted.

Remaining release proof (owned by the root release gate) includes the full
hermetic backend/desktop matrix, complete Bandit/rebrand scans, package/native
proof, and independent whole-diff review. No external HF model content was
downloaded.
