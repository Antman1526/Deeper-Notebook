# Deeper Notebook Luminous Research Folio Redesign

**Date:** 2026-08-09

**Author:** Anthony Henry with Codex

**Status:** Approved 2026-08-09

**Baseline:** `agent/documentation-reconstruction` at `7a926ed2`

## Purpose

Redesign Deeper Notebook into a visually distinctive, premium notebook
workspace while preserving every existing product feature and behavioral
contract.

The approved direction is **Luminous Research Folio**: a precise, dark research
instrument surrounding a warm, editorial living notebook. Aurora Cartography
provides slow ambient depth in negative space. The notebook itself provides the
product's organizing metaphor through pages, indexes, tabs, margins, evidence
inserts, atlas foldouts, bookmarks, and production folios.

The result should be more memorable and intellectually coherent than generic
AI card grids or a visual clone of Gemini Notebook. Deeper Notebook competes by
making research feel authored and durable while exposing advantages that are
already present in the product: local-first operation, connected knowledge,
source authority, exact evidence, local-model routing, and optional grounded
podcast production.

## Relationship to Existing Designs

This specification extends the approved Research Core OS visual system and the
Research Core Lab and Podcast Intelligence Studio designs. It keeps their
behavior, safety, theme, evidence, local-model, and verification contracts.

This specification refines the visual presentation in five ways:

1. It replaces the generic full-height application sidebar with a compact
   instrument dock plus contextual navigation.
2. It makes the notebook metaphor the product-wide information architecture,
   rather than limiting editorial styling to documents.
3. It pairs the existing Research Core teal/cyan identity with warm archival
   reading surfaces and a restrained brass accent.
4. It formalizes Aurora Cartography as a user-controllable ambient background.
5. It defines a phased whole-application migration and proof strategy.

It does not invalidate existing specifications for unified knowledge,
read-only external vaults, command navigation, workspace persistence, research
evidence, artifact generation, Podcast Studio, local models, or packaging.

## Baseline Snapshot

At the design baseline, the frontend contains 22 page entry points and 25
catalog theme selectors. It already provides:

- a semantic theme system with Research Core colors and an Aurora background;
- a global sidebar, command palette, guided tips, and responsive app shell;
- sources, capture, notebooks, notes, ask/search, Knowledge, graph, backlinks,
  workspaces, bookmarks, Studio, study, transformations, podcasts, and settings;
- Evidence Studio artifacts, citations, revisions, exports, and study viewers;
- Podcast Intelligence Studio, research sets, outline review, model plans,
  production stages, profiles, transcripts, audio, retry, and cancellation;
- local-model inventory, routing, benchmark receipts, and privacy boundaries;
- app-owned editable knowledge plus external read-only Obsidian and Logseq
  mounts; and
- native, browser, theme, desktop, DMG, and installed-application proof paths.

Implementation must reveal and reorganize this foundation. It must not create
parallel replacements for working features.

## Goals

1. Make Deeper Notebook immediately recognizable as a premium notebook product.
2. Create a breathtaking first impression without reducing reading comfort or
   operational clarity.
3. Give every route a coherent place in one notebook-oriented system.
4. Make evidence, provenance, authority, local/cloud routing, and review state
   visible at the point where they matter.
5. Preserve advanced density for experienced users while improving orientation
   for a first-time user.
6. Keep ambient motion optional, performant, accessible, and outside content
   reading surfaces.
7. Deliver the redesign incrementally so the application remains usable,
   testable, reviewable, and reversible after every phase.
8. Treat visual quality as a verified release requirement through deterministic
   renders plus explicit human review.

## Non-Goals

- No API, database schema, domain model, queue, or persistence rewrite.
- No changes to route URLs, command IDs, keyboard shortcuts, or stored theme IDs.
- No automatic generation, podcast production, scan, mount, import, or publish
  action caused by opening a redesigned surface.
- No write-back to external Obsidian or Logseq content.
- No silent cloud fallback or change to local-model eligibility.
- No new collaboration, hosting, or public distribution system.
- No copying of a competitor's layout, components, illustrations, or trade dress.
- No fake leather, metal rings, torn paper, handwriting fonts, curled corners,
  or slow page-turn animation.
