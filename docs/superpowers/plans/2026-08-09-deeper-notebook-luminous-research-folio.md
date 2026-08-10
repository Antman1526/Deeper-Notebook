# Deeper Notebook Luminous Research Folio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the complete Deeper Notebook application as a breathtaking, notebook-first Luminous Research Folio while preserving every route, feature, command, persisted contract, approval boundary, local-model rule, and external-vault authority rule.

**Architecture:** Build a downstream presentation system in `frontend/src/components/deeper-notebook/`, place it behind a static Next.js feature flag, and migrate surfaces through slot-based wrappers rather than rewriting working feature logic. The current `AppShell` remains the rollback path until every parity, visual, native-runtime, and package gate passes. The backend, database, domain model, route URLs, command IDs, keyboard shortcuts, theme IDs, queue identifiers, and authority contracts do not change.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, CSS custom properties, Zustand, Framer Motion, Lucide, Vitest/Testing Library, Playwright, Python/pytest, Ruff, PyInstaller, macOS `codesign`, `hdiutil`, and the existing SurrealDB-backed native runtime.

## Global Constraints

- Work from the repository root returned by `git rev-parse --show-toplevel`, require its basename to be `Deeper-Notebook`, and verify the active checkout before every phase.
- Read `/Users/Antman/.codex/context.md`, this plan, and `docs/superpowers/specs/2026-08-09-deeper-notebook-luminous-research-folio-design.md` before editing.
- Preserve unrelated dirty and untracked files. Never reset, overwrite, or sweep them into a redesign commit.
- Do not edit `frontend/src/components/ui/*` or `frontend/src/components/settings/*`.
- Keep page-file deltas surgical: import replacement, wrapper insertion, or class/slot connection only. Put new presentation logic under `frontend/src/components/deeper-notebook/`.
- Do not change route URLs, API payloads, database schemas, queue identifiers, command IDs, keyboard shortcuts, stored theme IDs, authentication behavior, or launch behavior.
- Do not trigger a scan, mount, import, podcast generation, publication, cloud request, or write by opening a redesigned surface.
- Keep Obsidian and Logseq mounts `external_read_only`; no UI event may write to their roots.
- Evidence receipts remain informational. Approval and outbound-URL validation remain mandatory and separate.
- Podcast creation remains optional and retains the review-then-confirm boundary.
- Aurora motion is confined to negative space, disabled for reduced motion, and independently switchable off.
- Every task starts with a failing focused test, implements the smallest passing change, reruns focused gates, and commits independently.
- Do not update snapshots merely because they changed. Inspect every candidate render at full size first.
- Keep `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` disabled by default until Task 15.
- Record exact commands, counts, failures, screenshots, revision, and environment in `docs/verification/2026-08-09-luminous-research-folio.md` as work progresses.

---

## Specification Traceability

| Approved specification area | Implementation tasks | Release proof |
|---|---:|---|
| Visual system, materials, typography, spacing, iconography | 2–3 | 13–14 |
| Instrument Dock, Command Bar, Adaptive Navigator, Canvas, Context Lens | 1, 4 | 13–16 |
| Intelligence Horizon | 6 | 13–16 |
| Research Core, graph atlas, evidence context | 7–8 | 13–16 |
| Evidence and Podcast Intelligence Studios | 9–10 | 13–16 |
| Complete route and feature preservation | 1, 4, 6–12 | 13, 15–16 |
| Themes and display preferences | 2, 5 | 13–16 |
| Interaction, Aurora motion, and guided tips | 2, 4–5 | 13–14, 16 |
| Loading, empty, error, offline, permission, read-only states | 3, 6–12 | 13–14 |
| Responsive architecture and accessibility | 3–5, 7–12 | 13–14, 16 |
| Performance requirements | 2, 4 | 13–14, 16 |
| Phased rollout, rollback, and feature flag | 1, 4, 15 | 16 |
| Native authority, no-write, packaging, and installation | 10, 16 | 16 |

The alternatives and decision rationale remain in the approved specification;
this plan implements only the selected Luminous Research Folio direction.

---

## File Structure Map

### Existing integration points

- `frontend/src/app/layout.tsx` — fonts, pre-hydration theme/display script, global providers.
- `frontend/src/app/globals.css` — global semantic theme variables and accessibility rules.
- `frontend/src/app/(dashboard)/layout.tsx` — create-dialog provider and command palette.
- `frontend/src/components/layout/AppShell.tsx` — one reversible switch between legacy and Luminous shells.
- `frontend/src/components/layout/AppSidebar.tsx` — existing navigation/create/account behavior retained as fallback.
- `frontend/src/components/deeper-notebook/tokens.css` — semantic Folio, aurora, material, and motion tokens.
- `frontend/src/components/vault/KnowledgeExplorer.tsx` — Research Core orchestration; visual framing only.
- `frontend/src/components/podcasts/PodcastStudio.tsx` — Podcast Studio orchestration; visual framing only.
- `frontend/src/app/(dashboard)/page.tsx` and `studio/page.tsx` — flagship entry points; logic remains intact.
- `frontend/src/lib/features.ts` — static client-safe feature flag contract.
- `frontend/src/lib/theme-script.ts` — pre-hydration theme and display attributes.
- `frontend/src/lib/stores/guided-tips-store.ts` — existing optional onboarding contract.
- `frontend/e2e/*` — browser parity, authority, and render proof.

