# Deeper Notebook Unified Knowledge Engine Design

**Date:** 2026-07-30

**Status:** Approved in design review; ready for implementation planning

**Baseline:** local `main` at `26c63f71`

**Initial delivery:** Unified-engine foundation, Productivity Core, then Tasks
and Journals

## Purpose

Replace the separate app-owned Overlay and mounted-vault query models with one
normalized knowledge domain before adding the remaining first-party
Obsidian/Logseq desktop-parity features.

The engine must give every feature one stable representation of documents,
blocks, relations, tasks, assets, saved views, provenance, and capabilities
without erasing where canonical content came from or who may modify it.

The first two product milestones are:

1. Productivity Core: portable templates, first-party Note Composer actions,
   global bookmarks, Random Note, document metrics, and named workspaces.
2. Tasks and Journals: normalized task aggregation, capability-aware task
   editing, and a unified journal timeline.

Deeper Notebook's notebooks, sources, grounded chat, research, Evidence Studio,
semantic search, podcasts, memory, local-model routing, privacy gate, MCP, and
native desktop runtime remain first-class consumers of the new engine.

## Scope Boundary

This program targets first-party Obsidian and Logseq desktop knowledge-work
capabilities.

It does not include:

- proprietary Obsidian Sync compatibility;
- proprietary Obsidian Publish compatibility;
- mobile applications;
- binary compatibility with third-party Obsidian plugins;
- executable JavaScript or Python template helpers;
- external-vault mutation during the first two milestones;
- Bases, Canvas, file recovery, guarded external write-back, advanced audio
  capture, slides, or web-viewer implementation in this specification.

Those first-party desktop features remain later unified-engine slices rather
than being abandoned.

## Approved Product Decisions

### Unified but federated

The new engine provides one domain, API, identity gateway, search surface, and
capability contract.

Canonical ownership remains federated:

- Deeper Notebook Overlay Markdown remains app-owned and writable.
- Mounted Obsidian Markdown remains canonical in its selected external root.
- Mounted Logseq Markdown remains canonical in its selected external root.
- External sources remain read-only during these milestones.

SurrealDB stores normalized projections, indexes, identity mappings, operational
receipts, and app-owned view definitions. It does not silently replace mounted
files as the source of truth.

### Delivery order

The unified-engine foundation and Productivity Core complete first. Tasks and
Journals begin only after Productivity Core passes equivalence, persistence,
browser, and native macOS gates.

### Implementation-plan boundaries

This program is intentionally decomposed into three implementation plans:

1. unified domain, adapters, shadow schema, backfill, dual projection, and
   equivalence infrastructure;
2. Productivity Core cutovers and product features;
3. Tasks and Journals cutovers and product features.

The first implementation plan does not include Productivity Core UI work. It
ends with a verified unified engine that can shadow the current document,
block, relation, task, search, graph, provenance, and capability projections
without changing canonical source files.

Each later plan begins only after the preceding plan has its own committed proof
record and approved completion review.

### Templates

Templates are portable Markdown with safe variables. They do not execute
scripts, import packages, read files, inspect the environment, or make network
requests.

### Note Composer

Note Composer matches first-party knowledge-work behavior:

- merge app-owned notes;
- extract an app-owned selection into a new app-owned note;
- move app-owned content between app-owned notes;
- copy an external selection into a new app-owned note with provenance.

It remains separate from AI drafting. AI output continues to require review,
explicit insertion, and an explicit save.

### Bookmarks and workspaces

Bookmarks form one global library spanning app-owned and mounted content. They
support folders and tags.

Named workspaces are explicit snapshots. A separate autosaved Current Session
record provides crash and restart recovery without continuously overwriting a
named snapshot.

### Tasks and journals

Tasks aggregate across all indexed sources. Only app-owned Overlay tasks may be
toggled or edited in these milestones.

One journal date may display a writable Overlay daily note, read-only Obsidian
daily pages, and read-only Logseq journal pages together. The engine does not
copy, merge, or deduplicate those canonical files.

## Architecture

### Layers

The engine has five explicit layers:

1. **Source adapters** discover, decode, parse, and normalize canonical source
   bytes.
2. **Domain contracts** validate normalized immutable snapshots and capability
   declarations.
