# Research Core OS Theme Foundation Verification

Status: verified after final-review repair. The focused frontend contracts,
Guided Tips contracts, desktop/API theme suite, generated-asset freshness
check, scoped ESLint, production build, and all eight deterministic visual
comparisons pass. Repository-wide lint remains blocked by pre-existing
Podcast/Vault findings; that unrelated gate is recorded separately below.

Commit: `b7b90cf0f2da49fc62cc546267e5f582ebf82d8e`

Foundation baseline commit: `53ec0990b14fdcd6413d8bd7af9936ce0c2e434b`

Branch: `codex/podcast-intelligence-studio-phase-2`

Worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/research-core-lab-phase-1`

## Scope

25-theme runtime, fresh default, semantic tokens, gallery, auxiliary surfaces, Guided Tips, and theme visual proof

This record covers the foundation slice only. Source authority is unchanged:
`desktop/window.py` remains the runtime palette authority, the frontend catalog
and API allowlist stay in lockstep, and generated auxiliary assets remain
derived from the runtime palettes. External Obsidian and Logseq vaults remain
read-only; no provider, model, watcher, protected-vault path, or source data
was changed by these checks.

The Dashboard, Knowledge, chat, and Podcast Studio anchor matrices are outside
this foundation proof and remain assigned to their subsequent redesign plans.
This record also does not claim the later shell, Knowledge workspace, grounded
chat, Podcast Intelligence Studio, complete anchor-route matrix, native visual
smoke, contact sheet, or human approval gates.

## Environment and revision

- Python: 3.12.13 (`.build-venv`); pytest: 8.3.4.
- Node: v24.17.0; npm: 11.13.0; Next.js: 16.2.12; Vitest: 4.1.8.
- The repair implementation revision above is the literal output of
  `git rev-parse HEAD` before this verification document was committed.
- Existing unrelated worktree changes and generated/untracked state were
  preserved and were not staged.

## Final-review repair closure

Product repair commit: `b7b90cf0f2da49fc62cc546267e5f582ebf82d8e`

- Canonical persisted `system` remains distinct from its resolved `dark` or
  `light-blue` palette. `ThemeProvider` owns one media-query listener only for
  the `system` selection, follows dark-to-light and light-to-dark changes, and
  removes the listener on cleanup. Explicit persisted catalog IDs stay fixed.
- The authoritative desktop palettes now provide WCAG AA (>=4.5:1) primary
  and accent foreground pairs for all 25 themes. The permanent parametrized
  test and all three generated auxiliary CSS files were refreshed from
  `desktop/window.py`.
- Settings exposes `data-testid="settings-scroll-viewport"`; the visual
  fixture temporarily unclips the internal scroll ancestors for full-page
  capture and asserts the final Classics group and Midnight Aurora card. Six
  full-page baselines were regenerated to 6382px; the two selected
  Accessibility card crops remained byte-identical.

## Regression gates

### 1. Frontend component and contract tests

Command:

```bash
cd frontend && npm test -- src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts src/lib/brand.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx src/components/deeper-notebook/ThemeGallery.test.tsx src/components/providers/ThemeProvider.test.tsx src/components/providers/ThemeProvider.integration.test.tsx src/lib/stores/theme-store.test.ts
```

Result: **exit 0 — 9 files passed; 44 tests passed.** This includes the
ThemeProvider system-selection/listener regressions and the permanent theme
store compatibility tests.

Command:

```bash
cd frontend && npm test -- src/lib/guided-tips/catalog.test.ts src/lib/stores/guided-tips-store.test.ts src/components/guided-tips/GuidedTipsProvider.test.tsx
```

Result: **exit 0 — 3 files passed; 11 tests passed.**

### 2. Desktop/API theme tests

The literal shell command from the brief was attempted first:

```bash
pytest -q desktop/tests/test_window.py desktop/tests/test_config.py desktop/tests/test_theme_static_assets.py desktop/tests/test_first_run.py desktop/tests/test_model_manager_server.py desktop/tests/test_memory_dashboard_server.py tests/test_deeper_notebook_router.py
```

Result: **exit 127 — `pytest` is not on the login-shell PATH.** The repository
working environment was used without changing dependencies:

```bash
PYTHONPATH=. ./.build-venv/bin/pytest -q desktop/tests/test_window.py desktop/tests/test_config.py desktop/tests/test_theme_static_assets.py desktop/tests/test_first_run.py desktop/tests/test_model_manager_server.py desktop/tests/test_memory_dashboard_server.py tests/test_deeper_notebook_router.py
```

Result: **exit 0 — 247 passed, 1 existing dependency deprecation warning.**

### 3. Static assets, lint, and production build

The literal generator command was attempted first:

```bash
python scripts/render_theme_static_assets.py --check
```

Result: **exit 127 — `python` is not on the login-shell PATH.** The same
check using the repository's working Python environment passed:

```bash
PYTHONPATH=. ./.build-venv/bin/python scripts/render_theme_static_assets.py --check
```

Result: **exit 0 — generated CSS and first-run catalog are fresh.**

The chained command from the brief was then attempted:

```bash
cd frontend && npm run lint && npm run build
```

Result: **exit 1 at `npm run lint`; the `npm run build` leg was not reached by
the `&&` chain.** Repository-wide ESLint reported 10 errors and 6 warnings,
all in pre-existing Podcast/Vault files (`no-explicit-any` errors and unused
or missing-effect-dependency warnings). No unrelated lint findings were
repaired in this documentation task.

The scoped repair lint was run independently:

```bash
cd frontend && npx eslint src/components/providers/ThemeProvider.tsx src/components/providers/ThemeProvider.integration.test.tsx src/lib/stores/theme-store.ts src/lib/theme-storage.ts src/components/deeper-notebook/ThemeGallery.tsx 'src/app/(dashboard)/settings/page.tsx' e2e/theme-gallery-visual.spec.ts
```

Result: **exit 0.**

The production build was run independently after the Guided Tips callback
narrowing repair so its result is recorded:

```bash
cd frontend && npm run build
```

Result: **exit 0.** Next.js compiled successfully, TypeScript completed, and
static page generation produced all 23 routes.

### 4. Deterministic visual proof

The required no-snapshot-update command was run unchanged:

```bash
cd frontend && npm run test:e2e:themes
```

Result: **exit 1 after all eight browser comparisons.** The two selected
Accessibility-card captures passed. The six full-page captures failed because
the repaired capture state now paints the complete Settings surface: each
previous baseline was 5150px tall while the unclipped capture was 6382px tall.
No snapshot was changed by this first run.

Following the reviewed baseline-closure decision, the exact update command was
run:

```bash
cd frontend && npm run test:e2e:themes -- --update-snapshots
```

Result: **exit 0 — 8 passed (6 full-page baselines regenerated to 6382px; 2
selected Accessibility-card captures unchanged).** Every changed full-page
image was visually inspected at its test viewport. The updated captures show
all five gallery groups through the final Classics/Midnight Aurora card, plus
the approved first-visit Settings Guided Tip and Guided Tips control row. No
unrelated visual drift was accepted. The two selected card crops were
byte-unchanged against the prior commit.

The required no-update command was then rerun unchanged:

```bash
cd frontend && npm run test:e2e:themes
```

Result: **exit 0 — 8 passed (40.5s).** No snapshots changed during this final
proof run. The selected-card captures are card crops from their 1440x900 page
viewport.

| Capture | Test viewport | Baseline file | Image dimensions |
| --- | ---: | --- | ---: |
| Research Core Dark full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/research-core-dark-1440x900-mocked-browser-darwin.png` | 1440x6382 |
| Research Core Light full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/research-core-light-1440x900-mocked-browser-darwin.png` | 1440x6382 |
| Deep Ocean full page | 1280x800 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/deep-ocean-1280x800-mocked-browser-darwin.png` | 1280x6382 |
| Archive Paper full page | 1280x800 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/archive-paper-1280x800-mocked-browser-darwin.png` | 1280x6382 |
| High Contrast Dark full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-dark-1440x900-mocked-browser-darwin.png` | 1440x6382 |
| High Contrast Light full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-light-1440x900-mocked-browser-darwin.png` | 1440x6382 |
| High Contrast Dark selected Accessibility card | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-dark-selected-accessibility-mocked-browser-darwin.png` | 378x228 |
| High Contrast Light selected Accessibility card | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-light-selected-accessibility-mocked-browser-darwin.png` | 378x228 |

The six full-page baselines are now the reviewed 6382px captures from repair
commit `b7b90cf0f2da49fc62cc546267e5f582ebf82d8e`; the two selected card crops
remain byte-identical to their prior proof. The production build and final
8/8 visual gate are green.

## Boundaries and next plans

The foundation ends with working themes, gallery, persistence, auxiliary
desktop surfaces, Guided Tips, and visual-proof infrastructure. It intentionally
does not redesign unrelated application screens. Subsequent plans consume the
stable tokens and fixtures in this order:

1. Research Core OS application shell, Dashboard, and Settings information
   architecture.
2. Knowledge workspace, grounded chat, evidence, and contradiction
   presentation.
3. Podcast Intelligence Studio visual production workspace.
4. Complete anchor-route render matrix, native visual smoke, contact sheet,
   and human approval gate.

## Open items

- Clean up the pre-existing repository-wide Podcast/Vault ESLint findings in a
  separate scope; they are not part of this verification record's fix.
