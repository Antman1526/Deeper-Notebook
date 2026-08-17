# User guide — source and regeneration

The end-user PDF guide (28 sections, ~40 pages) is built from the files in this directory.
The PDF itself is **not** committed — it is ~7.7 MB and is a build artifact.

## Files

| File | What it is |
|---|---|
| `guide.html` | The guide itself — content, print CSS, and figure captions |
| `shots/*.png` | 24 live application renders + the app icon |
| `render.mjs` | Chromium print-to-PDF driver |
| `../../frontend/e2e/docs-capture.spec.ts` | The harness that produces `shots/` |

## Regenerating the screenshots

`docs-capture.spec.ts` visits every dashboard route against the mocked-browser
fixtures — the same fixtures the visual release gate uses — so the shots are real
renders of the application, deterministic, and require no live backend.

It is excluded from the `mocked-browser` project's default run (see the `testIgnore`
list in `frontend/playwright.config.ts`), so it does not add ~50 s to every gate. Run
it explicitly:

```bash
cd frontend
npm run build && PORT=3117 npm run start &        # or let Playwright start it
DOCS_CAPTURE_DIR=../docs/user-guide/shots \
  npx playwright test e2e/docs-capture.spec.ts --project=mocked-browser
```

## Rendering the PDF

`render.mjs` needs `@playwright/test` resolvable, so run it from `frontend/`:

```bash
cd frontend
GUIDE_DIR="$(cd ../docs/user-guide && pwd)" node ../docs/user-guide/render.mjs
```

Output: `docs/user-guide/Deeper-Notebook-User-Guide.pdf` (A4, printed backgrounds,
page numbers in the footer).

## When to update

Refresh the shots whenever a route's layout changes materially, and bump the version
string in three places inside `guide.html`: the cover kicker, the cover meta line, and
the footer template in `render.mjs`.
