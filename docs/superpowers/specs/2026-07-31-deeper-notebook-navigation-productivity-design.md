# Deeper Notebook Navigation Productivity Design

**Date:** 2026-07-31

**Status:** Approved in design and written-spec review

**Baseline:** local `main` at `4d7ee247`

**Delivery slice:** Productivity Core phase 1 of 2

## Purpose

Add the navigation-oriented Productivity Core to the merged unified knowledge
engine: global bookmarks, bookmark folders and tags, Random Note, document
metrics, and named workspace snapshots.

The feature must feel native to Deeper Notebook's existing Knowledge workspace,
editor modes, command navigation, graph, search, daily-note flow, and durable
Current Session. It must not recreate a second source model or weaken the
read-only authority of mounted Obsidian, Logseq, or neutral Markdown content.

## Relationship to Earlier Designs

This specification refines and supersedes only the bookmark, Random Note,
document-metrics, and named-workspace sections of:

- `2026-07-29-deeper-notebook-overlay-productivity-design.md`; and
- `2026-07-30-deeper-notebook-unified-knowledge-engine-design.md`.

The unified knowledge engine foundation is already present at the baseline.
This slice consumes its stable identities, authority declarations,
capabilities, projections, and source revisions.

Templates and Note Composer form Productivity Core phase 2 and require a
separate implementation plan. Tasks and Journals remain the next milestone
after the complete Productivity Core passes its gates.

## Existing Foundation

The baseline already provides:

- normalized knowledge spaces, documents, blocks, relations, tasks, assets,
  views, source revisions, identity maps, and projection receipts;
- stable engine IDs and explicit `app_owned` or `external_read_only` authority;
- unified document, search, backlink, graph, provenance, and capability reads;
- a recursive pane and tab workspace with Reading, Source, Live Preview, and
  Graph modes;
- a durable autosaved Current Session for crash and restart recovery;
- the source tree, quick switcher, command palette, slash commands, and
  knowledge-aware open actions;
- app-owned Overlay notes, including daily- and unique-note flows; and
- strict redacted API contracts that do not expose canonical roots.

## Scope

### In scope

1. One global bookmark library across app-owned and external read-only spaces.
2. Nested bookmark folders and bookmark tags.
3. Bookmark targets for documents, headings or blocks, searches, graph views,
   and named workspaces.
4. Random Note across eligible unified documents, with space, authority, and
   tag filters.
5. Shared document and selection metrics in all document modes.
6. Named workspace save, load, rename, duplicate, replace, and delete.
7. An Integrated Utility Rail in the existing Knowledge sidebar.
8. Equivalent command-palette and slash-command actions.
9. Revision-safe, idempotent metadata mutations.
10. Explicit stale and unavailable target behavior.

### Out of scope

- templates and Note Composer;
- task aggregation or editing;
- journal timeline aggregation;
- external-vault writes, moves, renames, or metadata edits;
- Obsidian Sync, Publish, plugin binary compatibility, or mobile clients;
- storing copies of canonical external content in bookmark or workspace rows;
- bookmark synchronization to external `.obsidian` or Logseq configuration;
- workspace collaboration, sharing, or cloud synchronization;
- persisting document metrics; and
- changing the Current Session persistence authority.

## Product Decisions

### One global bookmark library

Bookmarks are user-owned Deeper Notebook metadata. They are global rather than
owned by a knowledge space or named workspace. A bookmark may target content in
any currently indexed space, while its folder and tags remain available even
when that target is stale or unavailable.

A bookmark has one target and belongs to zero or one folder. Tags provide
cross-folder organization. Tag display values are NFKC-normalized, trimmed,
whitespace-collapsed, and deduplicated by locale-independent case-folded keys;
the first display capitalization is preserved. Folders may nest to a maximum
depth of 16 and may be reordered among siblings. Deleting a non-empty folder
requires an explicit choice to move its children and bookmarks to the parent
or delete the folder tree and its contained bookmark metadata. Neither policy
deletes a target document.

