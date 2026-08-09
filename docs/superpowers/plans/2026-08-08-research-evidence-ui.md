# Deeper Notebook Research Evidence UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended; this plan is bounded to one component) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show immutable web-evidence provenance in the existing Research source approval panel without changing approval behavior.

**Architecture:** Extend the already typed `ResearchCandidate` API shape with an optional `ResearchEvidence` record and render a focused `EvidenceReceipt` child component inside `SourceApprovalPanel`. Keep the receipt presentational and read-only; use existing design-system Badge and semantic color tokens.

**Tech Stack:** Next.js/React, TypeScript, Tailwind utility classes, Vitest Testing Library.

## Global Constraints

- No new network calls, mutations, or source-fetch behavior.
- Evidence is optional for backward compatibility.
- Every status is conveyed with text and accessible semantics, not color alone.
- No animation is necessary for this frequent approval workflow.
- Preserve existing checkbox/button behavior and copy.

### Task 1: Add failing UI tests

**Files:**
- Modify: `frontend/src/components/research/SourceApprovalPanel.test.tsx`

- [x] **Step 1: Add RED assertions**

Add an evidence-bearing candidate with `provider: 'tavily'`, `freshness: 'stale'`, `degraded: true`, `retrieved_at`, and 64-character fingerprints. Assert the panel renders `Stale`, `Fallback provider`, provider text, both shortened fingerprints, and an accessible label containing the full source fingerprint. Add a legacy candidate without evidence and assert it still renders and remains selectable.

- [x] **Step 2: Run the focused test to confirm RED**

Run: `npm exec vitest run frontend/src/components/research/SourceApprovalPanel.test.tsx`

Expected: the new evidence assertions fail because the type and receipt do not exist.

### Task 2: Implement the typed evidence receipt

**Files:**
- Modify: `frontend/src/lib/api/research.ts`
- Create: `frontend/src/components/research/EvidenceReceipt.tsx`
- Create: `frontend/src/components/research/EvidenceReceipt.test.tsx`
- Modify: `frontend/src/components/research/SourceApprovalPanel.tsx`

- [x] **Step 1: Add the additive API type**

```ts
export interface ResearchEvidence {
  query: string
  provider: string
  title: string
  url: string
  snippet: string
  retrieved_at: string
  freshness: 'fresh' | 'stale' | 'unknown'
  degraded: boolean
  source_fingerprint: string
  evidence_id: string
}

export interface ResearchCandidate {
  // existing fields remain unchanged
  evidence?: ResearchEvidence | null
}
```

- [x] **Step 2: Build the presentational receipt**

Render a semantic `<dl>` with provider, freshness label, fallback label when degraded, localized-enough UTC retrieval text, and shortened fingerprints. Use `title`/`aria-label` for full fingerprint values. Return `null` when evidence is absent.

- [x] **Step 3: Compose it into SourceApprovalPanel**

Render `<EvidenceReceipt evidence={candidate.evidence} />` below the existing snippet. Do not alter the checkbox, selection state, or approval callback.

- [x] **Step 4: Run focused tests**

Run: `npm exec vitest run frontend/src/components/research/SourceApprovalPanel.test.tsx frontend/src/components/research/EvidenceReceipt.test.tsx`

Expected: all focused UI tests pass.

### Task 3: Run frontend quality gates

**Files:**
- No additional files unless a focused test exposes a scoped accessibility/type issue.

- [x] **Step 1: Run the frontend unit suite and lint/type/build checks**

Run the repository’s existing frontend unit, lint, typecheck, and production build commands from `frontend/package.json`. Record inherited diagnostics separately from new failures.

- [x] **Step 2: Run the mocked browser suite**

Run the existing mocked-browser Playwright project if this component is covered by the suite. Confirm the approval interaction remains unchanged.

- [x] **Step 3: Inspect scope and commit**

Confirm only the research API type and receipt/panel tests/components changed, then commit:

```bash
git add frontend/src/lib/api/research.ts frontend/src/components/research/EvidenceReceipt.tsx frontend/src/components/research/EvidenceReceipt.test.tsx frontend/src/components/research/SourceApprovalPanel.tsx frontend/src/components/research/SourceApprovalPanel.test.tsx docs/superpowers/specs/2026-08-08-research-evidence-ui-design.md docs/superpowers/plans/2026-08-08-research-evidence-ui.md
git commit -m "feat(ui): show research evidence receipts"
```

## Verification receipt (2026-08-08)

- Focused Vitest: 2 files, 5 tests passed.
- Frontend unit suite: 169 files, 1,332 tests passed; ESLint passed with no findings.
- Next.js production build passed. Standalone `npx tsc --noEmit` retains inherited test-only diagnostics in ThemeProvider/theme-store and use-knowledge-workspace; no research receipt diagnostics were reported.
- The mocked-browser project lists no SourceApprovalPanel/evidence-receipt test; no browser scenario directly collects this component.
