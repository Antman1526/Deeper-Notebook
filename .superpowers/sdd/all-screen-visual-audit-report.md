# All-screen visual and UX audit

Date: 2026-08-11

## Scope

Audited the 19 tracked dashboard routes plus login and first-launch setup in the canonical Luminous Folio shell. The deterministic browser matrix exercised 320x844, 768x1024, 1024x768, and 1440x900 viewports with typed, read-only fixtures. It asserted one route heading and main landmark, positive content width, no horizontal document overflow, no clipped visible controls, no duplicate IDs, no external requests, and no console or page errors. Existing keyboard, drawer, dialog, Focus mode, high-contrast, theme, and explicit rollback suites remained part of the release gate.

## Confirmed defects and corrections

- Compact command bar: the Focus label overlapped the product title at 320px. The <=360px presentation is now icon-only while the accessible name and title remain intact.
- Notebook cards and Horizon links: long notebook names could escape their grid tracks. Flex containers now permit shrinking and retain ellipsis.
- Sources: the fixed 800px table clipped the destructive source action at phone and tablet widths. Optional metadata columns now defer to xl while title/type/action stay available.
- Research Core: nested Folio rails collapsed the knowledge workspace at 1024px and pane toolbar actions escaped at phone width. Workspace tracks are width-contained and Research Core rails remain drawers until xl.
- Route landmarks: Evidence Studio lacked a main landmark; Podcast Studio lacked a route-level h1; Local Models emitted two h1 elements. Their semantic hierarchy is now unambiguous without changing embedded component defaults.
- Nested navigation: `/settings/api-keys` marked both Settings and API Keys current, producing duplicate active-marker IDs. The navigator now selects the longest matching route only.
- API Keys: missing-model and provider-filter controls clipped at 320px. Both control groups now stack or wrap responsively.
- Local model benchmark cards: role buttons exceeded compact cards. Each role stacks at mobile widths and returns to a row at sm.

No API, database schema, authority, provider, vault, or persistence behavior changed.

## Files changed and justification

- `frontend/src/components/deeper-notebook/shell/shell.css`: compact Focus presentation.
- `frontend/src/components/deeper-notebook/shell/AdaptiveNavigator.tsx` and `shell.test.tsx`: one most-specific current route and regression.
- `frontend/src/app/(dashboard)/notebooks/components/NotebookCard.tsx` and `frontend/src/components/deeper-notebook/horizon/IntelligenceHorizon.tsx`: contain long notebook names.
- `frontend/src/app/(dashboard)/sources/page.tsx`: retain source actions without horizontal clipping.
- `frontend/src/components/deeper-notebook/ResearchCoreFolioFrame.tsx`, `frontend/src/components/vault/KnowledgeExplorer.tsx`, `KnowledgeWorkspaceLayout.tsx`, `vault.css`, and `ResearchCoreVisualSystem.test.tsx`: responsive knowledge workspace containment and breakpoint contract.
- `frontend/src/components/deeper-notebook/studios/EvidenceStudioFolio.tsx`, its test, and the Studio page test: restore the route main landmark.
- `frontend/src/components/podcasts/PodcastStudio.tsx`, its test, and the Podcast Studio route: optional route-level h1 while preserving the embedded h2 default.
- `frontend/src/app/(dashboard)/settings/api-keys/page.tsx`: compact control wrapping.
- `frontend/src/app/(dashboard)/settings/local-models/page.tsx`, its test, and `frontend/src/components/local-models/RoleBenchmarkPanel.tsx`: correct heading hierarchy and mobile benchmark controls.
- `frontend/e2e/all-screen-visual-audit.spec.ts`: deterministic route, viewport, landmark, overflow, clipping, duplicate-ID, and hermetic-request coverage.
- Seven notebook visual baselines: reviewed and refreshed solely for the accepted long-title containment correction.

## Verification

- Focused Vitest: 13 files / 103 tests passed; additional targeted suites for Podcast Studio, Local Models, shell, and Research Core passed.
- Full Vitest: 207 files / 1,486 tests passed.
- ESLint and TypeScript: passed.
- Next production build: passed, 23 routes.
- Feature build contract: passed, 3 static routes.
- All-screen audit: 4/4 tests passed, including 76 dashboard route-viewport visits plus login/setup.
- Full default mocked browser: 53 passed / 3 intentional rollback-only skips / 0 failed.
- Explicit rollback flag: 3/3 passed.
- Luminous Folio visuals: 9/9 passed after inspected updates.
- Theme gallery/high-contrast visuals: 8/8 passed.

## Limits

This phase is browser/frontend proof. Native PyWebView, isolated Surreal/API/vault proof, packaged-device smoke, signing/notarization, clean-machine, hosted CI, merge, and push are owned by the remaining release phases. No axe dependency was added; accessibility coverage is semantic and behavior-based through existing Testing Library and Playwright contracts.
