# Deeper Notebook Second-Brain and Obsidian-Parity Design

**Date:** 2026-07-26

**Author:** Anthony Henry with Codex

**Repository:** https://github.com/Antman1526/Deeper-Notebook

**Reference workspace:** `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains`

**Status:** Approved by the user on 2026-07-26

## Purpose

Make Deeper Notebook a local-first personal knowledge workspace with first-party
Obsidian desktop feature parity while retaining Deeper Notebook's existing
research, evidence, local-AI, podcast, memory, MCP, and privacy capabilities.

The existing `2nd Brains` folder remains the canonical source of truth. Deeper
Notebook mounts, parses, indexes, searches, visualizes, and reasons over its
files. External-file write-back starts disabled and becomes available only
after round-trip and rollback gates pass.

## Selected Scope

### Included

Native Deeper Notebook equivalents for Obsidian's first-party desktop
knowledge-work capabilities:

- Audio recorder.
- Backlinks and unlinked mentions.
- Bases with table, list, and card views, filtering, sorting, grouping, and
  formulas.
- Bookmarks.
- Canvas.
- Command palette.
- Daily notes.
- File explorer.
- File recovery and local revisions.
- Footnotes view.
- Format conversion.
- Graph view.
- Note composer.
- Outgoing links.
- Outline.
- Page preview.
- Properties and properties view.
- Quick switcher.
- Random note.
- Search.
- Slash commands.
- Slides.
- Tags view.
- Templates.
- Unique note creator.
- Web viewer.
- Word count.
- Workspaces.

The workspace also supports:

- Markdown source mode.
- Live preview and rendered reading mode.
- Internal links to pages, headings, and blocks.
- Embeds and transclusion.
- Attachments.
- Multiple tabs and panes.
- Themes and Deeper Notebook's approved brand tokens.

### Excluded

The selected scope does not recreate:

- Obsidian Sync's proprietary hosted service.
- Obsidian Publish's proprietary hosted service.
- Obsidian mobile applications.
- Binary compatibility with third-party Obsidian plugins.

Deeper Notebook can later define its own extension API under a separate design.

## Keep Deeper Notebook's Existing Capabilities

No parity work removes or replaces:

- Notebooks, sources, notes, and transformations.
- Grounded chat and source citations.
- Ask and semantic synthesis.
- Research and Evidence Studio.
- Local and cloud model selection.
- Privacy gate and local/cloud routing.
- MCP tools and local web search.
- Podcasts and synchronized transcripts.
- Memory and recall.
- Capture Inbox.
- Study tools.
- Import/export and artifact generation.
- Native desktop launcher and local services.

The knowledge workspace enriches these capabilities. It does not create a
separate application inside Deeper Notebook.

## Reference-Workspace Findings

The inspected workspace contained:

- `Obsidian Brain`
- `Logseq Brain`
- `brain-engine`
- A Git repository with pre-existing modifications and lock files.

The analysis observed:

- 29 Obsidian Markdown files.
- 20 Logseq Markdown files.
- 183 Obsidian wikilinks.
- 133 Logseq wikilinks.
- 21 Obsidian files using YAML frontmatter.
- 70 Logseq property lines.
- 27 open tasks and 21 completed tasks at inspection time.
- A connector manifest with 21 approved documents.
- 12 approved source-evidence documents.
- 9 approved synthesis documents with `derivedFrom` provenance.
- Unique SHA-256 content hashes for all 21 exported documents.
- `writeBack.enabled = false`.

The workspace rules require:

- Never delete files.
- Treat `sources/` and `inbox/raw/` as immutable.
- Log every operation.
- Keep writes inside the vault.
- Require explicit approval for external actions.
- Preserve originals when ingesting.
- Commit automated loop work only when Git is healthy.

### Path drift

`brain-engine/config.json` and the existing connector manifest still identify
the former root:

`/Users/Antman/Desktop/2nd Brains`

The inspected root is:

`/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains`

Deeper Notebook detects and reports this stale-path condition. It does not
silently rewrite the engine configuration or manifest.

## Existing Deeper Notebook Foundations

The current application already provides:

