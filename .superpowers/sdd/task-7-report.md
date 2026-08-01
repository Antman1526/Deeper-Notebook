# Phase 1 Task 7 report

## Scope

- Added owner-only, atomic, secret-free local-model settings persistence with
  explicit readable-directory validation and restart restoration.
- Extended the desktop config with backwards-compatible strict-local,
  balanced defaults for execution policy, compute profile, memory limit, role
  overrides, and trusted external roots.
- Added redacted `GET`/`PUT` settings endpoints and a pure route-plan endpoint.
  API responses never serialize SurrealDB credentials or the encryption key.
- Exported the selected model directory and execution facts to launcher child
  environments. The resource governor records reservations, permits one MLX
  heavyweight, queues incompatible swaps, and terminates a partially started
  provider if its injected health check fails.
- Strict Local route planning consumes redacted injected candidates only. Its
  transport recorder regression proves no non-loopback request is issued.

## TDD evidence

The initial focused red command failed at collection because
`desktop.launcher.ResourceGovernor` did not exist. The owner-only settings
tests also initially could not import the absent settings module. After the
minimal implementation, focused tests passed.

## Final verification

```sh
uv run --no-sync pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py
# 69 passed; one existing FastAPI/TestClient deprecation warning

uv run --no-sync ruff check deeper_notebook/local_models/settings.py desktop/config.py desktop/launcher.py api/routers/local_models.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py
# all checks passed

git diff --check
# passed
```

## Boundaries

- No provider, model library, model source root, manifest, or external brain
  was mounted, scanned, or mutated.
- The pre-existing worktree-local `node_modules/` remains untracked and is not
  part of this task's commit.
