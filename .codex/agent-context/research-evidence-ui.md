# Deeper Notebook Research Evidence UI

## Objective

Add a read-only evidence receipt to the existing Research source approval panel.

## Requirements

- Extend frontend `ResearchCandidate` with optional `ResearchEvidence` matching the backend fields.
- Render provider, freshness, degraded/fallback status, retrieval time, and shortened source/evidence fingerprints with accessible full-value labels.
- Preserve checkbox/button behavior, legacy candidates, no new API calls, no source mutation, and no animations.
- Use existing design-system tokens/components; text must convey status independently of color.

## Files in scope

- `frontend/src/lib/api/research.ts`
- `frontend/src/components/research/EvidenceReceipt.tsx` and test
- `frontend/src/components/research/SourceApprovalPanel.tsx` and test
- supplied design/plan docs

## Verification

- Focused Vitest tests for receipt and approval panel
- Existing frontend unit/lint/type/build gates
- Mocked browser project if collected

Read `/Users/Antman/.codex/context.md` first. Preserve the two existing untracked web/research context files. Append a concise receipt before returning; do not push.

## Durable receipt (2026-08-08)

- Commit `85a51f44` (`feat(ui): show research evidence receipts`) adds the optional `ResearchEvidence` API shape, read-only `EvidenceReceipt`, and sibling composition in `SourceApprovalPanel`; checkbox/button behavior and legacy candidates remain unchanged.
- RED: package-local focused run failed the new receipt assertions/import before implementation. GREEN: focused Vitest 2 files/5 tests; full frontend Vitest 169 files/1,332 tests; ESLint; Next production build; mocked baseline Playwright 1/1; and post-commit diff check passed.
- Standalone `npx tsc --noEmit` still reports inherited ThemeProvider/theme-store/use-knowledge-workspace test diagnostics only. Mocked-browser collection has no direct SourceApprovalPanel/evidence-receipt scenario. Parent reconciliation remains open; no push performed.

## Follow-up browser coverage (2026-08-09)

- Added `frontend/e2e/research-evidence-receipt.spec.ts` with deterministic notebook/research-run API fixtures. It covers the real notebook route, wizard-cookie gate, approval panel, stale/fallback status, retrieval label, and full-value fingerprint titles.
- Made `PLAYWRIGHT_PORT` overrideable in `frontend/playwright.config.ts`; default remains 3117. This avoids reusing a different local worktree's server during browser proof.
- Isolated proof: `PLAYWRIGHT_PORT=3135 npm run test:e2e:mocked -- e2e/research-evidence-receipt.spec.ts` passed 1/1. Frontend lint and changed-file ESLint pass. TypeScript still has the same inherited test-only diagnostics listed above.
