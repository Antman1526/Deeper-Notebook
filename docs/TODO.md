# TODO

**Status: 2026-08-21 · desktop `0.8.114` (source) · server/container `1.8.5`**

Concrete, actionable work items. Strategy and rationale live in
[`ROADMAP.md`](ROADMAP.md); this file is the list you can pick from.

Every claim below is measured. Where a number appears, the command that
produced it is named so it can be re-run rather than trusted.

---

## 0. Blocked on you — I cannot do these

### 0.1 Revoke the leaked Google API key — **externally verified invalid**

The historical live-format key was tested without printing or persisting its
value. Google returned `API_KEY_INVALID`, so it is not currently usable. The
authenticated local Google account still lacks `apikeys.keys.lookup`, which
means this repository cannot prove whether the key was deleted, restricted, or
revoked in its owning Cloud project. The remaining owner action is to confirm
that state in Google Cloud Console and rotate any consumer that still refers to
the old identifier. History cleanup does not substitute for that confirmation.

### 0.2 Purge the key and `history.txt` from git history — **partially complete**

A full-ref backup bundle was created, permissioned `0600`, independently
verified, and restore-tested before rewriting. The sanitized mirror contains
neither the target key nor `history.txt`, and eight affected writable remote
branch heads were updated with exact force-with-lease protection. The remote
branch heads now match the sanitized authority.

Nine GitHub-generated pull-request refs remain outside normal Git push
authority (merged PR heads 1–6 and 9; open PR merge refs 7–8). GitHub Support
must dereference or purge those cached refs before this can truthfully be
called a complete remote-history purge. The recoverable backup is
`/Users/Antman/Downloads/deeper-notebook-origin-full-refs-20260820T174527Z.bundle`
with SHA-256
`69564a46f08452675d70d5b2e56ecd77b6fa12edd4e2e8ea01305e74741effd7`.

### 0.3 Packaged v0.8.114 build — final staged and installed local proof recorded

The final authorized local package was built from source authority `d5925e20`
and verified with the release-smoke runner through `cbf03876`. The arm64 app,
bundled runtime, and DMG are byte-identified as follows:

- app executable SHA-256 (staged and installed): `1d48e549250d9359fe05e81487d95a9900b1fe26a4f01cec9ce700e4a9808bb6`
- bundled Surreal runtime SHA-256 (staged and installed): `0afb5d9f0eb8902b5d0e9633c15898ddd2d3f8a259904174c9bc9e1ec1df5002`
- DMG SHA-256: `4ece62e4a315a309167313b00ecd411a30e990bb4c153ba1fe99b6b5eb8279e1`
- current pre-install backup: `/Applications/Deeper Notebook.app.backup-20260821T201559Z`
- earlier Task 8 backup: `/Applications/Deeper Notebook.app.backup-20260821T085744Z`
- pre-final staged artifacts: `/Users/Antman/Downloads/Deeper-Notebook-dist-pre-final-20260821T190049Z`

Final staged receipts are preserved under
`/private/tmp/deeper-notebook-final-staged-20260821T201559Z/`; final installed
receipts are preserved under
`/private/tmp/deeper-notebook-final-installed-20260821T201559Z/`. Both
`summary.json` files passed. Their `default.json` receipts prove the Gemini
Forward Light/V2 shell and all six runtime features enabled. Their
`source-visuals-off.json` receipts prove the usable Sources surface with only
`sourceVisuals=false`. Both modes used GET-only loopback traffic, emitted no
source-visual mutation, and shut down cleanly.

The earlier Task 8 receipts remain preserved under
`/private/tmp/deeper-notebook-task8-20260821T082218Z/` as historical proof:

- `staged-corrected-default.json` and `staged-corrected-off.json` passed
  package startup, readiness, runtime-feature, and clean-shutdown checks.
- `installed-corrected-default.json` and `installed-corrected-off.json` passed
  the same checks against `/Applications/Deeper Notebook.app`; the installed
  executable equals the staged executable hash above.
- `installed-browser-default-allowlist.json` passed the default Gemini
  Forward workspace and all six enabled features with GET-only loopback
  traffic.
- `installed-browser-off-fresh.json` passed the usable Sources surface,
  `sourceVisuals=false`, GET-only traffic, and zero source-visual mutation.

The original failed `staged-default.json` and three failed final staged-smoke
roots remain retained as diagnostic evidence; none supersedes the passing
roots above. No receipt or Task 8 log was deleted. The package uses the stable
local `Deeper Notebook Local` signing identity, not an Apple Developer ID, so
notarization, Gatekeeper clean-machine proof, and updater/public-distribution
proof remain open. Windows packaging remains open. Credential-owner action and
GitHub Support's cached pull-request-ref purge remain open; no credentials were
entered. Push, publication, and remote-history changes remain separate
owner-authorized gates and were not performed.

