# TODO

**Status: 2026-08-20 · desktop `0.8.114` (source) · server/container `1.8.5`**

Concrete, actionable work items. Strategy and rationale live in
[`ROADMAP.md`](ROADMAP.md); this file is the list you can pick from.

Every claim below is measured. Where a number appears, the command that
produced it is named so it can be re-run rather than trusted.

---

## 0. Blocked on you — I cannot do these

### 0.1 Revoke the leaked Google API key — **urgent, still open**

A live-format key (`AIza…`, 39 chars) is in git history and has been public on
GitHub. **Purging history does not un-leak it** — forks and clones retain it and
it may be indexed. Rotation in the Google Cloud console is the only real
remediation. This has been open across several sessions.

### 0.2 Purge the key and `history.txt` from git history

`git-filter-repo` was staged but the run is blocked by the permission
classifier, so it needs a human to execute. `history.txt` is a SurrealDB dump
carrying Fernet-encrypted credential blobs. This is hygiene, **not** a
substitute for 0.1.

### 0.3 Packaged v0.8.114 build — resolved 2026-08-20

The app was stopped, `make build-mac` completed, and the resulting v0.8.114
bundle was installed and smoke-tested. The original installation was retained
as a recoverable backup during verification.

---

## 1. Correctness — found 2026-08-20

### 1.1 Fix the 17 red integration tests — **root cause identified**

`SURREAL_INTEGRATION=1 uv run pytest tests/integration/` reports **17 failed,
104 passed**. These are *pre-existing* — the same 17 fail with this session's
migrations removed.

Fifteen are in `tests/integration/test_vault_projection.py` and share one cause:

```python
async def _restore_recorded_v32_state() -> None:
    await _restore_recorded_v35_state()
    ...
    DELETE type::thing('_sbl_migrations', 35);
    DELETE type::thing('_sbl_migrations', 34);
    DELETE type::thing('_sbl_migrations', 33);
```

The helper deletes migration rows **33–35 only**, but `get_latest_version()`
returns `max(version)` across every applied row. With migrations 36–50 also
present, it returns 50, and the tests assert `== 32`:

```
assert 49 == 32   # 49 was the head at the time; now 50
```

It has been failing since **migration 36** landed, and every migration since has
widened the gap. The helper was written when head *was* 35.

The fix is not a one-liner: correcting it means unwinding 33..HEAD, which needs
each down migration in that range to exist and be safe to apply. Decide between
that and re-scoping these tests to a dedicated namespace migrated only to v32.

### 1.2 Run the integration suite in CI — **the meta-lesson**

This is the highest-leverage item on the list.

Everything under `tests/integration/` is skipped unless `SURREAL_INTEGRATION=1`,
which nothing sets. Two separate defects survived for dozens of migrations
purely because of that:

* semantic search returned **zero results for every query** since migration 21;
* 15 vault tests have been red since migration 36.

The 5,670-test backend suite was green throughout. A suite nobody runs is a
suite that rots, and both defects were the silent kind — HTTP 200, no error, no
log line.

Gate it on a SurrealDB service container. Fix 1.1 first or CI starts red.

### 1.3 Audit the remaining SurrealQL defect classes

Three defect classes were found in `fn::vector_search` this session. Two have
been swept repo-wide; one has not.

| Class | Swept? | Result |
|---|---|---|
| One-arg KNN `<\|K\|>` against an HNSW index | yes | only `fn::vector_search`; fixed in 49 |
| `ORDER BY` on a statement carrying `GROUP BY` | yes | also `fn::text_search`; fixed in 50 |
| Function call in a WHERE that also drives an indexed scan | **no** | not yet swept |

The third is the subtle one: on SurrealDB 2.6.5 a `@@`/KNN predicate combined
with a function-based condition over the same indexed field returns **no rows**,
silently. A plain comparison survives; `array::len(...)` or
`vector::similarity::cosine(...)` does not. Anywhere that shape exists, the
query returns nothing and looks like "no matches".

Guards that already exist and run unconditionally:
`tests/test_v0_8_114_knn_operator_arity.py`,
`tests/test_v0_8_114_search_result_ordering.py`.

---

## 2. Search quality

### 2.1 BM25 collection statistics go stale after a bulk `DELETE`

Reproduced: after `DELETE source;`, every `search::score()` in that namespace
returns exactly `0.0` until the index is rebuilt. `REBUILD INDEX` on the emptied
table restores real scores.

No product impact known — nothing in the app deletes its whole corpus — but it
made an integration test **vacuous** (a list of identical zeros is trivially
"sorted", so an ordering assertion passed without testing anything).
`tests/integration/test_text_search_ordering.py` now rebuilds before seeding and
refuses to assert on all-identical scores.

Worth deciding: should deleting a notebook or a large source trigger a rebuild
of the affected BM25 indexes? Measure first — this may be purely a test concern.

### 2.2 The HNSW indexes are `DIST EUCLIDEAN`; the function ranks by cosine

Pre-existing and deliberately untouched by migration 49, whose job was to make
search return anything at all. For normalized embeddings the two agree on
ordering, so this is likely benign — but nothing verifies the embeddings are
normalized. Changing the index distance forces a rebuild and shifts result
ordering, so treat it as its own change with its own before/after measurement.

### 2.3 `EF` is set equal to `K` (100)

The conservative starting point. Larger `EF` trades latency for recall. Worth
tuning only against a measured recall benchmark, which does not exist yet.

### 2.4 A reranker leg for hybrid search

qmd's third leg, deliberately not implemented in v0.8.113: it would add another
GGUF to the sidecar fleet for a benefit this codebase has not measured. Revisit
only after 1.2 gives a way to measure retrieval quality at all.

---

## 3. Known-wrong small things

### 3.1 `embedded_chunks` is hard-coded to `0` in the sources list view

`api/routers/sources.py:638` — `embedded_chunks=0,  # Not needed in list view`.
The real count is non-zero (16 for the source checked). This cost real debugging
time this session: it made a healthy source look unembedded and sent the
vector-search investigation down a wrong path. Either compute it or drop the
field from the list response.

### 3.2 `source_visuals_enabled()` is not a registered setting

It reads `os.environ` directly instead of going through `resolve_env`, so it
alone ignores the product's legacy-alias normalization. Larger than it looks:
the name is absent from `environment.SETTINGS`, so routing it through
`resolve_env` without registering it makes the flag unreadable (verified — four
tests fail immediately). The fix is to register the setting, which brings alias
handling and deprecation policy with it.

---

## 4. Deferred, with reasons

* **`act()` warnings** — ~100 across three clusters
  (`GuidedTipsProvider`, Radix internals, unawaited async state). Every test
  passes. No shared fix; do them per-cluster while already in the area.
* **Source-shape tests** — 469 assertions across 88 files that grep exact source
  text. Long assumed to block a formatter; measured 2026-08-19 to not.
  Replace opportunistically, not as a project.
* **`pillow < 12`** — ~24 CVEs, accepted: moviepy 2.2.1 (latest) still pins
  `pillow<12.0`. Genuinely unresolvable upstream; re-check when moviepy moves.
* **The two version tracks** — `desktop/__init__.py` (app) and `pyproject.toml`
  (server/container) version different artifacts and are intentionally
  unreconciled. Confusing to every reader; still correct.

---

## Re-running the evidence

```bash
uv run pytest tests/ desktop/tests/ -q                      # 5,670 pass
SURREAL_INTEGRATION=1 uv run pytest tests/integration/ -q   # 17 pre-existing failures
uv run python scripts/rebrand_audit.py --check
make repair-rebrand-pins
make security-scan
cd frontend && npx vitest run
```
