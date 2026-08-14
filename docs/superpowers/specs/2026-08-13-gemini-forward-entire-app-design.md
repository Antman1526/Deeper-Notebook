# Deeper Notebook Gemini-Forward Entire-App Design

**Date:** 2026-08-13

**Status:** Approved design direction; implementation requires a phased plan

**Product:** Deeper Notebook

**Scope:** Every existing user-facing page and shared application state

## 1. Decision Summary

Deeper Notebook will adopt a Gemini Notebook-inspired visual language across the
entire application without copying Google branding, icons, wording, or exact
layouts.

The approved direction is:

1. A brighter, airy, rounded, image-rich visual system becomes the default for
   new installations.
2. The existing Research Core teal direction remains the dark counterpart,
   using the same hierarchy and components.
3. High-contrast mode remains a first-class, separately verified expression.
4. Notebook and source covers use source-derived imagery first, a clearly
   labeled locally generated abstract fallback second, and a typographic
   fallback last.
5. The Visual Source Gallery and Unified Artifact Studio are the first product
   enhancements.
6. Evidence-first reading is the interaction standard beneath the visual
   redesign.
7. The Insight Canvas follows after the gallery and studio foundations are
   stable.
8. Every existing view must remain functional across themes, viewports, core
   runtime states, keyboard navigation, and explicit rollback.

This is an additive presentation and workflow program. It does not replace
source authority, notebook ownership, model routing, assistant authority,
Study scheduling, Anki semantics, or existing persistence contracts.

## 2. Inspiration Boundary

Gemini Notebook is used as product-pattern inspiration for:

- calm visual hierarchy;
- legible source collections;
- rich but restrained notebook imagery;
- a consolidated studio of source-grounded outputs;
- progressive disclosure;
- conversational access to evidence;
- visual overviews that remain connected to sources.

Deeper Notebook must remain visually and behaviorally distinct:

- the product name, iconography, navigation, copy, and component geometry are
  original;
- Research Core teal remains a recognizable Deeper Notebook mode;
- all local-first and provenance rules remain stricter than the inspiration;
- no Google assets, trademarks, screenshots, gradients, or proprietary layout
  reproductions are copied;
- no cloud image provider is introduced implicitly.

Primary references:

- <https://notebooklm.google/>
- <https://support.google.com/gemininotebook/answer/16213268?hl=en>

## 3. Goals

### 3.1 Product goals

- Make notebooks, sources, questions, and generated artifacts understandable at
  a glance.
- Give every major route a coherent, modern, calm visual hierarchy.
- Surface the value of existing capabilities instead of adding parallel,
  disconnected workflows.
- Make provenance visible through imagery, citations, evidence panels, and
  artifact metadata.
- Preserve complete keyboard, screen-reader, reduced-motion, and high-contrast
  operation.
- Make compact desktop windows and narrow mobile layouts as functional as large
  desktop layouts.
- Keep the migration reversible until the complete route matrix is green.

### 3.2 Engineering goals

- Drive the redesign through shared tokens and primitives rather than page-local
  forks.
- Keep domain logic and API contracts independent from the visual-system flag.
- Represent source imagery as rebuildable presentation metadata, never as source
  authority.
- Reuse `studio_artifact` and existing artifact viewers for the Unified Artifact
  Studio.
- Generate a checked route inventory so a newly added page cannot silently miss
  the all-view gate.
- Bound image work by type, dimensions, bytes, duration, concurrency, and local
  storage.

## 4. Non-Goals

- Cloning Gemini Notebook or using Google brand assets.
- Replacing the existing notebook, source, artifact, Study, Podcast, or model
  domains.
- Sending private source content to a cloud image service.
- Adding a remote stock-photo dependency in the initial program.
- Rebuilding every feature in a new component hierarchy before the shared
  primitives are proven.
- Auto-playing audio or video.
- Publishing, sharing, uploading, or exporting content without the existing
  explicit user action.
- Removing current themes during migration.
- Treating generated covers or visual summaries as evidence.

## 5. Complete View Inventory

The implementation starts from a generated route manifest. At approval time the
application contains 22 page views:

1. `/login`
2. `/`
3. `/advanced`
4. `/capture`
5. `/knowledge`
6. `/notebooks`
7. `/notebooks/[id]`
8. `/podcasts`
9. `/podcasts/studio`
10. `/search`
11. `/settings`
12. `/settings/api-keys`
13. `/settings/launcher-prefs`
14. `/settings/local-models`
15. `/settings/mcp`
16. `/setup-wizard`
17. `/sources`
18. `/sources/[id]`
19. `/studio`
20. `/study`
21. `/study/plans/[planId]`
22. `/transformations`

The route manifest is derived from `frontend/src/app/**/page.tsx`, normalized to
public paths, and checked into a test fixture. A test fails when the filesystem
route inventory and tested route inventory differ.

Non-page route handlers such as `/config` remain covered by their existing API
and build-contract tests but do not count as visual pages.

## 6. Visual System

### 6.1 Theme family

The redesign is one semantic component system expressed through three themes.

#### Gemini-forward light

- default for new installations;
- warm off-white canvas rather than pure white;
- soft indigo, violet, cyan, and mint accents;
- restrained gradients only in non-text imagery and decorative regions;
- rounded cards with low-elevation shadows;
- generous spacing and clear section grouping;
- high legibility at compact widths.

#### Research Core dark

- preserves the approved teal-to-cyan identity;
- uses the same component hierarchy as light mode;
- replaces large pale surfaces with deep teal layers and bounded borders;
- keeps gradients away from paragraph text and controls;
- maintains readable evidence and citation differentiation without relying on
  hue alone.

#### High contrast

- uses opaque surfaces and explicit borders;
- excludes low-contrast gradients behind content;
- uses strong focus rings and state labels;
- preserves all actions and information available in the other themes;
- supports reduced transparency and reduced motion.

### 6.2 Semantic tokens

Existing Deeper Notebook tokens are extended rather than bypassed. Components
consume semantic roles such as:

- `canvas`, `surface`, `surface-raised`, `surface-selected`;
- `text-primary`, `text-secondary`, `text-muted`;
- `border`, `border-strong`, `focus-ring`;
- `accent-primary`, `accent-secondary`, `accent-success`, `accent-warning`;
- `evidence-supported`, `evidence-mixed`, `evidence-unsupported`;
- `image-overlay`, `image-placeholder`, `image-generated-label`;
- `shadow-low`, `shadow-medium`;
- `radius-control`, `radius-card`, `radius-hero`;
- spacing and density tokens for compact, comfortable, and spacious layouts.

No feature component may use a raw competitor-inspired color value when a
semantic token exists.

### 6.3 Typography

- Preserve the current product typefaces unless a separate licensing and bundle
  review approves a change.
- Use fluid type only within bounded `clamp()` ranges.
- Never solve compact layouts by shrinking body text below the existing
  accessible minimum.
- Prefer reflow, auto-fit grids, wrapping, and scroll reachability.
- Keep generated image text out of critical UI. Titles and labels render as
  real accessible text layered over or beside imagery.

### 6.4 Motion

- Motion explains spatial changes; it does not decorate idle screens.
- Transitions are short, interruptible, and disabled or simplified under
  `prefers-reduced-motion`.
- No auto-advancing carousels.
- No parallax behind reading surfaces.
- Image loading uses a stable aspect-ratio box to prevent layout shift.

## 7. Shared Component Architecture

The redesign extends the existing `frontend/src/components/deeper-notebook`
surface instead of creating a competitor-named component tree.

### 7.1 Shared primitives

- `WorkspacePage`: page landmark, title hierarchy, width and density authority.
- `WorkspaceHero`: optional notebook or route introduction with accessible
  imagery and actions.
- `VisualCard`: common source, notebook, artifact, and action card geometry.
- `VisualCardGrid`: container-query auto-fit layout with bounded minimum width.
- `SourceCover`: source imagery, provenance label, fallback state, and alt text.
- `NotebookCover`: composited source-derived or locally generated notebook
  identity.
- `SourceGallery`: filters, selection, freshness, source health, and evidence
  counts.
