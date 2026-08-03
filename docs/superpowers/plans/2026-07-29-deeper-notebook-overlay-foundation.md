# Deeper Notebook Overlay Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a distinct app-owned Markdown overlay with idempotent global daily notes, collision-safe unique notes, revision-safe editing, common knowledge projection, and visible Knowledge-workspace integration while every mounted external vault remains read-only.

**Architecture:** A new `deeper_notebook.overlay` package owns a versioned directory beneath the resolved Deeper Notebook data root and exposes only typed overlay IDs and logical names. Canonical Markdown is written atomically, while SurrealDB stores overlay identity, revision, receipt, and derived knowledge-projection records. The frontend adds an explicit `sourceAuthority` discriminant so overlay tabs use overlay APIs and editable source mode while external tabs continue through the existing read-only vault APIs.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI, SurrealDB, descriptor-relative filesystem access, Next.js 16, React 19, TypeScript, Zod 4, Zustand 5, TanStack Query 5, CodeMirror 6, Vitest 4, Testing Library, Pytest 9, Playwright.

## Global Constraints

- Mounted Obsidian, Logseq, and neutral Markdown roots remain canonical external sources and read-only.
- Overlay canonical Markdown lives only beneath `active_data_root() / "overlay" / "v1"`.
- Internal revision snapshots, receipts, quarantine, and recovery state live only beneath `active_data_root() / "overlay-state"`.
- No overlay mutation accepts a caller-supplied absolute path, external vault ID, or external note ID.
- Do not add `PUT`, `PATCH`, or `DELETE` routes under `/api/deeper-notebook/vaults`.
- Overlay Markdown is canonical; SurrealDB note content is a rebuildable projection.
- Every create or update is idempotent, revision-checked, root-bounded, same-directory atomic, fingerprinted, and receipt-backed.
- Daily notes use one global `YYYY-MM-DD` date key and visible path `Daily/YYYY-MM-DD.md`.
- Unique notes use `YYYYMMDD-HHmm Title.md`; deterministic `-2`, `-3`, and later suffixes resolve same-minute collisions.
- An existing filename does not change when editable title metadata changes.
- Existing version-1 Knowledge workspace documents remain loadable and default old tabs to `external-vault`.
- Overlay source editing must use a new editable CodeMirror component. Do not weaken `VaultCodeMirror`, `VaultSourceView`, `VaultLivePreview`, or any external-file read-only facet.
- API and UI errors use typed codes and never return absolute data-root paths, note content from an unrelated record, secrets, or raw tracebacks.
- All locale keys must exist in every supported locale.
- Windows packaged proof remains an explicit release gate; macOS results do not imply Windows filesystem or sandbox safety.

---

## File Map

### Backend overlay authority

- `deeper_notebook/overlay/__init__.py`: public overlay contracts and service exports.
- `deeper_notebook/overlay/contracts.py`: strict Pydantic authority, note, revision, receipt, creation, update, and page contracts.
- `deeper_notebook/overlay/paths.py`: logical-name validation, title slugging, daily/unique naming, and owned-root layout.
- `deeper_notebook/overlay/storage.py`: descriptor-safe reads, same-directory atomic replacement, revision snapshots, hashes, and durable receipts.
- `deeper_notebook/overlay/repository.py`: SurrealDB overlay identity, idempotency, optimistic revision, receipt, and projection transactions.
- `deeper_notebook/overlay/service.py`: daily/unique create, read, update, and projection orchestration.
- `deeper_notebook/database/migrations/36.surrealql`: overlay tables and optional common-projection authority fields.
- `deeper_notebook/database/migrations/36_down.surrealql`: remove only migration-36 tables, indexes, and optional fields.

### API

- `api/schemas/overlay.py`: strict request/response schemas with bounded bodies.
- `api/routers/overlay.py`: canonical `/overlay` resources and safe error mapping.
- `api/main.py`: initialize one overlay service after migrations and register only the canonical router.

### Frontend contracts and state

- `frontend/src/lib/api/overlay.ts`: Zod-validated overlay wire contracts and API client.
- `frontend/src/lib/hooks/use-overlay.ts`: queries, mutations, and exact invalidation.
- `frontend/src/lib/api/knowledge-workspace.ts`: source-authority discriminant with legacy default.
- `frontend/src/lib/stores/knowledge-workspace-store.ts`: authority-aware tab identity and reconciliation.

### Frontend workspace

- `frontend/src/components/overlay/OverlayUtilityPanel.tsx`: Today and New Unique Note actions plus overlay note tree.
- `frontend/src/components/overlay/CreateUniqueNoteDialog.tsx`: bounded title input and idempotent submission.
- `frontend/src/components/overlay/OverlayDocumentView.tsx`: Reading/Live Preview reuse, editable Source mode, save/conflict state, and revision badge.
- `frontend/src/components/overlay/OverlaySourceEditor.tsx`: editable CodeMirror lifecycle isolated from the external read-only editor.
- `frontend/src/components/vault/KnowledgeExplorer.tsx`: combine overlay and mounted roots without mixing authority.
- `frontend/src/components/vault/KnowledgePaneContent.tsx`: authority-directed query and render path.
- `frontend/src/components/vault/KnowledgeTabStrip.tsx`: writable/read-only authority badge.
- `frontend/src/components/vault/vault.css`: Research Core overlay/editor states.
- `frontend/src/lib/locales/*/index.ts`: exact overlay copy in all locales.

### Proof

- `tests/test_overlay_contracts.py`
- `tests/test_overlay_migration.py`
- `tests/test_overlay_paths.py`
- `tests/test_overlay_storage.py`
- `tests/test_overlay_repository.py`
- `tests/test_overlay_service.py`
- `tests/test_overlay_api.py`
- `frontend/src/lib/api/overlay.test.ts`
- `frontend/src/lib/api/knowledge-workspace.test.ts`
- `frontend/src/lib/stores/knowledge-workspace-store.test.ts`
- `frontend/src/components/overlay/OverlayUtilityPanel.test.tsx`
- `frontend/src/components/overlay/CreateUniqueNoteDialog.test.tsx`
- `frontend/src/components/overlay/OverlaySourceEditor.test.tsx`
- `frontend/src/components/overlay/OverlayDocumentView.test.tsx`
- `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- `frontend/src/components/vault/KnowledgePaneContent.test.tsx`
- `frontend/e2e/knowledge-overlay-foundation.spec.ts`
- `scripts/verify_overlay_foundation.py`
- `docs/verification/2026-07-29-deeper-notebook-overlay-foundation.md`

---

### Task 1: Define Overlay Contracts and Migration 36

**Files:**
- Create: `deeper_notebook/overlay/__init__.py`
- Create: `deeper_notebook/overlay/contracts.py`
- Create: `deeper_notebook/database/migrations/36.surrealql`
- Create: `deeper_notebook/database/migrations/36_down.surrealql`
- Create: `tests/test_overlay_contracts.py`
- Create: `tests/test_overlay_migration.py`
- Modify: `tests/test_migration_discovery.py`

**Interfaces:**
- Produces: `OverlaySourceAuthority`, `OverlayNoteKind`, `OverlayProjectionState`, `OverlaySpace`, `OverlayNote`, `OverlayRevision`, `OverlayMutationReceipt`, `CreateDailyNote`, `CreateUniqueNote`, `UpdateOverlayNote`, and `OverlayPage`.
- Consumes: existing `ParsedBlock`, `ParsedLink`, `ParsedTask`, `VaultGraph`, and strict Pydantic conventions.

- [ ] **Step 1: Write strict contract tests**

```python
# tests/test_overlay_contracts.py
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayMutationReceipt,
    OverlayNote,
    UpdateOverlayNote,
)


def test_daily_and_unique_requests_are_strict_and_bounded():
    daily = CreateDailyNote(date_key="2026-07-29")
    unique = CreateUniqueNote(
        title="Research Idea",
        idempotency_key="req-123",
    )
    assert daily.date_key == "2026-07-29"
    assert unique.title == "Research Idea"
    with pytest.raises(ValidationError):
        CreateDailyNote(date_key="07/29/2026")
    with pytest.raises(ValidationError):
        CreateUniqueNote(
            title="x" * 513,
            idempotency_key="req-123",
        )
    with pytest.raises(ValidationError):
        CreateUniqueNote(
            title="Research",
            idempotency_key="req-123",
            external_vault_id="vault_mount:forbidden",
        )


def test_overlay_note_forbids_paths_and_invalid_hashes():
    now = datetime.now(timezone.utc)
    note = OverlayNote(
        id="overlay_note:one",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-one",
        stable_id="01JTESTOVERLAY000000000001",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        content_hash="a" * 64,
        revision=1,
        projection_state="current",
        encoding="utf-8",
        newline="lf",
        created_at=now,
        updated_at=now,
    )
    assert note.source_authority == "overlay"
    with pytest.raises(ValidationError):
        OverlayNote.model_validate({
            **note.model_dump(),
            "relative_path": "/Users/owner/private.md",
        })
    with pytest.raises(ValidationError):
        OverlayNote.model_validate({
            **note.model_dump(),
            "content_hash": "not-a-hash",
        })


def test_update_requires_expected_revision_and_idempotency():
    update = UpdateOverlayNote(
        title="Today",
        markdown="# Today\n",
        expected_revision=3,
        idempotency_key="save-3",
    )
    assert update.expected_revision == 3
    with pytest.raises(ValidationError):
        UpdateOverlayNote(
            title="Today",
            markdown="# Today\n",
            expected_revision=0,
            idempotency_key="save-3",
        )


def test_receipt_has_no_content_or_absolute_path_fields():
    fields = set(OverlayMutationReceipt.model_fields)
    assert "markdown" not in fields
    assert "absolute_path" not in fields
    assert "root_path" not in fields
```

- [ ] **Step 2: Write migration contract tests**

```python
# tests/test_overlay_migration.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/36.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/36_down.surrealql"

TABLES = (
    "overlay_space",
    "overlay_note",
    "overlay_revision",
    "overlay_mutation_receipt",
)


