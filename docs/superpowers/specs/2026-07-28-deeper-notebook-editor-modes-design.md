# Deeper Notebook Read-Only Editor Modes Design

**Status:** Design adopted for the next Obsidian/Logseq parity slice under the
active Deeper Notebook goal.

**Product identity:** Deeper Notebook, expressed through the Notebook Spark
personality and Research Core teal/cyan colorway.

## Outcome

Deeper Notebook will provide four independently persisted views for every
mounted knowledge page:

1. Reading
2. Source
3. Live Preview
4. Local Graph

Reading, Source, and Live Preview will expose the same canonical projected
Markdown. Source and Live Preview will use a shared CodeMirror 6 foundation.
All three document views remain strictly read-only until guarded external-vault
write-back is separately designed, implemented, and approved.

This slice also completes the existing outline, footnote, property, tag, and
page-preview experience. It removes synthetic path identities so every open tab
is tied to the canonical relative path and content fingerprint recorded by the
vault projection.

## Scope

### Included

- Canonical file metadata on page responses.
- Canonical target path and title metadata on resolved links.
- Exact decoded source Markdown in Source mode.
- Obsidian-style inline Markdown treatment in Live Preview mode.
- Reading mode with GFM, footnotes, math, safe internal links, deterministic
  heading anchors, and visible task state.
- Navigable outline for headings at all six levels.
- Properties and tags with compact, accessible presentation.
- Hover/focus page previews for resolved internal links.
- Per-tab persistence of Reading, Source, Live Preview, and Graph modes.
- Keyboard-accessible mode switching.
- Research Core editor styling in light and dark themes.
- Unit, integration, API-contract, accessibility, and production-build proof.

### Excluded

- Any vault `POST`, `PUT`, `PATCH`, or `DELETE` mutation route.
- Local draft persistence or an editable internal copy.
- Checkbox mutation.
- Rename, move, delete, serializer, diff, backup, conflict resolution,
  rollback, or Git checkpoint behavior.
- Attachment upload or external-file access beyond existing safe projected
  metadata.
- Obsidian third-party plugin compatibility.

## Safety Invariants

1. Mounted Markdown and asset files remain canonical and read-only.
2. The frontend never receives an absolute vault root.
3. A page can open only when its canonical vault-relative path is known.
4. Source and Live Preview configure both `EditorState.readOnly.of(true)` and
   `EditorView.editable.of(false)`.
5. No command, keymap, toolbar, extension, or programmatic callback may dispatch
   a document-changing transaction.
6. Content is rendered from the projection returned by the page API, never by
   rereading the external path from the frontend.
7. Link previews use bounded projected page data and never fetch an arbitrary
   filesystem path or remote URL.
8. HTML embedded in Markdown is not executed.
9. External links are inert in this slice; only resolved vault links navigate.
10. A missing or inconsistent canonical path fails closed without manufacturing
    a filename.

## Architecture Decision

### Selected: CodeMirror 6

CodeMirror 6 provides a durable editor substrate for both read-only parity now
and guarded editing later. Its official facets separately disable direct DOM
editing and state mutation. Its Markdown language package provides syntax trees,
and its decoration/view-plugin APIs can render inline Markdown affordances only
for visible ranges.

The frontend will add the modular CodeMirror packages used directly by the
implementation:

- `@codemirror/commands`
- `@codemirror/lang-markdown`
- `@codemirror/language`
- `@codemirror/search`
- `@codemirror/state`
- `@codemirror/view`

The editor wrapper will not include an editable `basicSetup` bundle. It will
compose only the read-only capabilities that are explicitly required: line
numbers, selection, search, folding, syntax highlighting, draw-selection,
highlight-active-line, and safe non-mutating keymaps.

### Rejected: reuse `@uiw/react-md-editor`

The existing wrapper is appropriate for internal note forms, but its live mode
is a two-column editor/preview. It does not provide Obsidian-style inline live
preview, canonical-path integration, or a clean route to syntax-tree-driven
decorations.

### Rejected: custom `contenteditable`

A custom contenteditable Markdown surface would require Deeper Notebook to own
cursor mapping, composition/IME behavior, selection restoration, undo, screen
reader semantics, and virtualization. That risk is not justified when
CodeMirror already owns those contracts.

