# Deeper Notebook Overlay Productivity Design

Date: 2026-07-29
Status: Approved for planning
Scope: App-owned Markdown overlay, daily and unique notes, safe and scripted
templates, quick capture and research composition, global bookmarks, random
note, document metrics, and named workspace persistence

## Goal

Add the next Obsidian- and Logseq-style productivity layer to Deeper Notebook
without weakening the read-only contract around mounted external vaults.

The feature must let a user:

- create one global daily note for a local calendar date;
- create collision-safe unique notes named from a timestamp and title;
- create reusable Markdown templates with safe variables;
- use both JavaScript and Python template helpers through one restricted API;
- capture notes quickly or compose source-grounded drafts with AI;
- bookmark knowledge targets globally;
- open a random indexed note across overlay and mounted vaults;
- inspect words, characters, reading time, and selection metrics;
- save and restore multiple named Knowledge workspaces;
- browse overlay and mounted notes together with clear write-authority badges.

Canonical user notes and Markdown templates must remain portable Markdown.
Mounted Obsidian, Logseq, and neutral Markdown sources remain canonical,
external, and read-only.

## Existing Foundation

Deeper Notebook already provides:

- approved-root, symlink, TOCTOU, size, encoding, and provenance checks for
  external vaults;
- read-only Obsidian, Logseq, and neutral Markdown projections;
- canonical file, note, block, link, task, property, tag, backlink, graph, and
  search identities;
- durable recursive panes, tabs, focus, and per-tab view modes;
- Reading, Source, Live Preview, and Graph document modes;
- a knowledge-aware quick switcher, command palette, slash commands, and
  exact/indexed search;
- app-owned notes attached to notebooks;
- model routing, source-grounded generation, citation contracts, and explicit
  user review surfaces;
- a guarded desktop data-root resolver and native lifecycle.

This design adds a new app-owned authority. It does not convert an external
vault into a writable mount and does not add mutation methods to the external
vault API.

## Product Decisions

### Ownership model

The product exposes one writable virtual knowledge root named
**Deeper Notebook Overlay**.

Its files live beneath the resolved Deeper Notebook data root. They never live
in:

- the source repository;
- `/Users/Antman/Desktop/2nd Brains`;
- an Obsidian or Logseq control directory;
- any other mounted external root.

Overlay notes may link to external notes and external notes may resolve
backlinks from the overlay projection. This relationship does not transfer
write authority.

### Daily notes

There is one global daily note per local calendar date.

- The stable date key is `YYYY-MM-DD`.
- The visible default path is `Daily/YYYY-MM-DD.md`.
- Opening a date performs an idempotent lookup and creates the file only when
  it does not exist.
- Concurrent requests for the same date resolve to one note.
- A selected daily template may initialize the note.
- A later timezone change does not rename an existing note. Opening "Today"
  always uses the current local calendar date and then resolves its stable key.
- Past and future dates are valid explicit targets.

Daily notes are global rather than per-vault. They can link to any indexed
overlay or mounted note.

### Unique notes

The default visible name is:

`YYYYMMDD-HHmm Title.md`

- The timestamp uses the user's local time at creation.
- A stable overlay note ID is generated independently from the path.
- Same-minute, same-title collisions use deterministic numeric suffixes.
- The initial filename remains stable when editable title metadata changes;
  explicit file rename is outside this slice.
- Untitled creation uses a localized `Untitled` fallback without producing an
  empty or hidden filename.

### Templates

Markdown templates are canonical files under the app-owned overlay. They may
contain:

- ordinary Markdown;
- validated frontmatter defaults;
- safe variable expressions;
- references to zero or more trusted JavaScript or Python helpers.

The first safe-variable contract includes:

- local date and time;
- requested note title and note kind;
- tags and properties supplied by the user;
- selected source, note, heading, and block descriptors;
- canonical relative provenance and citations;
- active named-workspace identity;
- an explicitly approved AI-result object.

Safe variables cannot traverse arbitrary object properties, invoke host
functions, read files, make requests, or obtain secrets.

### Script trust

Locally authored JavaScript and Python helpers execute automatically without a
per-run prompt, subject to the sandbox and resource limits in this design.