- No decorative motion behind notes, source text, editors, transcripts, forms,
  citations, or dense settings.
- No requirement that a note or notebook be converted into a podcast.

## Product Position

The redesign expresses one sentence:

> Deeper Notebook is a living research notebook that can show how knowledge was
> formed, connect it across local spaces, and turn it into useful work.

The experience should outperform leading notebook research products in four
areas that are native to Deeper Notebook:

- **Durability:** research spaces, notes, graph context, and outputs persist as
  part of a long-lived knowledge system.
- **Trust:** citations, evidence receipts, source fingerprints, contradictions,
  model routes, and authority are first-class visual objects.
- **Ownership:** local models and external read-only vaults remain inspectable
  and under the user's control.
- **Creation:** reports, study material, visual artifacts, and podcasts emerge
  from the same notebook rather than an unrelated generator.

## Approved Direction

### Luminous Research Instrument

The outer application is a dark, precise instrument. It provides orientation,
commands, status, and contextual tools using compact glass and mineral
surfaces. It should feel engineered rather than templated.

### Living Research Folio

The active work area is a modern editorial notebook. Notebook cues carry real
meaning:

- an **index** establishes the notebook's sections and progress;
- **tabs** identify stable modes or destinations;
- a **spread** shows two related bodies of information together;
- the **margin** carries context, commentary, backlinks, or review notes;
- an **insert** carries evidence, a source receipt, a model route, or an artifact;
- an **atlas** is a spatial graph or map view;
- a **bookmark** preserves progress or highlights an important state; and
- a **folio** structures a production workflow such as evidence, study, or audio.

Notebook style is an information architecture, not a universal paper texture.
Dense settings, tables, terminals, code, and diagnostics retain precise digital
surfaces while inheriting the same typography, index, tab, and back-matter
grammar.

### Aurora Cartography

The outer canvas uses slow, layered teal, cyan, and warm mineral light to evoke
knowledge relationships. Aurora movement:

- stays in negative space outside reading and writing surfaces;
- uses bounded transform and opacity animation on pre-blurred layers;
- never performs network requests or loads remote wallpaper media;
- stops under operating-system reduced motion;
- has an explicit on/off display preference;
- falls back to a static gradient when motion or transparency is reduced; and
- must not make content availability depend on animation support.

## Visual System

### Color roles

The existing Research Core identity remains canonical. The following values are
reference anchors for the default Luminous Research Folio presentation, not new
hardcoded values for every theme:

| Role | Reference | Purpose |
|---|---:|---|
| Deep Ink | `#061315` | Outer canvas and darkest instrument structure |
| Abyss Teal | `#0A2729` | Navigation, context, and raised dark panels |
| Mineral Teal | `#2DD4BF` | Primary actions, trust, creation, and active location |
| Electric Mist | `#67E8F9` | Focus, live intelligence, and active relationships |
| Archive Ivory | `#F5F1E7` | Editorial pages and warm reading surfaces |
| Quiet Brass | `#CBAE70` | Durable insight, review, bookmarks, and selected inserts |

Destructive red, warning amber, success, information, editable, read-only,
local-model, cloud-model, and evidence states remain semantic tokens. Color is
never the only status signal.

Themes reinterpret paper, ink, glass, and accent temperature through semantic
variables. Components must not branch on theme IDs.

### Material hierarchy

Four materials are sufficient:

1. **Outer canvas:** deep atmospheric background and Aurora Cartography.
2. **Instrument glass:** dock, command bar, navigator, Context Lens, transient
   overlays, and selected status surfaces.
3. **Editorial paper:** notes, source reading, synthesis, reports, outlines,
   study material, and transcripts.
4. **Intelligence signal:** evidence, model routes, graph focus, progress, and
   review state.

Glass is reserved for structure and overlays. Editorial paper is opaque enough
to protect legibility. Texture remains subtle and can be disabled with reduced
transparency or high-contrast preferences.

### Typography

The type system has three voices:

- **Interface sans:** Inter for navigation, controls, labels, compact metadata,
  and dense utility surfaces.
