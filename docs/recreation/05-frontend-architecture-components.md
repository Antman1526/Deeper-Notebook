# 05 — Frontend Architecture & Components

> Next.js 16.2.12 (App Router) · React 19.2.3 · TypeScript 5 · Tailwind CSS 4
> **693 TS/TSX files**, ~125k LOC. Built to `standalone` output for desktop packaging.

---

## 1. Stack decisions

| Concern | Choice | Why |
|---|---|---|
| Framework | Next.js App Router | Standalone output packages cleanly into the .app |
| Server state | TanStack Query 5.83 | Cache + invalidation for a chatty local API |
| Client state | Zustand 5.0.6 (+`persist`) | Display prefs, chat UI state; no boilerplate |
| Components | Radix UI primitives + local `ui/` | Accessible primitives, own styling |
| Styling | Tailwind 4 + CSS custom properties | Themes are token swaps, not class rewrites |
| Forms | react-hook-form 7.60 + zod 4 | Shared validation shapes |
| Editor | CodeMirror 6 | Markdown source + live preview |
| Graph | @xyflow/react 12.11 | Vault/knowledge graph views |
| Motion | framer-motion 12.42 | Reduced-motion-aware transitions |
| i18n | i18next 25.7 + react-i18next 16.5 | Locale switching |
| Math/Markdown | react-markdown, remark-gfm, remark-math, rehype-katex, katex | Notes and chat rendering |
| Tests | Vitest 4.1.8 + Testing Library; Playwright 1.61.1 | Unit + browser matrices |

## 2. Route map (App Router)

```
/(auth)/login
/(dashboard)                        Intelligence workspace home
/(dashboard)/sources  ·  /sources/[id]
/(dashboard)/notebooks  ·  /notebooks/[id]
/(dashboard)/knowledge              Vault + knowledge engine
/(dashboard)/search                 Ask & Search
/(dashboard)/capture                Capture inbox
/(dashboard)/studio                 Evidence Studio
/(dashboard)/podcasts  ·  /podcasts/studio
/(dashboard)/study  ·  /study/plans/[planId]
/(dashboard)/transformations
/(dashboard)/advanced
/(dashboard)/settings  ·  /api-keys /local-models /mcp /launcher-prefs
/(dashboard)/setup-wizard
```

## 3. Shell architecture — two generations behind one flag

`isVisualSystemV2Enabled()` selects the shell. Both are maintained; V2 is the
notebook-voiced design.

```tsx
// components/deeper-notebook/workspace/WorkspaceAppShell.tsx
export function WorkspaceAppShell({ children }: { children: ReactNode }) {
  return (
    <div data-testid="visual-system-v2-shell" data-dn-visual-system="v2"
         className="dn-workspace-shell">
      <InstrumentDock />                       {/* 4.25rem icon rail */}
      <div className="dn-workspace-shell-body">
        <CommandBar />                          {/* ⌘K trigger + Focus control */}
        <AdaptiveNavigator />                   {/* contextual left nav */}
        <section className="dn-workspace-canvas">{children}</section>
        <ContextLens />                         {/* right evidence rail */}
      </div>
      <ShellUtilities />
    </div>
  )
}
```

CSS grid drives the layout:

```css
.dn-workspace-shell {
  display: grid;
  grid-template-areas: "dock body";
  grid-template-columns: 4.25rem minmax(0, 1fr);
  height: 100dvh; overflow: hidden; isolation: isolate;
}
.dn-workspace-shell-body {
  display: grid;
  grid-template-areas: "command command command" "navigator canvas lens";
  grid-template-columns: minmax(15rem,17rem) minmax(0,1fr) minmax(17.5rem,20rem);
  grid-template-rows: auto minmax(0, 1fr);
}
```