def test_migration_36_is_schemafull_idempotent_and_authority_explicit():
    sql = UP.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    assert "source_authority ON TABLE note" in sql
    assert "overlay_space_id ON TABLE note" in sql
    assert "overlay_note_id ON TABLE note" in sql
    assert "idx_overlay_daily" in sql
    assert "idx_overlay_path" in sql
    assert "idx_overlay_idempotency" in sql
    assert "overlay_note_id ON TABLE note_block" in sql
    assert (
        "DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block "
        "TYPE option<record<vault_file>>;"
    ) in sql
    defines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip().upper().startswith("DEFINE ")
        and "DEFINE FIELD OVERWRITE vault_file_id" not in line
    ]
    assert defines
    assert all("IF NOT EXISTS" in line.upper() for line in defines)


def test_migration_36_down_removes_only_overlay_schema():
    sql = DOWN.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"REMOVE TABLE IF EXISTS {table};" in sql
    assert "REMOVE TABLE IF EXISTS note;" not in sql
    assert "REMOVE TABLE IF EXISTS vault_mount;" not in sql
    assert "REMOVE TABLE IF EXISTS vault_file;" not in sql
    assert "DELETE note_block WHERE overlay_note_id != NONE;" in sql
    assert "DELETE note WHERE overlay_note_id != NONE;" in sql
    assert "DELETE knowledge_task WHERE note_id IN $projected_note_ids;" in sql
    assert "DELETE note_link WHERE source_note_id IN $projected_note_ids" in sql
    assert (
        "DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block "
        "TYPE record<vault_file>;"
    ) in sql
    for field in ("source_authority", "overlay_space_id", "overlay_note_id"):
        assert f"REMOVE FIELD IF EXISTS {field} ON TABLE note;" in sql
```

Extend `tests/test_migration_discovery.py`:

```python
def test_default_migration_discovery_includes_overlay_36_and_down():
    ups, downs = AsyncMigrationManager._discover_migrations()
    assert len(ups) >= 36
    assert "overlay_space" in ups[35].sql
    assert "overlay_mutation_receipt" in ups[35].sql
    assert downs[35] is not None
    assert "REMOVE TABLE IF EXISTS overlay_note" in downs[35].sql
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_contracts.py \
  tests/test_overlay_migration.py \
  tests/test_migration_discovery.py
```

Expected: collection fails because `deeper_notebook.overlay` and migration 36 do not exist.

- [ ] **Step 4: Implement the strict contracts**

```python
# deeper_notebook/overlay/contracts.py
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from typing import Any

from deeper_notebook.vault.repository import VaultGraph, VaultLink

OverlaySourceAuthority = Literal["overlay"]
OverlayNoteKind = Literal["daily", "unique"]
OverlayProjectionState = Literal["pending", "current", "failed", "conflict"]
OverlayReceiptStatus = Literal[
    "started", "success", "unchanged", "conflict", "failed", "superseded"
]

_HASH = re.compile(r"^[0-9a-f]{64}$")
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OverlaySpace(_Strict):
    id: str = Field(min_length=1, max_length=128)
    slug: Literal["default"] = "default"
    display_name: Literal["Deeper Notebook Overlay"] = "Deeper Notebook Overlay"
    root_version: Literal[1] = 1
    created_at: datetime
    updated_at: datetime


