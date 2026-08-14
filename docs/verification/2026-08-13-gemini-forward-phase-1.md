# Gemini-forward Phase 1 verification

## Task 1 baseline

Base commit: `c98e6a23467af404e1e4f1b0a8e7f25061af9add`.

Captured before production or test edits in `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/gemini-forward-workspace` on branch `codex/gemini-forward-workspace`.

`git status --short`:

```text
?? .codex/agent-context/gemini-forward-workspace.md
```

The supplied task context is intentionally preserved untracked.

### Current route source list

The current `frontend/src/app/**/page.tsx` inventory is:

```text
src/app/(auth)/login/page.tsx
src/app/(dashboard)/advanced/page.tsx
src/app/(dashboard)/capture/page.tsx
src/app/(dashboard)/knowledge/page.tsx
src/app/(dashboard)/notebooks/[id]/page.tsx
src/app/(dashboard)/notebooks/page.tsx
src/app/(dashboard)/page.tsx
src/app/(dashboard)/podcasts/page.tsx
src/app/(dashboard)/podcasts/studio/page.tsx
src/app/(dashboard)/search/page.tsx
src/app/(dashboard)/settings/api-keys/page.tsx
src/app/(dashboard)/settings/launcher-prefs/page.tsx
src/app/(dashboard)/settings/local-models/page.tsx
src/app/(dashboard)/settings/mcp/page.tsx
src/app/(dashboard)/settings/page.tsx
src/app/(dashboard)/setup-wizard/page.tsx
src/app/(dashboard)/sources/[id]/page.tsx
src/app/(dashboard)/sources/page.tsx
src/app/(dashboard)/studio/page.tsx
src/app/(dashboard)/study/page.tsx
src/app/(dashboard)/study/plans/[planId]/page.tsx
src/app/(dashboard)/transformations/page.tsx
```

### Flag-off build baseline

Command:

```bash
NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 npm run build
```

Result: exit `0`; Next.js compiled successfully, TypeScript completed, and all 23 static/dynamic app routes generated. Build output size at capture:

```text
.next              95,220 KiB allocated (87,261,857 file bytes)
.next/static        9,444 KiB allocated ( 9,369,036 file bytes)
.next/server       49,436 KiB allocated (48,360,148 file bytes)
```

The route table reported 23 app routes including `/_not-found`, 3 API routes, and 1 middleware proxy; the checked visual manifest covers the 22 page sources listed above.

## Task 1 execution receipt

### RED

After adding only the focused flag and manifest tests (before production implementation), ran:

```bash
cd frontend
npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/lib/visual-system/route-manifest.test.ts
```

Expected failure was reproduced: `src/lib/visual-system/route-manifest.test.ts` could not resolve the missing `./route-manifest` module; `isVisualSystemV2Enabled` was not a function; and the static public-flag contract rejected the absent `process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2` reference. Existing tests remained green (`8 passed`) and the run exited `1` (`3 failed` suites/tests as expected).

### GREEN and static checks

After adding the canonical static flag, exact 22-entry manifest, recursive inventory contract, and package script, reran:

```bash
cd frontend
npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/lib/visual-system/route-manifest.test.ts
```

Result: exit `0`, `3` test files and `13` tests passed.

```bash
npx tsc --noEmit
git diff --check
```

Both commands exited `0` with no diagnostics.

### Self-review

- `isVisualSystemV2Enabled()` is the only new runtime flag authority and uses the existing static `envFlag` helper with an explicit false default; `0` and unset remain rollback/off.
- The manifest contains exactly the 22 current `src/app/**/page.tsx` sources, unique source/route keys, exact dynamic browser fixtures, and the approved phase-one route boundary.
- The package script points to the planned mocked-browser matrix without adding dependencies or changing route/domain authority.
- The verification document preserves the immutable base, pre-edit status, route inventory, flag-off build metrics, RED/GREEN evidence, and this review.

### Commit and open items

- Atomic commit subject: `test(ui): freeze visual system route contract`.
- Changed files: this verification receipt; `frontend/package.json`; `frontend/src/lib/features.ts`; its two focused tests; and the new `frontend/src/lib/visual-system/route-manifest.ts` plus test.
- Post-commit status contains only the supplied untracked `.codex/agent-context/gemini-forward-workspace.md`; no unrelated files were staged.
- No Task 2–7 implementation, browser matrix run, network/provider action, or domain/API/persisted-authority change was performed. Those remain the planned downstream work.

## Task 6 visual-system matrix receipt

Task 6 hardened the fail-closed browser fixture, exact request-frequency maps,
browser-role inspection, 44px target floor, action/text containment, horizontal
overflow checks, and explicit lower-content scroll ownership. Route-level
repairs keep compact controls readable without changing API or persisted-data
authority.

### RED evidence

- The initial boundary suite counted landmark, disabled, aria-disabled, and
  inert nodes as actions; the hostile fixture observed 9 candidates instead of
  the 4 genuine controls.
- The 1280x631 Studio route rendered four 34px mode cards with visible text
  extending beyond card bounds.
- The 320px Local Models route rendered `Save local execution policy` at
  158x44 with its no-wrap label outside the action bounds.
- Route-by-route request ledgers rejected missing stable reads for Study plan,
  Podcast Studio, Launcher Preferences, MCP, and Advanced.
- The first explicit V2-off rollback rejected an incorrectly shared V2-on
  local-model health expectation for the legacy Working Desk and Setup Wizard.

### GREEN evidence

Focused component regressions:

```text
12 test files / 104 tests passed
```

Authoritative V2 production-build matrix:

```text
280 passed / 1 expected rollback skip
```

That run contains 16 fail-closed harness contracts plus all 264 cells from the
exact 22 routes x 3 themes x 4 viewports matrix. Each active cell validates the
canonical route, theme, one visible main and h1, exact same-origin requests,
zero external requests, reduced-motion parity, image integrity, unique IDs,
44px targets, browser-derived action semantics/names, card/action/text bounds,
horizontal containment, and route-owned lower-content reachability.

The independent V2-off production build passed, followed by the explicit
legacy rollback contract:

```text
1 passed
```

Both V2-on and V2-off Next.js production builds compiled, completed TypeScript,
and generated all 23 routes. Scoped ESLint exited with no errors; TypeScript
`--noEmit` and `git diff --check` exited 0.

### Flagship visual inspection

Captured and inspected 27 full-resolution combinations for Login, Working
Desk, and Setup Wizard across Gemini-Forward Light, Research Core Dark, and
High Contrast Light at 320x844, 1020x631, and 1440x900. All retained readable
hierarchy, coherent palette behavior, lower-content reachability, and bounded
controls without gradients, glass, decorative motion, or generated imagery.
Phase 2 source-derived imagery and local cache work remains intentionally out
of scope.
