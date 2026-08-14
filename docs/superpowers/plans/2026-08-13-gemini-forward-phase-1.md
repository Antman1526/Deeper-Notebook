# Gemini-Forward Entire App Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the reversible Gemini-forward visual-system foundation, shared shell, foundational routes, and executable all-view contract without changing domain behavior, persisted authority, or network traffic.

**Architecture:** Add one static presentation flag in front of the existing Luminous and legacy rollback stack, extend the current catalog/theme pipeline with a new light theme, and build focused workspace primitives under `frontend/src/components/deeper-notebook/workspace/`. Existing route hooks and domain components remain authoritative. A checked 22-route manifest and strict Playwright fixture establish the complete route/theme/viewport contract while only `/login`, `/setup-wizard`, `/`, and shared shell/state surfaces receive Phase 1 content migration.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, CSS custom properties and container queries, Zustand theme persistence, Lucide icons, Vitest with Testing Library, Playwright, ESLint, and the existing build/rebrand/secret-scan tooling.

## Global Constraints

- Work only in the isolated `codex/gemini-forward-workspace` worktree and confirm `git rev-parse --show-toplevel` before editing.
- Read `/Users/Antman/.codex/context.md`, `docs/superpowers/specs/2026-08-13-gemini-forward-entire-app-design.md`, and this plan before every task.
- Preserve unrelated dirty and untracked files; never reset or stage `.codex/agent-context/*`.
- Phase 1 is frontend-only. Do not add a database migration, API route, cloud provider, image generator, source cache, or artifact authority.
- `NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0` must render the pre-existing Luminous/legacy decision tree exactly; unset also remains legacy throughout Phase 1.
- `NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1` changes presentation only. It may not alter route URLs, request methods, API payloads, source authority, notebook ownership, assistant authority, model routing, Study behavior, Podcast behavior, authentication, or publication boundaries.
- Existing explicit saved themes remain unchanged. Only a user without canonical or legacy theme storage receives `gemini-forward-light` when V2 is enabled.
- Keep the existing `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` behavior intact whenever V2 is off.
- Use the existing fonts, dependencies, icons, query hooks, dialogs, navigation destinations, and localization framework. Do not add a runtime dependency.
- Use semantic tokens; no feature component may hardcode the inspiration product's colors, branding, icons, copy, assets, or layout.
- Body text stays at least `1rem`/16 px. Touch-capable controls remain at least `44px × 44px`. Use reflow, wrapping, container queries, and reachable scrolling instead of shrinking content.
- Every task starts with a focused RED test, records the expected failure, implements the smallest passing change, runs focused GREEN and static checks, and ends in an atomic commit.
- Do not update a visual snapshot until the actual render has been inspected at full size and the semantic geometry assertions are green.
- Record commands, counts, build flags, baseline sizes, failures, screenshots, and open limitations in `docs/verification/2026-08-13-gemini-forward-phase-1.md`.

---

## Specification Traceability

| Approved requirement | Phase 1 task | Proof |
|---|---:|---|
| Canonical V2 flag, explicit rollback, unchanged legacy flags | 1, 4 | unit, feature build, flag-off browser |
| Checked 22-route inventory | 1 | manifest unit contract |
| Gemini-forward light, Research Core dark, high contrast | 2 | catalog, theme script, CSS and browser matrix |
| Semantic visual roles, bounded type, motion, contrast | 2 | CSS contract and accessibility tests |
| Shared workspace primitives | 3 | component tests |
| Adaptive shell, navigation, commands, focus mode | 4 | shell parity and browser tests |
| `/login`, `/setup-wizard`, `/` | 5 | route/component tests and browser states |
| Every existing view remains reachable | 6 | 264-cell base matrix |
| Loading, empty, processing, degraded, error, unavailable, feature-off | 3, 5, 6 | state fixture map |
| No new network authority | 4, 6 | exact request ledgers |
| Responsive, keyboard and screen-reader contracts | 3–6 | unit and Playwright geometry/focus gates |
| Performance and reversible handoff | 7 | build comparison and full gate |

---

## File Structure Map

### Existing integration points

- `frontend/src/lib/features.ts` — static client-safe feature flag authority.
- `frontend/src/lib/themes/catalog.ts` — persisted theme IDs and previews.
- `frontend/src/lib/theme-script.ts` — pre-hydration theme selection.
- `frontend/src/lib/stores/theme-store.ts` — live catalog application.
- `frontend/src/app/globals.css` — theme palette declarations.
- `frontend/src/components/deeper-notebook/tokens.css` — component semantic roles.
- `frontend/src/components/layout/AppShell.tsx` — reversible shell selection.
- `frontend/src/components/deeper-notebook/shell/*` — existing navigation, command, utility, and focus behavior reused by the V2 shell.
- `frontend/src/app/(auth)/login/page.tsx` — login presentation boundary.
- `frontend/src/app/(dashboard)/page.tsx` — dashboard data/action authority.
- `frontend/src/app/(dashboard)/setup-wizard/page.tsx` — setup state and completion authority.
- `frontend/e2e/fixtures/luminous-folio.ts` — existing deterministic API fixture reused, not replaced by catch-all mocks.

### New Phase 1 modules

