# Luminous Research Folio verification receipt

## Task 1 baseline receipt

- Date: 2026-08-09
- Repository: `Deeper-Notebook`
- Branch: `agent/documentation-reconstruction`
- Baseline revision: `46e13127a26fa7cb87789e8d495ec7e8926f29b8`
- Scope: feature-flag and sidebar navigation parity contracts only.
- Rollback: omit `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` or set it to `0`; the flag
  remains disabled by default until the approved Task 15 gate.

### Preserved dirty-file inventory

The baseline had no modified tracked files. The following user-owned untracked
paths were present before Task 1 and are intentionally preserved outside the
Task 1 commit:

```text
.codex/agent-context/deeper-notebook-research-evidence-adoption.md
.codex/agent-context/deeper-notebook-web-intelligence.md
.codex/agent-context/luminous-research-folio.md
.codex/agent-context/research-evidence-ui.md
desktop/build/__pycache__/
```

### Current route-entry inventory

The baseline contains these route entry points:

```text
/ (frontend/src/app/page.tsx)
/login
/advanced
/capture
/knowledge
/notebooks/[id]
/notebooks
/ (dashboard root)
/podcasts
/podcasts/studio
/search
/settings/api-keys
/settings/launcher-prefs
/settings/local-models
/settings/mcp
/settings
/setup-wizard
/sources/[id]
/sources
/studio
/study
/transformations
```

The existing sidebar navigation contract retains this exact href order:

```text
/sources
/capture
/notebooks
/knowledge
/search
/studio
/podcasts
/study
/settings/api-keys
/transformations
/settings
/settings/mcp
/settings/launcher-prefs
/advanced
```

The create targets remain `source`, `notebook`, and `podcast`.

### Current theme IDs

```text
research-core-dark
research-core-light
deep-ocean
graphite-lab
arctic-research
archive-paper
high-contrast-dark
high-contrast-light
light-blue
system
solarized-light
github-light
paper
catppuccin-latte
rose-pine-dawn
dark
midnight-aurora
tokyo-night
catppuccin-mocha
rose-pine
one-dark
gruvbox-dark
solarized-dark
dracula
nord
```

### Evidence rule

Baseline failures and pre-existing diagnostics are recorded with their exact
command and output; they are not repaired opportunistically as part of this
visual migration.

## Task 1 implementation evidence

The static `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` flag defaults to `false` and reads
only its canonical static `process.env` property. Existing sidebar hrefs and
create targets are exported for downstream shell contracts without changing
their values.

Focused contract command:

```bash
cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx
```

Result: 3 files passed, 9 tests passed.

Required gates:

| Gate | Exact command | Result |
| --- | --- | --- |
| RED | `cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx` | Expected 3 failures: missing flag export, missing static flag reference, and missing navigation exports. |
| Focused GREEN | `cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx` | 3 files passed; 9 tests passed. |
| Feature build contract | `cd frontend && npm run test:feature-build-contract` | Exit 0; Next.js 16.2.12 production contract build and generated-value verification passed. |
| Scoped ESLint | `cd frontend && npm exec eslint src/lib/features.ts src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/layout/AppSidebar.tsx src/components/deeper-notebook/shell/navigation-contract.test.tsx` | Exit 0. |
| Diff check | `git diff --check` | Exit 0. |

Self-review confirmed that the sidebar href strings, section ordering, labels,
icons, create dialog handlers, and existing feature-flag aliases are unchanged;
only the requested static flag and downstream exports were added. The new flag
has no legacy alias and remains false by default. This receipt does not claim
later redesign, native-runtime, package, or release proof.

## Task 13 resilience checkpoint

- Date: 2026-08-10
- Revision under test: `f5bb989c` plus the uncommitted Task 13 changes below.
- Scope: Luminous-shell landmark/heading semantics, reduced-motion and solid
  transparency contracts, contrast, source-approval label structure, and
  deterministic responsive browser parity.

