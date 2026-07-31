# Deeper Notebook unified knowledge-engine foundation verification — 2026-07-31

## Verdict and tested tree

- Branch: `codex/unified-knowledge-engine-foundation`.
- Exact complete-gate tested tree:
  `65c99283b38ab4f070f081b13e0721641370e56e`
  (`fix(knowledge): bind startup checkpoint proof`).
- Exact controlled native proof implementation commit:
  `65c99283b38ab4f070f081b13e0721641370e56e`.
- Verdict: the macOS native, shadow-only unified knowledge-engine foundation
  passed its focused, complete-project, migration, controlled-restart, source
  preservation, and cleanup gates.
- The documentation commit follows the tested implementation tree. A
  documentation commit cannot contain its own final hash, so the tested
  implementation commit above is the stable proof anchor.
- No product feature was cut over to the unified engine. Existing compatibility
  read paths remain authoritative.

## Safety boundary

- The controlled proof used generated, marker-owned roots beneath the canonical
  macOS system temporary directory.
- The real `/Users/Antman/Desktop/2nd Brains` and
  `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains` folders were not
  mounted, scanned, read, fingerprinted, or modified. This record does not
  infer proof for either folder.
- No Docker runtime was used. Deeper Notebook, its API, and SurrealDB ran
  through native host processes.
- No token, note body, credential, database password, or real/private vault
  source path is recorded here. The disposable synthetic proof path is retained
  only as a command receipt.
- External write-back remains outside this foundation. Trust import creates a
  compatibility record; it does not grant external write capability.

## Foundation implemented

The tested tree introduces one strict domain model for app-owned Overlay notes
and read-only external vault content:

- typed spaces, documents, revisions, identities, links, tasks, trust records,
  projection receipts, and restartable backfill checkpoints;
- migration 38 storage with transactional snapshot replacement;
- canonical adapters for Overlay notes, vault files, trusted sources, and
  connector manifests;
- stable source, revision, and identity provenance;
- shadow dual projection behind disabled-by-default environment flags;
- resumable, idempotent startup backfill;
- authenticated, GET-only, redacted diagnostics and deterministic equivalence
  reports;
- exact text search, backlinks, graph edges, and task projection;
- parent/child vault isolation without identity aliasing;
- marker-gated two-phase native restart verification;
- fail-closed polling of the derived Overlay and actual parent-vault startup
  checkpoints before any controlled-proof mutation, followed by the derived
  child checkpoint after restart.

Migration 38 stores `schema_version: 1` explicitly on every replacement
snapshot. Projection digest selection is revision-bound and includes only the
legacy identity kinds that actually participate in compatibility equivalence.

## Feature flags and authority

| Configuration | Result |
| --- | --- |
| Shadow disabled, backfill disabled | No unified runtime or task starts; compatibility paths keep authority. |
| Shadow enabled, backfill disabled | Unified projection is available for shadow writes and diagnostics; no startup backfill runs. |
| Shadow enabled, backfill enabled | One tracked startup backfill runs and resumes through persisted checkpoints. |
| Shadow disabled, backfill enabled | Configuration fails closed; no partial unified runtime starts. |
| Invalid boolean value | Configuration fails closed and logs only the exception type. |

The flags used by the controlled proof were:

```text
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED=true
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_BACKFILL_ENABLED=true
```

## Focused and complete-project gates

All commands ran serially from the tested implementation tree.

