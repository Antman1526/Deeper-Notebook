# Final Local Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved theme and Source Gallery polish, close confirmed release regressions, prove every supported feature/rollback surface, rebuild the arm64 macOS package, and install and smoke-test that exact artifact recoverably.

**Architecture:** Extend the existing catalog/token systems rather than introducing a parallel visual framework. Keep Source Gallery mutation authority in its current owner while moving presentation into a focused action-menu component. Extend the package smoke verifier to discover launcher-assigned ports from the readiness file so the same deterministic tool can prove staged and installed bundles.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS, Radix Dropdown Menu, Vitest/Testing Library, Playwright, Python 3.12, pytest, SurrealDB 2.6.5, PyInstaller, macOS codesign/hdiutil.

## Global Constraints

- Work only in the isolated release worktree on `codex/today-productization`.
- Preserve `.superpowers/sdd/task-7-report.md` and `.codex/agent-context/today-productization-2026-08-20.md` unless a task explicitly appends a receipt.
- Do not push, merge, publish, notarize, dispatch Windows CI, change credentials, or mutate remote refs.
- Do not install until all source, browser, integration, security, review, and package-content gates are green.
- Preserve explicit-off feature authority and deliberately unavailable product boundaries.
- Use strict RED before production edits for every behavior change and confirmed defect.
- Keep the prior installed app recoverable until the user explicitly authorizes removal.
- Never use the Makefile's destructive `build-mac-install` target; install with an exact backup-first procedure.

---

### Task 1: Add the Gemini-Forward Dark catalog theme

**Files:**
- Modify: `frontend/src/lib/themes/catalog.ts`
- Modify: `frontend/src/lib/themes/catalog.test.ts`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/lib/theme-script.test.ts`
- Modify: `frontend/e2e/theme-gallery-visual.spec.ts`

**Interfaces:**
- Produces: catalog ID `gemini-forward-dark` and `THEME_BY_ID['gemini-forward-dark']`.
- Preserves: `VISUAL_SYSTEM_DEFAULT_THEME_ID === 'gemini-forward-light'`; no default switch.

- [ ] **Step 1: Write the failing catalog and bootstrap tests**

Add `gemini-forward-dark` immediately after `gemini-forward-light` in `expectedIds`, raise the exact catalog length to 27, assert `{ group: 'featured', dark: true }`, and assert `DARK_THEME_IDS` contains it. Add a theme-script assertion that the stored ID paints before hydration.

```ts
expect(THEME_BY_ID['gemini-forward-dark']).toMatchObject({
  group: 'featured',
  dark: true,
})
expect(DARK_THEME_IDS).toContain('gemini-forward-dark')
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd frontend
pnpm vitest run src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts
```

Expected: failures for the missing catalog ID and missing pre-hydration palette.

- [ ] **Step 3: Add the catalog entry and semantic palette**

Use this exact catalog shape:

```ts
{
  id: 'gemini-forward-dark',
  label: 'Gemini-Forward Dark',
  group: 'featured',
  dark: true,
  description: 'Mineral midnight with indigo, violet, cyan, and mint research light.',
  preview: {
    canvas: '#10111F', panel: '#191B2E', text: '#F1F2FF',
    primary: '#91A0FF', accent: '#C59BFF', border: '#343855',
  },
}
```

Add the matching `html[data-theme="gemini-forward-dark"]` variables to `globals.css`, using black foregrounds for the light primary/accent controls.

- [ ] **Step 4: Add the visual snapshot cell and run GREEN**

Add `gemini-forward-dark` to the theme-gallery visual matrix, update the exact catalog count, then run:

```bash
cd frontend
pnpm vitest run src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts
npx playwright test e2e/theme-gallery-visual.spec.ts --project=mocked-browser --grep 'gemini-forward-dark'
```

Expected: all selected tests pass and the new snapshot has no overflow/contrast failure.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/themes/catalog.ts frontend/src/lib/themes/catalog.test.ts frontend/src/app/globals.css frontend/src/lib/theme-script.test.ts frontend/e2e/theme-gallery-visual.spec.ts frontend/e2e/theme-gallery-visual.spec.ts-snapshots
git commit -m "feat(ui): add Gemini Forward dark theme"
```

