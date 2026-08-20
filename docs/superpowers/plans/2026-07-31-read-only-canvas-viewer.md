# Read-only Canvas Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open a trusted external Obsidian `.canvas` file as a dedicated, read-only tab in the Deeper Notebook knowledge workspace.

**Architecture:** The backend validates a bounded secure read of one mounted Canvas into a strict view model bound to its durable vault-file identity and SHA-256 hash. The frontend fetches that contract through the vault client, persists a `canvas` view mode, and renders safe text/file/group nodes and edges without an external write path.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, vault security/repository layer, Next.js, React, TypeScript, Zod, TanStack Query, Vitest, pytest.

## Global Constraints

- External vaults remain read-only: no Canvas save, edit, rename, move, delete, Finder reveal, task toggle, or external URL launch.
- The backend is the only filesystem boundary. The browser receives no host path and performs no local file read.
- Only a trusted mounted `.canvas` path may be read through `secure_read`; traversal, links, oversized files, and mid-read changes fail closed.
- Only canonical same-vault Markdown file-node targets are navigable. URLs and arbitrary local paths are non-interactive.
- Every response includes the current SHA-256 source hash and rejects a durable record whose hash differs from the secure read.
- Existing Markdown tabs, view modes, and write protections remain unchanged.

---

## File Structure

- Create `deeper_notebook/vault/canvas.py`: strict Canvas parser and typed view model.
- Create `tests/test_vault_canvas.py`: parser validation and safe-link tests.
- Modify `deeper_notebook/vault/repository.py`: exact durable file lookup by vault ID and canonical relative path.
- Modify `deeper_notebook/vault/service.py`: mounted-root secure read plus durable hash comparison.
- Modify `api/schemas/vault.py` and `api/routers/vault.py`: strict Canvas wire contract and read-only route.
- Modify `tests/test_vault_api.py` and `tests/test_vault_service.py`: route and secure-read lifecycle coverage.
- Modify `frontend/src/lib/api/knowledge-workspace.ts`, `frontend/src/lib/api/vault.ts`, and `frontend/src/lib/hooks/use-vault.ts`: persisted mode, contract, and query hook.
- Create `frontend/src/components/vault/CanvasViewer.tsx` and `CanvasViewer.test.tsx`: accessible viewer.
- Modify `frontend/src/components/vault/KnowledgeExplorer.tsx` and `KnowledgePaneContent.tsx`: open and render dedicated Canvas tabs.
- Modify `frontend/src/lib/api/vault.test.ts`, `knowledge-workspace.test.ts`, `KnowledgePaneContent.test.tsx`, and `VaultFileTree.test.tsx`: contract and UI regression coverage.

## Task 1: Implement a fail-closed Canvas parser

**Files:** Create `deeper_notebook/vault/canvas.py`; create `tests/test_vault_canvas.py`; modify `deeper_notebook/vault/security.py` only to expose the existing canonical relative-path validation without weakening it.

**Interfaces:** `parse_canvas_document(content: bytes, *, relative_path: str) -> CanvasDocument`; `CanvasDocumentError(code: str)`; immutable `CanvasNode`, `CanvasEdge`, and `CanvasDocument(nodes: tuple[CanvasNode, ...], edges: tuple[CanvasEdge, ...])` records.

- [ ] **Step 1: Write the failing parser tests.**

```python
def test_parse_canvas_document_keeps_safe_nodes_and_edges():
    result = parse_canvas_document(
        b'{"nodes":[{"id":"idea","type":"text","x":0,"y":0,"width":240,"height":120,"text":"Idea"},{"id":"note","type":"file","x":320,"y":0,"width":240,"height":120,"file":"notes/Plan.md"}],"edges":[{"id":"edge","fromNode":"idea","toNode":"note","label":"supports"}]}',
        relative_path="maps/plan.canvas",
    )
    assert result.nodes[1].file_path == "notes/Plan.md"
    assert result.edges[0].from_node == "idea"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"nodes":[{"id":"x","type":"file","x":0,"y":0,"width":1,"height":1,"file":"../secret.md"}],"edges":[]}',
        b'{"nodes":[{"id":"x","type":"text","x":0,"y":0,"width":1,"height":1}],"edges":[{"id":"e","fromNode":"x","toNode":"missing"}]}',
    ],
)
def test_parse_canvas_document_rejects_unsafe_input(payload):
    with pytest.raises(CanvasDocumentError):
        parse_canvas_document(payload, relative_path="maps/plan.canvas")
```

