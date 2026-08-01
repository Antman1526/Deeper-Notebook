# Phase 1 Task 6 report

## Scope

- Added a pure smallest-capable local route planner and redacted planning
  contracts. It performs no discovery, runtime, provider, transport, or model
  library operation.
- Added the approved eleven-role planner coverage, measured resource tiers,
  deterministic profile selection, override precedence, fresh-benchmark gate,
  memory reservation, and fail-closed local execution policy.
- Added capped higher-tier escalation receipts. Receipts retain only the
  first-pass identifier, fingerprint, measurements, declared reason, and
  bounded unit ID; they omit paths, source, prompt, and output content.
- Extended quality tasks to every approved role. Speech tasks use bounded
  capability/identity probes with an empty language prompt.
- Recorded benchmark peak memory, stable local fingerprint, completion time,
  and an explicit quality-bearing freshness acceptance check. Legacy
  speed-only history remains readable but cannot be accepted for a route.
- Kept the legacy heuristic role recommendations as read-only inventory
  guidance and added a separate adapter for the measured planner.

## TDD evidence

Red checks observed before their implementations:

```sh
PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_planner.py
# collection failed: LocalModelRouteCandidate was absent

PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_quality_tasks.py
# failed: QualityTask had no probe_kind for bounded speech probes

PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_role_routing.py
# failed: plan_local_model_route adapter was absent

PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_benchmarks.py
# collection failed: benchmark_is_accepted was absent
```

An additional benchmark red assertion verified that successful jobs did not
yet record a model fingerprint before the fingerprint field was wired.

## Final verification

```sh
PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_planner.py tests/test_local_model_quality_tasks.py tests/test_local_model_benchmarks.py tests/test_local_model_role_routing.py
# 46 passed; one existing FastAPI/TestClient deprecation warning

.venv/bin/ruff check --select F401 deeper_notebook/local_models/planner.py deeper_notebook/local_models/contracts.py deeper_notebook/local_models/role_routing.py deeper_notebook/local_models/quality_tasks.py deeper_notebook/local_models/benchmarks.py tests/test_local_model_planner.py tests/test_local_model_quality_tasks.py tests/test_local_model_benchmarks.py tests/test_local_model_role_routing.py
# all checks passed

git diff --check
# passed
```

## Boundaries and concerns

- No provider was contacted and no model directory, manifest, inventory, or
  source material was mutated by the planner tests or planner implementation.
- The pre-existing worktree-local `node_modules/` remains untracked and is not
  part of this task's commit.
