# All-screen visual and UX audit

Date: 2026-08-11

## Achieved coverage

`frontend/e2e/all-screen-visual-audit.spec.ts` is the deterministic Phase 7
proof for the mocked browser shell. The tracked dashboard inventory contains
19 routes. Each route runs at 320x844, 768x1024, 1024x768, and 1440x900, for
76 route/viewport visits per shell. Login and first-launch setup run at the
same four widths. The suite runs against both the default Luminous Folio shell
and an exact `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` rollback build; landmark counts
are mode-aware for the legacy nested-main routes.

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
half-width (200%-zoom-equivalent) overflow bounds, and interactive target
floors. Console errors, page errors, external requests, and unexpected API
requests are asserted at the end of each flow. The source table's intentional
horizontal scroll container is excluded from the clipped-control assertion.

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

## Limits

This is mocked-browser/frontend evidence, not proof of native PyWebView,
packaged-device, signing/notarization, clean-machine, hosted-CI, merge, or
push behavior. The zoom check uses a deterministic half-width viewport rather
than changing browser zoom. Accessibility assertions are semantic and
behavior-based; no axe dependency was added. Backend/API/MCP behavior is
covered by the separate server-side test suites and is not inferred from this
visual report.
