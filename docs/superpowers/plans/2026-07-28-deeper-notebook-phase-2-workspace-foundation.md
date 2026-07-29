# Deeper Notebook Phase 2 Workspace Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable knowledge-note tabs and recursively resizable split panes to the read-only Deeper Notebook vault workspace, including persistence across native packaged-app restarts.

**Architecture:** A versioned workspace document is validated and atomically stored below Deeper Notebook's canonical desktop data root, then exposed through authenticated `GET` and `PUT` endpoints. A focused Zustand store owns immediate pane/tab interactions and hydrates from that durable API; a debounced mutation saves state without relying on port-scoped browser storage. Presentational tab and recursive-layout components consume the store, while a refactored `KnowledgeExplorer` continues to own vault selection and file navigation.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, Next.js 16, React 19, TypeScript, Zustand 5, TanStack Query 5, react-resizable-panels, Radix/shadcn primitives, Vitest, Testing Library, Pytest.

## Global Constraints

- Mounted Markdown and asset files remain canonical; this plan must not add update, delete, move, rename, serialization, or external-vault write-back behavior.
- Existing notebooks, research, Evidence Studio, Capture, podcasts, memory, model routing, and native desktop workflows remain unchanged.
- Persist only vault IDs, note IDs, relative paths, titles, pane layout, and view preferences; never persist file content, hashes, credentials, or absolute paths.
- Keep the existing absolute-path response rejection in `frontend/src/lib/api/vault.ts`.
- The durable file is `active_data_root() / "workspaces" / "knowledge-workspace-v1.json"`.
- The durable API is exactly `GET /api/deeper-notebook/workspace/knowledge` and `PUT /api/deeper-notebook/workspace/knowledge`.
- The document schema version is exactly `1`.
- Support recursively nested horizontal and vertical splits; do not limit the UI to two panes.
- Bound hostile or corrupted durable input to at most 32 panes, 128 total tabs, and 64 levels of split nesting.
- Every interactive control must be keyboard accessible and expose an accessible name.
- Use Deeper Notebook's existing semantic tokens and component primitives; do not introduce a new palette or raw color values.
- Existing read-only behavior and source-hash guarantees remain unchanged.

---

### Task 1: Durable Workspace Contract and Atomic Persistence

**Files:**
- Create: `deeper_notebook/workspace/__init__.py`
- Create: `deeper_notebook/workspace/contracts.py`
- Create: `deeper_notebook/workspace/persistence.py`
- Test: `tests/test_knowledge_workspace_persistence.py`

**Interfaces:**
- Produces `KnowledgeWorkspaceDocument`, `KnowledgePaneState`, `KnowledgeTabState`, `PaneLayoutNode`, `SplitLayoutNode`, `WorkspaceStateError`, `default_knowledge_workspace()`, `knowledge_workspace_path()`, `load_knowledge_workspace()`, and `save_knowledge_workspace()`.
- `KnowledgeViewMode` is exactly `Literal["reading", "source", "live-preview", "graph"]`.
- `SplitDirection` is exactly `Literal["horizontal", "vertical"]`.
- Initial state is one empty pane with ID `pane-1`; `next_id` is `2`.

- [ ] **Step 1: Write the failing persistence tests**

