# Deeper Notebook Navigation Productivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unified-engine-native global bookmarks, nested bookmark folders and tags, Random Note, Unicode-aware document metrics, and revisioned named workspace snapshots to Deeper Notebook's existing Knowledge workspace.

**Architecture:** Migration 39 adds three navigation metadata tables plus a content-free operation-receipt table. Focused navigation contracts, repository, and service modules sit beside the existing unified-engine foundation; a target resolver bridges current vault and Overlay projections to stable unified IDs without persisting paths. The frontend consumes strict Zod contracts, extends the existing workspace store with navigation state, and presents the selected Integrated Utility Rail while preserving the file-backed Current Session as the autosave authority.

**Tech Stack:** Python 3.11/3.12, Pydantic 2 strict models, FastAPI, SurrealDB/SurrealQL, React 19, Next.js 16, TypeScript, Zod 4, Zustand 5, TanStack Query 5, CodeMirror 6, Vitest, Testing Library, Playwright, pytest, and Ruff.

## Global Constraints

- Work from a dedicated `codex/` feature worktree created at execution time.
- Baseline is local `main` at or after specification commit `7fd4de65`.
- Do not access, mount, scan, or modify `/Users/Antman/Desktop/2nd Brains` or `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains` during implementation or automated proof.
- External Obsidian, Logseq, and neutral Markdown remain `external_read_only`; this plan adds no external mutation route, capability, filesystem write, rename, move, or toggle.
- New bookmark and named-workspace rows store stable unified IDs, bounded filters, and cached display labels only; they store no canonical source body, selected text, absolute path, root, credential, or environment value.
- The file-backed Current Session remains the continuously autosaved crash-recovery authority. Named workspaces are explicit revisioned snapshots and never overwrite one another automatically.
- Existing unified-engine shadow and backfill defaults remain disabled. Automated tests use synthetic fixtures; controlled proof enables the existing flags explicitly against a temporary approved root.
- No new Python, Node, or browser dependency is required.
- Backend wire and domain models use `ConfigDict(extra="forbid", strict=True)`.
- Every metadata mutation includes `operation_id`; updates and deletes also include `expected_revision`.
- Repository mutations are parameterized, transactional, revision-safe, and durably idempotent through `knowledge_navigation_operation_receipt`.
- Folder depth is at most 16. Workspace limits remain 32 panes, 128 tabs, and layout depth 64.
- Random Note accepts at most 32 space IDs and 32 tags and never accepts a public random seed.
- Document metrics are frontend-only, use Unicode code points, count `Intl.Segmenter("und", { granularity: "word" })` segments with `isWordLike`, and estimate `ceil(words / 200)` minutes.
- Run backend and frontend suites serially on this Mac to avoid the existing memory-pressure/import-timeout failure mode.
- Do not push, merge, enable live external scanning, or promote feature defaults without a separate explicit user instruction.

---

## File Map

### Create

- `deeper_notebook/database/migrations/39.surrealql` — navigation metadata and operation-receipt schema.
- `deeper_notebook/database/migrations/39_down.surrealql` — remove only migration-39 tables and indexes.
- `deeper_notebook/knowledge_engine/navigation_contracts.py` — strict target, bookmark, folder, named-workspace, restore-plan, filter, and receipt models.
- `deeper_notebook/knowledge_engine/navigation_repository.py` — transactional metadata CRUD, idempotency receipts, hydration queries, and Random Note candidate reads.
- `deeper_notebook/knowledge_engine/navigation_service.py` — target hydration, folder policy, named-workspace restore planning, and injected Random Note selection.
- `api/schemas/knowledge_navigation.py` — strict redacted request/response contracts.
- `api/routers/knowledge_navigation.py` — canonical bookmark, folder, workspace, and Random Note routes.
- `tests/test_knowledge_navigation_migration.py`
- `tests/test_knowledge_navigation_contracts.py`
- `tests/test_knowledge_navigation_repository.py`
- `tests/test_knowledge_navigation_identity.py`
- `tests/test_knowledge_navigation_service.py`
- `tests/test_knowledge_navigation_api.py`
- `tests/integration/test_knowledge_navigation_persistence.py`
- `frontend/src/lib/api/knowledge-navigation.ts` — Zod schemas, wire conversions, and API client.
- `frontend/src/lib/api/knowledge-navigation.test.ts`
- `frontend/src/lib/hooks/use-knowledge-navigation.ts` — query keys and mutation hooks.
- `frontend/src/lib/hooks/use-knowledge-navigation.test.tsx`
- `frontend/src/lib/knowledge/document-metrics.ts` — pure metrics and fallback segmentation.
- `frontend/src/lib/knowledge/document-metrics.test.ts`
- `frontend/src/components/vault/DocumentMetricsFooter.tsx`
- `frontend/src/components/vault/DocumentMetricsFooter.test.tsx`
- `frontend/src/components/vault/KnowledgeUtilityRail.tsx`
- `frontend/src/components/vault/KnowledgeUtilityRail.test.tsx`
- `frontend/src/components/vault/KnowledgeBookmarksPanel.tsx`
- `frontend/src/components/vault/KnowledgeBookmarksPanel.test.tsx`
- `frontend/src/components/vault/KnowledgeWorkspacesPanel.tsx`
- `frontend/src/components/vault/KnowledgeWorkspacesPanel.test.tsx`
- `frontend/src/components/vault/WorkspaceRestoreDialog.tsx`
- `frontend/src/components/vault/WorkspaceRestoreDialog.test.tsx`
- `frontend/e2e/knowledge-navigation-productivity.spec.ts`
- `scripts/verify_navigation_productivity.py` — synthetic persistent-runtime verifier.
- `tests/test_verify_navigation_productivity.py`
- `docs/verification/2026-07-31-deeper-notebook-navigation-productivity.md`

### Modify