The legacy shell remains the sole `main` landmark while the feature flag is
off. With `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=1`, the route frame owns the sole
`main` landmark and its route title is the sole level-one heading; the product
wordmark is no longer a second page heading. This keeps the fallback and the
redesigned shell accessible without changing routes or handlers.

| Gate | Exact command | Result |
| --- | --- | --- |
| RED landmark test | `cd frontend && npm exec vitest run src/components/deeper-notebook/route-frames/KnowledgeRouteFrames.test.tsx` | Expected failure: two `main` landmarks in legacy mode. |
| RED heading test | `cd frontend && npm exec vitest run src/components/deeper-notebook/shell/shell.test.tsx` | Expected failure: two level-one headings in the Luminous shell. |
| Focused unit contracts | `cd frontend && npm exec vitest run src/components/deeper-notebook/luminous-accessibility.test.tsx src/components/deeper-notebook/shell/shell.test.tsx src/components/deeper-notebook/route-frames/KnowledgeRouteFrames.test.tsx src/components/deeper-notebook/route-frames/SystemRouteFrames.test.tsx src/components/research/SourceApprovalPanel.test.tsx src/lib/themes/catalog.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx` | 7 files passed; 36 tests passed before the final fixture type correction, then rerun clean. |
| Lint | `cd frontend && npm run lint` | Exit 0. |
| TypeScript | `cd frontend && npx tsc --noEmit` | Exit 0 after adding the required fixture snippet. |
| Flag-on production build | `cd frontend && NEXT_PUBLIC_DN_LUMINOUS_FOLIO=1 npm run build` | Exit 0; Next.js 16.2.12 generated 23 routes. |
| Responsive mocked browser parity | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-parity.spec.ts --project=mocked-browser` | 4 passed at 390x844, 768x1024, 1280x800, and 1440x900. |

The browser proof used a clean locally built frontend on port 3117 and the
repository's deterministic research-workbench API fixture. The first attempt
proved the fixture must be explicitly consumed; the next attempt revealed the
intentional guided-tip overlay intercepting a pointer. The final contract
dismisses that optional tip normally, then proves the mobile navigator and
context-lens controls, desktop rail/lens visibility, one `main`, one `h1`, no
horizontal overflow, and zero console errors. It does not claim a full visual
snapshot matrix, native runtime, DMG, signing, or installed-app proof.

## Task 14 visual-matrix checkpoint

- Date: 2026-08-10
- Scope: deterministic Luminous notebook-index render baselines only.
- Fixture: fixed notebook data, guided tips disabled before hydration, pinned
  theme/display preferences, static wallpaper, reduced motion, and solid
  transparency.

The first manual inspection rejected all four candidate renders because the
desktop dock expanded utility labels into the navigation rail. The repair made
those existing controls icon-first while preserving their accessible labels and
handlers. The regenerated captures were manually reviewed at original
resolution: no dock overlap, clipping, illegible glass, or horizontal document
overflow was accepted in Research Core Dark/Light, Archive Paper, or Deep
Ocean.

| Gate | Exact command | Result |
| --- | --- | --- |
| Flag-on build | `cd frontend && NEXT_PUBLIC_DN_LUMINOUS_FOLIO=1 npm run build` | Exit 0; 23 routes. |
| Candidate snapshots | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-visual.spec.ts --project=mocked-browser --update-snapshots` | 4 reviewed baselines generated. |
| Visual regression | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-visual.spec.ts --project=mocked-browser` | 4 passed. |
| Lint and TypeScript | `cd frontend && npm run lint && npx tsc --noEmit` | Exit 0. |

This is a deliberately partial matrix. Required next surfaces remain Horizon,
Research Core, Evidence Studio, Podcast Studio, state/error variants,
high-contrast views, and mobile visual renders. It does not authorize the
Task 15 default-on switch yet.

## Tasks 14–15 visual completion and default-on rollout

- Date: 2026-08-10
- Scope: Horizon, Knowledge, and research-evidence visual baselines; resilient
  deterministic fixtures; Luminous Folio default-on with an explicit legacy
  rollback.

The visual matrix now covers the Luminous notebook index in Research Core
Dark/Light, Archive Paper, Deep Ocean, and both high-contrast themes, plus a
390px mobile viewport. It also records the Intelligence Horizon, the
read-only Knowledge workspace, and the focused Guided Research evidence
receipt. The fixtures pin theme, wallpaper, motion, transparency, onboarding,
and readiness data before hydration; the Knowledge capture waits for its
local-save state and the evidence capture scopes itself to the stable workflow
region. This prevents a splash, guided tip, or transient save state from
becoming an accidental visual baseline.

The root route no longer redirects away from Intelligence Horizon. It now uses
the existing dashboard route-group page and provider tree, preserving the
existing data hooks and create-dialog authority while making the completed
Horizon discoverable as the normal home screen.

`NEXT_PUBLIC_DN_LUMINOUS_FOLIO` now defaults to enabled. Setting it to `0`
remains a supported presentation-only rollback: no records, mounts, models,
or podcast state are migrated or altered. A dedicated browser proof validates
that the legacy sidebar and notebook route still render with that override.

| Gate | Exact command | Result |
| --- | --- | --- |
| Expanded visual baseline + replay | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-visual.spec.ts e2e/research-evidence-receipt.spec.ts --project=mocked-browser --update-snapshots` then the same command without `--update-snapshots` | 10 passed. |
| Default-on contracts | `cd frontend && npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/layout/AppShell.test.tsx src/components/deeper-notebook/route-frames/KnowledgeRouteFrames.test.tsx src/components/deeper-notebook/luminous-accessibility.test.tsx` | 5 files, 21 tests passed. |
| Default-on production build | `cd frontend && npm run build` | Exit 0; Next.js 16.2.12 generated 23 routes. |
| Default-on responsive browser parity | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-parity.spec.ts --project=mocked-browser` | 4 passed at 390x844, 768x1024, 1280x800, and 1440x900. |
| Explicit rollback build | `cd frontend && NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build` | Exit 0; 23 routes. |
| Explicit rollback browser proof | `cd frontend && PLAYWRIGHT_PORT=3117 npx playwright test e2e/luminous-folio-rollback.spec.ts --project=mocked-browser` against the override build/run | 1 passed; legacy sidebar present, Instrument Dock absent, one `main`. |
| Lint and type checks | `cd frontend && npm run lint && npx tsc --noEmit` | Exit 0. |

These are frontend/browser proof receipts only. Fresh desktop packaging,
codesigning, installed-app launch, and native runtime checks remain separate
release gates.

## Task 16 final release proof — 2026-08-10

This section separates the current revision, code gates, native authority
evidence, package integrity, installed smoke, and review limitations. It does
not treat a browser or build result as a substitute for native or package
proof.

### Revision and preserved work

- Current revision is `ce6bf284` (`test(ui): preserve transformations
  route-frame parity`). Before this documentation change, the worktree had no
  tracked diff.
- The production/package revision is `022dda37`. The exact range proof is:
  `git diff --stat 022dda37..ce6bf284` reports one file with four insertions
  and one deletion, `frontend/src/app/(dashboard)/transformations/page.test.tsx`.
  The range contains no production or package path, so the package evidence
  below remains bound to a production-identical tree.
- Preserved pre-existing untracked paths remain outside this commit:
  `.codex/agent-context/deeper-notebook-research-evidence-adoption.md`,
  `.codex/agent-context/deeper-notebook-web-intelligence.md`,
  `.codex/agent-context/luminous-research-folio.md`,
  `.codex/agent-context/research-evidence-ui.md`, and
  `desktop/build/__pycache__/`.

### Code and browser gates

| Gate | Result |
| --- | --- |
| Backend `uv run pytest -q` | 4,662 passed, 66 skipped (32 warnings) |
| `uv run ruff check .` | Clean |
| Desktop tests | 792 passed, 2 skipped (4 warnings) |
| Frontend `npm test` | 192 files, 1,407 passed |
| Frontend lint, TypeScript, and production build | Clean; build generated 23 routes |
| Feature-build contract | Passed |
| Mocked browser | 41 passed, 1 skipped |
| Theme gallery | 8/8 passed |
| Folio visual matrix | 9/9 passed |
| Route/accessibility/preference rollback matrix | 64/64 in default-on mode and 64/64 with `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` |

The tracked Playwright `frontend/test-results/.last-run.json` was restored to
its canonical generated baseline after browser runs.

### Native authority and persistence proof

- The read-only vault and podcast authority checks preserved source hashes and
  issued zero external writes; the read-only verifier reported zero changed
  source files. Research Core native Playwright passed 7/7, Podcast Studio
  native Playwright passed 5/5, and Surreal-backed projection tests passed
  47/47.
- Task 20 used a unique real no-symlink synthetic root under `/Users/Shared`,
  disabled watchers, and dedicated task-owned loopback ports. The two-phase
  unified verifier's prepare phase exited 5 with the designed
  `knowledge_engine_restart_required` barrier; after a real API/Surreal
  restart, verify exited 0. The Overlay root and source fingerprints were
  preserved, trust replay was changed once and then idempotent, and the
  approved parent/child authority contract remained intact.
- The focused unified/backfill suite passed 41/41 and the lifecycle/service/
  equivalence suite passed 26/26. Task-owned services stopped cleanly, the
  loopback ports were free, and the exact synthetic root was moved to Trash;
  no task root, watcher, user vault, credential, or external source remained.

### Package and installed-app proof

- `make build-mac` at production-identical `022dda37` exited 0: desktop tests
  were 792 passed/2 skipped, the build precondition was 3,917 passed/1 skipped,
  and the frontend build generated 23 routes.
- The fresh arm64 artifact had bundle identity
  `com.antman1526.open-notebook-plus`, version `0.8.95`, and local ad-hoc
  signing. Deep/strict code signing and `hdiutil verify` passed. DMG SHA-256:
  `844499fddcce4f7ed3b7f9be5d94b2d9fddc8c610696964f6e4c9d910cf95393`.
  The artifact is not notarized; the expected `spctl`/Gatekeeper rejection is
  informational, not a signing failure.
- The validated app is installed at `/Applications/Deeper Notebook.app`.
  The prior app remains recoverable at
  `/Applications/Deeper Notebook.app.backup-task18-20260810-173703`.
- In the normal installed user-data launch/restart/close smoke on 2026-08-10,
  the native window title was observed, the API readiness response was 200,
  the frontend readiness marker was observed, and all child listeners were
  gone after each close. The launch started the configured local-model
  services, but no content workflow was invoked. No user data was deleted.

### Review and rollback

- The final Code Review Graph range was assessed as low risk, with its static
  untested-function caveat recorded. The manual visual matrix was reviewed
  earlier and snapshots are green; there is no human external visual approval
  beyond that review.
- Presentation rollback remains `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`; for a
  rebuilt legacy presentation, run:

  ```bash
  cd frontend && NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build
  ```

- Installed-app rollback is reversible and preserves both copies. After
  quitting the app, move the current bundle aside and restore the recorded
  backup:

  ```bash
  mv "/Applications/Deeper Notebook.app" "/Applications/Deeper Notebook.app.failed-$(date +%Y%m%d-%H%M%S)"
  cp -R "/Applications/Deeper Notebook.app.backup-task18-20260810-173703" "/Applications/Deeper Notebook.app"
  ```

No database rollback, external-vault mutation, or user-data deletion is part
of this visual release.
