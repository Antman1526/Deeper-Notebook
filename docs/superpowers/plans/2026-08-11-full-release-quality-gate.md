# Deeper Notebook Full Release Quality Gate Plan

**Date:** 2026-08-11
**Checkout:** `/Users/Antman/Documents/Open Notebook/Deeper-Notebook`
**Starting revision:** `4c8b5a3d1fe4`
**Branch:** `agent/documentation-reconstruction`

## Objective

Perform a whole-application, evidence-backed debug, security, performance,
code-quality, completeness, plugin-extension, and visual-polish pass without
breaking existing public APIs, persisted schemas, authority boundaries, or
working user flows. Repair confirmed defects in place, add regression coverage,
and finish with a release-quality evidence report.

## Non-negotiable constraints

- Preserve all existing public API paths, request/response contracts, database
  schemas, stored identifiers, external-vault authority rules, and user-facing
  workflows unless a reproducible defect requires a compatible correction.
- Call out every intentional behavior change as a bug fix and retain a rollback
  path.
- Preserve unrelated dirty and untracked user state. Never reset or broadly
  clean the checkout.
- Do not touch real vault content, credentials, model files, or user data during
  tests. Native proof must use isolated disposable roots and unique namespaces.
- Measure before optimizing. Do not add caches, memoization, indexes, or
  concurrency merely because they appear theoretically useful.
- A touched file must map to a documented finding, regression test, measured
  improvement, documentation requirement, or proof receipt.
- Separate unit/static proof, mocked-browser proof, native-runtime proof,
  package proof, installed-app proof, signing/notarization, and human visual
  review. Never collapse one into another.

## Phase 1 — Freeze scope and inventory

1. Record branch, revision, tracked-tree fingerprint, dirty-state inventory,
   runtimes, manifests, and available test commands.
2. Build a complete route/API/domain/desktop/service/command/background-worker
   inventory from source and generated OpenAPI where available.
3. Build/update a structural code graph and identify hubs, bridges, large
   functions, surprising coupling, and untested flows.
4. Map every user-visible feature to frontend route/components, API handlers,
   domain/service implementation, persistence or external dependency, and tests.
5. Classify MCP server registration as the current plugin-extension surface and
   verify whether it satisfies registration, loading, isolation, lifecycle,
   error containment, and documentation requirements before designing anything
   new.

**Done when:** the feature matrix accounts for all routes and API routers, each
feature has an owner path and verification approach, and no source edit has
occurred without a finding.

## Phase 2 — Baseline gates

Run serially and retain exact totals/logs:

- Backend hermetic pytest and Ruff.
- Product identity/rebrand audit.
- Desktop tests with the prepared build environment.
- Frontend unit tests, ESLint, TypeScript, production build, and feature-build
  contract.
- Mocked browser functional, visual, theme, Focus-mode on/off, accessibility,
  responsive, console, and unexpected-network gates.
- Dependency vulnerability inventories for Python and npm, classified by
  reachability and compatibility risk before any upgrade.
- Secret, unsafe-deserialization, shell/process, URL/SSRF, authorization,
  unbounded-input, and sensitive-log scans.
- TODO/FIXME/HACK/XXX, skipped/xfail, commented-code, unused-export, and orphan
  inventories. Historical notes and compatibility comments are classified, not
  mechanically deleted.

**Done when:** every red gate has a reproducible failure receipt and root-cause
classification; environment/config failures are separated from product defects.

## Phase 3 — Feature-by-feature functional proof

For each feature, exercise the happy path plus meaningful empty, loading, error,
malformed-input, unavailable-dependency, cancellation/retry, and permission or
authority cases. Cover at minimum:

- Authentication, setup wizard, shell/navigation, command palette, guided tips,
  themes/display preferences, Focus mode, recovery/runtime status, and updates.
- Capture, sources, source detail/chat/insights, notebooks, notes/editor modes,
  search/Ask, transformations, study, advanced tools, exports, and settings.
- Knowledge workspace, read-only Obsidian/Logseq vault mounts, watcher lifecycle,
  graph/backlinks/tasks, overlays, provenance, unified knowledge projection, and
  no-write/source-hash guarantees.
- Research Core, web evidence, discovery/approval, research runs, local library,
  source receipts, freshness, and failover.
- Studio artifacts, revisions, workflows, mind maps, podcast creation/studio,
  audio/video overview generation, profiles, playback, and export.
- Model/provider management, local model fleet, embedding/rebuild, prompt
  optimization, memory, MCP/web-search tools, Gmail, credentials/API keys, and
  launcher preferences.