```text
frontend/src/lib/visual-system/
├── route-manifest.ts
└── route-manifest.test.ts

frontend/src/components/deeper-notebook/workspace/
├── WorkspacePage.tsx
├── WorkspaceHero.tsx
├── VisualCard.tsx
├── VisualCardGrid.tsx
├── StatePanel.tsx
├── ResponsiveActionBar.tsx
├── WorkspaceAppShell.tsx
├── WorkspaceAuthFrame.tsx
├── WorkspaceHome.tsx
├── workspace.css
└── workspace.test.tsx

frontend/e2e/fixtures/visual-system.ts
frontend/e2e/visual-system-matrix.spec.ts
docs/verification/2026-08-13-gemini-forward-phase-1.md
```

### Locked public interfaces

```ts
export function isVisualSystemV2Enabled(): boolean

export const LEGACY_DEFAULT_THEME_ID = 'research-core-dark'
export const VISUAL_SYSTEM_DEFAULT_THEME_ID = 'gemini-forward-light'
export function getFreshThemeDefault(visualSystemEnabled: boolean): ThemeId

export type VisualRoutePhase = 1 | 2 | 3 | 4
export type VisualRouteState =
  | 'loading'
  | 'empty'
  | 'populated'
  | 'processing'
  | 'degraded'
  | 'offline'
  | 'error'
  | 'unavailable'
export interface VisualRouteEntry {
  source: string
  route: string
  browserPath: string
  phase: VisualRoutePhase
  states: readonly VisualRouteState[]
}
export const VISUAL_ROUTE_MANIFEST: readonly VisualRouteEntry[]

export interface WorkspacePageProps extends React.HTMLAttributes<HTMLElement> {
  title: React.ReactNode
  eyebrow?: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}

export interface WorkspaceHeroProps {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  image?: React.ReactNode
  actions?: React.ReactNode
}

export type VisualCardInteraction =
  | { href: string; onActivate?: never }
  | { href?: never; onActivate(): void }
  | { href?: never; onActivate?: never }

export type VisualCardProps = VisualCardInteraction & {
  title: string
  description?: React.ReactNode
  media?: React.ReactNode
  metadata?: React.ReactNode
  children?: React.ReactNode
}

export interface VisualCardGridProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  minimum?: 'compact' | 'standard' | 'wide'
}

export interface ResponsiveActionBarProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

export type StatePanelKind =
  | 'loading'
  | 'empty'
  | 'processing'
  | 'degraded'
  | 'offline'
  | 'error'
  | 'unavailable'

export interface StatePanelProps {
  kind: StatePanelKind
  title: string
  description: string
  preservation?: string
  action?: React.ReactNode
  details?: React.ReactNode
}

export type WorkspaceHomeProps = IntelligenceHorizonProps
```

---

### Task 1: Freeze the V2 Flag and Complete Route Manifest

**Files:**
- Modify: `frontend/src/lib/features.ts`
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features-build-contract.test.ts`
- Create: `frontend/src/lib/visual-system/route-manifest.ts`
- Create: `frontend/src/lib/visual-system/route-manifest.test.ts`
- Modify: `frontend/package.json`
- Create: `docs/verification/2026-08-13-gemini-forward-phase-1.md`

**Interfaces:**
- Consumes: the static `envFlag` helper and the current `frontend/src/app/**/page.tsx` tree.
- Produces: `isVisualSystemV2Enabled()` and `VISUAL_ROUTE_MANIFEST`, used by shell selection and the browser matrix.

- [ ] **Step 1: Record the immutable implementation base.**

Before editing production or test files, record the exact 40-character result of `git rev-parse HEAD` as `Base commit: \`<hash>\`` in `docs/verification/2026-08-13-gemini-forward-phase-1.md`, together with `git status --short`, the 22-route source list, and flag-off build sizes. The value is evidence, not a generated source file.

- [ ] **Step 2: Write failing flag and inventory tests.**

Add `NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2` to the exact public flag list and assert these states:

```ts
delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
expect(isVisualSystemV2Enabled()).toBe(false)
process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
expect(isVisualSystemV2Enabled()).toBe(true)
process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
expect(isVisualSystemV2Enabled()).toBe(false)
```

Create the manifest test so it recursively finds `page.tsx` beneath `src/app`, normalizes path separators, and compares the exact source list with `VISUAL_ROUTE_MANIFEST.map(entry => entry.source)`. Also assert 22 unique routes, exact browser paths for the three dynamic entries, and phase membership.

```ts
expect(VISUAL_ROUTE_MANIFEST).toHaveLength(22)
expect(new Set(VISUAL_ROUTE_MANIFEST.map(entry => entry.source)).size).toBe(22)
expect(new Set(VISUAL_ROUTE_MANIFEST.map(entry => entry.route)).size).toBe(22)
expect(byRoute['/notebooks/[id]'].browserPath).toBe('/notebooks/notebook-fixture-001')
expect(byRoute['/sources/[id]'].browserPath).toBe('/sources/source-fixture-001')
expect(byRoute['/study/plans/[planId]'].browserPath).toBe('/study/plans/study_plan%3Afixture')
expect(VISUAL_ROUTE_MANIFEST.filter(entry => entry.phase === 1).map(entry => entry.route)).toEqual([
  '/login', '/', '/setup-wizard',
])
```

- [ ] **Step 3: Run RED.**

```bash
cd frontend
npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/lib/visual-system/route-manifest.test.ts
```

Expected: import failures for the missing flag and manifest.

- [ ] **Step 4: Implement the static flag and exact manifest.**

Add only a canonical flag:

```ts
export function isVisualSystemV2Enabled(): boolean {
  return envFlag(process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2, undefined, false)
}
```

