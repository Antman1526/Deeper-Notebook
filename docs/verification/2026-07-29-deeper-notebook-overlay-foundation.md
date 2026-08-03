# Deeper Notebook Overlay Foundation Verification

Date: 2026-07-29 through 2026-07-30
Tested implementation commit: `bacca6ad`
Verification record parent: `bacca6ad`
Branch: `codex/deeper-notebook-overlay-productivity`

## Result

Plan A passed its macOS native, backend, frontend, browser, rebrand, and
external-immutability gates. The controlled proof used only marked synthetic
roots beneath the canonical macOS temporary directory. It did not mount, scan,
or modify the real `2nd Brains` folder or any other private vault.

The app-owned overlay remained a separate authority from external vaults.
Daily replay, same-minute unique collision suffixing, update, stale-revision
conflict, restart hydration, backlinks/graph/search projection, and source
fingerprint preservation were all exercised.

The editor now receives an explicit body-only `editable_markdown` field while
the canonical file and its reserved `deeper_notebook` frontmatter remain
server-owned. Per-tab unsaved drafts survive editor unmounts and tab switches,
and are cleared only after a successful page adoption, explicit tab/pane close,
or workspace reset. A filesystem compare-and-swap drift is surfaced through
the same recoverable HTTP 409 revision-conflict flow.

## Automated gates

All commands ran from the feature worktree unless a frontend working directory
is shown.

| Gate | Command | Result |
| --- | --- | --- |
| Focused backend and verifier | `uv run pytest -q tests/test_overlay_contracts.py tests/test_overlay_migration.py tests/test_overlay_paths.py tests/test_overlay_storage.py tests/test_overlay_repository.py tests/test_overlay_service.py tests/test_overlay_api.py tests/test_vault_security.py tests/test_vault_note_read_only.py tests/test_knowledge_workspace_persistence.py tests/test_knowledge_workspace_api.py tests/test_verify_overlay_foundation.py` | exit 0; 290 passed |
| Replay/body regression | `uv run pytest -q tests/test_overlay_service.py tests/test_overlay_api.py tests/test_overlay_contracts.py` | exit 0; 52 passed |
| Focused frontend | `npx vitest run src/lib/api/overlay.test.ts src/lib/api/knowledge-workspace.test.ts src/lib/stores/knowledge-workspace-store.test.ts src/components/overlay src/components/vault/KnowledgeExplorer.test.tsx src/components/vault/KnowledgePaneContent.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx src/components/vault/VaultCodeMirror.test.tsx src/lib/locales/index.test.ts --pool=forks --maxWorkers=1` | exit 0; 292 passed |
| Full backend | `uv run pytest -q` | exit 0; 3,949 passed, 48 skipped |
| Full frontend unit | `npm test` | exit 0; 955 passed |
| Frontend lint | `npm run lint` | exit 0 |
| Strict frontend types | `npx tsc --noEmit` | exit 0 |
| Production build | `npm run build` | exit 0; 22 static/dynamic routes built |
| Mocked browser | `npm run test:e2e:mocked` | exit 0; 9 passed |
| Rebrand audit | `uv run python scripts/rebrand_audit.py --check` | exit 0; no unexpected or stale entries |
| Diff hygiene | `git diff --check` | exit 0 |

The two overlay browser cases proved:

1. owned daily and unique creation/editing without external-vault mutation;
2. daily replay, deterministic `-2` collision suffixing, save conflict and
   draft preservation across a tab switch, restart hydration, and focus
   restoration.

The strict fixture exposes canonical `note.content` with reserved frontmatter
separately from body-only `editable_markdown`. The source editor asserted that
reserved frontmatter was absent, and update responses regenerated canonical
content from the submitted editable body. Backend regressions also rejected a
client attempt to submit reserved canonical frontmatter as an editable body
before any update reservation or filesystem write.

The strict browser fixture recorded every external-vault
`POST`/`PUT`/`PATCH`/`DELETE`, including scan requests. Overlay mutations were
observed while the external mutation ledger and unexpected-traffic ledger both
remained empty. Actual filesystem fingerprint preservation was proved by the
native verifier, not inferred from mocked browser state.

The older command-navigation and editor-mode browser cases also passed after
their strict fixture learned the new read-only overlay-list request.

## Post-review verifier hardening

Independent review found and closed four fail-closed evidence gaps:

- malformed or empty OpenAPI inventories are rejected;
- unrecognized mutating vault `POST` routes are unsafe by default, while the
  three existing metadata/read-only projection routes are explicitly allowed;
- report, token, marker, restart-state, overlay-root, and external-root
  locations must be disjoint, and reports are published by private atomic
  replacement;
- authentication-token files must be owner-only.

The four new adversarial regressions brought the verifier suite to 11 passing
tests. The hardened audit was also run directly against the application's real
generated OpenAPI inventory: 13 vault routes were observed, the only three
`POST` routes matched the explicit allowlist, and zero unsafe routes remained.

## Final integration review fixes

Independent whole-branch review found two integration defects after the
initial controlled proof: the editor consumed full canonical Markdown instead
of body-only Markdown, and component-local drafts could be lost when a tab
unmounted. Commit `33c6ffd5` closed both defects and added the recoverable 409
mapping for filesystem CAS drift.

A final adversarial pass found one narrow concurrent idempotency replay branch
that returned a repository page before body hydration. Commit `bacca6ad`
routes that branch through the same canonical storage read as every other page
response and adds a regression that simulates the concurrent winning commit.
The reviewer reported no Critical or Important findings at `bacca6ad`.

