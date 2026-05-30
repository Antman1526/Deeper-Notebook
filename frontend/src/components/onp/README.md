# `onp/` — Open notebook+ shadow layer

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
│   └── onp/                 ← OUR namespace (this folder)
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
3. **For redesigns**: build a new `onp/<component-name>.tsx`, then replace the
   relevant upstream import in the page file. The page file delta is one line.

## Importing in pages

```tsx
// Don't:
import { DefaultModelsPanel } from '@/components/settings/DefaultModelsPanel'

// Do:
import { ReasoningSlotCard } from '@/components/onp'
```

## Design tokens

`tokens.css` defines CSS custom properties **layered on top of** shadcn's tokens
(set by the desktop wrapper's theme injection at runtime). Tokens here are
purpose-specific:

- `--onp-card-elevation` — shadow strength for elevated cards
- `--onp-accent-soft` — translucent accent for highlights/badges
- `--onp-success` / `--onp-warning` — semantic colors not in shadcn defaults

When a shadow component needs a color, prefer:
1. Existing shadcn token (`var(--primary)`, `var(--muted-foreground)`)
2. An `--onp-*` token defined here
3. As a last resort, a hardcoded value (and add a TODO to promote it to a token)

## Theme integration

The desktop wrapper (`desktop/window.py`) injects 27 shadcn variables at page
load time. `tokens.css` adds another ~6 onp-namespaced ones on top, derived
from the active shadcn theme via `color-mix()` so they auto-adapt when the user
switches themes.

## What lives here so far

| File | What |
|---|---|
| `ReasoningSlotCard.tsx` | Polished card explaining what the v0.5 reasoning slot is — example of the pattern (small, self-contained, uses tokens). |

## Adding a new shadow component

1. Create `components/onp/MyThing.tsx`
2. Use shadcn primitives + design tokens (no raw colors)
3. Export from `components/onp/index.ts`
4. Update the upstream page to import the new component (1-line change)
5. If you're replacing an upstream component, note it here so future readers
   know what's been forked.
