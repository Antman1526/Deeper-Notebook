# 10 — Testing Strategy & Test Cases

> **4,906 backend tests** (1 skipped) · **940 desktop tests** (2 skipped) ·
> **1,832 frontend unit tests** across the frontend suite · Playwright browser matrices.
> Both Python suites gate `make build-mac`.

---

## 1. Test taxonomy

| Layer | Runner | Location | Count |
|---|---|---|---|
| Backend unit/functional | pytest 9.1.1 | `tests/` | 4,906 |
| Desktop | pytest (`.build-venv`) | `desktop/tests/`, `desktop/memory/tests/` | 940 |
| Integration (real DB) | pytest + SurrealDB | `tests/integration/` | opt-in |
| Frontend unit | Vitest 4.1.8 | `frontend/src/**/*.test.tsx` | 1,832 |
| Browser | Playwright 1.61.1 | `frontend/e2e/` | matrices |

```bash
make test                 # backend, hermetic
make test-integration     # needs SurrealDB; throwaway namespace
.build-venv/bin/python -m pytest -q desktop/tests/ desktop/memory/tests/
cd frontend && npx vitest run
cd frontend && npx playwright test --project=mocked-browser
```

## 2. Test archetypes unique to this codebase

### 2.1 Source-shape guards

Tests that read source files and assert on their **text**, protecting invariants a
behavioural test can't reach:

```python
def test_cancel_command_job_guards_private_core_service_import():
    """The surreal_commands.core.service import is wrapped in try/ImportError
    so an upstream rename doesn't silently break all job cancellation."""
    src = _read_source("api/command_service.py")
    assert "try:\n                from surreal_commands.core.service import" in src
    assert "except ImportError:" in src
    assert "from deeper_notebook.database.repository import repo_query" in src
```

> **They are brittle by design, and that has a cost.** These fire on formatting changes:
> a `ruff --fix` import reflow and a 6-line insertion each broke one during this project.
> When one fails, ask whether the *invariant* is violated or only its spelling — then fix
> the code, not the assertion.

### 2.2 Fixed-window greps

```python
idx = src.index("async def get_source(")
region = src[idx : idx + WINDOW]
assert "insights_count=insights_count" in region, (
    "regression: endpoint queries the count but doesn't pass it to SourceResponse"
)
```

Insertions that push the target past the window produce a confusing failure. Keep
additions compact inside guarded regions.

### 2.3 Contract tests over generated output

```ts
it('uses a static process.env property reference for every public flag', () => {
  for (const name of PUBLIC_FLAG_NAMES) expect(source).toContain(`process.env.${name}`)
})
it('never uses dynamic process.env lookup for client feature flags', () => {
  expect(source).not.toMatch(/process\.env\s*\[/)
})
```

Dynamic lookup would defeat Next's build-time inlining and silently disable a flag.

### 2.4 Governance tests

`tests/test_product_identity.py` (141 tests) runs `scripts/rebrand_audit.py --check` and
asserts zero unexpected active identity, exact contract digests, and no stale allowlist
entries. `tests/test_persisted_queue_identifiers.py` asserts queue identifiers come only
from the AST inventory.

## 3. Browser matrices

`frontend/e2e/source-gallery.spec.ts` is the reference pattern: dimensions come from a
**route manifest**, so cells can't silently disappear.

```ts
export const SOURCE_GALLERY_CELLS = [
  { id: 'sources-ready', route: '/sources', state: 'ready',      flags: 'enabled' },
  { id: 'sources-feature-off', route: '/sources', state: 'feature-off', flags: 'feature-off' },
  ...
] as const
```

Three matrices, each with an exact request ledger:

| Matrix | Build flags | Result |
|---|---|---|
| Enabled | `V2=1 SOURCE_VISUALS=1` | 8 cells × 3 themes × 4 viewports = **96**; max CLS 0.0028 |
| Dual-off | `V2=0 SOURCE_VISUALS=0` | 20 cells; **0 visual reads, 0 mutations** |
| Enabled build / disabled backend | `V2=1` + backend off | 20 cells; no `<img>`, no actions |

