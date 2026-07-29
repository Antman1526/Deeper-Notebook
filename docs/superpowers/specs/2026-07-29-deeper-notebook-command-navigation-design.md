# Deeper Notebook Command Navigation Design

Date: 2026-07-29
Status: Approved for planning
Scope: Quick switcher, knowledge-aware command palette, safe slash commands,
and combined exact/indexed knowledge search

## Goal

Add Obsidian-style keyboard navigation to Deeper Notebook without weakening the
current external-vault protection boundary.

The feature must let a user:

- open or activate any indexed Obsidian or Logseq note from the keyboard;
- run global and knowledge-workspace commands from one command palette;
- invoke knowledge commands with a slash gesture while the workspace has focus;
- change the active note view and pane layout without reaching for the mouse;
- search exact note metadata immediately and request indexed text or semantic
  results explicitly;
- understand when a command is unavailable and why.

The feature must not write to, rename, move, delete, or toggle anything in an
external vault. Those capabilities remain reserved for the protected write-back
phase.

## Existing Foundation

Deeper Notebook already has the necessary primitives:

- `CommandPalette` provides the dashboard-wide `Cmd/Ctrl+K` surface.
- `cmdk` and the shared command UI components provide filtering, keyboard
  selection, and accessible dialog behavior.
- `KnowledgeExplorer` owns mounted-vault selection and note navigation.
- `useKnowledgeWorkspaceStore` owns focused panes, tabs, split operations, view
  modes, and durable workspace revisions.
- vault APIs expose mounted vaults, indexed file metadata, page projections,
  scan operations, backlinks, and graph data.
- the normal search API supports text and vector searches and returns
  `vault_provenance` for mounted-vault results.

The design extends these primitives. It does not introduce a second command
framework or a second workspace state store.

## Product Decisions

### Keyboard map

- `Cmd/Ctrl+K`: open the existing global command palette.
- `Cmd/Ctrl+O`: open the Knowledge quick switcher when the current route is the
  Knowledge workspace.
- `/`: when the Knowledge workspace itself has focus and the event target is
  not editable, open the existing command palette prefiltered to safe knowledge
  commands.
- `Escape`: close either surface and restore focus to the invoking element when
  it is still mounted.

Existing shortcuts remain intact. Keyboard listeners must ignore:

- `input`, `textarea`, and `select` elements;
- genuinely editable `contenteditable` elements;
- IME composition events;
- repeated keydown events;
- modified slash keystrokes other than the explicitly supported shortcuts.

The read-only CodeMirror surfaces do not count as editable targets, but a slash
gesture is accepted only when focus is inside the Knowledge workspace region.

### Quick switcher

The quick switcher is a note-first surface rather than a general command list.
It displays mounted-vault files ranked by:

1. exact title match;
2. title prefix;
3. title token match;
4. relative-path segment match;
5. vault-name match;
6. stable lexical tie-breakers.

Ranking is deterministic and implemented as a pure function. Diacritic folding
and case folding are applied for matching without changing the displayed title
or path.

Each result shows:

- note title;
- relative path when it disambiguates the title;
- vault name and source format;
- an open-tab indicator when the note is already present in the workspace.

Selecting a result opens or activates it in the focused pane through
`useKnowledgeWorkspaceStore.openTab`. It does not navigate through an
untrusted filesystem path and does not read the source file directly.

### Command palette

The current global palette remains the only command palette. Its current
navigation, notebook, creation, theme, Search, and Ask behavior stays
available.

When the current route is Knowledge, the palette adds:

- switch/open note;
- switch the active tab to Reading, Source, Live Preview, or Graph;
- split the active pane right or down;
- close the active pane when another pane exists;
- close the active tab;
- scan the selected vault;
- open exact indexed results;
- run indexed text search;
- run semantic search explicitly;
- move to the next or previous open tab;
- focus the file tree, active pane, or links inspector.

Commands that require an active tab, multiple panes, a selected vault, or an
available embedding model are disabled or omitted with a stable reason. A
disabled command never partially executes.

### Slash commands

Slash commands are an alternate entry gesture into the same typed command
registry. They are not a separate parser and do not insert Markdown in this
phase.