```py
from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_notebook.workspace.contracts import (
    KnowledgeWorkspaceDocument,
    default_knowledge_workspace,
)
from deeper_notebook.workspace.persistence import (
    load_knowledge_workspace,
    save_knowledge_workspace,
)


def populated() -> KnowledgeWorkspaceDocument:
    return KnowledgeWorkspaceDocument.model_validate({
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {
            "pane-1": {
                "id": "pane-1",
                "active_tab_id": "tab:one",
                "tabs": [{
                    "id": "tab:one",
                    "vault_id": "vault:one",
                    "note_id": "note:one",
                    "title": "One",
                    "relative_path": "Projects/One.md",
                    "view_mode": "reading",
                }],
            },
        },
        "layout": {"type": "pane", "pane_id": "pane-1"},
    })


def test_missing_workspace_returns_default(tmp_path: Path):
    state = load_knowledge_workspace(path=tmp_path / "knowledge.json")
    assert state == default_knowledge_workspace()


def test_workspace_round_trips_through_atomic_file(tmp_path: Path):
    path = tmp_path / "workspaces" / "knowledge.json"
    save_knowledge_workspace(populated(), path=path)
    assert load_knowledge_workspace(path=path) == populated()
    assert not path.with_suffix(".json.tmp").exists()


def test_absolute_or_parent_relative_paths_are_rejected():
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["tabs"][0]["relative_path"] = "/Users/me/secret.md"
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)
    payload["panes"]["pane-1"]["tabs"][0]["relative_path"] = "../secret.md"
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)


def test_inconsistent_layout_is_rejected():
    payload = populated().model_dump()
    payload["layout"] = {"type": "pane", "pane_id": "missing"}
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)


def test_failed_replace_preserves_previous_document(tmp_path: Path, monkeypatch):
    path = tmp_path / "knowledge.json"
    save_knowledge_workspace(populated(), path=path)
    original = path.read_bytes()
    monkeypatch.setattr("deeper_notebook.workspace.persistence.os.replace",
                        lambda *_: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError, match="injected"):
        save_knowledge_workspace(default_knowledge_workspace(), path=path)
    assert path.read_bytes() == original
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run pytest tests/test_knowledge_workspace_persistence.py -q
```

Expected: collection fails because `deeper_notebook.workspace` does not exist.

- [ ] **Step 3: Implement strict Pydantic contracts**

Use `ConfigDict(extra="forbid")` on every model. Tabs validate `relative_path` by rejecting `/`, `\\`, UNC prefixes, drive prefixes, empty paths, and any `..` segment. `KnowledgeWorkspaceDocument` performs an after-model validation that:

- the dictionary key equals each pane's `id`;
- `active_pane_id` exists;
- every non-null `active_tab_id` exists in that pane;
- tab IDs are unique within a pane;
- every layout leaf references exactly one existing pane;
- no pane is absent from or duplicated in the layout;
- split IDs are unique;
- pane count is at most 32, total tab count at most 128, and nesting depth at most 64.

Use a discriminated recursive union:

```py
class PaneLayoutNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["pane"] = "pane"
    pane_id: str = Field(min_length=1, max_length=128)


class SplitLayoutNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["split"] = "split"
    id: str = Field(min_length=1, max_length=128)
    direction: SplitDirection
    first: "KnowledgeLayoutNode"
    second: "KnowledgeLayoutNode"


KnowledgeLayoutNode = Annotated[
    PaneLayoutNode | SplitLayoutNode,
    Field(discriminator="type"),
]
```

- [ ] **Step 4: Implement atomic persistence**

`knowledge_workspace_path()` returns `active_data_root() / "workspaces" / "knowledge-workspace-v1.json"`. `load_knowledge_workspace(path=None)` calls it only when no explicit test path is supplied. Missing files return `default_knowledge_workspace()`. Invalid JSON or invalid schema raises `WorkspaceStateError` without rewriting the file.

`save_knowledge_workspace(document, path=None)`:

1. creates only the canonical parent directory;
2. serializes deterministic UTF-8 JSON with a final newline;
3. opens a sibling `.tmp` file;
4. writes, flushes, and `os.fsync()`s it;
5. calls `os.replace(tmp, target)`;
6. fsyncs the parent directory where supported;
7. removes only its own temporary file on failure.

- [ ] **Step 5: Run tests and verify GREEN**