Define the manifest with these exact public routes and phases:

```ts
export const VISUAL_ROUTE_MANIFEST = [
  { source: 'src/app/(auth)/login/page.tsx', route: '/login', browserPath: '/login', phase: 1, states: ['empty', 'error'] },
  { source: 'src/app/(dashboard)/page.tsx', route: '/', browserPath: '/', phase: 1, states: ['loading', 'empty', 'populated', 'degraded', 'offline'] },
  { source: 'src/app/(dashboard)/setup-wizard/page.tsx', route: '/setup-wizard', browserPath: '/setup-wizard', phase: 1, states: ['loading', 'populated', 'degraded', 'error'] },
  { source: 'src/app/(dashboard)/notebooks/page.tsx', route: '/notebooks', browserPath: '/notebooks', phase: 2, states: ['loading', 'empty', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/notebooks/[id]/page.tsx', route: '/notebooks/[id]', browserPath: '/notebooks/notebook-fixture-001', phase: 2, states: ['loading', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/sources/page.tsx', route: '/sources', browserPath: '/sources', phase: 2, states: ['loading', 'empty', 'populated', 'processing', 'error'] },
  { source: 'src/app/(dashboard)/sources/[id]/page.tsx', route: '/sources/[id]', browserPath: '/sources/source-fixture-001', phase: 2, states: ['loading', 'populated', 'processing', 'error'] },
  { source: 'src/app/(dashboard)/knowledge/page.tsx', route: '/knowledge', browserPath: '/knowledge', phase: 2, states: ['loading', 'empty', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/search/page.tsx', route: '/search', browserPath: '/search', phase: 2, states: ['empty', 'populated', 'processing', 'error'] },
  { source: 'src/app/(dashboard)/capture/page.tsx', route: '/capture', browserPath: '/capture', phase: 2, states: ['empty', 'processing', 'error'] },
  { source: 'src/app/(dashboard)/studio/page.tsx', route: '/studio', browserPath: '/studio', phase: 3, states: ['empty', 'processing', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/podcasts/page.tsx', route: '/podcasts', browserPath: '/podcasts', phase: 3, states: ['loading', 'empty', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/podcasts/studio/page.tsx', route: '/podcasts/studio', browserPath: '/podcasts/studio', phase: 3, states: ['empty', 'processing', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/study/page.tsx', route: '/study', browserPath: '/study', phase: 3, states: ['loading', 'empty', 'populated', 'degraded', 'offline', 'error'] },
  { source: 'src/app/(dashboard)/study/plans/[planId]/page.tsx', route: '/study/plans/[planId]', browserPath: '/study/plans/study_plan%3Afixture', phase: 3, states: ['loading', 'populated', 'processing', 'degraded', 'error'] },
  { source: 'src/app/(dashboard)/transformations/page.tsx', route: '/transformations', browserPath: '/transformations', phase: 3, states: ['loading', 'empty', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/settings/page.tsx', route: '/settings', browserPath: '/settings', phase: 4, states: ['populated'] },
  { source: 'src/app/(dashboard)/settings/api-keys/page.tsx', route: '/settings/api-keys', browserPath: '/settings/api-keys', phase: 4, states: ['loading', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/settings/launcher-prefs/page.tsx', route: '/settings/launcher-prefs', browserPath: '/settings/launcher-prefs', phase: 4, states: ['loading', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/settings/local-models/page.tsx', route: '/settings/local-models', browserPath: '/settings/local-models', phase: 4, states: ['loading', 'empty', 'populated', 'degraded', 'error'] },
  { source: 'src/app/(dashboard)/settings/mcp/page.tsx', route: '/settings/mcp', browserPath: '/settings/mcp', phase: 4, states: ['loading', 'empty', 'populated', 'error'] },
  { source: 'src/app/(dashboard)/advanced/page.tsx', route: '/advanced', browserPath: '/advanced', phase: 4, states: ['populated', 'unavailable'] },
] as const satisfies readonly VisualRouteEntry[]
```

Add `test:e2e:visual-system` to `package.json` as `playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser`.

- [ ] **Step 5: Run GREEN and commit.**

```bash
cd frontend
npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/lib/visual-system/route-manifest.test.ts
npx tsc --noEmit
git diff --check
git add frontend/src/lib/features.ts frontend/src/lib/features.test.ts frontend/src/lib/features-build-contract.test.ts frontend/src/lib/visual-system/route-manifest.ts frontend/src/lib/visual-system/route-manifest.test.ts frontend/package.json docs/verification/2026-08-13-gemini-forward-phase-1.md
git commit -m "test(ui): freeze visual system route contract"
```

Expected: focused tests and TypeScript pass; one atomic commit.

---

### Task 2: Add the Theme Family and Semantic Tokens

**Files:**
- Modify: `frontend/src/lib/themes/catalog.ts`
- Modify: `frontend/src/lib/themes/catalog.test.ts`
- Modify: `frontend/src/lib/theme-script.ts`
- Modify: `frontend/src/lib/theme-script.test.ts`
- Modify: `frontend/src/components/providers/ThemeProvider.test.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/deeper-notebook/tokens.css`
- Modify: `frontend/src/components/deeper-notebook/luminous-accessibility.test.tsx`

**Interfaces:**
- Consumes: saved `dn-theme`, legacy `onp-theme`, Zustand fallback, and the catalog theme provider.
- Produces: `gemini-forward-light`, `getFreshThemeDefault()`, and semantic V2 component roles without rewriting any saved selection.

