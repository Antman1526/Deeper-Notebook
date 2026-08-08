# Deeper Notebook Research Evidence Adoption

## Goal

Carry the normalized web evidence contract into approval-first Research Runs so every discovered candidate can retain provenance and freshness before a user approves or rejects it.

## Scope

- Preserve `run_web_search()` as a backward-compatible raw `{title, url, snippet}` API.
- Refactor its existing failover loop behind an additive metadata path that records the provider that actually returned results and whether failover was used.
- Add `run_web_search_with_evidence()` that returns frozen `WebEvidence` records using the existing provider loop and normalizer; it creates no second network path.
- Persist an optional evidence receipt on `ResearchCandidate` and expose it additively in the Research Run API response.
- Keep approval, outbound URL validation, ingestion, vault writes, and source fetching exactly as they are. Evidence is a read-only search receipt, not authorization.
- Keep raw discovery normalization compatible for internal callers and malformed provider data.

## Data flow

`run_web_search_with_evidence()` → `ResearchCandidate.evidence` → persisted Research Run checkpoint → `ResearchCandidateResponse.evidence`.

The provider value is the actual provider attempt that returned the result (`serper`, `tavily`, or `searxng`). `degraded=true` means a later failover attempt supplied the result. The candidate URL remains subject to the existing outbound policy both at discovery normalization and immediately before approval/fetch.

## Compatibility and safety

The existing `run_web_search()` wrapper still returns only its legacy list, so chat, citation captures, and the Discover Sources endpoint do not change. The new Research API field is optional and absent for legacy or manually-created candidates. Pydantic extra-field rejection and frozen `WebEvidence` records prevent persisted evidence from being silently rewritten. No evidence field grants approval or bypasses the outbound URL policy.

If outbound URL policy canonicalization changes a discovered URL after evidence normalization (for example, adding the root slash), discovery drops that receipt instead of attaching hashes bound to a different candidate URL. The candidate remains approval-gated and can still be represented without evidence.

## Verification

Focused tests cover actual-provider metadata on failover, raw wrapper compatibility, research candidate persistence/API serialization, malformed result rejection, and approval remaining independent from evidence. Existing web-search, research, and repository tests must remain green.
