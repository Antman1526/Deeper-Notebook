# Deeper Notebook Research Core OS Visual System Design

**Date:** 2026-08-01

**Author:** Anthony Henry with Codex

**Status:** Approved in conversational design; pending written-spec review

**Baseline:** `codex/podcast-intelligence-studio-phase-2` at `4b257e2c`

## Purpose

Give Deeper Notebook a coherent, premium visual system that is immediately
recognizable as its own product and is competitive with NotebookLM, Notion AI,
Obsidian, and Logseq without copying their interfaces.

The approved direction is **Research Core OS**: NotebookLM-like clarity for a
new user, Obsidian/Logseq-level workspace depth for an expert, and a distinctly
Deeper Notebook layer of local-first model routing, provenance, evidence,
contradiction handling, and controlled podcast production.

This design makes Research Core the flagship identity, retains the existing
theme catalog as optional classics, adds eight curated themes, and establishes
a visual-render proof gate so a theme is not considered complete merely because
its token values compile.

## Relationship to Existing Designs

This specification extends the approved designs for:

- the Deeper Notebook rebrand and Notebook Spark identity;
- the unified knowledge engine;
- navigation productivity and command navigation;
- read-only Obsidian and Logseq integration; and
- Research Core Lab and Podcast Intelligence Studio.

It does not weaken existing source-authority, local-first, migration,
provenance, accessibility, or read-only external-vault contracts.

## Competitive Design Target

NotebookLM currently organizes work around selectable sources, grounded chat,
and a Studio that can generate multiple output types. Notion AI combines scoped
research with visible sources and saved reports. Obsidian and Logseq provide
deeper long-lived knowledge navigation and user-controlled workspaces.

Deeper Notebook should combine the best interaction qualities without becoming
a visual clone:

1. **Immediate comprehension:** the primary source, thinking, and output zones
   are understandable within seconds.
2. **Progressive depth:** split panes, backlinks, graphs, evidence, model routes,
   and production controls appear as the user needs them.
3. **Visible trust:** citations, source authority, evidence coverage, model
   location, and generation receipts are part of the interface hierarchy.
4. **Durable context:** notebook, workspace, search, graph, and Studio state can
   persist rather than behaving like disposable prompt sessions.
5. **Distinct identity:** teal/cyan Research Core color, Notebook Spark
   personality, editorial typography, precise instrument-like controls, and
   restrained depth replace generic blue SaaS styling.

Reference surfaces:

- <https://support.google.com/notebooklm/answer/16206563?hl=en>
- <https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-video-overviews-studio-upgrades/>
- <https://www.notion.com/help/research-mode>

## Design Principles

### Content first

Reading, thinking, and writing receive the largest visual area. Navigation and
status controls remain compact. Containers exist only when they communicate
grouping, authority, focus, or elevation.

### Fewer boxes, stronger hierarchy

The redesign removes unnecessary equal-weight bordered cards. Structure comes
from whitespace, alignment, tonal surfaces, typography, and thin dividers.
Raised cards are reserved for active work, generated artifacts, dialogs, and
important decisions.

### Calm intelligence

Research Core feels advanced through precision and responsiveness, not through
constant animation, glowing borders, particle fields, or excessive glass.
Decorative effects never compete with source content.

### Evidence has a shape

Source material, user-authored notes, AI inference, unresolved contradictions,
and verified outputs have related but distinguishable presentations. Color is
never the only distinction.

### Local-first status is useful

Local/cloud route, read-only authority, index state, and watcher state are
visible when relevant and quiet when healthy. Raw paths and implementation
details remain behind inspection affordances.

## Research Core OS Shell

The main research experience uses three adaptive zones:

```text
Sources and vaults  ->  Active research surface  ->  Intelligence and outputs
```

### Knowledge rail

The left rail contains app-owned notebooks, external read-only vaults, source
selection, bookmarks, saved workspaces, recents, and collections. It supports
expanded, compact, and drawer states without losing the current selection.

### Research canvas