- `deeper_notebook/knowledge_engine/repository.py` — current identity and open-descriptor resolution.
- `deeper_notebook/knowledge_engine/service.py` — expose identity and navigation-target reads.
- `deeper_notebook/knowledge_engine/__init__.py` — export navigation service contracts only.
- `deeper_notebook/workspace/contracts.py` — backward-compatible Current Session navigation-state defaults.
- `api/schemas/vault.py` — optional unified document/block identity bridge fields.
- `api/routers/vault.py` — hydrate identity bridge without breaking canonical page reads.
- `deeper_notebook/overlay/contracts.py` — optional unified identity fields with safe defaults.
- `api/routers/overlay.py` — hydrate Overlay identity bridge without changing Overlay authority.
- `api/main.py` — construct the navigation service and register its router.
- `tests/test_migration_discovery.py` — assert migration 39 discovery and down boundary.
- `tests/test_knowledge_engine_repository.py`
- `tests/test_knowledge_engine_service.py`
- `tests/test_knowledge_engine_lifespan.py`
- `tests/test_vault_api.py`
- `tests/test_overlay_api.py`
- `tests/test_knowledge_workspace_api.py`
- `tests/test_knowledge_workspace_persistence.py`
- `frontend/src/lib/api/knowledge-workspace.ts` — navigation state and optional unified tab identity.
- `frontend/src/lib/api/knowledge-workspace.test.ts`
- `frontend/src/lib/api/vault.ts` — parse bridge identities.
- `frontend/src/lib/api/overlay.ts` — parse bridge identities.
- `frontend/src/lib/stores/knowledge-workspace-store.ts` — atomic snapshot apply and navigation state.
- `frontend/src/lib/stores/knowledge-workspace-store.test.ts`
- `frontend/src/lib/hooks/use-knowledge-workspace.ts` — persist Current Session navigation state.
- `frontend/src/lib/hooks/use-knowledge-workspace.test.tsx`
- `frontend/src/lib/commands/command-registry.ts`
- `frontend/src/lib/commands/command-registry.test.ts`
- `frontend/src/lib/commands/knowledge-command-context-store.ts`
- `frontend/src/lib/commands/knowledge-command-context-store.test.ts`
- `frontend/src/components/vault/KnowledgeCommandBridge.tsx`
- `frontend/src/components/vault/KnowledgeCommandBridge.test.tsx`
- `frontend/src/components/vault/KnowledgeExplorer.tsx`
- `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- `frontend/src/components/vault/KnowledgeQuickSwitcher.tsx`
- `frontend/src/components/vault/KnowledgeQuickSwitcher.test.tsx`
- `frontend/src/components/vault/KnowledgePaneContent.tsx`
- `frontend/src/components/vault/KnowledgePaneContent.test.tsx`
- `frontend/src/components/overlay/OverlayDocumentView.tsx`
- `frontend/src/components/overlay/OverlayDocumentView.test.tsx`
- `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx`
- `frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx`
- `frontend/src/components/vault/VaultGraph.tsx`
- every `frontend/src/lib/locales/*/index.ts` locale bundle.
- `frontend/src/lib/locales/index.test.ts`
- `frontend/e2e/fixtures/knowledge-editor-modes.ts`

## Interfaces Locked by This Plan

### Backend

```python
KnowledgeTarget = Annotated[
    DocumentTarget | BlockTarget | SearchTarget | GraphTarget | WorkspaceTarget,
    Field(discriminator="kind"),
]


class KnowledgeNavigationRepository:
    async def create_folder(self, command: CreateFolder) -> BookmarkFolder:
        raise NotImplementedError

    async def update_folder(
        self, folder_id: str, command: UpdateFolder
    ) -> BookmarkFolder:
        raise NotImplementedError

    async def delete_folder(
        self, folder_id: str, command: DeleteFolder
    ) -> NavigationReceipt:
        raise NotImplementedError

    async def list_folders(self) -> list[BookmarkFolder]:
        raise NotImplementedError

    async def create_bookmark(self, command: CreateBookmark) -> Bookmark:
        raise NotImplementedError

    async def update_bookmark(
        self, bookmark_id: str, command: UpdateBookmark
    ) -> Bookmark:
        raise NotImplementedError

    async def delete_bookmark(
        self, bookmark_id: str, command: DeleteBookmark
    ) -> NavigationReceipt:
        raise NotImplementedError

    async def list_bookmarks(
        self, filters: BookmarkFilters, cursor: str | None, limit: int
    ) -> BookmarkPage:
        raise NotImplementedError

    async def create_workspace(
        self, command: CreateWorkspace
    ) -> NamedKnowledgeWorkspace:
        raise NotImplementedError

    async def update_workspace(
        self, workspace_id: str, command: UpdateWorkspace
    ) -> NamedKnowledgeWorkspace:
        raise NotImplementedError

    async def duplicate_workspace(
        self, workspace_id: str, command: DuplicateWorkspace
    ) -> NamedKnowledgeWorkspace:
        raise NotImplementedError

    async def delete_workspace(
        self, workspace_id: str, command: DeleteWorkspace
    ) -> NavigationReceipt:
        raise NotImplementedError

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        raise NotImplementedError

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        raise NotImplementedError

    async def random_candidate_count(self, filters: RandomNoteFilters) -> int:
        raise NotImplementedError

    async def random_candidate_at(
        self, filters: RandomNoteFilters, offset: int
    ) -> KnowledgeOpenDescriptor | None:
        raise NotImplementedError


class KnowledgeNavigationService:
    async def hydrate_target(self, target: KnowledgeTarget) -> HydratedKnowledgeTarget:
        raise NotImplementedError

    async def list_bookmarks(
        self, filters: BookmarkFilters, cursor: str | None, limit: int
    ) -> HydratedBookmarkPage:
        raise NotImplementedError

    async def workspace_restore_plan(
        self, workspace_id: str, revision: int
    ) -> WorkspaceRestorePlan:
        raise NotImplementedError

    async def random_note(self, filters: RandomNoteFilters) -> RandomNoteResult:
        raise NotImplementedError
```

`KnowledgeEngineService.resolve_legacy_page(note_id, block_keys)` returns
`KnowledgePageIdentity(document_id: str | None, block_ids: dict[str, str])` and
never raises into a successful legacy page read; unavailable identity hydration
returns `None` and an empty map.

### Frontend

```typescript
export type KnowledgeTarget =
  | { kind: 'document'; documentId: string }
  | { kind: 'block'; documentId: string; blockId: string; sourceRevisionId?: string }
  | { kind: 'search'; query: string; filters: KnowledgeSearchFilters }
  | { kind: 'graph'; rootDocumentId: string | null; filters: KnowledgeGraphFilters; viewport: GraphViewport }
  | { kind: 'workspace'; workspaceId: string }

export interface KnowledgeNavigationState {
  utilityMode: 'sources' | 'bookmarks' | 'workspaces'
  sidebarVisible: boolean
  sidebarWidth: number
  activeBookmarkFolderId: string | null
  bookmarkTags: string[]
  sourceTreeQuery: string
  searchQuery: string
  activeDraftId: string | null
  selectedSpaceIds: string[]
  authorityFilters: Array<'app_owned' | 'external_read_only'>
  metricsVisible: boolean
}

applyNamedWorkspace(document: KnowledgeWorkspaceDocument): boolean
```

The single `applyNamedWorkspace` Zustand action validates the complete document
before one `set` call. It increments the Current Session revision once and does
not clear Overlay drafts.

---

### Task 1: Migration 39 and Strict Navigation Contracts

**Files:**
- Create: `deeper_notebook/database/migrations/39.surrealql`
- Create: `deeper_notebook/database/migrations/39_down.surrealql`
- Create: `deeper_notebook/knowledge_engine/navigation_contracts.py`
- Test: `tests/test_knowledge_navigation_migration.py`
- Test: `tests/test_knowledge_navigation_contracts.py`
- Modify: `tests/test_migration_discovery.py`

**Interfaces:**
- Consumes: authority and capability literals from `deeper_notebook.knowledge_engine.capabilities`; workspace layout nodes from `deeper_notebook.workspace.contracts`.
- Produces: every navigation model named in **Interfaces Locked by This Plan**, `normalize_name(value: str) -> tuple[str, str]`, and `normalize_tags(values: list[str]) -> list[str]`.

- [ ] **Step 1: Write failing migration-boundary tests**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/39.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/39_down.surrealql"


def test_migration_39_defines_only_navigation_metadata_tables():
    sql = UP.read_text(encoding="utf-8")
    for table in (
        "knowledge_bookmark_folder",
        "knowledge_bookmark",
        "named_knowledge_workspace",
        "knowledge_navigation_operation_receipt",
    ):
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    assert "absolute_root" not in sql
    assert "normalized_body" not in sql
    assert "canonical_bytes" not in sql


def test_migration_39_down_removes_only_navigation_metadata():
    sql = DOWN.read_text(encoding="utf-8")
    assert "REMOVE TABLE IF EXISTS knowledge_bookmark;" in sql
    assert "REMOVE TABLE IF EXISTS named_knowledge_workspace;" in sql
    assert "knowledge_engine_document" not in sql
    assert "overlay_note" not in sql
    assert "vault_file" not in sql
```

- [ ] **Step 2: Run the migration tests and verify the expected failure**

Run: `uv run pytest -q tests/test_knowledge_navigation_migration.py tests/test_migration_discovery.py`

Expected: FAIL because migration 39 does not exist and discovery reports only 38 migrations.

- [ ] **Step 3: Add the schema-full migration and exact down boundary**

```surql
DEFINE TABLE IF NOT EXISTS knowledge_bookmark_folder SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE knowledge_bookmark_folder TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS name ON TABLE knowledge_bookmark_folder TYPE string;
DEFINE FIELD IF NOT EXISTS name_key ON TABLE knowledge_bookmark_folder TYPE string;
DEFINE FIELD IF NOT EXISTS parent_folder_id ON TABLE knowledge_bookmark_folder TYPE option<string>;
DEFINE FIELD IF NOT EXISTS position ON TABLE knowledge_bookmark_folder TYPE int ASSERT $value >= 0;
DEFINE FIELD IF NOT EXISTS revision ON TABLE knowledge_bookmark_folder TYPE int ASSERT $value >= 1;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE knowledge_bookmark_folder TYPE datetime;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE knowledge_bookmark_folder TYPE datetime;
DEFINE INDEX IF NOT EXISTS idx_kn_folder_parent_name ON TABLE knowledge_bookmark_folder COLUMNS parent_folder_id, name_key UNIQUE;

DEFINE TABLE IF NOT EXISTS knowledge_bookmark SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE knowledge_bookmark TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS target_kind ON TABLE knowledge_bookmark TYPE string ASSERT $value IN ["document", "block", "search", "graph", "workspace"];
DEFINE FIELD IF NOT EXISTS target ON TABLE knowledge_bookmark FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS display_label ON TABLE knowledge_bookmark TYPE string;
DEFINE FIELD IF NOT EXISTS authority_kind ON TABLE knowledge_bookmark TYPE option<string> ASSERT $value = NONE OR $value IN ["app_owned", "external_read_only"];
DEFINE FIELD IF NOT EXISTS space_id ON TABLE knowledge_bookmark TYPE option<string>;
DEFINE FIELD IF NOT EXISTS folder_id ON TABLE knowledge_bookmark TYPE option<string>;
DEFINE FIELD IF NOT EXISTS tags ON TABLE knowledge_bookmark TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS position ON TABLE knowledge_bookmark TYPE int ASSERT $value >= 0;
DEFINE FIELD IF NOT EXISTS revision ON TABLE knowledge_bookmark TYPE int ASSERT $value >= 1;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE knowledge_bookmark TYPE datetime;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE knowledge_bookmark TYPE datetime;
DEFINE INDEX IF NOT EXISTS idx_kn_bookmark_folder_position ON TABLE knowledge_bookmark COLUMNS folder_id, position, id;

DEFINE TABLE IF NOT EXISTS named_knowledge_workspace SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE named_knowledge_workspace TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS name ON TABLE named_knowledge_workspace TYPE string;
DEFINE FIELD IF NOT EXISTS name_key ON TABLE named_knowledge_workspace TYPE string;
DEFINE FIELD IF NOT EXISTS snapshot_version ON TABLE named_knowledge_workspace TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS snapshot ON TABLE named_knowledge_workspace FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS revision ON TABLE named_knowledge_workspace TYPE int ASSERT $value >= 1;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE named_knowledge_workspace TYPE datetime;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE named_knowledge_workspace TYPE datetime;
DEFINE INDEX IF NOT EXISTS idx_kn_workspace_name ON TABLE named_knowledge_workspace COLUMNS name_key UNIQUE;

DEFINE TABLE IF NOT EXISTS knowledge_navigation_operation_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE knowledge_navigation_operation_receipt TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS operation_id ON TABLE knowledge_navigation_operation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS operation_kind ON TABLE knowledge_navigation_operation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS entity_kind ON TABLE knowledge_navigation_operation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS entity_id ON TABLE knowledge_navigation_operation_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS payload_hash ON TABLE knowledge_navigation_operation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS result_status ON TABLE knowledge_navigation_operation_receipt TYPE string ASSERT $value IN ["succeeded", "conflict"];
DEFINE FIELD IF NOT EXISTS result_revision ON TABLE knowledge_navigation_operation_receipt TYPE option<int>;
DEFINE FIELD IF NOT EXISTS result_code ON TABLE knowledge_navigation_operation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE knowledge_navigation_operation_receipt TYPE datetime;
DEFINE FIELD IF NOT EXISTS completed_at ON TABLE knowledge_navigation_operation_receipt TYPE datetime;
DEFINE INDEX IF NOT EXISTS idx_kn_operation_id ON TABLE knowledge_navigation_operation_receipt COLUMNS operation_id UNIQUE;
```

Put exactly these removals in `39_down.surrealql`, in dependency order:

```surql
REMOVE TABLE IF EXISTS knowledge_bookmark;
REMOVE TABLE IF EXISTS knowledge_bookmark_folder;
REMOVE TABLE IF EXISTS named_knowledge_workspace;
REMOVE TABLE IF EXISTS knowledge_navigation_operation_receipt;
```

- [ ] **Step 4: Write failing strict-contract tests**

```python
import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.navigation_contracts import (
    BlockTarget,
    DocumentTarget,
    NamedWorkspaceSnapshot,
    normalize_name,
    normalize_tags,
)


def test_targets_accept_stable_ids_and_reject_paths():
    assert DocumentTarget(
        kind="document",
        document_id="knowledge_engine_document:plan",
    ).document_id.endswith(":plan")
    with pytest.raises(ValidationError):
        DocumentTarget(kind="document", document_id="/Users/Antman/Plan.md")
    with pytest.raises(ValidationError):
        BlockTarget(
            kind="block",
            document_id="knowledge_engine_document:plan",
            block_id="../block",
        )


def test_name_and_tag_normalization_preserves_first_display_value():
    assert normalize_name("  Research   Desk  ") == (
        "Research Desk",
        "research desk",
    )
    assert normalize_tags([" Research ", "research", "RÉSUMÉ"]) == [
        "Research",
        "RÉSUMÉ",
    ]


def test_snapshot_bounds_are_preflighted():
    payload = {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {
            f"pane-{index}": {"id": f"pane-{index}", "active_tab_id": None, "tabs": []}
            for index in range(33)
        },
        "layout": {"type": "pane", "pane_id": "pane-1"},
        "navigation": {},
    }
    with pytest.raises(ValidationError, match="32 panes"):
        NamedWorkspaceSnapshot.model_validate(payload)
```

- [ ] **Step 5: Add strict navigation contracts and normalizers**

Use discriminated Pydantic models for all five targets. The target fields are
exactly:

```python
class DocumentTarget(_Strict):
    kind: Literal["document"] = "document"
    document_id: KnowledgeDocumentId


class BlockTarget(_Strict):
    kind: Literal["block"] = "block"
    document_id: KnowledgeDocumentId
    block_id: KnowledgeBlockId
    source_revision_id: KnowledgeRevisionId | None = None


class SearchTarget(_Strict):
    kind: Literal["search"] = "search"
    query: str = Field(min_length=1, max_length=512)
    search_mode: Literal["exact", "text", "semantic"] = "text"
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    authority_kinds: list[AuthorityKind] = Field(default_factory=list, max_length=2)
    tags: list[str] = Field(default_factory=list, max_length=32)


class GraphTarget(_Strict):
    kind: Literal["graph"] = "graph"
    root_document_id: KnowledgeDocumentId | None = None
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    relation_kinds: list[str] = Field(default_factory=list, max_length=32)
    viewport: GraphViewport = Field(default_factory=GraphViewport)


class WorkspaceTarget(_Strict):
    kind: Literal["workspace"] = "workspace"
    workspace_id: NamedWorkspaceId
```

Implement `normalize_name` with NFKC, trim, whitespace collapse, and
`casefold()`. Implement `normalize_tags` by retaining the first display string
for each case-folded key. Add strict commands, rows, filters, an opaque cursor,
`BookmarkPage`, `HydratedBookmarkPage`, hydrated target, restore plan, Random
Note result, and operation receipt models required by the locked interfaces.
The bookmark cursor encodes only the last `(folder_id, position, id)` tuple,
uses URL-safe base64 JSON, and is rejected when malformed or longer than 512
characters.

- [ ] **Step 6: Run focused tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_migration.py tests/test_knowledge_navigation_contracts.py tests/test_migration_discovery.py`

Expected: all tests pass.

```bash
git add deeper_notebook/database/migrations/39.surrealql deeper_notebook/database/migrations/39_down.surrealql deeper_notebook/knowledge_engine/navigation_contracts.py tests/test_knowledge_navigation_migration.py tests/test_knowledge_navigation_contracts.py tests/test_migration_discovery.py
git commit -m "feat: define navigation productivity contracts"
```

### Task 2: Transactional Navigation Metadata Repository

**Files:**
- Create: `deeper_notebook/knowledge_engine/navigation_repository.py`
- Test: `tests/test_knowledge_navigation_repository.py`

**Interfaces:**
- Consumes: Task 1 commands and row models; existing `db_connection`, `ensure_record_id`, and `parse_record_ids`.
- Produces: `KnowledgeNavigationRepository` methods locked above and `KnowledgeNavigationRepositoryError(code: str)`.

- [ ] **Step 1: Write failing receipt, revision, folder, and rollback tests**

```python
@pytest.mark.asyncio
async def test_create_bookmark_replays_same_operation_and_rejects_new_payload(
    fake_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    command = create_bookmark_command(operation_id="bookmark-create-1")
    first = await repository.create_bookmark(command)
    replay = await repository.create_bookmark(command)
    assert replay == first
    with pytest.raises(KnowledgeNavigationRepositoryError, match="operation_conflict"):
        await repository.create_bookmark(
            command.model_copy(update={"display_label": "Changed"})
        )


@pytest.mark.asyncio
async def test_update_requires_exact_revision_and_rolls_back_receipt(fake_connection):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    existing = await repository.create_bookmark(create_bookmark_command())
    fake_connection.fail_after_receipt = True
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="repository_unavailable"
    ):
        await repository.update_bookmark(
            existing.id,
            update_bookmark_command(expected_revision=existing.revision),
        )
    assert fake_connection.committed_receipts == []


@pytest.mark.asyncio
async def test_folder_reparent_rejects_cycle_and_depth_seventeen(fake_connection):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    parent = None
    for index in range(16):
        parent = await repository.create_folder(
            create_folder_command(
                name=f"Level {index}", parent_folder_id=parent.id if parent else None
            )
        )
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_depth_exceeded"
    ):
        await repository.create_folder(
            create_folder_command(name="Level 16", parent_folder_id=parent.id)
        )
```

- [ ] **Step 2: Run repository tests and confirm they fail**

Run: `uv run pytest -q tests/test_knowledge_navigation_repository.py`

Expected: FAIL because `navigation_repository` does not exist.

- [ ] **Step 3: Implement stable ID, hash, query, and receipt helpers**

```python
_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")


def _record_id(table: str, value: str):
    pattern = re.compile(rf"^{re.escape(table)}:[A-Za-z0-9_-]+$")
    if pattern.fullmatch(value) is None:
        raise ValueError(f"invalid_{table}_id")
    return ensure_record_id(value)


def _payload_hash(command: BaseModel) -> str:
    payload = command.model_dump(mode="json", exclude={"operation_id"})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _generated_id(table: str, operation_id: str) -> str:
    return f"{table}:{sha256(operation_id.encode()).hexdigest()}"
```

`_query` must scrub database exceptions to
`KnowledgeNavigationRepositoryError("knowledge_navigation_repository_unavailable")`.
Do not interpolate caller data into SurrealQL.

- [ ] **Step 4: Implement one-transaction CRUD and replay semantics**

Each mutation transaction must:

```surql
BEGIN TRANSACTION;
LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id LIMIT 1);
IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {
    THROW 'operation_conflict';
};
IF array::len($prior) = 0 {
    CREATE $receipt_id CONTENT $receipt;
    UPSERT $entity_id CONTENT $entity;
};
COMMIT TRANSACTION;
RETURN { prior: $prior, entity: (SELECT * FROM $entity_id LIMIT 1) };
```

Update and delete transactions first compare `revision` with
`expected_revision`. Folder delete applies either `move_children` or
`delete_tree` in the same transaction. The tree policy deletes only folder and
bookmark rows. Receipt rows survive domain-row deletion.

- [ ] **Step 5: Implement deterministic list and Random Note reads**

Folder results order by `parent_folder_id, position, name_key, id`; bookmarks
order by `folder_id, position, id`, return at most `limit` rows plus an opaque
cursor, and never use offset pagination; workspaces order by `name_key, id`.
Random candidates query only documents with:

```surql
availability = "available"
AND parse_state = "ready"
AND document_kind IN ["note", "page", "journal"]
AND "read" IN capabilities
```

Add filters through bound variables, require every requested tag to be present,
and return only the safe open-descriptor fields required by Task 3.

- [ ] **Step 6: Run focused tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_repository.py`

Expected: all tests pass, including injected rollback and replay cases.

```bash
git add deeper_notebook/knowledge_engine/navigation_repository.py tests/test_knowledge_navigation_repository.py
git commit -m "feat: persist navigation productivity metadata"
```

### Task 3: Unified Identity Bridge and Safe Open Descriptors

**Files:**
- Modify: `deeper_notebook/knowledge_engine/repository.py`
- Modify: `deeper_notebook/knowledge_engine/service.py`
- Modify: `deeper_notebook/knowledge_engine/__init__.py`
- Modify: `api/schemas/vault.py`
- Modify: `api/routers/vault.py`
- Modify: `deeper_notebook/overlay/contracts.py`
- Modify: `api/routers/overlay.py`
- Modify: `frontend/src/lib/api/vault.ts`
- Modify: `frontend/src/lib/api/overlay.ts`
- Test: `tests/test_knowledge_navigation_identity.py`
- Modify: `tests/test_knowledge_engine_repository.py`
- Modify: `tests/test_knowledge_engine_service.py`
- Modify: `tests/test_vault_api.py`
- Modify: `tests/test_overlay_api.py`

**Interfaces:**
- Consumes: migration-38 identity rows and current document revisions.
- Produces: `resolve_legacy_page(note_id, block_keys) -> KnowledgePageIdentity`, `open_descriptor(document_id) -> KnowledgeOpenDescriptor`, and optional page wire fields `knowledge_document_id` and `knowledge_block_id`.

- [ ] **Step 1: Write failing current-revision identity tests**

```python
@pytest.mark.asyncio
async def test_resolve_legacy_page_ignores_stale_identity_claims(repository):
    resolved = await repository.resolve_legacy_page(
        legacy_note_id="note:plan",
        block_keys=("heading-parser", "claim-1"),
    )
    assert resolved.document_id == "knowledge_engine_document:current"
    assert resolved.block_ids == {
        "heading-parser": "knowledge_engine_block:heading",
        "claim-1": "knowledge_engine_block:claim",
    }
    assert "knowledge_engine_document:stale" not in resolved.model_dump_json()


@pytest.mark.asyncio
async def test_open_descriptor_contains_safe_logical_hints_only(repository):
    descriptor = await repository.open_descriptor("knowledge_engine_document:current")
    payload = descriptor.model_dump_json()
    assert descriptor.legacy_note_id == "note:plan"
    assert descriptor.legacy_container_id == "vault_mount:fixture"
    assert descriptor.relative_locator == "pages/plan.md"
    assert "/Users/" not in payload
    assert "normalized_body" not in payload
```

- [ ] **Step 2: Implement current-revision identity queries**

Use a query that joins identity claims only through the document's current
`source_revision_id`:

```surql
LET $document_claim = (
    SELECT engine_id, source_revision_id
    FROM knowledge_engine_identity_map
    WHERE legacy_kind = "note" AND legacy_id = $legacy_note_id
    ORDER BY created_at DESC
);
RETURN SELECT * FROM $document_claim
WHERE source_revision_id IN (
    SELECT VALUE source_revision_id FROM knowledge_engine_document
    WHERE id = $parent.engine_id
);
```

Resolve block keys with `legacy_kind = "source_native_block"` and the same
current revision. `open_descriptor` returns stable document/space IDs,
authority, source kind, title, validated relative locator, legacy note ID, and
legacy container ID. It excludes body, properties, source root, and source ref.

- [ ] **Step 3: Add fail-open page identity enrichment**

Add these safe optional fields:

```python
class VaultPageResponse(_VaultSchema):
    knowledge_document_id: str | None = None
    file: VaultFileResponse
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLinkResponse] = Field(default_factory=list)
    backlinks: list[VaultLinkResponse] = Field(default_factory=list)
```

Before returning a page, collect each block's `stable_source_id` or `parser_id`,
call the engine service once, set `knowledge_document_id`, and copy each
resolved `knowledge_block_id` into the response block dictionary. Catch all
identity-bridge failures and return the canonical legacy page with `None` and
no block IDs.

Add matching optional fields with defaults to Overlay page contracts. This
must not change Overlay revision, content hash, storage, or write behavior.

- [ ] **Step 4: Parse the safe IDs in frontend page schemas**

```typescript
const knowledgeDocumentIdSchema = z.string()
  .regex(/^knowledge_engine_document:[A-Za-z0-9_-]+$/)
const knowledgeBlockIdSchema = z.string()
  .regex(/^knowledge_engine_block:[A-Za-z0-9_-]+$/)

export const vaultBlockSchema = z.object({
  knowledge_block_id: knowledgeBlockIdSchema.nullable().optional(),
  markdown: z.string().optional(),
  heading_path: z.array(z.string()).optional(),
  block_kind: z.string().optional(),
  properties: z.record(z.string(), z.unknown()).optional(),
}).passthrough()
```

Add `knowledge_document_id: knowledgeDocumentIdSchema.nullable()` to both page
schemas. Keep all existing absolute-path and authored-content checks.

- [ ] **Step 5: Run identity and compatibility tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_identity.py tests/test_knowledge_engine_repository.py tests/test_knowledge_engine_service.py tests/test_vault_api.py tests/test_overlay_api.py`

Run: `cd frontend && npm test -- --run src/lib/api`

Expected: all tests pass; legacy page tests prove page reads succeed when the
engine is disabled.

```bash
git add deeper_notebook/knowledge_engine api/schemas/vault.py api/routers/vault.py deeper_notebook/overlay/contracts.py api/routers/overlay.py frontend/src/lib/api/vault.ts frontend/src/lib/api/overlay.ts tests/test_knowledge_navigation_identity.py tests/test_knowledge_engine_repository.py tests/test_knowledge_engine_service.py tests/test_vault_api.py tests/test_overlay_api.py
git commit -m "feat: bridge knowledge pages to unified identities"
```

### Task 4: Global Bookmark and Folder Service/API

**Files:**
- Create: `deeper_notebook/knowledge_engine/navigation_service.py`
- Create: `api/schemas/knowledge_navigation.py`
- Create: `api/routers/knowledge_navigation.py`
- Modify: `api/main.py`
- Create: `tests/test_knowledge_navigation_service.py`
- Create: `tests/test_knowledge_navigation_api.py`
- Modify: `tests/test_knowledge_engine_lifespan.py`

**Interfaces:**
- Consumes: Tasks 1-3 contracts, repository, and open descriptors.
- Produces: bookmark/folder route roots and target hydration with `available`, `stale`, `unavailable`, or `missing` state.

- [ ] **Step 1: Write failing hydration and API contract tests**

```python
@pytest.mark.asyncio
async def test_bookmark_collection_keeps_unavailable_metadata(service):
    service.engine_repository = UnavailableEngineRepository()
    page = await service.list_bookmarks(BookmarkFilters(), cursor=None, limit=50)
    assert page.items[0].display_label == "Research plan"
    assert page.items[0].target_state == "unavailable"


@pytest.mark.asyncio
async def test_create_bookmark_is_revisioned_and_redacted(api_client):
    response = await api_client.post(
        "/api/deeper-notebook/knowledge/bookmarks",
        json={
            "operation_id": "bookmark-create-api-1",
            "target": {
                "kind": "document",
                "document_id": "knowledge_engine_document:plan",
            },
            "display_label": "Research plan",
            "folder_id": None,
            "tags": ["Research"],
            "position": 0,
        },
    )
    assert response.status_code == 201
    assert response.json()["revision"] == 1
    assert "/Users/" not in response.text
    assert "normalized_body" not in response.text
```

- [ ] **Step 2: Implement target hydration and folder policy**

`hydrate_target` behavior is exact:

```python
async def hydrate_target(self, target: KnowledgeTarget) -> HydratedKnowledgeTarget:
    try:
        if target.kind == "document":
            return await self._hydrate_document(target)
        if target.kind == "block":
            return await self._hydrate_block(target)
        if target.kind == "search":
            return HydratedKnowledgeTarget(target=target, state="available")
        if target.kind == "graph":
            return await self._hydrate_graph(target)
        return await self._hydrate_workspace(target)
    except LookupError:
        return HydratedKnowledgeTarget(target=target, state="missing")
    except KnowledgeNavigationRepositoryError:
        return HydratedKnowledgeTarget(target=target, state="unavailable")
```

A block is stale when its document resolves but its block or revision hint does
not match. A rooted graph is stale when its root is stale; a global graph is
available. Search descriptors are available after strict validation because
they contain no source identity.

- [ ] **Step 3: Add strict wire models and canonical routes**

Register the router at prefix `/api/deeper-notebook/knowledge`. Implement:

```text
GET    /bookmarks
POST   /bookmarks
PATCH  /bookmarks/{bookmark_id}
DELETE /bookmarks/{bookmark_id}
GET    /bookmark-folders
POST   /bookmark-folders
PATCH  /bookmark-folders/{folder_id}
DELETE /bookmark-folders/{folder_id}
```

`GET /bookmarks` accepts `cursor` and `limit` from 1 through 100. It returns
`items` and `next_cursor`; cursor fields are opaque to clients. Folder-tree
responses are bounded by the stored depth and collection limits.

Use a bounded request route with a 1 MiB JSON limit. Map not found to 404,
revision/name/operation conflict to 409, strict validation to 422, and metadata
repository failure to 503. Never include exception text.

- [ ] **Step 4: Wire runtime ownership without changing engine defaults**

Create `KnowledgeNavigationService` unconditionally with its metadata
repository. Pass the optional engine service/repository when the unified engine
is enabled. Clear `app.state.knowledge_navigation_service` on lifespan exit.
Metadata lists remain available when hydration is not; Random Note later maps
engine absence to 503.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_engine_lifespan.py`

Expected: all tests pass and the OpenAPI route audit finds only canonical
Deeper Notebook paths.

```bash
git add deeper_notebook/knowledge_engine/navigation_service.py api/schemas/knowledge_navigation.py api/routers/knowledge_navigation.py api/main.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_engine_lifespan.py
git commit -m "feat: expose global knowledge bookmarks"
```

### Task 5: Revisioned Named Workspace Snapshots and Restore Plans

**Files:**
- Modify: `deeper_notebook/knowledge_engine/navigation_service.py`
- Modify: `api/schemas/knowledge_navigation.py`
- Modify: `api/routers/knowledge_navigation.py`
- Modify: `deeper_notebook/workspace/contracts.py`
- Modify: `tests/test_knowledge_navigation_service.py`
- Modify: `tests/test_knowledge_navigation_api.py`
- Modify: `tests/test_knowledge_workspace_api.py`
- Modify: `tests/test_knowledge_workspace_persistence.py`

**Interfaces:**
- Consumes: named snapshot contracts and safe open descriptors.
- Produces: named workspace CRUD and a non-mutating `WorkspaceRestorePlan`.

- [ ] **Step 1: Write failing snapshot revision and restore tests**

```python
@pytest.mark.asyncio
async def test_restore_plan_hydrates_every_target_without_mutating_current_session(
    service, current_session_path
):
    before = current_session_path.read_bytes()
    plan = await service.workspace_restore_plan("named_knowledge_workspace:desk", 3)
    assert plan.workspace_id == "named_knowledge_workspace:desk"
    assert plan.revision == 3
    assert plan.summary == {"available": 2, "stale": 1, "unavailable": 0, "missing": 0}
    assert current_session_path.read_bytes() == before


@pytest.mark.asyncio
async def test_restore_revision_conflict_returns_409_and_no_snapshot(api_client):
    response = await api_client.post(
        "/api/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk/restore-plan",
        json={"revision": 2},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "knowledge_workspace_revision_conflict"}
    }
```

- [ ] **Step 2: Extend Current Session with backward-compatible navigation defaults**

Add this field to `KnowledgeWorkspaceDocument` without changing `version: 1`:

```python
class KnowledgeWorkspaceNavigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utility_mode: Literal["sources", "bookmarks", "workspaces"] = "sources"
    sidebar_visible: bool = True
    sidebar_width: int = Field(default=320, ge=240, le=640)
    active_bookmark_folder_id: str | None = Field(default=None, max_length=128)
    bookmark_tags: list[str] = Field(default_factory=list, max_length=32)
    source_tree_query: str = Field(default="", max_length=256)
    search_query: str = Field(default="", max_length=512)
    active_draft_id: str | None = Field(default=None, max_length=128)
    selected_space_ids: list[str] = Field(default_factory=list, max_length=32)
    authority_filters: list[Literal["app_owned", "external_read_only"]] = Field(
        default_factory=list, max_length=2
    )
    metrics_visible: bool = True


class KnowledgeWorkspaceDocument(BaseModel):
    version: Literal[1] = 1
    active_pane_id: str
    next_id: int
    panes: dict[str, KnowledgePaneState]
    layout: KnowledgeLayoutNode
    navigation: KnowledgeWorkspaceNavigation = Field(
        default_factory=KnowledgeWorkspaceNavigation
    )
```

Add `knowledge_document_id: str | None = None` and
`graph_viewport: GraphViewport | None = None` to `KnowledgeTabState`. Add
`first_size: float = Field(default=50.0, ge=10.0, le=90.0)` to
`SplitLayoutNode`. These defaults preserve existing version-1 Current Session
files. The second panel size is always `100 - first_size` and is not stored
separately.

Old Current Session JSON without `navigation` must load with defaults. Existing
absolute-path, pane, tab, and layout validators remain unchanged.

- [ ] **Step 3: Implement named workspace service behavior**

Save validates that every document or block tab has a stable unified target.
Rename changes only name fields. Replace creates a new immutable snapshot
revision. Duplicate creates a new ID at revision 1. Delete removes only named
metadata. `workspace_restore_plan` validates the requested revision, hydrates
all targets, preserves pane/tab order, and returns safe open descriptors plus
summary counts.

The service must not import or call Current Session persistence functions.

- [ ] **Step 4: Add canonical workspace routes**

```text
GET    /workspaces
POST   /workspaces
GET    /workspaces/{workspace_id}
POST   /workspaces/{workspace_id}/restore-plan
PATCH  /workspaces/{workspace_id}
POST   /workspaces/{workspace_id}/duplicate
DELETE /workspaces/{workspace_id}
```

List responses exclude the full snapshot. Get and restore-plan include the
bounded snapshot or hydrated plan. Restore-plan accepts only `revision` and has
no state-changing code path.

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_workspace_api.py tests/test_knowledge_workspace_persistence.py`

Expected: all tests pass, including loading a pre-navigation Current Session.

```bash
git add deeper_notebook/knowledge_engine/navigation_service.py api/schemas/knowledge_navigation.py api/routers/knowledge_navigation.py deeper_notebook/workspace/contracts.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_workspace_api.py tests/test_knowledge_workspace_persistence.py
git commit -m "feat: add named knowledge workspace snapshots"
```

### Task 6: Filtered Random Note

**Files:**
- Modify: `deeper_notebook/knowledge_engine/navigation_service.py`
- Modify: `api/schemas/knowledge_navigation.py`
- Modify: `api/routers/knowledge_navigation.py`
- Modify: `tests/test_knowledge_navigation_repository.py`
- Modify: `tests/test_knowledge_navigation_service.py`
- Modify: `tests/test_knowledge_navigation_api.py`

**Interfaces:**
- Consumes: repository candidate count/read and safe open descriptors.
- Produces: `POST /api/deeper-notebook/knowledge/random-note` with `selected` or `empty` state.

- [ ] **Step 1: Write failing eligibility, determinism, and cache tests**

```python
@pytest.mark.asyncio
async def test_random_note_uses_injected_selector_and_all_filters(repository):
    service = KnowledgeNavigationService(
        repository=repository,
        random_index=lambda count: count - 1,
    )
    result = await service.random_note(
        RandomNoteFilters(
            space_ids=["knowledge_engine_space:research"],
            authority_kinds=["external_read_only"],
            tags=["Evidence"],
        )
    )
    assert result.state == "selected"
    assert result.document.document_id == "knowledge_engine_document:last"


@pytest.mark.asyncio
async def test_random_note_empty_is_200_and_no_store(api_client):
    response = await api_client.post(
        "/api/deeper-notebook/knowledge/random-note",
        json={"space_ids": [], "authority_kinds": [], "tags": ["missing"]},
    )
    assert response.status_code == 200
    assert response.json() == {"state": "empty", "document": None}
    assert response.headers["cache-control"] == "no-store"
```

- [ ] **Step 2: Implement bounded candidate selection**

```python
async def random_note(self, filters: RandomNoteFilters) -> RandomNoteResult:
    count = await self._repository.random_candidate_count(filters)
    if count == 0:
        return RandomNoteResult(state="empty", document=None)
    offset = self._random_index(count)
    if isinstance(offset, bool) or not 0 <= offset < count:
        raise KnowledgeNavigationServiceError("random_selector_invalid")
    document = await self._repository.random_candidate_at(filters, offset)
    if document is None:
        count = await self._repository.random_candidate_count(filters)
        if count == 0:
            return RandomNoteResult(state="empty", document=None)
        document = await self._repository.random_candidate_at(
            filters, min(offset, count - 1)
        )
    if document is None:
        raise KnowledgeNavigationServiceError("knowledge_engine_unavailable")
    return RandomNoteResult(state="selected", document=document)
```

The default selector is `secrets.randbelow`. The public request model has no
seed or offset.

- [ ] **Step 3: Add POST route and stable errors**

Return 503 when unified projections are unavailable, 422 for filter bounds, and
200 empty for no matches. Set `Cache-Control: no-store` on every 200 response.

- [ ] **Step 4: Run focused tests and commit**

Run: `uv run pytest -q tests/test_knowledge_navigation_repository.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py`

Expected: all tests pass.

```bash
git add deeper_notebook/knowledge_engine/navigation_service.py api/schemas/knowledge_navigation.py api/routers/knowledge_navigation.py tests/test_knowledge_navigation_repository.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py
git commit -m "feat: add filtered random note navigation"
```

### Task 7: Frontend Contracts, API Hooks, and Atomic Workspace State

**Files:**
- Create: `frontend/src/lib/api/knowledge-navigation.ts`
- Create: `frontend/src/lib/api/knowledge-navigation.test.ts`
- Create: `frontend/src/lib/hooks/use-knowledge-navigation.ts`
- Create: `frontend/src/lib/hooks/use-knowledge-navigation.test.tsx`
- Modify: `frontend/src/lib/api/knowledge-workspace.ts`
- Modify: `frontend/src/lib/api/knowledge-workspace.test.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.test.ts`
- Modify: `frontend/src/lib/hooks/use-knowledge-workspace.ts`
- Modify: `frontend/src/lib/hooks/use-knowledge-workspace.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx`
- Modify: `frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx`
- Modify: `frontend/src/components/vault/VaultGraph.tsx`

**Interfaces:**
- Consumes: Task 4-6 wire contracts.
- Produces: strict camel/wire target conversion, query/mutation hooks, Current Session navigation persistence, and atomic named restore.

- [ ] **Step 1: Write failing strict parsing and atomicity tests**

```typescript
it('rejects absolute paths and unknown target fields', () => {
  expect(() => parseBookmark({
    id: 'knowledge_bookmark:one',
    target: {
      kind: 'document',
      document_id: 'knowledge_engine_document:one',
      root_path: '/Users/Antman/private',
    },
    display_label: 'One',
    target_state: 'available',
    tags: [],
    folder_id: null,
    position: 0,
    revision: 1,
  })).toThrow()
})

it('applies a named workspace in one revision and preserves drafts', () => {
  seedWorkspaceWithDraft()
  const before = useKnowledgeWorkspaceStore.getState().revision
  const applied = useKnowledgeWorkspaceStore.getState().applyNamedWorkspace(namedDocument())
  expect(applied).toBe(true)
  expect(useKnowledgeWorkspaceStore.getState().revision).toBe(before + 1)
  expect(useOverlayDraftStore.getState().drafts).toHaveProperty('pane-1:tab-1')
})

it('leaves current state unchanged when named workspace validation fails', () => {
  const before = useKnowledgeWorkspaceStore.getState()
  expect(useKnowledgeWorkspaceStore.getState().applyNamedWorkspace(invalidDocument())).toBe(false)
  expect(useKnowledgeWorkspaceStore.getState()).toMatchObject(before)
})
```

- [ ] **Step 2: Implement strict Zod wire contracts**

Create discriminated target schemas and strict bookmark, folder, workspace,
restore-plan, and Random Note schemas. Run `assertNoAbsolutePath` over all
structural fields before Zod parsing. Export exact API methods:

```typescript
export const knowledgeNavigationApi = {
  listBookmarks,
  createBookmark,
  updateBookmark,
  deleteBookmark,
  listFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  listWorkspaces,
  createWorkspace,
  getWorkspace,
  updateWorkspace,
  duplicateWorkspace,
  deleteWorkspace,
  restorePlan,
  randomNote,
}
```

Every mutation creates `operationId` with `crypto.randomUUID()` at the UI event
boundary and passes the same value through retries.

- [ ] **Step 3: Extend Current Session serialization**

Add `navigation` to wire and camel schemas with defaults matching Task 5. Add
optional `knowledgeDocumentId` to current tab state:

```typescript
export interface KnowledgeTab {
  id: string
  vaultId: string
  noteId: string
  knowledgeDocumentId: string | null
  graphViewport: GraphViewport | null
  title: string
  relativePath: string
  viewMode: KnowledgeViewMode
  sourceAuthority: KnowledgeSourceAuthority
}
```

Old wire documents without `navigation` or `knowledge_document_id` parse with
defaults. Serialization emits both safe fields and retains the existing
absolute-path rejection.

Add `firstSize` to split layout nodes, `graphViewport` to tabs, and exact store
actions `setSplitSize(splitId, firstSize)` and
`setTabGraphViewport(paneId, tabId, viewport)`. `KnowledgeWorkspaceLayout`
persists `sizes[0]` from `ResizablePanelGroup.onLayout`; `VaultGraph` accepts a
controlled viewport and reports `onMoveEnd`. Existing version-1 documents
without either field use 50 percent and `{ x: 0, y: 0, zoom: 1 }`.

- [ ] **Step 4: Add navigation actions and atomic named apply**

Add setters for utility mode, active folder, filters, sidebar, active draft ID,
split size, graph viewport, and metrics.
`applyNamedWorkspace` must call `serializeKnowledgeWorkspace` before a single
`set` and must not call `resetOverlayDraftStore`:

```typescript
applyNamedWorkspace: (document) => {
  try {
    serializeKnowledgeWorkspace(document)
  } catch {
    return false
  }
  const state = get()
  set({
    ...document,
    hydrated: true,
    revision: state.revision + 1,
    durableRevision: state.durableRevision,
    durableFingerprint: state.durableFingerprint,
  })
  return true
},
```

- [ ] **Step 5: Add TanStack Query keys and hooks**

Use stable keys rooted at `['knowledge-navigation']`. Mutations invalidate only
the relevant bookmark/folder/workspace collections. Restore-plan and Random
Note are explicit mutations and do not run on mount.

- [ ] **Step 6: Run focused frontend tests and commit**

Run: `cd frontend && npm test -- --run src/lib/api/knowledge-workspace.test.ts src/lib/stores/knowledge-workspace-store.test.ts src/lib/hooks/use-knowledge-workspace.test.tsx src/lib/api/knowledge-navigation.test.ts src/lib/hooks/use-knowledge-navigation.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx`

Expected: all tests pass.

```bash
git add frontend/src/lib/api/knowledge-navigation.ts frontend/src/lib/api/knowledge-navigation.test.ts frontend/src/lib/hooks/use-knowledge-navigation.ts frontend/src/lib/hooks/use-knowledge-navigation.test.tsx frontend/src/lib/api/knowledge-workspace.ts frontend/src/lib/api/knowledge-workspace.test.ts frontend/src/lib/stores/knowledge-workspace-store.ts frontend/src/lib/stores/knowledge-workspace-store.test.ts frontend/src/lib/hooks/use-knowledge-workspace.ts frontend/src/lib/hooks/use-knowledge-workspace.test.tsx frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx frontend/src/components/vault/VaultGraph.tsx
git commit -m "feat: add navigation productivity client state"
```

### Task 8: Unicode Document and Selection Metrics

**Files:**
- Create: `frontend/src/lib/knowledge/document-metrics.ts`
- Create: `frontend/src/lib/knowledge/document-metrics.test.ts`
- Create: `frontend/src/components/vault/DocumentMetricsFooter.tsx`
- Create: `frontend/src/components/vault/DocumentMetricsFooter.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgePaneContent.tsx`
- Modify: `frontend/src/components/vault/KnowledgePaneContent.test.tsx`
- Modify: `frontend/src/components/overlay/OverlayDocumentView.tsx`
- Modify: `frontend/src/components/overlay/OverlayDocumentView.test.tsx`

**Interfaces:**
- Consumes: active Markdown buffer and current selection inside the active pane.
- Produces: `documentMetrics(text: string, segmenter?: WordSegmenter) -> DocumentMetrics` and one shared footer.

- [ ] **Step 1: Write failing Unicode fixture tests**

```typescript
it.each([
  ['hello world', 2, 11, 10],
  ['你好世界', 2, 4, 4],
  ['cafe\u0301 ☕', 1, 7, 6],
  ['', 0, 0, 0],
])('counts %s deterministically', (text, words, characters, noWhitespace) => {
  expect(documentMetrics(text)).toMatchObject({
    words,
    characters,
    charactersWithoutWhitespace: noWhitespace,
    readingMinutes: words === 0 ? 0 : 1,
  })
})

it('counts Unicode code points rather than UTF-16 units', () => {
  expect(documentMetrics('🧠').characters).toBe(1)
})
```

- [ ] **Step 2: Implement the pure metrics function and fallback**

```typescript
export function documentMetrics(text: string): DocumentMetrics {
  const characters = Array.from(text)
  const withoutWhitespace = characters.filter(character => !/\s/u.test(character))
  const segmenter = typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter('und', { granularity: 'word' })
    : null
  const words = segmenter
    ? Array.from(segmenter.segment(text)).filter(segment => segment.isWordLike).length
    : (text.match(/[\p{Letter}\p{Number}\p{Mark}]+/gu) ?? []).length
  return {
    words,
    characters: characters.length,
    charactersWithoutWhitespace: withoutWhitespace.length,
    readingMinutes: words === 0 ? 0 : Math.ceil(words / 200),
  }
}
```

- [ ] **Step 3: Build the accessible stable footer**

The footer accepts `text`, `selectionText`, `visible`, and localized labels. It
uses a fixed-height flex row, `role="status"`, `aria-live="polite"`, and renders
document counts plus selection counts when selection is non-empty.

- [ ] **Step 4: Feed current text and scoped selection from the pane**

`KnowledgePaneContent` owns the metrics footer. External Markdown comes from
the loaded vault page. Overlay starts from `editable_markdown`; add
`onMarkdownChange?: (markdown: string) => void` to `OverlayDocumentView` and
invoke it from the existing `changeDraft` function and page-adoption path.

Listen to `document.selectionchange`, but accept selection text only when both
selection endpoints are contained by the current pane section. Graph mode uses
the root document buffer; an absent root uses empty text.

- [ ] **Step 5: Run focused tests and commit**

Run: `cd frontend && npm test -- --run src/lib/knowledge/document-metrics.test.ts src/components/vault/DocumentMetricsFooter.test.tsx src/components/vault/KnowledgePaneContent.test.tsx src/components/overlay/OverlayDocumentView.test.tsx`

Expected: all tests pass with no mode-dependent count changes.

```bash
git add frontend/src/lib/knowledge/document-metrics.ts frontend/src/lib/knowledge/document-metrics.test.ts frontend/src/components/vault/DocumentMetricsFooter.tsx frontend/src/components/vault/DocumentMetricsFooter.test.tsx frontend/src/components/vault/KnowledgePaneContent.tsx frontend/src/components/vault/KnowledgePaneContent.test.tsx frontend/src/components/overlay/OverlayDocumentView.tsx frontend/src/components/overlay/OverlayDocumentView.test.tsx
git commit -m "feat: add Unicode document metrics"
```

### Task 9: Integrated Utility Rail and Bookmark Library UI

**Files:**
- Create: `frontend/src/components/vault/KnowledgeUtilityRail.tsx`
- Create: `frontend/src/components/vault/KnowledgeUtilityRail.test.tsx`
- Create: `frontend/src/components/vault/KnowledgeBookmarksPanel.tsx`
- Create: `frontend/src/components/vault/KnowledgeBookmarksPanel.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeQuickSwitcher.tsx`
- Modify: `frontend/src/components/vault/KnowledgeQuickSwitcher.test.tsx`
- Modify: `frontend/src/components/vault/VaultGraph.tsx`

**Interfaces:**
- Consumes: Task 7 hooks/store and existing `openTab` action.
- Produces: selected Integrated Utility Rail, folder/tag library, target repair/delete controls, and path-free open actions.

- [ ] **Step 1: Write failing context-preservation and authority tests**

```typescript
it('switches to bookmarks without replacing the active document', async () => {
  renderKnowledgeExplorer()
  const activeBefore = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId
  await userEvent.click(screen.getByRole('button', { name: 'Bookmarks' }))
  expect(screen.getByRole('navigation', { name: 'Bookmarks' })).toBeVisible()
  expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(activeBefore)
})

it('shows external target authority while keeping bookmark metadata editable', () => {
  renderBookmarks([externalBookmark()])
  expect(screen.getByText('External read-only')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Edit bookmark Research plan' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: /edit source/iu })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Build the compact rail controls**

Render Today, Bookmarks, Random Note, and Workspaces above a three-mode Sources,
Bookmarks, Workspaces switch. Today calls the existing Overlay daily action.
Random Note calls the Task 7 mutation and opens only the returned safe open
descriptor through `openTab`.

- [ ] **Step 3: Build bookmark folder/tag/state UI**

The bookmark panel renders the validated folder tree, tag chips, target-type
icon, authority badge, and state badge. Available targets open through typed
dispatch. Stale, unavailable, and missing targets expose Edit Target and Delete
only. Folder deletion presents the exact `move_children` and `delete_tree`
policies before sending a command.

- [ ] **Step 4: Build active-target bookmark creation**

Create descriptors only when the active page exposes
`knowledge_document_id`. Match a focused heading or block to the page block's
`knowledge_block_id`; otherwise bookmark the document. `KnowledgeQuickSwitcher`
exposes a keyboard-reachable **Bookmark search for {query}** action that records
the current exact, text, or semantic mode without replacing the active
document. `VaultGraph` supplies the current root document, filters, and
controlled viewport. Disable Bookmark Current Target with an unavailable
explanation when the unified ID is absent.

- [ ] **Step 5: Integrate the rail without changing pane layout**

Replace the current always-visible Overlay utility/file-tree stack with the
rail plus conditional panel. Keep the existing mount selector, file tree, scan
status, and Overlay note actions inside Sources mode. Use a keyboard-operable
horizontal resize handle and `ResizeObserver` to persist the clamped 240-640px
sidebar width; add a collapse/restore control for `sidebarVisible`. Do not move
the main pane or links inspector.

- [ ] **Step 6: Run focused tests and commit**

Run: `cd frontend && npm test -- --run src/components/vault/KnowledgeUtilityRail.test.tsx src/components/vault/KnowledgeBookmarksPanel.test.tsx src/components/vault/KnowledgeExplorer.test.tsx src/components/vault/KnowledgeQuickSwitcher.test.tsx`

Expected: all tests pass, including active-document and focus preservation.

```bash
git add frontend/src/components/vault/KnowledgeUtilityRail.tsx frontend/src/components/vault/KnowledgeUtilityRail.test.tsx frontend/src/components/vault/KnowledgeBookmarksPanel.tsx frontend/src/components/vault/KnowledgeBookmarksPanel.test.tsx frontend/src/components/vault/KnowledgeExplorer.tsx frontend/src/components/vault/KnowledgeExplorer.test.tsx frontend/src/components/vault/KnowledgeQuickSwitcher.tsx frontend/src/components/vault/KnowledgeQuickSwitcher.test.tsx frontend/src/components/vault/VaultGraph.tsx
git commit -m "feat: add integrated bookmark utility rail"
```

### Task 10: Named Workspace UI and Atomic Restore Confirmation

**Files:**
- Create: `frontend/src/components/vault/KnowledgeWorkspacesPanel.tsx`
- Create: `frontend/src/components/vault/KnowledgeWorkspacesPanel.test.tsx`
- Create: `frontend/src/components/vault/WorkspaceRestoreDialog.tsx`
- Create: `frontend/src/components/vault/WorkspaceRestoreDialog.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- Modify: `frontend/src/lib/api/knowledge-workspace.ts`

**Interfaces:**
- Consumes: Task 7 workspace hooks and `applyNamedWorkspace`.
- Produces: Save Current As, Open, Rename, Duplicate, Replace With Current, Delete, and Open Available/Cancel behavior.

- [ ] **Step 1: Write failing restore and conflict tests**

```typescript
it('does not apply a stale restore plan before confirmation', async () => {
  renderWorkspaces({ restorePlan: stalePlan() })
  const before = serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState())
  await userEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))
  expect(screen.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible()
  expect(serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState())).toEqual(before)
})

it('applies available targets once and resumes Current Session autosave', async () => {
  renderWorkspaces({ restorePlan: stalePlan() })
  await userEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))
  await userEvent.click(screen.getByRole('button', { name: 'Open available' }))
  expect(useKnowledgeWorkspaceStore.getState().revision).toBe(1)
  await expectWorkspacePersistenceToReceive('knowledge_engine_document:plan')
})
```

- [ ] **Step 2: Serialize the current store to a stable named snapshot**

For every open tab lacking `knowledgeDocumentId`, fetch its existing vault or
Overlay page once and read the Task 3 identity bridge. Abort Save Current As
with a visible engine-unavailable message if any tab remains unresolved. Convert
resolved tabs to stable document/block/search/graph descriptors and exclude
legacy note IDs and relative paths from the named snapshot payload.

- [ ] **Step 3: Implement named workspace actions**

List Current Session separately from named snapshots. Rename, duplicate,
replace, and delete send exact revisions. On 409, keep the dialog open, show a
conflict message, refetch metadata, and leave the current store unchanged.

- [ ] **Step 4: Implement two-step restore**

Request the restore plan at the listed revision. If every target is available,
convert safe open descriptors to the existing tab hints and call
`applyNamedWorkspace` once. If any target is stale, unavailable, or missing,
show summary rows; Open Available omits those tabs while retaining valid panes,
and Cancel changes nothing. If omission empties a pane, keep the pane with no
active tab so layout validation remains valid.

- [ ] **Step 5: Run focused tests and commit**

Run: `cd frontend && npm test -- --run src/components/vault/KnowledgeWorkspacesPanel.test.tsx src/components/vault/WorkspaceRestoreDialog.test.tsx src/components/vault/KnowledgeExplorer.test.tsx src/lib/stores/knowledge-workspace-store.test.ts`

Expected: all tests pass and no failed/canceled restore increments revision.

```bash
git add frontend/src/components/vault/KnowledgeWorkspacesPanel.tsx frontend/src/components/vault/KnowledgeWorkspacesPanel.test.tsx frontend/src/components/vault/WorkspaceRestoreDialog.tsx frontend/src/components/vault/WorkspaceRestoreDialog.test.tsx frontend/src/components/vault/KnowledgeExplorer.tsx frontend/src/components/vault/KnowledgeExplorer.test.tsx frontend/src/lib/api/knowledge-workspace.ts
git commit -m "feat: add named workspace restore UI"
```

### Task 11: Command, Slash, Accessibility, Localization, and Mocked Browser Parity

**Files:**
- Modify: `frontend/src/lib/commands/command-registry.ts`
- Modify: `frontend/src/lib/commands/command-registry.test.ts`
- Modify: `frontend/src/lib/commands/knowledge-command-context-store.ts`
- Modify: `frontend/src/lib/commands/knowledge-command-context-store.test.ts`
- Modify: `frontend/src/components/vault/KnowledgeCommandBridge.tsx`
- Modify: `frontend/src/components/vault/KnowledgeCommandBridge.test.tsx`
- Modify: every `frontend/src/lib/locales/*/index.ts`
- Modify: `frontend/src/lib/locales/index.test.ts`
- Modify: `frontend/e2e/fixtures/knowledge-editor-modes.ts`
- Create: `frontend/e2e/knowledge-navigation-productivity.spec.ts`

**Interfaces:**
- Consumes: UI callbacks from Tasks 8-10.
- Produces: command/pointer parity, locale parity, keyboard/focus proof, and mocked restart flows.

- [ ] **Step 1: Write failing command registry tests**

```typescript
it.each([
  'knowledge.bookmark-current',
  'knowledge.open-bookmarks',
  'knowledge.random-note',
  'knowledge.open-workspaces',
  'knowledge.save-workspace-as',
  'knowledge.replace-workspace',
  'knowledge.toggle-metrics',
] as const)('registers %s as a non-external-write command', id => {
  const command = knowledgeCommandDefinitions.find(candidate => candidate.id === id)
  expect(command).toBeDefined()
  expect(command?.safety).not.toBe('external-write')
})
```

- [ ] **Step 2: Add exact command callbacks and definitions**

Extend the page context with `bookmarkCurrentTarget`, `openBookmarks`,
`randomNote`, `openWorkspaces`, `saveWorkspaceAs`, `replaceWorkspace`, and
`toggleMetrics`. Register the seven IDs above. Commands call the same callbacks
as rail buttons and remain available in slash mode because none has
`external-write` safety.

- [ ] **Step 3: Add locale keys to every supported bundle**

Add non-empty translations for these exact nested keys:

```typescript
knowledge.navigation = {
  sources: 'Sources',
  bookmarks: 'Bookmarks',
  randomNote: 'Random Note',
  workspaces: 'Workspaces',
  currentSession: 'Current Session',
  saveCurrentAs: 'Save Current As',
  replaceWithCurrent: 'Replace With Current',
  openAvailable: 'Open available',
  targetAvailable: 'Available',
  targetStale: 'Stale',
  targetUnavailable: 'Unavailable',
  targetMissing: 'Missing',
  appOwned: 'App-owned',
  externalReadOnly: 'External read-only',
  words: '{{count}} words',
  characters: '{{count}} characters',
  readingMinutes: '{{count}} min read',
  selectionMetrics: 'Selection: {{words}} words, {{characters}} characters',
}
```

The English values above are exact. Each non-English bundle must contain a
native translation with the same interpolation variables. Extend locale tests
to enumerate the keys and reject empty values, missing variables, and fallback
to raw English in non-English bundles.

- [ ] **Step 4: Extend mocked route fixture and write browser flows**

The fixture owns in-memory bookmark, folder, named-workspace, operation-receipt,
and Random Note state. Add Playwright flows proving:

```typescript
test('bookmark random note metrics and named workspace survive mocked restart', async ({ page }) => {
  const state = initialKnowledgeFixtureState()
  await installKnowledgeRoutes(page, state, [], [])
  await page.goto('/knowledge')
  await page.getByRole('button', { name: 'Bookmarks' }).click()
  await page.getByRole('button', { name: 'Bookmark current target' }).click()
  await expect(page.getByRole('navigation', { name: 'Bookmarks' })).toContainText('Plan')
  await page.getByRole('button', { name: 'Random Note' }).click()
  await expect(page.getByRole('tab', { name: 'Evidence' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('status', { name: 'Document metrics' })).toContainText('words')
  await page.getByRole('button', { name: 'Workspaces' }).click()
  await page.getByRole('button', { name: 'Save Current As' }).click()
  await page.getByLabel('Workspace name').fill('Research desk')
  await page.getByRole('button', { name: 'Save workspace' }).click()
  await page.reload()
  await page.getByRole('button', { name: 'Workspaces' }).click()
  await expect(page.getByText('Research desk', { exact: true })).toBeVisible()
})
```

Also prove stale confirmation, revision conflict, keyboard operation, focus
return, no external mutation requests, and no unexpected API traffic.

- [ ] **Step 5: Run frontend quality gates and commit**

Run serially:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run test:e2e:mocked -- knowledge-navigation-productivity.spec.ts
npm run build
```

Expected: every command, locale, unit, accessibility, browser, lint, typecheck,
and build gate passes.

```bash
git add frontend/src/lib/commands frontend/src/components/vault/KnowledgeCommandBridge.tsx frontend/src/components/vault/KnowledgeCommandBridge.test.tsx frontend/src/lib/locales frontend/e2e/fixtures/knowledge-editor-modes.ts frontend/e2e/knowledge-navigation-productivity.spec.ts
git commit -m "test: prove navigation productivity parity"
```

### Task 12: Persistent Synthetic Runtime Proof and Completion Record

**Files:**
- Create: `scripts/verify_navigation_productivity.py`
- Create: `tests/test_verify_navigation_productivity.py`
- Create: `tests/integration/test_knowledge_navigation_persistence.py`
- Create: `docs/verification/2026-07-31-deeper-notebook-navigation-productivity.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one deterministic JSON proof report and a committed evidence record separating mock, API, SurrealDB, and native gates.

- [ ] **Step 1: Write failing verifier contract tests**

```python
def test_verifier_requires_persistent_api_and_surreal_runtime(tmp_path):
    result = run_verifier(
        api_url="http://127.0.0.1:9",
        fixture_root=tmp_path,
        output_path=tmp_path / "proof.json",
    )
    assert result.exit_code != 0
    assert result.report["status"] == "blocked"
    assert result.report["external_writes"] == 0


def test_verifier_rejects_real_second_brain_roots(tmp_path):
    with pytest.raises(ValueError, match="fixture root required"):
        verifier_config(
            fixture_root=Path("/Users/Antman/Desktop/2nd Brains"),
            output_path=tmp_path / "proof.json",
        )
```

- [ ] **Step 2: Implement the synthetic verifier**

The verifier creates a temporary Obsidian fixture, a temporary Logseq fixture,
and app-owned Overlay notes; records source hashes; waits for a caller-launched
persistent native API plus SurrealDB; then proves migration 39, bookmarks,
folder nesting, target hydration, idempotent replay, conflict behavior, Random
Note filters, named-workspace restore plans, restart persistence, backlinks,
graph, search, and unchanged source hashes.

It writes only a redacted JSON report containing counts, stable IDs, hashes,
revisions, route statuses, and gate results. It never starts a disposable API
whose parent shell exits before proof completes.

- [ ] **Step 3: Add live SurrealDB integration coverage**

Mark tests with `@pytest.mark.integration_surreal` and require
`SURREAL_INTEGRATION=1`. Prove migration 38 to 39, duplicate operation replay,
transaction rollback, delete receipt replay, restart reads, migration-39 down,
and re-up while migration-38 document counts and hashes remain unchanged.

- [ ] **Step 4: Run backend and audit gates**

Run serially:

```bash
uv run pytest -q tests/test_knowledge_navigation_migration.py tests/test_knowledge_navigation_contracts.py tests/test_knowledge_navigation_repository.py tests/test_knowledge_navigation_identity.py tests/test_knowledge_navigation_service.py tests/test_knowledge_navigation_api.py tests/test_knowledge_workspace_api.py tests/test_knowledge_workspace_persistence.py tests/test_verify_navigation_productivity.py
uv run ruff check deeper_notebook/knowledge_engine api/routers/knowledge_navigation.py api/schemas/knowledge_navigation.py scripts/verify_navigation_productivity.py tests/test_knowledge_navigation_*.py tests/test_verify_navigation_productivity.py
SURREAL_INTEGRATION=1 uv run pytest -q -m integration_surreal tests/integration/test_knowledge_navigation_persistence.py
```

Expected: all focused unit, lint, and real-SurrealDB tests pass.

- [ ] **Step 5: Run the controlled persistent runtime and native gates**

Launch SurrealDB and the native API in persistent terminals, explicitly set:

```bash
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED=true
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_BACKFILL_ENABLED=true
```

Point the verifier only at its generated temporary fixture root. Run mocked
Playwright, then the native-runtime Playwright project and macOS app smoke.
Record exact commands, process IDs, ports, exit codes, fixture hashes, and
artifact paths. Stop only the proof-owned processes after all receipts and
restart checks are collected.

- [ ] **Step 6: Write the completion record and commit**

The verification record must contain:

```markdown
## Verdict

## Baseline and commit

## Mocked browser evidence

## Persistent local API evidence

## SurrealDB migration and restart evidence

## Native macOS evidence

## External authority and source-fingerprint evidence

## Remaining gates
```

Do not mark native or runtime gates passed from an occupied port, a rendered UI,
or a disposable launcher alone. If any required gate is unavailable, record it
as blocked and do not claim the phase complete.

```bash
git add scripts/verify_navigation_productivity.py tests/test_verify_navigation_productivity.py tests/integration/test_knowledge_navigation_persistence.py docs/verification/2026-07-31-deeper-notebook-navigation-productivity.md
git commit -m "docs: verify navigation productivity core"
```

## Final Review Gate

### Specification coverage map

| Approved requirement | Owning tasks |
|---|---|
| Migration 39, strict metadata, receipts, down boundary | 1-2, 12 |
| Stable document/block/search/graph/workspace targets | 1, 3-4, 9 |
| Global folders, tags, repairable stale states, cursor pagination | 2, 4, 9 |
| Filtered Random Note and stable empty state | 2, 6, 9, 11 |
| Unicode document/selection metrics across modes | 7-8, 11 |
| Named save/rename/duplicate/replace/delete | 2, 5, 7, 10 |
| Two-step atomic restore and independent Current Session | 5, 7, 10, 12 |
| Split sizes, graph viewport, sidebar state, filters, active draft ID | 5, 7, 9-10 |
| Integrated Utility Rail and command/slash parity | 9-11 |
| Authority badges, no external writes, redacted contracts | 1-6, 9, 12 |
| Accessibility, localization, mocked browser proof | 8-11 |
| Persistent API, SurrealDB, restart, source-hash, native proof | 12 |

After Task 12:

1. Run `git status --short --branch` and preserve unrelated work.
2. Review every commit from the execution worktree against this plan and the approved specification.
3. Confirm no real Second Brain directory was read or modified.
4. Confirm migration 39 and every new route remain path-free and external-read-only.
5. Confirm Current Session recovery, named snapshots, Overlay drafts, bookmarks, Random Note, metrics, graph, backlinks, and search all retain their distinct authorities.
6. Use `superpowers:requesting-code-review` for implementation review.
7. Use `superpowers:verification-before-completion` before claiming completion.
8. Use `superpowers:finishing-a-development-branch` only after all required findings are resolved.

Productivity Core phase 2—Templates and Note Composer—starts from the verified
result of this plan and is not part of these tasks.