| Gate | Exact command | Exit | Evidence |
| --- | --- | ---: | --- |
| Focused foundation unit tests | `uv run pytest -q tests/test_knowledge_engine_contracts.py tests/test_knowledge_engine_adapters.py tests/test_knowledge_engine_migration.py tests/test_knowledge_engine_repository.py tests/test_knowledge_engine_backfill.py tests/test_knowledge_engine_shadow.py tests/test_knowledge_engine_service.py tests/test_knowledge_engine_lifespan.py tests/test_knowledge_engine_api.py tests/test_knowledge_engine_equivalence.py tests/test_verify_unified_knowledge_engine.py` | 0 | 165 passed; 7 warnings; 0 failures. |
| Native SurrealDB integration | `SURREAL_INTEGRATION=1 SURREAL_URL=ws://127.0.0.1:18080/rpc uv run pytest -q tests/integration/test_knowledge_engine_projection.py -m integration_surreal` | 0 | 16 passed; 1 warning; 0 failures (35.38s). |
| Full Python regression | `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q` | 0 | 4,126 passed; 65 skipped; 28 warnings; 0 failures (182.32s). |
| Frontend unit regression | `cd frontend && npm test` | 0 | 118 files passed; 955 tests passed; 0 failures (65.45s). |
| Frontend lint | `cd frontend && npm run lint` | 0 | `eslint src/` completed without errors. |
| Frontend type check | `cd frontend && npx tsc --noEmit` | 0 | No diagnostics. |
| Production build | `cd frontend && npm run build` | 0 | Next.js 16.2.12 compiled, type-checked, and generated 22 pages. |
| Mocked browser regression | `cd frontend && npm run test:e2e:mocked` | 0 | 9 Playwright tests passed (19.4s). |
| Rebrand audit | `uv run python scripts/rebrand_audit.py --check` | 0 | `unexpected_active_identity: 0`; `stale_allowlist: 0`. |
| Diff hygiene | `git diff --check` | 0 | No whitespace errors. |

The Python warnings were dependency deprecations and shutdown-time websocket
warnings, not test failures. Playwright emitted `NO_COLOR`/`FORCE_COLOR`
warnings; all scenarios passed. The tracked
`frontend/test-results/.last-run.json` fixture was restored exactly after the
browser run.

## Migration and native repository proof

The focused/native integration gates prove:

- a fresh database upgrades `0 -> 38`;
- a recorded database upgrades `37 -> 38`;
- `38 down -> 38 up` preserves unified records;
- no legacy table or record is removed;
- a failed adapter projection retains the last valid snapshot;
- persisted checkpoint state survives repository and service reconstruction.

The final controlled namespace started fresh and reached migration 38. Its
read-only pre-cleanup receipt contained:

| Record | Count |
| --- | ---: |
| Engine spaces | 3 |
| Engine documents | 4 |
| Engine revisions | 5 |
| Engine identities | 31 |
| Projection receipts | 8 |
| Backfill checkpoints | 3 |
| Overlay notes | 1 |
| Vault mounts | 2 |
| Vault files | 4 |
| Trust records | 1 |
| Failed receipts | 0 |

The prepare phase refused mutation until both startup checkpoints were
terminal and successful: Overlay projected one document and the parent vault
projected one document. After the native API restart, the verifier required
those two checkpoints plus the child checkpoint to be terminal and successful;
the child projected two documents. All three reported `unchanged: 0` and
`failed: 0`.

## Controlled two-phase native restart proof

The proof used native SurrealDB 2.1.0 on loopback port `18080`, namespace and
database `task10_checkpoint_bound`, and the native API on loopback port
`18081`. A harness created disjoint, marked synthetic Overlay, parent-vault,
and child-vault roots. Production root validation stayed active for every path
except the harness's exact marked synthetic roots.

These are the supported verifier arguments used for prepare. The actual
marker-owned root is retained here only as a command receipt; it was moved to
Trash after verification:

```sh
PROOF_ROOT='/private/var/folders/7t/0h7852yd50v0kj5wrlw487980000gn/T/deeper-notebook-task10-bound.sY638t/proof'
PYTHONDONTWRITEBYTECODE=1 uv run python scripts/verify_unified_knowledge_engine.py \
  --api-url http://127.0.0.1:18081 \
  --auth-token-file "$PROOF_ROOT/token" \
  --report-path "$PROOF_ROOT/report.json" \
  --space-id knowledge_engine_space:1b4d675e2e6893aeb66e3ec459efa4fdb5d5f17f58018dcdb100c0f2d9fcab89 \
  --space-id knowledge_engine_space:581847b4de06ad6f8549980d5fcfbec99add009dd9d8728b33a09a8300575675 \
  --exact-query proof-needle-20260731 \
  --require-shadow-enabled \
  --proof-phase prepare \
  --synthetic-manifest "$PROOF_ROOT/manifest.json" \
  --expected-prior-state "$PROOF_ROOT/restart-state.json"
```

After stopping the exact API process and starting a new native API process
against the same SurrealDB namespace and marked roots, the identical command
ran with `--proof-phase verify`.

`prepare` exited 5 with the required
`knowledge_engine_restart_required` state. The original API PID was `26789`.
After an external stop/start, `verify` observed API PID `34344`, a new process
nonce, the same database, the same Overlay root identity, stable projection
identities, and exited 0.