### Stable target descriptors

Bookmark targets use a discriminated descriptor with one of these kinds:

- `document`: stable `document_id`;
- `block`: stable `document_id`, stable `block_id`, and optional source
  revision hint;
- `search`: normalized search text plus validated engine filters;
- `graph`: stable root document ID or global graph marker plus validated graph
  filters and viewport state; or
- `workspace`: stable named-workspace ID.

Descriptors may include a cached display label, authority kind, and space ID so
the library remains understandable during an engine outage. They never include
canonical body text, selected text, external absolute paths, canonical roots,
credentials, or environment-derived values.

The cached label is presentation metadata, not identity. Opening a target
always resolves the stable IDs through the unified engine or named-workspace
repository.

### Target state

Every bookmark read returns a computed target state:

- `available`: the target resolves and can be opened;
- `stale`: the document resolves but a block, revision hint, or saved view no
  longer resolves exactly;
- `unavailable`: the owning knowledge space or hydration service is not
  currently available; or
- `missing`: the stable target is known not to exist.

Stale, unavailable, and missing bookmarks remain visible. The user may repair
the target, edit its organization, or delete the bookmark. Hydration failure
never silently mutates or removes bookmark metadata.

### Random Note

Random Note selects one eligible unified document. An eligible document:

- has availability `available` and parse state `ready`;
- exposes the `read` capability;
- has a note-like kind: `note`, `page`, or `journal`;
- satisfies every requested space, authority, and tag filter; and
- is not a template, asset, unresolved placeholder, missing record, or failed
  projection.

Normal product use is nondeterministic. The service accepts an injected random
selector in tests, but the public API does not accept a seed. The response is a
stable document descriptor only. The frontend opens it through the existing
workspace store. The API never resolves or opens a filesystem path.

An empty candidate set returns HTTP 200 with `state: "empty"`; it is not an
error. Random Note responses use `Cache-Control: no-store`.

### Document metrics

Metrics are computed in the frontend from the active Markdown text buffer and
are never persisted. Reading mode uses the same hydrated normalized Markdown
buffer as Source and Live Preview, so changing modes does not change the
numbers. Composer will reuse the same pure function in phase 2.

The shared result contains:

- words;
- Unicode code-point characters including whitespace;
- Unicode code-point characters excluding Unicode whitespace;
- estimated reading minutes; and
- selection words and characters when a text selection exists.

Word segmentation uses `Intl.Segmenter` with locale `und` and word granularity,
counting segments whose `isWordLike` flag is true. The compatibility fallback
uses Unicode letter, number, and combining-mark classes and is covered by the
same fixture corpus. Character counts use Unicode code points, not UTF-16 code
units. Reading time is `ceil(words / 200)`, with zero words producing zero
minutes.

Graph mode displays metrics for its root document when one exists and an
explicit no-document state for the global graph. A selection metric appears
only for a current text selection.

### Named workspaces and Current Session

The existing Current Session remains the continuously autosaved recovery
record. It is not renamed, versioned as a named workspace, or overwritten when
a named workspace changes.

A named workspace is an explicit immutable snapshot revision. It captures:

- recursive pane layout and split sizes;
- open tabs and the active tab in each pane;
- per-tab document or view mode;
- focused pane;
- selected knowledge-space and authority filters;
- source-tree, bookmark, and search filters;
- graph root, filters, and viewport;
- sidebar mode, visibility, and width;
- active bookmark folder; and
- active draft ID when one exists, never draft content.

Document tabs in a named snapshot use stable unified document IDs. Block,
search, and graph tabs use the same typed target descriptors as bookmarks.
Cached labels may support an unavailable-state preview, but no absolute paths
or canonical source bodies are stored.