- [ ] **Step 2: Run the test and confirm it fails because the parser is absent.**

Run: `.venv/bin/python -m pytest -q tests/test_vault_canvas.py`

Expected: collection fails with `ModuleNotFoundError` for `deeper_notebook.vault.canvas`.

- [ ] **Step 3: Implement the parser.**

```python
@dataclass(frozen=True)
class CanvasNode:
    id: str
    type: Literal["text", "file", "group", "unsupported"]
    x: float
    y: float
    width: float
    height: float
    text: str | None = None
    file_path: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class CanvasDocument:
    nodes: tuple[CanvasNode, ...]
    edges: tuple[CanvasEdge, ...]


def parse_canvas_document(content: bytes, *, relative_path: str) -> CanvasDocument:
    if not relative_path.casefold().endswith(".canvas"):
        raise CanvasDocumentError("canvas_path_invalid")
    raw = json.loads(content.decode("utf-8"))
    # Require object/list shapes, unique nonblank IDs, finite geometry, and canonical file paths.
```

Reject invalid JSON, non-object roots, more than 500 nodes or edges, node text/labels over 16 KiB, duplicate IDs, non-finite geometry, invalid file paths, and dangling edges. Preserve unknown node types only as non-interactive `unsupported`; never interpret strings as HTML, commands, URLs, or paths.

- [ ] **Step 4: Run focused tests.**

Run: `.venv/bin/python -m pytest -q tests/test_vault_canvas.py tests/test_vault_security.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit this increment.**

```bash
git add deeper_notebook/vault/canvas.py deeper_notebook/vault/security.py tests/test_vault_canvas.py
git commit -m "feat: validate read-only Canvas documents"
```

## Task 2: Expose a hash-bound read-only Canvas API

**Files:** Modify `deeper_notebook/vault/repository.py`, `deeper_notebook/vault/service.py`, `api/schemas/vault.py`, `api/routers/vault.py`, `tests/test_vault_api.py`, and `tests/test_vault_service.py`.

**Interfaces:** `VaultRepository.get_file(vault_id: str, relative_path: str) -> VaultFile`; `VaultService.read_canvas(vault_id: str, relative_path: str) -> VaultCanvasDocument`; `GET /deeper-notebook/vaults/{vault_id}/canvases/{relative_path:path}`.

- [ ] **Step 1: Add failing service and route tests.**

```python
def test_canvas_endpoint_returns_hash_bound_document(client):
    response = client.get(
        "/deeper-notebook/vaults/vault_mount:fixture/canvases/maps/plan.canvas"
    )
    assert response.status_code == 200
    assert response.json()["file"]["relative_path"] == "maps/plan.canvas"
    assert response.json()["source_hash"] == "a" * 64


def test_canvas_endpoint_rejects_traversal(client):
    response = client.get(
        "/deeper-notebook/vaults/vault_mount:fixture/canvases/../plan.canvas"
    )
    assert response.status_code in {403, 404, 409, 422}