class OverlayNote(_Strict):
    id: str = Field(min_length=1, max_length=128)
    source_authority: OverlaySourceAuthority = "overlay"
    space_id: str = Field(min_length=1, max_length=128)
    projected_note_id: str = Field(min_length=1, max_length=128)
    stable_id: str = Field(min_length=20, max_length=128)
    kind: OverlayNoteKind
    date_key: str | None = Field(default=None, max_length=10)
    relative_path: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=512)
    content_hash: str = Field(min_length=64, max_length=64)
    revision: int = Field(ge=1)
    projection_state: OverlayProjectionState
    encoding: Literal["utf-8"] = "utf-8"
    newline: Literal["lf"] = "lf"
    created_at: datetime
    updated_at: datetime

    @field_validator("content_hash")
    @classmethod
    def hash_is_lower_hex(cls, value: str) -> str:
        if not _HASH.fullmatch(value):
            raise ValueError("content_hash must be lowercase SHA-256")
        return value

    @field_validator("relative_path")
    @classmethod
    def path_is_canonical_relative(cls, value: str) -> str:
        parts = value.split("/")
        if (
            value.strip() != value
            or value.startswith(("/", "\\"))
            or "\\" in value
            or "\x00" in value
            or re.match(r"^[A-Za-z]:", value)
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("relative_path must be canonical and relative")
        return value

    @model_validator(mode="after")
    def kind_matches_date_key(self) -> "OverlayNote":
        if self.kind == "daily" and (
            self.date_key is None or not _DATE_KEY.fullmatch(self.date_key)
        ):
            raise ValueError("daily note requires an ISO date_key")
        if self.kind == "unique" and self.date_key is not None:
            raise ValueError("unique note cannot have date_key")
        return self


class OverlayRevision(_Strict):
    id: str
    overlay_note_id: str
    revision: int = Field(ge=1)
    relative_snapshot: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    created_at: datetime


class OverlayMutationReceipt(_Strict):
    id: str
    operation_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    overlay_note_id: str | None = None
    operation: Literal["create-daily", "create-unique", "update", "recover"]
    expected_revision: int | None = Field(default=None, ge=1)
    resulting_revision: int | None = Field(default=None, ge=1)
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: OverlayReceiptStatus
    error_code: str | None = Field(default=None, max_length=64)
    started_at: datetime
    completed_at: datetime | None = None


class CreateDailyNote(_Strict):
    date_key: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CreateUniqueNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def title_is_visible(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("title must contain visible text")
        return normalized


class UpdateOverlayNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    markdown: str = Field(max_length=10 * 1024 * 1024)
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class OverlayPage(_Strict):
    overlay: OverlayNote
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLink] = Field(default_factory=list)
    backlinks: list[VaultLink] = Field(default_factory=list)
    graph: VaultGraph | None = None
```

Export those types from `deeper_notebook/overlay/__init__.py`.

- [ ] **Step 5: Implement migration 36**

```surql
-- deeper_notebook/database/migrations/36.surrealql
DEFINE TABLE IF NOT EXISTS overlay_space SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE overlay_space TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS slug ON TABLE overlay_space TYPE string ASSERT $value = "default";
DEFINE FIELD IF NOT EXISTS display_name ON TABLE overlay_space TYPE string;
DEFINE FIELD IF NOT EXISTS root_version ON TABLE overlay_space TYPE int DEFAULT 1 ASSERT $value = 1;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE overlay_space TYPE datetime DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE overlay_space TYPE datetime DEFAULT time::now() VALUE time::now();
DEFINE INDEX IF NOT EXISTS idx_overlay_space_slug ON TABLE overlay_space COLUMNS slug UNIQUE;

DEFINE TABLE IF NOT EXISTS overlay_note SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE overlay_note TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS space_id ON TABLE overlay_note TYPE record<overlay_space>;
DEFINE FIELD IF NOT EXISTS projected_note_id ON TABLE overlay_note TYPE record<note>;
DEFINE FIELD IF NOT EXISTS stable_id ON TABLE overlay_note TYPE string;
DEFINE FIELD IF NOT EXISTS kind ON TABLE overlay_note TYPE string ASSERT $value IN ["daily", "unique"];
DEFINE FIELD IF NOT EXISTS date_key ON TABLE overlay_note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS relative_path ON TABLE overlay_note TYPE string;
DEFINE FIELD IF NOT EXISTS title ON TABLE overlay_note TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON TABLE overlay_note TYPE string;
DEFINE FIELD IF NOT EXISTS revision ON TABLE overlay_note TYPE int ASSERT $value >= 1;
DEFINE FIELD IF NOT EXISTS projection_state ON TABLE overlay_note TYPE string DEFAULT "pending" ASSERT $value IN ["pending", "current", "failed", "conflict"];
DEFINE FIELD IF NOT EXISTS encoding ON TABLE overlay_note TYPE string DEFAULT "utf-8" ASSERT $value = "utf-8";
DEFINE FIELD IF NOT EXISTS newline ON TABLE overlay_note TYPE string DEFAULT "lf" ASSERT $value = "lf";
DEFINE FIELD IF NOT EXISTS created_at ON TABLE overlay_note TYPE datetime DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE overlay_note TYPE datetime DEFAULT time::now() VALUE time::now();
DEFINE INDEX IF NOT EXISTS idx_overlay_stable_id ON TABLE overlay_note COLUMNS stable_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_overlay_daily ON TABLE overlay_note COLUMNS space_id, date_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_overlay_path ON TABLE overlay_note COLUMNS space_id, relative_path UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_overlay_projected_note ON TABLE overlay_note COLUMNS projected_note_id UNIQUE;

DEFINE TABLE IF NOT EXISTS overlay_revision SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE overlay_revision TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS overlay_note_id ON TABLE overlay_revision TYPE record<overlay_note>;
DEFINE FIELD IF NOT EXISTS revision ON TABLE overlay_revision TYPE int ASSERT $value >= 1;
DEFINE FIELD IF NOT EXISTS relative_snapshot ON TABLE overlay_revision TYPE string;
DEFINE FIELD IF NOT EXISTS content_hash ON TABLE overlay_revision TYPE string;
DEFINE FIELD IF NOT EXISTS byte_size ON TABLE overlay_revision TYPE int ASSERT $value >= 0;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE overlay_revision TYPE datetime DEFAULT time::now() VALUE $before OR time::now();
DEFINE INDEX IF NOT EXISTS idx_overlay_revision ON TABLE overlay_revision COLUMNS overlay_note_id, revision UNIQUE;

DEFINE TABLE IF NOT EXISTS overlay_mutation_receipt SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE overlay_mutation_receipt TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS operation_id ON TABLE overlay_mutation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS idempotency_key ON TABLE overlay_mutation_receipt TYPE string;
DEFINE FIELD IF NOT EXISTS overlay_note_id ON TABLE overlay_mutation_receipt TYPE option<record<overlay_note>>;
DEFINE FIELD IF NOT EXISTS operation ON TABLE overlay_mutation_receipt TYPE string ASSERT $value IN ["create-daily", "create-unique", "update", "recover"];
DEFINE FIELD IF NOT EXISTS expected_revision ON TABLE overlay_mutation_receipt TYPE option<int>;
DEFINE FIELD IF NOT EXISTS resulting_revision ON TABLE overlay_mutation_receipt TYPE option<int>;
DEFINE FIELD IF NOT EXISTS before_hash ON TABLE overlay_mutation_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS after_hash ON TABLE overlay_mutation_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS status ON TABLE overlay_mutation_receipt TYPE string ASSERT $value IN ["started", "success", "unchanged", "conflict", "failed", "superseded"];
DEFINE FIELD IF NOT EXISTS error_code ON TABLE overlay_mutation_receipt TYPE option<string>;
DEFINE FIELD IF NOT EXISTS started_at ON TABLE overlay_mutation_receipt TYPE datetime;
DEFINE FIELD IF NOT EXISTS completed_at ON TABLE overlay_mutation_receipt TYPE option<datetime>;
DEFINE INDEX IF NOT EXISTS idx_overlay_operation ON TABLE overlay_mutation_receipt COLUMNS operation_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_overlay_idempotency ON TABLE overlay_mutation_receipt COLUMNS operation, idempotency_key UNIQUE;

DEFINE FIELD IF NOT EXISTS source_authority ON TABLE note TYPE option<string> ASSERT $value = NONE OR $value IN ["external-vault", "overlay"];
DEFINE FIELD IF NOT EXISTS overlay_space_id ON TABLE note TYPE option<record<overlay_space>>;
DEFINE FIELD IF NOT EXISTS overlay_note_id ON TABLE note TYPE option<record<overlay_note>>;
DEFINE INDEX IF NOT EXISTS idx_note_overlay_note ON TABLE note COLUMNS overlay_note_id UNIQUE;

DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block TYPE option<record<vault_file>>;
DEFINE FIELD IF NOT EXISTS overlay_note_id ON TABLE note_block TYPE option<record<overlay_note>>;
DEFINE INDEX IF NOT EXISTS idx_note_block_overlay ON TABLE note_block COLUMNS overlay_note_id, parser_id UNIQUE;
```

`36_down.surrealql` is explicit and deletes derived rows before removing their
authority fields:

```surql
LET $projected_note_ids = SELECT VALUE projected_note_id FROM overlay_note;

DELETE knowledge_task WHERE note_id IN $projected_note_ids;
DELETE note_link
  WHERE source_note_id IN $projected_note_ids
     OR target_note_id IN $projected_note_ids;
DELETE note_block WHERE overlay_note_id != NONE;
DELETE note WHERE overlay_note_id != NONE;

REMOVE INDEX IF EXISTS idx_note_block_overlay ON TABLE note_block;
REMOVE FIELD IF EXISTS overlay_note_id ON TABLE note_block;
DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block TYPE record<vault_file>;

REMOVE INDEX IF EXISTS idx_note_overlay_note ON TABLE note;
REMOVE FIELD IF EXISTS overlay_note_id ON TABLE note;
REMOVE FIELD IF EXISTS overlay_space_id ON TABLE note;
REMOVE FIELD IF EXISTS source_authority ON TABLE note;

REMOVE TABLE IF EXISTS overlay_mutation_receipt;
REMOVE TABLE IF EXISTS overlay_revision;
REMOVE TABLE IF EXISTS overlay_note;
REMOVE TABLE IF EXISTS overlay_space;
```

This rollback must not delete a normal app note, external-vault note, vault
mount, vault file, or canonical overlay Markdown file.

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_contracts.py \
  tests/test_overlay_migration.py \
  tests/test_migration_discovery.py
```

Expected: all selected tests pass.

Commit:

```bash
git add \
  deeper_notebook/overlay/__init__.py \
  deeper_notebook/overlay/contracts.py \
  deeper_notebook/database/migrations/36.surrealql \
  deeper_notebook/database/migrations/36_down.surrealql \
  tests/test_overlay_contracts.py \
  tests/test_overlay_migration.py \
  tests/test_migration_discovery.py
git commit -m "feat(overlay): define owned note contracts"
```

---

### Task 2: Add Owned Paths and Collision-Safe Naming

**Files:**
- Create: `deeper_notebook/overlay/paths.py`
- Create: `tests/test_overlay_paths.py`
- Modify: `deeper_notebook/overlay/__init__.py`

**Interfaces:**
- Produces: `OverlayLayout.from_data_root(data_root)`, `validate_relative_path(value)`, `daily_relative_path(date_key)`, `unique_relative_path(local_time, title, exists)`, and `overlay_frontmatter(note: OverlayNote, body: str) -> str`.
- Consumes: `active_data_root()` only at the outer layout factory; pure naming functions receive explicit inputs.

- [ ] **Step 1: Write naming and root tests**

```python
# tests/test_overlay_paths.py
from datetime import datetime
from pathlib import Path

import pytest

from deeper_notebook.overlay.paths import (
    OverlayLayout,
    OverlayPathError,
    daily_relative_path,
    unique_relative_path,
    validate_relative_path,
)


def test_layout_stays_under_explicit_data_root(tmp_path: Path):
    layout = OverlayLayout.from_data_root(tmp_path)
    assert layout.canonical_root == tmp_path / "overlay" / "v1"
    assert layout.daily_root == layout.canonical_root / "Daily"
    assert layout.unique_root == layout.canonical_root / "Notes"
    assert layout.state_root == tmp_path / "overlay-state"


def test_daily_path_is_canonical():
    assert daily_relative_path("2026-07-29") == "Daily/2026-07-29.md"
    with pytest.raises(OverlayPathError):
        daily_relative_path("../2026-07-29")


def test_unique_path_uses_timestamp_title_and_suffixes():
    when = datetime(2026, 7, 29, 15, 42)
    occupied = {"Notes/20260729-1542 Research Idea.md"}
    path = unique_relative_path(
        when,
        " Research / Idea ",
        exists=occupied.__contains__,
    )
    assert path == "Notes/20260729-1542 Research Idea-2.md"


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/note.md",
        r"C:\note.md",
        r"Daily\one.md",
        "../one.md",
        "Daily/../one.md",
        "Daily//one.md",
        "Daily/\x00one.md",
    ],
)
def test_relative_path_rejects_absolute_and_escaping_values(value: str):
    with pytest.raises(OverlayPathError):
        validate_relative_path(value)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest -q tests/test_overlay_paths.py`

Expected: import fails because `overlay.paths` does not exist.

- [ ] **Step 3: Implement pure path and naming functions**

```python
# deeper_notebook/overlay/paths.py
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from desktop.data_root import active_data_root

MAX_FILENAME_CHARS = 180
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSAFE_TITLE = re.compile(r"[\x00-\x1f/\\:*?\"<>|]+")


class OverlayPathError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Overlay path is invalid.")


@dataclass(frozen=True, slots=True)
class OverlayLayout:
    canonical_root: Path
    daily_root: Path
    unique_root: Path
    templates_root: Path
    state_root: Path
    revisions_root: Path
    receipts_root: Path
    recovery_root: Path

    @classmethod
    def from_data_root(cls, data_root: Path) -> "OverlayLayout":
        canonical = data_root / "overlay" / "v1"
        state = data_root / "overlay-state"
        return cls(
            canonical_root=canonical,
            daily_root=canonical / "Daily",
            unique_root=canonical / "Notes",
            templates_root=canonical / "Templates",
            state_root=state,
            revisions_root=state / "revisions",
            receipts_root=state / "receipts",
            recovery_root=state / "recovery",
        )

    @classmethod
    def active(cls) -> "OverlayLayout":
        return cls.from_data_root(active_data_root())


def validate_relative_path(value: str) -> str:
    if value.strip() != value or "\\" in value or "\x00" in value:
        raise OverlayPathError("invalid_relative_path")
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise OverlayPathError("invalid_relative_path")
    return value


def daily_relative_path(date_key: str) -> str:
    if not _DATE_KEY.fullmatch(date_key):
        raise OverlayPathError("invalid_date_key")
    datetime.strptime(date_key, "%Y-%m-%d")
    return f"Daily/{date_key}.md"


def _safe_title(title: str) -> str:
    value = unicodedata.normalize("NFC", title).strip()
    value = _UNSAFE_TITLE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value or "Untitled"
    return value[:MAX_FILENAME_CHARS].rstrip(" .") or "Untitled"


def unique_relative_path(
    local_time: datetime,
    title: str,
    *,
    exists: Callable[[str], bool],
) -> str:
    stem = f"{local_time:%Y%m%d-%H%M} {_safe_title(title)}"
    candidate = f"Notes/{stem}.md"
    suffix = 2
    while exists(candidate):
        candidate = f"Notes/{stem}-{suffix}.md"
        suffix += 1
        if suffix > 10_000:
            raise OverlayPathError("unique_name_exhausted")
    return validate_relative_path(candidate)
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest -q tests/test_overlay_paths.py tests/test_overlay_contracts.py`

Expected: all selected tests pass.

Commit:

```bash
git add deeper_notebook/overlay/paths.py deeper_notebook/overlay/__init__.py tests/test_overlay_paths.py
git commit -m "feat(overlay): bound owned note paths"
```

---

### Task 3: Implement Descriptor-Safe Atomic Storage

**Files:**
- Create: `deeper_notebook/overlay/storage.py`
- Create: `tests/test_overlay_storage.py`
- Modify: `deeper_notebook/overlay/__init__.py`

**Interfaces:**
- Produces:
  - `OverlayStorage(layout, *, max_markdown_bytes=10 * 1024 * 1024)`
  - `read(relative_path) -> StoredOverlayBytes`
  - `create(relative_path, markdown, *, operation_id) -> StoredOverlayBytes`
  - `replace(relative_path, markdown, *, expected_hash, revision, operation_id) -> StoredOverlayBytes`
  - `snapshot(note_id, revision, content) -> OverlaySnapshot`
- Consumes: `OverlayLayout`, canonical relative paths, UTF-8 LF Markdown, and caller-generated opaque operation IDs.

- [ ] **Step 1: Write atomicity and adversarial tests**

```python
# tests/test_overlay_storage.py
import hashlib
from pathlib import Path

import pytest

from deeper_notebook.overlay.paths import OverlayLayout
from deeper_notebook.overlay.storage import (
    OverlayConflictError,
    OverlayStorage,
    OverlayStorageError,
)


def _storage(tmp_path: Path) -> OverlayStorage:
    return OverlayStorage(OverlayLayout.from_data_root(tmp_path))


def test_create_and_read_are_utf8_lf_and_hash_bound(tmp_path: Path):
    storage = _storage(tmp_path)
    stored = storage.create(
        "Daily/2026-07-29.md",
        "# Today\r\n",
        operation_id="create-1",
    )
    expected = b"# Today\n"
    assert stored.markdown == "# Today\n"
    assert stored.content_hash == hashlib.sha256(expected).hexdigest()
    assert storage.read("Daily/2026-07-29.md") == stored


def test_create_never_replaces_existing_file(tmp_path: Path):
    storage = _storage(tmp_path)
    storage.create("Notes/one.md", "first\n", operation_id="one")
    with pytest.raises(OverlayConflictError, match="overlay_file_exists"):
        storage.create("Notes/one.md", "second\n", operation_id="two")
    assert storage.read("Notes/one.md").markdown == "first\n"


def test_replace_requires_current_hash_and_preserves_on_failure(tmp_path: Path):
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    with pytest.raises(OverlayConflictError, match="overlay_hash_conflict"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash="0" * 64,
            revision=2,
            operation_id="two",
        )
    assert storage.read("Notes/one.md") == first


def test_source_symlink_and_parent_swap_fail_closed(tmp_path: Path):
    storage = _storage(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("private\n", encoding="utf-8")
    storage.layout.daily_root.mkdir(parents=True)
    (storage.layout.daily_root / "evil.md").symlink_to(outside)
    with pytest.raises(OverlayStorageError):
        storage.read("Daily/evil.md")
    assert outside.read_text(encoding="utf-8") == "private\n"


def test_injected_replace_failure_keeps_original_and_removes_owned_temp(
    tmp_path: Path,
    monkeypatch,
):
    storage = _storage(tmp_path)
    first = storage.create("Notes/one.md", "first\n", operation_id="one")
    monkeypatch.setattr(
        "deeper_notebook.overlay.storage.os.replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("injected")),
    )
    with pytest.raises(OSError, match="injected"):
        storage.replace(
            "Notes/one.md",
            "second\n",
            expected_hash=first.content_hash,
            revision=2,
            operation_id="two",
        )
    assert storage.read("Notes/one.md").markdown == "first\n"
    assert not list(storage.layout.unique_root.glob(".*.tmp"))
```

Add parameterized cases for hard links, directory targets, root identity
changes, Unicode normalization collisions, payloads over 10 MiB, invalid
relative paths, malformed UTF-8 bytes, changed-during-read, and cleanup that
must not unlink a substituted path.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest -q tests/test_overlay_storage.py`

Expected: import fails because `overlay.storage` does not exist.

- [ ] **Step 3: Implement the storage boundary**

Implement these exact public records and methods:

```python
# deeper_notebook/overlay/storage.py
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.overlay.paths import OverlayLayout, validate_relative_path


class OverlayStorageError(OSError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OverlayConflictError(OverlayStorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredOverlayBytes:
    relative_path: str
    markdown: str
    content_hash: str
    byte_size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class OverlaySnapshot:
    relative_snapshot: str
    content_hash: str
    byte_size: int


class OverlayStorage:
    def __init__(
        self,
        layout: OverlayLayout,
        *,
        max_markdown_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.layout = layout
        self.max_markdown_bytes = max_markdown_bytes

    @staticmethod
    def _encode(markdown: str, maximum: int) -> bytes:
        encoded = markdown.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        if len(encoded) > maximum:
            raise OverlayStorageError("overlay_file_too_large")
        return encoded
```

Add these exact public methods to the class:

- `read(self, relative_path: str) -> StoredOverlayBytes`
- `create(self, relative_path: str, markdown: str, *, operation_id: str) -> StoredOverlayBytes`
- `replace(self, relative_path: str, markdown: str, *, expected_hash: str, revision: int, operation_id: str) -> StoredOverlayBytes`
- `snapshot(self, note_id: str, revision: int, content: StoredOverlayBytes) -> OverlaySnapshot`

Implement each method with this descriptor-relative algorithm:

1. Create the exact owned `Daily`, `Notes`, and state directories with mode
   `0700` where supported.
2. Open and retain the canonical root directory descriptor.
3. Traverse only validated relative segments using `dir_fd`, `O_DIRECTORY`,
   `O_NOFOLLOW` where available, and `fstat`.
4. Reject symlinks, non-regular files, multi-linked files, root identity
   changes, and before/after metadata changes.
5. For create, use `O_CREAT | O_EXCL` in the destination directory.
6. For replace, re-read and hash the existing file, compare `expected_hash`,
   snapshot the current bytes, write a same-directory `0600` temp, flush it,
   and call descriptor-relative `os.replace`.
7. Fsync the destination directory when supported.
8. Remove only the temp inode created by this operation.
9. On Windows, use `lstat`/resolved-root identity checks and reject reparse
   points. Never silently downgrade to an unchecked `Path.write_text`.

The implementation must contain no `eval`, shell call, external-vault root, or
caller-provided absolute path.

- [ ] **Step 4: Run storage and existing vault security tests**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_storage.py \
  tests/test_overlay_paths.py \
  tests/test_vault_security.py
```

Expected: all selected tests pass and the existing external-vault reader remains
unchanged.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/overlay/storage.py deeper_notebook/overlay/__init__.py tests/test_overlay_storage.py
git commit -m "feat(overlay): write owned markdown atomically"
```

---

### Task 4: Persist Idempotent Revisions and Project Overlay Markdown

**Files:**
- Create: `deeper_notebook/overlay/repository.py`
- Create: `deeper_notebook/overlay/service.py`
- Create: `tests/test_overlay_repository.py`
- Create: `tests/test_overlay_service.py`
- Modify: `deeper_notebook/vault/repository.py`
- Modify: `tests/test_vault_repository.py`
- Modify: `tests/integration/test_vault_projection.py`
- Modify: `deeper_notebook/overlay/__init__.py`

**Interfaces:**
- Produces:
  - `OverlayRepository.ensure_default_space()`
  - `OverlayRepository.get_daily(date_key)`
  - `OverlayRepository.get_note(note_id)`
  - `OverlayRepository.list_notes(limit, offset)`
  - `OverlayRepository.reserve_create(operation, idempotency_key, kind, date_key, relative_path, title)`
  - `OverlayRepository.commit_revision(reservation, content_hash, byte_size, relative_snapshot, parsed)`
  - `OverlayRepository.record_failure(reservation, error_code)`
  - `OverlayService.create_daily(request)`
  - `OverlayService.create_unique(request)`
  - `OverlayService.get_page(note_id)`
  - `OverlayService.update(note_id, request)`
- Consumes: `OverlayStorage`, bounded Markdown parser, common projection
  repository, idempotency keys, and expected revisions.

- [ ] **Step 1: Write repository transaction tests**

```python
# tests/test_overlay_repository.py
import pytest

from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepository,
)


@pytest.mark.asyncio
async def test_daily_reservation_has_one_winner(repository: OverlayRepository):
    first = await repository.reserve_create(
        operation="create-daily",
        idempotency_key="daily:2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
    )
    second = await repository.reserve_create(
        operation="create-daily",
        idempotency_key="daily:2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
    )
    assert first.overlay_note_id == second.overlay_note_id
    assert first.operation_id == second.operation_id


@pytest.mark.asyncio
async def test_commit_requires_reserved_revision(repository: OverlayRepository):
    reservation = await repository.reserve_create(
        operation="create-unique",
        idempotency_key="unique-1",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Research.md",
        title="Research",
    )
    committed = await repository.commit_revision(
        reservation=reservation,
        content_hash="a" * 64,
        byte_size=12,
        relative_snapshot=None,
        parsed=_parsed_document(),
    )
    assert committed.revision == 1
    with pytest.raises(OverlayConflictError, match="overlay_revision_conflict"):
        await repository.reserve_update(
            note_id=committed.id,
            expected_revision=99,
            idempotency_key="save-1",
        )
```

Use a fake connection that asserts:

- reservation and receipt creation share one transaction;
- replay returns the original successful result;
- daily uniqueness is enforced by `(space_id, date_key)`;
- unique creation rechecks the reserved path;
- update compares both revision and current hash;
- `overlay_note`, projected `note`, blocks, links, tasks, revision, and receipt
  update in one database transaction after the file write;
- failure receipts contain hashes and typed codes but no Markdown or paths
  outside the logical relative path.

- [ ] **Step 2: Write service orchestration tests**

```python
# tests/test_overlay_service.py
from datetime import datetime

import pytest

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.service import OverlayService


@pytest.mark.asyncio
async def test_daily_creation_is_idempotent_across_service_instances(fixture):
    first_service = fixture.service()
    second_service = fixture.service()
    first = await first_service.create_daily(
        CreateDailyNote(date_key="2026-07-29")
    )
    second = await second_service.create_daily(
        CreateDailyNote(date_key="2026-07-29")
    )
    assert first.overlay.id == second.overlay.id
    assert first.overlay.content_hash == second.overlay.content_hash
    assert list(fixture.layout.daily_root.glob("*.md")) == [
        fixture.layout.daily_root / "2026-07-29.md"
    ]


@pytest.mark.asyncio
async def test_unique_collisions_receive_deterministic_suffixes(fixture):
    fixture.clock.return_value = datetime(2026, 7, 29, 15, 42)
    first = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    second = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="two")
    )
    assert first.overlay.relative_path.endswith("Research.md")
    assert second.overlay.relative_path.endswith("Research-2.md")


@pytest.mark.asyncio
async def test_update_conflict_never_replaces_canonical_file(fixture):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    with pytest.raises(Exception, match="overlay_revision_conflict"):
        await fixture.service().update(
            page.overlay.id,
            UpdateOverlayNote(
                title="Changed",
                markdown="# Changed\n",
                expected_revision=99,
                idempotency_key="save",
            ),
        )
    stored = fixture.storage.read(page.overlay.relative_path)
    assert stored.content_hash == page.overlay.content_hash
```

Also prove:

- a storage failure leaves no successful DB revision;
- a DB failure after file replacement marks projection pending and keeps the
  canonical file recoverable;
- retry by the same idempotency key reconciles rather than writing twice;
- parser failure preserves the previous valid projection;
- absolute root paths never appear in returned models or receipt logs.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_repository.py \
  tests/test_overlay_service.py
```

Expected: collection fails because repository and service modules do not exist.

- [ ] **Step 4: Extract a common projection seam**

Add a focused, authority-explicit method to `VaultRepository` rather than
copying its graph transaction:

```python
async def project_owned_document(
    self,
    *,
    source_authority: Literal["overlay"],
    overlay_space_id: str,
    overlay_note_id: str,
    projected_note_id: str,
    parsed: ParsedDocument,
    revision: int,
) -> OverlayPage:
    """Project app-owned Markdown without creating or mutating a vault mount."""
```

The method reuses block/link/task construction but writes:

```python
note_data = {
    "title": parsed.title,
    "title_key": canonical_title_key(parsed.title),
    "note_type": "human",
    "content": parsed.markdown,
    "source_format": parsed.source_format,
    "canonical_external": False,
    "source_authority": "overlay",
    "overlay_space_id": _db_id(overlay_space_id),
    "overlay_note_id": _db_id(overlay_note_id),
    "properties": parsed.properties,
    "tags": parsed.tags,
    "source_hash": parsed.content_hash,
    "external_state": None,
}
```

It must not create `vault_mount`, `vault_file`, or `vault_sync_receipt` rows.
Overlay blocks use `note_block.overlay_note_id` and a `NONE`
`note_block.vault_file_id`. Overlay-specific revision and receipt rows remain
owned by `OverlayRepository`. The returned `OverlayPage` is assembled from the
overlay record plus projected `note`, `note_block`, `knowledge_task`, and
`note_link` rows; it is not coerced into `VaultPage`. Link resolution initially
resolves overlay-to-overlay targets within the same `overlay_space_id`;
existing external resolution stays unchanged. Cross-authority resolution is
deferred to the later global-graph integration plan.

- [ ] **Step 5: Implement repository and service**

Use explicit typed records:

```python
@dataclass(frozen=True, slots=True)
class OverlayReservation:
    operation_id: str
    idempotency_key: str
    overlay_note_id: str
    projected_note_id: str
    relative_path: str
    title: str
    kind: OverlayNoteKind
    date_key: str | None
    expected_revision: int | None
```

Implement `OverlayRepository` with these exact method signatures:

- `async def ensure_default_space(self) -> OverlaySpace`
- `async def get_daily(self, date_key: str) -> OverlayNote | None`
- `async def get_note(self, note_id: str) -> OverlayNote`
- `async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]`
- `async def reserve_create(self, *, operation: Literal["create-daily", "create-unique"], idempotency_key: str, kind: OverlayNoteKind, date_key: str | None, relative_path: str, title: str) -> OverlayReservation`
- `async def reserve_update(self, *, note_id: str, expected_revision: int, idempotency_key: str) -> OverlayReservation`
- `async def commit_revision(self, *, reservation: OverlayReservation, content_hash: str, byte_size: int, relative_snapshot: str | None, parsed: ParsedDocument) -> OverlayNote`
- `async def record_failure(self, *, reservation: OverlayReservation, error_code: str) -> None`

Implement `OverlayService.__init__(repository, storage, *, clock)` plus:

- `async def create_daily(self, request: CreateDailyNote) -> OverlayPage`
- `async def create_unique(self, request: CreateUniqueNote) -> OverlayPage`
- `async def get_page(self, note_id: str) -> OverlayPage`
- `async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]`
- `async def update(self, note_id: str, request: UpdateOverlayNote) -> OverlayPage`

Creation order:

1. reserve database identity and idempotency receipt;
2. re-read a completed replay before touching disk;
3. create canonical Markdown with reserved identity frontmatter;
4. parse the exact stored bytes;
5. commit revision, receipt, and projection;
6. return the canonical page.

Update order:

1. reserve expected revision;
2. read and fingerprint canonical bytes;
3. create a revision snapshot;
4. atomically replace canonical bytes;
5. parse exact stored bytes;
6. commit revision, receipt, and projection;
7. if step 6 fails, retain canonical bytes and mark retryable reconciliation.

- [ ] **Step 6: Run focused projection and service tests**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_repository.py \
  tests/test_overlay_service.py \
  tests/test_vault_repository.py \
  tests/integration/test_vault_projection.py
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add \
  deeper_notebook/overlay/repository.py \
  deeper_notebook/overlay/service.py \
  deeper_notebook/overlay/__init__.py \
  deeper_notebook/vault/repository.py \
  tests/test_overlay_repository.py \
  tests/test_overlay_service.py \
  tests/test_vault_repository.py \
  tests/integration/test_vault_projection.py
git commit -m "feat(overlay): project owned markdown revisions"
```

---

### Task 5: Expose a Bounded Authenticated Overlay API

**Files:**
- Create: `api/schemas/overlay.py`
- Create: `api/routers/overlay.py`
- Create: `tests/test_overlay_api.py`
- Modify: `api/main.py`
- Modify: `tests/test_vault_api.py`

**Interfaces:**
- Produces:
  - `GET /api/deeper-notebook/overlay`
  - `GET /api/deeper-notebook/overlay/notes`
  - `PUT /api/deeper-notebook/overlay/daily/{date_key}`
  - `POST /api/deeper-notebook/overlay/notes/unique`
  - `GET /api/deeper-notebook/overlay/notes/{note_id}`
  - `PUT /api/deeper-notebook/overlay/notes/{note_id}`
- Consumes: `app.state.overlay_service`.

- [ ] **Step 1: Write API contract and route-boundary tests**

```python
# tests/test_overlay_api.py
def test_overlay_routes_are_canonical_and_vault_routes_stay_read_only(client):
    routes = {
        route.path: route.methods
        for route in client.app.router.routes
        if hasattr(route, "methods")
    }
    assert "/api/deeper-notebook/overlay" in routes
    assert "/api/deeper-notebook/overlay/daily/{date_key}" in routes
    assert "/api/deeper-notebook/overlay/notes/unique" in routes
    assert "/api/deeper-notebook/overlay/notes/{note_id}" in routes
    assert "/api/onp/overlay" not in routes
    for path, methods in routes.items():
        if path.startswith("/api/deeper-notebook/vaults"):
            assert not methods & {"PUT", "PATCH", "DELETE"}


def test_daily_create_is_idempotent_and_contains_no_absolute_path(client):
    first = client.put("/api/deeper-notebook/overlay/daily/2026-07-29")
    second = client.put("/api/deeper-notebook/overlay/daily/2026-07-29")
    assert first.status_code == second.status_code == 200
    assert first.json()["overlay"]["id"] == second.json()["overlay"]["id"]
    assert "/Users/" not in first.text


def test_unique_and_update_require_strict_revision_contract(client):
    created = client.post(
        "/api/deeper-notebook/overlay/notes/unique",
        json={"title": "Research", "idempotency_key": "create-1"},
    )
    assert created.status_code == 201
    note_id = created.json()["overlay"]["id"]
    conflict = client.put(
        f"/api/deeper-notebook/overlay/notes/{note_id}",
        json={
            "title": "Research",
            "markdown": "# Changed\n",
            "expected_revision": 99,
            "idempotency_key": "save-1",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "overlay_revision_conflict"


def test_overlay_requests_reject_unknown_fields_and_oversize_bodies(client):
    rejected = client.post(
        "/api/deeper-notebook/overlay/notes/unique",
        json={
            "title": "Research",
            "idempotency_key": "create-1",
            "external_vault_id": "vault_mount:forbidden",
        },
    )
    assert rejected.status_code == 422
    too_large = client.put(
        "/api/deeper-notebook/overlay/notes/overlay_note:one",
        content=b"x" * (10 * 1024 * 1024 + 2048),
        headers={"content-type": "application/json"},
    )
    assert too_large.status_code == 413
```

- [ ] **Step 2: Run the API tests and verify RED**

Run: `uv run pytest -q tests/test_overlay_api.py tests/test_vault_api.py`

Expected: overlay routes are absent.

- [ ] **Step 3: Implement strict schemas and router**

`api/schemas/overlay.py` re-exports strict wire models with
`ConfigDict(extra="forbid", strict=True)`. `api/routers/overlay.py` uses the
bounded-request pattern from `knowledge_workspace.py` with a
`10 * 1024 * 1024 + 64 * 1024` JSON ceiling.

Use this exact error map:

```python
_ERRORS = {
    "overlay_not_found": (404, "overlay_not_found"),
    "overlay_revision_conflict": (409, "overlay_revision_conflict"),
    "overlay_file_exists": (409, "overlay_file_exists"),
    "overlay_hash_conflict": (409, "overlay_revision_conflict"),
    "overlay_request_too_large": (413, "overlay_request_too_large"),
    "overlay_file_too_large": (413, "overlay_file_too_large"),
    "overlay_projection_pending": (503, "overlay_projection_pending"),
    "overlay_storage_unavailable": (503, "overlay_storage_unavailable"),
}
```

Unknown internal exceptions map to
`503 {"detail": {"code": "overlay_unavailable"}}`. Do not return `str(exc)`.

- [ ] **Step 4: Register lifecycle and router**

After migrations in `api/main.py`:

```python
overlay_service = None
try:
    from deeper_notebook.overlay.paths import OverlayLayout
    from deeper_notebook.overlay.repository import OverlayRepository
    from deeper_notebook.overlay.service import OverlayService
    from deeper_notebook.overlay.storage import OverlayStorage

    overlay_service = OverlayService(
        OverlayRepository(),
        OverlayStorage(OverlayLayout.active()),
    )
    app.state.overlay_service = overlay_service
except Exception as exc:
    logger.warning(
        "Overlay startup unavailable ({})",
        type(exc).__name__,
    )
```

Register:

```python
app.include_router(
    overlay.router,
    prefix="/api/deeper-notebook",
    tags=["deeper-notebook-overlay"],
)
```

Do not register an `/api/onp` alias.

- [ ] **Step 5: Run API, migration, and vault boundary tests**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_api.py \
  tests/test_overlay_migration.py \
  tests/test_vault_api.py \
  tests/test_vault_note_read_only.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add \
  api/schemas/overlay.py \
  api/routers/overlay.py \
  api/main.py \
  tests/test_overlay_api.py \
  tests/test_vault_api.py
git commit -m "feat(api): expose owned overlay notes"
```

---

### Task 6: Add Authority-Aware Frontend Contracts and Tabs

**Files:**
- Create: `frontend/src/lib/api/overlay.ts`
- Create: `frontend/src/lib/api/overlay.test.ts`
- Create: `frontend/src/lib/hooks/use-overlay.ts`
- Modify: `deeper_notebook/workspace/contracts.py`
- Modify: `frontend/src/lib/api/knowledge-workspace.ts`
- Modify: `frontend/src/lib/api/knowledge-workspace.test.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.test.ts`
- Modify: `tests/test_knowledge_workspace_persistence.py`

**Interfaces:**
- Produces: `overlayApi`, `overlayKeys`, `useOverlayNotes`, `useOverlayPage`,
  `useTodayOverlayNote`, `useCreateUniqueOverlayNote`, `useUpdateOverlayNote`,
  and `KnowledgeSourceAuthority`.
- Consumes: canonical overlay API wire responses and legacy version-1 workspace documents.

- [ ] **Step 1: Write hostile wire-response and legacy workspace tests**

```typescript
// frontend/src/lib/api/overlay.test.ts
it('rejects absolute paths, invalid hashes, and authority substitution', async () => {
  mockGet.mockResolvedValue({
    data: {
      ...validOverlayPage,
      overlay: {
        ...validOverlayPage.overlay,
        source_authority: 'external-vault',
        relative_path: '/Users/owner/private.md',
        content_hash: 'bad',
      },
    },
  })
  await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
})

it('encodes IDs and serializes only the strict update contract', async () => {
  await overlayApi.update('overlay_note:a/b', {
    title: 'Today',
    markdown: '# Today\n',
    expectedRevision: 1,
    idempotencyKey: 'save-1',
  })
  expect(mockPut).toHaveBeenCalledWith(
    '/deeper-notebook/overlay/notes/overlay_note%3Aa%2Fb',
    {
      title: 'Today',
      markdown: '# Today\n',
      expected_revision: 1,
      idempotency_key: 'save-1',
    },
  )
})
```

```typescript
// knowledge-workspace tests
it('loads legacy tabs as external-vault authority', () => {
  const parsed = parseKnowledgeWorkspace(legacyVersionOneDocument)
  expect(parsed.panes['pane-1'].tabs[0].sourceAuthority)
    .toBe('external-vault')
})

it('keeps overlay and external tabs distinct for identical note IDs', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab(externalTab)
  store.openTab({ ...externalTab, sourceAuthority: 'overlay' })
  expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
    .toHaveLength(2)
})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/api/overlay.test.ts \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: overlay API is absent and workspace tabs have no authority field.

- [ ] **Step 3: Implement strict Zod overlay contracts**

`frontend/src/lib/api/overlay.ts` defines:

```typescript
export const knowledgeSourceAuthoritySchema = z.enum([
  'external-vault',
  'overlay',
])

export const overlayNoteSchema = z.object({
  id: z.string().min(1).max(128),
  source_authority: z.literal('overlay'),
  space_id: z.string().min(1).max(128),
  projected_note_id: z.string().min(1).max(128),
  stable_id: z.string().min(20).max(128),
  kind: z.enum(['daily', 'unique']),
  date_key: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
  relative_path: canonicalVaultRelativePathSchema,
  title: z.string().min(1).max(512),
  content_hash: z.string().regex(/^[0-9a-f]{64}$/),
  revision: z.number().int().min(1),
  projection_state: z.enum(['pending', 'current', 'failed', 'conflict']),
  encoding: z.literal('utf-8'),
  newline: z.literal('lf'),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
}).strict()

export const overlayPageSchema = z.object({
  overlay: overlayNoteSchema,
  note: vaultNoteSchema,
  blocks: z.array(vaultBlockSchema),
  tasks: z.array(vaultTaskSchema),
  outgoing_links: z.array(vaultLinkSchema),
  backlinks: z.array(vaultLinkSchema),
  graph: vaultGraphSchema.nullable(),
}).strict()
```

Refactor the existing inline `vaultPageSchema.note` object into an exported
`vaultNoteSchema`, and the existing `z.array(z.unknown())` task member into an
exported `vaultTaskSchema = z.unknown()`. Reuse the already exported
`vaultBlockSchema`, `vaultLinkSchema`, and `vaultGraphSchema`. Rebuild
`vaultPageSchema` from these same exports so its accepted wire shape is
unchanged. Do not import or require `vaultFileSchema` from the overlay
contract.

- [ ] **Step 4: Add source authority to workspace serialization**

Backend:

```python
KnowledgeSourceAuthority = Literal["external-vault", "overlay"]

class KnowledgeTabState(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    vault_id: str = Field(min_length=1, max_length=128)
    note_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    relative_path: str = Field(min_length=1, max_length=4096)
    view_mode: KnowledgeViewMode
    source_authority: KnowledgeSourceAuthority = "external-vault"
```

Frontend:

```typescript
export type KnowledgeSourceAuthority = 'external-vault' | 'overlay'

export interface KnowledgeTab {
  id: string
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode: KnowledgeViewMode
  sourceAuthority: KnowledgeSourceAuthority
}

export interface OpenKnowledgeTab {
  vaultId: string
  noteId: string
  title: string
  relativePath: string
  viewMode?: KnowledgeViewMode
  sourceAuthority?: KnowledgeSourceAuthority
}
```

`knowledgeTabWireSchema` uses
`source_authority: knowledgeSourceAuthoritySchema.default('external-vault')`.
Serialization always writes the explicit field. `openTab` identity compares
`sourceAuthority`, `vaultId`, and `noteId`.

Use `vaultId: overlay.space_id` and `noteId: overlay.id` for overlay tabs.
`sourceAuthority` decides the API; the `vaultId` string does not grant authority.

- [ ] **Step 5: Implement hooks and exact invalidation**

```typescript
export const overlayKeys = {
  all: ['overlay'] as const,
  notes: ['overlay', 'notes'] as const,
  page: (id: string) => ['overlay', 'notes', id] as const,
}

export function useTodayOverlayNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (dateKey: string) => overlayApi.daily(dateKey),
    onSuccess: async (page) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: overlayKeys.notes }),
        client.setQueryData(overlayKeys.page(page.overlay.id), page),
        client.invalidateQueries({ queryKey: ['search'] }),
      ])
    },
  })
}
```

Create equivalent unique and update hooks. Update success replaces the exact
page cache and invalidates overlay notes, backlinks, graph, quick-switcher
catalog, and search.

- [ ] **Step 6: Run frontend and backend workspace tests**

Run:

```bash
uv run pytest -q \
  tests/test_knowledge_workspace_persistence.py \
  tests/test_knowledge_workspace_api.py