## Backend Contracts

### Canonical page file

`VaultPage` gains a required `file: VaultFile`. `VaultRepository.get_page()`
will resolve the page's `vault_file_id`, query that exact record within the
requested vault, and return it with the note, blocks, tasks, outgoing links, and
backlinks.

`VaultPageResponse` exposes the file through the existing
`VaultFileResponse` schema. This supplies:

- `relative_path`
- `content_hash`
- `encoding`
- `newline`
- `modified_ns`
- `size_bytes`
- `format`
- `parse_status`
- `deleted_state`

Migration `35.surrealql` adds optional `vault_file.newline` metadata for
existing installations, and `35_down.surrealql` removes only that field. New
projections persist `ParsedDocument.newline` as one of `lf`, `crlf`, `mixed`,
or `none`; older records may return `None` until they are rescanned.

The repository raises `vault_note_file_not_found` if a note exists without its
canonical file record. The API maps this to the path-free
`409 vault_canonical_file_unavailable` code before its generic lookup-error
mapping. A page whose canonical file lacks a complete 64-character hexadecimal
content hash maps to `409 vault_page_invalid`. It does not return a partial
page or expose a filesystem path in either error.

### Canonical resolved-link target

`VaultLink` and `VaultLinkResponse` gain:

- `target_note_title: str | None`
- `target_relative_path: str | None`
- `source_start: int`
- `source_end: int`

The link query projects those values through the resolved target note and its
vault file. Both values remain `None` for unresolved links. A link marked
`resolved=True` without a target note ID, present target title, or canonical
relative path is rejected as inconsistent projection data. An empty canonical
title remains present and valid; display code may fall back to `target_text`.
The source span remains the parser's zero-based UTF-8 byte range and is
converted to a JavaScript string range before matching rendered Markdown links.

### Content identity

The note's `content` remains the exact UTF-8-decoded Markdown captured by the
parser, preserving original line endings. The page file's `content_hash`
identifies the original bytes, including BOM when present. The UI displays the
hash in abbreviated form but preserves and passes the full value internally.
File-list compatibility may retain nullable hashes for old unscanned rows, but
an opened page is accepted only with the complete hash.

## Frontend Contracts

`vaultPageSchema` gains a required `file: vaultFileSchema`.
`vaultLinkSchema` gains the optional target title, target relative path, and
required source-span fields. One shared canonical-relative-path schema rejects
empty paths, leading or trailing whitespace, absolute paths, backslashes, NULs,
repeated separators, and `.` or `..` segments for both the page file and
resolved targets.

The API layer performs two consistency checks:

1. `page.file.note_id === page.note.id`
2. `page.file.vault_id` matches the requested vault ID

The caller receives a stable `VaultPage` only after those checks pass. Document
Markdown is selected exactly as `page.note.content ?? page.note.markdown ?? ''`;
blocks never reconstruct or replace the canonical projected source.

The frontend translates only the two stable page HTTP error codes into
`VaultPageContractError`: `vault_canonical_file_unavailable` becomes
`canonical-path-unavailable`, and `vault_page_invalid` becomes `page-invalid`.
Other HTTP failures remain generic load failures.

`KnowledgeTab.relativePath` always comes from `VaultFile.relative_path`.
`KnowledgeExplorer.fallbackRelativePath()` is removed. Resolved link navigation
uses `target_relative_path` and `target_note_title`. If an existing hydrated tab
contains older synthetic metadata, the first successful page response replaces
its title and relative path with canonical values through an idempotent
`reconcileTabReference()` store action.

## Component Boundaries

### `KnowledgePaneContent`

Owns page loading, active mode selection, graph loading, and canonical tab
reconciliation. It does not render mode-specific Markdown.

### `VaultDocumentView`

Receives one validated `VaultPage`, the owning pane/tab `viewId`, plus
navigation callbacks. It selects:

- `VaultReadingView`
- `VaultSourceView`
- `VaultLivePreview`

The component has no mutation callback.

### `VaultReadingView`

Uses `react-markdown` with:

- `remark-gfm`
- `remark-math`
- `rehype-katex`