```

- [ ] **Step 2: Run focused backend tests and confirm the new endpoint is missing.**

Run: `.venv/bin/python -m pytest -q tests/test_vault_api.py tests/test_vault_service.py`

Expected: the new Canvas route/service assertions fail.

- [ ] **Step 3: Implement the route through the existing secure boundary.**

```python
async def read_canvas(self, vault_id: str, relative_path: str) -> VaultCanvasDocument:
    file = await self._repository.get_file(vault_id, relative_path)
    mount = await self._repository.get_mount(vault_id)
    with approve_vault_root(mount.root_path) as root:
        source = secure_read(root, relative_path)
    if source.sha256 != file.content_hash:
        raise VaultSecurityError("changed_during_read")
    return VaultCanvasDocument(
        file=file,
        source_hash=source.sha256,
        document=parse_canvas_document(source.content, relative_path=relative_path),
    )
```

Make `get_file` an exact-match repository query, not a prefix lookup. Return `VaultCanvasResponse(file, source_hash, nodes, edges)` with `extra='forbid'`. Map missing, invalid, and changed Canvas states to stable `canvas_not_found`, `canvas_invalid`, and `canvas_source_changed` detail codes without returning an absolute path.

- [ ] **Step 4: Run the focused backend suite.**

Run: `.venv/bin/python -m pytest -q tests/test_vault_canvas.py tests/test_vault_api.py tests/test_vault_service.py tests/test_vault_security.py`

Expected: all selected tests pass, including source-hash mismatch and no absolute path in every failure body.

- [ ] **Step 5: Commit this increment.**

```bash
git add deeper_notebook/vault/repository.py deeper_notebook/vault/service.py api/schemas/vault.py api/routers/vault.py tests/test_vault_api.py tests/test_vault_service.py
git commit -m "feat: expose trusted Canvas documents read-only"
```

## Task 3: Add the frontend contract and persisted Canvas view mode

**Files:** Modify `frontend/src/lib/api/knowledge-workspace.ts`, `knowledge-workspace.test.ts`, `vault.ts`, `vault.test.ts`, and `frontend/src/lib/hooks/use-vault.ts`.

**Interfaces:** Add `canvas` to `KnowledgeViewMode`; add `VaultCanvasDocument`, `vaultApi.canvas(vaultId, relativePath)`, `vaultKeys.canvas`, and `useVaultCanvas(vaultId, relativePath, enabled)`.

- [ ] **Step 1: Write failing client and workspace-schema tests.**

```tsx
it('accepts a hash-bound Canvas response without a host path', async () => {
  mockGet.mockResolvedValue({ data: { file: canvasFile, source_hash: 'a'.repeat(64), nodes: [], edges: [] } })
  await expect(vaultApi.canvas('vault_mount:one', 'maps/plan.canvas')).resolves.toMatchObject({ source_hash: 'a'.repeat(64) })
})

it('persists canvas as a knowledge view mode', () => {
  expect(knowledgeViewModeSchema.parse('canvas')).toBe('canvas')
})
```

- [ ] **Step 2: Run client tests and confirm the contract is absent.**

Run: `cd frontend && npm test -- src/lib/api/vault.test.ts src/lib/api/knowledge-workspace.test.ts`

Expected: failures because `vaultApi.canvas` and `canvas` view mode do not exist.

- [ ] **Step 3: Implement the strict client contract.**

```ts
export const vaultCanvasSchema = z.object({
  file: vaultFileSchema,
  source_hash: z.string().regex(/^[0-9a-f]{64}$/i),
  nodes: z.array(vaultCanvasNodeSchema).max(500),
  edges: z.array(vaultCanvasEdgeSchema).max(500),
}).strict()
```

Keep `assertNoAbsolutePath` before Zod parsing. Build the request URL by encoding each relative-path segment separately so slashes remain route separators. Enable `useVaultCanvas` only when both identifiers exist and the tab is actually Canvas.

- [ ] **Step 4: Run contract tests and TypeScript validation.**

Run: `cd frontend && npm test -- src/lib/api/vault.test.ts src/lib/api/knowledge-workspace.test.ts && npx tsc --noEmit`

Expected: all selected tests and TypeScript checking pass.

- [ ] **Step 5: Commit this increment.**

```bash
git add frontend/src/lib/api/knowledge-workspace.ts frontend/src/lib/api/knowledge-workspace.test.ts frontend/src/lib/api/vault.ts frontend/src/lib/api/vault.test.ts frontend/src/lib/hooks/use-vault.ts
git commit -m "feat: add Canvas workspace data contract"
```

## Task 4: Render an accessible Canvas with no write surface

**Files:** Create `frontend/src/components/vault/CanvasViewer.tsx` and `CanvasViewer.test.tsx`.

**Interfaces:** `<CanvasViewer canvas isLoading error onRetry vaultId paneId files onNavigate />`; `files` supplies durable note IDs for valid same-vault file-node paths.

- [ ] **Step 1: Write failing viewer tests.**

```tsx
it('opens only a same-vault Markdown file node', () => {
  render(<CanvasViewer canvas={canvasFixture} vaultId='vault_mount:one' paneId='pane-1' files={[markdownFile]} onNavigate={onNavigate} />)
  fireEvent.click(screen.getByRole('button', { name: 'Plan' }))
  expect(onNavigate).toHaveBeenCalledWith('vault_mount:one', markdownFile.note_id, 'notes/Plan.md', 'Plan', 'pane-1', 'Plan', 'external-vault')
})

