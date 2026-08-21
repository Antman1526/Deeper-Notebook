# Final Local Release Design

**Date:** 2026-08-20
**Scope:** `codex/today-productization` local macOS release
**Decision:** Focused release polish, followed by a bounded defect pass, full supported-feature verification, package rebuild, recoverable installation, and installed-app smoke testing.

## Objective

Finish the current Deeper Notebook local-release line without turning the work into a broad redesign. The result must improve the most visible theme inconsistencies, preserve every established feature and rollback contract, repair any defects found by the final bounded audit, produce a verified arm64 macOS package, and replace the installed application through a recoverable procedure.

The goal is complete only when the installed application—not merely source tests or an uninstalled `dist` bundle—has passed its runtime smoke checks.

## Boundaries

This release may change application source, tests, documentation, and local packaging artifacts in the active worktree. It may replace `/Applications/Deeper Notebook.app` only after the existing application is stopped, its exact identity is verified, and a recoverable backup is created.

This release does not push or merge Git branches, publish a GitHub release, dispatch Windows CI, notarize with Apple, change external credentials, delete remote refs, or remove unrelated user work. Explicitly unfinished product features remain honest unavailable states unless the implementation plan separately proves they can be completed inside this release without widening its architecture.

## Visual Design

### Theme system

Add `gemini-forward-dark` as the dark companion to the current `gemini-forward-light` default. It uses the same indigo, violet, cyan, and mint identity on a low-glare near-black mineral canvas. It participates in the existing catalog, persistence, preview, system-theme, and accessibility contracts rather than creating a second theme mechanism.

The theme gallery retains all existing themes but reduces first-view overload. Its information architecture becomes:

1. Recommended: Gemini Forward Light/Dark, Research Core Light/Dark, Archive Paper, and the two high-contrast themes.
2. Recent: bounded locally persisted recent selections when available.
3. More themes: the remaining catalog, collapsed by default and searchable.

Search must reveal matching themes regardless of collapsed group state. Preview remains reversible and Apply remains the only persistence action.

### Semantic visual artifacts

Slide decks, infographics, and notebook Mind Map nodes must consume semantic theme roles instead of hard-coded palette values. Add or reuse named roles for artifact canvas, artifact panel, source node, note node, edge, subtle text, and status states. The roles derive from the active catalog theme and remain legible under light, dark, high-contrast, and forced-colors environments.

Success, warning, and information states must not alias brand primary/accent by default. Each state receives a distinct semantic token with a valid foreground role. Existing component APIs remain unchanged unless a small typed token interface makes the boundary clearer.

### Source Gallery

Reduce action density without removing capability:

- The cover/title becomes the primary Open action.
- Refresh visual, Remove visual, and Delete source move into one compact actions menu on gallery cards.
- Action names remain explicit to assistive technology, targets remain at least 44px, and destructive actions keep confirmation.
- Queued and processing states use a quiet theme-aware placeholder/status treatment; reduced-motion users receive no shimmer or animation.
- Compact notebook/search/capture uses remain actionless unless their existing owner explicitly supplies actions.

The existing authoritative visual receipt, identity fencing, pagination continuity, keyboard selection, evidence peek, and explicit backend-off behavior must not change.

## Functional Audit and Repair

The final defect pass is bounded by supported shipped surfaces and current release contracts:

- runtime feature defaults and partial/explicit rollback;
- Sources, Capture, Notebooks, Knowledge, Search, Studio, Podcasts, Study, Models, Settings, and MCP routes;
- source ingestion, visual lifecycle, deletion/search maintenance, hybrid search, chat/Ask FSM, theme persistence, and desktop startup/shutdown;
- real SurrealDB integration and migration rewind;
- macOS package contents, first-run bootstrap, runtime readiness, and cleanup.

The audit does not promise that deliberately unavailable features are implemented. Scoped Knowledge Ask, study-plan import, podcast Phase 3 evidence/verification, automatic ingestion enrichment, and a local reranker remain unavailable or opt-in unless a confirmed regression shows their existing boundary is dishonest or breaks another supported flow.

Every confirmed defect is repaired test-first. Test-only, fixture-only, dependency-network, signing, and external-service limitations are recorded separately from product defects.

## Runtime and Error Handling

Feature authority continues to flow from build defaults to `/api/features` runtime overrides. Valid partial updates merge atomically; malformed updates are ignored; explicit false values remain authoritative. New UI must subscribe through the existing reactive feature client.

Visual actions preserve exact source identity and one-shot mutation behavior. Failed refresh/remove operations unlock only the matching pending identity and retain the last authoritative visual state. Delete remains separately confirmed.

Theme preview failures fall back to the prior applied theme. Storage or native-bridge persistence failure does not leave the document in an unknown theme. Unknown stored theme IDs resolve through the existing safe default path.

Package installation is fail-closed:

1. Verify current installed-app identity and prove no app/sidecar process is running.
2. Verify the newly built app and DMG independently.
3. Move the existing application to a timestamped recoverable backup; do not overwrite it in place.
4. Copy the verified app to `/Applications`.
5. Verify installed hashes/signature/architecture against the staged artifact.
6. Run installed-app default-on and explicit Source Visuals-off smoke checks in isolated data roots.
7. If installed smoke fails, stop only the owned process, restore the backup, and record the failure.

User documents, databases, model libraries, and settings are never deleted or migrated destructively by this procedure.

## Verification Design

### Focused tests

- theme catalog/default/system pairing and persistence;
- gallery grouping, search, preview, Apply, Recent behavior, keyboard and accessibility;
- artifact and Mind Map semantic-token computed styles in representative light, dark, and high-contrast themes;
- Source Gallery open/menu/delete/refresh/remove, pending identity, failure recovery, 44px targets, compact actionlessness, pagination, and rollback;
- every production defect added during the bounded audit receives a strict regression.

### Full gates

- complete frontend Vitest, TypeScript, ESLint, production build, and visual budgets;
- supported Visual System and Source Gallery browser matrices in enabled and explicit-off states;
- backend unit suite excluding integration, followed by the complete real-Surreal integration suite;
- Ruff, format, compileall, product-identity/rebrand, diff checks, dependency/security checks, and Gitleaks;
- fresh code review with all Critical and Important findings closed.

### Package and install proof

- one repository-authoritative `make build-mac` after all source gates are green;
- manifest, bundle ID/version, arm64 binaries, hashes, deep signature, DMG verification and read-only mount;
- recoverable installation with installed/staged executable hash equality;
- installed default-on readiness, migrations, feature authority, Gemini Forward theme, Source Gallery, and critical navigation smoke;
- installed explicit Source Visuals-off rollback with zero visual mutations and usable legacy source flows;
- no leftover owned process, listener, mount, or temporary smoke root.

## Completion Criteria

The release is complete only when:

1. The visual changes above are implemented and reviewed.
2. No confirmed Critical or Important product defect remains in the bounded audit.
3. All focused and full required gates pass from the final commit.
4. The macOS package is rebuilt once from that final commit and independently verified.
5. `/Applications/Deeper Notebook.app` matches the verified artifact and passes both installed smoke states.
6. The prior installed app remains recoverable until the user explicitly authorizes its removal.
7. Final receipts distinguish local proof from uncompleted push, publication, Windows, Developer ID, notarization, and external security work.