The center is the durable workspace for reading, writing, grounded chat,
search, graphs, Canvas files, and Podcast Studio. Existing tabs and split panes
remain authoritative. A mode changes the work surface; it does not navigate to
an unrelated visual universe.

### Intelligence rail

The right rail follows the active pane and exposes citations, backlinks,
outline, properties, tasks, related evidence, contradictions, model route, and
generated artifacts. It can become a drawer or a full split pane.

### Context bar

A compact bar communicates:

- current notebook, vault, or saved workspace;
- active source set and filters;
- editable or external-read-only authority;
- local/cloud model route;
- background research or production state; and
- command search and one context-aware Create action.

Healthy technical state collapses to a quiet summary. Warnings reveal an
explanation and one safe recovery action.

## Visual Language

### Color

Research Core uses deep blue-green structure, quiet mineral surfaces, teal
primary actions, cyan focus and intelligence accents, warm amber review states,
and restrained destructive red.

Core brand anchors remain:

| Role | Value |
|---|---|
| Deep research ink | `#071B1D` |
| Dark teal structure | `#0F766E` |
| Primary teal | `#2DD4BF` |
| Intelligence cyan | `#38BDF8` |
| Light mineral foreground | `#CCFBF1` |

Themes may reinterpret surface temperatures, but flagship brand actions and
Notebook Spark accents remain recognizable.

### Typography

The visual system uses three roles:

- a precise sans-serif for navigation, controls, and short-form interface copy;
- an editorial reading face for notes, reports, transcripts, and source detail;
- a monospaced face or tabular numerals for source fingerprints, revisions,
  timing, counts, model routes, and production stages.

The implementation must resolve the existing Inter/Geist token mismatch. Fonts
must be bundled through the existing build path and must not require a network
request when the native app launches offline.

### Shape and spacing

- Primary work surfaces use medium radii, not universally large rounded cards.
- Compact controls share consistent height and focus treatment.
- Reading columns target a comfortable line length.
- Dense knowledge utilities use smaller spacing without shrinking tap targets.
- Dialogs, menus, tooltips, toasts, and empty states use the same surface and
  depth grammar as the main shell.

### Depth

Four depth levels are sufficient:

1. canvas;
2. structural panel;
3. active or raised work surface;
4. transient overlay.

Each level has a semantic surface, edge, and shadow token. Glass is allowed
only for transient overlays and selected hero moments. It is not a default card
style.

### Motion

Motion is limited to spatial explanation and feedback:

- rail and drawer transitions;
- active pane and tab transitions;
- citation-to-source focus;
- graph selection and relationship emphasis;
- research and podcast stage progression; and
- theme-preview transitions.

Operating-system reduced motion remains authoritative. No important meaning is
available only through animation.

## Theme Architecture

### Catalog structure

The theme picker groups themes into:

1. **Featured**
2. **Light**
3. **Dark**
4. **Accessibility**
5. **Classics**

Each theme displays a miniature shell preview instead of two color dots. The
preview shows canvas, panel, primary action, accent, text, and selected state.
It also communicates light/dark mode and contrast validation.

Search and keyboard navigation are supported. Selecting a theme previews it
immediately. Apply and Restore Previous make experimentation recoverable.

### New themes

The following eight themes are added:

| Theme | Group | Character |
|---|---|---|
| Research Core Dark | Featured | Signature deep teal/cyan research instrument |
| Research Core Light | Featured | Warm mineral paper with precise teal structure |
| Deep Ocean | Dark | Navy depth with bioluminescent teal and cyan |
| Graphite Lab | Dark | Neutral charcoal with restrained Research Core accents |
| Arctic Research | Light | Cool white, graphite text, glacial cyan focus |
| Archive Paper | Light | Warm archival paper with dark teal and brass review accents |
| High Contrast Dark | Accessibility | Near-black canvas, high-luminance text and unambiguous states |
| High Contrast Light | Accessibility | White canvas, near-black text and saturated focus states |

All existing themes remain available under Light, Dark, or Classics. Existing
stored IDs remain valid. No user theme selection is silently replaced.