Names are unique after Unicode NFKC normalization, trimming, whitespace
collapse, and locale-independent case folding. Display capitalization is
preserved. Save, rename, duplicate, replace, and delete use explicit revision
checks.

Loading a named workspace is a two-step operation:

1. the backend validates and hydrates the complete snapshot and returns a
   restore plan with available, stale, unavailable, and missing targets;
2. the frontend asks for confirmation when any target is not available, then
   atomically replaces the workspace store from the validated plan.

Canceling, a revision conflict, a hydration error, or a failed validation leaves
the current workspace unchanged. Applying a named snapshot immediately becomes
the new Current Session and resumes normal autosave. It does not mutate the
named snapshot.

## Interaction Design

### Integrated Utility Rail

The selected layout is **Integrated Utility Rail**.

The top of the existing left sidebar exposes compact first-party actions:

- Today;
- Bookmarks;
- Random Note; and
- Workspaces.

Below those actions, the sidebar has three utility modes:

1. `Sources`, showing the existing knowledge-space and document tree;
2. `Bookmarks`, showing folder navigation, tag filters, target states, and
   bookmark management; and
3. `Workspaces`, showing Current Session status and named snapshots.

Selecting Bookmarks or Workspaces changes only the left utility panel. It does
not replace the active note, close panes, or change focus unless the user opens
a target. Today and Random Note open their resolved documents through the
existing workspace-store action.

### Bookmark interactions

The user can bookmark the active document, focused heading or block, current
search, current graph, or named workspace. The create menu shows the target
type and authority before saving. The library supports folder creation,
nesting, rename, reorder, tag edit, target repair, and delete.

Authority and state badges are explicit:

- app-owned;
- external read-only;
- stale;
- unavailable; and
- missing.

An external read-only bookmark is not visually presented as editable content.
Bookmark metadata itself remains editable because Deeper Notebook owns it.

### Workspace interactions

The Workspaces mode shows Current Session separately from named snapshots.
Named-workspace actions are Save Current As, Open, Rename, Duplicate, Replace
With Current, and Delete. Replace and Delete require confirmation. A stale
restore plan lists affected targets before the user chooses Open Available or
Cancel.

### Metrics placement

The document footer shows words, characters, and reading time. When a text
selection exists, the footer adds selection counts without replacing document
counts. The footer is keyboard reachable, has an accessible label, and does not
shift the document layout when values change.

### Command parity

The existing command registry and slash-command system expose:

- Open Today;
- Bookmark Current Target;
- Open Bookmarks;
- Random Note;
- Open Workspaces;
- Save Workspace As;
- Replace Named Workspace; and
- Toggle Document Metrics.

Commands invoke the same typed frontend services as pointer-driven controls.
They do not duplicate routing, hydration, or mutation logic.

## Persistence Design

### Migration 39

Migration 39 is additive and defines three schema-full domain tables plus one
content-free operational receipt table:

1. `knowledge_bookmark_folder`;
2. `knowledge_bookmark`; and
3. `named_knowledge_workspace`.

The operational table is `knowledge_navigation_operation_receipt`. It exists
only to make retried creates, updates, tree operations, duplicates, replaces,
and deletes durably idempotent.

Migration 39 does not alter or delete migration-38 unified projection tables,
legacy vault projections, canonical Overlay Markdown, external source files, or
the file-backed Current Session.

#### `knowledge_bookmark_folder`

Required fields:

- `schema_version` = 1;
- stable record ID;
- display `name` and normalized `name_key`;
- optional `parent_folder_id`;
- non-negative sibling `position`;
- integer `revision` starting at 1;
- `created_at` and `updated_at`.

Sibling `name_key` values are unique. Repository validation rejects cycles,
missing parents, self-parenting, and depth greater than 16.

#### `knowledge_bookmark`

Required fields:

- `schema_version` = 1;
- stable record ID;
- discriminated `target_kind` and validated `target` object;
- cached `display_label`, `authority_kind`, and optional `space_id`;
- optional `folder_id`;
- normalized string `tags`;
- non-negative sibling `position`;
- integer `revision` starting at 1;
- `created_at` and `updated_at`.