- **Editorial serif:** Newsreader through the existing Next font build path for
  notebook titles, questions, reports, narrative artifacts, and selected
  reading hierarchy. Runtime use must be self-hosted by the built application;
  no native launch may depend on a font network request.
- **Data mono:** the platform monospace stack for hashes, paths, model IDs,
  timestamps, revisions, duration, and production stages.

Implementation must first resolve the current Inter body versus undefined
Geist token mismatch. Fallbacks must use compatible local fonts and preserve
layout if the editorial face cannot load.

### Shape, depth, and spacing

- Work pages use restrained radii and subtle page-edge depth.
- The notebook gutter indicates relationship without a fake binding.
- Tabs and bookmarks are compact navigational markers, not decorative labels.
- Borders are reserved for focus, authority, selected state, or material edges.
- Whitespace and typography replace grids of equal-weight cards.
- Dense tools reduce internal spacing without reducing pointer targets.
- Reading columns use a comfortable measure and responsive line length.
- Shadows remain soft and theme-derived; high-contrast modes remove ambiguous
  depth in favor of explicit borders.

### Iconography

The existing Lucide icon language remains. Selected primary tools may sit in a
contained tile. Notebook meaning comes from layout and material, not emoji or
illustrative icon mixtures.

## Application Shell

The approved shell has four adaptive regions.

### Instrument Dock

A compact persistent rail provides all current top-level destinations. It
retains accessible labels and tooltips, selection state, creation entry points,
theme/language controls, authentication actions, and keyboard navigation.

The dock does not remove or rename route contracts. On narrow layouts it becomes
a compact bottom navigation or an accessible menu without duplicating state.

### Command Bar

The top bar provides:

- notebook, knowledge space, or workflow breadcrumb;
- global search, ask, and command entry;
- local/cloud route summary where relevant;
- connection, index, watcher, or production state where relevant;
- one context-aware primary Create action; and
- account and application controls.

Healthy state stays quiet. Warnings show a reason and one bounded recovery
action.

### Adaptive Navigator

The second rail behaves as the current notebook index. Its contents change with
the active route family while selection identity remains single-sourced.

Examples include notebook sections, Knowledge workspace tools, source groups,
Studio stages, Podcast library views, settings categories, and saved views. It
can collapse to tabs or open as a drawer without discarding selection.

### Editorial Canvas and Context Lens

The central canvas contains the active page, spread, atlas, or folio. A
context-sensitive right region exposes evidence, backlinks, properties,
outline, model route, tasks, citations, revisions, or media without maintaining
a second active-document identity.

On smaller layouts the Context Lens becomes a sheet or drawer. Closing it must
not erase filters, selection, or unsaved app-owned edits.

## Flagship Surface Families

### Intelligence Horizon

The dashboard becomes the notebook library and work desk. It prioritizes:

1. the active inquiry or task worth continuing;
2. recent notebooks and workspaces;
3. unprocessed sources or review items;
4. active research, artifacts, study, or podcast production; and
5. local runtime readiness and safe recovery state.

Quick actions remain available, but the screen is not a warehouse of equal
cards. Opening Horizon remains non-mutating.

### Research Core

Knowledge becomes the flagship working notebook. Existing tabs, recursive
splits, panes, Reading, Source, Live Preview, graph, Canvas, bookmarks,
workspaces, search, backlinks, commands, and persistence remain authoritative.

The approved notebook forms are:

- an index for Overview, Sources, Notes, Graph, Research, Evidence, and saved
  views;
- working spreads for source plus note, answer plus citation, or synthesis plus
  evidence;
- an atlas for graph relationships and selected-node evidence;
- margins for backlinks, contradictions, tasks, properties, and commentary;
- evidence inserts with provider, freshness, retrieval time, and fingerprints;
  and
- visible external-read-only authority and source-hash integrity.

### Intelligence Studios

Evidence Studio, Study, and Podcast Studio use a shared folio grammar:

- source or research-set manifest;
- outline or artifact architecture;
- model and tool route plan;
- explicit review and approval gate;
- bounded production timeline;
- result, revisions, citations, and export; and
- retry, cancellation, and recovery that retain the user's work.