it('shows an alert and no save/edit/delete controls for an invalid document', () => {
  render(<CanvasViewer error={new Error('canvas_invalid')} />)
  expect(screen.getByRole('alert')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /save|edit|delete/i })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the viewer test and confirm it fails because the component is absent.**

Run: `cd frontend && npm test -- src/components/vault/CanvasViewer.test.tsx`

Expected: collection fails because `CanvasViewer` does not exist.

- [ ] **Step 3: Implement pan/zoom, safe rendering, and keyboard discovery.**

```tsx
if (isLoading) return <div role='status'>Loading Canvas…</div>
if (error || !canvas) return <div role='alert'><Button onClick={() => void onRetry?.()}>Retry Canvas</Button></div>
return <section aria-label='Canvas viewer' tabIndex={0}>
  <div role='toolbar' aria-label='Canvas controls'>
    <Button aria-label='Zoom in' onClick={() => setZoom(value => Math.min(2, value + 0.1))}>+</Button>
    <Button aria-label='Zoom out' onClick={() => setZoom(value => Math.max(0.5, value - 0.1))}>−</Button>
  </div>
  <svg aria-hidden='true'>{canvas.edges.map(edge => <line key={edge.id} x1={centers[edge.from_node].x} y1={centers[edge.from_node].y} x2={centers[edge.to_node].x} y2={centers[edge.to_node].y} />)}</svg>
  <ul aria-label='Canvas nodes'>{canvas.nodes.map(node => <li key={node.id}>{node.file_path && matchingFile(node.file_path) ? <Button onClick={() => navigateFile(node.file_path)}>{node.label ?? node.file_path}</Button> : node.label ?? node.text ?? node.type}</li>)}</ul>
</section>
```

Define `centers` with `Object.fromEntries(canvas.nodes.map((node) => [node.id, { x: node.x + node.width / 2, y: node.y + node.height / 2 }]))`; `matchingFile(path)` must find a file in `files` whose `relative_path === path`, `vault_id === vaultId`, and suffix is `.md`; `navigateFile(path)` must call `onNavigate` with that file's durable `note_id`. Use ordinary React text rendering; do not use `dangerouslySetInnerHTML`. Group and unsupported nodes are non-interactive. Do not add a Canvas library or an external URL action.

- [ ] **Step 4: Run component tests.**

Run: `cd frontend && npm test -- src/components/vault/CanvasViewer.test.tsx`

Expected: rendering, keyboard focus, internal navigation, loading, retry, and no-write assertions pass.

- [ ] **Step 5: Commit this increment.**

```bash
git add frontend/src/components/vault/CanvasViewer.tsx frontend/src/components/vault/CanvasViewer.test.tsx
git commit -m "feat: render read-only Canvas tabs"
```

## Task 5: Integrate Canvas selection into the existing workspace

**Files:** Modify `frontend/src/components/vault/KnowledgeExplorer.tsx`, `KnowledgePaneContent.tsx`, `KnowledgePaneContent.test.tsx`, `VaultFileTree.test.tsx`, and `KnowledgeWorkspaceLayout.test.tsx`.

**Interfaces:** A selected `.canvas` file opens or focuses a tab with `viewMode: 'canvas'`; a selected Markdown file continues to use `reading`; `KnowledgePaneContent` renders `CanvasViewer` before any Markdown-page query.

- [ ] **Step 1: Write failing workspace integration tests.**

```tsx
it('opens a Canvas in a reusable dedicated tab while Markdown keeps its preview', async () => {
  renderKnowledgeExplorerWithFiles([canvasFile, markdownFile])
  await userEvent.click(screen.getByRole('treeitem', { name: 'maps/Plan.canvas' }))
  expect(await screen.findByLabelText('Canvas viewer')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('treeitem', { name: 'notes/Plan.md' }))
  expect(screen.getByText(/Canonical source/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run integration tests and confirm Canvas is not yet routed.**

Run: `cd frontend && npm test -- src/components/vault/VaultFileTree.test.tsx src/components/vault/KnowledgePaneContent.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx`

Expected: Canvas selection is currently handled like a Markdown page or has no viewer.

- [ ] **Step 3: Wire the new mode without changing Markdown behavior.**

```ts
viewMode: file.relative_path.toLocaleLowerCase().endsWith('.canvas') ? 'canvas' : 'reading',

const isCanvas = !isOverlay && visibleMode === 'canvas'
const canvas = useVaultCanvas(vaultId, activeTab?.relativePath, isCanvas)
if (isCanvas) return <CanvasViewer canvas={canvas.data} isLoading={canvas.isLoading} error={canvas.error} onRetry={canvas.refetch} vaultId={vaultId!} paneId={pane.id} files={vaultFiles} onNavigate={onNavigate} />
```

Extend `KnowledgePaneContentProps` with `vaultFiles: VaultFile[]`; pass `files.data ?? []` from `KnowledgeExplorer` into every rendered pane. Strip `.md` and `.canvas` suffixes from tab titles. Hide the Markdown view-mode toolbar for Canvas. Do not issue `page`, `outgoing`, or `graph` queries for Canvas mode. Preserve split panes and the normal reusable tab identity.

- [ ] **Step 4: Run focused UI verification, lint, type check, and build.**

Run: `cd frontend && npm test -- src/components/vault/CanvasViewer.test.tsx src/components/vault/VaultFileTree.test.tsx src/components/vault/KnowledgePaneContent.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx && npm run lint && npx tsc --noEmit && npm run build`

Expected: every command exits zero.

- [ ] **Step 5: Run backend regression and commit.**

Run: `.venv/bin/python -m pytest -q tests/test_vault_canvas.py tests/test_vault_api.py tests/test_vault_service.py tests/test_vault_security.py`

Expected: all selected backend tests pass.

```bash
git add frontend/src/components/vault/KnowledgeExplorer.tsx frontend/src/components/vault/KnowledgePaneContent.tsx frontend/src/components/vault/KnowledgePaneContent.test.tsx frontend/src/components/vault/VaultFileTree.test.tsx frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx
git commit -m "feat: open trusted Canvas files in knowledge workspace"
```

## Final Verification

- [ ] Run full backend regression: `.venv/bin/python -m pytest -q`.
- [ ] Run full frontend regression: `cd frontend && npm test`.
- [ ] Run frontend lint, type check, and production build: `cd frontend && npm run lint && npx tsc --noEmit && npm run build`.
- [ ] In a disposable mounted vault only, scan a valid Canvas, open it in a split pane, activate a same-vault Markdown node, and verify the Canvas SHA-256 is unchanged before and after. Do not mount or alter either real 2nd Brains directory.