cd frontend
npx vitest run \
  src/lib/api/overlay.test.ts \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add \
  deeper_notebook/workspace/contracts.py \
  frontend/src/lib/api/overlay.ts \
  frontend/src/lib/api/overlay.test.ts \
  frontend/src/lib/hooks/use-overlay.ts \
  frontend/src/lib/api/knowledge-workspace.ts \
  frontend/src/lib/api/knowledge-workspace.test.ts \
  frontend/src/lib/stores/knowledge-workspace-store.ts \
  frontend/src/lib/stores/knowledge-workspace-store.test.ts \
  tests/test_knowledge_workspace_persistence.py
git commit -m "feat(knowledge): distinguish overlay tab authority"
```

---

### Task 7: Add Today, Unique Note, and Overlay Navigation

**Files:**
- Create: `frontend/src/components/overlay/OverlayUtilityPanel.tsx`
- Create: `frontend/src/components/overlay/OverlayUtilityPanel.test.tsx`
- Create: `frontend/src/components/overlay/CreateUniqueNoteDialog.tsx`
- Create: `frontend/src/components/overlay/CreateUniqueNoteDialog.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeQuickSwitcher.tsx`
- Modify: `frontend/src/lib/commands/knowledge-command-catalog.ts`
- Modify: `frontend/src/lib/commands/knowledge-command-catalog.test.ts`
- Modify: `frontend/src/lib/locales/*/index.ts`

**Interfaces:**
- Produces: visible Overlay root, Today action, unique-note dialog, overlay file selection, and command/quick-switcher candidates.
- Consumes: overlay hooks and authority-aware `openTab`.

- [ ] **Step 1: Write creation and authority tests**

```typescript
// OverlayUtilityPanel.test.tsx
it('opens the one returned daily note as an overlay tab', async () => {
  render(<OverlayUtilityPanel onOpen={onOpen} />)
  await user.click(screen.getByRole('button', { name: 'Today' }))
  await waitFor(() => expect(mockDaily).toHaveBeenCalledWith(localDateKey()))
  expect(onOpen).toHaveBeenCalledWith({
    sourceAuthority: 'overlay',
    vaultId: 'overlay_space:default',
    noteId: 'overlay_note:daily',
    title: '2026-07-29',
    relativePath: 'Daily/2026-07-29.md',
    viewMode: 'source',
  })
})

it('does not call any vault mutation while creating overlay notes', async () => {
  render(<OverlayUtilityPanel onOpen={onOpen} />)
  await user.click(screen.getByRole('button', { name: 'Today' }))
  expect(mockVaultScan).not.toHaveBeenCalled()
  expect(mockApiCalls.some(({ url }) => url.includes('/vaults/'))).toBe(false)
})
```

```typescript
// CreateUniqueNoteDialog.test.tsx
it('trims the title, sends one idempotency key, and opens the result', async () => {
  render(<CreateUniqueNoteDialog open onOpenChange={vi.fn()} onOpen={onOpen} />)
  await user.type(screen.getByLabelText('Title'), '  Research Idea  ')
  await user.click(screen.getByRole('button', { name: 'Create note' }))
  expect(mockCreate).toHaveBeenCalledWith({
    title: 'Research Idea',
    idempotencyKey: expect.stringMatching(/^unique-/),
  })
  expect(onOpen).toHaveBeenCalledTimes(1)
})
```

Add Knowledge Explorer tests that prove:

- overlay renders even when no external mounts exist;
- external mount scan remains disabled when overlay is selected;
- overlay and external trees preserve their badges;
- overlay note selection uses `sourceAuthority: "overlay"`;
- quick switcher ranks overlay and external notes without collapsing identical
  IDs or titles;
- slash and command palette include Today/New Unique Note but no external write.

- [ ] **Step 2: Run focused component tests and verify RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/overlay/OverlayUtilityPanel.test.tsx \
  src/components/overlay/CreateUniqueNoteDialog.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/lib/commands/knowledge-command-catalog.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: overlay components and commands are absent.

- [ ] **Step 3: Implement the utility panel and dialog**

Use one mapping helper:

```typescript
export function tabFromOverlay(page: OverlayPage): OpenKnowledgeTab {
  return {
    sourceAuthority: 'overlay',
    vaultId: page.overlay.space_id,
    noteId: page.overlay.id,
    title: page.overlay.title,
    relativePath: page.overlay.relative_path,
    viewMode: 'source',
  }
}
```

`OverlayUtilityPanel` lists overlay notes grouped under Daily and Notes. Today
uses a locale-independent local date-key helper:

```typescript
export function localDateKey(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
```

The unique dialog allocates one request ID when opened and reuses it across
safe mutation retries. Closing and reopening allocates a new ID.

- [ ] **Step 4: Integrate without mixing selected authority**

`KnowledgeExplorer` maintains:

```typescript
type SelectedKnowledgeRoot =
  | { authority: 'overlay'; id: 'overlay_space:default' }
  | { authority: 'external-vault'; id: string }
```

The scan button renders only for `external-vault`. Overlay loading errors do not
hide healthy external mounts, and external mount errors do not hide overlay.

Add command definitions:

```typescript
{
  id: 'knowledge.overlay.today',
  safety: 'workspace',
  labelKey: 'knowledge.overlay.today',
  execute: (context) => context.openTodayOverlay(),
}
{
  id: 'knowledge.overlay.unique',
  safety: 'workspace',
  labelKey: 'knowledge.overlay.newUnique',
  execute: (context) => context.openUniqueOverlayDialog(),
}
```

- [ ] **Step 5: Add exact locale keys**

Add the same key shape in all locales:

```typescript
overlay: {
  name: 'Deeper Notebook Overlay',
  writable: 'Writable app-owned note',
  today: 'Today',
  newUnique: 'New unique note',
  uniqueTitle: 'Unique note title',
  create: 'Create note',
  creating: 'Creating note…',
  empty: 'No overlay notes yet',
  loadError: 'Overlay notes could not be loaded.',
  createError: 'The overlay note could not be created.',
}
```

Use accurate translations rather than copying English into non-English locale
files. Extend the locale parity test to assert this exact leaf set.

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
cd frontend
npx vitest run \
  src/components/overlay/OverlayUtilityPanel.test.tsx \
  src/components/overlay/CreateUniqueNoteDialog.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  src/lib/commands/knowledge-command-catalog.test.ts \
  src/lib/locales/index.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: all selected tests pass.

Commit:

```bash
git add \
  frontend/src/components/overlay \
  frontend/src/components/vault/KnowledgeExplorer.tsx \
  frontend/src/components/vault/KnowledgeExplorer.test.tsx \
  frontend/src/components/vault/KnowledgeQuickSwitcher.tsx \
  frontend/src/lib/commands/knowledge-command-catalog.ts \
  frontend/src/lib/commands/knowledge-command-catalog.test.ts \
  frontend/src/lib/locales
git commit -m "feat(knowledge): create daily and unique notes"
```

---

### Task 8: Add Revision-Safe Overlay Editing

**Files:**
- Create: `frontend/src/components/overlay/OverlaySourceEditor.tsx`
- Create: `frontend/src/components/overlay/OverlaySourceEditor.test.tsx`
- Create: `frontend/src/components/overlay/OverlayDocumentView.tsx`
- Create: `frontend/src/components/overlay/OverlayDocumentView.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgePaneContent.tsx`
- Modify: `frontend/src/components/vault/KnowledgePaneContent.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeTabStrip.tsx`
- Modify: `frontend/src/components/vault/KnowledgeTabStrip.test.tsx`
- Modify: `frontend/src/components/vault/vault.css`
- Modify: `frontend/src/lib/locales/*/index.ts`

**Interfaces:**
- Produces: editable overlay Source mode, explicit Save, dirty state, optimistic revision conflict UI, and overlay authority badge.
- Consumes: `useOverlayPage`, `useUpdateOverlayNote`, existing Reading/Live Preview/Graph renderers, and workspace view-mode state.

- [ ] **Step 1: Write editable-isolation tests**

```typescript
// OverlaySourceEditor.test.tsx
it('accepts local edits and reports the current document', async () => {
  const onChange = vi.fn()
  render(
    <OverlaySourceEditor
      ariaLabel="Research source"
      markdown="# Research\n"
      onChange={onChange}
    />,
  )
  const editor = screen.getByRole('textbox', { name: 'Research source' })
  expect(editor).toHaveAttribute('aria-readonly', 'false')
  await user.click(editor)
  await user.keyboard('{End}Changed')
  expect(onChange).toHaveBeenLastCalledWith(expect.stringContaining('Changed'))
})