- [ ] **Step 1: Write failing theme/default tests.**

Assert the catalog grows to 26 unique IDs, the new ID is the first featured light theme, and the legacy default stays dark:

```ts
expect(THEME_CATALOG).toHaveLength(26)
expect(THEME_BY_ID['gemini-forward-light']).toMatchObject({ group: 'featured', dark: false })
expect(LEGACY_DEFAULT_THEME_ID).toBe('research-core-dark')
expect(VISUAL_SYSTEM_DEFAULT_THEME_ID).toBe('gemini-forward-light')
expect(getFreshThemeDefault(false)).toBe('research-core-dark')
expect(getFreshThemeDefault(true)).toBe('gemini-forward-light')
```

Add pre-hydration tests that dynamically import `theme-script.ts` after setting the build flag and then execute the script with empty storage. Assert V2 paints `gemini-forward-light`, V2 off paints `research-core-dark`, and either build preserves an explicit `archive-paper` selection.

Add CSS source assertions for every required role:

```ts
for (const token of [
  '--dn-canvas', '--dn-panel', '--dn-panel-raised', '--dn-selection',
  '--dn-focus', '--dn-image-overlay', '--dn-image-placeholder',
  '--dn-evidence-supported', '--dn-evidence-mixed', '--dn-evidence-unsupported',
  '--dn-radius-control', '--dn-radius-card', '--dn-radius-hero',
]) expect(tokens).toContain(token)
```

- [ ] **Step 2: Run RED.**

```bash
cd frontend
npx vitest run src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts src/components/providers/ThemeProvider.test.tsx src/components/deeper-notebook/luminous-accessibility.test.tsx
```

Expected: failures for the missing theme ID, default resolver, and tokens.

- [ ] **Step 3: Implement the catalog/default boundary.**

Add these exports:

```ts
export const LEGACY_DEFAULT_THEME_ID = 'research-core-dark' as const
export const VISUAL_SYSTEM_DEFAULT_THEME_ID = 'gemini-forward-light' as const
export const DEFAULT_THEME_ID = LEGACY_DEFAULT_THEME_ID

export function getFreshThemeDefault(visualSystemEnabled: boolean): ThemeId {
  return visualSystemEnabled ? VISUAL_SYSTEM_DEFAULT_THEME_ID : LEGACY_DEFAULT_THEME_ID
}
```

Add this catalog entry:

```ts
{
  id: 'gemini-forward-light',
  label: 'Gemini-Forward Light',
  group: 'featured',
  dark: false,
  description: 'Airy mineral canvas with original indigo, violet, cyan, and mint research accents.',
  preview: {
    canvas: '#F7F7FC', panel: '#FFFFFF', text: '#202235', primary: '#5367D9',
    accent: '#7B5BD6', border: '#D9DDF0',
  },
}
```

In `theme-script.ts`, compute `freshDefault` from `isVisualSystemV2Enabled()` at build time. Use it only when canonical, legacy, and Zustand selections are absent or malformed. Never overwrite storage.

- [ ] **Step 4: Implement semantic palettes and accessibility guards.**

Add the exact palette declaration to `globals.css`, then derive component roles in `tokens.css`:

```css
html[data-theme="gemini-forward-light"] {
  --dn-theme-canvas: #F7F7FC;
  --dn-theme-panel: #FFFFFF;
  --dn-theme-text: #202235;
  --dn-theme-primary: #5367D9;
  --dn-theme-primary-foreground: #FFFFFF;
  --dn-theme-accent: #7B5BD6;
  --dn-theme-accent-foreground: #FFFFFF;
  --dn-theme-border: #D9DDF0;
}

:root {
  --dn-image-overlay: linear-gradient(to top, rgb(20 23 45 / 72%), transparent 72%);
  --dn-image-placeholder: color-mix(in oklab, var(--card) 84%, var(--primary) 16%);
  --dn-image-generated-label: color-mix(in oklab, var(--card) 92%, var(--accent) 8%);
  --dn-evidence-supported: var(--success);
  --dn-evidence-mixed: var(--warning);
  --dn-evidence-unsupported: var(--destructive);
  --dn-radius-control: 0.75rem;
  --dn-radius-card: 1rem;
  --dn-radius-hero: 1.5rem;
  --dn-shadow-low: var(--shadow-sm);
  --dn-shadow-medium: var(--shadow-md);
}

@media (forced-colors: active) {
  [data-dn-visual-system="v2"] * { forced-color-adjust: auto; }
  [data-dn-visual-system="v2"] :focus-visible { outline: 2px solid CanvasText; }
}
```

- [ ] **Step 5: Run GREEN and commit.**

```bash
cd frontend
npx vitest run src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts src/components/providers/ThemeProvider.test.tsx src/components/deeper-notebook/luminous-accessibility.test.tsx
npx tsc --noEmit
npm run lint
git diff --check
git add frontend/src/lib/themes/catalog.ts frontend/src/lib/themes/catalog.test.ts frontend/src/lib/theme-script.ts frontend/src/lib/theme-script.test.ts frontend/src/components/providers/ThemeProvider.test.tsx frontend/src/app/globals.css frontend/src/components/deeper-notebook/tokens.css frontend/src/components/deeper-notebook/luminous-accessibility.test.tsx
git commit -m "feat(ui): add Gemini-forward theme foundation"
```

---

### Task 3: Build Shared Workspace Primitives

