# Read-only external Canvas viewer design

## Status

Approved architecture (2026-07-31). This document specifies the first Canvas
increment only: viewing trusted, externally owned Obsidian `.canvas` files
inside Deeper Notebook. It deliberately does not add Canvas editing or any
external-vault write capability.

## Goals

- Display a selected mounted `.canvas` file in a dedicated Deeper Notebook
  knowledge tab, including within the existing split-pane workspace.
- Render supported Canvas nodes and edges with pan and zoom controls.
- Navigate a Canvas file-link node only to an existing note in the same mounted
  vault, using the existing knowledge navigation path.
- Preserve the vault boundary: no direct browser filesystem access, no mutation
  of an external Canvas file, and no implicit access outside the selected vault.
- Make source freshness explicit by associating a displayed Canvas document with
  its trusted vault-file record and source hash.

## Non-goals

- Creating, editing, moving, renaming, deleting, or saving `.canvas` files.
- Opening arbitrary local paths, executing embedded commands, or treating URLs
  as trusted navigation targets.
- Implementing Obsidian plugins, arbitrary Canvas node types, collaborative
  editing, or write-back to a mounted vault.
- Changing the existing Markdown editor, its write-back policy, or the protected
  vault-editing roadmap.

## Architecture

### Backend boundary

A new read-only Canvas document endpoint will accept a vault identity and a
canonical relative `.canvas` path. It will use the existing trusted vault
repository and secure path classification rather than a client-supplied absolute
path. The endpoint will:

1. require an approved mounted vault;
2. require an indexable `.canvas` path that belongs to that vault;
3. obtain the current content through the existing bounded, race-safe vault read
   path and its durable vault-file record;
4. return an immutable response containing the vault ID, relative path, content
   hash, and parsed Canvas payload; and
5. reject malformed, oversized, missing, untrusted, or changed content with a
   typed error response.

The server remains the sole filesystem boundary. The browser never receives a
host path and never reads a Canvas file directly.

### Canvas parsing contract

The parser will support the stable subset needed for an initial Obsidian Canvas
viewer:

- text nodes;
- file nodes whose target is a canonical same-vault Markdown path;
- group nodes as non-navigable visual containers; and
- directed edges with optional labels.

Node IDs, coordinates, dimensions, and edge endpoints are validated before they
reach the UI. Unknown node properties are ignored; unknown node types are
represented as a non-interactive unsupported node rather than interpreted as
HTML, code, a URL, or an external file reference. Duplicate IDs, invalid numeric
geometry, dangling edges, invalid paths, and invalid JSON make the document
unrenderable and return a safe error state.

### Frontend workspace integration

Canvas becomes a first-class content kind in the existing knowledge workspace,
not a replacement for Markdown preview. Selecting a Canvas creates or activates
a dedicated Canvas tab using the existing tab identity and split-pane model.

`KnowledgePaneContent` selects a `CanvasViewer` for this tab kind. The viewer
loads the document using the read-only endpoint and renders a keyboard-accessible
SVG/HTML scene with:

- pan and zoom controls;
- visible Canvas node and edge labels;
- a focusable node list for keyboard discovery; and
- link-node activation that delegates only to the existing internal note
  navigation callback.

No tab action offers Save, Edit, Delete, Open in Finder, or external-URL launch.
The original Canvas file stays externally owned and unchanged.

## Data flow

1. The user selects an indexed `.canvas` item from an approved vault.
2. The knowledge workspace opens or focuses its Canvas tab.
3. The viewer requests the vault-scoped Canvas document.
4. The API validates the mount, relative path, classification, trust, bounded
   read, and source hash; it parses the document into a safe view model.
5. The viewer displays that view model. A same-vault Markdown link calls the
   existing note-navigation callback. Every other action stays non-mutating.
6. A refresh gets a new payload and hash; an unavailable or changed source
   produces a clear stale/unavailable state rather than editing cached content.

## Error handling and accessibility

- Invalid or unsupported Canvas documents show a readable error card with the
  relative path and no raw exception details.
- A missing or changed source shows a refresh option; it does not retain a
  silently stale interactive document.
- Backend authorization, traversal, and trust failures return no filesystem
  path information.
- Nodes have accessible names and roles; pan/zoom controls are keyboard
  reachable; the visible node list supplies a non-pointer navigation path.
- The viewer uses no `dangerouslySetInnerHTML` and does not interpret Canvas
  strings as markup.

## Test strategy

Backend tests will prove that the endpoint:

- permits only trusted mounted `.canvas` paths;
- rejects traversal, non-Canvas, unmounted, missing, malformed, and oversized
  inputs;
- returns the current recorded content hash and a validated view model; and
- refuses unsafe file-node targets and dangling/invalid edge data.

Frontend tests will prove that the workspace:

- opens a Canvas in a dedicated reusable tab and preserves Markdown preview;
- renders text, file, group, and edge data safely;
- navigates a valid same-vault note link through the existing callback;
- does not provide write or external-launch controls; and
- presents useful loading, invalid, stale, and unavailable states.

The existing backend suite, relevant frontend component tests, frontend type
check, and production build will be run before this increment is claimed ready.

## Acceptance criteria

- A trusted external `.canvas` opens in a dedicated knowledge tab and works in a
  split pane.
- Its source hash is returned by the read-only API and a changed/missing source
  is not silently used as current.
- Valid same-vault Markdown file nodes navigate internally.
- Invalid content and unsafe links fail closed.
- The viewer performs no external-vault write and exposes no write controls.
- Existing Markdown tabs and preview behavior remain unchanged.
