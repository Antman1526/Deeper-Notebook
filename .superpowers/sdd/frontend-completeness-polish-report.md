# Frontend Completeness and MCP UX Polish Report

Date: 2026-08-11
Checkout: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook`
Scoped starting revision: `bae64d07`
Verification revision: `b8c8288e`

## Outcome

The frontend completeness slice is implemented without changing backend
routers, API schemas, database authority, proxy trust, or CORS behavior. The
runtime config endpoint now fails closed for malformed forwarded protocol and
host input. MCP settings has a persistent, keyboard-accessible enabled state
per server, keeps the existing add/test/delete/reorder mutations, and wraps
rows and controls at phone and desktop widths. Rollback-only Focus specs are
gated by the canonical `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` flag. Only the three
confirmed dead files were removed.

## Changed files and reasons

- `frontend/src/app/config/route.ts`: retains explicit `API_URL` /
  `NEXT_PUBLIC_API_URL` priority and `{ apiUrl }` JSON shape; accepts only
  HTTP/HTTPS, parses the host authority with WHATWG `URL` (including bracketed
  IPv6), rejects credentials, paths, queries, fragments, whitespace, and
  malformed hosts, and returns the loopback fallback without logging raw
  input.
- `frontend/src/app/config/route.test.ts`: RED-to-GREEN coverage for explicit
  override, HTTP/HTTPS hostname and IPv4/IPv6 derivation, malformed protocol,
  comma-separated protocol, credential/path/query/fragment input, and missing
  host. The tests assert the exact public JSON shape and safe fallback.
- `frontend/src/app/(dashboard)/settings/mcp/page.tsx`: adds status text,
  `aria-pressed`, and an enable/disable button whose mutation body is exactly
  `{ enabled }`; guards duplicate clicks, preserves test/delete/reorder, and
  uses stacked rows plus a two-column phone control grid that becomes a
  wrapping horizontal control group from `sm` upward. The single shared
  update mutation is intentionally serialized while pending so React Query's
  per-call settlement callback cannot clear another row's guard.
- `frontend/src/app/(dashboard)/settings/mcp/page.test.tsx`: component RED
  coverage for current state semantics, exact PATCH body, duplicate guard,
  test/delete pending isolation, and responsive class structure.
- `frontend/src/lib/locales/*/index.ts` (all 14 locale catalogs): adds the
  four MCP labels (`enableButton`, `disableButton`, `enabledStatus`,
  `disabledStatus`) to preserve locale-key parity. The short labels currently
  use the existing English fallback wording in non-English catalogs; a future
  translation pass can replace them without changing the contract.
- `frontend/e2e/mcp-settings.spec.ts`: mocked browser proof at 320px for
  keyboard Enter toggle, exact expected MCP request set, add flow, failed Test
  isolation, row bounds, no console errors, and no unexpected MCP traffic.
- `frontend/e2e/focus-mode-rollback.spec.ts`: skips rollback-only Focus tests
  unless `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`; explicit flag-off execution remains
  required and separately verified.
- `frontend/src/components/common/ThemeToggle.tsx`,
  `frontend/src/lib/types/auth.ts`, and `frontend/src/lib/types/common.ts`:
  removed only after reference searches showed no active imports/usages;
  `ThemeSwitcher` is the active replacement and auth/common types are not
  consumed elsewhere. Build and TypeScript proof follow the deletion.
- This report records the Knip classification, receipts, and residual proof
  boundaries required for handoff.

No backend, API, schema, authority, proxy, CORS, desktop, or parent-owned E2E
files are part of this slice.

## Verification receipts

- Focused frontend Vitest (locale parity, config route, MCP page): **3 files,
  186 tests passed**.
- Full frontend Vitest (`npm test`): **207 files, 1,484 tests passed**.
- ESLint (`npm run lint`): passed.
- TypeScript (`npx tsc --noEmit`): passed.
- Next production build (`npm run build`): passed; **23/23 routes** generated.
- Feature build contract (`npm run test:feature-build-contract`): passed.
- Dedicated MCP mocked browser (`npm run test:e2e:mocked --
  e2e/mcp-settings.spec.ts`): **1 passed** (46.3s); exact request sequence,
  keyboard toggle, add, failed test isolation, 320px row bounds, and console
  cleanliness verified.
- Explicit rollback proof (`NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run
  test:e2e:mocked -- e2e/focus-mode-rollback.spec.ts`): **2 passed** (30.7s).
- Aggregate default mocked browser after the parent working-tree E2E repair:
  **47 passed, 3 skipped, 2 failed** (52 total, 2.5m). The two failures are
  outside this slice and are recorded below; the two rollback Focus tests are
  skipped by the canonical flag as intended.
- `.last-run.json` was restored byte-for-byte after browser runs. SHA-256:
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`, equal
  to the starting tracked file.
- `git diff --check`: run as the final staging gate.
- Product identity/rebrand audit (`python3 scripts/rebrand_audit.py --check`):
  passed with `unexpected_active_identity: 0` and `stale_allowlist: []`.

## Knip and dead-code classification

`npx --yes knip --reporter compact` exits 1 for intentional findings: **4
unused files, 61 unused exports, 40 unused exported types, and 14 duplicate
exports**. The dependency-only run (`npx --yes knip --dependencies
--reporter compact`) exits 0, so no dependency/unresolved/binary issue was
introduced.

The four retained file findings are deliberate:

1. `public/pdf.worker.min.mjs` is loaded through the literal worker URL in
   `src/components/source/PdfSourceViewer.tsx`; deleting it breaks PDF viewing.
2. `scripts/backfill-locales.mjs` is a one-shot maintenance utility. Its
   explicit supported use is `node scripts/backfill-locales.mjs` from
   `frontend/`; it is retained as an operator-reproducible migration tool.
3. `src/components/sources/AddSourceButton.tsx` is a documented extension
   component described by `src/components/sources/README.md`.
4. `src/components/sources/index.ts` is the matching documented extension
   barrel and is retained with the public extension surface.

The remaining export/type/duplicate findings are retained and classified as
compatibility-facing component exports, route/domain schemas, test fixtures,
or shared UI barrels. They were not mechanically removed because the task
authorizes only the three confirmed dead source/type files above.

## Residuals and proof boundaries

The aggregate mocked browser still has two unrelated failures in the parent
working tree:

- `e2e/evidence-review-completeness.spec.ts:99` expects the sorted background
  request list to contain three entries:
  `POST /api/chat/context`, `GET /api/notebooks/notebook-fixture-001/suggested-questions`,
  `POST /api/chat/context`. The actual sorted list contains those entries plus
  a third `POST /api/chat/context` (four total), so the failure is a count/set
  mismatch rather than ordering.
- `e2e/knowledge-navigation-productivity.spec.ts:63` (`stale restore cancels
  unchanged then opens available targets and returns focus`) exceeds the
  30-second teardown timeout. Its browser log repeatedly reports
  `ResizeObserver loop completed with undelivered notifications.`

Those files and fixes remain parent-owned and are intentionally not staged by
this commit. The default aggregate result therefore is not a release claim;
the focused MCP and explicit flag-off receipts above are the in-scope browser
proof. A later visual audit should rerun the aggregate gate after the parent
repairs and inspect the 320/768/1024/1440 states.
