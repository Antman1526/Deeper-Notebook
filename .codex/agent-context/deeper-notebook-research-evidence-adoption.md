# Deeper Notebook Research Evidence Adoption

## Objective

Add provider-aware immutable web evidence to approval-first Research Run candidates while preserving the existing raw search/citation contract.

## Required behavior

- Refactor the existing provider failover loop once; do not add a second network implementation.
- Keep `run_web_search()` returning the existing raw list and keep chat/citation behavior unchanged.
- Add `run_web_search_with_evidence()` returning `tuple[WebEvidence, ...]` with the actual winning provider and `degraded=True` when fallback was required.
- Add optional `evidence: WebEvidence | None` to `ResearchCandidate` and `ResearchCandidateResponse`.
- Research discovery consumes evidence, but outbound URL validation and explicit approval remain mandatory and unchanged.
- Invalid records are skipped; no vault writes, watcher changes, frontend work, credentials, or remote push.

## Files in scope

- `deeper_notebook/tools/web_search.py`
- `deeper_notebook/tools/web_evidence.py`
- `deeper_notebook/research/state.py`
- `deeper_notebook/research/discovery.py`
- `api/schemas/research.py`
- `api/routers/research.py`
- focused tests and supplied design/plan docs

## Verification

- `uv run pytest -q tests/test_v0_8_64_web_search.py tests/test_web_evidence.py tests/test_research_api.py tests/test_research_graph.py tests/test_search_api.py tests/test_research_discovery.py`
- scoped Ruff over changed Python files
- `git diff --check`

## Coordination

Read `/Users/Antman/.codex/context.md` first. Preserve the existing untracked foundation context file and unrelated user work. Append a concise durable receipt to `/Users/Antman/.codex/context.md` before returning.

## Worker milestones

- RED complete: added failover-provider metadata, raw-wrapper compatibility,
  evidence-aware candidate/JSON round-trip, discovery URL filtering, additive
  API serialization, and approval URL-policy regression tests. The exact RED
  command failed 4 tests as expected because the metadata runner, evidence
  candidate field, and discovery wrapper did not yet exist.

- GREEN complete: the existing failover loop now returns raw results plus the
  actual provider and fallback state; `run_web_search()` remains raw and
  `run_web_search_with_evidence()` normalizes immutable receipts. Research
  candidates/API responses carry optional evidence, discovery accepts legacy
  mappings and evidence records, and drops a receipt if outbound URL
  canonicalization would make its URL/fingerprints inconsistent.

- Verification before commit: focused/regression suites pass 74 tests with 3
  native SurrealDB integration skips; scoped Ruff and `git diff --check` pass;
  nested `ResearchRun.model_dump(mode="json")` evidence round-trip passes.