> **Layering lesson (v0.8.84 / v0.8.96).** The dock is `z-index: 2`. Full-text badges
> inside the 4.25rem rail refused to shrink (`min-width: auto`) and painted **over** the
> navigator. Fix: clip the dock and collapse badges to a wrapped dot cluster.
>
> `FocusModeControl` taught the same lesson twice. It was `position: absolute` at the
> shell's top-right with nothing reserving its footprint, so it covered the command bar's
> palette trigger at every width. The first fix reserved 18rem on the command row — but
> it selected `.dn-workspace-shell-body > .dn-command-bar` while the rendered bar's parent
> is `.dn-luminous-workspace`, so the rule matched nothing and the overlap survived
> unnoticed for another release.
>
> **The v0.8.96 fix is structural:** the control moved *into* `CommandBar`, inside a
> `.dn-command-actions` flex group, so the two controls lay out side by side with no
> reservation to keep in sync. Only the legacy shell — which has no command bar — still
> floats it. Prefer flow over floating chrome; a reservation is a second source of truth
> that will drift.

## 4. Display preferences (persisted, four axes)

```ts
// lib/stores/display-preferences-store.ts
export type WallpaperPreference    = 'aurora' | 'static' | 'off'
export type MotionPreference       = 'system' | 'full' | 'reduced'
export type TransparencyPreference = 'frosted' | 'solid'
export type DensityPreference      = 'comfortable' | 'compact'   // v0.8.87

export const DEFAULT_DISPLAY_PREFERENCES = {
  wallpaper: 'aurora', motion: 'system',
  transparency: 'frosted', density: 'comfortable', focusMode: false,
}
```

Every setter validates through a type guard and falls back to the default — persisted
storage is untrusted input:

```ts
setDensity: (value) => set({
  density: isDensityPreference(value) ? value : DEFAULT_DISPLAY_PREFERENCES.density,
}),
```

Values are mirrored onto the document root, and CSS reads them:

```ts
export function applyDisplayPreferencesToDocument(values: DisplayPreferenceValues) {
  const root = document.documentElement
  root.dataset.dnWallpaper    = values.wallpaper
  root.dataset.dnMotion       = resolveMotionPreference(values.motion)
  root.dataset.dnTransparency = values.transparency
  root.dataset.dnDensity      = values.density
}
```

```css
/* Comfortable = today's layout (no rules). Compact re-scales shared tokens. */
:root[data-dn-density='compact'] .dn-workspace-shell {
  --dn-space-3: 0.5rem; --dn-space-4: 0.65rem; --dn-space-6: 1rem;
  --dn-write-leading: 1.55;
}
```

## 5. The notebook design language (v0.8.85)

Token-driven, theme-adaptive — no per-theme overrides:

```css
.dn-workspace-shell {
  --dn-paper:      color-mix(in oklab, var(--background) 97%, var(--foreground));
  --dn-rule:       color-mix(in oklab, var(--foreground) 9%, transparent);
  --dn-margin-ink: color-mix(in oklab, var(--primary) 30%, transparent);
  --dn-write-leading: 1.7;
}
/* Titles take the written voice; chrome stays sans. */
.dn-workspace-shell .dn-workspace-page-title { font-family: var(--font-serif), Georgia, serif; }
/* The editor becomes ruled paper — rules scroll WITH the text. */
.dn-workspace-shell .dn-vault-editor .cm-content {
  background-image: repeating-linear-gradient(to bottom,
    transparent 0,
    transparent calc(1em * var(--dn-write-leading) - 1px),
    var(--dn-rule) calc(1em * var(--dn-write-leading) - 1px),
    var(--dn-rule) calc(1em * var(--dn-write-leading)));
  background-attachment: local;
}
@media (prefers-contrast: more) { .dn-workspace-shell { --dn-rule: transparent; } }
```

## 6. Feature flags are build-time constants

```ts
// lib/features.ts — MUST use static process.env property access
export function isSourceVisualsEnabled(): boolean {
  return envFlag(process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS, undefined, false)
}
```

A contract test (`features-build-contract.test.ts`) asserts every flag uses a **static**
`process.env.X` reference and never `process.env[...]` — dynamic lookup defeats Next's
inlining and the flag silently reads `undefined` in production.

**Consequence:** in a packaged app these cannot be flipped. Verified by diffing SSR
chunks between an on and off build — exactly two files differ:

```js
"isSourceVisualsEnabled",0,function(){return c("1",void 0,!1)}   // enabled build
"isSourceVisualsEnabled",0,function(){return c("0",void 0,!1)}   // disabled build
```

## 7. Component: SourceCover (capability-aware)

```tsx
const visualsDisabled = source.visual_status?.state === 'disabled'
// ...
{visual ? (
  <img src={visual.asset_url}
       alt={`${title} — ${sourceVisualOriginLabel(visual.origin)}: ${visual.alt_text}`}
       width={visual.width} height={visual.height} loading={priority ? 'eager' : 'lazy'}
       onError={() => setFailedAssetIdentity(assetIdentity)} />
) : (
  <div className="dn-source-cover__fallback">
    <p className="dn-source-cover__title">{title}</p>
    <p className="dn-source-cover__status" role="status">{statusCopy(source)}</p>
  </div>
)}
{onRefresh && !visualsDisabled ? <button …>Refresh visual for {title}</button> : null}
{onRemove  && !visualsDisabled ? <button …>Remove visual for {title}</button>  : null}
```

Width/height are always emitted so the layout reserves space — the enabled matrix holds
max CLS at **0.0028** against a 0.05 budget.

## 8. Tool picker

`McpToolPicker` renders registry MCP servers **plus** two synthetic rows for the built-in
tools, so an always-on network tool always has a per-turn off switch:

```tsx
const webSearchAvailable = !!webSearch?.enabled
const scholarlyAvailable = !!webSearch?.scholarly_enabled   // optional → old shape safe
if (servers.length === 0 && !webSearchAvailable && !scholarlyAvailable) return null
```

## 9. Component: ExamLab and the Debate mode toggle

`frontend/src/components/study/ExamLab.tsx` drives the timed-exam flow against
`/api/study/exams/*` (`lib/api/study-exams.ts`, `lib/hooks/use-study-exams.ts`). It renders
strictly from whichever half of `ExamAttemptResponse` the backend sent — `questions` during
the attempt, `results` after submit — so the client can't accidentally render an answer key
early even if it wanted to; the field it would need isn't in the payload.

Debate mode is not a separate screen — it's a per-turn toggle on the existing chat surface:

```tsx
// frontend/src/components/source/ChatPanel.tsx
<Button
  variant={debateMode ? 'secondary' : 'ghost'}
  aria-pressed={debateMode}
  aria-label={debateMode ? 'Leave Debate mode' : 'Enter Debate mode'}
  title="Debate mode — the assistant argues the opposing case, grounded in your sources"
  onClick={onToggleDebateMode}
  data-testid="debate-mode-toggle"
>
  <Swords className="h-3.5 w-3.5" aria-hidden="true" />
  Debate
</Button>

// ChatColumn.tsx — the toggle is a controlled prop, state owned by the chat hook:
// debateMode={chat.debateMode}
// onToggleDebateMode={() => chat.setDebateMode(!chat.debateMode)}
// every sent turn carries chat_mode: 'debate' and the assistant argues
// the opposing position — see ChatPanel.debate-mode.test.tsx
```

State lives in the `chat` hook alongside the rest of the conversation state, not in
`ChatPanel` itself — `ChatPanel` only renders the controlled boolean it's handed. It resets
to standard mode on a fresh session, matching the backend contract: `chat_mode` travels
per-request, nothing about it is persisted server-side.

## 10. Testing

- **Unit:** Vitest + Testing Library — 240 files, 1,832 tests.
- **Browser:** Playwright, `workers: 1` (shared stateful Next server), three projects:
  `mocked-browser`, `native-runtime`, `packaged-device`.
- **Matrices:** the source-gallery spec runs 8 cells × 3 themes × 4 viewports = 96 with
  an exact request ledger, plus dual-off (20 cells) and enabled-build/disabled-backend.

Known flakes under machine load ≳20: `brand.test.ts`, `workspace.test.tsx`,
`KnowledgePodcastPane.test.tsx` — all pass in isolation.

---

*Continues in [06 — Authentication & Authorization](./06-authentication-authorization.md).*