it('does not change the locked external editor contract', () => {
  render(
    <VaultCodeMirror
      ariaLabel="External source"
      markdown="unchanged"
      extensions={[]}
    />,
  )
  expect(screen.getByRole('textbox', { name: 'External source' }))
    .toHaveAttribute('aria-readonly', 'true')
})
```

```typescript
// OverlayDocumentView.test.tsx
it('saves with the loaded revision and updates only after success', async () => {
  render(<OverlayDocumentView page={pageAtRevision3} mode="source" />)
  await editMarkdown('# Changed\n')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(mockUpdate).toHaveBeenCalledWith({
    noteId: pageAtRevision3.overlay.id,
    title: pageAtRevision3.overlay.title,
    markdown: '# Changed\n',
    expectedRevision: 3,
    idempotencyKey: expect.stringMatching(/^save-/),
  })
  expect(await screen.findByText('Revision 4')).toBeInTheDocument()
})

it('keeps the draft on conflict and never retries as an overwrite', async () => {
  mockUpdate.mockRejectedValue(new OverlayApiError('overlay_revision_conflict'))
  render(<OverlayDocumentView page={pageAtRevision3} mode="source" />)
  await editMarkdown('# Local draft\n')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('changed elsewhere')
  expect(currentEditorText()).toBe('# Local draft\n')
  expect(mockUpdate).toHaveBeenCalledTimes(1)
})
```

Add pane tests proving an external tab never mounts `OverlaySourceEditor` and an
overlay tab never calls `vaultApi.page`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/overlay/OverlaySourceEditor.test.tsx \
  src/components/overlay/OverlayDocumentView.test.tsx \
  src/components/vault/KnowledgePaneContent.test.tsx \
  src/components/vault/KnowledgeTabStrip.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: overlay editors and authority-directed pane rendering are absent.

- [ ] **Step 3: Implement an independent editable CodeMirror**

`OverlaySourceEditor` may share pure theme and Markdown extensions, but it must
not import `lockedExtensions` or alter `VaultCodeMirror`.

```typescript
export interface OverlaySourceEditorProps {
  ariaLabel: string
  markdown: string
  onChange: (markdown: string) => void
  disabled?: boolean
}
```

Its core extensions include:

```typescript
EditorState.readOnly.of(false),
EditorView.editable.of(true),
EditorView.contentAttributes.of({
  role: 'textbox',
  'aria-multiline': 'true',
  'aria-readonly': 'false',
}),
EditorView.updateListener.of((update) => {
  if (update.docChanged) onChangeRef.current(update.state.doc.toString())
}),
history(),
keymap.of([
  ...defaultKeymap,
  ...historyKeymap,
  { key: 'Mod-f', run: openSearchPanel },
  { key: 'F3', run: findNext },
  { key: 'Shift-F3', run: findPrevious },
  ...foldKeymap,
]),
```

External prop updates use a transaction annotation and do not emit `onChange`.

- [ ] **Step 4: Implement overlay document state**

`OverlayDocumentView`:

- initializes draft text and title from the loaded page;
- derives dirty state from loaded content hash plus local draft fingerprint;
- uses one idempotency key per Save attempt;
- disables Save when clean or pending;
- keeps the draft on every failure;
- accepts the returned page as the new revision only after success;
- resets from a new server page only when the local draft is clean;
- presents a conflict action to reload the server revision in a confirmation
  dialog; it never force-overwrites;
- reuses `VaultMarkdown`, `VaultLivePreview`, `VaultGraph`, outline, properties,
  and links for non-Source modes;
- shows `Revision N`, projection state, and a writable overlay badge.

- [ ] **Step 5: Route panes by explicit authority**

In `KnowledgePaneContent`:

```typescript
const isOverlay = activeTab?.sourceAuthority === 'overlay'
const overlayPage = useOverlayPage(isOverlay ? noteId : undefined)
const vaultPage = useVaultPage(
  isOverlay ? undefined : vaultId,
  isOverlay ? undefined : noteId,
)
```

Never choose the API by ID prefix. The authority discriminant is the only
router. Graph and link hooks follow the same rule.

`KnowledgeTabStrip` renders text and icon badges for overlay versus external;
color alone is insufficient.

- [ ] **Step 6: Add locale and style contracts**

Add keys for Save, Saving, Saved, dirty draft, revision, projection pending,
projection failed, reload confirmation, conflict, writable overlay, and
external read-only. Add Research Core focus, dirty, conflict, and badge styles
without hard-coded light-only colors.

- [ ] **Step 7: Run component, locale, and build tests**

Run:

```bash
cd frontend
npx vitest run \
  src/components/overlay/OverlaySourceEditor.test.tsx \
  src/components/overlay/OverlayDocumentView.test.tsx \
  src/components/vault/KnowledgePaneContent.test.tsx \
  src/components/vault/KnowledgeTabStrip.test.tsx \
  src/components/vault/VaultCodeMirror.test.tsx \
  src/components/vault/VaultSourceView.test.tsx \
  src/lib/locales/index.test.ts \
  --pool=forks --maxWorkers=1
