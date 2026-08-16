# Gemini-Forward Phase 2A Source Gallery — Acceptance Receipt

Date completed: 2026-08-15

Implementation range: `e9eb5add` through this final exact-scope commit

Task 12 base: `0c073aca`

Final commit subject: `feat(ui): deliver local source visual gallery`

## Outcome and scope

Phase 2A delivers a default-off, local-only Source Visual Gallery across Sources,
Notebook, Knowledge, Search, and Capture. Visuals are bounded static WebP
derivatives with visible provenance; they are presentation aids and never evidence.
The existing non-visual routes remain authoritative when either feature flag is
off.

This receipt does not claim native signed or notarized packaging, hosted CI,
deployment, or public release. None of those actions was authorized or performed.

## Implementation authority

- The Phase 2A implementation follows the approved specification at `bbd67220`
  and the aligned plan at `26e896bf`.
- The cumulative Source Gallery implementation contains 61 commits after the
  Phase 1 closeout `e9eb5add` and touches 94 tracked paths before this receipt.
- Task 12 introduced no dependency change: `pyproject.toml`, `uv.lock`, and
  `frontend/package.json` are unchanged by its final repair range.
- Migration 46 SHA-256 values used by the real-database proof are:
  - up: `d64bdbbf2bcb7d8e56c961b080a03295767c6a64483d772cab311e83f3b38e34`
  - down: `eb27dab48545ef59f8cc4c77e2f5d60ebf082398745d83804ac6ac9fdd706c31`

## Strict RED evidence

Task 12 began with a new real-Surreal integration contract before production
repair. The first exact run failed 4 tests in 11.33 seconds: live-owner
contention, request-conflict replay, and duplicate cache identity were not
enforced by the installed driver path, while the migration metadata fixture
needed result-shape normalization.

The expanded contract then failed 5 tests and passed 2. It exposed a SurrealQL
parse failure in atomic command finalization, SCHEMAFULL accepting an unknown
field, and current-ready projection omitting a successfully published row.
After narrowing those repairs, a delete-intent test still failed because a
forbidden ready cache row was written before `DELETE_REQUESTED` surfaced.

The final added post-delete receipt regression also failed first: an unbound
new refresh returned false instead of requiring reacquisition. Intermediate
queries exposed incompatible `IF` syntax, result envelopes discarded by the
driver, strict unknown-field rejection of helper projections, and validation
against `command_id=None` after exact command binding. Each failure was retained
until the smallest production repair made its exact selector green.

## Real SurrealDB and preservation proof

The final 619-line integration file is
`tests/integration/test_source_visual_repository.py`. The exact command was run
twice in separate fresh fixture processes:

```text
SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_source_visual_repository.py -m integration_surreal
9 passed in 22.28s

SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_source_visual_repository.py -m integration_surreal
9 passed in 22.43s
```

Every run used a fresh disposable loopback `onp_test_<uuid>` namespace and the
fixture teardown. The matrix proves:

- migration 46 down/up, SCHEMAFULL unknown-field non-persistence under the
  installed SurrealDB filtering semantics, deletion of a valid seeded visual
  cache row on downgrade, and byte-for-byte preservation of every pre-existing
  source row;
- unique `(source_id, content_sha256)` cache authority;
- independent-client claim contention, live-owner fencing, and 90-second stale
  takeover;
- exact request replay/conflict, claim-command binding, and atomic operation
  finalization;
- concurrent ready publication, stale-source omission, and current projection;
- file-before-DB and DB-before-cleanup recovery, deletion restore, restart
  hydration, and bounded eviction;
- queued delete fencing without a forbidden cache write, followed by a later
  exact bound refresh that may publish; and
- post-delete commandless refresh reacquisition until the current exact claim
  command is durably bound.

No application namespace or user database was used.

## Regression and static gates

- Affected backend matrix after the final review repair: 339 passed, 7 warnings.
- Full backend non-integration suite after final review repair: 4712 passed,
  1 skipped, 19 warnings in 225.18 seconds.
- Full frontend unit suite: 240 files and 1769 tests passed.
- Frontend TypeScript: `npx tsc --noEmit` exited 0.
- Frontend lint exited 0 with three pre-existing unused-variable warnings
  (two in Study Voice Tutor and one `_fullText` test parameter).
- Identity, migration discovery, and persisted queue inventory: 160 passed,
  6 warnings.
- Repository focused matrix after final review repair: 36 passed.
- `uv lock --check`, scoped Ruff, compileall, and `git diff --check` exited 0.
- Rebrand audit exited 0 with compatibility/historical/migration/unexpected/
  upstream counts `829/1749/587/0/99` and zero stale entries.

The Task 12 queue and command repairs retain the persisted application identity
literal `open_notebook`; the refreshed audit inventory and allowlist describe
that compatibility boundary without changing the product identity.

## Browser, rollback, accessibility, and budgets

Task 11's final browser authority remains valid because Task 12 did not change
frontend runtime, CSS, browser fixtures, route manifest, or visual receipt
decoder authority.

- Source Gallery enabled: 33 passed, 1 expected skip; 96/96 cells; maximum CLS
  `0.006388483705218826`; 84 visual reads; 24 visual mutations; zero unexpected
  or external requests.
- Explicit dual-feature-off rollback: 10 passed, 24 expected enabled skips;
  20/20 route/viewport cells; zero visual reads and zero visual mutations.
- Phase 1 compatibility matrix: 280 passed, 1 expected explicit-off skip;
  all 264 route/theme/viewport cells passed.
- Enabled and explicit-off production builds generated 23/23 static pages;
  the feature-build contract exited 0.
