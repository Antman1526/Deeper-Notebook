# All-screen visual and UX audit

## Objective

Complete the route-by-route visual, responsive, interaction, and accessibility portion of the full release quality gate. This is a polish pass, not a redesign. Preserve APIs, schemas, permissions, authority boundaries, data behavior, all Folio features, and the explicit legacy-shell rollback.

## Required context

Read first:

- `/Users/Antman/.codex/context.md`
- `.codex/agent-context/full-release-quality-gate.md`
- `docs/superpowers/plans/2026-08-11-full-release-quality-gate.md`
- the current `git status`, HEAD, relevant existing Playwright fixtures/specs, theme tokens, Folio shell CSS, and route-frame components

## Exact route inventory

Audit these user surfaces, including the dynamic fixture routes:

- `/`, `/login`, `/setup-wizard`
- `/capture`, `/notebooks`, `/notebooks/<fixture-id>`
- `/sources`, `/sources/<fixture-id>`
- `/knowledge`, `/search`, `/studio`, `/study`, `/transformations`
- `/podcasts`, `/podcasts/studio`, `/advanced`
- `/settings`, `/settings/api-keys`, `/settings/launcher-prefs`, `/settings/local-models`, `/settings/mcp`

## Required state and viewport matrix

For every route where the state exists, cover empty, populated, loading, and recoverable error states. Exercise active dialogs/drawers/menus and their dismiss/focus return behavior. Test canonical Folio at 320x844, 768x1024, 1024x768, and 1440x900. Exercise the explicit `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` rollback on representative navigation, settings, notebook, source, and dense workspace routes.

## Proof requirements

1. Start with RED assertions for every genuine defect before production edits.
2. Use deterministic mocked routes only; no real user data, provider credentials, external network, or writes.
3. Assert no horizontal document overflow, no zero-width primary content, no clipped primary actions, no pointer interception, no duplicate landmarks/IDs, no console/page errors, and no unexpected API traffic.
4. Keyboard: Tab through primary nav and route actions; Enter/Space activate custom controls; Escape closes overlays; focus returns to the invoker.
5. Accessibility: semantic heading order, named main/region landmarks, form labels, visible focus, non-color status labels, 44px touch targets where applicable, and an automated axe scan if the installed frontend dependencies support it without adding a new dependency.
6. Media/user preferences: reduced motion, 200% browser zoom or equivalent compact layout proof, high-contrast themes, light/dark themes, static wallpaper fallback.
7. Inspect actual screenshots before changing any baseline. Refresh only a baseline that is coherent and intentionally changed by an accepted fix; document each changed image.
8. Prefer design-token/CSS/component corrections over route-specific hacks. Do not introduce a new design system or broad visual direction.

## Quality gates

- focused Vitest RED then GREEN
- focused Playwright RED then GREEN
- full frontend `npm test`
- `npm run lint`
- `npm exec tsc -- --noEmit`
- `npm run build`
- `npm run test:feature-build-contract`
- full default mocked-browser matrix
- explicit flag-off rollback matrix
- all existing visual suites without `--update-snapshots`
- `git diff --check`
- restore `frontend/test-results/.last-run.json` byte-for-byte

## Scope, commit, and receipt rules

Preserve unrelated untracked files and concurrent root work. Touch only evidence-backed UI/test files. For every file changed, record why. Commit atomically with no source outside the frontend. Write `.superpowers/sdd/all-screen-visual-audit-report.md`, append durable results and open items to this file and `/Users/Antman/.codex/context.md`, and return commit, diff summary, test totals, screenshots changed, and remaining limitations. Do not package/install/merge/push.

## Completion receipt — 2026-08-11

- Corrected evidence-backed compact layout and landmark defects across notebook cards, sources, Research Core, Evidence Studio, Podcast Studio, nested navigation, API Keys, and Local Models; no backend/schema/authority behavior changed.
- New hermetic matrix covers 19 dashboard routes at 320/768/1024/1440 plus login/setup and asserts landmark, width, overflow, clipped-control, duplicate-ID, external-request, console, and page-error contracts.
- Verification: focused 13 files/103 tests; full Vitest 207/1,486; lint, tsc, Next build 23 routes, feature contract, all-screen 4/4, default mocked 53 pass/3 intentional skips, rollback 3/3, Folio visuals 9/9, theme visuals 8/8.
- Seven reviewed notebook baselines changed only because long fixture titles now truncate inside their cards.
- Open after this phase: native/Surreal/vault/plugin proof, packaged/install smoke, independent whole-diff review, final release report.