**Files:**
- Create: `frontend/src/components/deeper-notebook/workspace/WorkspacePage.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/WorkspaceHero.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/VisualCard.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/VisualCardGrid.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/StatePanel.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/ResponsiveActionBar.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/workspace.css`
- Create: `frontend/src/components/deeper-notebook/workspace/workspace.test.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/components/deeper-notebook/index.ts`

**Interfaces:**
- Consumes: semantic tokens, `cn`, native semantic elements, and caller-owned actions.
- Produces: fetch-free presentation primitives used by all later route phases.

- [ ] **Step 1: Write failing component contracts.**

Test one `main`/`h1`, action dispatch exactly once, `StatePanel` roles, accessible IDs, optional details, ref forwarding, and real text remaining outside any image layer. Add source-level CSS assertions for `container-type: inline-size`, `repeat(auto-fit, minmax(`, `min-height: 44px`, reduced motion, and no fixed page width.

```tsx
render(
  <WorkspacePage title="Sources" actions={<button type="button">Add source</button>}>
    <VisualCardGrid><VisualCard title="Paper A">Grounded summary</VisualCard></VisualCardGrid>
  </WorkspacePage>,
)
expect(screen.getAllByRole('main')).toHaveLength(1)
expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
expect(screen.getByRole('button', { name: 'Add source' })).toHaveAccessibleName()
```

```tsx
render(<StatePanel kind="error" title="Could not load" description="The current notebook was preserved." action={<button>Retry</button>} />)
expect(screen.getByRole('alert')).toHaveAccessibleName('Could not load')
expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
```

- [ ] **Step 2: Run RED.**

```bash
cd frontend
npx vitest run src/components/deeper-notebook/workspace/workspace.test.tsx
```

Expected: missing module imports.

- [ ] **Step 3: Implement semantic primitives.**

Use `React.forwardRef` for every exported surface. `WorkspacePage` owns the one `main` and generated heading ID. `WorkspaceHero` renders imagery only through an `image?: ReactNode` slot and always renders title/copy as DOM text. `VisualCard` defaults to `article`, accepts an optional `href` or button callback but never both, and generates distinct action labels from its title. `VisualCardGrid` is a container. `ResponsiveActionBar` is a wrapping `div` with no duplicate mobile action tree.

`StatePanel` uses this role map:

```ts
const stateRole: Record<StatePanelKind, 'status' | 'alert'> = {
  loading: 'status', empty: 'status', processing: 'status',
  degraded: 'status', offline: 'status', error: 'alert', unavailable: 'status',
}
```

Add these structural CSS contracts:

```css
.dn-workspace-page { container: dn-workspace / inline-size; min-width: 0; width: 100%; }
.dn-visual-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: clamp(0.75rem, 2cqi, 1.25rem); }
.dn-responsive-action-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; }
.dn-responsive-action-bar > :is(button, a) { min-height: 44px; }
.dn-visual-card { min-width: 0; overflow-wrap: anywhere; border-radius: var(--dn-radius-card); }
@media (prefers-reduced-motion: reduce) { .dn-workspace-page * { scroll-behavior: auto; transition-duration: 0.01ms; } }
```

- [ ] **Step 4: Run GREEN and commit.**

```bash
cd frontend
npx vitest run src/components/deeper-notebook/workspace/workspace.test.tsx src/components/deeper-notebook/folio/folio.test.tsx src/components/deeper-notebook/luminous-accessibility.test.tsx
npx tsc --noEmit
npm run lint
git diff --check
git add frontend/src/components/deeper-notebook/workspace frontend/src/app/layout.tsx frontend/src/components/deeper-notebook/index.ts
git commit -m "feat(ui): add adaptive workspace primitives"
```

---

### Task 4: Add the Reversible V2 Application Shell

**Files:**
- Create: `frontend/src/components/deeper-notebook/workspace/WorkspaceAppShell.tsx`
- Modify: `frontend/src/components/deeper-notebook/workspace/workspace.css`
- Modify: `frontend/src/components/deeper-notebook/workspace/workspace.test.tsx`
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Modify: `frontend/src/components/layout/AppShell.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/shell/navigation-contract.test.tsx`

**Interfaces:**
- Consumes: `InstrumentDock`, `CommandBar`, `AdaptiveNavigator`, `ContextLens`, `ShellUtilities`, `FocusModeControl`, and `isVisualSystemV2Enabled()`.
- Produces: a single V2 shell slot with the existing navigation, create, auth, language, theme, health, version, audio, guided-tip, and focus authorities.

- [ ] **Step 1: Write failing three-way shell tests.**

Prove selection precedence:

```tsx
process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '0'
render(<AppShell><div data-testid="page" /></AppShell>)
expect(screen.getByTestId('visual-system-v2-shell')).toBeInTheDocument()
expect(screen.queryByTestId('legacy-sidebar')).not.toBeInTheDocument()
```

```tsx
process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = '1'
render(<AppShell><div data-testid="page" /></AppShell>)
expect(screen.getByRole('navigation', { name: 'Primary tools' })).toBeInTheDocument()
expect(screen.queryByTestId('visual-system-v2-shell')).not.toBeInTheDocument()
```

Also assert one child mount, one guided-tip anchor per destination, unchanged exact href order, one Focus control, and one dispatch for Source/Notebook/Podcast creation.

- [ ] **Step 2: Run RED.**