The target object is bounded and schema-validated in application contracts
before repository access. It cannot carry unrecognized fields.

#### `named_knowledge_workspace`

Required fields:

- `schema_version` = 1;
- stable record ID;
- display `name` and normalized `name_key`;
- validated `snapshot_version` = 1;
- bounded `snapshot` object;
- integer `revision` starting at 1;
- `created_at` and `updated_at`.

`name_key` is globally unique. Snapshot validation retains the existing limits
of 32 panes, 128 total tabs, and layout depth 64, and adds bounded filter,
bookmark, graph, and descriptor collections.

#### `knowledge_navigation_operation_receipt`

Required fields:

- `schema_version` = 1;
- globally unique `operation_id`;
- `operation_kind` and `entity_kind`;
- optional stable `entity_id`;
- canonical request `payload_hash`;
- terminal response status and optional resulting revision;
- stable result code; and
- `created_at` and `completed_at`.

The receipt stores no labels, names, tags, filters, snapshots, target
descriptors, canonical content, or paths. Successful and terminal conflict
receipts are retained as compact local operational evidence so delete retries
can be answered after the domain row is gone.

### Revision and idempotency contract

Every mutation supplies a caller-generated `operation_id`. Creation operations
store and replay the first successful result for the same operation and payload.
An operation ID reused with a different payload returns an idempotency conflict.

Updates and deletes additionally supply `expected_revision`. The repository
performs comparison and mutation in one transaction. A mismatch returns the
current revision number but no source content. Successful updates increment the
revision exactly once.

Repository methods—not router code—own normalization, uniqueness checks,
transaction boundaries, and replay semantics.

### Down migration

Migration 39 down removes only the four migration-39 tables and their indexes.
Migration-38 projection data and the file-backed Current Session remain
unchanged. Reapplying migration 39 recreates the empty metadata schema without
modifying earlier data. The product does not claim that bookmark, named
workspace, or operation-receipt rows survive an explicit down migration.

## API Design

All routes are local authenticated routes under the canonical Deeper Notebook
namespace. Request and response models are strict and reject unknown fields.

### Bookmark routes

Base: `/api/deeper-notebook/knowledge/bookmarks`

- `GET /bookmarks` lists metadata plus computed target state with folder, tag,
  target-kind, authority, and state filters.
- `POST /bookmarks` creates a bookmark.
- `PATCH /bookmarks/{bookmark_id}` changes organization, cached label, or
  target through a revisioned repair.
- `DELETE /bookmarks/{bookmark_id}` deletes bookmark metadata only.

Base: `/api/deeper-notebook/knowledge/bookmark-folders`

- `GET /bookmark-folders` returns the validated folder tree.
- `POST /bookmark-folders` creates a folder.
- `PATCH /bookmark-folders/{folder_id}` renames, reparents, or reorders it.
- `DELETE /bookmark-folders/{folder_id}` applies an explicit `move_children`
  or `delete_tree` policy. The latter deletes descendant folder and bookmark
  metadata in the same transaction, never target content.

List responses are deterministically ordered and cursor-paginated. Folder-tree
responses are bounded by the stored depth and collection limits.

### Workspace routes

Base: `/api/deeper-notebook/knowledge/workspaces`

- `GET /workspaces` lists named snapshot metadata without full snapshots.
- `POST /workspaces` saves the validated current state under a name.
- `GET /workspaces/{workspace_id}` returns one named snapshot.
- `POST /workspaces/{workspace_id}/restore-plan` validates and hydrates a
  snapshot without changing Current Session.
- `PATCH /workspaces/{workspace_id}` renames or replaces a snapshot.
- `POST /workspaces/{workspace_id}/duplicate` duplicates it under a new name.
- `DELETE /workspaces/{workspace_id}` deletes only the named snapshot.