"Locally authored" means the helper was created or edited through the app-owned
template editor and its current fingerprint is recorded as trusted.

These helpers are not automatically trusted:

- imported helpers;
- helpers copied directly into the data directory;
- helpers whose bytes changed outside Deeper Notebook;
- helpers whose accepted runtime or API-contract version changed.

Those helpers are quarantined until the user accepts the exact fingerprint.
Trust applies to one fingerprint, language, runtime contract, and template ID.
It is not inherited by a later edit.

### Composer

One Composer surface supports two related workflows:

1. quick capture of text, tags, properties, links, and a selected template;
2. source-grounded drafting or transformation through the existing AI routing
   and citation contracts.

AI output always appears in a review preview. The only actions that can move it
into a draft are explicit **Insert** or **Replace selection** actions. Saving the
draft remains a separate explicit action. A generation response never writes a
file directly.

### Bookmarks

Bookmarks form one global library shared by every named workspace.

Bookmarkable targets include:

- overlay or external notes;
- headings and blocks with canonical identities;
- searches and search filters;
- graph views;
- named workspaces.

Folders and tags organize bookmarks. Bookmark targets use stable IDs and
validated relative provenance, never absolute external paths. Missing and stale
targets remain visible with a repairable status rather than being silently
deleted.

### Random Note

Random Note draws from all currently available indexed overlay and external
notes.

- Optional vault and tag filters narrow the candidate set.
- Missing, invalid, stale, or unavailable records are excluded.
- Empty candidate sets produce a stable empty state.
- Test code can supply a deterministic selection seed; normal product use is
  nondeterministic.
- Selection opens the canonical note through the workspace store, never by
  directly resolving a source path.

### Document metrics

The document footer displays:

- word count;
- character count with and without whitespace;
- estimated reading time;
- selection word and character count when a selection exists.

Metrics are derived from the current document or draft and are not written into
canonical Markdown. The counting contract is Unicode-aware and shared by
Reading, Source, Live Preview, and Composer surfaces.

### Named workspaces

A named workspace persists:

- recursive pane layout and sizes;
- open tabs and active tab per pane;
- per-tab document mode;
- focused pane;
- file-tree, bookmark, and search filters;
- graph viewport and graph filters;
- sidebar visibility and size;
- the active bookmark folder;
- the active overlay or mounted-vault scope.

Composer drafts are app-owned and autosaved separately. A workspace stores only
the active draft ID, so switching, replacing, or deleting a workspace cannot
overwrite draft content.

Workspace names are unique under normalized Unicode case folding. Rename,
duplicate, replace, and delete operations use explicit revision checks.

## Architecture

### Authority separation

The backend maintains two explicit authorities:

```text
external-vault
  canonical owner: mounted filesystem
  Deeper Notebook authority: read, index, cite

overlay
  canonical owner: Deeper Notebook data root
  Deeper Notebook authority: create, read, revise, recover
```

The discriminant is carried through backend contracts, database records,
frontend schemas, query keys, commands, and UI badges.

An overlay mutation accepts an overlay space ID and overlay note ID. It does not
accept an external vault ID, external note ID, or caller-supplied absolute path.
The external vault router receives no new mutation routes.

### Overlay filesystem

The data-root resolver supplies the canonical overlay root. A versioned layout
keeps user-visible Markdown separate from internal control state:

```text
overlay/
  v1/
    Daily/
    Notes/
    Templates/
      Markdown/
      JavaScript/
      Python/

overlay-state/
  revisions/
  receipts/
  quarantine/
  recovery/
```

Only the overlay storage service can resolve paths beneath these roots.
Callers provide typed IDs and logical names.

The service:

1. validates IDs, names, extensions, and size limits;
2. resolves the owned root through descriptor-safe containment;
3. verifies the current revision and fingerprint;
4. writes a temporary file in the destination directory;
5. flushes file contents and metadata;
6. atomically replaces the target;
7. flushes the containing directory when supported;
8. appends a revision and mutation receipt;
9. schedules projection refresh.

Failed writes remove only the exact temporary file owned by the operation.
Existing canonical bytes remain unchanged.

### Canonical Markdown identity

Overlay Markdown frontmatter contains a reserved `deeper_notebook` object:

```yaml
deeper_notebook:
  id: "overlay-note-id"
  kind: "daily"
  created_at: "2026-07-29T15:42:00-05:00"
  updated_at: "2026-07-29T15:42:00-05:00"
  date_key: "2026-07-29"
  template_id: "optional-template-id"
```

The parser validates reserved fields and preserves user frontmatter. A user
cannot change the stable ID by editing form fields. If the on-disk reserved ID
is missing, duplicated, or inconsistent with the repository record, the note
enters reconciliation rather than being silently assigned a new identity.

### Projection

Overlay files use the existing bounded Markdown parser and canonical note graph
contracts. Overlay-specific repository records own writable revision state,
then project into the common read graph used by:

- Knowledge Explorer;
- backlinks and outgoing links;
- blocks, tasks, properties, and tags;
- text and semantic search;
- citations and context building;
- local and global graph views;
- quick switcher and command palette.

Projection state is derived. A successful canonical write is not rolled back
only because indexing or embedding is temporarily unavailable. Instead:

- the prior valid projection remains queryable;
- the new revision is marked `projection_pending` or `projection_failed`;
- retry is idempotent by note ID, revision, and content hash;
- the UI shows the exact state and retry action.

### App-owned metadata repositories

SurrealDB stores:

- overlay spaces and note revision heads;
- mutation and recovery receipts;
- template definitions, helper fingerprints, and trust state;
- composer drafts and draft revisions;
- bookmarks, folders, and tags;
- named workspaces and workspace revisions.

Canonical note and Markdown-template content remains in Markdown files. Database
records do not become an alternate canonical copy of that content.

### APIs

New authenticated routes are grouped under a canonical overlay namespace.
Conceptual resources are:

- overlay notes and revisions;
- daily-note resolution;
- unique-note creation;
- templates and helper trust;
- template preview and execution;
- composer drafts and reviewed AI insertion;
- bookmarks and folders;
- random-note candidate selection;
- named workspaces.

Every mutation uses an expected revision or creation idempotency key. Conflicts
return typed, localized-safe errors without including absolute data-root paths,
source text, secrets, or raw runtime tracebacks.

### Frontend state

TanStack Query owns server resources and invalidation. Focused local state is
split by responsibility:

- the durable Knowledge workspace store continues to own live pane/tab state;
- a composer store owns current draft interaction before server persistence;
- template-run state is ephemeral and keyed by request generation;
- selection metrics remain component-local;
- modal and focus-restoration state is never persisted.

Named workspace load validates the server document before replacing live state.
A failed load leaves the current workspace untouched.

## Script Runtime

### Shared capability API

Both language adapters receive the same versioned, immutable input and must
return the same validated output shape.

Allowed input:

- safe template variables;
- bounded user-entered parameters;
- selected canonical source descriptors and cited excerpts already approved for
  the template invocation;
- optional reviewed AI result;
- deterministic helper utilities for text, dates, tags, and properties.

Allowed output:

- Markdown text;
- tags;
- user properties outside the reserved identity namespace;
- bounded template sections;
- non-secret diagnostics suitable for the preview.

The runtime exposes no ambient filesystem, process, environment, package,
network, credential, clipboard, desktop, database, model-provider, or external
vault API.

### Isolation

JavaScript and Python execute outside the API and UI processes through dedicated
runtime adapters.

Each invocation has:

- a sanitized, explicit input message;
- no inherited secrets or provider environment;
- an empty or runtime-owned working directory;
- strict wall-clock, CPU, memory, recursion, and output limits;
- an invocation-specific process or isolate lifetime;
- a cancellation path;
- schema validation before output reaches Composer.

Language-level restrictions alone are not treated as a security boundary. The
platform adapter must pass a startup self-test proving the required isolation.
If it cannot, scripted templates are disabled with a stable explanation.
Deeper Notebook never falls back to unrestricted `node`, `python`, `exec`,
`eval`, or a shell subprocess.

The implementation plan must select runtime technologies whose isolation
contracts can be tested on macOS and Windows. The product may ship the safe
variable engine while a platform's script adapter remains unavailable; it may
not claim script support on that platform without the sandbox proof.

### Execution receipts

Each invocation records:

- request and template IDs;
- helper fingerprint and language;
- capability API and runtime versions;
- start time and bounded duration;
- result status and typed failure code;
- input descriptor hash and output hash;
- whether output was inserted, discarded, or left in preview.

Receipts exclude prompt text, note text, generated output, environment values,
credentials, and absolute paths.

## User Experience

### Knowledge Explorer

The Deeper Notebook Overlay appears above mounted vaults. It has a writable
overlay badge. Mounted vaults retain their existing read-only external-file
badge.

A utility section exposes:

- Today;
- New Unique Note;
- Templates;
- Bookmarks;
- Random Note;
- Workspaces.

The tree and quick switcher combine overlay and mounted candidates while
preserving their authority badges.

### Composer

Quick Capture opens a compact composer. Expansion reveals:

- title and note-kind controls;
- template selection and template parameters;
- tags and properties;
- selected source links and citations;
- AI drafting and transformation actions;
- document metrics;
- revision-safe Save.

AI responses enter a comparison preview with **Insert**, **Replace selection**,
and **Discard**. Focus returns to the invoking field or command after dialogs
close.

### Commands

The existing typed command registry gains safe overlay commands:

- open today's note;
- create unique note;
- open Composer;
- apply or preview template;
- bookmark current target;
- open random note;
- save, load, duplicate, rename, or delete a named workspace;
- show document metrics.

External mutation commands remain absent. Slash commands use the same registry
and safety classification.

### Template state

The template UI shows stable states:

- safe-variable only;
- trusted;
- changed;
- quarantined;
- sandbox unavailable;
- running;
- succeeded;
- failed;
- timed out.

A failed or quarantined script never produces a partial note or partial draft
update.

### Accessibility and localization

All controls use the existing Notebook Spark/Research Core tokens and component
primitives.

The feature must provide:

- keyboard-complete creation, composition, bookmarking, and workspace switching;
- focus restoration after dialogs and command surfaces;
- screen-reader announcements for creation, saves, conflicts, script state,
  AI-preview state, and random-note empty state;
- reduced-motion behavior;
- exact locale-key parity for all supported locales;
- no color-only distinction between writable overlay and read-only external
  content.

## Concurrency, Failure, and Recovery

### Creation idempotency

Daily creation is keyed by overlay space and date key. Unique-note creation is
keyed by a client-generated idempotency key. Replaying a successful request
returns the original note.

### Optimistic concurrency

Every overlay update and metadata mutation includes an expected revision.
Revision mismatch returns a conflict document containing hashes, timestamps,
and safe metadata, not note contents from an unrequested record.

Composer autosave is revisioned independently from canonical note Save.

### Revisions

Before replacing an existing overlay note, the service stores a bounded
revision record and verifies its hash. Revision retention is policy-driven and
must never remove the last recoverable version.

Recovery creates a new head revision; it does not erase history or mutate an
external source.

### Script failure

Timeout, crash, resource violation, invalid output, and sandbox self-test
failure:

- leave canonical Markdown unchanged;
- leave the current Composer draft unchanged;
- terminate the invocation;
- append a content-free receipt;
- expose a localized recovery action.

### AI failure

Provider errors, cancellation, stale generations, missing provenance, and
invalid citations leave the draft unchanged. A response from an older request
generation cannot replace a newer preview.

### Missing bookmark and workspace targets

Missing bookmark targets remain visible as stale. Loading a named workspace
skips unavailable tabs only after presenting a restore summary; invalid
workspace state cannot overwrite the current live layout.

## Security Boundaries

The following are non-negotiable:

- no overlay resolver accepts an absolute path from an API caller;
- no overlay mutation accepts an external vault or external note identity;
- no new `PUT`, `PATCH`, `POST`, or `DELETE` route is added beneath the external
  vault resource namespace;
- no script runtime inherits secrets, model keys, data-root paths, or provider
  configuration;
- no template variable can access arbitrary object properties or host functions;
- no AI response can write a canonical file;
- no external note checkbox, property, filename, or content becomes editable;
- no error or receipt exposes an absolute private-vault path;
- no migration or rollback removes existing notebooks, external projections, or
  source files.