The third matrix exists because it is the state a **packaged rollback** actually produces
(frontend flags are frozen at build time). Its absence was a real finding.

The ledger asserts request-count equality, not just success:

```ts
export function assertExactSourceGalleryLedger(fixture) {
  expect(fixture.ledger.unexpected).toEqual([])
  expect(fixture.ledger.external).toEqual([])       // zero third-party requests
  expect(delegatedSeen).toEqual(delegatedExpected)  // exact counts
}
```

## 4. Runtime budget receipts

Matrices emit a machine-checkable receipt:

```json
{ "schema": "deeper-notebook.source-gallery-runtime-budget.v1",
  "mode": "enabled", "maximumCls": 0.0027664303626543213, "clsLimit": 0.05,
  "viewportCells": 96, "expectedViewportCells": 96,
  "visualRequestCount": 84, "visualMutationCount": 24,
  "unexpectedCount": 0, "externalCount": 0, "passed": true }
```

New cells that shouldn't disturb a receipted proof are excluded from the budget counter
deliberately, so historical receipts stay comparable.

## 5. Integration protocol

```bash
SURREAL_INTEGRATION=1 uv run pytest -q \
  tests/integration/test_source_visual_repository.py -m integration_surreal
# 9 passed
```

Fresh disposable `onp_test_<uuid>` namespace per run. The visual repository proof covers:
migration down/up, SCHEMAFULL unknown-field rejection, unique `(source_id,
content_sha256)`, claim contention, live-owner fencing, 90 s stale takeover, request
replay/conflict, atomic finalization, restart hydration, bounded eviction, delete fencing,
and **byte-for-byte preservation of every pre-existing source row**.

## 6. Test-isolation hazards (learned the hard way)

**Env mirroring.** Product normalization copies canonical names into legacy spellings;
`monkeypatch` can't undo writes it didn't make. Clear every spelling from the registry, or
patch the predicate:

```python
monkeypatch.setattr(
    "deeper_notebook.tools.scholarly_search.scholarly_search_enabled", lambda: False
)
```

**Client pooling.** Pool identity is keyed on the client *class*, so a monkeypatched
client in one test is never served to another. Tests assert this directly.

**Always-on tools.** Adding a default-bound tool breaks every "no tools bound" test.
Disable it the same way the test already disables its siblings — don't weaken assertions.

## 7. Flake register

Timing-scaled tests that fail only under machine load ≳20 (Backblaze syncing build
artifacts, in the observed case) and pass in isolation:

- `tests/test_vault_parsers.py::test_projection_budget_subprocess_rss_and_time_are_bounded`
- `tests/test_vault_parsers.py::test_logseq_task_tag_association_scales_linearly`
- `frontend`: `brand.test.ts`, `workspace.test.tsx`, `KnowledgePodcastPane.test.tsx`

The build gate retries **only failed** backend tests once. A deterministic failure still
fails twice; a load blip no longer kills a 25-minute build. Loosening the budgets was
rejected — that would discard the signal the tests exist to provide.

Environmental in the other direction: `test_repair_desktop_db_script.py` **cannot** pass
while the app or SurrealDB runs, so the gate preflights and fails fast with the remedy.

## 8. Writing a new test — checklist

1. Name states the invariant, not the mechanism.
2. Docstring says *why* — cite the failure that motivated it.
3. One failure path minimum (timeout, malformed payload, missing dependency).
4. No network. Patch `httpx.AsyncClient`; live checks belong in a manual/integration lane.
5. Reset module state in fixtures (`reset_web_search_caches`, `reset_scholarly_cache`).
6. If it asserts on source text, say so and pin the smallest possible literal.

---

*Continues in [11 — Build & Deployment Pipeline](./11-build-deployment-pipeline.md).*
