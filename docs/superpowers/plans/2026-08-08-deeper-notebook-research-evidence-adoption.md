# Deeper Notebook Research Evidence Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach provider-aware immutable web evidence to approval-first Research Run candidates while preserving all existing raw search and source-approval behavior.

**Architecture:** Extract the current provider failover loop into one internal result runner that can return raw results plus the actual provider and fallback status. Keep `run_web_search()` as a compatibility wrapper and add `run_web_search_with_evidence()` on top of that same runner. Research discovery consumes the evidence tuple, stores it as an optional frozen `WebEvidence` field on each candidate, and exposes that field additively in the API.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, pytest/pytest-asyncio, existing httpx provider adapter.

## Global Constraints

- No second provider/network implementation; the existing failover loop remains the only network path.
- `run_web_search()` return shape and chat/citation behavior remain unchanged.
- Evidence never authorizes imports or bypasses `normalize_outbound_url`/`validate_outbound_url`.
- No vault writes, watcher changes, credential logging, frontend changes, or remote push.
- New API fields are optional and backward-compatible.

### Task 1: Define failing provider-metadata and research-evidence tests

**Files:**
- Modify: `tests/test_v0_8_64_web_search.py`
- Modify: `tests/test_research_api.py`
- Create: `tests/test_research_discovery.py`

- [x] **Step 1: Add RED tests**

Cover these outcomes:

```python
@pytest.mark.asyncio
async def test_evidence_reports_provider_that_won_failover(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "serper")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily")
    # fake Serper raises; fake Tavily returns one result
    evidence = await ws.run_web_search_with_evidence("q")
    assert evidence[0].provider == "tavily"
    assert evidence[0].degraded is True


@pytest.mark.asyncio
async def test_raw_web_search_wrapper_preserves_legacy_shape(monkeypatch):
    result = await ws.run_web_search("q")
    assert result == [{"title": "T", "url": "https://example.com", "snippet": "S"}]


def test_research_candidate_keeps_optional_evidence():
    evidence = normalize_web_results(
        [{"title": "T", "url": "https://example.com/source", "snippet": "S"}],
        query="q",
        provider="tavily",
    )[0]
    candidate = normalize_candidates([evidence])[0]
    assert candidate.evidence == evidence
    assert (
        ResearchRun.model_validate(
            ResearchRun(objective="q", candidates=[candidate]).model_dump()
        )
        .candidates[0]
        .evidence
        == evidence
    )
```

Also extend the Research API fixture assertion to require an additive `evidence` object containing the actual provider, `source_fingerprint`, `evidence_id`, freshness, and degraded state. Add a regression proving a candidate with evidence still requires the existing approval URL validation.

- [x] **Step 2: Run the new focused tests to confirm RED**

Run: `uv run pytest -q tests/test_research_discovery.py tests/test_v0_8_64_web_search.py::test_evidence_reports_provider_that_won_failover tests/test_research_api.py::test_create_discovers_normalized_candidates_then_pauses`

Expected: collection or assertions fail because the metadata runner, optional candidate evidence, and API field do not exist.

### Task 2: Add one provider-aware runner and evidence wrapper

**Files:**
- Modify: `deeper_notebook/tools/web_search.py`
- Modify: `tests/test_v0_8_64_web_search.py`

- [x] **Step 1: Extract the existing failover loop without changing behavior**

Implement an internal async runner returning `(results, provider, degraded)`. Preserve the existing offline short-circuit, timeout budget, provider order, logging, empty-result rules, and no-raise behavior. Mark `degraded` true only when a later chain attempt returns results.

- [x] **Step 2: Keep the legacy wrapper and add evidence**

```python
async def run_web_search(query: str, *, max_results: int | None = None) -> list[dict]:
    results, _provider, _degraded = await _run_web_search_result(...)
    return results


async def run_web_search_with_evidence(
    query: str, *, max_results: int | None = None
) -> tuple[WebEvidence, ...]:
    results, provider, degraded = await _run_web_search_result(...)
    if not results or provider is None:
        return ()
    return normalize_web_results(
        results,
        query=query,
        provider=provider,
        max_results=max_results,
        degraded=degraded,
    )
```

- [x] **Step 3: Run web-search tests**

Run: `uv run pytest -q tests/test_v0_8_64_web_search.py tests/test_web_evidence.py`

Expected: all existing and new web tests pass, including raw-shape compatibility and failover metadata.

### Task 3: Persist evidence on Research candidates and expose it additively

**Files:**
- Modify: `deeper_notebook/research/state.py`
- Modify: `deeper_notebook/research/discovery.py`
- Modify: `api/schemas/research.py`
- Modify: `api/routers/research.py`
- Modify: `tests/test_research_discovery.py`
- Modify: `tests/test_research_api.py`

- [x] **Step 1: Add the optional state/API fields**

Add `evidence: WebEvidence | None = None` to `ResearchCandidate` and `ResearchCandidateResponse`. Legacy candidates serialize with `evidence: null`; no required field changes.

- [x] **Step 2: Make discovery consume evidence while retaining raw normalization**

Use `run_web_search_with_evidence()` in the Research discovery stage. `normalize_candidates()` accepts either `WebEvidence` or legacy mappings. For evidence entries, validate/canonicalize the URL with the existing outbound policy, preserve the evidence only when the candidate remains valid, and never use evidence as approval. Keep candidate IDs URL-derived and deduplicate by canonical URL.

- [x] **Step 3: Run research tests**

Run: `uv run pytest -q tests/test_research_discovery.py tests/test_research_api.py tests/test_research_graph.py tests/integration/test_research_repository.py`

Expected: focused tests pass; the integration repository test remains skipped unless a native SurrealDB runtime is available.

### Task 4: Review and commit

**Files:**
- Modify: this plan only to check completed steps

- [x] **Step 1: Run compatibility and style gates**

Run: `uv run pytest -q tests/test_v0_8_64_web_search.py tests/test_web_evidence.py tests/test_research_api.py tests/test_research_graph.py tests/test_search_api.py tests/test_research_discovery.py`, `uv run ruff check deeper_notebook/tools/web_search.py deeper_notebook/tools/web_evidence.py deeper_notebook/research/state.py deeper_notebook/research/discovery.py api/schemas/research.py api/routers/research.py tests/test_v0_8_64_web_search.py tests/test_web_evidence.py tests/test_research_discovery.py tests/test_research_api.py`, and `git diff --check`.

- [x] **Step 2: Inspect scope and persistence shape**

Confirm no provider keys, vault paths, fetch/approval policy removals, frontend files, or unrelated generated files changed; confirm `ResearchRun.model_dump(mode="json")` round-trips nested evidence.

- [x] **Step 3: Commit**

```bash
git add deeper_notebook/tools/web_search.py deeper_notebook/tools/web_evidence.py deeper_notebook/research/state.py deeper_notebook/research/discovery.py api/schemas/research.py api/routers/research.py tests/test_v0_8_64_web_search.py tests/test_web_evidence.py tests/test_research_discovery.py tests/test_research_api.py docs/superpowers/specs/2026-08-08-deeper-notebook-research-evidence-adoption-design.md docs/superpowers/plans/2026-08-08-deeper-notebook-research-evidence-adoption.md
git commit -m "feat(research): persist web evidence receipts"
```
