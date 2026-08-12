# All-screen visual and UX audit

Date: 2026-08-11

## Achieved coverage

`frontend/e2e/all-screen-visual-audit.spec.ts` is the deterministic Phase 7
proof for the mocked browser shell. The tracked dashboard inventory contains
19 routes. Each route runs at 320x844, 768x1024, 1024x768, and 1440x900, for
76 route/viewport visits per shell. Login and first-launch setup run at the
same four widths. The suite runs against both the default Luminous Folio shell
and an exact `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` rollback build; both builds
require exactly one visible main landmark on every route.

Every route visit checks a visible heading and main landmark, positive main
width, document overflow, duplicate IDs, visible-control bounds, and the
expected shell. The request ledger fails on unmatched same-origin API calls,
while the external-request detector uses an exact `localhost`, `127.0.0.1`,
and `::1` allowlist (including bracketed IPv6). Hostile lookalikes such as
`attacker127.0.0.1` and `notlocalhost` are covered as pure classifier tests;
they are not requested by the browser.

Representative notebook/source flows run at all four widths with bounded
loading, empty, error, recovery, and populated states. They also cover a
polite loading announcement, keyboard focus visibility and tab progression,
dialog initial focus, Escape close, focus return, reduced-motion mode,
half-width responsive-proxy overflow bounds, and interactive target floors.
Console errors, page errors, external requests, and unexpected API requests
are asserted at the end of each flow. Only controls inside the explicitly
marked Sources table scroll container may be exempted from clipping; the
container itself must be inside the viewport and genuinely scrollable, and
each exempted control must enter the container and viewport after a bounded
programmatic scroll. An unmarked overflow canary remains a failure.

## Product corrections in this repair

- Revalidated API-key and provider controls at compact widths; fixed setup
  wizard's API-key route link.
- Kept notebook/source titles and action groups shrinkable, added compact
  notebook grids, and preserved source-table access through a bounded scroll
  surface.
- Added notebook dialog trigger focus return and Escape handling.
- Contained Research Core/Folio nested rails at rollback breakpoints.
- Added compact action target floors and wrapped local-model/podcast controls.
- Added the shared exact loopback request policy and its hostile-host tests.

## Verification receipts

- Focused Vitest: 11 files, 32 tests passed.
- Default `npm run build`: passed; default mocked all-screen: 7 passed.
- Exact rollback `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build`: passed;
  rollback mocked all-screen: 7 passed.
- `npm run lint`, `npx tsc --noEmit`, and feature-build contract: passed.
- `python3 scripts/rebrand_audit.py`: passed with 0 unexpected active
  identities and an empty stale allowlist.
- No screenshots were refreshed; no visual baseline was accepted without
  inspection.

## Final repair receipt — 2026-08-11

- Rollback landmark ownership now matches the default shell: `LegacyAppShell`
  is a non-main wrapper, shared `FolioRouteFrame` and `EvidenceStudioFolio`
  own the single route main in both builds, while direct workspace/login/studio
  mains remain unchanged. Login now exposes its title as the visible h1 used by
  the route contract.
- The clipped-control audit uses only the explicit Sources marker as an
  exemption. It verifies marker viewport containment, real horizontal
  scrollability, bounded scroll reachability, and a hostile unmarked-overflow
  canary. The compact-width check is described as a half-width responsive proxy.
- Focused Vitest: AppShell 3/3, Sources 1/1, Knowledge route frames 7/7, studio
  frames 3/3 (run in isolated processes). Default and exact rollback all-screen
  Playwright: 7/7 each. Default/rollback Next builds, lint, tsc, feature-build
  contract, rebrand audit (0 unexpected active identities), and diff-check pass.
  `.last-run.json` restored to baseline SHA
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`.

## Limits

This is mocked-browser/frontend evidence, not proof of native PyWebView,
packaged-device, signing/notarization, clean-machine, hosted-CI, merge, or
push behavior. The compact-layout check uses a deterministic half-width
responsive proxy rather than changing browser zoom. Accessibility assertions are semantic and
behavior-based; no axe dependency was added. Backend/API/MCP behavior is
covered by the separate server-side test suites and is not inferred from this
visual report.