### Route parity inventory

| Entry point | Redesign owner |
|---|---|
| `/` | Preserve the existing redirect contract in Task 12 |
| `/login` | Auth Folio in Task 12 |
| `/` dashboard | Intelligence Horizon in Task 6 |
| `/sources`, `/sources/[id]`, `/capture` | Collect family in Task 11 |
| `/notebooks`, `/notebooks/[id]`, `/search`, `/study` | Organize/Discover families in Task 11 |
| `/knowledge` | Research Core Folio in Tasks 7–8 |
| `/studio` | Evidence Studio Folio in Task 9 |
| `/podcasts`, `/podcasts/studio` | Podcast library/Studio in Tasks 10 and 12 |
| `/transformations` | Create/Manage family in Task 12 |
| `/settings`, `/settings/api-keys`, `/settings/local-models` | Settings/Models family in Tasks 5 and 12 |
| `/settings/mcp`, `/settings/launcher-prefs` | Integrations/Launcher family in Task 12 |
| `/advanced`, `/setup-wizard` | Advanced/Setup family in Task 12 |

This inventory contains all 22 current `page.tsx` entry points, counting the
root redirect and dashboard root as separate files even though both display as
`/` under their respective route-group behavior.

### New downstream modules

```text
frontend/src/components/deeper-notebook/
├── folio/
│   ├── FolioPage.tsx
│   ├── FolioSpread.tsx
│   ├── FolioIndex.tsx
│   ├── FolioTab.tsx
│   ├── MarginNote.tsx
│   ├── EvidenceInsert.tsx
│   ├── FolioState.tsx
│   ├── FolioRouteFrame.tsx
│   ├── folio.css
│   └── folio.test.tsx
├── shell/
│   ├── LuminousAppShell.tsx
│   ├── InstrumentDock.tsx
│   ├── CommandBar.tsx
│   ├── AdaptiveNavigator.tsx
│   ├── ContextLens.tsx
│   ├── AuroraCartography.tsx
│   ├── ShellUtilities.tsx
│   ├── shell.css
│   └── shell.test.tsx
├── horizon/
│   ├── IntelligenceHorizon.tsx
│   └── IntelligenceHorizon.test.tsx
├── studios/
│   ├── EvidenceStudioFolio.tsx
│   ├── PodcastStudioFolio.tsx
│   └── studios.test.tsx
└── index.ts

frontend/src/lib/stores/display-preferences-store.ts
frontend/src/lib/stores/display-preferences-store.test.ts
frontend/e2e/fixtures/luminous-folio.ts
frontend/e2e/luminous-folio-visual.spec.ts
frontend/e2e/luminous-folio-parity.spec.ts
docs/verification/2026-08-09-luminous-research-folio.md
```

---

## Task 1: Freeze the Feature and Navigation Parity Contract

**Files:**

- Modify: `frontend/src/lib/features.ts`
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features-build-contract.test.ts`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Create: `frontend/src/components/deeper-notebook/shell/navigation-contract.test.tsx`
- Create: `docs/verification/2026-08-09-luminous-research-folio.md`

**Interfaces:**

- Consumes: current sidebar sections, hrefs, translations, icons, create targets, and static environment-variable access.
- Produces: `isLuminousFolioEnabled(): boolean`, exported `getNavigation(t)`, exported `CreateTarget`, and a frozen parity receipt.

- [ ] Add RED tests asserting the new feature flag defaults off, reads the canonical static environment key, and does not alter any existing feature flag. Do not invent a new legacy alias for a new feature.

```ts
expect(isLuminousFolioEnabled()).toBe(false)
process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = 'enabled'
expect(isLuminousFolioEnabled()).toBe(true)
expect(source).toContain('process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO')
expect(source).not.toMatch(/process\.env\s*\[/)
```

- [ ] Add a RED navigation contract test that calls `getNavigation(t)` and asserts this exact href order:

```ts
expect(sections.flatMap(section => section.items.map(item => item.href))).toEqual([
  '/sources', '/capture', '/notebooks', '/knowledge', '/search',
  '/studio', '/podcasts', '/study', '/settings/api-keys',
  '/transformations', '/settings', '/settings/mcp',
  '/settings/launcher-prefs', '/advanced',
])
expect(CREATE_TARGETS).toEqual(['source', 'notebook', 'podcast'])
```

- [ ] Run RED:

```bash
cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx
```

Expected: failures for the missing flag and non-exported navigation contract only.

- [ ] Implement the static flag and export existing navigation without changing its values:

```ts
export function isLuminousFolioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO,
    undefined,
    false,
  )
}
```

```ts
export const CREATE_TARGETS = ['source', 'notebook', 'podcast'] as const
export type CreateTarget = (typeof CREATE_TARGETS)[number]
export const getNavigation = (t: TFunction) => [/* existing entries unchanged */] as const
```

- [ ] Write the verification receipt header with baseline revision, dirty-file inventory, current route list, current theme IDs, and the rule that baseline failures are recorded rather than repaired opportunistically.
- [ ] Run GREEN, `npm run test:feature-build-contract`, and `git diff --check`.
- [ ] Commit: `test(ui): freeze luminous folio parity contracts`.

---

## Task 2: Add Display Preferences, Typography, and Pre-Hydration State

**Files:**

- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/lib/theme-script.ts`
- Modify: `frontend/src/lib/theme-script.test.ts`
- Create: `frontend/src/lib/stores/display-preferences-store.ts`
- Create: `frontend/src/lib/stores/display-preferences-store.test.ts`
- Modify: `frontend/src/components/deeper-notebook/tokens.css`