npm run lint
npm run build
```

Expected: all tests pass, ESLint exits 0, and Next.js production build succeeds.

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/src/components/overlay \
  frontend/src/components/vault/KnowledgePaneContent.tsx \
  frontend/src/components/vault/KnowledgePaneContent.test.tsx \
  frontend/src/components/vault/KnowledgeTabStrip.tsx \
  frontend/src/components/vault/KnowledgeTabStrip.test.tsx \
  frontend/src/components/vault/vault.css \
  frontend/src/lib/locales
git commit -m "feat(knowledge): edit owned overlay notes safely"
```

---

### Task 9: Prove Full Regression, External Immutability, and Native Restart

**Files:**
- Create: `frontend/e2e/knowledge-overlay-foundation.spec.ts`
- Modify: `frontend/e2e/fixtures/knowledge-editor-modes.ts`
- Create: `scripts/verify_overlay_foundation.py`
- Create: `docs/verification/2026-07-29-deeper-notebook-overlay-foundation.md`
- Modify: `scripts/rebrand-allowlist.json` only if exact line movement requires coordinate refresh

**Interfaces:**
- Produces: strict mocked-browser proof, controlled native proof script, source-fingerprint evidence, and completion record.
- Consumes: the complete Plan A implementation.

- [ ] **Step 1: Extend the strict mocked fixture**

