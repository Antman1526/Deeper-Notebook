# Deeper Notebook Research Evidence UI

## Goal

Make the Research Run approval screen show the provenance and freshness of each discovered web candidate before the user approves it.

## Scope

- Extend the existing frontend ResearchCandidate type with the additive `evidence` object already returned by the API.
- Render a compact, accessible evidence receipt inside each pending candidate row: provider, freshness, fallback/degraded state, retrieval time, and shortened source/evidence fingerprints.
- Keep the existing approval checkboxes and button semantics unchanged.
- Keep evidence read-only; no links are auto-fetched, no new API calls are introduced, and no source is imported by viewing the receipt.
- Handle legacy candidates with `evidence: null` or a missing field without layout gaps or errors.

## Visual/interaction direction

Use the existing border, muted surface, Badge, and typography tokens. Freshness must include text, not color alone. Fingerprints use a readable monospace truncation and an accessible label/title with the full value. The receipt is always visible for evidence-bearing candidates, with no animation or hover-only information.

## Verification

Component tests cover evidence-bearing and legacy candidates, degraded/fresh/stale labels, fingerprint visibility, checkbox approval behavior, and accessible labels. Run the focused component tests, frontend type/lint/build gates, and the existing mocked browser suite if the changed component is collected by it.