Run the command from Step 2. Expected: 5 tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add deeper_notebook/workspace tests/test_knowledge_workspace_persistence.py
git commit -m "feat(workspace): persist knowledge layout atomically"
```

---

### Task 2: Authenticated Workspace API

**Files:**
- Create: `api/routers/knowledge_workspace.py`
- Modify: `api/main.py`
- Test: `tests/test_knowledge_workspace_api.py`

**Interfaces:**
- Consumes Task 1 contracts and persistence.
- Produces:
  - `GET /api/deeper-notebook/workspace/knowledge`
  - `PUT /api/deeper-notebook/workspace/knowledge`
- Both endpoints return a `KnowledgeWorkspaceDocument` and never return a filesystem path.

- [ ] **Step 1: Write failing API tests**

Create a minimal FastAPI app with the new router and monkeypatch the persistence path through the module's `_workspace_path()` seam. Assert:

```py
@pytest.mark.asyncio
async def test_get_returns_default_and_put_survives_new_client(api_app):
    async with AsyncClient(transport=ASGITransport(app=api_app),
                           base_url="http://test") as client:
        initial = await client.get("/api/deeper-notebook/workspace/knowledge")
        assert initial.status_code == 200
        payload = initial.json()
        payload["panes"]["pane-1"]["tabs"] = [{
            "id": "tab:one", "vault_id": "vault:one", "note_id": "note:one",
            "title": "One", "relative_path": "One.md", "view_mode": "reading",
        }]
        payload["panes"]["pane-1"]["active_tab_id"] = "tab:one"
        saved = await client.put("/api/deeper-notebook/workspace/knowledge",
                                 json=payload)
        assert saved.status_code == 200
    async with AsyncClient(transport=ASGITransport(app=api_app),
                           base_url="http://test") as restarted_client:
        restored = await restarted_client.get(
            "/api/deeper-notebook/workspace/knowledge")
    assert restored.json()["panes"]["pane-1"]["active_tab_id"] == "tab:one"


@pytest.mark.asyncio
async def test_put_rejects_absolute_relative_path(api_app):
    payload = default_knowledge_workspace().model_dump(mode="json")
    payload["panes"]["pane-1"]["tabs"] = [{
        "id": "tab:bad", "vault_id": "v", "note_id": "n", "title": "Bad",
        "relative_path": "C:\\Users\\me\\secret.md", "view_mode": "reading",
    }]
    payload["panes"]["pane-1"]["active_tab_id"] = "tab:bad"
    async with AsyncClient(transport=ASGITransport(app=api_app),
                           base_url="http://test") as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge", json=payload)
    assert response.status_code == 422
```

Also assert malformed stored JSON produces a stable `409 workspace_state_invalid` response and write failures produce `503 workspace_state_unavailable`.

- [ ] **Step 2: Run API tests and verify RED**

```bash
uv run pytest tests/test_knowledge_workspace_api.py -q
```

Expected: FAIL because the router does not exist.

- [ ] **Step 3: Implement and register the router**

The router path is `/workspace/knowledge`; `api/main.py` registers it under the existing `/api/deeper-notebook` prefix. Add a private `_workspace_path()` that delegates to Task 1's `knowledge_workspace_path()` and pass that path explicitly to load/save, giving hermetic router tests one patch seam. Catch only `WorkspaceStateError` as 409 and filesystem errors as 503. Let Pydantic produce 422 for invalid request documents. Do not create a hidden legacy write alias for this new canonical feature.

- [ ] **Step 4: Run API and regression tests**

```bash
uv run pytest \
  tests/test_knowledge_workspace_persistence.py \
  tests/test_knowledge_workspace_api.py \
  tests/test_vault_api.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add api/routers/knowledge_workspace.py api/main.py tests/test_knowledge_workspace_api.py
