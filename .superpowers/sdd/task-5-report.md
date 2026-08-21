### Task 5 report — 2026-08-01

Implemented verified local-model inventory/readiness classification without
touching a live model library or performing model/runtime/network work.

- Added pure, fail-closed readiness contracts. `ready_verified` requires
  complete files, a supported/configured runtime with matching identity, a
  bounded healthy probe, an accepted benchmark, and trusted symlink evidence;
  a manifest row alone yields no verification.
- Added an explicit external-root trust record keyed by the selected symlink
  identity and resolved-target identity. Discovery uses `os.walk` with
  `followlinks=False`; it traverses only an exact trusted external target,
  including rejecting an untrusted `MLX` category symlink.
- Added redacted `GET /api/local-models/readiness`. It exposes model identity,
  format, modality, readiness/reason, measured tier, accepted roles, and route
  eligibility, but no path or model root. Paths remain on the dedicated
  inventory endpoint.
- Added synthetic MLX/GGUF/Transformers/partial/manifest/external-STT tests.
  Fixture SHA-256 values are recorded before discovery and asserted unchanged
  afterwards. Planned, removed, incomplete, unsupported, unverified, and
  identity-mismatched rows are all visible and route-ineligible.

Verification:

```sh
PATH="$PWD/.venv/bin:$PATH" pytest -q tests/test_v0_8_39_local_models_inventory.py tests/test_local_model_manifest.py tests/test_research_core_local_models_api.py
# 49 passed; one existing FastAPI/TestClient deprecation warning
.venv/bin/python -m ruff check deeper_notebook/local_models/contracts.py deeper_notebook/local_models/inventory.py deeper_notebook/local_models/manifest.py api/routers/local_models.py tests/test_v0_8_39_local_models_inventory.py tests/test_local_model_manifest.py tests/test_research_core_local_models_api.py
git diff --check
```

## Task 5 search-quality productization — 2026-08-20

- **HNSW:** a strict disposable SurrealDB 2.6.5 RED used 768-dimensional raw
  non-unit vectors: exact cosine selected `cosine winner` (1.0), while the
  former Euclidean HNSW candidate pool selected `euclidean candidate 000`
  (0.8). SurrealDB accepted `DIST COSINE`. Migration 51 drop/redefines all
  shipped candidate indexes (`source_embedding`, `source_insight`, and `note`)
  as cosine; its down migration restores Euclidean. Static definition contracts
  and real up/down/up proof passed.
- **Embedding norm boundary:** a fake provider returned a short norm of `5.0`
  and batched norms `[5.0, 10.0]` unchanged through the source-relevant utility
  paths. No provider was contacted, no output was normalized, and no data was
  re-embedded.
- **BM25:** two fresh real-Surreal REDs showed `Source.delete()` left stale
  survivor order until rebuild. The delete path now best-effort rebuilds only
  the four fixed affected source indexes after success; failed deletes do not
  rebuild, and individual rebuild failure logs table/index context without
  changing an irreversible success into a false failure. Product retrieval
  identity/order is stable over comparison rebuilds. SurrealDB 2.6.5 changes
  raw BM25 magnitude on each identical rebuild pass, so that unsupported
  idempotence is documented rather than asserted; hybrid fusion is rank-based.
- **Recall/latency:** two fresh 128-vector fixtures measured EF 100 recall@10
  `1.000` at median `8.552` then `9.170 ms`; read-only EF 200 also reached
  `1.000` at `9.188` then `10.053 ms`. No EF tuning is justified.
- **Reranker:** repository inventory confirms only BM25/vector RRF legs and no
  configured local reranker/cross-encoder invocation. No model was downloaded
  or run; a reranker delta remains separately authorized work.

Focused verification:

```sh
SURREAL_INTEGRATION=1 uv run pytest -q -s tests/integration/test_search_quality_benchmark.py
# 5 passed in 15.01s (run 1); 5 passed in 15.23s (run 2)
uv run pytest -q tests/test_search_quality_embedding_norms.py tests/test_search_quality_source_delete.py tests/test_search_quality_migration.py tests/test_v0_8_114_knn_operator_arity.py tests/test_v0_7_133.py::TestSourceDeletePostSweep tests/test_domain.py::TestSourceDomain
# 21 passed, one existing Pydantic deprecation warning
uv run ruff check ... && uv run ruff format --check ... && uv run python -m compileall -q ...
git diff --check
gitleaks detect --no-git --source <owned-files> --redact --no-banner
# no leaks found
```