3. **Projection repository** commits a complete snapshot, identity mappings,
   relations, indexes, and receipts transactionally.
4. **Knowledge services** expose documents, search, graph, tasks, journals,
   templates, bookmarks, workspaces, and product operations.
5. **Consumers** include the Knowledge UI, research/chat citation assembly,
   Evidence Studio, search, graph, and later parity features.

Source-specific syntax does not leak into feature components. Features operate
on domain records and invoke source-specific mutations only through
capability-checked engine commands.

### Authority is data

Authority is not inferred from a path, route, UI badge, or source-format name.

Each knowledge space declares:

- `authority_kind`: `app_owned` or `external_read_only` in this specification;
- `source_kind`: `overlay`, `obsidian`, `logseq`, or `markdown`;
- canonical-root identity;
- supported adapter contract version;
- policy version;
- allowed capability set;
- availability and projection state.

Future guarded write-back may introduce a separately reviewed
`external_write_enabled` authority. No code in these milestones may synthesize
that authority.

### Capability contract

The server calculates effective capabilities for each document and block.

The initial capability vocabulary is:

- `read`;
- `copy_content`;
- `edit_body`;
- `append_body`;
- `edit_properties`;
- `toggle_task`;
- `rename`;
- `move`;
- `merge`;
- `archive`;
- `create_child`;
- `create_link`;
- `bookmark`;
- `cite`.

Capabilities are returned by the engine and checked again by command handlers.
Hiding a UI control is not authorization.

Mounted external content initially receives read, copy, bookmark, cite, and
navigation capabilities only. Overlay content receives the applicable
app-owned mutation capabilities.

## Unified Domain Model

### `knowledge_space`

Represents one canonical authority boundary.

Required fields:

- stable ID;
- display name;
- authority kind;
- source kind;
- canonical-root identity;
- format mode;
- availability state;
- projection state;
- adapter and parser versions;
- capability policy;
- created and updated timestamps.

Absolute local roots remain server-private. Public contracts expose only the
space ID and validated relative display locators.

### `knowledge_document`

Represents one normalized page, note, journal, template, asset document, or
other canonical document.

Required fields:

- stable engine ID;
- space ID;
- canonical relative locator;
- source-native stable identity when available;
- document kind;
- title;
- normalized body projection;
- properties and tags;
- canonical source hash;
- source revision ID;
- provenance;
- availability and parse states;
- effective capabilities;
- created, observed, and updated timestamps.

The normalized body is a query projection. It is not a replacement for
canonical bytes.

### `knowledge_block`

Represents ordered structure within a document.

Required fields:

- stable engine ID;
- document ID;
- parent block ID;
- ordered position;
- explicit source ID or deterministic parser ID;
- block kind;
- normalized Markdown and plain text;
- properties;
- raw and normalized task states;
- heading path;
- exact canonical source span.

Explicit Obsidian block IDs and Logseq UUIDs take precedence. Deterministic
parser IDs remain scoped to a source revision and are not presented as durable
cross-revision identities when nearby structural edits make that unsafe.

### `knowledge_relation`

Represents:

- wikilinks and Markdown links;
- heading and block references;
- embeds and transclusion;
- aliases;
- tags;
- property references;
- citations;
- unresolved targets.

Every relation preserves its source document, optional source block, exact
source span, target text, resolution state, and resolved target identity when
available.

Matching titles across spaces never merge automatically. The engine may create
an alias candidate for explicit review.

### `knowledge_task`

Projects task semantics without taking ownership of canonical text.

Required fields:

- source document and block IDs;
- raw source marker;
- normalized status;
- due, scheduled, completed, and recurrence values;
- priority;
- tags and properties;
- effective task capabilities;
- source span and source revision.

The initial normalized statuses are:

- `open`;
- `in_progress`;
- `blocked`;
- `done`;
- `cancelled`;
- `unknown`.

Adapters preserve the raw checkbox or Logseq keyword even when mapping it to a
normalized status.

### `knowledge_asset`

Represents an attachment or media target with:

- stable ID;
- owning space;
- canonical relative locator;
- media kind;
- content hash and byte size;
- availability;
- extracted metadata;
- provenance;
- source revision.

Binary content remains in its canonical source location.

### `knowledge_view`