git commit -m "feat(api): expose durable knowledge workspace"
```

---

### Task 3: Frontend Contract, Hydration, and Immediate Workspace Store

**Files:**
- Create: `frontend/src/lib/api/knowledge-workspace.ts`
- Create: `frontend/src/lib/api/knowledge-workspace.test.ts`
- Create: `frontend/src/lib/stores/knowledge-workspace-store.ts`
- Create: `frontend/src/lib/stores/knowledge-workspace-store.test.ts`
- Create: `frontend/src/lib/hooks/use-knowledge-workspace.ts`
- Test: `frontend/src/lib/hooks/use-knowledge-workspace.test.tsx`

**Interfaces:**
- Produces frontend equivalents of the Task 1 document types.
- Produces `knowledgeWorkspaceApi.get()` and `.put(document)`.
- Produces `useKnowledgeWorkspaceStore`, `selectActiveKnowledgeTab`, `selectPaneCount`, `useHydrateKnowledgeWorkspace()`, and `usePersistKnowledgeWorkspace()`.
- The Zustand store is not persisted to browser storage.

- [ ] **Step 1: Write failing schema and store tests**

Test that the Zod contract rejects absolute `relative_path` values and inconsistent layout references. Test state transitions:

```ts
const plan = {
  vaultId: 'vault:one',
  noteId: 'note:plan',
  title: 'Plan',
  relativePath: 'Projects/Plan.md',
} as const

it('deduplicates an open note inside the active pane', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab(plan)
  store.openTab(plan)
  expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(1)
})

it('creates recursively nestable horizontal and vertical splits', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab(plan)
  const second = store.splitPane('pane-1', 'horizontal')
  store.splitPane(second, 'vertical')
  expect(selectPaneCount(useKnowledgeWorkspaceStore.getState())).toBe(3)
})

it('closes a split pane without losing its sibling', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab(plan)
  const second = store.splitPane('pane-1', 'horizontal')
  store.closePane(second)
  expect(useKnowledgeWorkspaceStore.getState().layout)
    .toEqual({ type: 'pane', paneId: 'pane-1' })
})
```

Also cover close-tab neighbor selection and per-tab view mode.

- [ ] **Step 2: Run schema/store tests and verify RED**

```bash
cd frontend
npx vitest run \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement Zod API and pure Zustand actions**

The API module uses snake_case wire fields and converts them to the camelCase store document. It recursively rejects absolute paths before parsing, matching the vault API boundary. The store exposes:

```ts
interface KnowledgeWorkspaceState extends KnowledgeWorkspaceDocument {
  hydrated: boolean
  replaceWorkspace: (document: KnowledgeWorkspaceDocument) => void
  openTab: (tab: OpenKnowledgeTab, paneId?: string) => void
  closeTab: (paneId: string, tabId: string) => void
  activateTab: (paneId: string, tabId: string) => void
  setActivePane: (paneId: string) => void
  setTabViewMode: (paneId: string, tabId: string, mode: KnowledgeViewMode) => void
  splitPane: (paneId: string, direction: SplitDirection) => string
  closePane: (paneId: string) => void
  resetWorkspace: () => void
}
```

Use a recursive immutable replacement helper for splits and a recursive collapse helper for pane close. `splitPane` copies the source pane's active tab, makes the new pane active, and returns its ID. `openTab` deduplicates by `vaultId` plus `noteId` inside the target pane.

- [ ] **Step 4: Write failing hydration/persistence hook tests**

With a fresh QueryClient, mock the API and fake timers. Assert:

- GET replaces the default state exactly once and marks it hydrated.
- state changes before GET resolves are not overwritten by the late response;
- a post-hydration state change triggers one debounced PUT after 400 ms;
- initial hydration does not echo an immediate PUT;
- failed PUT leaves local state intact and exposes an error.

- [ ] **Step 5: Run hook tests and verify RED**

```bash
cd frontend
npx vitest run src/lib/hooks/use-knowledge-workspace.test.tsx --pool=forks --maxWorkers=1
```

Expected: FAIL because the hooks do not exist.

- [ ] **Step 6: Implement durable synchronization**

`useHydrateKnowledgeWorkspace()` issues the query and applies it only if the store has not been modified since the query started. `usePersistKnowledgeWorkspace()` subscribes to serializable state after hydration and issues a 400 ms debounced PUT. Serialize only version, panes, layout, active pane, and next ID. Flush the final pending valid state on unmount with `mutateAsync`; never use `navigator.sendBeacon`.

- [ ] **Step 7: Run focused frontend tests and verify GREEN**