### Review repair — coalesced source-index maintenance (2026-08-20)

- Fresh lifecycle RED: the initial post-delete helper held a successful source
  deletion until a blocked first rebuild. A second RED showed maintenance could
  start before the race-window post-sweep, leaving a newly deleted straggler
  unrefreshed. The repair uses a per-event-loop coordinator with a strong task
  reference only while pending, generation/pending coalescing, serialized
  fixed-whitelist passes, and a `10s` bounded wait per index.
- A successful `Source.delete()` schedules in a `finally` immediately after the
  post-sweep attempt, including caller cancellation after the irreversible
  delete, while no rebuild can run before the sweep. Failed or interrupted
  attempts retain the durable marker for later reconciliation. A delete during
  an active pass yields one trailing convergence pass rather than `4*N`
  overlapping rebuilds. Per-index errors/timeouts log exact table/index context
  and detached task failures are consumed.
- Existing mocked source-delete fixtures now flush maintenance before their
  repository patch exits; unrelated source-domain tests patch scheduling. This
  prevents a detached task from falling through to real repository work and
  contaminating the shared pool. The completed-task regression proves state no
  longer retains a finished task/event loop.

Verification: focused lifecycle/static selector `26 passed` (one existing
Pydantic warning); one fresh real-Surreal benchmark `5 passed in 15.06s`.
Scoped Ruff/format/compileall/diff-check and Gitleaks passed; no broad suite.

### Review repair — durable source-index reconciliation (2026-08-20)

- The desktop launcher has an eight-second default shutdown grace, so a
  four-index/two-pass worst-case rebuild cannot be honestly guaranteed by a
  long shutdown wait. `Source.delete()` now writes and confirms the fixed
  source-search rebuild-pending marker with a fresh opaque token before any
  file or database deletion; failure to write it aborts the
  delete before mutation.
- The coordinator retains the marker after any timeout/failure and clears it
  only with an exact-token CAS after a successful fixed-whitelist pass. A newer
  token observed during a pass causes exactly one trailing pass; any forced
  kill leaves the marker for the next API startup instead of falsely claiming
  durability.
- API startup awaits reconciliation before services begin serving. Clean
  shutdown waits at most five seconds before pool closure; timeout or
  cancellation logs degraded search and retains the marker. This is explicitly
  not a guarantee for an unclean forced-kill process.
- Fresh focused lifecycle selector passed `18`; a fresh disposable SurrealDB
  2.6.5 marker UPSERT/new-token/stale-CAS/live-CAS probe plus Task 5 benchmark
  passed `6` tests. No full integration suite was run.

### Review repair — fenced marker readiness and shutdown quiescence (2026-08-20)

- The fixed durable marker now has two states. `Source.delete()` writes its
  opaque token as `intent` before any destructive action, then exact-token CAS
  promotes it to `ready` only after its post-sweep has completed or been
  attempted. Maintenance rebuilds and clears only `ready`; an older pass
  rechecks the exact ready token before each fixed index and stops when a newer
  intent arrives. A newer promoted generation gets one serial trailing pass.
- Startup runs before the API accepts requests, so it may safely promote a
  crash-left `intent`; request-time workers never do. The real SurrealDB 2.6.5
  CAS probe validates stale promotion/clear rejection and live promotion/clear
  success. This is still a clean-shutdown guarantee only; forced process kills
  retain the marker for next startup rather than claiming completed work.
- If the five-second shutdown drain times out or lifespan is cancelled, API
  explicitly cancels and awaits the exact loop-owned worker before pool close
  (or re-raise). Cancellation never clears the marker. Deterministic lifecycle
  tests prove the worker is done/cancelled before mocked `close_pool`.

### Review repair — serialized source deletion maintenance (2026-08-20)

- The durable receipt is a singleton record, so `Source.delete()` now holds a
  per-event-loop async mutex from marker write through pre-sweep, parent delete,
  post-sweep, exact promotion, and maintenance scheduling. A no-op/false delete
  cannot overwrite a live deletion token before that deletion finalizes.
- The post-sweep/promote/schedule finalizer runs after any parent mutation
  attempt, including a `False` parent result and caller cancellation; it keeps
  the parent's return/exception semantics while ensuring search convergence is
  independent. A failed promotion leaves the newer durable token authoritative.
- Deterministic RED/GREEN coverage proves the B-success/A-false interleaving,
  false-result sweeps, and cancellation behavior. Focused source/lifespan
  selector passed `22`; one disposable SurrealDB benchmark/CAS run passed `6`.