### Task 2: Curate and shorten the theme gallery

**Files:**
- Modify: `frontend/src/lib/theme-storage.ts`
- Modify: `frontend/src/lib/theme-storage.test.ts`
- Modify: `frontend/src/components/deeper-notebook/ThemeGallery.tsx`
- Modify: `frontend/src/components/deeper-notebook/ThemeGallery.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/ThemePreviewCard.tsx`

**Interfaces:**
- Produces: `readRecentThemeIds(storage: Storage): string[]` and `recordRecentThemeId(storage: Storage, themeId: string): void`.
- Storage key: `dn-theme-recents`; maximum four unique IDs, newest first.
- Consumes: `isThemeId`, `THEME_BY_ID`, `THEME_CATALOG`.

- [ ] **Step 1: Write failing recent-storage tests**

```ts
recordRecentThemeId(localStorage, 'archive-paper')
recordRecentThemeId(localStorage, 'gemini-forward-dark')
recordRecentThemeId(localStorage, 'archive-paper')
expect(readRecentThemeIds(localStorage)).toEqual([
  'archive-paper',
  'gemini-forward-dark',
])
```

Cover malformed JSON, non-string entries, duplicate IDs, and the four-item bound.

- [ ] **Step 2: Write failing gallery tests**

Assert the initial gallery shows `Recommended`, hides an unselected classic behind `Show more themes`, renders `Recent` after Apply, and makes a hidden match visible while search is non-empty.

```ts
expect(screen.getByRole('heading', { name: 'Recommended' })).toBeVisible()
expect(screen.queryByText('Dracula')).not.toBeInTheDocument()
fireEvent.click(screen.getByRole('button', { name: 'Show more themes' }))
expect(screen.getByText('Dracula')).toBeVisible()
```

- [ ] **Step 3: Run RED**

```bash
cd frontend
pnpm vitest run src/lib/theme-storage.test.ts src/components/deeper-notebook/ThemeGallery.test.tsx
```

Expected: missing recent functions and missing curated disclosure behavior.

- [ ] **Step 4: Implement bounded recents and curated sections**

Use a constant recommended ID list:

```ts
const RECOMMENDED_THEME_IDS = [
  'gemini-forward-light', 'gemini-forward-dark',
  'research-core-light', 'research-core-dark',
  'archive-paper', 'high-contrast-light', 'high-contrast-dark',
] as const
```

`recordRecentThemeId` parses defensively, prepends the supplied ID, removes duplicates, slices to four, and writes one JSON array. `ThemeGallery` validates recents with `isThemeId`. A non-empty query bypasses the disclosure and groups every match by its existing catalog group. Preview never changes recents; Apply records the selection only after the canonical write attempt.

- [ ] **Step 5: Run GREEN and accessibility checks**

```bash
cd frontend
pnpm vitest run src/lib/theme-storage.test.ts src/components/deeper-notebook/ThemeGallery.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx
npx eslint src/lib/theme-storage.ts src/components/deeper-notebook/ThemeGallery.tsx src/components/deeper-notebook/ThemePreviewCard.tsx
```

Expected: all tests and ESLint pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/theme-storage.ts frontend/src/lib/theme-storage.test.ts frontend/src/components/deeper-notebook/ThemeGallery.tsx frontend/src/components/deeper-notebook/ThemeGallery.test.tsx frontend/src/components/deeper-notebook/ThemePreviewCard.tsx
git commit -m "feat(ui): curate theme selection"
```

### Task 3: Make visual artifacts and graph nodes theme-semantic

**Files:**
- Modify: `frontend/src/components/deeper-notebook/tokens.css`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/deeper-notebook/VisualArtifactViewers.tsx`
- Modify: `frontend/src/components/deeper-notebook/VisualArtifactViewers.test.tsx`
- Modify: `frontend/src/components/notebooks/MindMap.tsx`
- Create: `frontend/src/components/notebooks/MindMap.theme.test.tsx`
- Modify: `frontend/e2e/visual-system-matrix.spec.ts`