Provides one app-owned model for:

- bookmarks and bookmark folders;
- saved searches;
- named workspaces and Current Session;
- journal and task view definitions;
- later Bases and Canvas definitions.

The record stores stable engine target IDs and validated view state. It never
stores absolute external paths.

### `knowledge_source_revision`

Records observed canonical evidence:

- space and document IDs;
- canonical content hash;
- byte size;
- encoding;
- newline style;
- observed modification metadata;
- adapter and parser versions;
- parse status;
- created timestamp.

Receipts and revisions do not contain note text, secrets, tokens, or exported
full home-directory paths.

### `knowledge_identity_map`

Maps existing overlay, vault-file, note, block, link, and task IDs into the new
namespace.

The mapping is append-only for a given source revision. Ambiguous or conflicting
mappings become reviewable records and block automatic cutover for the affected
entity.

### `knowledge_projection_receipt`

Records backfill, scan, projection, equivalence, cutover, and rollback outcomes
with:

- operation ID;
- space and optional document identity;
- source revision;
- input and output hashes;
- adapter and schema versions;
- status and stable error code;
- timestamps.

## Adapter Contract

### Input envelope

An adapter receives a bounded source envelope containing:

- knowledge-space identity;
- validated relative locator;
- canonical bytes;
- declared format mode;
- size, encoding, and modification metadata;
- prior source revision when available.

It receives no unrestricted root path, database connection, network client,
environment accessor, secret provider, or process-launch capability.

### Output snapshot

An adapter returns one immutable `KnowledgeSnapshot` containing:

- the document;
- ordered blocks;
- relations;
- tasks;
- asset references;
- source revision;
- adapter diagnostics.

The engine validates the entire snapshot before opening the projection
transaction. Partial snapshots never become visible.

Unknown syntax remains represented by retained source spans and diagnostics.
An adapter may mark a document partially supported while preserving the last
valid normalized snapshot.

### Initial adapters

- `OverlayKnowledgeAdapter`: reads canonical app-owned Markdown and supports
  capability-checked app-owned serialization.
- `ObsidianKnowledgeAdapter`: reads YAML properties, links, headings, blocks,
  embeds, tags, tasks, callouts, footnotes, and attachments.
- `LogseqKnowledgeAdapter`: reads page and block properties, hierarchy, page and
  block references, journals, task keywords, scheduling metadata, embeds, and
  namespaces.
- `MarkdownKnowledgeAdapter`: reads neutral Markdown without inventing
  source-specific semantics.

External adapter serialization is absent from these milestones.

## Read and Write Flows

### Read and projection

1. The approved source watcher observes a stable relative file.
2. The source boundary revalidates containment, symlinks, size, and encoding.
3. The engine hashes canonical bytes and creates a source envelope.
4. The selected adapter returns a normalized snapshot.
5. Domain validation verifies IDs, spans, ownership, capabilities, and limits.
6. One transaction commits the snapshot, identity mappings, relations, tasks,
   and projection receipt.
7. Exact search and graph indexes become available from the durable snapshot.
8. Embeddings run separately under the existing privacy gate.
9. Consumers receive one engine event after the durable commit.

Embedding failure does not roll back a valid parsed snapshot.

### App-owned mutations

1. The client submits an engine command with target ID, expected source
   revision, idempotency key, and requested operation.
2. The server resolves effective capabilities and rejects an unauthorized
   operation.
3. The Overlay adapter produces a preview and exact canonical patch.
4. The current canonical hash must match the expected source revision.
5. The storage boundary creates a recovery snapshot.
6. The canonical Overlay file is atomically replaced and re-read.
7. The adapter parses the resulting bytes.
8. The unified and compatibility projections commit from those exact bytes.
9. A mutation receipt records the result.

No database-only edit may report success while canonical Overlay bytes remain
unchanged.

### Note Composer transaction behavior

Merge, move, and extract show a preview before mutation.

For an app-owned merge:

- the target update commits first;
- the source moves to an app-owned recoverable archive only after the target is
  verified;
- failure to archive does not erase the source;
- every step is receipted and idempotent.

For an app-owned move or extraction:

- the destination creation/update must commit before removal from the source;
- a later source failure leaves a recoverable duplicate rather than losing
  content;
