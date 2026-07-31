# Task 5 — Revisioned Named Workspace Snapshots and Restore Plans

## Outcome

Implemented revision-aware named workspace service/API support and a
non-mutating restore plan. Named snapshots remain separate from the file-backed
version-1 Current Session autosave.

## Red/green evidence

- **RED 1:**
  `uv run pytest -q tests/test_knowledge_navigation_service.py::test_restore_plan_hydrates_every_target_without_mutating_current_session tests/test_knowledge_workspace_persistence.py::test_pre_navigation_current_session_loads_with_version_one_defaults tests/test_knowledge_workspace_persistence.py::test_split_first_size_defaults_without_storing_a_second_panel_size`
  produced three expected failures: no `workspace_restore_plan`, no Current
  Session `navigation`, and no split `first_size`.
- **GREEN 1:** the same three tests passed after the minimal contract and
  restore-plan implementation.
- **RED 2:** workspace OpenAPI/list/restore tests failed as expected because
  the canonical workspace routes did not yet exist (missing paths and 404s).
- **GREEN 2:** those API tests passed after schemas, route handlers, and the
  scrubbed restore-revision-conflict mapping were added.
- **Focused suite:**
  `uv run pytest -q tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_workspace_api.py tests/test_knowledge_workspace_persistence.py`
  — **75 passed**.
- **Quality checks:** `uv run ruff check ...`, `uv run ruff format --check ...`,
  and `git diff --check` passed. The API suite includes the canonical OpenAPI
  path audit.

## Implemented surface

- Version-1-compatible Current Session navigation defaults, stable optional
  document/graph tab context, and single stored split percentage.
- Named-workspace CRUD service delegation. Snapshot replacements are validated,
  name changes are limited to names, and duplicate/delete delegate to the
  revisioned metadata repository.
- `workspace_restore_plan(workspace_id, revision)` verifies the exact current
  revision, hydrates every target in pane/tab order, returns safe descriptors,
  counts all four target states, and does not import or call Current Session
  persistence.
- Canonical `/workspaces` routes. List responses contain summaries only; get
  and restore responses contain bounded contracts. Restore accepts only a
  revision and its mismatch returns the exact scrubbed 409 envelope.

## Files

- `deeper_notebook/knowledge_engine/navigation_service.py`
- `api/schemas/knowledge_navigation.py`
- `api/routers/knowledge_navigation.py`
- `deeper_notebook/workspace/contracts.py`
- `tests/test_knowledge_navigation_service.py`
- `tests/test_knowledge_navigation_api.py`
- `tests/test_knowledge_workspace_api.py`
- `tests/test_knowledge_workspace_persistence.py`

## Commit and concerns

- Implementation commit: `e5782335 feat: add named knowledge workspace snapshots`
- No task failures or blockers remain. The focused suite emits existing
  third-party deprecation warnings from Surreal/LangGraph/SWIG during the
  main-app OpenAPI audit; they do not affect the assertions.