**Interfaces:**
- Produces CSS roles: `--dn-artifact-canvas`, `--dn-artifact-panel`, `--dn-artifact-ink`, `--dn-artifact-muted`, `--dn-artifact-line`, `--dn-graph-source`, `--dn-graph-note`, `--dn-graph-fallback`, `--dn-status-success`, `--dn-status-warning`, `--dn-status-info`, and matching foreground roles.
- Consumes only semantic catalog variables; no component receives a theme ID.

- [ ] **Step 1: Write strict source and rendering RED tests**

Add tests that reject the old artifact and graph hex literals and assert semantic classes/styles:

```ts
expect(source).not.toMatch(/#17324d|#f7f8fa|#2563eb|#d97706|#94a3b8/)
expect(screen.getByRole('figure', { name: 'Evidence at a glance' }))
  .toHaveClass('bg-[var(--dn-artifact-canvas)]')
```

The Mind Map test supplies one notebook, source, and note node and asserts the exact `var(--dn-graph-*)` values forwarded to React Flow.

- [ ] **Step 2: Run RED**

```bash
cd frontend
pnpm vitest run src/components/deeper-notebook/VisualArtifactViewers.test.tsx src/components/notebooks/MindMap.theme.test.tsx
```

Expected: failures identify the hard-coded palette.

- [ ] **Step 3: Define semantic roles**

In `tokens.css`, derive artifact roles from `--background`, `--card`, `--foreground`, `--muted-foreground`, `--border`, `--primary`, and `--accent`. Define distinct status hues using fixed OKLCH hue families and explicit foreground roles; add high-contrast overrides under the existing high-contrast theme selectors and forced-colors overrides using system colors.

```css
--dn-artifact-canvas: color-mix(in oklab, var(--background) 88%, var(--primary) 12%);
--dn-artifact-panel: var(--card);
--dn-artifact-ink: var(--foreground);
--dn-artifact-muted: var(--muted-foreground);
--dn-artifact-line: var(--border);
--dn-graph-source: color-mix(in oklab, var(--primary) 78%, var(--accent) 22%);
--dn-graph-note: color-mix(in oklab, var(--warning) 76%, var(--foreground) 24%);
```

- [ ] **Step 4: Replace component literals**

Use arbitrary token classes in `VisualArtifactViewers.tsx` and `var(...)` React Flow style values in `MindMap.tsx`. Preserve component props, document schemas, keyboard navigation, and graph callback behavior.

- [ ] **Step 5: Run GREEN and representative visual matrix**

```bash
cd frontend
pnpm vitest run src/components/deeper-notebook/VisualArtifactViewers.test.tsx src/components/notebooks/MindMap.theme.test.tsx
npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser --grep 'artifact|mind map|high contrast'
```

Expected: unit tests pass; light, dark, high-contrast, and forced-color cells remain usable.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/deeper-notebook/tokens.css frontend/src/app/globals.css frontend/src/components/deeper-notebook/VisualArtifactViewers.tsx frontend/src/components/deeper-notebook/VisualArtifactViewers.test.tsx frontend/src/components/notebooks/MindMap.tsx frontend/src/components/notebooks/MindMap.theme.test.tsx frontend/e2e/visual-system-matrix.spec.ts
git commit -m "fix(ui): theme visual artifacts semantically"
```

### Task 4: Consolidate Source Gallery card actions

**Files:**
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceCoverActions.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceCoverActions.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/source-gallery/SourceCover.tsx`
- Modify: `frontend/src/components/deeper-notebook/source-gallery/SourceCover.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/source-gallery/SourceGallery.tsx`
- Modify: `frontend/src/components/deeper-notebook/source-gallery/SourceGallery.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/source-gallery/source-gallery.css`
- Modify: `frontend/src/app/(dashboard)/sources/page.tsx`
- Modify: `frontend/src/app/(dashboard)/sources/page.test.tsx`
- Modify: `frontend/e2e/source-gallery.spec.ts`