Fresh validation at that exact implementation commit included the complete
Python suite, replay/body regression suite, frontend unit, lint, strict-type,
production-build, rebrand-audit, and mocked-browser gates listed above. The
verification-record commit contains documentation only and has `bacca6ad` as
its parent, so the tested code tree is unambiguous.

## Native SurrealDB and migration evidence

SurrealDB 2.1.0 ran natively from the packaged desktop binary cache. The
application ran as a native API process; no Docker runtime was used.

- A fresh database upgraded from version 0 through migration 37 and reported
  version 37.
- A pre-existing version-36 database upgraded through migration 37 and reported
  version 37.
- A separate native syntax proof executed migration 37 up, its intentionally
  sticky down migration, and migration 37 up again. The command exited 0, the
  down result returned `schema_preserved: true` and
  `repaired_index_restored: false`, and final table metadata showed no
  `idx_overlay_daily` index.
- Migration 37 removes the SurrealDB 2.1 composite unique index that treated
  every unique note's optional `date_key` as the same `NONE` value. Daily
  uniqueness remains enforced by deterministic daily note identity and
  idempotency; unique path races remain protected by `idx_overlay_path`.

## Controlled native restart proof

The verifier was run twice with the identical command, marked overlay root,
authentication-token file, synthetic external fixture, and database:

```text
uv run python scripts/verify_overlay_foundation.py \
  --api-url http://127.0.0.1:49134 \
  --auth-token-file <disposable-token-file> \
  --overlay-data-root <marked-disposable-overlay-root> \
  --external-fixture-root <marked-synthetic-external-root> \
  --report-path <disposable-report-path> \
  --run-controlled-proof
```

Phase 1 exited 4 with the expected
`native_restart_requires_external_restart` state. Phase 2, after an exact API
restart, exited 0 and reported `controlled proof: PASSED`.

| Evidence | Phase 1 | Phase 2 |
| --- | --- | --- |
| API PID | `60304` | `63105` |
| API nonce SHA-256 | `cc3ae7f7fa0b9a15fb1b6a3922713bd658dc5fbc5b6a02ebce196ae22dd8b1b8` | `bca63f8a8043d9ed6a9565e5bfc69f1c1814862f05d13bb7ba9749f0633ac86c` |
| Overlay-root SHA-256 | `f2b2e340173949d364e4a67c9b5f3c723582e72aba34c4d4576f1d60fd3da5e8` | same |
| Restart state | pending | passed |
| Persistence state | pending | passed |

Persisted overlay sources after restart:

| Relative path | Revision | SHA-256 |
| --- | ---: | --- |
| `Daily/2026-07-30.md` | 1 | `5d49ef8a6076e139ad540052ee9c1335c0b9d38c870c29edb5ce1f2f85f66825` |
| `Notes/20260730-0719 Controlled Proof.md` | 2 | `e516232f02b4f69ad9ed365624d98deb037e352a0be7a2e5d22fac240cc2a83d` |
| `Notes/20260730-0719 Controlled Proof-2.md` | 1 | `d7ee2a222b3b4c0eb6af0420ff25cfe0da9a5fffa8e872534e14815708dfc340` |

The verifier also confirmed exact overlay IDs, revisions, and hashes survived
the process boundary. It pinned API identity before and after each phase and
recorded request IDs without recording authentication tokens or note contents.

## External immutability and write-path audit

The synthetic external Git repository was clean before and after:

- Git-status digest before and after:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Git index fingerprint before and after:
  `9e358799214188fdbc2131d1ce89b41282f6cc33b726f9b0885929b8e6170ba0`
- `evidence.md` fingerprint before and after:
  `0bd2e635098edb18ef37abe89b3464ccbeb2865f9fcb10fe0b4fe3af84d2e91e`
- Every other recorded file fingerprint was equal before and after.
- The OpenAPI route audit found no unsafe external-vault mutation route.

The static client/route search for external vault update, delete, rename, move,
write, save, or editable content returned no matches. The filesystem primitive
search found overlay writes only in `deeper_notebook/overlay/storage.py`, where
they are descriptor-bound and receipt/snapshot controlled.

## Runtime ownership and shutdown

Only the exact disposable processes were stopped. API PIDs `60304` and `63105`
and the SurrealDB PID were confirmed dead; TCP ports 49133, 49134, and the
separate migration-proof port 49135 were confirmed free. No live mount, scan,
API, or SurrealDB proof runtime remained.

## Non-blocking warnings

- Pydantic, Starlette/httpx, LangGraph serializer, and SWIG deprecation
  warnings remain upstream dependency warnings.
- The controlled API emitted expected podcast-profile warnings because the
  disposable database intentionally contained no model credentials.
- Playwright's web server reported that `FORCE_COLOR` overrides `NO_COLOR`.
- Compatibility tests emitted expected warnings for deprecated environment
  aliases.

None affected gate results or external-vault isolation.

## Open gates and Plan A boundary

Real Windows packaged restart proof remains open. It is a release/platform
gate, not a macOS Plan A implementation failure.

The following remain outside Plan A: templates, scripts, Composer, global
bookmark folders/tags, Random Note, metrics, named workspaces, protected
write-back, Canvas, Bases, plugins, Sync/Publish, and mobile. They require
separate specifications and approval.