The private, redacted result files were mode `0600` during proof execution:

| Artifact | SHA-256 |
| --- | --- |
| Final report | `ec0fd4610d89855abd81cf1601300448a3e6cfe7456aa04200726869d6f14204` |
| Restart state | `3199e0582cc399022a79bf4c80060f61f1eae18d247deafe4e3cb754ad710c19` |
| Projection snapshot | `aa868468275bfca78738563063e59e1660333526ffd8863b10c9fd901b2b6016` |
| Overlay snapshot | `0e79e14af349d424128cd99fc4e4cdafa8789b9a02eb64b9dccb3f1515ee62c4` |

The report asserted:

- `restart_verified: true`;
- `source_fingerprints_preserved: true`;
- `trust_import_idempotent: true`;
- two applicable equivalence spaces with no differences;
- exact query `proof-needle-20260731` returned the expected child document;
- Overlay update persisted as revision 2 with projection state `current`;
- one backlink, one graph edge, and one projected task persisted.

## Containment, trust replay, and equivalence

The child scan retained its parent relationship while projecting under its own
space identity. Its two present parsed Markdown files produced two knowledge
documents. The parent retained two present files: the trusted source and its
connector manifest.

Relative trust-manifest replay returned:

| Attempt | Changed | Unchanged | Resolved | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| First | 1 | 0 | 1 | 0 |
| Identical replay | 0 | 1 | 1 | 0 |

The parent was deliberately reclassified to
`trusted-source/unsupported` by trust import. It is therefore proved by
mount/file/hash/trust/idempotency evidence and is not presented as an
applicable legacy projection-equivalence space. Equivalence succeeded for the
Overlay and parsed child spaces, which are the two dual-projected spaces with
comparable legacy and unified views.

Before cleanup, every present synthetic vault-file hash matched its bytes on
disk. The parent trusted-source SHA-256 was
`86fe174e9e1a2a0fdaccca17e5b1b86fe463a7d3ed30b5e211dbc1a562b90579`;
its connector manifest was
`4a4ebb5e3170dfd2e81cb4d384446a91ed8f56b71c8c7f52553b478c5a5dbb0e`.
The child file hashes were
`7b862f5cd08929c6abbb8375ecbb21f852b2ab1194c1e17def9a1a131a2a2bb8`
and
`0af698ec5ae77c021113a330315c5f0de065b110826ad5d083e12d3f69a72a68`.
The current Overlay content hash was
`77c8fd3e55879f3ad8596faef1045d8fc46525a55319e6f6fbdaf9ee4059fc79`.
No note content is recorded.

## Cleanup proof

- Both native processes were stopped gracefully.
- Loopback ports `18080` and `18081` were verified free.
- Only the two exact marker-verified disposable proof roots were moved with
  `/usr/bin/trash`; they are absent from their original locations and remain
  recoverable from macOS Trash.
- The private report, manifest, restart state, database, and synthetic source
  trees are no longer present at their proof paths.
- No live proof runtime, mount, scan, backfill, or synthetic source remains.
- Docker and the unrelated port `8000` runtime were not touched.
- The repository worktree was clean after generated-fixture restoration.

## Independent review

Independent read-only review result: **approved**.

- Critical findings: none.
- Important findings: none.
- Minor findings: none.
- The initial review identified one Important checkpoint-binding gap: prepare
  accepted free-form manifest checkpoint IDs. Commit `65c99283` removed that
  field, derives Overlay and actual parent IDs in prepare, re-derives them from
  persisted parent state in verify, and independently derives the child ID.
- Repeat review confirmed the exact-schema rejection, supported CLI flags,
  commit/PID/exit/checkpoint/hash consistency, and passed 76 focused tests,
  Ruff, the rebrand audit, and `git diff --check`.

## Later gates and non-claims

This foundation does not claim:

- Windows packaged-app runtime proof, which remains a later release gate;
- a live proof against either real `2nd Brains` folder;
- write-back to external vaults;
- product cutover from compatibility reads;
- complete Obsidian or Logseq feature parity.

The next implementation phase is the Productivity Core on this normalized
engine. Tasks and Journals follow under their own plan. Broader
Obsidian/Logseq parity remains phased product work rather than a claim of this
foundation proof.