GFM covers footnote references/definitions, tables, strikethrough, autolinks,
and task-list syntax. KaTeX renders math without enabling raw HTML.

Custom renderers:

- assign deterministic IDs to headings prefixed by the pane/tab `viewId`, so
  two split panes showing the same note never share a heading ID;
- turn resolved vault links into keyboard-accessible buttons;
- make task checkboxes disabled and explicitly read-only;
- render attachments as projected metadata placeholders;
- leave external links inert;
- style footnote backlinks and the notes section.

A local `remarkVaultLinks` transformer recognizes wiki links without rewriting
the Markdown input. It retains the original MDAST positions and stores exact
UTF-8 source-byte spans on generated link nodes. Both wiki and ordinary
Markdown links resolve only by those spans, so duplicate labels and Unicode
prefixes cannot cross-wire targets. The localized `knowledge.footnotes` value
is passed to React Markdown rather than hard-coding an English label.

### `VaultSourceView`

Hosts `VaultCodeMirror` with source extensions:

- Markdown syntax highlighting
- line numbers
- code folding
- local search
- selection and copy
- active-line highlight
- read-only facets

It displays exact projected Markdown without normalization. A compact status
bar shows relative path, source format, line ending, encoding, byte size, and
abbreviated source hash.

### `VaultLivePreview`

Hosts the same `VaultCodeMirror` with a live-preview extension. A pure
`buildLivePreviewDecorations(state, visibleRanges)` function walks the Markdown
syntax tree and creates only visible-range decorations.

The initial supported constructs are:

- ATX headings
- emphasis, strong, and strikethrough
- inline code and fenced code blocks
- Markdown links and resolved wiki links
- task list markers
- block quotes
- horizontal rules
- ordered and unordered list markers
- tags
- footnote references
- math delimiters

Source punctuation is visually collapsed outside the current selection.
Selecting a construct reveals its exact Markdown tokens. Since the editor is
read-only, selection is the inspection boundary rather than an editing cursor.
Unsupported constructs remain visible as source text instead of disappearing.

Decorations never replace ranges spanning line breaks when supplied through a
view plugin. Block widgets are provided directly where vertical layout changes
are required.

### `VaultNoteSidebar`

Owns outline, properties, tags, and source provenance. It is shared by Reading,
Source, and Live Preview so mode switches do not move the user's context.

The outline parser consumes the Markdown syntax tree rather than a regular
expression. It supports heading levels one through six, duplicate headings, and
stable slugs. Clicking an item scrolls the active view to the corresponding
source offset or reading-mode anchor. Reading-mode lookup is scoped to the
owning `VaultDocumentView` container and its pane/tab-prefixed heading IDs;
global DOM ID lookup is forbidden.

### `VaultPagePreview`

Resolved wiki/Markdown links show a bounded preview on hover and keyboard focus.
The preview query is enabled only after a short intent delay and reuses the
validated page API/cache. It shows title, relative path, source format, up to
three non-empty projected text blocks, and outgoing/backlink counts. It never
renders arbitrary HTML or initiates navigation until activated.

## Data Flow

1. The active tab supplies `vaultId` and `noteId`.
2. `useVaultPage()` fetches and validates page, file, block, link, and task data.
3. `KnowledgePaneContent` reconciles the active tab with canonical file
   metadata.
4. The active persisted `viewMode` selects Reading, Source, Live Preview, or
   Graph.
5. Reading and Live Preview resolve internal links only against validated
   outgoing-link records.
6. Outline selection maps one heading descriptor to either a rendered anchor
   or source byte/character offset.
7. Page preview uses the target note ID from a resolved link and the same
   validated query cache.
8. A mode change updates workspace state and enters the existing globally
   coordinated durable-save path.

## Mode Switching

The tab mode control contains four labelled buttons and exposes a roving
keyboard model:

- `Control+1`: Reading
- `Control+2`: Source
- `Control+3`: Live Preview
- `Control+4`: Graph

The shortcuts operate only when the knowledge workspace owns focus and do not
override browser/system shortcuts involving Command or Alt.

Mode state remains per tab, not per pane or globally. Switching tabs restores
that tab's last mode. Splitting a pane preserves each tab's mode through the
existing workspace serialization contract.