- Markdown note editing and note CRUD.
- Notebooks, sources, notes, and graph membership relations.
- Full-text and vector search across sources and notes.
- One-time Markdown/ZIP folder import.
- A Capture Inbox watcher with approved roots, stability windows, and
  fingerprint deduplication.
- A React Flow notebook map.
- Source provenance and artifact receipts.
- Filesystem path validation and unsafe-root rejection.
- Import size limits and ZIP traversal protection.
- Export overwrite protection.

The application does not yet provide:

- External vault mounts or live vault synchronization.
- Parsed wiki-link and backlink edges.
- Block-level outliner data.
- Journals and daily notes.
- First-class task records.
- Persisted note properties and tags.
- Note templates.
- General editable canvas.
- Bases.
- File revisions for externally mounted notes.
- Obsidian-class workspace and pane management.

## Architecture

### Canonical-source rule

Mounted Markdown and asset files remain canonical. SurrealDB stores the parsed,
queryable projection and operational receipts.

The database projection can be rebuilt from the files and receipts. Deeper
Notebook does not require users to abandon portable Markdown.

### Read path

1. A user registers an approved vault root.
2. The filesystem adapter canonicalizes the root and rejects unsafe/system
   locations.
3. The watcher waits for file stability and computes a content hash.
4. The format detector selects Obsidian, Logseq, or neutral Markdown parsing.
5. The parser produces pages, blocks, links, properties, tags, tasks, embeds,
   and attachment references.
6. A transaction updates the vault projection and appends a sync receipt.
7. Search indexing and embeddings run asynchronously.
8. The UI updates backlinks, graph, explorer, properties, tasks, and search
   state.

Durable parse/index completion is separate from embedding completion.

### Write path

External write-back is initially disabled.

When enabled for an approved vault and area:

1. The editor captures the base content hash.
2. The user saves or invokes a write-capable command.
3. Deeper Notebook renders the exact file diff.
4. Policy checks validate the root, relative path, area, operation kind, and
   symlink state.
5. The current file hash is compared with the base hash.
6. A mismatch creates a conflict and blocks the write.
7. A backup is created.
8. Content is written to a sibling temporary file and flushed.
9. The temporary file atomically replaces the target.
10. The written bytes are re-read and hashed.
11. An append-only receipt records the result and rollback location.
12. The watcher re-indexes the file.

No database failure, receipt failure, or conflict falls through to an
unrecorded file write.

## Domain Model

### `vault_mount`

Represents an approved local root.

Fields:

- `id`
- `name`
- `root_path`
- `format_mode`: `obsidian`, `logseq`, `mixed`, or `markdown`
- `status`
- `watch_enabled`
- `write_policy`
- `protected_globs`
- `parser_version`
- `last_scan_started_at`
- `last_scan_completed_at`
- `created`
- `updated`

The root path is local-only and never sent to an LLM or exported without an
explicit operator action.

### `vault_file`

Tracks one canonical external file.

Fields:

- `id`
- `vault_id`
- `relative_path`
- `file_kind`
- `format`
- `content_hash`
- `size_bytes`
- `modified_ns`
- `encoding`
- `parse_status`
- `parse_error_code`
- `indexed_at`
- `deleted_state`

Deletion detection marks a record missing. It does not delete knowledge records
until a separate reconciliation decision.

### `Note` extensions

Existing notes gain optional external-document metadata:

- `vault_id`
- `vault_file_id`
- `source_format`
- `canonical_external`
- `properties`
- `tags`
- `source_hash`
- `external_state`

Normal Deeper Notebook notes leave these fields empty.

### `note_block`

Represents ordered block structure without discarding the source Markdown.

Fields:

- `id`
- `note_id`
- `vault_file_id`
- `parent_block_id`
- `position`
- `stable_source_id`
- `block_kind`
- `markdown`
- `plain_text`
- `properties`
- `task_state`
- `heading_path`
- `source_start`
- `source_end`

Stable source IDs use explicit Obsidian block IDs or Logseq block UUIDs when
present. Otherwise they are deterministic parser IDs and may change when nearby
content is structurally rewritten.

### `note_link`

Represents links without overloading existing notebook `artifact` relations.

Fields:

- `id`
- `source_note_id`
- `source_block_id`
- `target_note_id`
- `target_block_id`
- `target_text`
- `target_heading`
- `link_kind`
- `resolved`
- `source_span`

Unresolved links are preserved and can appear as unlinked or missing targets.

### `knowledge_task`

Projects task semantics from Markdown without owning the canonical text.

Fields:

- `id`
- `note_id`
- `block_id`
- `status`
- `scheduled`
- `due`
- `completed`
- `priority`
- `recurrence`
- `tags`

### `vault_revision`

Stores local recovery metadata and small-file snapshots.

Fields:

- `id`
- `vault_file_id`
- `operation_id`
- `content_hash`
- `previous_hash`
- `snapshot_path`
- `size_bytes`
- `created`
- `retention_class`

Large binaries use filesystem backups and hash references rather than database
blobs.

### `vault_sync_receipt`

Append-only operational evidence.

Fields:

- `id`
- `operation_id`
- `vault_id`
- `vault_file_id`
- `operation`
- `source`
- `before_hash`
- `after_hash`
- `observed_modified_ns`
- `parser_version`
- `policy_decision`
- `status`
- `error_code`
- `rollback_path`
- `started_at`
- `completed_at`

Receipts never contain file content, secrets, or full user-home paths in
exported telemetry.

### Advanced feature records

Later phases add:

- `knowledge_base_view`
- `knowledge_base_formula`
- `knowledge_canvas`
- `knowledge_canvas_node`
- `knowledge_canvas_edge`
- `knowledge_bookmark`
- `knowledge_workspace`
- `knowledge_template`
- `audio_capture`

These records reference notes and vault files; they do not duplicate note
content.

## Parser Contracts

### Obsidian

The parser preserves:

- YAML frontmatter and property value types.
- Wikilinks and aliases.
- Heading links.
- Block links and block IDs.
- Embeds and transclusion.
- Markdown links.
- Tags.
- Tasks.
- Callouts.
- Footnotes.
- Attachments.
- Canvas and Base file references.

### Logseq

The parser preserves:

- Bullet indentation and ordered block hierarchy.
- Page properties using `key:: value`.
- Block properties.
- Page references.
- Block references and block UUIDs.
- Journals.
- Task markers and scheduling properties.
- Embeds.
- Namespaces.

### Round-trip rule

A parse followed by a no-op serialization must return byte-identical content.

When a structured edit is made:

- Untouched ranges remain byte-identical.
- Newline style is preserved.
- Encoding is preserved when supported.
- Unknown syntax is retained.
- The serializer produces the smallest practical diff.

If safe round-trip serialization is impossible, the file remains read-only and
the UI explains why.

## Workspace Design

### Navigation

The existing Deeper Notebook sidebar gains a **Knowledge** group:

- Vaults
- Files
- Daily
- Tasks
- Graph
- Bases
- Canvas
- Bookmarks

Existing Collect, Process, Create, and Manage groups remain.

### Primary workspace

The knowledge workspace supports:

- File explorer.
- Multiple tabs.
- Split panes.
- Source, live-preview, and reading modes.
- Outline and footnotes.
- Properties and tags.
- Backlinks, outgoing links, and unlinked mentions.
- Page preview.
- Word count.
- Command palette and slash commands.

### Search and quick switching

Search combines:

- Path and filename search.
- Exact text search.
- Property and tag filters.
- Task filters.
- Link/backlink filters.
- Existing semantic search.

Every result identifies its vault, path, page/block context, and provenance.

### Graph

The existing React Flow map evolves into:

- Global vault graph.
- Local page graph.
- Filters by vault, folder, tag, property, task state, and link kind.
- Unresolved-link visibility.
- Stable layout persistence.
- Direct navigation to page, heading, or block.

### Bases

Deeper Notebook Bases use local file properties as the underlying data.

Supported first-party views:

- Table
- List
- Cards

Supported operations:

- Filter
- Sort
- Group
- Property editing
- Formula evaluation

Base definitions are stored as portable `.base` files or Deeper Notebook
records with an explicit export command. Mounted Obsidian `.base` files remain
canonical when present.

### Canvas

Canvas provides an infinite spatial workspace with:

- Note cards.
- Text cards.
- Asset cards.
- Web cards.
- Groups.
- Directed and undirected connections.
- Deep links to headings and blocks.

Obsidian `.canvas` JSON is imported and exported without erasing unknown keys.

### Daily notes and tasks

- Vault-specific daily-note format and location.
- Template application.
- Journal navigation.
- Task aggregation without moving task text out of its source file.
- Status, due, scheduled, priority, and tag filters.
- Direct navigation from a task to its source block.

### File recovery

Local file recovery uses:

- Pre-write backups.
- Revision metadata.
- Configurable retention.
- Preview before restore.
- Restore as another receipted write.

No background pruning runs without a documented retention policy.

## Deeper Notebook AI Integration

Mounted pages and blocks participate in:

- Grounded chat.
- Ask and research synthesis.
- Semantic search.
- Evidence views.
- Notebook and source collections.
- Study tools.
- Memory, subject to existing privacy rules.

AI output never becomes canonical vault content automatically.

Write-capable AI actions:

- Produce a proposed diff.
- Identify affected files and blocks.
- Show source evidence.
- Require approval under the vault write policy.
- Emit receipts.

The existing `brain-engine` can continue operating independently. Deeper
Notebook does not invoke its write-capable Ralph loop during read-only phases.

## Integrating the Actual `2nd Brains` Folder

### Registration

Register the inspected root as a mixed parent workspace with two child mounts:

- `Obsidian Brain` as `obsidian`.
- `Logseq Brain` as `logseq`.

`brain-engine` is registered as connector metadata, not as a writable vault.

### Initial trust import

The existing 21-document manifest is used to seed approval and provenance
metadata:

- `status = approved`
- reviewer and reviewed timestamp
- source type
- evidence class
- content hash
- `derivedFrom`

The generated copies are not imported as duplicate notes when the canonical
source file is available.

### Cross-vault identity

Pages with matching normalized titles are not merged automatically.

The index creates an alias candidate containing:

- Obsidian source.
- Logseq source.
- Content hashes.
- Link neighborhoods.
- Evidence/provenance class.

The user may confirm a shared concept identity. Both source paths remain
addressable.

### Protected areas

The default policy marks these read-only:

- `Obsidian Brain/sources/**`
- `Obsidian Brain/inbox/raw/**`
- `Logseq Brain/journals/**` for rewrite operations
- `brain-engine/**` except explicit connector maintenance
- Generated connector output
- Control files and task queues during initial phases

Append-only journal linking can be designed separately from rewrite permission.

### Stale path handling

The app reports the former root in `brain-engine/config.json` and the existing
manifest. It offers a previewable maintenance action only after write-back is
enabled. The first read-only integration uses the path selected in Deeper
Notebook and does not depend on the stale engine path.

## Feature Delivery

### Phase 0: Identity and safety baseline

- Complete the Deeper Notebook rebrand.
- Add centralized identity constants and legacy aliases.
- Define approved-root, immutable-area, and receipt contracts.
- Register the actual second-brain root without modifying it.

### Phase 1: Read-only vault foundation

- Add vault, file, note metadata, block, link, and receipt migrations.
- Implement Obsidian and Logseq parsers.
- Adapt Capture Inbox watcher stability and fingerprint behavior.
- Add scan, status, and read-only APIs.
- Index the actual second-brain workspace.
- Expose explorer, backlinks, and local graph.

### Phase 2: Core workspace parity

- Tabs and panes.
- Source/live-preview/reading editor.
- Quick switcher.
- Command palette and slash commands.
- Search, graph, backlinks, outgoing links, and outline.
- Properties, tags, page preview, and footnotes.
- Daily notes, unique notes, templates, and random note.
- Bookmarks, composer, and word count.

### Phase 3: Advanced first-party features

- Bases.
- Canvas.
- Tasks and journal dashboards.
- Audio recorder and attachment workflows.
- Slides.
- Web viewer.
- Format converter.
- Workspaces and themes.
- File recovery.

### Phase 4: Guarded write-back and release