No backend endpoint applies a restore plan directly to the frontend workspace.
The frontend owns the atomic in-memory apply after reviewing the complete plan.

### Random Note route

Base: `/api/deeper-notebook/knowledge/random-note`

- `POST /random-note` accepts bounded space IDs, authority kinds, and normalized
  tags, then returns `selected` with a document descriptor or `empty`.

POST and `no-store` prevent intermediary caching from turning random selection
into a stale navigation result.

### Stable failure behavior

- `404` for bookmark, folder, or named-workspace metadata not found;
- `409` for revision, normalized-name, or idempotency conflicts;
- `422` for malformed descriptors, invalid restore snapshots, cycles, excessive
  nesting, unknown fields, or collection bounds;
- `503` when the metadata repository or unified query service is unavailable.

If metadata storage is available but unified target hydration is unavailable,
bookmark and workspace reads still return their metadata with target state
`unavailable`; they do not fail the whole collection. If metadata storage itself
is unavailable, the API returns 503 and performs no partial mutation.

Error responses contain stable codes, safe IDs or revision numbers when needed,
and no canonical content, external root, absolute path, SQL, or stack trace.

## Data Flow

### Create bookmark

1. The active view creates a typed descriptor from its unified document, block,
   search, graph, or named-workspace state.
2. The frontend submits the descriptor, organization fields, and operation ID.
3. The API validates bounds, stable ID shapes, authority metadata, and target
   discriminant.
4. The repository transaction validates folder membership and records the
   revisioned metadata.
5. The response hydrates target state through the unified engine without
   copying canonical content into the bookmark row.

### Open bookmark

1. The library requests or reuses a hydrated bookmark result.
2. Available document and block targets invoke the existing workspace-store
   open action.
3. Search and graph targets invoke their existing validated view actions.
4. Workspace targets request a restore plan.
5. Stale, unavailable, or missing targets show repair and delete actions and do
   not attempt filesystem resolution.

### Restore named workspace

1. The frontend requests a restore plan for a named snapshot revision.
2. The backend validates every target against current unified projections and
   returns the complete plan plus summary counts.
3. A fully available plan may be opened directly; any other plan requires an
   explicit Open Available or Cancel decision.
4. The frontend builds the replacement workspace state off-store.
5. One atomic store action installs the validated state, then Current Session
   autosave resumes.

There is no state in which half of the old workspace and half of the named
workspace are committed to the store.

## Security and Authority Boundaries

- External sources remain `external_read_only` regardless of bookmark or
  workspace ownership.
- Bookmark and workspace records grant no content capability.
- Open actions re-check current server-calculated capabilities.
- Public contracts accept stable IDs and bounded filters, not absolute paths.
- Cached labels are treated as untrusted display text and escaped by the UI.
- Search text and tags are data, never SurrealQL fragments.
- Repository queries are parameterized.
- Mutation payloads, folder depth, tags, filters, descriptors, snapshots, pane
  counts, tab counts, and labels have explicit bounds.
- Logs and receipts contain operation IDs, metadata IDs, counts, revisions, and
  stable error codes only; no note bodies, selections, secrets, or source roots.
- No migration, repository, route, command, or UI action in this slice writes
  to an external source root.
- Tests use synthetic fixtures and temporary roots. They do not mount or scan
  either real Second Brain directory.

## Accessibility and Localization

- All utility-rail actions, folder-tree operations, target menus, workspace
  actions, confirmation dialogs, and metrics are keyboard operable.
- Active utility mode, expanded folders, target state, authority, conflict, and
  restore summaries have programmatic labels.
- Focus returns to the initiating control when a dialog closes and moves to the
  opened document only after a successful navigation.
- Reduced motion is respected; no feature depends on animation.
- New user-facing strings are added to every supported locale bundle.
- Name normalization is storage behavior and does not force display strings to
  lowercase or ASCII.