Podcast creation remains optional. Every eligible notebook or note may offer a
Turn into Podcast action, but no notebook requires an episode and opening a
Studio never queues work.

Podcast-specific surfaces retain episode and speaker profiles, editorial brief,
outline storyboard, stage plan, local voice routing, synchronized transcript,
waveform/audio, Episode Lab, templates, library, and global player.

## Complete Feature-Preservation Map

| Existing surface | New presentation | Preserved contracts |
|---|---|---|
| `/` | Intelligence Horizon | Recents, quick actions, runtime status, navigation |
| `/sources`, `/sources/[id]` | Source folio and reading page | Add, inspect, process, chat, citations, readiness |
| `/capture` | Inbox page | Capture behavior, validation, notebook targeting |
| `/notebooks`, `/notebooks/[id]` | Library, index, and working spread | CRUD, notes, sources, chat, artifacts, podcast actions |
| `/knowledge` | Research Core notebook and atlas | Tabs, splits, graph, backlinks, workspaces, bookmarks, vaults |
| `/search` | Discovery index and results folio | Ask/search behavior, citations, context, commands |
| `/studio` | Evidence production folio | Inputs, artifacts, citations, revisions, exports, review |
| `/podcasts`, `/podcasts/studio` | Podcast library and production folio | Templates, profiles, stages, audio, transcript, retry/cancel |
| `/study` | Study pack | Source-grounded review, scheduling, cards, quizzes |
| `/transformations` | Methods index | Existing transformations, prompts, validation, results |
| `/settings` | Notebook back matter | Guided tips and all current settings behavior |
| API keys and local models | Instrument panels | Providers, keys, inventory, benchmarks, routes, receipts |
| MCP and launcher preferences | Integration back matter | Current configuration and safety boundaries |
| `/advanced` and setup | Technical appendix | Advanced controls, setup sequence, diagnostics |
| Login, dialogs, menus, toasts | Cover and overlays | Authentication, focus, validation, portal theme inheritance |

The route list is a compatibility inventory, not permission to combine or
delete routes. Any later consolidation requires a separate approved product
design.

## Themes and Display Preferences

All existing theme IDs and persisted user selections remain valid. The new
materials derive from the active theme's semantic variables.

Theme behavior:

- Research Core themes use the approved Deep Ink, mineral, cyan, archival, and
  brass hierarchy.
- Light themes use warm or cool paper with darker ink and restrained Aurora.
- Dark themes use slate or luminous vellum reading surfaces rather than forcing
  bright paper.
- High-contrast themes remove nonessential texture, transparency, and shadow.
- Classic themes retain their recognizable palette while adopting the new
  hierarchy.
- Portals, dialogs, tooltips, menus, toasts, and native wrapper surfaces inherit
  the active theme.

Appearance settings include:

- current theme selection and preview;
- Aurora wallpaper on/off;
- system-authoritative reduced motion with an optional in-app reduction;
- reduced transparency;
- guided tips on/off and Replay all tips; and
- reading typography or density only if it can be added without changing stored
  content.

Display preferences remain local presentation state. They do not change source
authority, model routing, research logic, or stored notebook content.

## Interaction and Motion

The motion scale is:

| Role | Target | Examples |
|---|---:|---|
| Immediate | 120 ms | Hover, press, focus, icon state |
| Interface | 200 ms | Selection, panel disclosure, control transition |
| Narrative | 320–400 ms | Route reveal, artifact arrival, completed stage |
| Ambient | 18–26 s | Aurora Cartography drift |

Motion rules:

- motion explains location, relationship, progress, or consequence;
- ambient layers animate transform and opacity, not layout;
- reading surfaces do not drift, pulse, shimmer, or parallax;
- loading shimmer stops under reduced motion;
- route changes never wait for decorative animation;
- focus is visible before, during, and after transitions; and
- no meaning is available only in motion.

## Guided Tips

The existing Guided Tips system remains and adopts the new visual language.
Tips:

- anchor to stable controls or headings;
- show one at a time;
- remain non-modal, dismissible, keyboard reachable, and screen-reader named;
- pause while dialogs or critical workflows own focus;
- never start a scan, generation, mount, import, or mutation;
- fail closed when an anchor is absent;
- can be disabled globally; and
- can be replayed without changing any unrelated local state.

