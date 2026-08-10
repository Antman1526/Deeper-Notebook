# `deeper-notebook/` — downstream component layer

This namespace exists to **replace or extend specific upstream React components**
without ever editing upstream files. When upstream releases a new version, our
work is in a discrete namespace and rebases trivially.

## The pattern

```
frontend/src/
├── app/                     ← upstream Next.js pages
├── components/
│   ├── ui/                  ← upstream shadcn primitives — DO NOT edit
│   ├── settings/...         ← upstream feature components — DO NOT edit
│   └── deeper-notebook/     ← downstream namespace (this folder)
│       ├── README.md        ← you are here
│       ├── index.ts         ← exports
│       ├── tokens.css       ← additional design tokens layered on top of shadcn
│       └── *.tsx            ← shadow / new components
```

### Discipline (the rule)

1. **Never edit `components/ui/*.tsx` or `components/settings/*.tsx`.** Those
   are upstream — they get rebased on every upstream release.
2. **Edit upstream pages (`app/.../page.tsx`) only for tiny surgical changes**
   that can be expressed in 1–3 lines (e.g. adding a config row, swapping one
   import). Anything larger goes into a shadow component.
3. **For redesigns**: build a new `deeper-notebook/<component-name>.tsx`, then replace the
   relevant upstream import in the page file. The page file delta is one line.

## Importing in pages

```tsx
// Don't:
import { DefaultModelsPanel } from '@/components/settings/DefaultModelsPanel'

// Do:
import { ReasoningSlotCard } from '@/components/deeper-notebook'
```

## Design tokens

`tokens.css` defines CSS custom properties **layered on top of** shadcn's tokens
(set by the desktop wrapper's theme injection at runtime). Tokens here are
purpose-specific:

- `--dn-card-elevation` — shadow strength for elevated cards
- `--dn-accent-soft` — translucent accent for highlights/badges
- `--dn-success` / `--dn-warning` — semantic colors not in shadcn defaults

When a shadow component needs a color, prefer:
1. Existing shadcn token (`var(--primary)`, `var(--muted-foreground)`)
2. An `--dn-*` token defined here
3. As a last resort, a hardcoded value (and add a TODO to promote it to a token)

## Theme integration

The desktop wrapper (`desktop/window.py`) injects 27 shadcn variables at page
load time. `tokens.css` adds a small `dn`-namespaced layer on top, derived
from the active shadcn theme via `color-mix()` so they auto-adapt when the user
switches themes.

## What lives here so far

| File | What |
|---|---|
| `ReasoningSlotCard.tsx` | Polished card explaining what the v0.5 reasoning slot is — example of the pattern (small, self-contained, uses tokens). |
| `SourceHealthPill.tsx` | Reusable source readiness badge for Evidence Studio and future source health surfaces. |
| `ModelFleetBadge.tsx` | Reusable local model runtime badge for GGUF, MLX, and future local providers. |
| `CitationCoverageBadge.tsx` | Reusable citation-count badge for artifact and trust surfaces. |
| `CitationDrawer.tsx` | Focused evidence panel for inspecting citation previews, source IDs, locations, and source-record jumps. |
| `StudyArtifactViewers.tsx` | Interactive flashcard, quiz, Course Pack, Research Run, Mind Map, and Data Table viewers for Evidence Studio artifacts. |
| `RunTimeline.tsx` | Compact Claude Code-style run inspector for notebook chat context, routing, MCP, privacy, and agent state. |

## Luminous folio primitives

The `folio/` namespace is the presentation-only notebook grammar. These
components accept content and callbacks from an owning surface; they do not
fetch data, own route knowledge, or write to stores.

| Primitive | Use it for |
|---|---|
| `FolioPage` | One named `main`, `section`, or `article` with an associated title, optional subtitle/actions, and a complementary margin slot. |
| `FolioRouteFrame` | A route-level composition that supplies section metadata and keeps the page landmark contract consistent. |
| `FolioSpread` | A primary reading surface plus an optional labelled context lens. |
| `FolioIndex` / `FolioTab` | Controlled notebook sections with roving focus, Arrow/Home/End keyboard navigation, and 44px targets. |
| `MarginNote` | Backlinks, commentary, review notes, or other non-primary context. |
| `EvidenceInsert` | An evidence receipt/content insert; receipt actions stay outside form labels. |
| `FolioState` | Explicit loading, empty, error, offline, or permission states with a bounded action slot. |

Use semantic shadcn variables and the `--dn-*` token layer when composing
inside these primitives. Keep content, evidence approval, external-vault
authority, and route behavior in the owning feature surface.

## Adding a new shadow component

1. Create `components/deeper-notebook/MyThing.tsx`
2. Use shadcn primitives + design tokens (no raw colors)
3. Export from `components/deeper-notebook/index.ts`
4. Update the upstream page to import the new component (1-line change)
5. If you're replacing an upstream component, note it here so future readers
   know what's been forked.