```bash
cd frontend
npx vitest run src/components/layout/AppShell.test.tsx src/components/deeper-notebook/workspace/workspace.test.tsx src/components/deeper-notebook/shell/navigation-contract.test.tsx
```

Expected: missing V2 shell and failed precedence assertion.

- [ ] **Step 3: Implement the V2 shell without forking authorities.**

Use the existing shell children exactly once:

```tsx
export function WorkspaceAppShell({ children }: { children: React.ReactNode }) {
  return (
    <div data-testid="visual-system-v2-shell" data-dn-visual-system="v2" className="dn-workspace-shell">
      <InstrumentDock />
      <div className="dn-workspace-shell-body">
        <CommandBar />
        <AdaptiveNavigator />
        <section className="dn-workspace-canvas">{children}</section>
        <ContextLens />
      </div>
      <ShellUtilities />
      <FocusModeControl />
    </div>
  )
}
```

Select it before the current decision tree:

```tsx
export function AppShell({ children }: AppShellProps) {
  if (isVisualSystemV2Enabled()) return <WorkspaceAppShell>{children}</WorkspaceAppShell>
  return isLuminousFolioEnabled()
    ? <LuminousAppShell>{children}</LuminousAppShell>
    : <LegacyAppShell>{children}</LegacyAppShell>
}
```

CSS must use grid areas at wide sizes, a compact rail at 768–1023 px, and the existing mobile navigator at widths below 768 px. The document must not gain horizontal overflow; `.dn-workspace-canvas` owns route scrolling with `min-width: 0`, `min-height: 0`, and `overflow: auto`.

- [ ] **Step 4: Run GREEN, build both flags, and commit.**

```bash
cd frontend
npx vitest run src/components/layout/AppShell.test.tsx src/components/deeper-notebook/workspace/workspace.test.tsx src/components/deeper-notebook/shell/shell.test.tsx src/components/deeper-notebook/shell/navigation-contract.test.tsx
npx tsc --noEmit
npm run lint
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 npm run build
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 npm run build
git diff --check
git add frontend/src/components/deeper-notebook/workspace/WorkspaceAppShell.tsx frontend/src/components/deeper-notebook/workspace/workspace.css frontend/src/components/deeper-notebook/workspace/workspace.test.tsx frontend/src/components/layout/AppShell.tsx frontend/src/components/layout/AppShell.test.tsx frontend/src/components/deeper-notebook/shell/navigation-contract.test.tsx
git commit -m "feat(ui): add reversible visual workspace shell"
```

---

### Task 5: Migrate Login, Setup, and Home Surfaces

**Files:**
- Create: `frontend/src/components/deeper-notebook/workspace/WorkspaceAuthFrame.tsx`
- Create: `frontend/src/components/deeper-notebook/workspace/WorkspaceHome.tsx`
- Modify: `frontend/src/components/deeper-notebook/workspace/workspace.css`
- Modify: `frontend/src/components/deeper-notebook/workspace/workspace.test.tsx`
- Modify: `frontend/src/app/(auth)/login/page.tsx`
- Create: `frontend/src/app/(auth)/login/page.test.tsx`
- Modify: `frontend/src/app/(dashboard)/page.tsx`
- Modify: `frontend/src/app/(dashboard)/page.test.tsx`
- Modify: `frontend/src/app/(dashboard)/setup-wizard/page.tsx`
- Modify: `frontend/src/app/(dashboard)/setup-wizard/page.test.tsx`

**Interfaces:**
- Consumes: existing `LoginForm`, dashboard hooks/callbacks, setup health hooks, `markWizardCompleted`, and Phase 1 primitives.
- Produces: V2 presentations for the three Phase 1 routes while V2 off retains their exact prior components and request behavior.

- [ ] **Step 1: Write failing flag-on/flag-off route tests.**

For each route, test both modes. Flag-on must expose `data-dn-visual-system="v2"` or the V2 frame marker, one `main`, one visible `h1`, and the same enabled actions. Flag-off must retain `AuthFolio`, `IntelligenceHorizon`, or `SystemRouteFrame` markers. Mock existing hooks and assert identical call counts before and after the visual branch.

Dashboard action assertions remain exact:

```tsx
fireEvent.click(screen.getByRole('button', { name: 'New Notebook' }))
expect(openNotebookDialog).toHaveBeenCalledTimes(1)
fireEvent.click(screen.getByRole('button', { name: 'Podcast' }))
expect(openPodcastDialog).toHaveBeenCalledTimes(1)
fireEvent.click(screen.getByRole('link', { name: 'Ask' }))
expect(push).toHaveBeenCalledWith('/search')
```

Setup assertions retain automatic healthy/returning-user redirect, degraded continue, unavailable-disabled behavior, exact cookie attributes, and zero new API calls.

- [ ] **Step 2: Run RED.**

```bash
cd frontend
npx vitest run 'src/app/(auth)/login/page.test.tsx' 'src/app/(dashboard)/page.test.tsx' 'src/app/(dashboard)/setup-wizard/page.test.tsx' src/components/deeper-notebook/workspace/workspace.test.tsx
```

Expected: missing V2 route components and markers.

- [ ] **Step 3: Implement presentation-only route branches.**

`WorkspaceAuthFrame` owns the login `main` and visible `h1`; `LoginForm` remains unchanged. `WorkspaceHome` accepts the same dashboard props as the current presentation, uses `WorkspaceHero`, a four-card `VisualCardGrid`, `StatePanel`, and existing `RuntimeStatusPanel`. It must not fetch.