## Operational States

Every redesigned family must include intentional versions of these states:

- **loading:** preserve final layout and name the real operation where known;
- **empty:** explain value and offer one safe primary next step;
- **offline:** retain available local work and expose a bounded retry;
- **degraded:** identify the unavailable provider or model without hiding usable
  content;
- **read-only:** show source authority at the point of attempted editing;
- **warning/review:** explain freshness, contradiction, or approval requirement;
- **failure:** retain selections, manifests, drafts, and recovery context; and
- **success:** confirm the outcome without blocking continued work.

Skeletons may communicate loading structure. They must not replace actionable
progress, and shimmer must be disabled under reduced motion.

## Responsive Architecture

The same hierarchy adapts rather than creating a second mobile product:

- **large desktop:** dock, navigator, editorial canvas, and Context Lens;
- **compact desktop/tablet:** dock, canvas, and either navigator or Context Lens;
- **narrow:** one main page, bottom or compact navigation, navigator drawer, and
  Context Lens sheet.

The current desktop experience remains the primary optimization target. Narrow
layouts must still support task completion, keyboard navigation where present,
touch targets, 200 percent zoom, and horizontal-overflow prevention.

## Accessibility Requirements

- Meet WCAG 2.2 AA contrast for normal text, controls, focus, and meaningful
  non-text graphics.
- Preserve semantic headings, landmarks, lists, forms, dialogs, tabs, and status
  announcements.
- Support full keyboard operation and logical focus restoration.
- Pair status color with text, icon, shape, or pattern.
- Give evidence, authority, model route, and production state accessible names.
- Respect operating-system reduced motion before the first animated frame.
- Keep high-contrast layouts usable without relying on glass, shadow, texture,
  or page-depth illusion.
- Prevent guided tips, tabs, margins, and inserts from trapping focus or
  obscuring the active control.

## Performance Requirements

- Aurora uses a bounded number of fixed layers and no particle canvas.
- No wallpaper, texture, font, or animation requires a runtime network request.
- Ambient animation does not trigger continuous layout work.
- Large graphs, transcripts, source lists, and artifact collections retain
  bounded rendering or virtualization.
- Theme changes do not reload the application.
- Initial theme and motion preference are available before hydration.
- The shell must reveal usable local content even if the API, model runtime, or
  external provider is unavailable.
- Production build analysis must show no unexplained large dependency added for
  visual decoration.

## Component and Token Architecture

Implementation follows the downstream component discipline in
`frontend/src/components/deeper-notebook/`.

The design calls for reusable families rather than route-specific copies:

- shell: Instrument Dock, Command Bar, Adaptive Navigator, Editorial Canvas,
  and Context Lens;
- atmosphere: Aurora Cartography and static/reduced variants;
- notebook: page, spread, index, tab, margin, insert, bookmark, atlas, folio,
  and back-matter primitives;
- state: empty, loading, offline, degraded, read-only, review, and success;
- settings: display preferences and visual previews; and
- proof fixtures: deterministic flagship data and theme/viewport matrices.

New tokens extend the existing `--dn-*` semantic layer. They should represent
roles such as paper, ink, page edge, margin rule, folio surface, brass review,
and Aurora intensity. They derive from the active theme and do not replace
existing `--background`, `--foreground`, `--card`, `--primary`, `--accent`,
authority, graph, evidence, or model-route tokens.

Large upstream components are not restyled through broad selector overrides.
Create downstream shadow components and keep upstream page changes surgical.

## Alternatives Considered

### Pure Research Instrument

A fully dark precision interface would be fast to apply and consistent with
Research Core, but it would make long-form reading colder and would not give
Deeper Notebook a sufficiently ownable notebook identity.

### Pure Luminous Archive

A predominantly warm editorial interface would be beautiful for reading, but
it would understate live models, evidence, graph relationships, audio, and
operational status.

### Deep Space Lab

A cinematic dark interface with more glow and spatial effects would create a
strong first impression, but it risks generic AI styling, poorer reading
comfort, and excessive motion.