**Interfaces:**

- Consumes: `dn-theme`, `theme-storage`, system dark mode, `prefers-reduced-motion`.
- Produces: `data-dn-wallpaper`, `data-dn-motion`, `data-dn-transparency`, `--font-dn-sans`, `--font-dn-editorial`, and persisted `dn-display-preferences-v1`.

- [ ] Add RED store tests for defaults, persisted updates, and `reset()`:

```ts
expect(useDisplayPreferencesStore.getState()).toMatchObject({
  wallpaper: 'aurora', motion: 'system', transparency: 'frosted',
})
useDisplayPreferencesStore.getState().setWallpaper('off')
expect(useDisplayPreferencesStore.getState().wallpaper).toBe('off')
```

- [ ] Add RED pre-hydration tests asserting malformed storage fails closed and reduced-motion/system preferences become stable root attributes before React hydrates.
- [ ] Run RED:

```bash
cd frontend && npm exec vitest run src/lib/theme-script.test.ts src/lib/stores/display-preferences-store.test.ts
```

- [ ] Implement the store with exact public types:

```ts
export type WallpaperPreference = 'aurora' | 'static' | 'off'
export type MotionPreference = 'system' | 'full' | 'reduced'
export type TransparencyPreference = 'frosted' | 'solid'

export interface DisplayPreferencesState {
  wallpaper: WallpaperPreference
  motion: MotionPreference
  transparency: TransparencyPreference
  setWallpaper(value: WallpaperPreference): void
  setMotion(value: MotionPreference): void
  setTransparency(value: TransparencyPreference): void
  reset(): void
}
```

- [ ] Extend `themeScript` to parse only the three allowlisted enum values and set attributes; on error use `aurora/system/frosted` without deleting legacy theme storage.
- [ ] Configure self-hosted Next fonts:

```ts
const inter = Inter({ subsets: ['latin'], variable: '--font-dn-sans' })
const newsreader = Newsreader({ subsets: ['latin'], variable: '--font-dn-editorial' })
<body className={`${inter.variable} ${newsreader.variable} font-sans`}>
```

- [ ] Correct global font tokens to use `--font-dn-sans`; use `--font-dn-editorial` only for folio titles, quotations, and editorial summaries, never dense controls or source text.
- [ ] Add semantic color, folio paper, brass, glow, grain, shell, lens, and motion tokens. Remove the duplicate `animation: dn-aurora-drift` declaration while preserving its timing.
- [ ] Add CSS guards for `prefers-reduced-motion`, `data-dn-motion="reduced"`, `data-dn-wallpaper="off"`, and `data-dn-transparency="solid"`.
- [ ] Run GREEN, full theme/provider tests, build, and diff check.
- [ ] Commit: `feat(ui): add luminous display preferences and typography`.

---

## Task 3: Build the Notebook Primitive Library

**Files:**

- Create all `frontend/src/components/deeper-notebook/folio/*` files listed in the structure map.
- Modify: `frontend/src/components/deeper-notebook/index.ts`
- Modify: `frontend/src/components/deeper-notebook/README.md`

**Interfaces:**

- Consumes: semantic shadcn and `--dn-*` tokens only.
- Produces: composable notebook layout primitives with stable landmark semantics and no data fetching.

- [ ] Write RED accessibility/composition tests covering one `main` landmark, heading association, optional margin, controlled tab selection, empty/loading/error states, and evidence receipt placement outside labels.
- [ ] Define complete public props before implementation:

```ts
export interface FolioPageProps extends React.HTMLAttributes<HTMLElement> {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  margin?: React.ReactNode
  children: React.ReactNode
  as?: 'main' | 'section' | 'article'
}

export interface FolioSpreadProps extends React.HTMLAttributes<HTMLDivElement> {
  primary: React.ReactNode
  secondary?: React.ReactNode
  secondaryLabel?: string
}

export interface FolioTabItem { id: string; label: string; badge?: React.ReactNode }
export interface FolioIndexProps {
  label: string
  items: readonly FolioTabItem[]
  value: string
  onValueChange(value: string): void
}

export interface FolioStateProps {
  kind: 'loading' | 'empty' | 'error' | 'offline' | 'permission'
  title: string
  description: string
  action?: React.ReactNode
}

export interface FolioRouteFrameProps {
  section: string
  title: string
  description?: string
  actions?: React.ReactNode
  context?: React.ReactNode
  children: React.ReactNode
}
```

