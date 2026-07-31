# Task 6 — Filtered Random Note

## Delivered

- Added canonical `POST /api/deeper-notebook/knowledge/random-note`.
- Uses the existing bounded `RandomNoteFilters` and repository eligibility query,
  returning only safe `KnowledgeOpenDescriptor` fields.
- Selects candidates through an injectable test selector; production defaults to
  `secrets.randbelow` and exposes neither seed nor offset in the request schema.
- Handles the count/read race by recounting once, clamping the original offset,
  then failing closed when a usable projection is still unavailable.
- Returns `200` selected or empty results with `Cache-Control: no-store`.
  Validation/invalid selectors return scrubbed `422`; unavailable projections
  return scrubbed `503`.

## Verification

- Red: focused selector/route tests initially failed because the selector and
  route did not exist.
- Green: `uv run pytest -q tests/test_knowledge_navigation_repository.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py` — 78 passed.
- `uv run ruff check` and `uv run ruff format --check` passed for the Task 6 files.
- Canonical OpenAPI path assertion and `git diff --check` passed.

## Scope

Synthetic in-memory test fixtures only; no external vault or Second Brain data
was read.
