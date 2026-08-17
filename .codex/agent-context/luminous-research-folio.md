# Luminous Research Folio Execution Context

## Task 16 — active release blocker (2026-08-10)

- Tasks 12–15 are complete; the Luminous Folio is default-on at `f26da105`
  with `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` retained as the one-release rollback.
- Fresh `make build-mac` reached the backend preflight but stopped before
  producing a new artifact because six exact product-identity checks fail in
  `scripts/rebrand_audit.py`: its compatibility selector inventory no longer
  recognizes the established exact `ONP_` frontend alias contracts in
  `frontend/src/lib/features.ts`.
- `scripts/rebrand_audit.py --regenerate` correctly refused to broaden the
  allowlist automatically (`17` `ONP_` and `3` `onp-theme` groups require
  review). Do not use it as a fix. Establish the exact previous contracts,
  add a focused regression first, then make the smallest audit-only repair.
- After this is green: rerun the full `make build-mac` pipeline; validate the
  current DMG timestamp/signature/contents; perform the already approved exact
  `/Applications/Deeper Notebook.app` install; launch and verify the installed
  app separately from source/browser proof; then complete the final review.

## Task 16 repair receipt — 2026-08-10

- Root cause: the frontend semantic mapper required exactly eight public flags,
  so adding canonical `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` dropped the four existing
  `ONP_` selectors. The repair accepts additional canonical DN flags while
  requiring each established DN/ONP name exactly once and the exact ONP set;
  unknown or duplicate ONP aliases remain rejected.
- Reconciled only the exact allowlist drift: 45 same-fingerprint line shifts,
  four removed stale contexts, and six current occurrences (three existing
  compatibility contracts plus three migration-documentation entries). Updated
  the two affected contract coverage digests and pinned selector digest; no
  broad regeneration or production behavior change.
- RED regressions preceded the audit change. Commit `d81af867`
  (`fix(rebrand): preserve exact feature alias contracts`) contains only the
  audit, allowlist, and product-identity regression test changes.
- Verification: focused regressions 2/2; exact six product-identity checks 9/9
  including the parametrized seam cases; full `tests/test_product_identity.py`
  141 passed; `rebrand_audit.py --check` clean (unexpected 0, stale 0);
  regeneration-refusal tests 3/3; scoped Ruff and `git diff --check` pass.
- Open: parent must run the complete packaging/native install/release proof;
  no package build or app install was run in this repair lane.

## Task 16 Ruff release-gate receipt — 2026-08-10

- Baseline `uv run ruff check .` was 128 findings: 122 I001 import-order
  findings plus F821 `Path` and four F811 shared-fixture shadowing findings.
  RED coverage proved runtime annotation resolution and fixture registration
  before the minimal test corrections.
- Ruff `--fix` changed exactly the 83 reported files. The downloader now
  imports `Path` and checks its local annotation seam with `get_type_hints`;
  pool deadlock tests use shared fixtures without parameter shadowing. No
  production behavior or lint suppressions changed.
- Ruff-induced source line shifts caused 37 unexpected/35 stale audit rows,
  all exact existing contract occurrences (29 desktop `ONP_` anchors, five
  `OpenNotebook`, one `open-notebook-plus`, and nested-safe aliases). Updated
  only those 35 line anchors, three affected contract coverage digests, and
  the pinned selector digest; no broad regeneration or new contract.
- Commit `af0ce6ca` (`chore(lint): clear repository Ruff gate`) contains the
  83 Ruff files plus the two mechanically required audit files. Verification:
  focused downloader/pool 19 passed; full product identity 141 passed;
  audit check unexpected/stale 0/0; full Ruff clean; full pytest 4662 passed,
  66 skipped, 32 warnings; `git diff --check` clean.
- Open: parent owns packaging, native install, and final release proof. This
  lane did not build/package/install/start services.

## Task 16 lint-gate repair — active

- `uv run pytest -q` is green at `4661 passed, 66 skipped` on the release
  revision.
- The mandatory `uv run ruff check .` currently fails with `128` existing
  violations: `122` mechanically fixable import-order issues and six test-code
  correctness violations (undefined `Path` in a downloader test and fixture
  redefinition warnings in a pool-deadlock test).
- This requires a dedicated cleanup: add focused RED coverage for the six
  non-formatting cases, apply only the repository's Ruff fixes plus minimal
  test corrections, then rerun full Ruff and relevant tests. Do not waive or
  suppress lint. Package build remains blocked until it exits zero.

## Task 16 frontend route-frame repair — active

- Full frontend `npm test` after the source and lint gates produced exactly two
  failures: `src/app/(dashboard)/search/page.test.tsx` and
  `src/app/(dashboard)/podcasts/page.test.tsx` expect English accessible main
  names, while their existing test translation provider returns untranslated
  resource keys. Default-on Folio correctly derives the accessible name from
  the localized `h1`, so the pages expose `searchPage.askAndSearch` and
  `podcasts.listTitle` in that test harness.
- Establish mode/parity and i18n evidence before editing. The repair must
  preserve real localized runtime headings and one-main semantics; do not
  hard-code English labels in product code merely to satisfy a mock.

## Scope

Implement the approved Luminous Research Folio plan incrementally in this
checkout. The first bounded unit is Task 1, feature and navigation parity.

## Required reads

- `/Users/Antman/.codex/context.md` (global context; Deeper Notebook facts in
  this file are authoritative for this task)
- `docs/superpowers/plans/2026-08-09-deeper-notebook-luminous-research-folio.md`
- `docs/superpowers/specs/2026-08-09-deeper-notebook-luminous-research-folio-design.md`

## Active checkout and baseline

- Repository: `Deeper-Notebook`
- Branch: `agent/documentation-reconstruction`
- Task-1 base: `46e13127a26fa7cb87789e8d495ec7e8926f29b8`
- Working mode: current non-main branch; preserve all unrelated untracked files.

