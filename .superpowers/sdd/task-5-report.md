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
