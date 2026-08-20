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