---

## 1. Correctness — found 2026-08-20

### 1.1 Stabilize the real-Surreal integration suite — **complete 2026-08-20**

The migration-rewind fixture now captures the live migration head, uses the
canonical runner for every rewind, and restores the original schema/head after
each test. The current real-Surreal suite is green, including a regression that
seeds normalized 768-dimensional memory vectors and proves semantic recall
returns facts, preferences, and episodes through the HNSW indexes.

### 1.2 Keep the integration suite in CI — **implemented**

`test.yml` runs `tests/integration/` with `SURREAL_INTEGRATION=1` against the
pinned `surrealdb/surrealdb:v2.6.5` container. The local gate remains opt-in to
avoid accidental database connections; run it explicitly with:

```bash
SURREAL_INTEGRATION=1 uv run pytest tests/integration/ -q
```

### 1.3 Audit the remaining SurrealQL defect classes — **complete 2026-08-20**

Three defect classes were found in `fn::vector_search` this session. All three
have now been swept across the current production authority.

| Class | Swept? | Result |
|---|---|---|
| One-arg KNN `<\|K\|>` against an HNSW index | yes | `fn::vector_search` and Python memory recall use `<\|K,EF\|>`; static + real-Surreal guards cover both |
| `ORDER BY` on a statement carrying `GROUP BY` | yes | also `fn::text_search`; fixed in 50 |
| Function call in a WHERE that also drives an indexed scan | yes | current/effective `fn::vector_search` (49), `fn::text_search` (50), and all tracked production Python query sites are clean |

The third is the subtle one: on SurrealDB 2.6.5 a `@@`/KNN predicate combined
with a function-based condition over the same indexed field returns **no rows**,
silently. A plain comparison survives; `array::len(...)` or
`vector::similarity::cosine(...)` does not. Anywhere that shape exists, the
query returns nothing and looks like "no matches".

The final audit used the migrations a fresh database actually applies, not
superseded forward definitions or down migrations. Migration 49 has three
inner HNSW predicates with only `embedding <|100,100|> $query`; its
`array::len(...)` and cosine filters are in outer non-KNN queries. Migration 50
has six `@1@` full-text predicates with no function call in their `WHERE`
clauses. Across all 425 tracked production Python modules, the only direct
indexed predicates are the three bare HNSW queries in
`deeper_notebook/utils/memory_recall.py`; `deeper_notebook/domain/notebook.py`
only invokes the two database functions. No current indexed KNN or full-text
predicate shares its `WHERE` clause with a function call.

Guards that already exist and run unconditionally:
`tests/test_v0_8_114_knn_operator_arity.py`,
`tests/test_v0_8_114_search_result_ordering.py`.

---

## 2. Search quality

### 2.1 Source deletion refreshes its affected BM25 indexes

**Implemented and measured (2026-08-20).** A realistic product
`Source.delete()` with one retired source, two surviving sources, and source
chunks left survivors in the same meaningful, non-tied retrieval order as two
subsequent comparison rebuilds. `Source.delete()` now performs exactly one
best-effort rebuild pass over the fixed internal whitelist:
`source.idx_source_title`, `source.idx_source_full_text`,
`source_embedding.idx_source_embed_chunk`, and
`source_insight.idx_source_insight`. It does not rebuild note indexes and never
interpolates user input. A failed delete performs no rebuild; a rebuild failure
is logged with its table/index and returns the completed delete, with search
relevance explicitly degraded until the next successful rebuild.

Each source-delete attempt first writes the fixed
source-search rebuild-pending record with a fresh opaque token; if that write
cannot be confirmed, deletion aborts before any file or database
mutation. The coalesced coordinator clears the marker only through an exact
token compare-and-set after a successful fixed-index pass. API startup waits
for any persisted marker before serving, while clean shutdown drains for at
most five seconds before closing the pool. A timeout, cancellation, or forced
kill leaves the marker and logs degraded search for next-startup reconciliation;
this is a clean-shutdown guarantee, not a claim that an unclean process kill
finishes maintenance.

SurrealDB 2.6.5 changes raw BM25 score magnitudes on repeated identical
`REBUILD INDEX` passes (the deterministic fixture progressed from
`[1.9793, 0.8760]` after the delete pass to `[2.2471, 0.9935]` and
`[2.4984, 1.1035]`), while the survivor identity/order stayed stable. Hybrid
fusion consumes rank, so the regression protects non-vacuous scores and
identity/order, not unsupported magnitude idempotence. Evidence:
`SURREAL_INTEGRATION=1 uv run pytest -q -s tests/integration/test_search_quality_benchmark.py`
(two fresh namespaces, now 6 passed each including the marker/CAS contract).

### 2.2 HNSW candidates now use the final cosine metric