- the UI reports the incomplete operation and provides a retry.

For an external selection:

- Composer may copy it into a new Overlay note;
- provenance identifies the source document, block or span, and source hash;
- external bytes never change.

## Strangler Migration

### Stage 1: shadow schema

Add unified tables, indexes, domain contracts, adapters, repositories, and
identity mappings. Existing APIs and consumers remain unchanged.

Migration down behavior preserves any unified records once production writes
exist. Rollback disables unified consumers rather than destructively dropping
knowledge data.

### Stage 2: deterministic backfill

Backfill uses canonical files through the new adapters. Existing records seed
identity mappings but do not replace canonical parsing.

The backfill:

- is restartable and idempotent;
- checkpoints by space and canonical locator;
- records source revisions and receipts;
- never modifies source files;
- preserves previous valid unified snapshots after a failed item;
- does not mark missing legacy records as deleted automatically.

### Stage 3: dual projection

Each new scan or app-owned save projects the same canonical bytes into:

- the existing compatibility repositories;
- the unified engine.

Dual projection does not mean dual canonical writes. There remains exactly one
canonical file operation.

### Stage 4: equivalence gate

The verifier compares legacy and unified results for:

- stable identity mappings;
- document, block, link, task, property, tag, and asset counts;
- canonical hashes and relative locators;
- backlinks and outgoing links;
- graph nodes and edges;
- exact-search result membership and provenance;
- task status and journal-date projections;
- overlay revisions and capabilities.

Differences must be either zero or explicitly classified as a corrected legacy
projection defect with a reviewed fixture and migration note.

### Stage 5: feature cutover

Server-side cutover flags select the read implementation per feature. Cutover
order is:

1. document/page reads;
2. exact search and quick switching;
3. backlinks and graph;
4. templates, bookmarks, Random Note, metrics, and workspaces;
5. Note Composer;
6. task aggregation;
7. journal timeline.

A feature whose equivalence check fails remains on its compatibility read path.
Flags do not grant write capabilities.

Legacy tables, repositories, and rollback paths remain through both product
milestones and their native restart proofs.

## Milestone 1: Productivity Core

### Template library

Templates are canonical Markdown under the app-owned Overlay template area.

Safe variables include:

- local date and time;
- requested note title and kind;
- tags and properties supplied through validated UI fields;
- active knowledge-space and named-workspace identities;
- selected document, heading, block, or asset descriptors;
- relative provenance and citation descriptors.

Variable resolution supports a fixed grammar and a fixed registry. Missing
required values create a preview error. Unknown expressions are retained in the
preview and block application until corrected.

Template application always produces a preview. Applying a template creates or
updates only an app-owned draft; saving remains explicit.

### Note Composer

Composer operates on stable engine document and block IDs.

Supported actions:

- merge Overlay note into Overlay note;
- move selected Overlay content to another Overlay note;
- extract selected Overlay content into a new Overlay note;
- copy selected external content into a new Overlay note with provenance.

Destructive source-side steps are limited to app-owned content, recoverable,
previewed, explicitly confirmed, and receipted.

### Global bookmarks

Bookmark targets include:

- documents;
- headings and blocks;
- assets;
- searches and search filters;
- graph views;
- task and journal views;
- named workspaces.

Bookmarks use stable engine identities. Folders and tags organize the global
library. Missing or unavailable targets remain visible with a repairable state.

### Random Note

Random Note queries available documents through the engine.

It supports optional filters for space, folder, tag, property, and document
kind. It excludes unavailable, invalid, unsupported, stale, or capability-less
targets. An empty candidate set has a stable localized state.

Tests may provide a deterministic seed; normal product use is nondeterministic.

### Document metrics

The shared metrics contract produces:

- word count;
- character count with whitespace;
- character count without whitespace;
- estimated reading time;
- selection word and character counts.

Metrics are Unicode-aware, derived from the current displayed body or draft,
and never written into canonical content.

### Named workspaces

A named snapshot stores:

- recursive pane layout and sizes;
- open tabs and active tab per pane;
- per-tab document mode;
- focused pane;
- active space and explorer scope;
- search and graph filters;
- graph viewport;
- sidebar and utility-panel state;
- active bookmark folder;
- selected task or journal view.