**Interfaces:**
- Produces:

```ts
type SourceCoverActionsProps = {
  title: string
  pending: boolean
  visualsDisabled: boolean
  onRefresh?: () => void
  onRemove?: () => void
  onDelete?: () => void
}
```

- Extends `SourceCoverProps` and `SourceGalleryProps` with `onDelete?: (sourceId: string) => void`.
- Preserves exact `sourceId` callback authority and current confirmation dialog owner.

- [ ] **Step 1: Write menu and card RED tests**

Assert that the primary cover button opens the exact source, the menu dispatches refresh/remove/delete once, pending disables only matching visual mutations, backend-off hides visual actions but retains Delete, and compact actionless covers render no menu.

```ts
fireEvent.click(screen.getByRole('button', { name: 'Actions for First source' }))
fireEvent.click(screen.getByRole('menuitem', { name: 'Delete source' }))
expect(onDelete).toHaveBeenCalledWith('source:one')
```

Add a page test proving Delete opens confirmation for the menu's source even when another card was selected.

- [ ] **Step 2: Run RED**

```bash
cd frontend
pnpm vitest run src/components/deeper-notebook/source-gallery/SourceCoverActions.test.tsx src/components/deeper-notebook/source-gallery/SourceCover.test.tsx src/components/deeper-notebook/source-gallery/SourceGallery.test.tsx 'src/app/(dashboard)/sources/page.test.tsx'
```

Expected: missing component/prop/menu failures.

- [ ] **Step 3: Implement the focused action menu**

Build `SourceCoverActions` with the existing Radix `DropdownMenu` components and `MoreHorizontal`, `RefreshCw`, `ImageOff`, and `Trash2` icons. The trigger is always visible, 44px minimum, labelled `Actions for ${title}`. Destructive Delete uses `text-destructive`; it only opens the existing page confirmation.

Wrap the visual/title region in a semantic Open button only when `onOpen` exists. Retain the current visual receipt validation and dispatch identity fence. Add theme-aware queued/processing data attributes; CSS may animate opacity only outside `prefers-reduced-motion: reduce`.

- [ ] **Step 4: Wire exact delete authority in the Sources page**

Replace the selected-card toolbar delete with:

```ts
const handleGalleryDelete = useCallback((sourceId: string) => {
  const source = sources.find(candidate => candidate.id === sourceId)
  if (source) setDeleteDialog({ open: true, source })
}, [sources])
```

Pass `onDelete={handleGalleryDelete}` to `SourceGallery`. Keep sort in the filters and keep the table-path delete unchanged.

- [ ] **Step 5: Run GREEN and focused browser contracts**

```bash
cd frontend
pnpm vitest run src/components/deeper-notebook/source-gallery/SourceCoverActions.test.tsx src/components/deeper-notebook/source-gallery/SourceCover.test.tsx src/components/deeper-notebook/source-gallery/SourceGallery.test.tsx 'src/app/(dashboard)/sources/page.test.tsx'
npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser --grep 'source actions|delete|keyboard|explicit off|pagination'
```

