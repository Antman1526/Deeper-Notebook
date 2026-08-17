# Working Desk Responsive Repair

## Objective

Fix the clipping visible in the user-provided 1020x631 screenshot so Working Desk text remains readable and reachable as the native app window becomes shorter or narrower.

## Authority

- Worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/study-workbench`
- Branch: `codex/study-workbench`
- Design commit: `f65ccc31 docs(ui): specify responsive working desk`
- Design: `docs/superpowers/specs/2026-08-13-working-desk-responsive-design.md`
- Plan: `docs/superpowers/plans/2026-08-13-working-desk-responsive.md`
- Screenshot: `/var/folders/7t/0h7852yd50v0kj5wrlw487980000gn/T/codex-clipboard-de3c70a0-ebca-40b0-b959-390b19e071af.png`

## Current evidence

- Baseline focused Horizon suite: 10 passed.
- `IntelligenceHorizon.tsx` currently selects action columns with viewport breakpoints (`sm:grid-cols-2 xl:grid-cols-4`).
- The actual primary column is narrowed by the surrounding navigation and Runtime Status columns; at the shown window size, four action cards are rendered at unreadably narrow widths.
- Horizon already owns a nested `overflow-y-auto` scroll region, so the fix should preserve and prove that authority rather than add resize state.

## Binding constraints

- RED before production edits.
- CSS/container-aware presentation only; no API/data/state changes.
- Keep existing text sizes, action order, callbacks, routes, accessible names, focus rings, and >=44px targets.
- No CSS zoom, transform scaling, line clamp, ellipsis, or hidden overflow.
- Browser proof at 1020x631 and 800x600 plus existing all-screen audit.
- Preserve all unrelated untracked `.codex/agent-context` files.
- Commit exact subject `fix(ui): adapt working desk to compact windows` after gates.

## Durable result

- RED before production: Horizon Vitest was 10 tests with 8 pass/2 fail on the
  absent `data-dn-horizon-page`/`data-dn-horizon-actions` hooks. The semantic
  browser matrix then reproduced the actual clipped layout at 1280x631: all
  four cards were 34px wide and text extended beyond their cards; 1020x631
  and 800x600 were retained as safeguards.
- Implementation adds presentation-only Horizon hooks, inline-size container
  authority, auto-fit action cards, a larger container-aware minimum where
  available, and bounded short-height page/cover/spread spacing. Action
  semantics, routes, callbacks, text sizes, focus rings, and min-height targets
  are unchanged.
- GREEN: focused Vitest matrix 3 files/16 passed; compact browser matrix
  3/3 (1020x631, 800x600, 1280x631); full luminous/all-screen browser gate
  19/19; TypeScript; production Next build; staged diff-check and gitleaks.
  Lint exits 0 with two pre-existing StudyVoiceTutor unused-var warnings.
- Post-scroll receipts: `/tmp/working-desk-responsive-postscroll-1020x631.png`
  shows four readable cards and Recent folios; `...postscroll-1280x631.png`
  shows the readable one-column stack and Recent folios. Initial after shots:
  `/tmp/working-desk-responsive-after-1020x631.png` and
  `/tmp/working-desk-responsive-after-1280x631.png`.
- The tracked Horizon 1440 visual baseline was refreshed intentionally for the
  readable card reflow. Only the direct four test/implementation files and
  that one affected snapshot were staged; supplied `study-task-13..19.md`
  contexts remain untracked and untouched, while this task context was updated
  as required.

## Open items

- Commit `cbf9f9c2` (`fix(ui): adapt working desk to compact windows`) is
  complete. The existing top-right Focus/Quick Actions overlap is present in
  the pre-change 1440 baseline and is outside this responsive folio scope.

## Fresh review outcome

- CHANGES_REQUIRED: runtime/CSS behavior and preserved semantics inspect clean,
  but `luminous-folio-visual.spec.ts` does not assert recorded vertical text
  bounds and its scroll proof can pass without actual overflow or viewport
  reveal. Require strict `scrollHeight > clientHeight`, increased `scrollTop`,
  and post-scroll intersection/containment checks for the lower targets.
- Fresh review gates: unit 16/16, compact browser 3/3, canonical route audit at
  320/768/1024/1440 passed. OCR preview/rules available; graph evidence absent.

## Working Desk scroll-proof repair — 2026-08-13

- Review RED receipt: a temporary assertion against the old
  `horizon-scroll-region` owner failed all three compact cases because its
  `scrollHeight` equaled `clientHeight` (872/872, 1086/1086, 1329/1329).
  This confirms the actual owner must be `document.scrollingElement`/HTML.
- `frontend/e2e/luminous-folio-visual.spec.ts` now asserts non-empty visible
  action text, horizontal and vertical text containment, action height >=44,
  HTML ownership, deterministic lower-target start below the visual viewport,
  strict document overflow, strict scrollTop increase, and final lower-target
  intersection plus full viewport containment. Production files are untouched.
- Geometry receipt for `Recent folios` heading: 1020x631 initial owner
  631/1094, target 807.656..835.656, final scrollTop 463 and target
  344.656..372.656; 800x600 600/1308, 997.828..1025.828 -> 708 and
  289.828..317.828; 1280x631 631/1447, 1200.906..1228.906 -> 816 and
  384.906..412.906.
- Final GREEN: compact browser 3/3; full luminous + all-screen browser 19/19;
  focused Horizon/Folio/Shell Vitest 16/16; `tsc --noEmit` RC0; lint RC0 with
  the two existing StudyVoiceTutor unused-var warnings. Build was skipped as
  test-only. `.last-run` restored; generated test artifacts cleaned.

## Open items

- Parent must review and commit the direct test-only repair with exact subject
  `test(ui): prove working desk scroll reachability`; supplied task contexts
  remain untracked and must not be staged.

## Final scroll-proof re-review

- APPROVED through `863917c2`. The strict actual-owner overflow/scroll advance,
  lower-target initial exclusion/final viewport containment, four-edge text
  containment, non-empty text, and 44px target assertions close the sole prior
  Important finding. Fresh compact browser matrix passed 3/3.
- OCR default rules excluded the test-only file; Code Review Graph remains
  unavailable. No production edits or remaining blocking findings.