- [ ] Run RED:

```bash
cd frontend && npm exec vitest run src/components/deeper-notebook/folio/folio.test.tsx
```

- [ ] Implement semantic HTML, `forwardRef`, keyboard-operable tabs, CSS logical properties, 44px touch targets, and `data-dn-folio-*` selectors. Do not add fetches, stores, dialogs, or route knowledge.
- [ ] Export every primitive from the downstream barrel and document when to use page/spread/index/margin/evidence/state.
- [ ] Run GREEN, lint scoped files, TypeScript, and diff check.
- [ ] Commit: `feat(ui): add living folio primitives`.

---

## Task 4: Build the Reversible Luminous Application Shell

**Files:**

- Create all `frontend/src/components/deeper-notebook/shell/*` files except the navigation contract already created.
- Modify: `frontend/src/components/deeper-notebook/index.ts`
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/AppShell.test.tsx`

**Interfaces:**

- Consumes: exported sidebar navigation, `useCreateDialogs`, `useAuth`, `useIsDesktop`, `ThemeSwitcher`, `LanguageToggle`, `GmailSidebarButton`, `LocalModelHealthBadges`, desktop version, current pathname, and display preferences.
- Produces: dock, contextual navigation, command bar, context lens, aurora canvas, mobile bottom navigation, and the exact current shell utilities.

- [ ] Write RED shell tests proving:

```ts
expect(screen.getByRole('navigation', { name: 'Primary tools' })).toBeVisible()
expect(screen.getByRole('navigation', { name: 'Notebook index' })).toBeVisible()
expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
expect(screen.getByText('Deeper Notebook')).toBeVisible()
expect(screen.getByTestId('global-audio-player')).toBeInTheDocument()
```

Also assert all 14 routes, Source/Notebook/Podcast create actions, theme, language, Gmail, sign out, local-model health, desktop version, command shortcut, four banners, guided tips, and exactly one page-content slot.

- [ ] Run RED; expect missing shell components.
- [ ] Implement `LuminousAppShell` with this composition contract:

```tsx
export function LuminousAppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="dn-luminous-shell">
      <AuroraCartography />
      <InstrumentDock />
      <div className="dn-luminous-workspace">
        <CommandBar />
        <AdaptiveNavigator />
        <section className="dn-editorial-canvas">{children}</section>
        <ContextLens />
      </div>
      <ShellUtilities />
    </div>
  )
}
```

- [ ] `ShellUtilities` must compose the existing four banners, `GuidedTipsProvider`, and `GlobalAudioPlayer`; it must not duplicate their logic.
- [ ] Preserve `data-guided-tip-anchor` values, active-route exact/child matching, `onp-sidebar-active` compatibility identifier where required by the old shell, and current create handlers.
- [ ] Mobile: transform dock into a bottom tool row, navigator into an accessible sheet/drawer, and context lens into an on-demand overlay. Desktop: dock 64–72px, navigator 240–304px, lens 280–360px.
- [ ] Modify `AppShell` only as a switch:

```tsx
export function AppShell({ children }: AppShellProps) {
  return isLuminousFolioEnabled()
    ? <LuminousAppShell>{children}</LuminousAppShell>
    : <LegacyAppShell>{children}</LegacyAppShell>
}
```

Keep the current implementation intact in a private `LegacyAppShell` in the same file.
- [ ] Run shell tests with flag off and on, existing `AppSidebar.test.tsx`, all banner tests, guided-tip tests, command-palette tests, and build-contract test.
- [ ] Commit: `feat(ui): add reversible luminous application shell`.

---

## Task 5: Integrate Settings Controls and Guided Orientation

**Files:**

- Create: `frontend/src/components/deeper-notebook/DisplayPreferencesPanel.tsx`
- Create: `frontend/src/components/deeper-notebook/DisplayPreferencesPanel.test.tsx`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`
- Modify: `frontend/src/lib/guided-tips/catalog.ts`
- Modify: guided-tip catalog/provider tests.

**Interfaces:**

- Consumes: display preference store and existing guided-tip enable/replay actions.
- Produces: independent Wallpaper, Motion, Transparency controls and versioned shell/folio guidance.

- [ ] Write RED tests asserting every control is labeled, keyboard operable, immediately updates the root attribute, persists, and leaves theme selection unchanged.
- [ ] Implement `DisplayPreferencesPanel` as a downstream component. The settings page change is one import plus one component insertion; do not edit settings primitives.
- [ ] Add versioned tips for Instrument Dock, Notebook Index, Context Lens, Evidence Inserts, and Podcast production review. Tips remain non-modal, dismissible, globally disableable, replayable, and suspended under dialogs.
- [ ] Ensure changing a preference never opens a dialog or initiates a network request.
- [ ] Run focused settings, theme, and guided-tip suites; commit: `feat(ui): add folio display and guidance controls`.

---

## Task 6: Migrate the Intelligence Horizon Dashboard Pilot

**Files:**

