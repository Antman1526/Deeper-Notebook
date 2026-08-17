# Frontend Completeness and MCP UX Polish

## Confirmed gaps

1. `/settings/mcp` supports backend `enabled` updates but exposes no persistent
   enable/disable control. Server rows do not communicate disabled state.
2. The MCP row uses a single non-wrapping flex layout with four controls and can
   overflow at phone widths. Preserve add/test/delete/priority behavior.
3. The full default mocked Playwright command collects two rollback-only Focus
   specs that require `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`; the explicit rollback
   run passes, but the default aggregate gate reports two avoidable config
   failures. Gate/skip by the canonical flag without weakening explicit proof.
4. Knip reports nine orphan files. Classify rather than delete mechanically:
   - `public/pdf.worker.min.mjs` is a literal runtime URL in
     `PdfSourceViewer.tsx`; retain.
   - `scripts/backfill-locales.mjs` is a one-shot maintenance script; either
     document an explicit package command/use or remove only if its completed
     migration is proven obsolete.
   - `ClaimReviewDrawer.tsx` and `use-evaluation.ts` are owned by the approved
     evidence-review completion batch; do not touch here.
   - `AddSourceButton.tsx` and `sources/index.ts` are documented extension
     components in `components/sources/README.md`; retain unless the public docs
     are migrated in the same change.
   - `ThemeToggle.tsx` is superseded by `ThemeSwitcher` and has only commented
     references; remove with no-behavior regression proof.
   - `lib/types/auth.ts` and `lib/types/common.ts` have no imports; remove only
     after exact reference/type/build proof.
5. Generated bundle diagnostics show large uncompressed first-load totals, but
   the desktop app serves locally and no interaction regression is measured.
   Do not speculative-split. Preserve current route behavior.
6. `frontend/src/app/config/route.ts` derives the browser API origin from an
   unvalidated `x-forwarded-proto` value and `hostHeader.split(':')[0]`. The
   latter breaks bracketed IPv6 hosts, while the former can emit a malformed or
   non-HTTP(S) URL. Preserve the explicit `API_URL` override and remote-host
   auto-detection, but add RED route-handler tests and use a strict HTTP/HTTPS
   protocol plus standards-based hostname parsing with the existing safe
   fallback. Do not broaden trusted proxy or CORS behavior.

## Required behavior

- Add an accessible persistent MCP enabled switch/button per row. It must call
  the existing update mutation with only `{enabled}`, expose current state to
  assistive tech, prevent duplicate mutation, preserve test/delete/reorder, and
  remain keyboard-operable.
- Make MCP list rows and controls calm, legible, and non-overflowing at 320,
  768, 1024, and 1440 widths. Use existing design tokens/components.
- Add RED component tests for enable/disable and responsive/semantic structure,
  then GREEN. Add mocked browser proof for add, toggle, test failure isolation,
  keyboard traversal, mobile layout, no console error/unexpected request.
- Make the default mocked suite green while preserving a separately executable
  canonical flag-off rollback proof.
- Harden the runtime config auto-detection without changing its public JSON
  shape: explicit configured URL remains first priority; valid HTTP(S)
  IPv4/hostname/IPv6 requests resolve correctly; malformed protocol/host input
  falls back safely and never emits credentials, paths, or non-HTTP schemes.
- Delete only the three confirmed superseded/unused source/type files unless
  new evidence proves another orphan safe. Run Knip afterward and report every
  retained orphan with reason.
- No backend/API/schema/authority changes. No broad redesign.

## Gates

- Focused MCP/settings/shell/feature-flag Vitest RED→GREEN.
- Full frontend Vitest, ESLint, TypeScript, Next build, feature-build contract.
- Full default mocked Playwright plus explicit flag-off Focus proof; restore
  `.last-run.json` byte-for-byte.
- Knip dependency categories remain zero; reduced orphan count classified.
- Diff/rebrand checks, atomic commits, task/global context receipts.

## 2026-08-11 implementation receipt

- Scoped frontend work is complete from `bae64d07`; verification ran at
  `b8c8288e` with parent-owned changes preserved. Runtime config retains the
  explicit API URL/JSON shape, accepts strict HTTP(S) + WHATWG host parsing,
  handles bracketed IPv6, and fails closed. MCP settings has accessible
  persistent enable/disable controls, exact `{enabled}` PATCH payloads,
  duplicate guarding, responsive rows, and mocked browser proof. Focus rollback
  specs skip by `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`; explicit flag-off proof is
  green. ThemeToggle/auth/common dead files were deleted after reference/build
  evidence. Knip now reports four retained/documented files, zero dependency
  findings, and classified export/type/duplicate findings.
- Receipts: focused Vitest 3 files/186 tests; full Vitest 207 files/1,484
  tests; lint, tsc, Next build (23 routes), and feature contract pass; MCP
  mocked browser 1/1; explicit flag-off Focus 2/2. Aggregate mocked browser
  remains parent-owned residual 47 passed/3 skipped/2 failed: Evidence Review
  has one extra `POST /api/chat/context` (four actual vs three expected), and
  Knowledge Navigation stale restore times out during teardown with repeated
  `ResizeObserver loop completed with undelivered notifications.`
- `.last-run.json` restored byte-for-byte (SHA-256
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`).
- Open items: parent repairs the two aggregate browser failures and performs
  the all-screen visual audit; this slice must stage only its listed frontend,
  report, and task-context files.

## 2026-08-11 locale review repair

- Reviewer finding `b8c8288e..82d9011c`: the four new MCP labels were English
  in every non-English catalog. Replaced `enableButton`, `disableButton`,
  `enabledStatus`, and `disabledStatus` with native translations in all 13
  non-English files; `en-US` and behavior files remain untouched. Exact values
  are recorded in `.superpowers/sdd/frontend-completeness-polish-report.md`.
- Locale parity + MCP page: 2 files/173 tests passed; ESLint, TypeScript, and
  diff-check passed. Rebrand audit now reports zero unexpected active identity
  and no stale allowlist. The aggregate mocked browser residual remains
  parent-owned and unchanged.