Use build-static branches at page boundaries:

```tsx
return isVisualSystemV2Enabled()
  ? <WorkspaceAuthFrame><LoginForm /></WorkspaceAuthFrame>
  : <AuthFolio><LoginForm /></AuthFolio>
```

```tsx
const View = isVisualSystemV2Enabled() ? WorkspaceHome : IntelligenceHorizon
return <AppShell><View {...presentationProps} /></AppShell>
```

For setup, keep the current hook and effect body in the page. Only switch the outer presentation frame; do not duplicate `useDeepHealth`, `useNotebooks`, the auto-advance effect, or `handleContinue`.

- [ ] **Step 4: Run GREEN and commit.**

```bash
cd frontend
npx vitest run 'src/app/(auth)/login/page.test.tsx' 'src/app/(dashboard)/page.test.tsx' 'src/app/(dashboard)/setup-wizard/page.test.tsx' src/components/deeper-notebook/workspace/workspace.test.tsx src/components/deeper-notebook/horizon/IntelligenceHorizon.test.tsx
npx tsc --noEmit
npm run lint
git diff --check
git add frontend/src/components/deeper-notebook/workspace frontend/src/app/'(auth)'/login/page.tsx frontend/src/app/'(auth)'/login/page.test.tsx frontend/src/app/'(dashboard)'/page.tsx frontend/src/app/'(dashboard)'/page.test.tsx frontend/src/app/'(dashboard)'/setup-wizard/page.tsx frontend/src/app/'(dashboard)'/setup-wizard/page.test.tsx
git commit -m "feat(ui): migrate visual system entry routes"
```

---

### Task 6: Build the Strict 264-Cell All-View Browser Contract

**Files:**
- Create: `frontend/e2e/fixtures/visual-system.ts`
- Create: `frontend/e2e/visual-system-matrix.spec.ts`
- Modify: `frontend/e2e/all-screen-visual-audit.spec.ts`
- Modify: `frontend/src/lib/visual-system/route-manifest.test.ts`

**Interfaces:**
- Consumes: `VISUAL_ROUTE_MANIFEST`, `installLuminousFolioFixture`, the Study fixture's exact handlers, and existing request policy.
- Produces: 22 routes × 3 themes × 4 viewports = 264 base cells plus flag-off and focused state cases.

- [ ] **Step 1: Write failing fixture and matrix tests.**

Use these exact themes and viewports:

```ts
export const VISUAL_MATRIX_THEMES = [
  'gemini-forward-light', 'research-core-dark', 'high-contrast-light',
] as const
export const VISUAL_MATRIX_VIEWPORTS = [
  { name: 'mobile', width: 320, height: 844 },
  { name: 'narrow', width: 768, height: 1024 },
  { name: 'compact-desktop', width: 1020, height: 631 },
  { name: 'large-desktop', width: 1440, height: 900 },
] as const
```

Assert their cartesian product with 22 routes equals 264. Add a deliberately wrong-method fixture probe and require HTTP 405 plus an `unexpected` ledger entry. Add a route inventory mismatch test by comparing the manifest sources to the app tree.

- [ ] **Step 2: Run RED.**

```bash
cd frontend
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser --grep "fixture rejects wrong methods|matrix contract"
```

Expected: missing fixture/spec behavior.

- [ ] **Step 3: Implement exact fixtures without a catch-all API handler.**

`installVisualSystemFixture(page, options)` must:

1. install the existing deterministic Luminous/research handlers;
2. add only named exact handlers for setup health and Study plan routes absent from that fixture;
3. validate request method before fulfilling;
4. record `{ viewport, method, canonicalPath, status }`;
5. pin theme, reduced motion, solid transparency, wizard cookie, and deterministic locale before hydration;
6. record unknown same-origin `/api/` requests as failures;
7. reject external network requests;
8. return an assertion object with exact `expected` and `seen` frequency maps.

Do not use `**/api/**`, `route.fallback()` for unknown APIs, or a catch-all success response.

- [ ] **Step 4: Implement semantic geometry helpers.**

For every visible action and card, return actionable name, bounding rectangle, parent rectangle, target size, and clipping. For the document scroll owner, record initial `scrollTop`, `scrollHeight`, `clientHeight`, scroll to the last `[data-dn-matrix-lower-content]` marker, and prove strict increase plus final four-edge viewport containment. Assert:

```ts
expect(await page.getByRole('main').count()).toBe(1)
expect(await page.getByRole('heading', { level: 1 }).count()).toBe(1)
expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
expect(geometry.clipped).toEqual([])
expect(geometry.brokenImages).toEqual([])
expect(geometry.duplicateKeys).toEqual([])
```

- [ ] **Step 5: Run the complete V2 and rollback matrices.**

```bash
cd frontend
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 npm run build
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 npm run test:e2e:visual-system -- --workers=1
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser --grep "explicit rollback" --workers=1
```

Expected: 264 base cells pass under V2; rollback cases show no V2 marker, no V2-only requests, and preserve the legacy shell/routes. Restore `test-results/.last-run.json` byte-for-byte and delete only task-owned failure output.

- [ ] **Step 6: Inspect flagship screenshots and commit.**

Capture `/login`, `/`, and `/setup-wizard` in all three themes at 320, 1020×631, and 1440×900. Inspect each at full resolution. Add or update only the three stable flagship snapshots whose semantic assertions already pass.