## Deeper Notebook final release cleanup Task 5 worker verification — 2026-08-21

- HEAD is `ede85d96`; `7e8fcc49..HEAD` contains 16 commits. The exact affected suite passed `111` tests in `8.73s` (`real 9.93s`).
- Ruff check passed in `0.14s`; Ruff format check passed (`856 files`) in `0.11s`; compileall passed in `2.69s` with two existing vendored LLDB invalid-escape `SyntaxWarning`s. Range `git diff --check` passed in `0.05s`.
- Product identity is the blocking failure: `141 passed, 1 failed in 53.82s` (`real 54.57s`). Its rebrand assertion and direct audit both fail: `unexpected_active_identity=4`, `stale_allowlist=12`. The four unexpected entries are the final release report, Task 8 report, final cleanup plan, and final cleanup design; the twelve stale entries are in `desktop/tests/test_release_manifest.py`.
- Range Gitleaks passed across 16 commits / approximately 151,905 bytes with zero leaks in `0.12s`. No product/source, app, browser, network, install, merge, push, rebuild, backup, or receipt mutation occurred.
- Worktree remains limited to known modified Task 3/4 reports, the two supplied untracked contexts, and fourteen generated untracked desktop `__pycache__/*.pyc` files; tracked `.pyc` count remains zero. Open for Sol rebrand reconciliation and cumulative/fresh-review/local-main/external gates.

## Task 5 rebrand reconciliation completion — 2026-08-21

- Verified the recorded Luna `BLOCKED` receipt and Sol's narrow fallback
  authority. The committed diff is exactly two repository-relative plan/spec
  path edits, the selector-inventory pin, and regenerated allowlist metadata:
  twelve `desktop/tests/test_release_manifest.py` line shifts, two historical
  `migration_documentation` entries, two coverage hashes, and the two approved
  ThemeGallery/theme-storage explanation-only refreshes. Their path, pattern,
  context SHA, category, and compatibility contract remain unchanged; historical
  report content was not edited.
- `uv run python scripts/rebrand_audit.py --check` is green with
  `unexpected=0` and `stale=0`; `tests/test_product_identity.py` is 142/142,
  with the targeted rebrand/audit slice 10 passed. Repository Ruff check and
  format check pass (901 files), as do diff-check and staged Gitleaks (5.22 KB,
  no leaks).
- Commit `addfc044` (`fix(identity): reconcile final release receipts`) contains
  exactly the four approved plan/spec/audit/allowlist files. Existing Task 3–5
  report modifications, supplied contexts, and generated bytecode remain
  uncommitted. Open: Sol cumulative/fresh review, local-main integration, and
  the existing signing/notary, Windows, credential/Support, publication, and
  backup-cleanup gates; no app/browser/network/install/remote action occurred.

## Task 5 identity repair correction — 2026-08-21

- Corrected the allowlist accounting: deterministic regeneration refreshed three
  existing explanation strings total—the `desktop/tests/test_release_manifest.py`
  line-45 release-manifest entry plus the `ThemeGallery.test.tsx` and
  `theme-storage.ts` entries. Identities, categories, compatibility contracts,
  and context hashes remained appropriately governed; no allowlist policy or
  historical report content changed.
- The cleanup plan/spec now record the exact shell-safe checkout
  `/Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.worktrees/today-productization`.
- Fresh gates: rebrand audit `unexpected=0`, `stale=0`; product identity
  `142 passed`; staged diff-check passed; staged Gitleaks scanned 257 bytes with
  no leaks. The docs-only commit remains the next handoff step.

## Task 5 identity repair commit completion — 2026-08-21

- Commit `56a10c4a` (`fix(docs): restore exact cleanup checkout`) contains
  exactly the two owned plan/spec files and no allowlist or historical-report
  changes.
- Post-commit gates remain green: strict rebrand audit
  `unexpected=0/stale=0`, product identity `142/142`, range
  `git diff --check 7e8fcc49..HEAD`, and Gitleaks over 18 commits / 157,378
  bytes with no leaks.
- Exact status preserves the pre-existing modified Task 3/4/5 reports, both
  supplied task contexts, and fourteen generated untracked desktop bytecode
  files. No product, app, provider, network, install, merge, push, or release
  mutation occurred. Open: Sol's cumulative review and local-main integration;
  external signing/notary, Windows, credential/Support, publication, and
  backup-cleanup gates remain open.
