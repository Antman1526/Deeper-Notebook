# Responsive Working Desk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep every Working Desk action label and supporting text readable and reachable as the native app window becomes shorter or narrower.

**Architecture:** The Horizon component exposes stable presentation hooks, while its colocated/global folio CSS uses container-aware auto-fit grid sizing and bounded height compaction. The existing Horizon scroll region remains the overflow authority; no JavaScript resize state is introduced.

**Tech Stack:** React 19, TypeScript, Tailwind utility classes, global CSS, Vitest/Testing Library, Playwright, Next.js 16.

## Global Constraints

- Preserve existing action elements, callbacks, routes, keyboard behavior, source order, and accessible names.
- Preserve readable text sizes and a 44 CSS-pixel minimum interactive target.
- Never use CSS `zoom`, transform scaling, line clamping, ellipsis, or hidden overflow to make text appear to fit.
- The 1020 by 631 screenshot size and 800 by 600 compact size must have no horizontally clipped action text.
- Content that exceeds the short viewport must remain reachable through the existing Horizon scroll region.
- Preserve unrelated untracked `.codex/agent-context` files and do not change APIs, schemas, or data hooks.

---

### Task 1: Reproduce compact-window clipping

**Files:**
- Modify: `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.test.tsx`
- Modify: `frontend/e2e/luminous-folio-visual.spec.ts`

**Interfaces:**
- Consumes: `IntelligenceHorizon` action names and `data-testid="horizon-scroll-region"`.
- Produces: a failing compact-window contract for stable layout hooks, readable action-card geometry, and scroll reachability.

- [ ] **Step 1: Add the component contract before production edits**

Render the Horizon and require a `data-dn-horizon-page="true"` ancestor plus `data-dn-horizon-actions="true"` on the action navigation. Continue asserting the four existing accessible action names and the scroll-region classes.

- [ ] **Step 2: Add the browser regression before production edits**

At `{ width: 1020, height: 631 }` and `{ width: 800, height: 600 }`, install the existing Luminous fixture, visit `/`, and inspect each action's bounding box and its visible text descendants. Assert action width is at least 112 CSS pixels, text boxes remain within the action's inline bounds, the document has no horizontal overflow, and the scroll region can reveal the final action and Recent folios section.

- [ ] **Step 3: Run RED**

Run:

```bash
cd frontend
npx vitest run src/components/deeper-notebook/horizon/IntelligenceHorizon.test.tsx
npx playwright test e2e/luminous-folio-visual.spec.ts --project=mocked-browser --grep "compact Working Desk"
```

Expected: the component contract fails because the new presentation hooks are absent, and the browser test fails because the current viewport-driven four-column layout produces action cards narrower than 112 CSS pixels.

### Task 2: Implement container-aware responsive layout

**Files:**
- Modify: `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.tsx`
- Modify: `frontend/src/components/deeper-notebook/folio/folio.css`

**Interfaces:**
- Consumes: existing `HorizonActions` markup and `FolioPage`/`FolioSpread` primitives.
- Produces: `data-dn-horizon-page`, `data-dn-horizon-cover`, `data-dn-horizon-actions`, and CSS-only adaptive layout behavior.

- [ ] **Step 1: Add stable presentation hooks**

Add the Horizon page and actions data attributes without changing callbacks, routes, or accessible names. Remove the viewport breakpoint column utilities from the action navigation so CSS owns column selection.

- [ ] **Step 2: Add minimal CSS**

In `folio.css`, make the Horizon page an inline-size container. Define the action grid as:

```css
[data-dn-horizon-actions] {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr));
  gap: var(--dn-space-3);
}
```

Use a Horizon-scoped container query to choose a larger minimum card measure when space permits. Add a Horizon-scoped short-height media query that reduces only outer padding/gaps and cover/spread spacing. Do not reduce font sizes or control minimum heights.

- [ ] **Step 3: Run GREEN**

Run the Task 1 Vitest and Playwright commands. Expected: both pass, with two or one action columns in constrained primary containers and reachable lower content.

### Task 3: Verify responsive and release boundaries

**Files:**
- Modify only if a real regression requires it: the four files above.

**Interfaces:**
- Consumes: completed responsive implementation.
- Produces: browser, static, and build evidence for review.

- [ ] **Step 1: Run focused and adjoining frontend tests**

```bash
cd frontend
npx vitest run \
  src/components/deeper-notebook/horizon/IntelligenceHorizon.test.tsx \
  src/components/deeper-notebook/folio/folio.test.tsx \
  src/components/deeper-notebook/shell/shell-css.test.ts
npm run lint
npx tsc --noEmit
```

Expected: all tests pass, lint has no new errors or warnings, and TypeScript exits zero.

- [ ] **Step 2: Run real-browser viewport proof**

```bash
cd frontend
npx playwright test \
  e2e/luminous-folio-visual.spec.ts \
  e2e/all-screen-visual-audit.spec.ts \
  --project=mocked-browser --workers=1
```

Expected: compact Working Desk checks and the existing all-screen audit pass without console errors, clipped controls, or horizontal overflow.

- [ ] **Step 3: Run production build**

```bash
cd frontend
NEXT_TELEMETRY_DISABLED=1 npm run build
```

Expected: Next.js production build exits zero.

- [ ] **Step 4: Inspect and commit**

Verify `git diff --check`, inspect the exact diff, run staged secret scanning, and commit only the responsive design, implementation, and direct tests with:

```bash
git commit -m "fix(ui): adapt working desk to compact windows"
```

Expected: atomic commit, tracked worktree clean, supplied untracked task contexts preserved.