The fixture must provide:

- one empty overlay;
- one synthetic read-only external vault;
- strict overlay create/read/update responses with revisions;
- external source fingerprints;
- an unexpected-request trap;
- zero external mutation routes.

Every successful overlay mutation updates only fixture-owned overlay state.
Any `PUT`, `PATCH`, or `DELETE` under `/vaults` fails the test immediately.

- [ ] **Step 2: Write the browser acceptance proof**

```typescript
// frontend/e2e/knowledge-overlay-foundation.spec.ts
test('creates and edits owned notes without touching external vaults', async ({ page }) => {
  await installStrictKnowledgeFixture(page)
  await page.goto('/knowledge')

  await page.getByRole('button', { name: 'Today' }).click()
  await expect(page.getByText('Writable app-owned note')).toBeVisible()
  await page.getByRole('textbox', { name: /source/i }).fill('# Today\n\nDraft')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Revision 2')).toBeVisible()

  await page.getByRole('button', { name: 'New unique note' }).click()
  await page.getByLabel('Unique note title').fill('Research Idea')
  await page.getByRole('button', { name: 'Create note' }).click()
  await expect(page.getByText(/20260729-\d{4} Research Idea/)).toBeVisible()

  await openExternalEvidenceNote(page)
  await expect(page.getByText('Read-only external file')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save' })).toHaveCount(0)

  expect(fixture.externalMutationRequests).toEqual([])
  expect(fixture.externalFingerprintsAfter).toEqual(fixture.externalFingerprintsBefore)
  expect(fixture.unexpectedRequests).toEqual([])
})
```