Research Core Dark becomes the recommended native default for a fresh install.
Research Core Light is offered alongside it during first run. Changing the
actual persisted default requires migration tests and explicit implementation
proof; the design decision alone does not mutate an existing installation.

### Required semantic tokens

Every theme must define or derive:

- canvas, foreground, panel, raised panel, popover, and sidebar;
- primary, secondary, accent, focus ring, and selected state;
- muted text, border, strong border, and separator;
- success, warning, information, destructive, and evidence states;
- graph node, graph edge, graph selection, and unresolved relationship;
- editable, external-read-only, local-model, and cloud-model indicators;
- low, medium, and overlay elevation; and
- document selection and cited-passage highlight.

Components consume semantic tokens and do not branch on theme IDs.

### Contrast and differentiation

- Normal text meets WCAG AA contrast.
- Large text and non-text controls meet applicable contrast requirements.
- Focus rings remain visible against every canvas and panel.
- Status is conveyed with text or icon as well as color.
- Selected, hovered, focused, disabled, and destructive states are visibly
  distinct in every theme.
- Themes are rejected if they only change hue while producing the same visual
  hierarchy or if their muted text becomes unreadable.

## Anchor Experience Redesigns

### Dashboard and notebook library

The dashboard becomes a calm research launch surface rather than a grid of
equal cards. Continue Research, recent notebooks, active productions, saved
workspaces, and local-model readiness receive distinct priorities. Creation is
one clear action with contextual destinations.

### Knowledge workspace

The Knowledge screen becomes the flagship expression of Research Core OS. It
keeps tabs, splits, command navigation, backlinks, graphs, and read-only vaults
while adding stronger active-pane emphasis, cleaner utility rails, anchored
citation previews, and persistent source-set context.

### Grounded chat and research

Answers expose source coverage, citation count, contradictions, confidence or
verification state, model route, and generation receipt without turning every
response into a badge wall. Selecting a citation opens the exact source context
in the current workspace.

### Podcast Intelligence Studio

Studio becomes a production workspace with:

- an output launcher;
- research-set preview;
- editorial brief and audience controls;
- visual storyboard;
- evidence-coverage meter;
- local model and voice route;
- production timeline;
- synchronized transcript and waveform;
- clickable citations; and
- output versions and comparison.

Opening Studio remains non-mutating. Production requires the existing explicit
review and confirmation gates.

### Settings and theme gallery

Settings uses a searchable two-level structure rather than a long undifferentiated
list. Appearance includes the theme gallery, density, reading typography,
motion preference, and contrast preview. Advanced technical configuration stays
available without dominating the default surface.

## Render Quality Gate

"Attractive" is treated as a verified product requirement, not a subjective
postscript.

### Anchor render matrix

The implementation produces deterministic screenshots for:

- dashboard/notebook library;
- a populated Knowledge workspace;
- grounded chat with citations and a contradiction;
- Podcast Intelligence Studio;
- theme gallery;
- empty, loading, warning, and failure states.

The required theme matrix includes:

- Research Core Dark;
- Research Core Light;
- Deep Ocean;
- Archive Paper;
- High Contrast Dark; and
- High Contrast Light.

The required viewport matrix includes:

- `1728x1117` large native workspace;
- `1440x900` standard desktop;
- `1280x800` compact desktop; and
- `390x844` narrow responsive behavior.

### Automated proof

- Theme token completeness and palette-ID lockstep tests pass.
- Contrast tests cover foreground, muted text, controls, focus, and statuses.
- Screenshot tests use stable seeded content, deterministic animation state,
  and controlled fonts.
- No anchor render has unintended horizontal overflow.
- Theme selection survives navigation and relaunch without a wrong-theme flash.
- Portaled menus, dialogs, tooltips, and toasts inherit the active theme.
- Reduced-motion screenshots contain no transitional capture artifacts.

### Human visual review

Automation cannot approve taste. A contact sheet groups the anchor renders by
theme and viewport for explicit human review. Review checks:

- immediate hierarchy;
- brand recognition;
- reading comfort;
- source/AI/evidence differentiation;
- density and alignment;
- state clarity;
- visual consistency across routes; and
- absence of generic AI-gradient or card-grid styling.

A theme cannot ship as Featured until both automated gates and the visual review
are accepted.

## Accessibility and Responsiveness

- Keyboard navigation reaches every theme, rail, pane, mode, citation, and
  Studio control.
- Focus does not disappear when panes split, drawers close, or citations open.
- Screen-reader names communicate source authority and production state.
- The narrow layout turns secondary rails into drawers; it does not compress
  three desktop columns into unreadable strips.
- Touch targets remain usable on narrow and touch-capable devices.
- Zoom to 200 percent preserves task completion on supported desktop widths.

## Performance Budgets

- Theme preview does not trigger a full application reload.
- Theme CSS does not duplicate full component styles per theme.
- Decorative layers do not cause continuous layout or paint work.
- Initial theme is available before hydration to avoid a visible flash.
- Large graphs, transcripts, and source lists retain their existing
  virtualization or bounded-rendering behavior.
- Visual polish must not delay safe access to content when local models or
  background services are unavailable.

## Failure and Recovery States

- An invalid stored theme falls back to the last valid theme, then Research
  Core Dark for a fresh install, without erasing the invalid value before a
  diagnostic receipt is available.
- A partially loaded theme never leaves unreadable text or invisible focus.
- Theme preview can be cancelled and restored.
- Missing fonts use declared local fallbacks with compatible metrics.
- A failed background research or production task retains the source set and
  exposes retry or recovery without discarding the workspace.
- External vault errors never imply that Deeper Notebook modified the source.

## Compatibility and Migration

- Existing theme IDs and persisted selections remain valid.
- The desktop palette, frontend theme catalog, API allowlist, first-run wizard,
  model manager, and memory dashboard remain lockstep-tested.
- Legacy `ONP` theme bridges remain temporary compatibility aliases while `DN`
  remains canonical.
- Existing user data, notebooks, workspaces, model configuration, and external
  vault authority are unaffected by visual-system migration.
- New visual tokens are additive until all consumers are migrated and verified.

## Delivery Sequence

1. Normalize semantic tokens and theme metadata without changing layouts.
2. Add the eight themes, categorized gallery, contrast proof, and persistence
   tests.
3. Upgrade the application shell, typography, spacing, depth, and interaction
   states.
4. Redesign Dashboard, Knowledge, grounded chat, Podcast Studio, and Settings
   anchor surfaces in controlled slices.
5. Generate the complete render matrix and visual-review contact sheet.
6. Fix cross-theme and responsive defects, then run frontend, desktop, backend,
   native-launch, and packaging gates proportional to changed surfaces.

Implementation should use vertical slices so each anchor surface remains usable
and testable. It must not combine theme migration, protected-vault mutation, or
unrelated backend changes in one unreviewable patch.

## Acceptance Criteria

The design is implemented when:

1. Research Core Dark and Light are unmistakable flagship themes.
2. All eight new themes pass token, contrast, persistence, overlay, and visual
   proof gates.
3. Existing themes and persisted selections remain functional.
4. The dashboard, Knowledge workspace, grounded chat, Podcast Studio, and theme
   gallery share one coherent visual hierarchy.
5. The anchor render matrix is complete and the contact sheet is explicitly
   approved.
6. Narrow, reduced-motion, keyboard, and high-contrast paths remain usable.
7. Source authority, provenance, and model-route states remain clear in every
   theme.
8. External Obsidian and Logseq vaults remain read-only.
9. Opening a research or Podcast Studio surface does not start generation.
10. Required frontend, desktop, native, and packaging checks pass at the exact
    implementation head.

## Decision Summary

The approved product direction is **Research Core OS** with Research Core as the
flagship identity, eight new curated themes, preserved classic themes, an
adaptive source/canvas/intelligence workspace, evidence-first visual language,
advanced Podcast Studio presentation, restrained motion, and a screenshot plus
human-review render gate.
