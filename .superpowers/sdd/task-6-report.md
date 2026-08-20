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

## Review repair — eligibility order and receipt bounds

### Red

New planner regressions first failed because benchmark freshness was reported
before a candidate's wrong modality, future timestamps were incorrectly
accepted as fresh, and arbitrary `bounded_unit_id` text was placed unchanged
in escalation receipts.

### Repair

- The eight observable eligibility gates now run exactly as specified:
  readiness, modality, role acceptance, context, structured output, health,
  memory reservation, then execution policy. Freshness/accepted-quality proof
  is evaluated only after those observable gates, so malformed candidates do
  not mask a modality (or any earlier ordered) failure.
- Benchmark age now requires `0 <= now - benchmarked_at <= 30 days`; a future
  timestamp fails closed.
- `bounded_unit_id` is retained only when it is an opaque ASCII identifier of
  at most 128 characters (`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`); malformed,
  path-like, multiline, or overlong values are recorded as `null`.

### Verification

```sh
PYTHONPATH="$PWD" /Users/Antman/Documents/Open\ Notebook/Deeper-Notebook/.venv/bin/pytest -q tests/test_local_model_planner.py
# 24 passed
```

## Final review repair — rejected-reason redaction

### Red

The escalation receipt was constructed before the reason allowlist rejection,
so a malicious invalid reason could be recorded verbatim despite the returned
escalation being blocked.

### Repair and verification

- Valid allowlisted reasons remain receipt-safe enum values.
- Every rejected reason is replaced in the receipt with the static
  `rejected_unrecognized_reason` code; no caller-provided reason text is
  retained. The escalation remains blocked.
- A malicious multiline source/output-looking reason regression first failed,
  then passed with the planner suite (`25 passed`).

## Today productization Task 6 — React-warning and Pillow audit (2026-08-20)

### Scope and warning inventory

- Captured one complete single-worker frontend Vitest run outside the
  repository at `/private/tmp/deeper-notebook-task6-vitest-before.XXXXXX.log`
  (SHA-256
  `17fa879185fbd8c658a062ddea1102e126ae0700ffc380b09a3f3b31ab716075`).
  It found **0 total / 0 unique** React `act()`/unawaited-state warnings and
  therefore no application-owned or Radix-only stack owner to repair. Console
  output was neither filtered nor suppressed.
- The required first owner, `GuidedTipsProvider`, was rerun separately:
  `7 passed`, with no React warning. Because the inventory is empty, there is
  no honest RED/GREEN warning repair to add; the React 19.2 `act` guidance
  remains the standard for any future cluster:
  https://react.dev/reference/react/act.
- The full baseline was not green: `243` files / `1,808` tests ran, with
  `240` files / `1,803` tests passing and five deterministic Task 2
  default-on/runtime follow-ups. They are outside this warning-only scope:
  `AppShell.test.tsx` has two legacy cases that omit
  `NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0`; `use-sources.test.tsx` omits the new
  `useSourceVisualsEnabled` feature mock; and `theme-script.test.ts` retains
  two Research Core-default expectations after the Visual System V2 default
  changed. Task 7 must repair and verify those tests; this task does not claim
  a full frontend green result.

### Pillow/MoviePy decision

- Installed values are MoviePy `2.2.1` and Pillow `11.3.0`. Current official
  PyPI metadata for MoviePy `2.2.1` still declares
  `pillow>=9.2.0,<12.0`, and upstream issue #2553 requesting Pillow 12 support
  remains open. Official sources:
  https://pypi.org/pypi/moviepy/json and
  https://github.com/Zulko/moviepy/issues/2553.
- The GitHub Advisory API reports 18 unwithdrawn advisories whose ranges affect
  Pillow `11.3.0`; first patched releases are `12.1.1`, `12.2.0`, or `12.3.0`.
  MoviePy's upper bound prevents every known fixed release, so no dependency,
  lockfile, or resolver change was made. Source:
  https://api.github.com/advisories?ecosystem=pip&affects=pillow&per_page=100.