Add a second test for daily replay, unique collision suffixes, save conflict,
draft preservation, restart hydration, and focus restoration.

- [ ] **Step 3: Write the controlled native verifier**

`scripts/verify_overlay_foundation.py` accepts only:

```text
--api-url
--auth-token-file
--overlay-data-root
--external-fixture-root
--report-path
--check
```

`--check` is the default and performs no mutation. The mutating proof requires
`--run-controlled-proof` plus an overlay root created by the verifier beneath a
caller-supplied disposable directory. It refuses:

- the real Deeper Notebook data root;
- `/`, a home directory, Desktop, Documents, or `/Users`;
- the actual `2nd Brains` root;
- a symlink or broad parent;
- an API whose reported instance nonce does not match the verifier session.

The report contains relative overlay paths, hashes, revisions, request IDs,
external before/after hashes, Git-status digest, route audit, and pass/fail
states. It contains no note contents, auth token, or absolute private-vault
root.

- [ ] **Step 4: Run focused backend and frontend suites**

Run:

```bash
uv run pytest -q \
  tests/test_overlay_contracts.py \
  tests/test_overlay_migration.py \
  tests/test_overlay_paths.py \
  tests/test_overlay_storage.py \
  tests/test_overlay_repository.py \
  tests/test_overlay_service.py \
  tests/test_overlay_api.py \
  tests/test_vault_security.py \
  tests/test_vault_note_read_only.py \
  tests/test_knowledge_workspace_persistence.py \
  tests/test_knowledge_workspace_api.py

cd frontend
npx vitest run \
  src/lib/api/overlay.test.ts \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts \
  src/components/overlay \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/KnowledgePaneContent.test.tsx \
  src/components/vault/KnowledgeTabStrip.test.tsx \
  src/components/vault/VaultCodeMirror.test.tsx \
  src/lib/locales/index.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: all selected tests pass.

- [ ] **Step 5: Run full automated gates**

Run:

```bash
uv run pytest -q
cd frontend
npm test
npm run lint
npm run build
npm run test:e2e:mocked
cd ..
uv run python scripts/rebrand_audit.py --check
git diff --check
```

Expected: zero failed tests, zero lint errors, successful production build,
mocked-browser proof green, rebrand audit green, and clean diff check.

- [ ] **Step 6: Inspect authority and write-path safety**

Run:

```bash
rg -n \
  'vaultApi\\.(update|delete|rename|move|write|save)|/vaults/.*/(write|save|rename|move|delete)|contenteditable=.true.' \
  frontend/src api deeper_notebook

rg -n \
  'write_text|write_bytes|os\\.replace|Path\\.replace|unlink|rename' \
  deeper_notebook/overlay api/routers/overlay.py
```

Expected:

- the first search has no external-vault mutation client or route;
- editable content exists only under overlay components;
- every overlay filesystem mutation is confined to `OverlayStorage` or its
  exact receipt/snapshot helper;
- no caller-provided absolute path reaches those methods.

- [ ] **Step 7: Run the controlled native macOS restart proof**

1. Build or launch the exact feature commit with a disposable data root.
2. Start the owned API and SurrealDB runtime and record exact PIDs and instance
   nonce.
3. Create a descriptor-safe synthetic external vault and record hashes/Git
   status.
4. Create/reopen the same daily note.
5. Create two same-minute unique notes and prove `-2`.
6. Edit and save one overlay note, inject one stale-revision conflict, and prove
   the local draft survives.
7. Restart the native app and prove tabs, overlay files, revisions, and
   projection survive.
8. Verify the external fixture hashes and Git status are unchanged.
9. Stop only the exact owned runtime PIDs.
10. Record that real Windows packaged proof remains open.

- [ ] **Step 8: Write the verification record**

The record must include:

- tested commit;
- exact commands and exit codes;
- focused and full test totals;
- migration up/down/up evidence;
- browser proof result;
- overlay source hashes/revisions;
- external before/after fingerprint equality;
- route/write-path audit;
- native PID/nonce ownership and shutdown evidence;
- non-blocking warnings;
- open Windows gate;
- explicit statement that templates, scripts, Composer, bookmarks, Random Note,
  metrics, named workspaces, protected write-back, Canvas, Bases, plugins,
  Sync/Publish, and mobile remain outside Plan A.

- [ ] **Step 9: Commit proof artifacts**

```bash
git add \
  frontend/e2e/knowledge-overlay-foundation.spec.ts \
  frontend/e2e/fixtures/knowledge-editor-modes.ts \
  scripts/verify_overlay_foundation.py \
  docs/verification/2026-07-29-deeper-notebook-overlay-foundation.md \
  scripts/rebrand-allowlist.json
git commit -m "test(overlay): prove owned note isolation"
```

---

## Plan A Completion Gate

Plan A is ready for review only when:

- the app-owned overlay has an explicit authority distinct from external vaults;
- canonical Markdown lives only beneath the versioned overlay root;
- global daily creation is idempotent across concurrency and restart;
- unique-note collisions use deterministic suffixes and never replace a file;
- create/update operations are atomic, revision-checked, fingerprinted,
  receipt-backed, and recoverable;
- overlay projection supplies Reading, links, tasks, tags, backlinks, graph, and
  search data without creating a writable external vault;
- overlay Source mode is editable and external Source/Live Preview remain
  locked;
- old workspace documents load with external authority and new documents
  serialize authority explicitly;
- the browser and native proofs show zero external-vault writes and unchanged
  external fingerprints;
- full backend, frontend, locale, lint, build, mocked-browser, rebrand, and diff
  gates pass;
- real Windows packaged proof remains explicitly open.

## Follow-on Plans

After Plan A is reviewed and merged, write and execute separate plans in this
order:

1. Markdown safe-variable templates plus restricted JavaScript and Python
   runtime adapters, trust fingerprints, quarantine, receipts, and adversarial
   sandbox proof.
2. Quick Capture and source-grounded AI Composer with preview-only AI output,
   draft autosave, explicit insertion, and explicit Save.
3. Global bookmark folders/tags, Random Note across overlay and mounted notes,
   Unicode document metrics, and named workspace management.
4. Cross-authority global graph/link resolution and the final combined native
   release proof for the complete approved overlay-productivity specification.