- Create: `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.tsx`
- Create: `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.test.tsx`
- Modify: `frontend/src/app/(dashboard)/page.tsx`
- Modify: `frontend/src/app/(dashboard)/page.test.tsx`

**Interfaces:**

- Consumes: current dashboard notebook data, ready status, recent items, quick actions, loading/empty states, create-dialog actions, and data-path copy.
- Produces: notebook-cover welcome, Today spread, Recent folios, Trust/model status margin, and unchanged actions.

- [ ] Write RED tests that render fixture props and assert the exact existing quick actions: Studio, New Notebook, Podcast, Ask; recent notebook links; ready/offline states; command hint; and no action on mount.
- [ ] Define the pure view model:

```ts
export interface IntelligenceHorizonProps {
  status: 'loading' | 'ready' | 'offline'
  recentNotebooks: readonly HorizonNotebook[]
  onOpenStudio(): void
  onCreateNotebook(): void
  onCreatePodcast(): void
  onAsk(): void
  dataPath?: string
}
```

- [ ] Move presentation only into `IntelligenceHorizon`; keep hooks, navigation, and dialog wiring in the page. Replace the page JSX with one component call.
- [ ] Use Folio primitives and semantic states; no card-grid clone. The first viewport must read as a notebook cover opening into a working spread.
- [ ] Run dashboard tests under both shell flags and commit: `feat(ui): redesign intelligence horizon`.

---

## Task 7: Frame Research Core as a Living Knowledge Folio

**Files:**

- Create: `frontend/src/components/deeper-notebook/ResearchCoreFolioFrame.tsx`
- Create: `frontend/src/components/deeper-notebook/ResearchCoreFolioFrame.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx`
- Modify: `frontend/src/components/vault/ResearchCoreHeader.tsx`
- Modify: `frontend/src/components/vault/vault.css`
- Modify: `frontend/src/components/vault/ResearchCoreVisualSystem.test.tsx`

**Interfaces:**

- Consumes: existing Research Core header, recursive split layout, file tree, tab strip, utility rail, intelligence rail, overlays, drawers, resizers, and authority markers.
- Produces: folio index/tree, editorial work surface, evidence margin, atlas-ready graph presentation, and unchanged workspace state.

- [ ] Extend existing RED integration assertions to require a folio frame, one main landmark, visible authority/read-only cues, and the same open tabs/workspace behavior.
- [ ] Implement `ResearchCoreFolioFrame` as slots:

```ts
export interface ResearchCoreFolioFrameProps {
  header: React.ReactNode
  index: React.ReactNode
  workspace: React.ReactNode
  lens?: React.ReactNode
  overlays?: React.ReactNode
}
```

- [ ] Wrap existing regions without moving state ownership or changing callback signatures. Preserve `data-testid="knowledge-workspace"`, resizer semantics, focus restoration, tab persistence, bookmarks, workspaces, search, commands, and drawers.
- [ ] Style app-owned/editable versus external/read-only content with text plus icon/state—not color alone.
- [ ] Run `KnowledgeExplorer`, workspace, tab-strip, utility-rail, intelligence-rail, bookmarks, workspaces, mode-pane, and visual-system tests.
- [ ] Commit: `feat(ui): frame research core as a living folio`.

---

## Task 8: Elevate the Graph Atlas and Evidence Context Lens

**Files:**

- Create: `frontend/src/components/deeper-notebook/GraphAtlasFrame.tsx`
- Create: `frontend/src/components/deeper-notebook/GraphAtlasFrame.test.tsx`
- Modify: `frontend/src/components/vault/VaultGraph.tsx`
- Modify: `frontend/src/components/vault/KnowledgeIntelligenceRail.tsx`
- Modify: `frontend/src/components/research/EvidenceReceipt.tsx`
- Modify corresponding tests.

**Interfaces:**

- Consumes: existing graph selection, backlinks, node actions, podcast handoff, evidence receipt, freshness, hashes, source navigation, and authority.
- Produces: atlas foldout framing and evidence-insert hierarchy; no graph algorithm or evidence contract change.

- [ ] Add RED tests asserting graph selection/actions and receipt fields are unchanged while atlas/lens landmarks and accessible labels exist.
- [ ] Implement a pure frame around the graph canvas, legend, filters, and selection inspector. Keep XYFlow state and callbacks in `VaultGraph`.
- [ ] Restyle `EvidenceReceipt` as a compact evidence insert while retaining provider, retrieval time, freshness, fingerprint, full accessible values, null-safe legacy behavior, and separation from approval controls.
- [ ] Run VaultGraph, intelligence rail, EvidenceReceipt, SourceApprovalPanel, and research-evidence browser tests.
- [ ] Commit: `feat(ui): add graph atlas and evidence lens`.

---

## Task 9: Redesign Evidence Studio as an Intelligence Folio

**Files:**

- Create: `frontend/src/components/deeper-notebook/studios/EvidenceStudioFolio.tsx`
- Modify: `frontend/src/components/deeper-notebook/studios/studios.test.tsx`
- Modify: `frontend/src/app/(dashboard)/studio/page.tsx`
- Modify existing Studio tests.

**Interfaces:**