- Bundle budget: JavaScript gzip delta -4 bytes and CSS delta 0 bytes.
- Extraction proof: PDF 2 candidates/19170 bytes, video 3/5736, audio 1/1950;
  all below 60 seconds. Cache was 26856 bytes, below the 2 GiB bound, with zero
  source-row queries and no source-row mutation.
- The browser proof covers useful alt text, visible provenance, 44px actions,
  high contrast, reduced motion, focus return, no horizontal overflow, all
  clipping ancestors, true vertical scroll reachability, and client-box
  containment at compact and large sizes.

## Security and tool availability

- Frozen advisory input export completed without changing the lock.
- Bandit was unavailable in the configured environment (`uv run bandit` exited
  2 because the executable was absent).
- `uvx pip-audit -r /tmp/gemini-phase2a-requirements.txt --no-deps` stopped in
  the host bootstrap before auditing because Python `ensurepip` died with
  `SIGABRT`. This is recorded as an environment limitation, not a green audit.
- No dependency file changed in Task 12, so no new Phase 2A dependency was
  introduced by the final repair.
- Exact staged and commit-range Gitleaks receipts are recorded after the final
  commit below.

## Fresh review

The first fresh-context review found three Important authority/proof gaps:
`bind_command` could synthesize an unpersisted command after an opaque failed
transaction, expired claims could clear the post-delete reacquisition fence or
repair a queued receipt, and the initial migration receipt overstated unknown
field behavior and did not seed a cache row before downgrade. Strict unit RED
was 3 failed. The migration extension was already green against the installed
engine and established its actual filtering semantics.

The repair now requires the persisted command to equal the requested command,
rejects expired claims during finalization, treats an expired post-delete claim
as requiring reacquisition, and proves that downgrade removes a valid cache row
without changing source bytes. Focused GREEN is 3/3; the repository unit module
is 36/36; the real-Surreal matrix is 9/9 after the repair.

The final fresh-context re-review APPROVED the repaired Task 12 diff and this
receipt with no Critical or Important findings. OCR preview/rules succeeded.
Code Review Graph was unavailable because `graphify-out/graph.json` was absent;
the native Sol review path remained authoritative.

## Cleanup and exclusions

- Generated `desktop/build/__pycache__` files created by compileall were
  validated as task-owned and removed; the directory is absent.
- Browser result directories are absent and the canonical tracked
  `frontend/test-results/.last-run.json` remains unchanged.
- Supplied `.codex/agent-context/*` files remain untracked and are not part of
  the final commit.
- No native package, signing/notarization, hosted CI run, deployment, public
  release, user-data migration, or external publication was performed.

## Final exact-scope receipt

The intentional Task 12 commit contains the real-Surreal integration proof,
database-driver compatibility repairs demonstrated by that proof, exact API and
persisted-queue identity compatibility fixes, their unit regressions, refreshed
rebrand metadata, the one frontend test stabilization, and this receipt. No
generated artifact, dependency file, or supplied agent-context file belongs to
the staged scope.

The exact commit subject is `feat(ui): deliver local source visual gallery`.
Staged and commit-range diff/secret-scan results are reported in the final task
handoff after the commit; this commit is the implementation-range endpoint named
at the top of this receipt.

## Addendum — 2026-08-15, release-gate coverage

Added after `5e662990` during release-candidate preparation. This addendum does
not restate or revise any measurement above; all of them still hold.

### Why a cell was missing

`NEXT_PUBLIC_*` flags are inlined by `next build`, and `build-mac-frontend`
runs a plain `npm run build`. At runtime `desktop/launcher.py` injects only
`NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_API_BASE`, never the gallery flags. An
installed app built with the gallery on therefore cannot turn its client gate
back off; only `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0` remains as a runtime
kill switch. The emergency rollback state for a packaged enabled build is
**client-on, backend-off**, which the dual-off matrix never exercised — every
`state: 'feature-off'` cell in the route manifest is paired with
`flags: 'feature-off'`.

Consequence for sequencing: the rollout flag decision must precede the release
candidate build, not follow it.

### New cell and result

`frontend/e2e/source-gallery.spec.ts` gains
`enabled build against a disabled backend keeps all five routes usable with
zero visual requests`, running the five `feature-off` cells across four
viewports under an enabled build.

```text
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 \
  npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser
34 passed, 1 skipped
```

- 20 route/viewport combinations, zero visual reads, zero visual mutations.
- Covers degrade to the titled fallback: no `<img>`, status reads
  `Visual cover unavailable`, no page errors, exact request ledger.
- The cell is deliberately excluded from the enabled runtime budget receipt so
  the receipted 96-cell proof stays comparable. Re-measured budget after the
  addition: 96/96 viewport cells, maximum CLS `0.0027664303626543213`.
- Dual-off matrix re-run after the addition: 10 passed, 25 skipped, 20/20
  cells, zero visual reads and zero visual mutations.
- `npx tsc --noEmit` exited 0. `npm run lint` exited 0 with the same three
  pre-existing warnings recorded above.

### Open finding, not fixed here

In the packaged rollback state the fallback cover still renders
`Refresh visual for <title>` and `Remove visual for <title>`. Those dispatch
`POST /visual:refresh` and `DELETE /visual`, which the backend guard at
`api/routers/source_visuals.py` 404s while the flag is off. `SourceCover`'s
`dispatch` catches the rejection and clears its pending state, so the result is
a silent no-op rather than a crash or a data change — dead controls, not broken
ones.

This is not fixed here because the client cannot distinguish "backend disabled"
from "visual not yet extracted" — both present as null `visual` and null
`visual_status`, and Refresh is legitimately useful in the second case. A real
fix needs the backend to surface capability, which is a new scope requiring
owner approval.
