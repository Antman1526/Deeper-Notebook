# Research Core OS Theme Foundation Verification

Status: partially verified. The focused frontend contracts, Guided Tips
contracts, desktop/API theme suite, and generated-asset freshness check pass.
The repository-wide lint, production build, and current visual command remain
open at this implementation head; their actual failures are recorded below.

Commit: `7e696b1078ecc6a69ef56945cb4a987c7cf5c234`

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
- The implementation revision above is the literal output of
  `git rev-parse HEAD` before this verification document was committed.
- Existing unrelated worktree changes and generated/untracked state were
  preserved and were not staged.

## Regression gates

### 1. Frontend component and contract tests

Command:

```bash
cd frontend && npm test -- src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts src/lib/brand.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx src/components/deeper-notebook/ThemeGallery.test.tsx
```

Result: **exit 0 — 6 files passed; 31 tests passed.**

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
./.build-venv/bin/pytest -q desktop/tests/test_window.py desktop/tests/test_config.py desktop/tests/test_theme_static_assets.py desktop/tests/test_first_run.py desktop/tests/test_model_manager_server.py desktop/tests/test_memory_dashboard_server.py tests/test_deeper_notebook_router.py
```

Result: **exit 0 — 197 passed, 1 existing dependency deprecation warning.**

### 3. Static assets, lint, and production build

The literal generator command was attempted first:

```bash
python scripts/render_theme_static_assets.py --check
```

Result: **exit 127 — `python` is not on the login-shell PATH.** The same
check using the repository's working Python environment passed:

```bash
./.build-venv/bin/python scripts/render_theme_static_assets.py --check
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

The production build was run independently so its result is recorded:

```bash
cd frontend && npm run build
```

Result: **exit 1.** Next.js compiled successfully, then TypeScript failed at
`src/components/guided-tips/GuidedTipsProvider.tsx:87:37` because `tip` is
possibly `undefined` inside the keyboard handler. This is an implementation
issue outside Task 8's documentation-only ownership; it remains open rather
than being silently treated as a passing build.

### 4. Deterministic visual proof

The required no-snapshot-update command was run unchanged:

```bash
cd frontend && npm run test:e2e:themes
```

Result: **exit 1 before browser startup.** The Playwright web server invokes
`npm run build`, which stops on the same `GuidedTipsProvider.tsx:87:37`
TypeScript error. Therefore this Task 8 invocation executed zero browser
comparisons and changed no snapshots.

The eight baselines below are the unchanged Task 6 visual proof consumed by
this handoff. Task 6 regenerated them, reran the command without updates, and
visually inspected all eight at the stated page viewports. The selected-card
captures are card crops from their 1440x900 page viewport.

| Capture | Test viewport | Baseline file | Image dimensions |
| --- | ---: | --- | ---: |
| Research Core Dark full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/research-core-dark-1440x900-mocked-browser-darwin.png` | 1440x5068 |
| Research Core Light full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/research-core-light-1440x900-mocked-browser-darwin.png` | 1440x5068 |
| Deep Ocean full page | 1280x800 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/deep-ocean-1280x800-mocked-browser-darwin.png` | 1280x5068 |
| Archive Paper full page | 1280x800 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/archive-paper-1280x800-mocked-browser-darwin.png` | 1280x5068 |
| High Contrast Dark full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-dark-1440x900-mocked-browser-darwin.png` | 1440x5068 |
| High Contrast Light full page | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-light-1440x900-mocked-browser-darwin.png` | 1440x5068 |
| High Contrast Dark selected Accessibility card | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-dark-selected-accessibility-mocked-browser-darwin.png` | 378x228 |
| High Contrast Light selected Accessibility card | 1440x900 | `frontend/e2e/theme-gallery-visual.spec.ts-snapshots/high-contrast-light-selected-accessibility-mocked-browser-darwin.png` | 378x228 |

No snapshot was regenerated during Task 8. The inherited proof remains
unchanged, but a fresh current-head visual pass is still open until the
production build type error is repaired in its owning implementation scope.

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

- Repair or otherwise resolve the `GuidedTipsProvider.tsx:87:37` TypeScript
  narrowing error in the Task 7 implementation scope, then rerun the production
  build and `npm run test:e2e:themes` without updating snapshots.
- Clean up the pre-existing repository-wide Podcast/Vault ESLint findings in a
  separate scope; they are not part of this verification record's fix.