## Binding boundaries

- No backend/domain/API/database/route/command/keyboard/theme-ID changes.
- No automatic scans, mounts, imports, generation, cloud calls, or writes.
- Obsidian and Logseq remain `external_read_only`.
- Evidence is informational; explicit approval and outbound URL validation are
  unchanged.
- Do not edit `frontend/src/components/ui/*` or `frontend/src/components/settings/*`.
- New visual code belongs under `frontend/src/components/deeper-notebook/`.
- `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` defaults false until Task 15. Do not create
  a new legacy alias for this new flag.

## Task 1 expected files and completion

- `frontend/src/lib/features.ts`
- `frontend/src/lib/features.test.ts`
- `frontend/src/lib/features-build-contract.test.ts`
- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/components/deeper-notebook/shell/navigation-contract.test.tsx`
- `docs/verification/2026-08-09-luminous-research-folio.md`

Use RED then GREEN with the exact focused Vitest command in the plan. Preserve
the existing 14 navigation hrefs and the three create targets. Commit only the
Task 1 files. Write a concise result and remaining risks below before return.

## Results

### Task 1 — complete

- Status: DONE.
- Commit: `8d71b076` (`test(ui): freeze luminous folio parity contracts`).
- Changed only the six approved Task 1 files: the canonical static flag and
  tests, sidebar navigation/create exports and parity test, and the frozen
  verification receipt.
- RED command (exact):
  `cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx`
  produced the expected 3 failures (missing flag and navigation contracts)
  with 6 existing tests passing.
- GREEN command (exact): same focused Vitest command; 3 files and 9 tests
  passed.
- `cd frontend && npm run test:feature-build-contract`: exit 0; Next.js
  16.2.12 production build, TypeScript, static generation, and generated
  feature-value verification passed.
- Scoped ESLint over all changed frontend source/tests: exit 0.
- `git diff --check`: exit 0 before commit; staged diff check also passed.
- The receipt records baseline `46e13127a26fa7cb87789e8d495ec7e8926f29b8`,
  preserved dirty-file inventory, 22 route entries, 25 theme IDs, 14 sidebar
  hrefs, three create targets, and the no-opportunistic-repair rule.

Open items: Task 2 and all later redesign tasks remain pending. No native,
packaged, release, or full-regression claim is made by this Task 1 commit.

## Task 2 — visual foundation

- Base: `8d71b076`.
- Files: `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`,
  `frontend/src/lib/theme-script.ts`, `frontend/src/lib/theme-script.test.ts`,
  `frontend/src/lib/stores/display-preferences-store.ts`,
  `frontend/src/lib/stores/display-preferences-store.test.ts`, and
  `frontend/src/components/deeper-notebook/tokens.css`.
- Use RED then GREEN exactly as Task 2 specifies. Persist only the allowlisted
  wallpaper, motion, and transparency enums. Do not delete or alter current
  theme storage or any of the 25 stored theme identifiers. Do not enable the
  new shell or touch the existing visual fallback.
- Required final gates: focused tests, theme/provider tests, build, and diff
  check. Commit Task 2 only and append detailed receipts here.

### Task 2 — complete

- Commit: `89b0b2dc feat(ui): add luminous display preferences and typography`.
- RED reproduced missing store/pre-hydration behavior; GREEN was 2 files/11
  tests. Theme/provider compatibility: 7 files/41 tests; scoped ESLint,
  production build, and diff checks passed.
- Independent review approved with no findings. Existing theme storage,
  `dn-theme`/`onp-theme` precedence, and all 25 stored theme identifiers remain
  intact.

## Task 3 — notebook primitives

- Base: `89b0b2dc`.
- Create only the planned `frontend/src/components/deeper-notebook/folio/*`
  primitives, their focused test, and downstream barrel/README updates.
- No feature logic, fetches, stores, dialogs, routes, or page changes. Use only
  semantic existing tokens plus `--dn-*` tokens. Implement keyboard-operable
  tabs, semantic landmarks, 44px targets, and no invalid label nesting.
- Use RED then GREEN from Task 3; run scoped lint, TypeScript, and diff check.

### Task 2 — complete

- Status: DONE.
- Commit: `89b0b2dc` (`feat(ui): add luminous display preferences and typography`)
  on base `8d71b076`.
- Changed only the seven approved Task 2 files: display-preference store and
  tests, pre-hydration theme script and tests, self-hosted font layout, global
  font tokens, and Luminous material/motion CSS tokens and guards.
- Exact RED command:
  `cd frontend && npm exec vitest run src/lib/theme-script.test.ts src/lib/stores/display-preferences-store.test.ts`
  failed as expected with the absent store module and two pre-hydration
  assertion failures.
- Exact GREEN command: same focused Vitest command; 2 files and 11 tests
  passed.
- Theme/provider plus visual compatibility command passed 7 files/41 tests;
  scoped ESLint passed; `cd frontend && npm run build` passed Next.js 16.2.12
  compilation, TypeScript, and 23 route generation; `git diff --check` and
  staged diff check passed.
- The store persists only the allowlisted wallpaper (`aurora|static|off`),
  motion (`system|full|reduced`), and transparency (`frosted|solid`) fields.
  The pre-hydration script resolves OS reduced motion before React and defaults
  safely without deleting legacy theme storage. Existing 25 theme IDs and the
  disabled Luminous shell flag remain unchanged.
- Full report: `.superpowers/sdd/task-2-report.md`.

Open items: later Luminous Folio tasks and native/browser/package/release proof
remain pending; no full-regression or runtime visual claim is made here.

## Task 3 — complete

- Status: DONE. Base `89b0b2dc`; commit `e40c5c76` (`feat(ui): add living
  folio primitives`). Only the 12 approved downstream files changed:
  `frontend/src/components/deeper-notebook/folio/{FolioPage,FolioSpread,FolioIndex,FolioTab,MarginNote,EvidenceInsert,FolioState,FolioRouteFrame,folio.css,folio.test.tsx}`,
  the downstream `index.ts` barrel, and `README.md`.
- The primitives use semantic HTML and existing/`--dn-*` tokens only. Page and
  route frame keep one heading-associated landmark; Spread provides a labelled
  context lens; Index/Tab is controlled with Arrow/Home/End roving focus and
  44px targets; MarginNote/EvidenceInsert use complementary landmarks; receipt
  actions are outside any form label; State supports loading/empty/error/
  offline/permission with status/alert semantics. No fetch, store, dialog,
  route, feature logic, approval, external-vault, or authority code was added.
- RED exact command:
  `cd frontend && npm exec vitest run src/components/deeper-notebook/folio/folio.test.tsx`
  failed 4/4 before implementation. GREEN exact command passed 1 file/4
  tests. Scoped ESLint, `npm exec tsc --noEmit`, `npm run build` (23 routes),
  `git diff --check`, and staged diff check all passed.
- Full report: `.superpowers/sdd/luminous-task-3-report.md`. Existing unrelated
  untracked context files and `desktop/build/__pycache__/` remain untouched.

Open: Task 4+ shell/page integration and full browser/native/package/release
proof remain pending; stylesheet runtime is build-verified but the focused
Vitest test mocks the repository PostCSS plugin failure for component CSS.

## Task 3 review repair — complete

- Status: DONE. Commit `9e13b844` (`fix(ui): isolate folio stylesheet import`)
  removes the `folio.css` side-effect import from
  `frontend/src/components/deeper-notebook/index.ts`, adds the stylesheet once
  at `frontend/src/app/layout.tsx`, and removes the stylesheet mock from
  `folio.test.tsx`. This preserves production Next styling and prevents
  unrelated barrel consumers such as ChatPanel from loading component CSS in
  Vitest. No folio semantics or product behavior changed.
- RED exact command:
  `cd frontend && npm exec vitest run src/components/source/ChatPanel.cancel-run.test.tsx src/components/deeper-notebook/folio/folio.test.tsx`
  failed both suites on the barrel's `Invalid PostCSS Plugin` side effect.
  GREEN exact command passed 2 files / 6 tests. Scoped ESLint, `npm exec tsc
  --noEmit`, `npm run build` (23 routes), `git diff --check`, and staged diff
  check all passed.
- Repair evidence appended to `.superpowers/sdd/luminous-task-3-report.md`;
  unrelated dirty/untracked files remain preserved.

Open: later Luminous shell/page integration and full browser/native/package/
release proof remain pending.

## Task 4 — reversible Luminous shell

- Base: `9e13b844`.
- Create only the shell modules named in the plan and add the thin AppShell
  switch/test. Reuse current navigation, create dialogs, sign-out, theme,
  language, Gmail, local-model health, desktop version, banners, guided tips,
  and global audio player; do not duplicate their logic or change their
  semantics.
- The new shell renders only when `isLuminousFolioEnabled()` is true. The
  current AppShell body remains a private legacy fallback, tested in both modes.
- Preserve existing `data-guided-tip-anchor` attributes and the
  `onp-sidebar-active` compatibility identifier where used by fallback code.
- Mobile must use accessible dock/navigation/lens adaptations; never add a
  request, scan, mount, generation, or write on shell mount.
- Use a unique report path: `.superpowers/sdd/luminous-task-4-report.md`.

### Task 4 — complete

- Commits: `9ce77b0a feat(ui): add reversible luminous application shell` and
  `d7148fe6 fix(ui): repair luminous shell parity`.
- RED preceded implementation. Final parity: 10 files/68 tests, scoped lint,
  TypeScript, Next build (23 routes), and range diff check passed.
- Independent review found then cleared three Important issues: mobile utility
  availability, unique `/search` guided-tip anchor, and Radix Create-menu
  keyboard/dismissal parity. A generated report was removed from rewritten
  local history and remains ignored/untracked. Final review approved.

## Task 5 — display controls and guided orientation

- Base: `d7148fe6`.
- Add only downstream `DisplayPreferencesPanel`, focused tests, a surgical
  settings-page insertion, and versioned guided-tip catalog/test updates.
- All controls must be keyboard operable, immediately change the existing root
  display attributes, persist only through the existing display preference
  store, and leave theme selection unchanged. Tips remain non-modal,
  dismissible, disableable, replayable, and suspended under dialogs.
- No new network request, dialog, route, approval, scan, mount, generation, or
  external-vault behavior. Use unique SDD paths beginning `luminous-task-5-`.

### Task 5 — complete

- Commit: `87075ee9 feat(ui): add folio display and guidance controls`.
- RED preceded implementation; focused settings/theme/guided-tip coverage was
  7 files/33 tests, shell compatibility 2 files/6 tests, with lint, TypeScript,
  build (23 routes), and diff checks green. Independent review approved.
- Review caveat for final visual/mobile testing: on narrow Luminous layouts,
  route anchors in a closed CSS-hidden index can defer visual tip placement
  until the index opens. It is not a behavior or safety regression.

## Task 6 — Intelligence Horizon dashboard pilot

- Base: `87075ee9`.
- Create only the planned pure downstream `IntelligenceHorizon` component and
  test; keep dashboard hooks/navigation/dialog wiring in the page and replace
  only its presentation JSX with one component call.
- Preserve the four exact actions (Studio, New Notebook, Podcast, Ask), recent
  links, status/offline/loading/empty states, command hint, data-path copy,
  and zero actions/requests on mount. The component owns no fetches or stores.
- Use Folio primitives. The page remains compatible with both shell flags. Use
  `luminous-task-6-brief.md` and `luminous-task-6-report.md` only.

## Task 4 — complete

- Status: DONE. Base `9e13b844`; implementation commit is recorded in the
  parent handoff. Added only the downstream shell modules, shell parity tests,
  private `LegacyAppShell` switch, barrel exports, app-level shell stylesheet
  import, and the unique Task 4 report.
- The canonical flag controls the branch: false renders the unchanged legacy
  body and true renders `LuminousAppShell`. `AdaptiveNavigator` consumes the
  existing `getNavigation` (14 hrefs) and `CREATE_TARGETS`; exact/child active
  matching, all guided-tip anchors, and `onp-sidebar-active` are preserved.
  Existing create-dialog handlers, auth logout, ThemeSwitcher,
  LanguageToggle, GmailSidebarButton, LocalModelHealthBadges,
  `readDesktopVersion`, command shortcut, four banners, GuidedTipsProvider,
  and GlobalAudioPlayer are composed without duplicated service logic.
- Mobile CSS provides a bottom tool row, accessible navigator sheet toggle, and
  on-demand Context Lens overlay; desktop CSS keeps dock/navigator/lens within
  the approved dimensions. The shell adds no shell-owned request, scan,
  generation, write, route/API/DB/command/keyboard/theme-ID/authority path.
- Exact RED focused Vitest run failed on missing `LuminousAppShell` and the
  unimplemented flag-on branch. GREEN focused run passed 2 files/3 tests. The
  required AppSidebar/banner/GuidedTips/CommandPalette/build-contract matrix
  passed 10 files/65 tests. Scoped ESLint, `tsc --noEmit`, Next build (23
  routes), and diff checks passed. Full report:
  `.superpowers/sdd/luminous-task-4-report.md`.
- A direct shell stylesheet import initially caused the known shared-barrel
  PostCSS regression; moving the import once to `frontend/src/app/layout.tsx`
  closed it. Browser/native/package/release proof remains open.

## Task 4 review repair — complete

- Status: DONE pending commit. Repair scope is limited to
  `CommandBar.tsx`, `InstrumentDock.tsx`, `shell.css`, `shell.test.tsx`, and
  the Task 4 report. Narrow-screen utilities remain accessible; the canonical
  AdaptiveNavigator owns the sole `/search` guided-tip anchor; and the create
  menu uses the existing Radix DropdownMenu with Source/Notebook/Podcast
  callbacks and keyboard/outside dismissal semantics.
- Focused shell run passed 1 file/4 tests. Required matrix including
  `GuidedTipsProvider.test.tsx` passed 10 files/68 tests. Scoped ESLint,
  `npx tsc --noEmit`, Next 16.2.12 build (23 routes), and `git diff --check`
  passed.
- Unrelated dirty/untracked files remain untouched. Browser/native/package/
  release proof remains open.

## Task 4 report-history repair — complete

- Rebuilt only commits after `9e13b844` without the ignored report:
  `9ce77b0a` (shell product/tests) and `d7148fe6` (shell review repair).
  Product/test trees compare cleanly to the pre-rewrite range; no unrelated
  paths were touched.
- `git log 9e13b844..HEAD -- .superpowers/sdd/luminous-task-4-report.md` is
  empty; the report remains ignored/untracked. `git diff 9e13b844..HEAD
  --check` passes. Post-rewrite matrix is 10 files/68 tests; scoped ESLint,
  `npx tsc --noEmit`, and Next 16.2.12 build (23 routes) pass.
- Report receipt appended locally to `.superpowers/sdd/luminous-task-4-report.md`.

## Task 5 — complete

- Status: DONE. Base `d7148fe6`; commit `87075ee9` (`feat(ui): add folio
  display and guidance controls`). Only the six approved product/test files
  changed: downstream `DisplayPreferencesPanel` plus tests, one settings-page
  import/insertion, and guided-tip catalog/provider tests.
- The panel uses labelled, keyboard-operable native selects for Wallpaper,
  Motion, and Transparency. Changes synchronously mirror the existing root
  display attributes, persist only through `dn-display-preferences-v1`, honor
  OS reduced motion, and leave the catalog theme attribute/storage unchanged.
  No settings primitive, network request, dialog, route, approval, scan,
  mount, generation, or external-vault behavior changed.
- Five existing route tips are versioned to 2 with the approved orientation:
  Instrument Dock, Notebook Index, Context Lens, Evidence Inserts, and Podcast
  production review. Provider behavior remains one-at-a-time, non-modal,
  dismissible, globally disableable, replayable, and dialog-suspended.
- Genuine RED preceded implementation. GREEN focused settings/theme/guided-tip
  matrix: 7 files/33 tests; shell/AppShell matrix: 2 files/6 tests. Scoped
  ESLint, `npx tsc --noEmit`, Next 16.2.12 build (23 routes), and diff checks
  pass. Full report: `.superpowers/sdd/luminous-task-5-report.md`.
- Open: browser, native, packaged, install, deployment, and release gates
  remain for later plan phases. Unrelated dirty/untracked files were preserved.

## Task 6 — complete

- Base `87075ee9`; Task 6 adds only the downstream `IntelligenceHorizon`
  component/test and the dashboard page/test presentation handoff. The page
  retains notebook/system hooks, route callbacks, and create-dialog wiring;
  the child owns no hooks, stores, fetches, writes, dialogs, or authority.
- The Horizon uses FolioPage/Spread/State/MarginNote/EvidenceInsert and keeps
  Studio, New Notebook, Podcast, Ask, recent notebook links, ready/loading/
  offline/empty states, `/readyz` status copy, command hint, data path, and
  quiet mount behavior. Both `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` and `=1`
  focused runs pass 2 files/9 tests.
- Scoped ESLint, `npx tsc --noEmit`, Next 16.2.12 build (23 routes), and
  `git diff --check` pass. Full report: `.superpowers/sdd/luminous-task-6-report.md`.
- Open: commit and independent parent review; browser/native/package/release
  proof remains for later Luminous plan gates. Existing unrelated untracked
  context and desktop `__pycache__` paths remain untouched.

## Task 6 review repair — complete

- Repair scope remained the four Task 6 component/page source and test files.
  The Horizon now owns a full-height `min-h-0` vertical scroll region,
  separates notebook loading from readiness, renders the existing `/readyz`
  API/database/migration statuses and error/pending details, and preserves
  native modifier/middle-click behavior for Studio and Ask links.
- Genuine repair RED reproduced all four review findings with 8 failing
  assertions. GREEN focused Horizon/page suites pass 2 files/15 tests under
  both `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` and `=1`; scoped ESLint, `npx tsc
  --noEmit`, Next 16.2.12 build (23 routes), and `git diff --check` pass.
- Open: repair-only commit and parent independent review; browser/native/
  package/release proof remains outside Task 6. Unrelated dirty/untracked
  paths remain untouched.

## Task 6 review repair — committed

- Repair commit `130fa68f` (`fix(ui): restore intelligence horizon parity`)
  contains only the four approved Horizon/page source and test files. The
  ignored Task 6 report now records the commit and the complete verification
  receipt; unrelated dirty/untracked paths remain untouched.

## Task 6 mapping repair — complete

- The remaining adapter defect is fixed only in `page.tsx` and its focused
  page test. Runtime `horizonStatus` now derives solely from `useSystemStatus`;
  `notebooksLoading` remains an independent child prop, so a slow notebook
  query cannot downgrade a known ready/offline runtime to loading.
- RED was the new known-ready/slow-notebooks regression (1 failure, 5 passed).
  GREEN focused Horizon/page suites pass 2 files/16 tests under both shell
  flags; scoped ESLint, `npx tsc --noEmit`, Next 16.2.12 build (23 routes),
  and `git diff --check` pass.
- Open: mapping-fix commit and parent re-review; browser/native/package/
  release proof remains outside Task 6. Unrelated dirty/untracked paths stay
  untouched.

## Task 6 mapping repair — committed

- Mapping repair commit `d3f2c692` (`fix(ui): preserve horizon readiness
  mapping`) contains only `page.tsx` and its focused page regression. The
  report append records the commit and final verification; unrelated
  dirty/untracked paths remain untouched.

## Task 6 final direct review — complete

- The final reviewer slot remained unavailable. Sol directly inspected the
  full `87075ee9..d3f2c692` range, confirmed the four prior review repairs and
  runtime-only readiness mapping, and reran focused Horizon/page tests in both
  shell modes: 2 files/16 tests each. No remaining Task 6 blocker found.
- This direct-review exception must be surfaced in the final whole-branch
  review package.

## Task 7 — Research Core living knowledge folio

- Base: `d3f2c692`.
- Create `ResearchCoreFolioFrame` and focused test; integrate only through the
  planned KnowledgeExplorer/WorkspaceLayout/ResearchCoreHeader/vault CSS and
  visual-system test touchpoints.
- Preserve `data-testid="knowledge-workspace"`, exactly one `main`, split
  resizers, focus restoration, persisted tabs/workspaces/bookmarks, commands,
  search, overlays, drawers, and app-owned/external-read-only authority. No
  graph algorithm, API, store, or vault mutation.
- App-owned versus external-read-only cues must be textual and icon/state
  based, never color-only. Use unique `luminous-task-7-*` files.

## Task 7 — implementation receipt

- RED: `ResearchCoreFolioFrame.test.tsx` failed at collection because the
  planned frame module did not yet exist.
- GREEN: `ResearchCoreFolioFrame` owns only visual slots; KnowledgeExplorer
  retains all state, callbacks, commands, overlays, drawers, and persistence.
  The one existing main remains in KnowledgeWorkspaceLayout; the frame adds no
  landmark. The index remains the actual utility/tree region, and the lens
  remains the existing intelligence rail.
- Authority cues now combine explicit editable/read-only text with Lucide
  document/lock icons, so source authority is not color-only.
- Verification: focused 12 files/100 tests; scoped ESLint; `npx tsc --noEmit`;
  Next 16.2.12 build (23 routes); `git diff --check` all pass. The desktop
  resizer remains semantic and is positioned at the index edge rather than
  becoming a grid column.
- Commit: `6c9a1d00` (`feat(ui): frame research core as a living folio`). The
  independent reviewer slot remained unavailable, so Sol reviewed the exact
  commit diff and rechecked slot ownership, one-main semantics, desktop/narrow
  grid placement, resizer/focus preservation, authority cues, and dirty-file
  boundaries directly. No Task 7 blocker found; include this exception in the
  final whole-branch review package.

## Task 8 — Graph Atlas and evidence context lens

- RED: the new atlas module was unresolved, and focused graph, lens, and
  evidence assertions all failed for their absent landmarks/folio receipt.
- GREEN: `GraphAtlasFrame` is pure presentation. VaultGraph retains its
  viewport, relation filter, bookmark publication, graph-node navigation, and
  review-only podcast handoff. The atlas renders controls, canvas, counted
  legend, and a non-mutating inspection cue. EvidenceReceipt keeps the same
  provider, freshness, UTC retrieval, fallback text, and full fingerprint
  accessibility while using the shared compact evidence-insert styling.
- Verification: focused 5 files/10 tests; scoped ESLint; `npx tsc --noEmit`;
  Next 16.2.12 build (23 routes); `git diff --check` all pass. The existing
  mocked-browser evidence receipt test was launched three times but its runner
  hung before emitting a result; all three exact task-owned runners were
  terminated, their generated `.last-run` file restored byte-for-byte, and no
  browser result is claimed.
- Commit: `2701fedd` (`feat(ui): add graph atlas and evidence lens`). Direct
  Sol diff review found no Task 8 blocker; reviewer capacity was unavailable,
  so include this exception and the pending browser proof in final review.

## Task 9 — Evidence Studio intelligence folio

- RED: `EvidenceStudioFolio` was missing. The new page parity test then proved
  the completed slot wiring does not request generation on mount and only calls
  the existing notebook mutation after a source plus an explicit click.
- GREEN: the page still owns every hook, mutation, payload, error path, and
  router navigation. Upload/input is the Source Desk; modes/profiles are the
  Editorial Brief; existing error/generate controls are Artifact Pages; the
  Trust Margin is informational only. No backend/API/artifact state changes.
- Verification: folio/page plus Studio, artifact rail/export, citation,
  visual viewer, and run timeline tests: 9 files/60 tests. Scoped ESLint,
  `npx tsc --noEmit`, Next 16.2.12 build (23 routes), and diff checks pass.
- Commit: `9d2b5dd2` (`feat(ui): redesign evidence studio folio`). Direct Sol
  review found no behavior/scope concern; keep the same reviewer-capacity and
  browser-proof exceptions in the final review package.

## Task 10 — Podcast production folio

- RED: `PodcastStudioFolio` was unresolved. GREEN frames the existing research
  set, brief, outline, model plan, production timeline, and review message
  while PodcastStudio still owns all local state, readiness, selection,
  override, review, submit, error, retry, and cancellation behavior.
- The integration test still verifies the original four ordered studio regions,
  opening has zero readiness/submission calls, and the new production folio is
  present. Full podcast suite: 17 files/66 tests; scoped ESLint, `npx tsc
  --noEmit`, Next 16.2.12 build (23 routes), and diff checks pass.
- Native `podcast-intelligence-studio.spec.ts` was not run: its explicit 40-hex
  revision environment is absent and `curl 127.0.0.1:65060/readyz` refused the
  connection. No native proof is claimed and no runtime was started.
- Commit: `8ef8d164` (`feat(ui): redesign podcast production folio`). Direct
  Sol review found no behavior or safety regression; review/browser/native
  capacity exceptions remain for final whole-branch validation.

## Task 16 frontend route-frame repair — 2026-08-10 receipt

- RED baseline: search and podcasts page tests failed in default/on and
  `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` modes because their mocks returned the
  translation keys (`searchPage.askAndSearch`, `podcasts.listTitle`) while the
  assertions expected English labels and always requested a `main` landmark.
- GREEN: production Folio markup was already correct. The two tests now derive
  the expected `main` versus legacy `region` role from `isLuminousFolioEnabled`,
  assert the localized mock key, and verify the h1/`aria-labelledby` association.
  No production code or i18n behavior changed.
- Verification: each page test passed individually in default/on and flag-off
  modes (4/4); folio/route-frame/accessibility suite 24/24; frontend ESLint,
  `tsc --noEmit`, and `git diff --check` passed. Full `npm test` was not rerun
  per scope; parent owns the complete regression and packaging/native proof.
- Commit: `eff4ded2` (`test(ui): align localized folio route labels`).
- Open: no task-owned implementation concerns; retain unrelated untracked
  context/cache files and complete the parent release gates.

## Task 16 mocked-browser release-gate repair — 2026-08-10 receipt

- RED/root causes: baseline fixture lacked wizard cookies and redirected through
  setup; default-on runs incorrectly exercised the flag-off-only rollback spec;
  at 1280px the shell plus Research Core utility/lens rails collapsed the core
  workspace to 12px, causing heading/save pointer interception; closed Radix
  dialogs retained pointer events during exit; conflict alerts had zero-width
  text in the compact column; theme snapshots described the pre-default-on
  shell. Focused regressions were added before production fixes.
- GREEN: fixture cookies, explicit rollback skip guard (flag-off proof retained),
  compact Research Core shell media rule, important closed-dialog pointer-event
  variants, wrapping conflict alerts, and a workspace-width/closed-dialog test
  contract. Eight theme gallery PNGs were regenerated only after manual actual
  screenshot review; no production data/API behavior changed.
- Verification: mocked E2E 41 passed/1 skipped; explicit flag-off rollback 1
  passed; baseline, knowledge command, overlay, and Research Core Lab focused
  suites passed; frontend lint, `npx tsc --noEmit`, Next build (23 routes), and
  `git diff --check` passed. Tracked `frontend/test-results/.last-run.json`
  restored byte-for-byte. No package/install/service/native packaging run.
- Open: parent must review/stage this isolated frontend release-gate diff and
  run remaining desktop/native/package proof; default rollback remains an
  intentional skip unless built with `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`.

## Task 17 controlled native-runtime proof and interaction repair — 2026-08-10 receipt

- RED/root causes: the shell's informational banner layer intercepted clicks on
  the podcast close control; Knowledge `selectionchange` state updates
  rerendered the external document subtree and collapsed selected text before
  the selected-block review receipt could commit. No force-click or weakened
  assertion was used.
- GREEN commit `022dda37` (`fix(ui): preserve native knowledge interactions`):
  banner surfaces are pointer-transparent while their links/buttons remain
  interactive; `VaultDocumentView` receives stable memoized page/navigation
  props and skips focused-block-only rerenders, preserving native selection.
- Native proof: read-only vault verifier rerun exit 0 (2 expected/trust,
  1 synthesis, 4 source files, 0 changed); Surreal-backed projection tests
  47 passed; research-core native Playwright 7/7; podcast verifier exit 0,
  verifier-owned Playwright 5/5, external writes 0, source hashes unchanged;
  mocked command navigation 2/2, overlay foundation 2/2, navigation
  productivity 3/3, editor modes 4/4, Research Core Lab 7/7, theme gallery
  8/8, Folio visual 9/9, and explicit flag-off rollback 1/1. Frontend lint,
  `npx tsc --noEmit`, two Folio builds (flag on/off), and `git diff --check`
  passed. Theme baselines were manually inspected; no snapshots changed.
- Sanitized receipts remain under
  `/Users/Antman/.codex/task17-native-726197b5-20260810-162455-runtime/reports/`.
  Task-owned API/Surreal/frontend processes and synthetic roots were stopped
  and removed. Captured runtime source prehash was
  `4510a4991b783a93bfabd8acac610e191dac35d74c65dca4f6c544ee436194da`; the
  tracked-inventory method at commit boundary was HEAD
  `c8fdd265d2942fb43ef3393dbc70c27cb6d73bccadb85858c29a5a15bf82107a`,
  worktree `5707ffc168600822485f1d890e13864aecdb0f9941ddcfa43a82891b1af179e0`.
- Open/blocker: unified controlled proof could not safely run. A task-owned
  `TMPDIR` under `.codex` fails the verifier's explicit disjoint-from-home
  synthetic-root rule (`synthetic_manifest_invalid`); a realpath/writable
  `/Volumes/MainStore` fallback passed verifier path checks but backfill had no
  terminal checkpoints (`verification_unavailable`) and the API correctly
  rejected `/Volumes` vault roots (`vault_root_invalid`). No security rule or
  production verifier was relaxed. Podcast semantic-selection remains the
  verifier's explicit `verified_unified_embedding_index_required` subcheck.

## Task 18 local packaging + installation receipt — 2026-08-10

- Revision-bound proof at HEAD `022dda37`: mocked E2E 41 passed/1 skipped;
  `make build-mac` exit 0 with desktop 792 passed/2 skipped, backend 3917
  passed/1 skipped, and Next 23 routes. Fresh arm64 ad-hoc app/DMG identity
  `com.antman1526.open-notebook-plus` / `0.8.95`; app executable SHA-256
  `9886ec5e955eb4f223df0b77f9f3b202d4194bb4256e5fa6880b92a6ba5d5430`, DMG
  SHA-256 `844499fddcce4f7ed3b7f9be5d94b2d9fddc8c610696964f6e4c9d910cf95393`.
  Deep/strict codesign, read-only DMG mount/layout, hdiutil verify, and the
  frozen package-content verifier passed; `spctl` rejection is expected for
  local ad-hoc signing. Build-generated `desktop/requirements.lock` drift was
  restored byte-for-byte.
- Safe install replaced only `/Applications/Deeper Notebook.app` after
  validation. Original backup is
  `/Applications/Deeper Notebook.app.backup-task18-20260810-173703`; installed
  executable hash matched the fresh artifact, Info.plist identity/version
  matched, and no quarantine xattr was present. User data under
  `~/.deeper-notebook` was untouched.
- Revision-bound tracked-source fingerprint was
  `8e9db65dcf5ccb0bee0f4200e3197f348370e3c19125e66f304e1824e7248d80` before
  and after packaging (HEAD tree
  `431ee5afa4e9c408434bef102172c6f2bfd7ba72`); no tracked source changes
  remain.
- Disposable isolated installed smoke (provider `none`, model target blocked
  by `/dev/null`) exercised real service paths: installed `GET /readyz` returned
  200 with database online; installed Next root returned `/setup-wizard` and
  followed HTML was 29,020 bytes with `__next_f`. PyWebView did not emit
  `desktop-readiness.json` before the launcher exited in this automation
  session; exact orphaned API/Surreal/Next children were terminated and
  verified absent. The task root and temporary environment were removed; no
  tracked source changes were made.
- Open concerns: ad-hoc Gatekeeper rejection is informational/expected;
  PyInstaller emitted nonfatal `aiohttp._helpers` and sharp/libvips rpath
  warnings; local-model feature behavior was not claimed under the isolated
  `provider=none` smoke.

## Task 19 strict final acceptance audit — 2026-08-10

- Route/source matrix: `/podcasts`, `/transformations`, `/settings`,
  `/settings/api-keys`, `/settings/local-models`, `/settings/mcp`,
  `/settings/launcher-prefs`, `/advanced`, and `/setup-wizard` use
  `SystemRouteFrame`; `/login` uses `AuthFolio`. The focused 12-file route,
  accessibility, preferences, and feature-contract matrix is 64/64 with the
  default Folio and 64/64 with `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`. The
  flag-off RED was one stale transformations test expecting `main` while the
  production rollback correctly renders a named `region`; the test now derives
  the role from the feature flag. No production source behavior changed.
- Dense settings contracts are source/test-backed by `DisplayPreferencesPanel`
  root `data-dn-transparency="solid"` and `data-dn-motion="reduced"` tokens,
  prefers-reduced-motion guards, and the focused preference/accessibility
  tests. `/settings/api-keys`, `/advanced`, and `/login` have source/build/full
  test coverage but no dedicated page test in this matrix; no manual UI claim
  is made.
- Backend gates: `uv run pytest -q` 4662 passed/66 skipped/32 warnings;
  `uv run ruff check .` clean; desktop tests 792 passed/2 skipped/4 warnings.
  Static/verifier subset (read-only vault, podcast, unified knowledge,
  evidence approval/artifacts, claim, podcast selection) passed 183 with 8
  warnings.
- Frontend gates at this revision: `npm test` 192 files/1407 passed;
  `npm run lint`, `npx tsc --noEmit`, `npm run build` (23/23 routes), and
  `npm run test:feature-build-contract` passed. Mocked E2E 41 passed/1
  skipped; theme gallery 8/8; Folio visuals 9/9. After each Playwright run,
  `frontend/test-results/.last-run.json` was restored byte-for-byte to HEAD
  (`5fca3f84bc7b9240b2963858fe2f32f7c515a8d4`).
- Native/package/install evidence is historical Task 17/18 evidence, not
  rerun here. Task 17 unified controlled proof remains blocked by its explicit
  safe-root/backfill/API policy mismatch, and Task 18 installed smoke did not
  produce a PyWebView readiness marker; ad-hoc Gatekeeper rejection remains
  expected. These facts prevent claiming full Task 16/native-window acceptance
  despite green code/browser gates.
- Worktree change from this audit is the narrow test-only rollback parity fix in
  `frontend/src/app/(dashboard)/transformations/page.test.tsx`; unrelated
  untracked contexts/cache are preserved. No receipt doc or commit was created.

## Deeper Notebook Task 20 unified native proof refresh — 2026-08-10

- Revision-bound HEAD was `ce6bf2848068e3135e19e8457f3d05e40f16ba20`; no
  tracked source edits were made. The tracked-inventory SHA-256 at final
  cleanup was `68b7f6feb8099fe97342caa3b078d9a546936e4c7a01b49a2c45ab190c4e0508`.
  Critical verifier/backfill/vault source hashes matched HEAD before/after:
  `scripts/verify_unified_knowledge_engine.py`=`1e635b1…`,
  `knowledge_engine/backfill.py`=`31e4add…`,
  `vault/repository.py`=`ca90606…`, `vault/service.py`=`38ab55f…`.
- A unique real, no-symlink root under `/Users/Shared` passed ancestor,
  writable/sticky, and API `approve_vault_root` checks without elevated
  permissions. Disposable native Surreal/API ran only on loopback ports
  `18680`/`18681`, with unique namespace/database, isolated data/log roots,
  `watch_enabled=false` mounts, and no user vault or credentials.
- The two-phase verifier used `TMPDIR` inside that task root and the approved
  exact inventory: Overlay plus parsed child equivalence spaces. Parent
  trusted-source/unsupported content was proved via mount/file/hash/trust
  evidence and intentionally excluded from equivalence, matching the prior
  approved proof contract. `--proof-phase prepare` exited 5 with
  `knowledge_engine_restart_required`; after a real API stop/start,
  `--proof-phase verify` exited 0. Restart PID/nonce changed; Overlay root
  hash and all synthetic source fingerprints were preserved; startup backfill
  completed for Overlay, parent, and child; trust replay was changed=1 then
  unchanged=1; counts were parent_files=2, child_files=2, knowledge_docs=3,
  tasks=1, graph_edges=1, backlinks=1, trust_records=1. Private report and
  restart state were mode 0600 with hashes `2857ed3db90a31b1cae887398c08b47475b0799656e399a26494e5ed7c41eb40`
  and `0563703703470d92d77576cf0175028068925dcc8fdcf1693960e803fa5510e1`.
- Focused runtime suites passed: `tests/test_verify_unified_knowledge_engine.py`
  plus `tests/test_knowledge_engine_backfill.py` = 41 passed/1 warning;
  lifespan/service/equivalence suite = 26 passed/7 warnings. `git diff --check`
  passed. Task-owned API/Surreal processes stopped; loopback ports were free;
  exact task root was moved to macOS Trash, leaving no task temp path.
- Open: this is controlled API/Surreal restart evidence, not a PyWebView or
  manual native-window claim. Existing unrelated untracked contexts/cache are
  preserved.

## Task 21 final release receipt — 2026-08-10

- Commit `8d710255` (`docs: close luminous folio release proof`) appends the
  final Task 16 evidence section to
  `docs/verification/2026-08-09-luminous-research-folio.md` only.
- The receipt binds current test-only HEAD `ce6bf284` to production/package
  revision `022dda37`, records the complete backend/desktop/frontend/browser
  totals, Task 17/20 native authority evidence, package hash/signing status,
  installed launch/restart/close smoke, rollback commands, and preserved
  untracked inventory. No source, test, package, install, or user-data change
  was made in Task 21.
- Verification: staged diff contained exactly the one receipt document;
  `git diff --cached --check` and the post-commit docs diff review passed; the
  staged sensitive-literal scan found no personal paths, port numbers, tokens,
  or secrets. Existing untracked contexts/cache remain preserved.
- Open: parent decides final acceptance. Local ad-hoc signing remains not
  notarized and the receipt records no external human visual approval beyond
  the earlier manual matrix review.

## Readiness compatibility repair — 2026-08-10

- Root cause was confirmed at both boundaries: the desktop `apiClient` adds
  `/api` to the hook's `/readyz` path, while FastAPI exposed only `/readyz`;
  the resulting 404 payload lacked `checks`, and the Horizon dereference
  reached the error boundary.
- RED preceded source edits: the real-app alias test observed root 200 versus
  `/api/readyz` 404; the hook test observed `{detail: "Not Found"}` returned
  directly instead of a safe readiness shape.
- Commit `3cf2ec69` (`fix(release): align readiness endpoint and payload guard`)
  adds the auth-exempt `/api/readyz` alias to `api/main.py`, validates the
  readiness wire shape in `useSystemStatus`, and synthesizes a generic
  `not_ready` fallback for malformed payloads. It includes only the two
  focused regressions and these source changes.
- GREEN: backend health suites `tests/test_health_endpoints.py` and
  `tests/test_healthz_deep.py` passed 15/15; frontend hook/Horizon/dashboard
  suites passed 17/17; scoped Ruff, ESLint, TypeScript, frontend build (23
  routes), and `git diff --check` passed. No package/install/restart/kill was
  performed.
- Open: parent owns rebuild and installed-app smoke rerun against this commit.