- Desktop Supervisor, bundled SurrealDB/API/worker/Next lifecycle, readiness,
  crash/retry, startup receipts, backup/restore/provenance, package layout,
  update verification, and graceful shutdown.

**Done when:** every inventory row has pass/fail/blocked evidence and all confirmed
in-scope defects have a repair task.

## Phase 4 — Targeted repairs

For each confirmed defect:

1. Preserve the minimal reproduction.
2. Add a regression test that is RED before the production change.
3. Fix the root cause with the smallest compatible change.
4. Run focused tests, adjacent contract tests, static checks, and the original
   end-to-end scenario.
5. Record why every file was touched and whether user-visible behavior changed.
6. Commit coherent repairs atomically; do not mix unrelated categories.

Security fixes must fail closed, bound hostile input, redact paths/secrets/raw
errors, preserve loopback/local-first defaults, and retain explicit authority
checks. Refactors are allowed only when tests demonstrate unchanged behavior and
the result materially improves clarity or removes verified duplication/dead code.

## Phase 5 — Performance

1. Measure route/build/bundle sizes, browser interaction/layout costs, backend
   endpoint latency, database/query counts where observable, startup milestones,
   and memory/process lifecycle.
2. Prioritize only material bottlenecks in common or release-critical flows.
3. Add performance contracts or deterministic bounds where practical.
4. Re-measure the same scenario and record before/after evidence and tradeoffs.

**Done when:** each optimization has a measured benefit or is deliberately
rejected as unjustified; no speculative micro-optimization remains.

## Phase 6 — Plugin extension system

Treat registered MCP servers as the preferred existing plugin architecture if
end-to-end evidence confirms:

- authenticated registration/update/delete and safe URL validation;
- explicit enable/disable and per-conversation tool suppression;
- bounded discovery and invocation timeouts;
- tool-name/input validation and result-size limits;
- failure isolation so one server cannot break chat or startup;
- lifecycle test/probe/status visibility;
- a minimal local example plugin and operator/developer documentation.

Only add an internal plugin runtime if the MCP surface cannot satisfy the stated
requirements. Any new extension architecture must be additive, opt-in, bounded,
and must not execute arbitrary code merely because files exist in a directory.

## Phase 7 — Visual and UX audit

Audit all routes and meaningful empty/loading/error/populated states at 320, 768,
1024, and 1440 pixel widths in both Folio and rollback shells where applicable.
Check keyboard-only traversal, focus visibility/order, landmark/headings,
dialog focus/return, reduced motion, 200% zoom, touch targets, contrast, overflow,
loading announcements, error recovery, no pointer interception, and console or
unexpected-request errors. Refresh visual baselines only after inspecting the
actual image and documenting the intentional change.

## Phase 8 — Integrated release proof

After repairs:

- Rerun the complete baseline matrix.
- Run isolated real SurrealDB/API/worker/Next and native PyWebView scenarios.
- Prove read-only vault source fingerprints and external writes remain unchanged.
- Build and verify the macOS `.app` and `.dmg`, deep-sign validation, package
  contents, launch/readiness, graceful cleanup, and recoverable install swap.
- Keep notarization, Gatekeeper acceptance, clean-machine proof, and manual human
  GUI review explicitly separate if unavailable.

## Phase 9 — Independent review and report

Run a fresh-context, suggestion-only whole-diff review using the structural graph
and code-review tooling. Repair any accepted high/important findings with the
same RED-to-GREEN discipline, rerun affected gates, then publish:

1. Overall application summary.
2. Complete tech stack and each component's role.
3. Full feature inventory with interaction and evidence status.
4. Changes grouped by bugs, performance, code quality, completeness, plugin
   system, and visual/UX, including every touched file and reason.
5. Scores out of 10 for functionality, code quality, performance, UX/visual
   polish, completeness, and production readiness, plus an overall grade.
6. Remaining risks, blocked proofs, and prioritized recommendations.

## Release acceptance criteria

- No unexplained failing required gate.
- No unreviewed public API, schema, persisted identifier, or authority change.
- All confirmed repaired defects have regression coverage.
- All tracked routes and API routers are represented in the feature matrix.
- Plugin/MCP extension path is demonstrably usable and documented.
- Visual proof covers every route category, state category, and required viewport.
- Native/package proof uses disposable data and leaves no task-owned listener or
  process behind.
- Final tracked diff is reviewed, scoped, secret-scanned, and passes diff checks.
- Report distinguishes completed proof from remaining external/manual limits.