Protected write-back remains a separate future design requiring per-vault
permission, source-fingerprint checks, round-trip serialization, user-visible
diffs, conflict detection, backup, atomic replacement, rollback, and optional
Git checkpoint policy.

## Testing Strategy

### Pure contract tests

- overlay IDs, logical names, reserved frontmatter, and authority discriminants;
- local-date and date-key resolution, including DST and timezone changes;
- unique-note filenames, slugs, and deterministic collisions;
- safe-variable parsing and rejection of traversal or calls;
- JavaScript/Python shared input and output schemas;
- Unicode word, character, selection, and reading-time metrics;
- bookmark target descriptors and stale-state transitions;
- random-note filtering and seeded selection;
- named-workspace normalization and revision rules.

### Filesystem and repository tests

- approved-root containment, symlink and hard-link defenses, TOCTOU replacement,
  case folding, Unicode normalization, oversize content, and unsupported
  encodings;
- atomic create/update and injected failure at every durability boundary;
- daily-note concurrent creation and request replay;
- revision creation, retention, and recovery;
- parser/projection retry without canonical-file rollback;
- no external-vault write method or route;
- migration clean up/down/up cycles scoped to overlay records.

### Script adversarial tests

For both JavaScript and Python:

- filesystem reads and writes;
- directory and environment discovery;
- network and DNS access;
- shell and child-process creation;
- package or module loading outside the approved runtime;
- database, clipboard, and desktop access;
- infinite loops, recursion, memory pressure, oversized input/output, malformed
  Unicode, cancellation, and runtime crash;
- fingerprint changes, import quarantine, API-version changes, and stale trust;
- sandbox-startup self-test failure and proof that no unrestricted fallback runs.

### Frontend tests

- overlay versus external authority badges and controls;
- Today, unique-note, template, bookmark, random-note, metrics, and workspace
  commands;
- Composer quick capture, template preview, AI preview, explicit insertion, and
  stale generation suppression;
- draft autosave isolation from named workspace mutations;
- bookmark folders/tags and missing-target states;
- workspace load validation and focus restoration;
- locale parity, live announcements, reduced motion, and keyboard navigation.

### Browser and native proof

A strict mocked-browser fixture proves the full overlay flow while rejecting
unexpected network traffic.

A controlled native macOS proof must:

1. use a disposable app-owned overlay and synthetic external vault;
2. record external source fingerprints and Git status before launch;
3. create/reopen a daily note and create colliding unique notes;
4. run safe-variable, JavaScript, and Python templates;
5. prove escape attempts fail;
6. use quick capture and reviewed AI insertion;
7. create bookmarks and named workspaces;
8. restart the native app and restore overlay, drafts, and workspace state;
9. re-record external fingerprints and Git status unchanged;
10. verify cleanup stops only the owned runtime.

Equivalent packaged Windows sandbox, persistence, upgrade, and restart proof is
a release gate and may not be inferred from macOS results.

## Completion Gate

This slice is complete only when:

- canonical overlay Markdown is portable, root-bounded, atomic, revisioned, and
  recoverable;
- one global daily note per local date is idempotent across concurrency and
  restart;
- unique-note collisions never replace a file;
- safe variables and both requested script languages use the approved restricted
  capability contract;
- script isolation passes adversarial tests and fails closed when unavailable;
- AI output requires explicit insertion and explicit Save;
- global bookmarks, Random Note, document metrics, and named workspaces behave
  as specified;
- external vault routes and UI remain read-only;
- external source hashes and Git state remain unchanged through browser and
  native proof;
- existing notebooks, research, Studio, Capture, podcasts, memory, model,
  workspace, editor, command, search, graph, and citation regressions pass;
- backend, frontend, locale, lint, type, production-build, mocked-browser, and
  native macOS gates pass;
- Windows packaged proof remains explicitly open until run on Windows.

## Explicitly Deferred

This design does not include:

- write-back to mounted external vaults;
- external checkbox toggles, rename, move, delete, serializer, diff, backup,
  conflict resolution, or rollback;
- editable Canvas, Bases/database views, task dashboards, or file recovery;
- Obsidian third-party plugin binary compatibility;
- proprietary Obsidian Sync or Publish compatibility;
- mobile applications;
- unrestricted JavaScript, Python, shell, filesystem, network, or package access.