The slash-prefiltered palette contains only commands whose safety classification
is `read` or `workspace`. Examples include `/open`, `/reading`, `/source`,
`/live-preview`, `/graph`, `/split-right`, `/split-down`, and `/scan`.

External-file mutation commands are not registered in this phase. When
protected write-back is implemented, mutation commands may be added only behind
all of these gates:

- explicit per-vault write permission;
- a current source fingerprint;
- round-trip serialization;
- a user-visible diff;
- conflict detection;
- atomic replacement;
- backup and rollback;
- optional Git checkpoint policy.

## Architecture

### Typed command registry

Extract command metadata and execution from the monolithic
`CommandPalette` component into focused modules.

```ts
type CommandScope = 'global' | 'knowledge'
type CommandSafety = 'read' | 'workspace' | 'external-write'

interface CommandDefinition {
  id: string
  scope: CommandScope
  safety: CommandSafety
  labelKey: string
  aliases: string[]
  keywords: string[]
  shortcut?: string
  isAvailable(context: CommandContext): boolean
  unavailableReason?(context: CommandContext): string | null
  execute(context: CommandContext): void | Promise<void>
}
```

Registry entries are data-oriented and independently testable. React
components render definitions but do not own command business rules.

`external-write` is part of the type now so the future permission boundary is
explicit. The current registry builder rejects that safety class for slash and
Knowledge read-only surfaces.

### Command execution context

The command context is assembled from existing runtime sources:

- Next.js route and router;
- current theme and create-dialog handlers;
- mounted vault queries;
- focused workspace pane and active tab;
- workspace store actions;
- selected vault and scan mutation;
- exact and indexed search state.

The durable workspace document remains the source of truth for tabs and panes.
Ephemeral palette state, query text, invocation source, and focus restoration
are not persisted.

Knowledge-page runtime context is exposed through a dedicated ephemeral Zustand
store named `knowledge-command-context-store`. `KnowledgeExplorer` registers
the selected vault ID, focus targets, and scoped handlers with a monotonically
increasing registration generation. Cleanup clears the context only when its
generation still owns the registration, preventing an old component cleanup
from erasing a newer route instance. The store must not copy the durable
pane/tab document or cache source content. Registration is removed when
`KnowledgeExplorer` unmounts so global commands cannot act on a stale page
instance.

### Indexed file catalog

A focused hook loads file metadata for each ready mounted vault with TanStack
Query. Queries are enabled only while a knowledge command surface needs the
catalog or while the Knowledge page is active.

The hook returns:

- healthy candidates;
- per-vault loading state;
- the number of failed vault catalogs;
- stable retry actions.

One failed mount does not suppress results from healthy mounts. Results retain
`vault_id` and `note_id`; relative paths are display/provenance hints rather
than filesystem authorities.

### Exact and indexed search

The feature uses three deliberately distinct search paths:

1. **Quick switcher exact search** operates locally over indexed file metadata
   and returns immediately.
2. **Indexed text search** calls the existing search API after a short debounce
   and a minimum non-whitespace query length.
3. **Semantic search** runs only when the user selects the semantic-search
   command. It is never triggered on every keystroke.

Search results carrying canonical `vault_provenance` open the projected vault
note in the focused pane. Other notebook/source results continue through the
existing Search page. A result without sufficient provenance is never guessed
into a vault path.

If no embedding model is configured, semantic search presents the existing
model-configuration route rather than silently falling back and claiming a
semantic result.

## Components

### `KnowledgeQuickSwitcher`

Responsibilities:

- own open/query/selection UI state;
- render ranked file candidates;
- show loading, partial-failure, and empty states;
- open the chosen projected note through the workspace store;
- restore focus after close.

It does not own vault fetching, workspace persistence, or filesystem access.

### `CommandPalette`

Responsibilities after refactoring:

- own the global dialog lifecycle and query;
- combine registry groups with notebook and search result groups;
- preserve existing global behaviors;
- render availability and shortcut hints;
- prefilter by invocation mode (`global` or `slash`);
- dispatch through the command executor.

It does not contain pane mutation algorithms or duplicate vault ranking logic.

### Knowledge command bridge

Responsibilities:

- register the current Knowledge route context;
- expose selected-vault scan and focus targets;
- handle scoped slash and quick-switcher listeners;
- unregister atomically on route exit.

The bridge does not persist source content, permission state, or callbacks
across app restarts.

## Failure Handling

- A failed file-catalog request is isolated to its vault and can be retried.
- A failed indexed search leaves exact quick-switcher results usable.
- A failed scan reports through the existing mutation error state.
- A command execution rejection keeps the palette open and announces the
  reason.
- Stale context registration is treated as unavailable; no command executes.
- Invalid or missing `vault_provenance` cannot open a projected note.
- Search cancellation and query changes discard stale responses.
- All failures preserve the current pane/tab document and external source
  files.

## Accessibility and Localization

- Dialog titles, descriptions, group labels, empty states, disabled reasons,
  and shortcuts are announced through accessible text.
- Results use a single predictable listbox/command-item order.
- Mount format is supplementary text, not the only distinguishing signal.
- All user-facing strings are added to the existing locale contract.
- Non-English locale files receive complete keys, following the project
  locale-consistency test.
- Keyboard-only operation covers opening, filtering, selecting, closing, and
  focus restoration.

## Security and Data-Safety Invariants

The implementation must prove:

- no vault write, rename, move, delete, task-toggle, or raw-file endpoint is
  introduced or called;
- commands open projected records by stable IDs, not arbitrary user-supplied
  paths;
- command labels and result metadata are rendered as text;
- stale async results cannot act after a palette closes or context changes;
- read-only editor contracts remain `aria-readonly=true` and
  `contenteditable=false`;
- scan remains the only command that changes the local index, and it does not
  modify canonical source files;
- the real Second Brain is not used during automated tests.

## Verification Strategy

### Unit tests

- deterministic ranking, normalization, tie-breaking, and result caps;
- command scope, aliases, availability, disabled reasons, and safety filtering;
- provenance-to-tab mapping;
- stale search-response suppression;
- no `external-write` command in slash or read-only registries.

### Component tests

- `Cmd/Ctrl+O` opens only on the Knowledge route;
- slash opens only from the focused, non-editable Knowledge workspace;
- `Cmd/Ctrl+K` preserves existing global commands;
- exact note selection opens the focused pane;
- view and split commands update the workspace store;
- partial mount failures preserve healthy results;
- semantic-search unavailability is explicit;
- focus is restored after close;
- no vault mutation client method is called.

### Browser tests

Use synthetic mounted-vault fixtures to prove:

- quick switching between notes;
- activating an already-open tab;
- slash invocation and safe command filtering;
- changing view modes and splitting panes;
- exact and indexed search result routing;
- keyboard guards inside inputs;
- zero external write requests.

### Regression gates

- focused frontend Vitest suites;
- full frontend test suite;
- frontend lint;
- frontend production build;
- mocked browser suite;
- rebrand audit;
- production dependency audit.

Backend tests are required only if the implementation changes a backend search
contract. Reusing the existing contract requires focused API contract tests in
the frontend and the normal full backend regression gate before integration.

## Acceptance Criteria

1. The global palette retains all existing commands and opens with
   `Cmd/Ctrl+K`.
2. `Cmd/Ctrl+O` opens a deterministic cross-vault note switcher on Knowledge.
3. Selecting a result opens or activates the note in the focused pane.
4. `/` from the focused Knowledge workspace exposes only safe knowledge
   commands.
5. View, split, close, scan, and focus commands honor their availability rules.
6. Exact metadata results remain available when indexed or semantic search is
   unavailable.
7. Semantic search is explicit and accurately reports missing model support.
8. Search results open vault notes only when canonical provenance is present.
9. Keyboard listeners do not hijack editable controls or IME input.
10. All user-visible strings satisfy the locale contract.
11. Automated and browser tests observe no external-vault write request.
12. Full frontend regression, lint, build, browser, rebrand, and production
    audit gates pass before integration.

## Follow-On Boundary

This phase deliberately does not implement Markdown insertion slash commands,
daily-note creation, templates, bookmarks, or external-vault editing. The typed
registry and safety classification are extension points for those later
approved phases; they are not permission to bypass their separate data,
serialization, diff, conflict, and recovery designs.