### Big-bang route rewrite

Rebuilding every route around a new component tree could create perfect
consistency on paper, but it would increase regression risk, delay visible
value, complicate upstream synchronization, and make provenance or authority
mistakes harder to isolate.

### Decision

Use the combined Luminous Research Instrument plus Living Research Folio, with
Aurora Cartography outside opaque work surfaces and a progressive migration.

## Delivery Sequence

### Phase 0 — Baseline and rollback

- Record exact branch, dirty state, route inventory, command inventory, theme
  catalog, and feature flags.
- Capture current flagship screenshots and behavior receipts.
- Define a reversible branch stack and visual fixture data.
- Do not update snapshots merely to make the baseline green.

### Phase 1 — Visual and notebook foundation

- Normalize font variables and add the offline editorial font path.
- Extend semantic material, notebook, and motion tokens.
- Implement Aurora Cartography and display preferences.
- Implement page, index, tab, margin, insert, bookmark, atlas, and folio
  primitives with reduced-motion and high-contrast variants.
- Prove theme compatibility before route migration.

### Phase 2 — Application shell

- Implement the Instrument Dock, Command Bar, Adaptive Navigator, Editorial
  Canvas, and Context Lens.
- Preserve all destinations, command IDs, keyboard paths, theme/language
  controls, authentication actions, and responsive behavior.
- Keep a reversible shell switch until parity is proven.

### Phase 3 — Flagship pilots

- Redesign Intelligence Horizon.
- Redesign Research Core, including a populated spread and graph atlas.
- Redesign Evidence Studio and Podcast Studio folios.
- Prove dense data, empty/loading/failure state, guided tip, narrow viewport,
  high contrast, and reduced motion on each flagship.

### Phase 4 — Route-family migration

- Migrate sources and capture.
- Migrate notebooks and note workspaces.
- Migrate ask/search and grounded chat.
- Migrate study, transformations, and artifact viewers.
- Migrate podcast library, profiles, Episode Lab, and player surfaces.
- Migrate settings, local models, MCP, launcher preferences, advanced, setup,
  authentication, dialogs, menus, and toasts.
- Use small reviewable batches and preserve existing tests.

### Phase 5 — Release proof

- Complete the deterministic render matrix and human contact-sheet review.
- Run full frontend, backend, theme, browser, native, desktop, and packaging
  gates at the exact release revision.
- Build and verify the macOS DMG.
- Install and launch the exact built application.
- Re-prove external-vault no-write/source-hash preservation where the packaged
  shell or Knowledge presentation changed.
- Record sanitized receipts and the artifact SHA-256.

## Verification Strategy

### Component and contract gates

- Unit tests cover notebook primitives, shell navigation, focus, state variants,
  display preferences, and theme inheritance.
- Existing route, command, guided-tip, workspace, vault, research, Studio,
  podcast, and local-model tests remain green.
- TypeScript, ESLint, production build, Ruff, and backend tests run without
  suppressing introduced diagnostics.

### Render matrix

Deterministic screenshots cover:

- Intelligence Horizon;
- a populated notebook index and working spread;
- Research Core graph atlas with selected evidence;
- grounded search or chat with citations and a contradiction;
- Evidence Studio;
- Podcast Studio and Episode Lab;
- theme and display settings;
- empty, loading, offline, read-only, review, and failure states;
- guided tip visible and disabled; and
- menus, dialogs, tooltips, toasts, and Context Lens overlays.

Required themes include Research Core Dark, Research Core Light, Archive Paper,
a representative classic dark theme, a representative classic light theme,
High Contrast Dark, and High Contrast Light.

Required viewports include large native desktop, standard desktop, compact
desktop, and narrow responsive presentation. Reduced-motion and
reduced-transparency captures are separate proof cases.

### Human visual review

A contact sheet is reviewed for:

- immediate notebook identity;
- hierarchy and reading comfort;
- consistency across route families;
- evidence, authority, model, and review clarity;
- absence of generic card-grid styling;
- absence of gimmicky notebook decoration;
- density, alignment, rhythm, and responsive composition;
- visual quality across dark, light, classic, and high-contrast themes; and
- whether the product feels more memorable without becoming less usable.