Named snapshots change only through explicit Save, Replace, Rename, Duplicate,
or Delete actions with revision checks.

Current Session autosaves recoverable UI state. Draft bodies are separately
owned and referenced by ID so workspace operations cannot overwrite content.

## Milestone 2: Tasks and Journals

### Task normalization

Adapters normalize:

- Markdown task checkboxes;
- supported custom checkbox states;
- Logseq `TODO`, `DOING`, `NOW`, `LATER`, `WAITING`, `DONE`, and cancelled
  states;
- due, scheduled, completed, priority, recurrence, tag, and property metadata.

Raw syntax remains available for display and source navigation.

This milestone projects recurrence metadata but does not automatically create
the next recurring task instance.

### Task dashboard

The dashboard supports:

- status;
- due, scheduled, and completed dates;
- priority;
- recurrence presence;
- tag and property;
- knowledge space;
- document and folder;
- provenance and availability.

Every result navigates to the exact source block or best safe source span.

Overlay tasks expose supported task-edit commands. External tasks expose
read-only state, Copy, Bookmark, Cite, and source navigation.

### Journal identity

Adapters assign `journal_date` only when the date is unambiguous.

Resolution order is:

1. an explicit validated journal/date property;
2. the Overlay daily-note stable date key;
3. a supported Logseq journal filename;
4. a user-configured per-space daily-note pattern;
5. a supported unambiguous date filename.

The engine does not read excluded Obsidian or Logseq control directories to
guess configuration. Ambiguous files remain ordinary documents.

### Unified journal timeline

One date group may contain multiple canonical documents:

- one writable Overlay daily note;
- zero or more read-only Obsidian daily pages;
- zero or more read-only Logseq journal pages.

The timeline provides:

- calendar navigation;
- previous and next available date;
- direct date opening;
- missing-date states;
- task rollups;
- exact and semantic search entry points;
- source badges and provenance;
- links to each canonical document.

Opening a missing current date may create the global Overlay daily note through
the existing idempotent operation. It never creates or changes an external
journal file.

## Research-Core Integration

The unified engine becomes the source for:

- exact and semantic search context;
- graph and backlink context;
- grounded chat citations;
- research and Evidence Studio source selection;
- notebook/source collection references;
- study tools;
- memory inputs subject to existing policy.

Every cited record carries its knowledge-space identity, relative provenance,
canonical source hash, and source revision.

AI output may propose an app-owned draft or task change. It never invokes a
mutation automatically.

## State and Error Model

### Space states

- `disconnected`;
- `scanning`;
- `backfilling`;
- `dual_projecting`;
- `equivalence_pending`;
- `ready`;
- `stale`;
- `degraded`;
- `unavailable`.

### Document states

- `pending`;
- `current`;
- `stale`;
- `unsupported`;
- `invalid`;
- `ambiguous_identity`;
- `missing`.

### Required failure behavior

- Canonical hash mismatch rejects a stale mutation and preserves the draft.
- Adapter failure retains the last valid snapshot and records a stable error.
- Projection failure exposes no partial new snapshot.
- Database failure never changes external source files.
- Identity ambiguity creates a reviewable candidate and blocks automatic merge.
- Source unavailability retains stale provenance and disables mutation.
- Equivalence drift blocks only the affected feature cutover.
- Compatibility fallback does not alter capability decisions.
- Embedding failure retains exact search and durable normalized content.
- Recovery snapshot failure blocks an app-owned destructive operation.
- Receipt failure prevents reporting mutation success.

## Security and Privacy

- All roots are explicitly selected and validated.
- Canonical locators are relative and source-bound.
- Source adapters receive bounded input and no ambient authority.
- Server-issued capabilities are checked at the command boundary.
- External mutation capabilities do not exist in these milestones.
- Obsidian and Logseq control directories remain excluded.
- Raw source, secret, credential, Git-internal, and protected areas remain
  excluded according to existing policy.
- Discovery, parsing, normalization, exact search, task aggregation, and
  journal grouping are local operations.
- Semantic indexing follows the existing local/cloud privacy gate.
- Note contents and tokens never appear in receipts or logs.
- Exported diagnostics redact user-home prefixes and absolute roots.
- Symlink, containment, time-of-check/time-of-use, size, and encoding defenses
  apply before adapter invocation.

