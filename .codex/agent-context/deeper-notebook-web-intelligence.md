# Deeper Notebook Web Intelligence Foundation

## Objective

Implement the approved bounded web-intelligence slice in the correct Deeper Notebook checkout. Add one pure, provider-neutral normalization layer over the existing `deeper_notebook.tools.web_search` result shape.

## Required behavior

- Keep `run_web_search()` provider selection, failover, offline short-circuit, env-key opt-in, return shape, and citation capture unchanged.
- Add frozen/immutable evidence records with bounded query/provider/title/url/snippet, normalized HTTP(S) URL, retrieval timestamp, freshness (`fresh|stale|unknown`), degraded flag, deterministic source fingerprint, and deterministic evidence ID.
- Invalid records are skipped fail-closed; no new network clients, vault writes, watcher changes, or secrets in logs.
- Add focused TDD tests first, then implementation and compatibility tests.

## Files in scope

- `deeper_notebook/tools/web_evidence.py` (new)
- `tests/test_web_evidence.py` (new)
- design/plan docs supplied by Sol

## Verification

- `uv run pytest -q tests/test_web_evidence.py`
- `uv run pytest -q tests/test_v0_8_64_web_search.py tests/test_search_api.py tests/test_research_api.py`
- `uv run ruff check deeper_notebook/tools/web_evidence.py tests/test_web_evidence.py`
- `git diff --check`

## Independent review repair receipt

The first review found four bounded-input defects that must be repaired before integration:

- `max_results` currently caps accepted records but not examined entries; add a fixed examined-entry ceiling so invalid or infinite iterables cannot run unbounded.
- Reject unpaired Unicode surrogates before canonical UTF-8 hashing; malformed provider text must be skipped, not raised.
- Bound raw string size before trimming; reject oversized hostile strings before `.strip()` scans them.
- Make the freshness test clock-independent instead of asserting a fixed historical timestamp remains fresh forever.

Add regression tests for each defect, run the focused/compatibility suites, Ruff, and diff checks, then commit the repair separately from `a5376693`.

## Coordination

Read `/Users/Antman/.codex/context.md` before work. Preserve unrelated user changes. Do not push or modify vault/source directories. Append a concise durable result and open items to `/Users/Antman/.codex/context.md` before returning to Sol.

## Worker milestones

- RED complete: `uv run pytest -q tests/test_web_evidence.py` failed at
  collection with the expected `ModuleNotFoundError` for the new module.
- GREEN implementation is in progress in the scoped pure adapter; no provider,
  network, vault, watcher, frontend, or credential paths were touched.
- GREEN complete: focused evidence tests pass 4/4, compatibility tests pass
  53/53 across web-search/search/research, and scoped Ruff passes.

## Final receipt

- Scope review found only the pure adapter, focused tests, design/plan docs;
  no provider keys, network clients, vault paths, watchers, frontend/backend
  callers, or generated files changed. `git diff --check` passes.
- Final verification rerun: focused evidence 4/4, compatibility 53/53, Ruff,
  and both working/staged diff checks pass. No external network or vault proof
  is part of this slice.
- Commit `a5376693` (`feat(web): add normalized evidence foundation`) contains
  exactly the pure adapter, focused tests, design, and completed plan docs.

## Task 2A bounded-input repair — 2026-08-08

- RED against `a5376693`: focused evidence tests passed 4 and failed 3,
  reproducing unbounded invalid-entry traversal (1,000 examined), acceptance
  of a 2,049-space-prefix title after trimming, and an unpaired-surrogate
  `UnicodeEncodeError` during canonical hashing. The baseline fixed-date
  freshness assertion was changed to a runtime-relative timestamp.
- GREEN: the adapter now stops after a fixed 100 examined entries independent
  of accepted `max_results`, rejects raw text above a documented 4x field-size
  multiple before trimming, validates UTF-8 encodability for query/provider,
  title/snippet, and URL values, and skips malformed Unicode entries. URL and
  query surrogate regressions were added alongside the title regression.
- Verification: focused plus compatibility suites pass 62 tests; scoped Ruff
  and `git diff --check` pass. No provider, network, vault, watcher, frontend,
  backend, credential, or generated-source paths changed. Unrelated
  `desktop/build/__pycache__/` remains untracked and untouched.
- Open: parent reconciliation/review remains; no external network or vault
  proof is part of this pure-adapter repair.
- Commit `7eb34789` (`fix(web): bound evidence normalization inputs`) contains
  only the adapter, focused regressions, and the updated tracked plan; this
  supplied task context remains intentionally untracked.

## Native proof and idempotency closeout — 2026-08-09

- Added a deterministic receipt claim gate to `KnowledgeRepository.commit_snapshot` so concurrent identical projections resolve to one `projected` and one `unchanged` result instead of double-projecting. The claim lock is scoped per running event loop and operation ID; persisted failed receipts remain retryable.
- Updated native integration rollback helpers and expectations for migration 40 (Podcast Intelligence Studio metadata), and kept historical rollback coverage intact.
- Controlled native proof used the bundled SurrealDB 2.1.0 binary on isolated `127.0.0.1:18000` memory storage; no existing Docker database or vault was touched.
- Final receipt: `SURREAL_INTEGRATION=1 SURREAL_URL=ws://127.0.0.1:18000/rpc uv run pytest -q -m integration_surreal` => 63 passed, 1 skipped, 8 warnings. Focused repository/migration tests => 28 passed; Ruff and diff checks clean.
- Child mounts, trust import/idempotency, source-hash preservation, backlinks/graph, projection children, replay/idempotency, source fingerprint and migration rollback paths are covered by the passing native suite. Runtime was stopped and isolated temporary state was discarded.
- Open: podcast generation UI/evidence linkage and inherited TypeScript baseline diagnostics remain separate release work; no push was performed.

## Release gate cleanup — 2026-08-09

- Regenerated the three static theme bundles and corrected the renderer to emit a single final newline. Commit `f0594818`; theme static-assets tests pass and the full non-native backend gate is now `4659 passed, 3 skipped`.
- Closed the inherited frontend test-only TypeScript diagnostics with typed media-query callbacks, optional target guards, and a safe theme-ID assertion. Commit `ad4ab9c0`.
- Frontend final receipt: `npm test` => 169 files / 1332 tests passed; `npm exec tsc -- --noEmit` passes; `npm run lint` passes; `npm run build` passes.
- Current checkout remains local-only, main is 315 commits ahead of origin, and the three handoff context files plus unrelated `desktop/build/__pycache__/` remain untracked and preserved.