Run all three Task 3 test files. Expected: all tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add \
  frontend/src/lib/api/knowledge-workspace.ts \
  frontend/src/lib/api/knowledge-workspace.test.ts \
  frontend/src/lib/stores/knowledge-workspace-store.ts \
  frontend/src/lib/stores/knowledge-workspace-store.test.ts \
  frontend/src/lib/hooks/use-knowledge-workspace.ts \
  frontend/src/lib/hooks/use-knowledge-workspace.test.tsx
git commit -m "feat(knowledge): hydrate durable workspace state"
```

---

### Task 4: Accessible Tabs and Recursive Resizable Panes

**Files:**
- Create: `frontend/src/components/vault/KnowledgeTabStrip.tsx`
- Create: `frontend/src/components/vault/KnowledgeTabStrip.test.tsx`
- Create: `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx`
- Create: `frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx`
- Modify: `frontend/src/lib/locales/en-US/index.ts`

**Interfaces:**
- `KnowledgeTabStrip` consumes a `KnowledgePane` plus activate/close callbacks.
- `KnowledgeWorkspaceLayout` accepts `renderPane: (pane: KnowledgePane) => React.ReactNode`.

- [ ] **Step 1: Write failing tab tests**

Assert active `aria-selected`, click activation, separate close behavior, and wrapping ArrowLeft/ArrowRight plus Home/End navigation. Close buttons use `Close {title}`.

- [ ] **Step 2: Run tab tests and verify RED**

```bash
cd frontend
npx vitest run src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the tab strip**

Use `role="tablist"`, real tab buttons with roving `tabIndex`, adjacent non-nested close buttons, existing `Button`/`Tooltip` primitives, `X`, semantic tokens, truncation, and visible focus styles. Keyboard selection must move DOM focus to the selected tab.

- [ ] **Step 4: Write failing recursive-layout tests**

Open a fixture tab, render the layout, click Split pane right then Split pane down, and assert three accessible pane regions. Close the second pane and assert the split collapses. Focus a pane and assert it becomes the active pane.

- [ ] **Step 5: Run layout tests and verify RED**

```bash
cd frontend
npx vitest run src/components/vault/KnowledgeWorkspaceLayout.test.tsx --pool=forks --maxWorkers=1
```

Expected: FAIL because the component does not exist.

- [ ] **Step 6: Implement recursive resizable layout**

- A pane node renders an accessible region with the tab strip, split-right, split-down, and close-pane controls plus `renderPane(pane)`.
- A split node renders `ResizablePanelGroup` with its exact direction, two `ResizablePanel` children, and one `ResizableHandle`.
- `autoSaveId` may improve same-origin responsiveness, but the split tree itself remains durable through Task 3.
- Clicking or focusing a pane calls `setActivePane`.
- Close-pane is disabled when only one pane exists.
- The active pane uses the existing primary semantic ring.

Add English keys: `openTabs`, `closeTab`, `knowledgeWorkspace`, `knowledgePane`, `splitPaneRight`, `splitPaneDown`, and `closePane`.

- [ ] **Step 7: Run Task 4 tests and commit**

Run the tab, layout, and store tests. Then:

```bash
git add frontend/src/components/vault/KnowledgeTabStrip* \
  frontend/src/components/vault/KnowledgeWorkspaceLayout* \
  frontend/src/lib/locales/en-US/index.ts
git commit -m "feat(knowledge): add accessible tabbed split panes"
```

---

### Task 5: Integrate the Durable Workspace with the Read-Only Explorer