## Verification Strategy

### Contract and adapter tests

Golden fixtures cover:

- Overlay reserved frontmatter and editable body separation;
- Obsidian properties, links, headings, blocks, embeds, tasks, callouts,
  footnotes, and attachments;
- Logseq hierarchy, properties, references, UUIDs, journals, tasks, schedules,
  and namespaces;
- neutral Markdown;
- malformed content;
- unknown syntax;
- mixed newlines and supported encodings;
- stable and ambiguous identity cases;
- capability derivation.

### Migration tests

- clean migration up;
- pre-existing schema upgrade;
- down/up preservation behavior;
- restartable and idempotent backfill;
- interrupted checkpoint recovery;
- dual-projection transaction failures;
- identity-map conflicts;
- compatibility rollback;
- feature-flag cutover and fallback.

### Equivalence verifier

The verifier records exact counts, IDs, hashes, locators, relations, tasks,
properties, tags, graph membership, search membership, provenance, and
capabilities for both implementations.

The report contains no note content, tokens, or exported absolute roots.

### Product tests

Backend and frontend tests cover:

- template validation, preview, and application;
- Composer previews, recovery, partial-failure behavior, and external copy;
- bookmark organization and stale targets;
- deterministic Random Note tests and empty states;
- Unicode metrics;
- workspace snapshots, revisions, recovery, and draft isolation;
- task normalization, filters, editing permissions, and source navigation;
- journal date resolution, grouping, navigation, and task rollups;
- accessibility, localization, keyboard behavior, and announcements.

### Browser proof

A strict mocked browser:

- records every mutating request;
- rejects unknown routes and methods;
- proves only Overlay commands mutate;
- exercises restart hydration and Current Session recovery;
- proves external task and journal controls remain read-only;
- checks source badges, provenance, conflict recovery, and focus restoration.

### Native macOS proof

The controlled proof uses marked synthetic Overlay and external roots.

It verifies:

- migration and backfill;
- dual projection and equivalence;
- Productivity Core persistence across process restart;
- Tasks and Journals persistence after their milestone;
- canonical source fingerprints and external Git state remain unchanged;
- cleanup stops only the owned runtime and leaves no live mount or scanner.

### Real Second Brain proof

Only after synthetic and native gates pass, run a separately controlled
read-only proof against the selected `2nd Brains` root.

The proof:

- records source fingerprints and Git state before and after;
- scans twice and proves idempotency;
- preserves trust-manifest provenance;
- reconciles normalized documents, links, tasks, properties, and journals;
- performs no source mutation;
- stops the owned runtime and scan at completion.

### Windows release gate

A real packaged Windows environment must prove migration, backfill, launch,
restart, rollback, and persistence before release. macOS results do not satisfy
this gate.

## Completion Criteria

The unified-engine foundation is complete when:

- all supported sources project into the normalized domain;
- canonical ownership and capabilities remain explicit;
- backfill and dual projection are restartable and idempotent;
- equivalence passes for every cut-over read surface;
- one feature can return to its compatibility path without data loss;
- no external source bytes change.

Productivity Core is complete when:

- all six selected capabilities use the unified engine;
- templates remain portable and non-executable;
- Composer operations are previewed, recoverable, and capability-checked;
- bookmarks and workspaces use stable engine identities;
- Current Session restores without overwriting drafts;
- native restart and external-fingerprint gates pass.

Tasks and Journals are complete when:

- task syntax normalizes without erasing raw source semantics;
- only Overlay task mutations are available;
- journal dates group separate canonical documents without copying;
- dashboard, navigation, search, research citations, and restart persistence
  pass;
- external fingerprints and Git state remain unchanged.

Legacy projections may be retired only under a later cleanup specification
after both milestones and platform release gates have passed. They are not
deleted by this program.

## Later Unified-Engine Slices

After these milestones:

1. Bases and database views.
2. Canvas.
3. File recovery and revision UI.
4. Advanced attachment, audio, slides, and web-viewer workflows.
5. Guarded external-vault write-back with diff, backup, conflict, rollback, and
   per-area policy.
6. Themes and remaining first-party workspace refinements.

Each slice receives its own approved design, implementation plan, and proof
record.
