# Runtime Supply Chain and Performance Batch

## Confirmed defects

1. `desktop/build/fetch_runtimes.py` downloads and extracts pinned SurrealDB,
   Node.js, uv, and python-build-standalone archives without checking a pinned
   digest. `desktop/build/runtimes.toml` contains versions and URLs only.
2. `desktop/window.py` shell interpolation is owned by the prior security batch.
3. `deeper_notebook/local_models/snapshot_installer.py` follows a mutable
   Hugging Face repository branch and records no immutable revision.
4. The download, snapshot-install, and benchmark `_JOBS` registries retain every
   completed job for the lifetime of the API process. Repeated completed work
   grows memory without a bound.
5. Radon identified complexity hotspots, but refactoring them without a measured
   defect would violate this audit's no-rewrite boundary. Do not refactor those
   solely for a score.
6. Bandit reports high-confidence archive extraction findings in
   `desktop/bootstrap.py` and `desktop/build/fetch_runtimes.py`. The tar paths
   currently use Python's `filter="data"`, but neither tar nor ZIP paths enforce
   the small expected member/layout contract before extraction. Treat this as
   part of the supply-chain boundary: reject absolute paths, traversal,
   escaping links, devices, duplicate targets, and unexpected members before
   writing. The pinned Python runtime legitimately contains nine relative
   in-tree symlinks under `python/bin`, `python/lib/pkgconfig`, and its manpage;
   preserve safe contained symlinks rather than banning all links.
   Preserve the existing successful archive layouts and public function
   signatures.

## Required design

- Add SHA-256 fields for every supported runtime URL and verify the complete
  downloaded file before extraction/use. Verification failure must delete only
  the task-owned downloaded archive and fail closed. Add tests using synthetic
  archives and mismatched digests before implementation.
- Add one shared, bounded archive-member validator (or equivalent small helpers)
  and RED tests for traversal, absolute, escaping-link, duplicate-target, and
  unexpected-layout tar/ZIP members. Do not rely solely on Bandit's recognition
  of the standard-library filter; validate before extraction and keep extraction
  inside task-owned destinations.
- Pin managed Hugging Face snapshot installs to a resolved commit SHA before
  download and retain the revision in restart metadata/job receipts. Existing
  callers that omit a revision remain source-compatible. Reject malformed or
  missing commit identifiers before model files are treated as complete.
- Bound completed/cancelled/failed in-memory job history with a generous finite
  retention count while never evicting queued/downloading jobs. Preserve all
  current API response shapes and duplicate-in-flight behavior.
- Measure registry size and archive verification overhead with deterministic
  tests; do not claim broader application speedups.

## Proof

- RED then GREEN focused tests for fetch runtimes, snapshot install, downloader,
  and benchmarks.
- Adjoining local-model API and desktop build-helper suites, Ruff, compileall,
  rebrand/product identity, full hermetic backend/desktop gates.
- No live model download and no user model/data mutation.

## 2026-08-11 Luna implementation receipt

- At base `1c43691c`, added RED tests for runtime manifest HTTPS/digests,
  staged mismatch cleanup, archive traversal/link/device/duplicate/layout
  guards, immutable HF revisions, and bounded terminal registries.
- Implemented exact pinned SHA-256 verification with unique staging/atomic
  replacement; shared tar/ZIP validation with evidence-based budgets (50,000
  members, 4 GiB declared bytes, 4 KiB names/links); bootstrap validates before
  extraction and preserves contained Python/Node symlinks. TOML keeps all
  official asset URLs and hashes.
- Snapshot downloads now resolve/validate a 40-character HF commit before new
  downloads, pass `revision`, and retain it in job/sidecar/API receipts.
  Existing complete local snapshots remain an offline no-download skip.
- Downloader, snapshot, and benchmark `_JOBS` retain 512 terminal records and
  never evict active jobs; duplicate-in-flight semantics remain unchanged.
- Focused GREEN: runtime/performance/snapshot 38 passed; adjoining downloader
  + benchmark 41 passed; bootstrap suites 35 passed; scoped Ruff passed.
  Disposable exact official archives validated (Node 5,371 members; Python
  1,828 with nine symlinks; uv 3; Surreal 1). No model/user-data mutation.
- Open release proof: full hermetic backend/desktop gates, Bandit/rebrand,
  package/native proof, independent whole-diff review, and final atomic commit
  reconciliation by root.

## 2026-08-11 final receipts

- Commits: `825c1d1d` runtime supply/performance implementation; `7b6d45e1`
  rebrand/report anchor correction. Both are based on `1c43691c`; unrelated
  untracked state remains untouched.
- Focused runtime/performance/snapshot: 40 passed, 1 warning; full adjoining
  batch: 111 passed, 1 warning. Product identity: 141 passed. Rebrand audit:
  compatibility 825, historical 1747, migration 584, unexpected 0, stale 0.
  Ruff, compileall, diff-check, and scoped Bandit high/medium scan passed;
  Bandit used `uvx` because project `uv run bandit` is unavailable.
- Official pinned runtime URLs/hashes and archive budgets are documented in
  `.superpowers/sdd/runtime-supply-performance-report.md`; no model content,
  user data, installed app, or package was downloaded or mutated.
- Open root gates: full hermetic backend/desktop matrices, final package/native
  proof, independent whole-diff review, and any release-level signing/proof.