- Consumes: current upload/input controls, mode choices, source health, artifact rail, citations, run timeline, revision/export actions, study/visual viewers, and all existing event handlers.
- Produces: Source Desk, Editorial Brief, Artifact Pages, and Trust Margin slots.

- [ ] Write RED slot tests and page tests asserting upload/input, mode selection, generate controls, artifact actions, citations, exports, revision controls, and no request on mount.
- [ ] Define a view-only slot API:

```ts
export interface EvidenceStudioFolioProps {
  sourceDesk: React.ReactNode
  editorialBrief: React.ReactNode
  artifactPages: React.ReactNode
  trustMargin?: React.ReactNode
  status?: React.ReactNode
}
```

- [ ] Replace only the page’s top-level layout grid with `EvidenceStudioFolio`; do not move hooks, mutations, request payloads, or artifact state.
- [ ] Keep all generate actions explicit and disabled states legible in every theme.
- [ ] Run Studio, ArtifactRail, viewers, export, citations, and run-timeline suites.
- [ ] Commit: `feat(ui): redesign evidence studio folio`.

---

## Task 10: Redesign Podcast Intelligence Studio as a Production Folio

**Files:**

- Create: `frontend/src/components/deeper-notebook/studios/PodcastStudioFolio.tsx`
- Modify: `frontend/src/components/deeper-notebook/studios/studios.test.tsx`
- Modify: `frontend/src/components/podcasts/PodcastStudio.tsx`
- Modify: `frontend/src/components/podcasts/PodcastStudio.test.tsx`
- Modify: `frontend/src/app/(dashboard)/podcasts/studio/page.tsx` only if one wrapper import is needed.

**Interfaces:**

- Consumes: Research Set, Editorial Brief, Outline Storyboard, Model Plan, Production Timeline, Review, profiles, transcripts, audio, retry, cancel, and close-without-producing behavior.
- Produces: production folio spread with source dossier, script pages, cast/model margin, and explicit production gate.

- [ ] Add RED tests proving opening and closing Studio produces nothing, review remains before confirm, all selected source IDs survive, cancel/retry remain explicit, and local/cloud route labels remain visible.
- [ ] Implement the slot API:

```ts
export interface PodcastStudioFolioProps {
  researchSet: React.ReactNode
  editorialBrief: React.ReactNode
  storyboard: React.ReactNode
  modelPlan: React.ReactNode
  production: React.ReactNode
  review: React.ReactNode
}
```

- [ ] Replace the current four-column layout wrapper only. Preserve panel props, ordering constraints, mutations, and aria names.
- [ ] Run the full podcast component suite and native `podcast-intelligence-studio.spec.ts`; verify zero external-vault writes and zero generation on open.
- [ ] Commit: `feat(ui): redesign podcast production folio`.

---

## Task 11: Migrate Collect, Organize, and Discover Route Families

**Files:**

- Modify page entry points for `/sources`, `/sources/[id]`, `/capture`, `/notebooks`, `/notebooks/[id]`, `/search`, and `/study`.
- Create: `frontend/src/components/deeper-notebook/route-frames/KnowledgeRouteFrames.tsx`
- Create: `frontend/src/components/deeper-notebook/route-frames/KnowledgeRouteFrames.test.tsx`
- Modify corresponding page/component tests.

**Interfaces:**

- Consumes: each route’s existing page body and actions.
- Produces: consistent FolioRouteFrame metadata and context slots.

- [ ] Start with a RED table-driven test for the exact route-to-folio mapping:

```ts
const routes = [
  ['/sources', 'Sources'], ['/capture', 'Capture'],
  ['/notebooks', 'Notebooks'], ['/search', 'Ask & Search'], ['/study', 'Study'],
] as const
```

- [ ] Implement route-specific downstream wrappers; pages may only swap one import or wrap their existing returned body.
- [ ] Preserve creation/import dialogs, pagination, filters, search parameters, note editing, autosave, delete confirmations, source details, podcast handoffs, and study actions.
- [ ] Run every touched page test plus mocked browser navigation/command tests.
- [ ] Commit route families separately if the diff exceeds 800 changed lines:
  - `feat(ui): migrate collect routes to folio`
  - `feat(ui): migrate organize and discover routes to folio`

---

## Task 12: Migrate Create, Manage, Setup, Auth, and Advanced Route Families

**Files:**

- Modify page entry points for `/podcasts`, `/transformations`, `/settings`, `/settings/api-keys`, `/settings/local-models`, `/settings/mcp`, `/settings/launcher-prefs`, `/advanced`, `/setup-wizard`, and `/login`.
- Create: `frontend/src/components/deeper-notebook/route-frames/SystemRouteFrames.tsx`
- Create: `frontend/src/components/deeper-notebook/route-frames/SystemRouteFrames.test.tsx`
- Create: `frontend/src/components/deeper-notebook/AuthFolio.tsx`
- Create: `frontend/src/components/deeper-notebook/AuthFolio.test.tsx`
- Modify corresponding page/component tests.

**Interfaces:**