### Runtime and package gates

The release candidate runs the repository's current proportional gates,
including:

- frontend Vitest, ESLint, TypeScript, and production build;
- mocked-browser and theme Playwright suites;
- native-runtime browser cases for Knowledge, research evidence, artifacts, and
  Podcast Studio;
- full backend and desktop pytest plus Ruff;
- native SurrealDB integration where the changed surface depends on persisted
  state;
- packaged-device checks;
- `make build-mac`, DMG verification, installed launch, and runtime health; and
- controlled external-vault source-hash/no-write proof.

A passing build is not packaged proof. A mocked screenshot is not native data
proof. A native page load is not external-vault integrity proof.

## Risks and Mitigations

### Notebook styling becomes decoration

**Mitigation:** every page, margin, tab, insert, and folio must communicate a
real relationship or state. Remove any cue that cannot explain its information
role.

### Visual depth harms readability

**Mitigation:** keep content surfaces opaque, cap line length, verify contrast,
and remove texture/transparency under accessibility preferences.

### Aurora harms performance or focus

**Mitigation:** use bounded fixed layers, transform/opacity animation, static
fallbacks, explicit user control, and performance measurements on native builds.

### Shell migration hides an existing feature

**Mitigation:** maintain a route/command/action parity inventory and require
keyboard plus browser receipts before removing the reversible old-shell path.

### Theme migration breaks stored preferences

**Mitigation:** preserve theme IDs, derive new roles from semantic tokens, test
pre-hydration selection, and verify portaled/native surfaces.

### Broad restyling complicates upstream synchronization

**Mitigation:** use downstream shadow components and surgical page import
changes instead of editing shared upstream primitives or broad global selectors.

### Visual work weakens authority or approval boundaries

**Mitigation:** keep read-only, provenance, local/cloud, freshness, and review
states explicit in component contracts and native proof fixtures.

## Acceptance Criteria

The redesign is complete only when:

1. Deeper Notebook is immediately recognizable as a Luminous Research Folio.
2. The approved shell, notebook primitives, flagship families, interaction
   rules, and Aurora display controls are implemented coherently.
3. All current route destinations, commands, keyboard paths, theme IDs,
   settings, and product behaviors remain available.
4. All current themes render usable notebook, instrument, overlay, and state
   surfaces without theme-ID component branches.
5. Knowledge retains tabs, splits, graph, backlinks, workspaces, bookmarks,
   commands, and external read-only vault authority.
6. Studio retains artifacts, citations, revisions, exports, study interactions,
   production review, and safe recovery.
7. Podcast creation remains optional and retains its research, outline, model,
   voice, transcript, audio, review, retry, and cancellation contracts.
8. Local-model routing, receipts, privacy, and fallback behavior are unchanged.
9. Guided Tips remain optional, non-modal, locally persisted, and replayable.
10. Empty, loading, offline, degraded, read-only, review, failure, and success
    states are intentionally designed.
11. Keyboard, screen-reader, high-contrast, reduced-motion, reduced-transparency,
    narrow, and 200-percent zoom paths remain usable.
12. The deterministic render matrix passes and the contact sheet receives
    explicit human approval.
13. Full frontend, backend, native, desktop, and package gates pass at the exact
    release revision.
14. The exact DMG is verified, installed, launched, and recorded with a SHA-256.
15. External Obsidian and Logseq source hashes remain unchanged through the
    controlled packaged proof.

## Decision Summary

The approved product direction is **Luminous Research Folio**:

- a dark Luminous Research Instrument shell;
- a Living Research Folio notebook architecture;
- Aurora Cartography in negative space;
- Inter, Newsreader, and a platform mono role system;
- Mineral Teal, Electric Mist, Archive Ivory, and Quiet Brass material roles;
- Intelligence Horizon, Research Core, and Intelligence Studios as the three
  product-wide layout families;
- optional guided help and user-controlled atmosphere;
- complete feature and authority preservation; and
- a progressive, proof-gated whole-application rollout.

The next step after written-spec approval is a task-level implementation plan.
No product implementation is authorized by this design document alone.