**Files:**
- Create: `frontend/src/components/vault/KnowledgePaneContent.tsx`
- Create: `frontend/src/components/vault/KnowledgeLinksInspector.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- Modify: `frontend/src/lib/locales/en-US/index.ts`

**Interfaces:**
- `KnowledgeExplorer` maps selected `VaultFile` records to `OpenKnowledgeTab`.
- `KnowledgePaneContent` accepts `pane`, `mounts`, and `onNavigate`.
- `KnowledgeLinksInspector` follows the globally active pane/tab.

- [ ] **Step 1: Extend explorer tests and verify RED**

Add a second fixture file/page and reset the workspace store before each test. Assert:

- selecting two files opens two deduplicated tabs;
- splitting copies the current tab and a later selection changes only the active pane;
- the links inspector follows the focused pane;
- Reader/Local Graph selection persists in the active tab;
- hydration loading and durable-save failure have visible non-destructive states;
- existing link/graph loading and error states remain.

Run:

```bash
cd frontend
npx vitest run src/components/vault/KnowledgeExplorer.test.tsx --pool=forks --maxWorkers=1
```

Expected: FAIL because the explorer still owns one local `noteId`.

- [ ] **Step 2: Extract pane content and links inspector**

Move the existing note query, Markdown reader, properties, tags, outline, graph, backlinks, outgoing links, loading, and error behavior out of the monolithic explorer. Each pane calls `useVaultPage` and conditionally `useVaultGraph` for its active tab. Reader maps to `reading`; Local Graph maps to `graph`. Empty panes render the existing select-note state. Every pane retains the read-only badge and canonical-source description.

- [ ] **Step 3: Refactor `KnowledgeExplorer` around durable state**

Call the hydration and persistence hooks once. Keep the header, scan control, vault selector, mount status, and file tree. Selecting a file calls:

```ts
openTab({
  vaultId: file.vault_id,
  noteId: file.note_id,
  title: file.relative_path.split('/').pop()?.replace(/\.md$/i, '') || file.relative_path,
  relativePath: file.relative_path,
})
```

Render `KnowledgeWorkspaceLayout` in the center and `KnowledgeLinksInspector` on the right. Selecting another vault updates the explorer filter but does not destroy tabs from other mounts. Persisted tabs missing from the first 100-file listing retain their stored relative-path label and load directly by note ID.

- [ ] **Step 4: Run focused frontend and backend tests**

```bash
uv run pytest \
  tests/test_knowledge_workspace_persistence.py \
  tests/test_knowledge_workspace_api.py \
  tests/test_vault_api.py -q
cd frontend
npx vitest run \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  src/lib/hooks/use-knowledge-workspace.test.tsx \
  src/components/vault/KnowledgeTabStrip.test.tsx \
  src/components/vault/KnowledgeWorkspaceLayout.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/VaultFileTree.test.tsx \
  src/lib/hooks/use-vault.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: all focused tests pass.

- [ ] **Step 5: Run full regression and production verification**

```bash
uv run pytest -q
cd frontend
npm test
npm run lint
npm run build
```

Expected: zero failed tests, zero lint errors, and a successful Next.js production build.

- [ ] **Step 6: Commit Task 5**

```bash
git add \
  frontend/src/components/vault/KnowledgeExplorer.tsx \
  frontend/src/components/vault/KnowledgeExplorer.test.tsx \
  frontend/src/components/vault/KnowledgePaneContent.tsx \
  frontend/src/components/vault/KnowledgeLinksInspector.tsx \
  frontend/src/lib/locales/en-US/index.ts
git commit -m "feat(knowledge): integrate durable tabbed workspace"
```

---

## Completion Gate

- Opening a vault file creates or activates one tab in the active pane.
- Multiple notes remain open as tabs.
- Horizontal and vertical splits nest without a two-pane UI limit.
- Closing a pane collapses its split without losing its sibling.
- Each pane independently preserves its active note and Reader/Graph view.
- The global links inspector follows the focused pane.
- Layout and tabs survive a new API/browser client and a changing frontend port.
- Invalid or hostile stored workspace state is rejected without overwriting it.
- The external vault remains read-only and no write-capable vault endpoint is called.
- Full backend/frontend tests, lint, and production build pass.

## Follow-on Phase 2 Plans

After this foundation is reviewed and merged, execute separate plans in this order:

1. Source, live-preview, and reading editor modes plus outline, footnotes, properties, tags, and page preview.
2. Quick switcher, knowledge-aware command palette, slash commands, and combined exact/semantic search.
3. Daily and unique notes, templates, random note, bookmarks, composer, word count, and named workspace persistence.