## Verification Strategy

### Migration and repository tests

- migration 38 to 39 on an existing fixture database;
- idempotent migration-39 application;
- migration-39 down removes only new metadata tables;
- down then up leaves migration-38 data and Current Session intact;
- folder uniqueness, nesting, cycle, order, and deletion policies;
- bookmark target validation and target repair;
- named-workspace name normalization and snapshot limits;
- mutation replay, operation-ID conflict, revision conflict, and exactly-once
  revision increments; and
- transaction rollback on every injected repository failure.

### Service and API tests

- hydration for all bookmark target kinds;
- available, stale, unavailable, and missing target states;
- partial hydration outage with metadata still visible;
- strict request and redacted response contracts;
- status-code and stable error-code matrix;
- cursor ordering and filter combinations;
- workspace restore summaries and snapshot revision validation;
- Random Note eligibility, space, authority, and tag filtering;
- deterministic Random Note service tests through injected randomness;
- stable empty Random Note response and `Cache-Control: no-store`; and
- proof that no request accepts or returns an absolute source path.

### Frontend unit and integration tests

- utility-mode changes preserve the active document and focus;
- bookmark create, edit, repair, organize, and delete flows;
- command, slash, and pointer actions call the same typed services;
- named-workspace atomic application and unchanged state on cancel or failure;
- stale restore confirmation and Open Available behavior;
- Current Session autosave after a named snapshot is opened;
- Unicode words, emoji, combining marks, non-Latin scripts, whitespace, empty
  text, and text-selection metric fixtures;
- metric consistency across Reading, Source, and Live Preview;
- graph-root and global-graph metric states; and
- accessibility roles, focus, keyboard actions, and locale completeness.

### Browser and runtime proof

A mocked Playwright suite proves bookmark, folder, Random Note, metrics, named
workspace, stale target, conflict, and restart-recovery flows without accessing
real external roots.

Controlled local proof then verifies:

1. migration 39 against a persistent local SurrealDB runtime;
2. API persistence and idempotency across restart;
3. Current Session recovery remains independent from named snapshots;
4. unified document, backlink, graph, and search navigation still work;
5. external target authority remains read-only; and
6. source hashes and source revisions remain unchanged by every navigation
   productivity operation.

The final gate runs the relevant Python tests, frontend tests, lint, typecheck,
production build, mocked Playwright suite, route audit, legacy-name audit, and
native macOS smoke test. An occupied port or rendered UI alone is not proof.

## Acceptance Criteria

This slice is complete only when all of the following are demonstrated:

- migration 39 is additive, reversible within its documented boundary, and
  safe over migration-38 data;
- one global bookmark library works across app-owned and external read-only
  unified targets;
- folders, tags, all five target kinds, and repairable stale states work;
- Random Note respects all filters and never opens a path directly;
- metrics are consistent, Unicode-aware, selection-aware, and unpersisted;
- named snapshots survive restart and never replace or continuously overwrite
  Current Session;
- workspace restore is atomic and preserves the current state on failure;
- revision and idempotency behavior is verified at repository and API layers;
- the Integrated Utility Rail preserves active-document context;
- command, slash, keyboard, and pointer interactions have behavior parity;
- external source hashes and revisions are unchanged after the complete proof;
- no route or contract exposes canonical roots or accepts external mutation;
- all automated and native runtime gates pass; and
- the proof record distinguishes mocked browser evidence, persistent local API
  evidence, SurrealDB evidence, and native-app evidence.

## Phase Boundary

After this specification is approved and implemented, Productivity Core phase 2
adds portable safe-variable templates and first-party Note Composer actions on
the same unified engine. It must reuse stable target descriptors, authority
checks, workspace open actions, metrics, and the Integrated Utility Rail rather
than establishing parallel feature models.

Tasks and Journals begin only after both Productivity Core phases have committed
verification records and passed completion review.