- Round-trip serializers.
- Diff preview.
- Conflict resolution.
- Atomic write and backup.
- Rollback and recovery.
- Per-vault permissions.
- Optional Git checkpoints.
- Native macOS and Windows package proof.

## State and Error Model

Vault state is one of:

- `disconnected`
- `scanning`
- `ready-read-only`
- `ready-write-enabled`
- `stale`
- `conflict`
- `degraded`
- `unavailable`

File parse state is one of:

- `pending`
- `parsed`
- `unsupported`
- `invalid`
- `conflict`
- `missing`

Failures behave as follows:

- Path escape or unsafe symlink: reject and receipt.
- Unsupported encoding: retain file listing, skip content indexing, show reason.
- Parse failure: preserve previous valid projection and mark it stale.
- Watcher event storm: debounce and deduplicate by path and hash.
- Database outage: do not write external files.
- Embedding failure: keep durable parsed content and retry embedding separately.
- External modification before save: block write and open conflict UI.
- Backup failure: block write.
- Atomic replacement failure: preserve original and temporary recovery file.
- Receipt failure: block write or roll back before reporting success.

## Security and Privacy

- Vault roots are local and explicitly selected.
- No cloud upload occurs as part of mounting, parsing, indexing, or search.
- Existing privacy routing governs any later LLM request.
- Raw files, secrets, credentials, and immutable source areas are excluded from
  automatic write-back.
- File content is never placed in logs.
- Receipts use relative paths internally and redact user-home prefixes in
  exported diagnostics.
- Symlink traversal and time-of-check/time-of-use races are tested.
- Write permissions are per vault and per area, not global.
- AI write proposals are untrusted until validated and approved.

## Verification

### Parser tests

Golden fixtures cover:

- Frontmatter types.
- Wikilinks, aliases, headings, and blocks.
- Embeds and attachments.
- Callouts and footnotes.
- Logseq block hierarchy and properties.
- Journals and tasks.
- Unknown syntax.
- Mixed newline styles.
- Malformed input.

### Round-trip tests

- No-op parse/serialize is byte-identical.
- Structured edits create minimal expected diffs.
- Unknown syntax survives.
- External hash changes block writes.
- Backups restore exact original bytes.

### Security tests

- Path traversal.
- Unsafe symlinks.
- Protected-area writes.
- Stale file descriptors.
- Concurrent changes.
- Oversized files.
- Non-UTF-8 files.
- Receipt and backup failure.
- Database failure before write.

### Real-workspace read-only proof

Before and after the initial scan:

- Hash all source files.
- Record Git status without staging or committing.
- Verify zero source hashes changed.
- Reconcile file, link, property, and task counts.
- Import all 21 approved manifest records as trust metadata.
- Verify all 9 synthesis records retain `derivedFrom`.
- Re-run the scan and prove idempotency.

### Application tests

- Focused backend domain and API tests.
- Frontend Vitest coverage for explorer, editor modes, backlinks, graph,
  properties, tasks, Bases, and Canvas.
- Playwright browser flows.
- Native runtime smoke.
- Desktop launcher and bridge tests.
- Production frontend build.
- macOS app and DMG build.
- Windows installer build on Windows.
- Packaged launch and vault-mount smoke on both platforms.

## Acceptance Criteria

- The actual `2nd Brains` folder mounts without source modification.
- Obsidian and Logseq files remain portable and parse with provenance.
- Backlinks, graph, properties, tags, tasks, daily notes, and search work across
  both formats.
- First-party Obsidian desktop features in scope have native Deeper Notebook
  equivalents.
- Existing Deeper Notebook research and AI features remain operational.
- Grounded AI can cite mounted pages and blocks.
- No-op saves are byte-identical.
- Conflicts never overwrite external changes.
- Protected areas remain immutable by default.
- Every write is backed up, atomic, validated, and receipted.
- Write-back remains disabled until read-only and rollback gates pass.
- Native macOS and Windows package checks pass before release.

## References

- Obsidian core plugins: https://obsidian.md/help/plugins
- Obsidian Bases: https://obsidian.md/help/bases
- Obsidian URI and block/heading navigation:
  https://help.obsidian.md/Extending%2BObsidian/Obsidian%2BURI
- Reference workspace:
  `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains`
