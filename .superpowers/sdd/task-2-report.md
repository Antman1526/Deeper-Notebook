# Task 2 Report: Canonical Deeper Notebook Environment Variables

Date: 2026-07-26
Branch: `codex/deeper-notebook-implementation`

## Outcome

Implemented one product-owned environment resolver with deterministic precedence:

`DEEPER_NOTEBOOK_*` > `DN_*` > `OPEN_NOTEBOOK_*` > `ONP_*`

Long-form settings that historically had only `OPEN_NOTEBOOK_*` aliases retain
that two-name compatibility surface. Empty strings count as assigned values.
Resolution receipts and deprecation warnings contain key names only, never
values.

## Implementation

- Added `deeper_notebook/environment.py` with:
  - one registry for all supported product-owned settings;
  - canonical resolution, including compatibility for callers that still pass
    a registered legacy identifier;
  - file-aware getter support for `*_FILE` secrets;
  - canonical/legacy child-process mirroring;
  - once-per-legacy-key warnings without values;
  - receipts containing only canonical name, winning key, and legacy status.
- Routed active Python runtime reads in `api/`, `commands/`, `desktop/`, and
  `open_notebook/` through `resolve_env()`.
- Invoked normalization before API runtime imports and surreal-command module
  imports.
- Built desktop child environments from canonical keys and normalized mirrors.
- Canonicalized `launcher.env` writes while retaining all required legacy
  whitelist entries.
- Updated the environment example and reference documentation with canonical
  names first and legacy aliases marked deprecated.
- Preserved the Gmail callback at `/api/onp/gmail/callback`.
- Preserved an existing Gmail refresh token when Google omits a replacement on
  repeat consent.
- Preserved Surreal namespace/database `open_notebook`; command identifiers and
  installer identifiers were not changed.
- Added an AST guard that rejects new direct legacy product-key reads in
  production Python.

## TDD Evidence

Initial RED command:

```text
uv run pytest tests/test_environment_aliases.py -q
```

Result:

```text
ERROR tests/test_environment_aliases.py
ModuleNotFoundError: No module named 'deeper_notebook.environment'
1 error in 0.11s
```

Required focused GREEN command:

```text
uv run pytest tests/test_environment_aliases.py desktop/tests/test_launcher_prefs.py tests/test_credentials_api.py tests/test_db_pool.py -q
```

Result:

```text
43 passed, 12 warnings in 14.04s
```

Required Ruff command:

```text
uv run ruff check deeper_notebook/environment.py tests/test_environment_aliases.py
```

Result:

```text
All checks passed!
```

Additional Gmail continuity test:

```text
uv run pytest tests/test_gmail_router.py -q
7 passed, 9 warnings in 1.19s
```

Fresh full backend suite:

```text
uv run pytest tests -q
2288 passed, 16 skipped, 89 warnings in 54.26s
```

`git diff --check` also passed.

## Full-Suite Regression Triage

The first full-suite pass exposed 21 failures. They were grouped and handled by
root cause rather than patched individually:

1. Helper compatibility: existing helper tests passed legacy key identifiers
   into the new resolver. The resolver now maps any registered alias back to its
   canonical owner while preserving canonical precedence and receipts.
2. Stale source-contract tests: several tests asserted literal direct legacy
   reads or legacy `launcher.env` writeback. They now assert canonical resolver
   calls and canonical writeback.
3. Warning test order: once-per-process warning deduplication was correct, but
   warning-specific tests needed isolated reset state.
4. Environment refresh ordering: normalizing the entire process environment
   allowed an old canonical mirror to outrank a newly submitted legacy update.
   The endpoint now normalizes the accepted request patch independently, so the
   new request wins and all aliases receive the new value.

After focused `--last-failed` reruns, the final fresh full suite passed.

## Self-Review and Concerns

- No secret values are included in receipts or warnings.
- The full suite intentionally reports legacy-key deprecation warnings where
  existing tests exercise compatibility aliases. Those warnings contain key
  names only.
- Existing third-party deprecation warnings and the pre-existing
  `desktop/paths.py` invalid-escape `SyntaxWarning` remain outside this task.
- The environment migration touches many runtime modules mechanically because
  the guard requires every active product-owned legacy read to use the central
  resolver.