- Consumes: existing forms, model inventory, API keys, MCP, launcher preferences, transformations, setup steps, podcast episodes/templates, and advanced tools.
- Produces: system ledger, model roster, transformation index, setup folio, authentication cover, and podcast library frames.

- [ ] Add RED table-driven route framing tests and interaction smoke tests for every existing save, test, delete, create, install, and navigation control.
- [ ] Apply downstream wrappers only. Do not edit settings primitives or change request payloads/secrets handling.
- [ ] Wrap the existing login form in `AuthFolio` without changing validation, authentication calls, redirect behavior, error copy, password semantics, or the root route's redirect contract.
- [ ] Ensure dense settings use solid, low-motion surfaces even when Aurora/frosted glass is enabled.
- [ ] Run all touched page tests, model/MCP/launcher tests, setup tests, and podcast list tests.
- [ ] Commit by route family when necessary to retain reviewable diffs.

---

## Task 13: Prove Responsive, Accessibility, Theme, and Performance Resilience

**Files:**

- Create: `frontend/src/components/deeper-notebook/luminous-accessibility.test.tsx`
- Modify: `frontend/src/lib/themes/catalog.test.ts`
- Modify: `frontend/src/components/vault/ResearchCoreVisualSystem.test.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/deeper-notebook/tokens.css`
- Create: `frontend/e2e/luminous-folio-parity.spec.ts`

**Interfaces:**

- Consumes: all shell, folio, theme, motion, keyboard, and viewport behaviors.
- Produces: deterministic accessibility/responsive contract.

- [ ] Add RED tests for one main landmark, heading order, focus-visible state, 44px targets, non-color authority signals, no invalid label nesting, static reduced-motion rendering, and solid-transparency fallback.
- [ ] Add a pure contrast helper in the test file and assert key Research Core, Archive Paper, and high-contrast token pairs meet WCAG AA: 4.5:1 normal text and 3:1 large text/controls.
- [ ] Add Playwright cases at 390×844, 768×1024, 1280×800, and 1440×900 proving dock/nav/lens transformations without horizontal document overflow.
- [ ] Add keyboard-only traversal: skip link, dock, navigator, command palette, page actions, context lens, and return focus.
- [ ] Measure browser performance with an injected observer. Acceptance:
  - no long task over 200ms caused by Aurora after steady state;
  - animation changes only transform/opacity/filter;
  - no continuously animating layer exists under editor/source/transcript text;
  - zero console errors/hydration warnings.
- [ ] Run unit, lint, TypeScript, build, and mocked parity E2E.
- [ ] Commit: `test(ui): prove luminous folio resilience`.

---

## Task 14: Create and Review the Deterministic Visual Render Matrix

**Files:**

- Create: `frontend/e2e/fixtures/luminous-folio.ts`
- Create: `frontend/e2e/luminous-folio-visual.spec.ts`
- Create snapshot directories produced by Playwright only after review.
- Modify: `frontend/package.json`
- Update: `docs/verification/2026-08-09-luminous-research-folio.md`

**Interfaces:**

- Consumes: deterministic mocked data and every required theme/viewport/state.
- Produces: reviewed screenshots for shell, dashboard, Research Core, Evidence Studio, Podcast Studio, states, and responsive modes.

- [ ] Add a script:

```json
"test:e2e:folio-visuals": "playwright test e2e/luminous-folio-visual.spec.ts --project=mocked-browser"
```

- [ ] Build deterministic fixture helpers that disable guided tips, time variation, intro animation, and network variability while leaving the redesigned shell enabled.
- [ ] Capture this minimum matrix:
  - Research Core Dark and Light: shell, Horizon, Research Core, Evidence Studio, Podcast Studio at 1440×900.
  - Archive Paper and Deep Ocean: Horizon and Research Core at 1280×800.
  - High Contrast Dark and Light: shell plus focused/disabled/error states at 1440×900.
  - Research Core Dark: mobile Horizon, mobile Research Core, reduced motion, wallpaper off, solid transparency.
  - loading, empty, offline, error, permission, external-read-only, evidence receipt, and podcast review states.
- [ ] Run once without updating snapshots; inspect actual screenshots at original resolution. Record issues by surface/severity.
- [ ] Fix source styles, rerun focused tests, then generate candidate snapshots with `--update-snapshots`.
- [ ] Inspect every changed candidate against the approved spec. Reject clipping, accidental gradients, illegible glass, card-grid regression, generic hero copy, excessive pills, and notebook decoration without function.
- [ ] Commit only reviewed snapshots: `test(ui): add luminous folio visual proofs`.

---

## Task 15: Enable the Redesign by Default After Full Parity

**Files:**