```bash
git diff --check
git add frontend/e2e/fixtures/visual-system.ts frontend/e2e/visual-system-matrix.spec.ts frontend/e2e/all-screen-visual-audit.spec.ts frontend/src/lib/visual-system/route-manifest.test.ts frontend/e2e/*visual-system*.png
git commit -m "test(ui): prove complete visual route matrix"
```

---

### Task 7: Phase 1 Regression, Performance, Review, and Handoff

**Files:**
- Modify: `docs/verification/2026-08-13-gemini-forward-phase-1.md`
- Modify only if an actual gate requires a scoped correction: Phase 1-owned files listed in Tasks 1–6.

**Interfaces:**
- Consumes: all Phase 1 commits and the pre-change build receipt.
- Produces: an independently reviewable Phase 1 closeout with explicit rollback and Phase 2 boundary.

- [ ] **Step 1: Run the focused Phase 1 suite.**

```bash
cd frontend
npx vitest run \
  src/lib/features.test.ts \
  src/lib/features-build-contract.test.ts \
  src/lib/visual-system/route-manifest.test.ts \
  src/lib/themes/catalog.test.ts \
  src/lib/theme-script.test.ts \
  src/components/providers/ThemeProvider.test.tsx \
  src/components/layout/AppShell.test.tsx \
  src/components/deeper-notebook/workspace/workspace.test.tsx \
  'src/app/(auth)/login/page.test.tsx' \
  'src/app/(dashboard)/page.test.tsx' \
  'src/app/(dashboard)/setup-wizard/page.test.tsx'
```

Expected: all focused tests pass with no new warnings.

- [ ] **Step 2: Run the full frontend and static gates.**

```bash
cd frontend
npm test -- --run
npm run lint
npx tsc --noEmit
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 npm run build
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 npm run build
npm run test:feature-build-contract
```

Expected: all commands exit zero. Existing warnings may be documented only if they are unchanged from the Task 1 baseline.

- [ ] **Step 3: Enforce Phase 1 performance budgets.**

From clean V2-off and V2-on production builds, record compressed shared JS and CSS totals from `.next`. The V2 build may add no more than 30 KiB gzip shared JavaScript and 20 KiB gzip shared CSS relative to the off build. The browser matrix records no layout-shift entry above `0.05` on `/login`, `/`, or `/setup-wizard`. No new runtime package may appear in `package.json` or the lockfile.

- [ ] **Step 4: Run repository safety gates.**

```bash
cd ..
python3 scripts/rebrand_audit.py --check
git diff --check
git status --short
```

Stage only Phase 1 source, tests, intentional snapshots, and the verification receipt. Then run:

```bash
git diff --cached --check
git diff --cached --binary | gitleaks detect --pipe --no-banner --redact
```

Expected: rebrand unexpected/stale counts are zero, diff checks pass, and no secrets are found.

- [ ] **Step 5: Request fresh-context review.**

Supply the approved specification, this plan, `git diff` from the Phase 1 base, route matrix receipt, build comparison, and tests to a fresh reviewer. Acceptance requires no Critical or Important findings. Repair findings with RED-first focused tests and rerun affected gates.

- [ ] **Step 6: Commit the verified handoff.**

```bash
git add docs/verification/2026-08-13-gemini-forward-phase-1.md
git commit -m "docs(ui): close visual system phase one"
git show --check --oneline --stat HEAD
phase1_base="$(sed -n 's/^Base commit: `\([0-9a-f]\{40\}\)`.*/\1/p' docs/verification/2026-08-13-gemini-forward-phase-1.md | head -1)"
test "${#phase1_base}" -eq 40
gitleaks git --log-opts="${phase1_base}..HEAD" --redact --no-banner
```

The receipt must state that Phase 2 source imagery/cache work has not begun.

---

## Phase 1 Completion Gate

Phase 1 is complete only when all of the following are true:

1. V2 is static, canonical, unset-off, and explicitly reversible.
2. V2 off preserves the current Luminous/legacy flag behavior and request ledger.
3. Existing users retain saved themes; a fresh V2 user receives `gemini-forward-light`.
4. Research Core dark and high-contrast light remain first-class verified themes.
5. Shared primitives own semantic landmarks, state roles, focus, responsive actions, and container sizing.
6. The V2 shell preserves all navigation, commands, utilities, dialogs, focus mode, auth, and audio behavior with one dispatch path each.
7. `/login`, `/`, and `/setup-wizard` use V2 presentation without changing hooks, requests, redirects, storage, or cookies.
8. The checked manifest contains every one of the 22 current `page.tsx` views.
9. All 264 route/theme/viewport base cells pass semantic, geometry, scrolling, request, and console assertions.
10. Loading, empty, populated, processing, degraded, offline, error, unavailable, and feature-off cases are covered where declared by the manifest.
11. Full frontend unit, lint, TypeScript, flag-on/off build, feature-build, browser, rebrand, diff, and secret gates pass.
12. Performance deltas stay within the Phase 1 budgets.
13. Fresh-context review reports no Critical or Important findings.
14. No Phase 2 database, source imagery, local generation, or Artifact Studio work is present.

## Phase Boundary

After this plan is accepted, stop. The next approved plan is Phase 2: notebooks, sources, knowledge, search, capture, Visual Source Gallery, source-derived covers, bounded local fallback generation, `source_visual_cache`, Evidence Peek, media-security review, and real SurrealDB migration proof. Unified Artifact Studio remains Phase 3.
