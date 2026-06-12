# Frontend Bundle Analysis

v0.7.127 added `@next/bundle-analyzer` so any maintainer can measure
client-bundle size + identify lazy-load opportunities.

## How to run

```bash
cd frontend
npm run build:analyze
```

This runs a production build with `ANALYZE=true`, which triggers
`@next/bundle-analyzer` to write three HTML reports:

- `.next/analyze/client.html` — what ships to the browser
- `.next/analyze/server.html` — what runs in the Node.js server
- `.next/analyze/edge.html` — what runs at the edge (middleware)

Open any of them with `open .next/analyze/client.html` (macOS) or
`xdg-open .next/analyze/client.html` (Linux). You get an interactive
treemap where rectangle area = bytes contributed.

## What to look for

1. **Largest single chunks** — sort by size descending. Anything
   over ~150 KB compressed deserves a hard look.

2. **Modules duplicated across chunks** — sign that a dependency
   should be hoisted to a shared chunk via the `experimental.optimizePackageImports`
   config or webpack splitChunks tuning.

3. **Server-only libraries in the client bundle** — biggest possible
   win. Anything that *only* runs on the server (parsing libraries,
   AI SDK secrets, etc.) accidentally leaking into client code
   doubles its actual cost.

4. **Heavy dependencies on the initial-load path** — anything that
   isn't visible above the fold can be lazy-loaded via
   `next/dynamic`.

## Known lazy-load opportunities (as of v0.7.127)

These are educated guesses based on import-graph analysis, NOT yet
verified against the analyzer output. Run `build:analyze` and confirm
before acting.

### High-impact candidates

| Component | Size estimate | Why it's a candidate |
|---|---:|---|
| `CommandPalette` | ~30 KB | Loaded on every dashboard page mount but only used on Cmd+K. Already client-only; refactor into outer (key listener) + lazy body. |
| Studio multi-page export dialogs (v0.7.105) | ~15 KB | Used only when the user clicks "Export"; already dialog-gated but the source modules are eagerly bundled. |
| Import preview dialog (v0.7.105) | ~10 KB | Same pattern. |
| `@uiw/react-md-editor` | ~80 KB | **Already lazy** via `markdown-editor.tsx` using `dynamic()`. |
| `react-markdown` + `remark-gfm` | ~40 KB | Used in 5+ places, all interactive views. Could be lazy in less-hot paths (TransformationPlayground). |

### Already-handled

- ✅ `@uiw/react-md-editor` — wrapped in `dynamic()` with `ssr:false`.
- ✅ All `*Dialog.tsx` components — render-gated by `open` state, but
  imports happen at parent mount. Lazy-importing the dialog bodies
  would save bytes on routes where dialogs are present-but-closed.

## Concrete next steps for an operator

1. Run `npm run build:analyze` after a `npm install`.
2. Open `.next/analyze/client.html`.
3. Look for any single module > 200 KB gzipped.
4. For each candidate, wrap it in
   `dynamic(() => import('./Component'), { ssr: false, loading: ... })`.
5. Re-run analyzer to confirm the chunk moved out of the
   initial-load bundle into its own lazy chunk.

## Why this isn't auto-optimized

Bundle decisions depend on usage patterns specific to your install:

- If most users press Cmd+K within 5 seconds, lazy-loading
  CommandPalette is net-negative (you pay the network round-trip
  during the moment of intent).
- If most users *never* press it, lazy-loading is a clear win.

The right move is to look at the analyzer output, gut-check against
your user's behavior, and make targeted decisions. We provide the
tool; the maintainer makes the call.

## Bundle-size budget (proposed, not yet enforced)

These are reasonable starting targets for a Next.js dashboard app.
Failing one of them is a signal something has crept in that
shouldn't have.

| Bundle | Budget (gzipped) | Notes |
|---|---:|---|
| First-load JS | < 200 KB | The user's first paint depends on this. |
| Largest route chunk | < 50 KB | Routes shouldn't be that heavy individually. |
| Total client JS (all chunks) | < 1 MB | Includes lazy chunks; informational. |

To enforce these in CI, configure `experimental.bundlePagesRouterDependencies`
and set the `BUNDLE_ANALYZE_THRESHOLD_KB` env var (not yet wired —
deferred until we have real numbers from `build:analyze` runs).