- `ArtifactStudio`: grouped artifact creation, status, viewing, revision, export,
  and failure recovery.
- `EvidencePeek`: the exact source passage behind a claim without losing reading
  position.
- `StatePanel`: shared loading, empty, degraded, offline, error, and unavailable
  states.
- `ResponsiveActionBar`: wraps actions without clipping or reducing touch target
  size.

### 7.2 Boundary rules

- Shared components receive typed data and callbacks; they do not fetch domain
  data directly unless they are an existing query-owning route surface.
- A visual-system component does not decide source authority, artifact
  publication, Study permission, or model routing.
- Feature routes retain their existing hooks and service contracts.
- Existing components migrate incrementally behind the visual-system flag.
- There is one DOM action per user action; desktop and mobile controls may not
  create duplicate dispatch paths.

## 8. Visual Source Gallery

### 8.1 Information shown

Each source card can show:

- source-derived or fallback cover;
- title and source kind;
- notebook membership;
- processing/readiness state;
- freshness or last-updated signal;
- page count, duration, or domain where applicable;
- source-health indicator;
- number of grounded claims or artifacts when available;
- a visible imagery provenance label.

### 8.2 Imagery priority

The fixed priority is:

1. an embedded image selected through deterministic quality rules;
2. a representative video frame selected from bounded candidate timestamps;
3. a locally captured webpage preview when the current security policy permits
   the URL and preview operation;
4. embedded audio artwork or deterministic waveform treatment;
5. a locally generated abstract cover using bounded prompts derived from safe,
   non-sensitive metadata;
6. a deterministic typographic cover based on source kind and checksum.

The user can replace or remove a cover. Removing a generated cover falls back to
the next safe strategy; it never deletes the source.

### 8.3 Non-authoritative presentation record

Source imagery is a rebuildable cache and must not modify source authority. A
new schema-full `source_visual_cache` record stores only bounded presentation
metadata:

- `source_id: record<source>`;
- `content_sha256: string`;
- `asset_sha256: string`;
- `asset_relpath: string` under the controlled data root;
- `origin: embedded | video_frame | web_preview | audio_artwork |
  local_generated | typographic`;
- `source_locator: option<object>` containing a bounded page, timestamp, or
  embedded-resource identifier;
- `generator_id: option<string>` and `generator_version: option<string>`;
- `alt_text: string`;
- `width`, `height`, `mime_type`, `created_at`, and `updated_at`;
- a unique key over source identity and content hash.

Stale records are ignored when the source content hash changes. Missing or
invalid files fall back safely and may be regenerated. The table has a symmetric
down migration.

### 8.4 Local-generation policy

- Local generation is optional and disabled when no approved local image model
  is available.
- Prompts use bounded title, source kind, user-approved notebook topic, and
  abstract style vocabulary; raw source text is not automatically inserted.
- No network provider is selected as a fallback.
- Generated covers are visibly labeled.
- Generated covers are never interpreted as factual source content.
- Generation uses durable idempotency, bounded concurrency, cancellation, and
  exact content-hash invalidation.

## 9. Unified Artifact Studio

The Unified Artifact Studio is a presentation and orchestration layer over
existing `studio_artifact`, Study artifacts, Podcast outputs, Anki receipts, and
their current service authority.

### 9.1 Artifact groups

- **Understand:** report, briefing, data table, research run, citation review.
- **Visualize:** mind map, infographic, timeline, visual brief, slide deck.
- **Learn:** study guide, flashcards, quiz, course pack, Anki package.
- **Listen and watch:** audio overview, podcast, video overview when supported.
- **Share and export:** existing export formats and explicit publication actions.

### 9.2 Artifact card contract

Every artifact card shows:

- type, title, status, and revision;
- source count and citation coverage;
- local/cloud provider disclosure when relevant;
- created and updated times;
- generation progress or typed failure;
- view, retry, revise, export, and delete actions only when authorized;
- accessible alternative for visual artifacts;
- no auto-play and no automatic publication.

### 9.3 Existing authority remains canonical

