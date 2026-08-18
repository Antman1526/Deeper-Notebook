# User guide — source and regeneration

The end-user PDF guide (28 sections, 45 pages) is built from the files in this directory.
The PDF itself is **not** committed — it is ~7.9 MB and is a build artifact.

## Files

| File | What it is |
|---|---|
| `guide.html` | The guide itself — content, print CSS, and figure captions |
| `shots/*.png` | 26 live application renders + the app icon |
| `render.mjs` | Chromium print-to-PDF driver |
| `../../frontend/e2e/docs-capture.spec.ts` | The harness that produces `shots/` |

## Regenerating the screenshots

`docs-capture.spec.ts` visits every dashboard route against the mocked-browser
fixtures — the same fixtures the visual release gate uses — so the shots are real
renders of the application, deterministic, and require no live backend.

Three tests in the file, one command runs all of them: the main loop (24 static routes),
plus two interaction-driven captures that click through to a specific UI state —
`25-chat-debate-mode` (toggle clicked, `aria-pressed` asserted before the shot) and
`26-study-examlab` (a mocked quiz artifact walked through notebook→quiz→start, one
answer selected). Both reuse `installGuideBackgroundRoutes`, the same route setup the
main loop uses, so a route added for one shot can't drift out of sync with the others.

It is excluded from the `mocked-browser` project's default run (see the `testIgnore`
list in `frontend/playwright.config.ts`), so it does not add ~50 s to every gate.
Setting `DOCS_CAPTURE_DIR` — which a capture run needs anyway — lifts the exclusion,
so there is no separate flag to remember:

```bash
cd frontend
DOCS_CAPTURE_DIR="$(cd ../docs/user-guide/shots && pwd)" \
  npx playwright test e2e/docs-capture.spec.ts --project=mocked-browser
```

Pass an absolute path: the spec writes relative to the Playwright working directory,
not to this file. Playwright starts (or reuses) the Next server itself; a cold
`npm run build` can exceed the 120 s `webServer` timeout, so on a slow machine build
first and leave `PORT=3117 npm run start` running.

## Rendering the PDF

```bash
node docs/user-guide/render.mjs
```

Runnable from anywhere — it resolves Chromium through `frontend/node_modules`
explicitly rather than relying on the working directory. Output:
`docs/user-guide/Deeper-Notebook-User-Guide.pdf` (A4, printed backgrounds, page
numbers in the footer). The PDF is gitignored.

## When to update

Refresh the shots whenever a route's layout changes materially, and bump the version
string in three places: the cover kicker and the cover meta line in `guide.html`, and
the footer template in `render.mjs`.