## Loading And Failure Behavior

- Page loading shows the existing non-destructive loading state.
- Page validation failure shows a stable `knowledge.pageInvalid` error without
  opening an editor.
- Missing canonical file metadata shows `knowledge.canonicalPathUnavailable`.
- Editor initialization failure falls back to Reading mode for display only and
  does not rewrite the persisted selected mode. The boundary resets when note
  ID, selected editor mode, or canonical content hash changes.
- A live-preview decoration failure falls back to visible source syntax for the
  affected construct.
- Page-preview failure suppresses the preview body and leaves its trigger and
  link navigation available.
- Graph failures remain isolated to Graph mode.
- Empty Markdown renders an explicit empty-note state in all document modes.

## Accessibility

- Mode buttons expose `aria-pressed` and descriptive labels.
- Source and Live Preview have an accessible document label containing the note
  title and mode.
- Read-only state is exposed through `aria-readonly`.
- The editor remains keyboard scrollable, searchable, selectable, and copyable.
- Heading outline entries are buttons with their level announced.
- Page previews open on focus as well as hover and close with Escape.
- Link activation remains a real button, not a click handler on plain text.
- Color is never the only indicator of source format, mode, or read-only state.

## Visual Direction

The editor chrome remains quiet and research-oriented:

- Research Core teal marks active mode, resolved internal links, and the current
  outline item.
- Cyan is reserved for hover/focus and live-preview affordances.
- Graph keeps its existing format-based node colors.
- Source text uses the app's mono font and theme tokens.
- No glassmorphism, decorative gradients behind body text, or oversized mode
  controls.
- Read-only status stays visible but compact.

## Verification

### Backend

- Repository tests prove the page and its file belong to the same vault.
- API tests prove canonical relative path, hash, encoding, and newline metadata
  survive the response.
- Link tests prove resolved targets include canonical paths and unresolved
  targets do not fabricate them.
- Failure tests prove orphaned notes and inconsistent resolved links fail
  closed.

### Frontend

- Zod tests reject absolute paths, cross-vault page/file mismatches, malformed
  target paths, and missing canonical file data.
- Store tests prove hydration and canonical reconciliation are idempotent.
- Component tests prove all four persisted modes render and switch.
- Source tests prove content is byte-equivalent after UTF-8 decoding and cannot
  be changed through typing, paste, drop, keymaps, or dispatched user commands.
- Live-preview tests cover every supported construct plus unsupported-source
  fallback.
- Reading tests cover GFM, localized footnotes, math, duplicate pane-scoped
  heading anchors, disabled tasks, source-span-safe wiki/Markdown links,
  properties, tags, Unicode prefixes, and duplicate link labels.
- Preview tests cover hover, focus, delay, cache reuse, failure, Escape, and
  no-absolute-path behavior.
- Accessibility tests cover button names, pressed state, `aria-readonly`,
  keyboard mode switching, focus previews, and split-pane-isolated outline
  navigation.

### Integration and release gates

- Full backend and frontend suites pass.
- ESLint passes.
- TypeScript passes with `npx tsc --noEmit`.
- Next.js production build passes.
- Rebrand audit passes with zero unexpected identities and zero stale entries.
- A native desktop smoke proves mode persistence across app restart without a
  vault mutation.
- A packaged macOS smoke proves Source and Live Preview render after restart.
- Windows packaged proof remains a release gate before calling the complete
  cross-platform phase finished.

## Acceptance Criteria

The slice is complete only when:

1. Every opened tab has a canonical relative path and content hash.
2. Reading, Source, Live Preview, and Graph are available and persisted per tab.
3. Source displays exact projected Markdown and cannot be edited.
4. Live Preview renders the supported syntax inline and cannot be edited.
5. Reading renders GFM, footnotes, math, safe links, properties, tags, and
   disabled tasks.
6. Outline and page previews work with mouse and keyboard.
7. No vault mutation route or external filesystem write exists.
8. Existing notebooks, research, Studio, Capture, podcasts, memory, model, vault,
   workspace, and rebrand tests remain green.
9. Native restart proof shows mode and tab persistence with unchanged source
   fingerprints.