- The Studio does not fabricate completed status.
- Study artifacts remain bound to approved plan and source authority.
- Anki import/export retains explicit preview and publication confirmation.
- Podcast generation retains its existing source and provider checks.
- Artifact retries reuse stable request identities.
- Revision, deletion, and export use existing repository and API contracts.

## 10. Evidence-First Reading

Evidence-first reading is a cross-application interaction contract:

- selecting a citation reveals the exact supporting passage;
- the evidence panel identifies source, location, and retrieval context;
- compare mode may show agreement, disagreement, and missing evidence;
- unsupported or mixed claims use text labels and icons, not color alone;
- opening and closing evidence preserves reading and keyboard position;
- quoted source text remains within existing copyright and data-access rules;
- the AI response and the supporting source remain visually distinct;
- a generated image is never shown as support for a factual claim.

The first program does not require a new claim graph. It composes current
citations and evaluation receipts. The later Insight Canvas may project these
same records visually.

## 11. Route-Family Rollout

The entire-app scope is decomposed into independently reviewable sub-projects.
Each sub-project receives its own implementation plan, focused tests, review,
and atomic commits.

### Phase 1 — Foundation and shell

- semantic tokens and theme migration;
- shared primitives;
- application shell, adaptive navigation, command surfaces, and focus mode;
- `/login`, `/setup-wizard`, `/`, and shared state panels;
- route-manifest and all-view test harness;
- explicit visual-system rollback.

### Phase 2 — Research core

- `/notebooks`, `/notebooks/[id]`;
- `/sources`, `/sources/[id]`;
- `/knowledge`, `/search`, `/capture`;
- Visual Source Gallery;
- source imagery extraction, cache, provenance, and fallbacks;
- Evidence Peek and reading interactions.

### Phase 3 — Creation and learning

- `/studio`, `/podcasts`, `/podcasts/studio`;
- `/study`, `/study/plans/[planId]`;
- `/transformations`;
- Unified Artifact Studio over existing artifact authorities;
- creation, status, revision, export, and retry parity.

### Phase 4 — System surfaces and release

- `/settings` and every settings subroute;
- `/advanced`;
- theme and display preference controls;
- degraded, offline, unavailable, recovery, and update surfaces;
- complete visual matrix, browser audit, native build, installed-app smoke, and
  default-on flip.

### Phase 5 — Insight Canvas follow-up

- mind-map, timeline, and evidence-map projections;
- direct navigation from visual nodes to source passages;
- exportable accessible alternatives;
- no dependency on this phase for the first entire-app visual release.

## 12. Rollout and Compatibility

### 12.1 Feature control

Use one canonical presentation flag:

`NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2`

Rules:

- explicit `0` means legacy visual presentation;
- `1` means the new presentation;
- unset remains legacy during Phases 1–3;
- unset becomes new presentation only after the complete Phase 4 release gate;
- domain API calls and persisted data must not differ solely because the visual
  flag changes;
- direct and dynamic routes consult the same canonical flag helper;
- when V2 is explicitly off, the existing Luminous Folio and legacy presentation
  flags retain their current behavior; V2 does not reinterpret those variables;
- the feature-off browser contract proves no V2-only network calls.

### 12.2 Theme migration

- Existing users keep their explicit saved theme.
- New users default to Gemini-forward light.
- Users with system theme continue to follow the system.
- High contrast remains an explicit preference and may also respond to platform
  forced-colors behavior.
- Theme preference decoding remains strict and fail-safe.

### 12.3 Data compatibility

- No existing record is renamed or rewritten for presentation purposes.
- `source_visual_cache` is additive and rebuildable.
- Existing source, notebook, artifact, Study, Podcast, model, and update records
  remain canonical.
- Up and down migrations are symmetric.
- Feature-off and downgrade paths ignore presentation-cache records safely.

## 13. Responsive and Compact-Window Contract

The visual system responds to the component's available inline size, not only
the browser viewport.

Required widths:

- 320 px compact/mobile;
- 768 px tablet or narrow desktop;
- 1020 × 631 px compact desktop reference;
- 1440 × 900 px large desktop reference.