Expected: callbacks are exact/one-shot; confirmation, keyboard, pagination, and rollback tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/deeper-notebook/source-gallery frontend/src/app/'(dashboard)'/sources/page.tsx frontend/src/app/'(dashboard)'/sources/page.test.tsx frontend/e2e/source-gallery.spec.ts
git commit -m "feat(ui): consolidate source gallery actions"
```

### Task 5: Make packaged smoke discover dynamic launcher ports

**Files:**
- Modify: `desktop/build/package_smoke.py`
- Modify: `desktop/tests/test_package_smoke_contract.py`
- Modify: `desktop/tests/test_release_manifest.py`
- Modify: `Makefile`

**Interfaces:**
- Adds CLI options `--readiness-file PATH`, `--environment KEY=VALUE`, and `--expected-feature NAME=BOOL`.
- When `--readiness-file` is present, `--api-url` and `--frontend-url` are forbidden; URLs come from the launcher's atomically written readiness JSON.
- Receipt schema version becomes 2 and records resolved URLs and expected feature results.

- [ ] **Step 1: Write parsing, timeout, cleanup, and receipt RED tests**

```py
args = smoke.parse_environment(["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0"])
assert args == {"DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED": "0"}
```

Test malformed environment values, readiness JSON missing URLs, child exit before readiness, exact process-group cleanup, feature mismatch, and a successful dynamic receipt.

- [ ] **Step 2: Run RED**

```bash
uv run pytest -q desktop/tests/test_package_smoke_contract.py desktop/tests/test_release_manifest.py
```

Expected: missing parser/CLI/receipt-v2 failures.

- [ ] **Step 3: Implement dynamic readiness and feature probes**

Launch with a copied environment, poll the readiness file until it contains loopback `api_url` and `frontend_url`, then probe `/readyz`, `/api/features`, and the frontend marker. Reject non-loopback URLs. Preserve artifact hash checks and `start_new_session=True`; always stop and await only the owned process group.

```py
launch_env = os.environ.copy()
launch_env.update(parse_environment(args.environment))
process = subprocess.Popen(command, env=launch_env, start_new_session=True, text=True)
```

- [ ] **Step 4: Add non-destructive Make smoke targets**

Add `smoke-mac-app` and `smoke-installed-mac-app` targets that call the verifier but never copy/remove `/Applications`. Require explicit artifact paths and receipt paths; do not modify `build-mac-install` in this task.

- [ ] **Step 5: Run GREEN**

```bash
uv run pytest -q desktop/tests/test_package_smoke_contract.py desktop/tests/test_release_manifest.py
uv run ruff check desktop/build/package_smoke.py desktop/tests/test_package_smoke_contract.py desktop/tests/test_release_manifest.py
uv run python -m compileall -q desktop/build/package_smoke.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add desktop/build/package_smoke.py desktop/tests/test_package_smoke_contract.py desktop/tests/test_release_manifest.py Makefile
git commit -m "test(desktop): smoke dynamic packaged ports"
```

### Task 6: Run the bounded defect pass and reconcile stale contracts

**Files:**
- Modify only files implicated by a reproduced product defect.
- Modify: `docs/TODO.md`
- Modify: `docs/5-CONFIGURATION/onp-env-reference.md`
- Modify: `docs/7-DEVELOPMENT/phase-5-advanced-memory.md`
- Create: `.superpowers/sdd/final-local-release-report.md`

**Interfaces:**
- Documentation authority: Agent FSM unset default is `on`; the newly built app is not called installed until hash equality proves it.
- Product defect threshold: deterministic reproduction in a supported surface, not a test fixture, package-index timeout, local signature, or unavailable feature boundary.

- [ ] **Step 1: Run bounded feature selectors**

```bash
uv run pytest -q tests/test_v0_8_107_runtime_features.py tests/test_source_visual_*.py tests/test_search_quality_*.py tests/test_chat_history_cap.py tests/test_source_chat_history_cap.py
cd frontend
pnpm vitest run src/lib/features.test.ts src/lib/hooks/use-runtime-features.test.tsx src/lib/hooks/use-source-visuals.test.tsx src/components/deeper-notebook/ThemeGallery.test.tsx src/components/deeper-notebook/source-gallery/*.test.tsx
```

Expected: all supported contracts pass. If a product behavior fails, stop this task, add one strict regression beside the owner, record RED, implement the smallest complete repair, and rerun the entire bounded selector.

- [ ] **Step 2: Inspect explicit unavailable surfaces**

Run:

```bash
rg -n "unavailable until|coming in a later release|Phase 3|deliberately not implemented" frontend/src deeper_notebook --glob '!**/*.test.*'
```

Verify each result is honest, disabled, documented, and cannot dispatch a hidden request. Do not implement selection-aware Ask, study import, podcast Phase 3, or a reranker in this release.

- [ ] **Step 3: Correct stale documentation**

Update `TODO.md` to distinguish the staged verified package from the currently installed hash until Task 8. Remove the obsolete five-frontend-failure note because the current full suite is green. Change both Agent FSM documents from default-off to default-on with explicit `0` rollback.

- [ ] **Step 4: Write the release report baseline**

Record current commit, bounded commands/counts, confirmed defects and repairs, unavailable feature boundaries, external limitations, and the exact remaining gates. Do not claim broad or installed proof yet.

- [ ] **Step 5: Run docs/security gates and commit**

```bash
uv run python scripts/rebrand_audit.py --check
git diff --check
gitleaks protect --staged --redact
git add docs/TODO.md docs/5-CONFIGURATION/onp-env-reference.md docs/7-DEVELOPMENT/phase-5-advanced-memory.md
git add -f .superpowers/sdd/final-local-release-report.md
git commit -m "docs: reconcile final release authority"
```

Expected: rebrand reports zero unexpected/stale identities; diff and Gitleaks pass.

### Task 7: Prove the final source commit and close review findings

**Files:**
- Modify only files required by failing gates or confirmed Critical/Important review findings.
- Append: `.superpowers/sdd/final-local-release-report.md`

**Interfaces:**
- Produces one reviewed source HEAD eligible for packaging.
- No package command runs until every source gate below is green.

- [ ] **Step 1: Run complete frontend gates**

```bash
cd frontend
pnpm vitest run
npx tsc --noEmit
npm run lint
npm run build
```

Expected: all test files/tests pass, TypeScript and build exit 0, ESLint has zero errors.

- [ ] **Step 2: Run browser matrices serially**

Use unique ports and never overlap Next builds:

```bash
CI=1 PLAYWRIGHT_PORT=4161 NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser
CI=1 PLAYWRIGHT_PORT=4162 NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser --grep 'explicit rollback'
CI=1 PLAYWRIGHT_PORT=4163 NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser
CI=1 PLAYWRIGHT_PORT=4164 NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 NEXT_PUBLIC_DN_SOURCE_VISUALS=0 npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser
```

Expected: enabled matrices and dedicated rollback cells pass with no unexpected/external browser requests and within recorded CLS/bundle budgets.

- [ ] **Step 3: Run backend and real-Surreal gates**

```bash
uv run pytest tests/ -q --ignore=tests/integration
SURREAL_INTEGRATION=1 uv run pytest tests/integration/ -q
```

Expected: both exit 0; no failed-test retry is accepted as final evidence.

- [ ] **Step 4: Run static, identity, and security gates**

```bash
uv run ruff check api deeper_notebook desktop tests
uv run ruff format --check api deeper_notebook desktop tests
uv run python -m compileall -q api deeper_notebook desktop tests
uv run pytest -q tests/test_product_identity.py
uv run python scripts/rebrand_audit.py --check
git diff --check
gitleaks git --redact --log-opts='34ef47cd..HEAD'
```

Expected: all exit 0; rebrand has zero unexpected/stale; Gitleaks reports no leaks in the release range.

- [ ] **Step 5: Request fresh review and repair findings test-first**

Provide the design, plan, `34ef47cd..HEAD` diff, global context, task context, and test receipts to a fresh Sol reviewer. Any Critical or Important finding gets a strict regression, focused repair, affected full-gate rerun, and separate commit. Repeat until APPROVED.

- [ ] **Step 6: Freeze packaging HEAD**

Append exact receipts and review verdict to the report. Verify `git status --short` contains only explicitly preserved report/context state, then record `git rev-parse HEAD` as the only package source authority.

### Task 8: Rebuild, verify, install recoverably, and smoke the installed app

**Files:**
- Append: `.superpowers/sdd/final-local-release-report.md`
- Update: `/Users/Antman/Downloads/DEEPER-NOTEBOOK-CLOSEOUT-HANDOFF-2026-08-20.md`
- Create outside Git: timestamped `/Applications/Deeper Notebook.app.backup-<timestamp>`.

**Interfaces:**
- Consumes: final reviewed HEAD, dynamic package smoke verifier, current installed app.
- Produces: verified `dist/Deeper Notebook.app`, verified DMG, installed app with matching executable hash, default-on and explicit-off smoke receipts, and recoverable prior app.

- [ ] **Step 1: Fail-closed preflight**

```bash
git status --short
pgrep -fl '/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook|surreal-darwin' || true
test -d '/Applications/Deeper Notebook.app'
test ! -e dist/Deeper-Notebook-mac-arm64.dmg
```

If an installed app/sidecar process is live, stop and request the user quit it; do not signal it without fresh authority. Move any old `dist` to a task-owned timestamped archive rather than deleting it.

- [ ] **Step 2: Build exactly once**

```bash
make build-mac
```

Expected: exit 0 without a failed-test retry; app and DMG exist. If a source/test gate fails, do not retry the package command—return to the owning task, repair, rerun source gates, then seek fresh package authority.

- [ ] **Step 3: Verify staged artifacts independently**

```bash
uv run python desktop/build/verify_package_contents.py 'dist/Deeper Notebook.app'
file 'dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook'
file 'dist/Deeper Notebook.app/Contents/Resources/surreal-darwin'
codesign --verify --deep --strict --verbose=2 'dist/Deeper Notebook.app'
hdiutil verify dist/Deeper-Notebook-mac-arm64.dmg
shasum -a 256 'dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook' dist/Deeper-Notebook-mac-arm64.dmg
```

Expected: manifest/version/bundle/arm64/signature/DMG checks pass and hashes are recorded.

- [ ] **Step 4: Smoke the staged app in both feature states**

Use fresh owned HOME/data roots and readiness paths:

```bash
uv run python desktop/build/package_smoke.py --executable 'dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook' --readiness-file "$TASK_ROOT/default/desktop-readiness.json" --expected-feature sourceVisuals=true --artifact dist/Deeper-Notebook-mac-arm64.dmg --receipt "$TASK_ROOT/staged-default.json"
uv run python desktop/build/package_smoke.py --executable 'dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook' --readiness-file "$TASK_ROOT/off/desktop-readiness.json" --environment DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0 --expected-feature sourceVisuals=false --artifact dist/Deeper-Notebook-mac-arm64.dmg --receipt "$TASK_ROOT/staged-off.json"
```

Expected: both receipts `status=passed`; process groups and ports are gone after each serial run.

- [ ] **Step 5: Create an exact recoverable backup**

Resolve one timestamp without repurposing system variables:

```bash
release_stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_app="/Applications/Deeper Notebook.app.backup-${release_stamp}"
test ! -e "$backup_app"
mv '/Applications/Deeper Notebook.app' "$backup_app"
```

Immediately verify the backup bundle and executable remain readable. If the move fails, stop without copying the new app.

- [ ] **Step 6: Install and verify exact hash equality**

```bash
ditto 'dist/Deeper Notebook.app' '/Applications/Deeper Notebook.app'
codesign --verify --deep --strict --verbose=2 '/Applications/Deeper Notebook.app'
test "$(shasum -a 256 'dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook' | awk '{print $1}')" = "$(shasum -a 256 '/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook' | awk '{print $1}')"
```

Expected: signature and exact executable hash match. On failure, move the incomplete new app to a task-owned quarantine path and restore `$backup_app`.

- [ ] **Step 7: Smoke the installed app in both states**

Run the same dynamic verifier serially against `/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook`, with fresh roots and receipts `installed-default.json` and `installed-off.json`. Default must report all six runtime features true and render the Gemini Forward workspace; off must report `sourceVisuals=false`, keep Sources usable, and emit no visual mutation.

- [ ] **Step 8: Prove cleanup and finalize receipts**

```bash
pgrep -fl '/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook|surreal-darwin' || true
hdiutil info | rg 'Deeper-Notebook|Deeper Notebook' || true
git diff --check
```

Expected: no owned process/listener/mount/temp root remains. Preserve the backup app. Append final source HEAD, hashes, backup path, package/install receipts, local-signature limitation, and out-of-scope release items to the report and Downloads handoff. Commit only repository-owned receipt documentation after diff/Gitleaks checks.