**Implemented and migration-tested (2026-08-20).** A deterministic
real-Surreal 768-dimensional fixture with a non-unit exact cosine winner and
101 Euclidean-nearer decoys made the old candidate pool return an incorrect
identity (`euclidean candidate 000`) instead of `cosine winner`. The provider
stub measurement confirms that short and batch source-relevant embedding paths
forward raw norms (`5.0`; `[5.0, 10.0]`), so existing data cannot be declared
unit-normalized. No provider outputs were normalized and no data was
re-embedded.

Migration 51 drops/redefines `source_embedding_hnsw`, `source_insight_hnsw`,
and `note_hnsw` as `DIST COSINE`; rollback restores their exact
`DIST EUCLIDEAN` definitions. Drop/redefine is the required definition rebuild;
`REBUILD INDEX` alone would preserve the wrong metric. Real up/down/up proof
and static contracts pass in disposable SurrealDB 2.6.5 namespaces.

### 2.3 Keep the shipped `EF=100` authority

**Measured; no tuning.** Fixed exact-cosine recall@10 was `1.000` for all
three queries over 128 vectors in both fresh runs. Median query latency was
`8.552 ms` then `9.170 ms` for EF 100; the read-only EF 200 comparator was
also `1.000` recall with `9.188 ms` then `10.053 ms` median latency. There is
no safe parameterized production setting and no measured recall gain, so EF
100 remains unchanged.

### 2.4 Reranker evaluation is blocked by absent authorized capability

Repository inventory finds two retrieval legs fused by rank in
`deeper_notebook/search/fusion.py`; it explicitly says the LLM reranker is not
implemented. There is no configured local reranker model, cross-encoder, or
reranker invocation path. No model was downloaded or invoked. The new fixture
has deterministic retrieval judgments, but it cannot measure a reranker delta
until a separately authorized local reranker is configured.

---

## 3. Known-wrong small things

### 3.1 Source-list embedding metadata — **complete 2026-08-20**

Both source-list query branches now project the authoritative related
`source_embedding` count as `embedded_chunks`; `embedded` is derived from
`embedded_chunks > 0`. Focused tests cover notebook-filtered and all-source
queries, nonzero and missing counts, and prove the implementation does not add
a per-row `Source.get_embedded_chunks()` call.

### 3.2 Source-visual feature registration — **complete 2026-08-20**

`SOURCE_VISUALS_ENABLED` is registered in the canonical environment registry,
and `source_visuals_enabled()` now uses the normal alias/deprecation resolver.
Visual System V2 and Source Visuals default on, while canonical and legacy
explicit-off values remain authoritative. Mounted frontend consumers subscribe
to runtime feature changes, so a delayed backend rollback removes queries and
controls without a reload; malformed or partial authority payloads cannot
silently re-enable a disabled feature.

---

## 4. Deferred, with reasons

* **Automatic source summary and key topics remain opt-in** — Task 4 review on
  2026-08-20 kept both defaults false. The focused parser/default tests pass,
  but no focused test proves ingestion remains nonblocking under a missing
  model, offline/provider failure, or timeout; no browser settings spec covers
  either control. `process_source_command` only isolates setup of the optional
  transformations, while their execution remains on the ingest path. Do not
  default-enable either setting or introduce implicit LLM work until those
  failure paths and the per-source cost boundary are proven.
* **Source-shape tests** — 469 assertions across 88 files that grep exact source
  text. Long assumed to block a formatter; measured 2026-08-19 to not.
  Replace opportunistically, not as a project.
* **`pillow < 12`** — the installed MoviePy 2.2.1 and official current PyPI
  metadata still require `pillow>=9.2.0,<12.0`, while the official Pillow-12
  support issue remains open. GitHub's advisory API reports 18 unwithdrawn
  advisories affecting installed Pillow 11.3.0; their first patched releases
  are 12.1.1, 12.2.0, or 12.3.0. No resolver override or dependency update is
  safe. Re-check only after an official compatible MoviePy release exists:
  https://pypi.org/pypi/moviepy/json,
  https://github.com/Zulko/moviepy/issues/2553, and
  https://api.github.com/advisories?ecosystem=pip&affects=pillow&per_page=100.
* **The two version tracks** — `desktop/__init__.py` (app) and `pyproject.toml`
  (server/container) version different artifacts and are intentionally
  unreconciled. Confusing to every reader; still correct.

---

## Re-running the evidence

```bash
uv run pytest tests/ desktop/tests/ -q                      # 5,672 pass
SURREAL_INTEGRATION=1 uv run pytest tests/integration/ -q   # 126 passed, 10 warnings (2026-08-20)
uv run python scripts/rebrand_audit.py --check
make repair-rebrand-pins
make security-scan
cd frontend && npx vitest run
```