Additional short-height checks cover constrained windows where the sidebar,
command bar, or secondary rail reduces content width.

Rules:

- grids use container queries and bounded `auto-fit` tracks;
- body text retains the accessible minimum size;
- controls retain at least a 44 × 44 px target where touch interaction applies;
- titles and actions wrap or reflow before truncation;
- truncation is allowed only for repeated metadata and must expose the full value
  accessibly;
- no horizontal document overflow;
- the actual scroll owner is asserted;
- lower content is reachable and can be brought fully into the visual viewport;
- overlays, rails, banners, and toasts do not cover primary actions;
- safe-area insets are respected.

## 14. State and Error Design

Every relevant route defines and tests:

- loading;
- empty;
- populated;
- partial or processing;
- degraded model/runtime;
- offline;
- typed API error with retry when safe;
- unavailable or unauthorized;
- feature-off legacy presentation.

State panels use one consistent anatomy:

1. plain-language title;
2. concise explanation;
3. current data preservation statement when relevant;
4. one primary recovery action;
5. optional secondary details or support code;
6. no invented diagnosis.

Image failures never fail the route. They fall back from source image to local
generated image to typographic cover. Artifact failures remain visible and
retryable through existing typed failure paths.

## 15. Accessibility

The release gate requires:

- exactly one primary `main` landmark and one visible page `h1`;
- semantic headings without skipped structural levels;
- keyboard access to every action;
- focus return after dialogs, drawers, menus, and evidence panels;
- visible focus in all themes;
- accessible names that distinguish repeated card actions;
- no information communicated by image or color alone;
- useful alt text for source-derived imagery;
- generated imagery labeled in visible and accessible text;
- decorative images hidden from assistive technology;
- reduced-motion and forced-colors handling;
- live regions limited to meaningful state changes;
- zoom and text-resize operation without clipping;
- no keyboard trap in galleries, carousels, or artifact viewers.

## 16. Privacy and Security

- Image extraction reads only authorized source records and controlled paths.
- Asset paths are canonicalized under the controlled data root.
- URL previews reuse existing outbound URL and SSRF protections.
- Image decoders enforce MIME allowlists, byte limits, pixel limits, frame limits,
  and decompression-bomb protection.
- Video-frame extraction is time- and resource-bounded.
- SVG is rejected or sanitized through an explicitly approved pipeline before
  rendering.
- Locally generated cover prompts exclude raw private source text by default.
- No cloud generation fallback occurs silently.
- Temporary files use task-owned directories and deterministic cleanup.
- Cache deletion never deletes the source or authoritative artifact.
- Logs and receipts exclude secrets and full private source content.

## 17. Performance Budgets

- Route shell remains interactive without waiting for cover generation.
- Gallery image work is lazy and viewport-aware.
- Initial cards use bounded thumbnails, not original assets.
- Thumbnail dimensions and encoded bytes are capped.
- Cover extraction and generation use bounded worker concurrency.
- Duplicate requests coalesce by source content hash and presentation version.
- Layout shift from image loading is prevented with fixed aspect ratios.
- Route bundles do not import heavy media tooling into the browser.
- The artifact studio paginates or virtualizes large collections.
- Theme changes do not require a page reload.

Exact numeric budgets are set in each phase plan from measured current
baselines; a phase may not regress its approved baseline without an explicit
receipt and review.

## 18. All-View Acceptance Contract

### 18.1 Base matrix

All 22 page views are checked at:

- 3 themes: light, dark, high contrast;
- 4 required viewport profiles: 320 px, 768 px, 1020 × 631 px, 1440 × 900 px.

This creates **264 route/theme/viewport checks** before state-specific cases.

The visual browser harness may group routes to keep runtime bounded, but the
route manifest must prove every page participates.

### 18.2 Assertions for every matrix cell

- route loads without an unexpected console or network error;
- one visible page `h1` and one `main` landmark;
- no horizontal document overflow;
- primary actions exist, are visible, and are not clipped;
- text and actionable descendants stay within their card or intended viewport;
- the page's actual scroll owner exposes all lower content;
- navigation and command destinations remain available when authorized;
- theme tokens produce readable text and controls;
- no raw missing-image icon or broken asset;
- no duplicate React key, hydration, or accessibility warning;
- exact route-specific request ledger uses the expected methods and paths.