- Modify: `frontend/src/lib/features.ts`
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/components/layout/AppShell.test.tsx`
- Update: verification receipt.

**Interfaces:**

- Consumes: all prior green gates and approved render matrix.
- Produces: Luminous Folio default-on with explicit environment rollback.

- [ ] Change only the default argument:

```ts
export function isLuminousFolioEnabled(): boolean {
  return envFlag(
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO,
    undefined,
    true,
  )
}
```

- [ ] Prove `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` renders the full legacy shell and `=1` renders the full new shell.
- [ ] Run exact route/navigation/create/theme/command/audio/banner/guided-tip parity tests in both modes.
- [ ] Keep fallback code for one release cycle; removal requires a separate approved migration.
- [ ] Commit: `feat(ui): enable luminous research folio`.

---

## Task 16: Full Regression, Native Authority, DMG, and Installed-App Proof

**Files:**

- Update: `docs/verification/2026-08-09-luminous-research-folio.md`
- Modify code only for defects found by these gates, each with a RED regression test and separate focused commit.

**Interfaces:**

- Consumes: the complete redesign revision.
- Produces: release-candidate evidence tied to one immutable commit and a rollback statement.

- [ ] Ensure the worktree contains only intentional redesign files plus preserved user-owned files. Run `git diff --check` and the rebrand audit; classify pre-existing reconstruction-doc audit findings separately rather than hiding them.
- [ ] Run backend and desktop gates:

```bash
uv run pytest -q
uv run ruff check .
.build-venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q
```

- [ ] Run frontend gates:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
npm run test:feature-build-contract
npm run test:e2e:mocked
npm run test:e2e:themes
npm run test:e2e:folio-visuals
```

- [ ] Start a persistent disposable SurrealDB/API/worker runtime rooted outside protected user data. Bind the proof to the exact Git revision. Run native Research Core, evidence receipt, Podcast Studio, and parity suites. Stop and remove only task-owned services/data afterward.
- [ ] Mount controlled fixture Obsidian and Logseq vaults as `external_read_only`; watchers begin disabled. Hash every source file before and after scan, search, backlinks, graph, child scan, idempotent rescan, and podcast-source selection. Require identical hashes and zero external mutation requests.
- [ ] Prove no podcast job is created by opening/closing Studio and that production occurs only after explicit review and confirmation.
- [ ] Build the release artifact with the stable local signing identity when available:

```bash
make build-mac DEEPER_NOTEBOOK_CODESIGN_IDENTITY="Deeper Notebook Local"
codesign --verify --deep --strict "dist/Deeper Notebook.app"
hdiutil verify "dist/Deeper-Notebook-mac-$(uname -m).dmg"
```

If no stable identity exists, use the documented ad-hoc path and label it explicitly as not notarized/Gatekeeper distribution proof.
- [ ] Back up the currently installed `/Applications/Deeper Notebook.app`, install with `make build-mac-install`, launch the installed app, and verify:
  - exact installed bundle path and version;
  - `/readyz` and frontend readiness;
  - Luminous shell, Horizon, Research Core, Evidence Studio, Podcast Studio;
  - theme/display persistence across restart;
  - local-model health visibility;
  - external-vault read-only behavior;
  - clean close with no orphan task-owned processes.
- [ ] Record the backup path and tested rollback command. Do not delete the prior app until the user accepts the installed build.
- [ ] Run a fresh Sol review of the actual diff, tests, snapshots, native proof, package receipt, and authority hashes. Address every high/medium finding with RED tests or explicitly block release.
- [ ] Commit final receipts: `docs: close luminous folio release proof`.

---

## Final Acceptance Checklist

- [ ] Every existing route remains reachable by navigation and command palette.
- [ ] Every existing create, edit, search, graph, study, transform, podcast, model, settings, setup, and advanced workflow retains its behavior.
- [ ] App-owned knowledge remains editable; external Obsidian/Logseq knowledge remains read-only.
- [ ] Evidence receipts never grant approval or bypass URL validation.
- [ ] Podcast creation remains optional and review-gated.
- [ ] Guided tips, wallpaper, motion, transparency, theme, and shell rollback are independently controllable.
- [ ] The first viewport is unmistakably a premium living notebook, not a generic AI dashboard.
- [ ] Aurora is beautiful in negative space and absent behind dense reading/editing content.
- [ ] Research Core, Evidence Studio, and Podcast Studio feel like one product while retaining specialized information architecture.
- [ ] All unit, lint, TypeScript, build, mocked-browser, theme, visual, native, authority, desktop, DMG, and installed-app gates pass at one revision.
- [ ] Human visual review explicitly approves the final render matrix.
- [ ] The verification receipt distinguishes passing code gates, native runtime proof, package integrity, installed-app proof, signing identity, and notarization status.

## Rollback

1. Before Task 15, omit `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` or set it to `0` to use the legacy shell.
2. After Task 15, set `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`, rebuild, and rerun the feature-build contract to restore the legacy presentation without data migration.
3. If the installed app fails, quit it, restore the recorded `/Applications/Deeper Notebook.app` backup, and relaunch. Do not touch the user data directory or external vaults.
4. Never use a database rollback for this visual redesign; no database migration is authorized by this plan.

## Done Definition

The redesign is complete only when the Luminous Research Folio is default-on, the legacy shell remains a proven one-release-cycle fallback, every behavioral and safety contract passes, every required deterministic render has been inspected and approved, a revision-bound native no-write proof is green, the DMG verifies, and the installed `/Applications/Deeper Notebook.app` passes a real launch/restart/close smoke test. A passing unit suite, build, screenshot, or local browser preview alone is not completion.