### 18.3 State coverage

Component and focused browser tests cover loading, empty, populated, processing,
degraded, offline, error, unauthorized, and feature-off states where each is
valid. State coverage is mapped to routes in a checked fixture; irrelevant state
combinations are explicitly marked rather than silently skipped.

### 18.4 Regression gates

- focused component tests for each migrated component;
- locale parity for every new user-facing key;
- ESLint with no new warnings;
- TypeScript `--noEmit`;
- default-on and explicit-off production builds;
- full frontend unit suite;
- existing backend and real-database gates when APIs or migrations change;
- exact visual browser matrix;
- rebrand and compatibility audits;
- staged and commit-range secret scans;
- native arm64 package build and signature verification;
- task-owned installed-app smoke and restart parity;
- recoverable backup and rollback receipt.

## 19. Testing Architecture

### 19.1 Route manifest

A small script or test derives page routes from the app tree and compares them
with a typed test fixture. Dynamic routes receive deterministic fixture IDs. No
catch-all API handler is allowed in the browser fixture.

### 19.2 Component tests

Shared primitives test:

- rendering in every state;
- strict prop and decoder behavior;
- accessible names and focus movement;
- image origin labels and fallback order;
- container-size behavior;
- action dispatch exactly once;
- feature-off behavior.

### 19.3 Browser tests

The browser fixture records exact method, canonical path, response state, and
viewport. It rejects unknown requests and wrong methods. Visual snapshots are
used only for stable flagship surfaces; semantic geometry and accessibility
assertions remain the primary contract.

### 19.4 Backend and database tests

If `source_visual_cache` is introduced:

- strict codec and schema tests;
- source/content-hash authority tests;
- malformed path and MIME rejection;
- concurrent idempotency and stale-cache replacement;
- real Surreal migration, uniqueness, and cleanup tests;
- downgrade symmetry;
- proof that cache deletion leaves sources untouched.

## 20. Implementation Program Boundaries

This design is intentionally larger than one safe implementation task. Work is
split into the five phases in Section 11.

The next implementation plan covers **Phase 1 only**:

- semantic tokens and theme family;
- shared primitives;
- shell and foundational routes;
- route-manifest harness;
- visual-system flag and rollback;
- baseline accessibility and responsive contracts.

Phase 2 begins only after Phase 1 is independently reviewed and merged. The
Source Gallery, imagery cache, and local-generation pipeline receive their own
Phase 2 plan because they cross frontend, backend, storage, media-security, and
real-database boundaries.

## 21. Definition of Done

The entire program is complete only when:

1. all 22 current page views use the shared visual system;
2. newly added routes are automatically included in the route contract;
3. the 264-cell base matrix is green;
4. relevant state coverage is complete and checked;
5. source imagery provenance and fallback labels are visible and accessible;
6. local generation never falls through to an unapproved cloud provider;
7. Artifact Studio preserves existing domain authority and explicit publication;
8. light, dark, and high-contrast themes pass accessibility checks;
9. compact windows contain readable text and reachable actions;
10. explicit feature-off rollback preserves the legacy presentation and network
    behavior;
11. full frontend, affected backend, real-database, visual, build, rebrand,
    security, and native package gates are green;
12. installed-app smoke and restart parity pass from a task-owned data root;
13. the original installed app remains recoverable until acceptance completes;
14. a fresh-context review reports no Critical or Important findings.

## 22. Approved Decisions

- Visual direction: Gemini-forward.
- Product scope: entire app.
- First enhancements: Visual Source Gallery and Unified Artifact Studio.
- Imagery policy: source-derived with clearly labeled local fallback.
- Theme strategy: Gemini-forward light default, Research Core dark counterpart,
  dedicated high contrast.
- Route assurance: every existing view participates in an executable acceptance
  matrix.
- Delivery strategy: phased, reversible, independently reviewed.
- Insight Canvas: follow-up after gallery and studio foundations.
