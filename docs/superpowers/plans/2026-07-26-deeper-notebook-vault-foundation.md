# Deeper Notebook Read-Only Vault Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount the existing Obsidian and Logseq Second Brain as a read-only, live-indexed knowledge workspace inside Deeper Notebook with portable Markdown as the source of truth, durable provenance, backlinks, blocks, tasks, explorer views, and a local graph.

**Architecture:** Introduce a bounded `deeper_notebook.vault` domain. Explicitly approved local roots are observed using Capture Inbox’s stability and containment principles, parsed into a rebuildable SurrealDB projection, and committed with append-only receipts. Canonical files are never modified. Parsed pages are represented as externally canonical notes so existing full-text/vector search and grounded AI can reuse them. New link, block, task, and trust records power the explorer, backlinks, and graph without overloading notebook membership relations.

**Tech Stack:** Python 3.11-3.12, Pydantic v2, PyYAML, FastAPI, SurrealDB, watchdog, Next.js 15, React 19, TanStack Query, React Flow, Zod, Vitest, pytest.

**Depends on:**

- Approved design in `docs/superpowers/specs/2026-07-26-deeper-notebook-second-brain-design.md`.
- Completion of `docs/superpowers/plans/2026-07-26-deeper-notebook-rebrand.md`; all paths below assume `deeper_notebook` is canonical.

---

## Global Constraints

- The reference root is `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains`.
- Phase 1 is read-only. Do not add update, delete, move, rename, serialize, or write-back endpoints.
- Do not modify, stage, commit, lock, or repair the reference vault’s Git repository.
- Do not invoke the `brain-engine` Ralph loop.
- Do not follow symlinks outside an approved root.
- Do not log file content, secrets, absolute user-home paths in exported diagnostics, or frontmatter values classified as secrets.
- A newer parse failure advances only `vault_file` invalid/stale provenance while preserving the last valid note graph; older failures are superseded and equal-timestamp hash conflicts require reconciliation.
- A database failure never falls through to an external file write; Phase 1 has no external write path.
- Durable projection completion and embedding completion are separate states.
- Do not merge pages merely because normalized titles match across Obsidian and Logseq.
- Preserve existing notebook `artifact` and source `reference` relationship meanings.
- Keep `sources/`, `inbox/raw/`, `brain-engine/**`, and generated connector output protected and unmodified.

## File Map

**Create**

- `deeper_notebook/database/migrations/32.surrealql`
- `deeper_notebook/database/migrations/32_down.surrealql`
- `deeper_notebook/vault/__init__.py`
- `deeper_notebook/vault/contracts.py`
- `deeper_notebook/vault/repository.py`
- `deeper_notebook/vault/security.py`
- `deeper_notebook/vault/parsers/__init__.py`
- `deeper_notebook/vault/parsers/common.py`
- `deeper_notebook/vault/parsers/markdown.py`
- `deeper_notebook/vault/parsers/obsidian.py`
- `deeper_notebook/vault/parsers/logseq.py`
- `deeper_notebook/vault/watcher.py`
- `deeper_notebook/vault/service.py`
- `deeper_notebook/vault/trust.py`
- `api/schemas/vault.py`
- `api/routers/vault.py`
- `tests/fixtures/vault/obsidian/**`
- `tests/fixtures/vault/logseq/**`
- `tests/fixtures/vault/mixed/**`
- `tests/test_vault_migration.py`
- `tests/test_vault_parsers.py`
- `tests/test_vault_security.py`
- `tests/test_vault_watcher.py`
- `tests/test_vault_repository.py`
- `tests/test_vault_service.py`
- `tests/test_vault_api.py`
- `tests/integration/test_vault_projection.py`
- `frontend/src/lib/api/vault.ts`
- `frontend/src/lib/hooks/use-vault.ts`
- `frontend/src/lib/api/vault.test.ts`
- `frontend/src/lib/hooks/use-vault.test.tsx`
- `frontend/src/app/(dashboard)/knowledge/page.tsx`
- `frontend/src/components/vault/VaultWorkspace.tsx`
- `frontend/src/components/vault/VaultExplorer.tsx`
- `frontend/src/components/vault/VaultPageReader.tsx`
- `frontend/src/components/vault/BacklinksPanel.tsx`
- `frontend/src/components/vault/VaultGraph.tsx`
- `frontend/src/components/vault/VaultStatusCard.tsx`
- `frontend/src/components/vault/*.test.tsx`
- `scripts/verify_read_only_vault.py`
- `tests/test_verify_read_only_vault.py`

**Modify**

- `pyproject.toml`
- `deeper_notebook/domain/notebook.py`
- `deeper_notebook/utils/context_builder.py`
- `api/main.py`
- `api/models.py`
- `api/routers/search.py`
- `frontend/src/lib/api/search.ts`
- Search result and grounded-citation components.
- `frontend/src/components/layout/AppSidebar.tsx`
- `frontend/src/lib/types/api.ts`
- All locale files for the new Knowledge navigation and status strings.
- Search response/result mapping where mounted-note provenance is surfaced.

---

### Task 1: Define Vault Contracts and the SurrealDB Projection

**Files:**

- Create: `deeper_notebook/vault/contracts.py`
- Create: `deeper_notebook/database/migrations/32.surrealql`
- Create: `deeper_notebook/database/migrations/32_down.surrealql`
- Create: `tests/test_vault_migration.py`
- Create: `tests/integration/test_vault_projection.py`
- Modify: `deeper_notebook/domain/notebook.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing migration contract tests**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/32.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/32_down.surrealql"


def test_vault_migration_is_present_and_idempotent():
    sql = UP.read_text()
    for table in (
        "vault_mount",
        "vault_file",
        "note_block",
        "note_link",
        "knowledge_task",
        "vault_sync_receipt",
        "vault_trust_record",
    ):
        assert f"DEFINE TABLE IF NOT EXISTS {table}" in sql
    assert "DEFINE FIELD IF NOT EXISTS vault_id ON TABLE note" in sql


def test_vault_down_migration_removes_only_vault_schema():
    sql = DOWN.read_text()
    assert "REMOVE TABLE IF EXISTS vault_mount" in sql
    assert "REMOVE TABLE IF EXISTS note" not in sql
    assert "REMOVE FIELD IF EXISTS vault_id ON TABLE note" in sql
```

- [ ] **Step 2: Run and confirm RED**

Run:

```bash
uv run pytest tests/test_vault_migration.py tests/test_migration_discovery.py -q
```

Expected: migration 32 is missing.

- [ ] **Step 3: Add direct parser dependencies**

Add direct project dependencies so production does not rely on transitive packages:

```toml
"pyyaml>=6.0.3,<7",
"markdown-it-py>=4.0.0,<5",
```

Regenerate `uv.lock` once and review the dependency diff.

- [ ] **Step 4: Define strict Pydantic contracts**

Use these public types:

```python
VaultFormat = Literal["obsidian", "logseq", "mixed", "markdown"]
VaultState = Literal[
    "disconnected",
    "scanning",
    "ready-read-only",
    "ready-write-enabled",
    "stale",
    "conflict",
    "degraded",
    "unavailable",
]
VaultFileState = Literal[
    "pending", "parsed", "unsupported", "invalid", "conflict", "missing"
]
TaskStatus = Literal["todo", "doing", "done", "canceled", "unknown"]


class ParsedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parser_id: str
    parent_parser_id: str | None = None
    position: int = Field(ge=0)
    stable_source_id: str | None = None
    block_kind: str
    markdown: str
    plain_text: str
    properties: dict[str, Any] = Field(default_factory=dict)
    task_state: TaskStatus | None = None
    heading_path: list[str] = Field(default_factory=list)
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class ParsedLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_block_parser_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: Literal["wikilink", "markdown", "embed", "tag", "block-ref"]
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class ParsedTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_parser_id: str
    status: TaskStatus
    scheduled: date | None = None
    due: date | None = None
    completed: date | None = None
    priority: str | None = None
    recurrence: str | None = None
    tags: list[str] = Field(default_factory=list)


class ParsedEmbed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_block_parser_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str
    source_format: VaultFormat
    title: str
    markdown: str
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    blocks: list[ParsedBlock] = Field(default_factory=list)
    links: list[ParsedLink] = Field(default_factory=list)
    tasks: list[ParsedTask] = Field(default_factory=list)
    embeds: list[ParsedEmbed] = Field(default_factory=list)
    content_hash: str
    encoding: str = "utf-8"
    newline: Literal["lf", "crlf", "mixed", "none"]
```

Source spans are zero-based byte offsets into the original file bytes, not rendered-text offsets.

- [ ] **Step 5: Add migration 32**

Use `SCHEMAFULL`, `IF NOT EXISTS`, `schema_version`, UTC timestamps, and indexes. Required uniqueness:

```surql
DEFINE INDEX IF NOT EXISTS idx_vault_mount_root ON TABLE vault_mount COLUMNS root_path UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_vault_file_path ON TABLE vault_file COLUMNS vault_id, relative_path UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_note_vault_file ON TABLE note COLUMNS vault_file_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_note_block_parser ON TABLE note_block COLUMNS vault_file_id, parser_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_note_link_span ON TABLE note_link COLUMNS source_note_id, source_start, source_end UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_task_block ON TABLE knowledge_task COLUMNS block_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_vault_receipt_operation ON TABLE vault_sync_receipt COLUMNS operation_id, vault_file_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_vault_trust_manifest ON TABLE vault_trust_record COLUMNS vault_id, manifest_relative_path, manifest_id UNIQUE;
```

Add optional note fields:

```surql
DEFINE FIELD IF NOT EXISTS vault_id ON TABLE note TYPE option<record<vault_mount>>;
DEFINE FIELD IF NOT EXISTS vault_file_id ON TABLE note TYPE option<record<vault_file>>;
DEFINE FIELD IF NOT EXISTS source_format ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS canonical_external ON TABLE note TYPE option<bool>;
DEFINE FIELD IF NOT EXISTS properties ON TABLE note FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS tags ON TABLE note TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS source_hash ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS external_state ON TABLE note TYPE option<string>;
```

`vault_mount` gains optional `parent_vault_id`; the mixed parent is organizational and has `watch_enabled=false`. `vault_file` missing records remain present with `deleted_state="missing"`.

- [ ] **Step 6: Extend `Note` without changing normal notes**

```python
class Note(ObjectModel):
    vault_id: str | None = None
    vault_file_id: str | None = None
    source_format: str | None = None
    canonical_external: bool | None = None
    properties: dict[str, Any] | None = None
    tags: list[str] | None = None
    source_hash: str | None = None
    external_state: str | None = None
```

Normal note create/update APIs leave these fields unset. Enforce read-only
protection in the `Note` domain boundary, not only the new UI:

- `Note.save()` rejects caller-driven changes to an already persisted external note unless an unforgeable internal projection context is active.
- `Note.delete()` rejects external notes.
- `Note.add_to_notebook()` rejects external notes so a later notebook cascade cannot delete a canonical projection.
- Existing `PUT /notes/{id}` and `DELETE /notes/{id}` map the domain error to HTTP 409 `external_note_read_only`.

Tests exercise direct domain calls, both generic note API mutations, notebook
membership, and notebook cascade behavior. The vault repository alone receives
the private projection capability used to refresh these records.

- [ ] **Step 7: Run checks and commit**

Run:

```bash
uv run pytest tests/test_vault_migration.py tests/test_migration_discovery.py tests/test_v0_7_176_migration_idempotency.py tests/test_notes_api.py -q
SURREAL_INTEGRATION=1 uv run pytest tests/integration/test_vault_projection.py -q -k migration
uv run ruff check deeper_notebook/vault/contracts.py tests/test_vault_migration.py
```

Commit:

```bash
git add pyproject.toml uv.lock deeper_notebook/database/migrations/32* deeper_notebook/vault/contracts.py deeper_notebook/domain/notebook.py tests/test_vault_migration.py tests/integration/test_vault_projection.py tests/test_notes_api.py
git commit -m "feat(vault): define read-only projection schema"
```

---

### Task 2: Implement Safe Obsidian, Logseq, and Neutral Markdown Parsers

**Files:**

- Create: `deeper_notebook/vault/parsers/__init__.py`
- Create: `deeper_notebook/vault/parsers/common.py`
- Create: `deeper_notebook/vault/parsers/markdown.py`
- Create: `deeper_notebook/vault/parsers/obsidian.py`
- Create: `deeper_notebook/vault/parsers/logseq.py`
- Create: `tests/fixtures/vault/**`
- Create: `tests/test_vault_parsers.py`

- [ ] **Step 1: Add golden fixtures**

Fixtures must include:

- Typed YAML frontmatter: string, number, bool, null, date string, list, nested object.
- Obsidian `[[Page]]`, `[[Page|Alias]]`, `[[Page#Heading]]`, `[[Page^block-id]]`, `![[embed]]`.
- Markdown links, tags, headings, explicit block IDs, callouts, footnotes, attachments.
- Logseq indentation, page properties, block properties, `((block-uuid))`, namespaces, journals, tasks, scheduling/deadline markers, embeds.
- LF, CRLF, mixed newlines, UTF-8 BOM, malformed YAML, unknown syntax, and a size-limit fixture.

- [ ] **Step 2: Write failing parser tests**

```python
def test_obsidian_parser_preserves_links_blocks_and_frontmatter():
    raw = fixture_bytes("obsidian/complete.md")
    parsed = parse_document("complete.md", raw, format_mode="obsidian")
    assert parsed.properties["aliases"] == ["Complete note", "Reference"]
    assert {link.target_text for link in parsed.links} >= {"Research", "Methods"}
    assert any(block.stable_source_id == "claim-1" for block in parsed.blocks)
    assert sha256(raw).hexdigest() == parsed.content_hash


def test_logseq_parser_preserves_hierarchy_and_task_semantics():
    parsed = parse_document(
        "journals/2026_07_26.md",
        fixture_bytes("logseq/journal.md"),
        format_mode="logseq",
    )
    assert parsed.blocks[1].parent_parser_id == parsed.blocks[0].parser_id
    assert parsed.tasks[0].status == "todo"
    assert parsed.tasks[0].scheduled == date(2026, 7, 27)


def test_parse_is_read_only_and_deterministic(tmp_path):
    path = copy_fixture(tmp_path, "obsidian/complete.md")
    before = path.read_bytes()
    first = parse_document(path.name, before, format_mode="obsidian")
    second = parse_document(path.name, path.read_bytes(), format_mode="obsidian")
    assert path.read_bytes() == before
    assert first == second
```

- [ ] **Step 3: Implement bounded byte decoding**

Maximum Markdown size defaults to 10 MiB and is configurable via `DN_VAULT_MAX_MARKDOWN_BYTES`. Accept UTF-8 and UTF-8 BOM. Unsupported encodings return a typed `VaultParseError("unsupported_encoding")`; do not guess or transcode in Phase 1.

- [ ] **Step 4: Implement YAML parsing safely**

Use `yaml.safe_load`, require a mapping at the root, cap frontmatter to 256 KiB and nesting depth to 20, and normalize only JSON-safe values. Dates remain ISO strings in the projection. YAML constructors capable of instantiating Python objects are forbidden.

- [ ] **Step 5: Implement deterministic block and link extraction**

Use Markdown-It tokens for neutral block boundaries and format-specific scanners for syntax Markdown-It does not understand. Parser IDs are:

```python
parser_id = sha256(
    f"{relative_path}\0{parent_id or ''}\0{position}\0{block_kind}\0{markdown}".encode()
).hexdigest()[:24]
```

Explicit Obsidian block IDs and Logseq UUIDs populate `stable_source_id`. Unknown syntax stays in block Markdown. Do not render or serialize source text.

- [ ] **Step 6: Implement format detection**

Rules:

1. Explicit mount mode `obsidian`, `logseq`, or `markdown` wins.
2. In `mixed`, files under `Obsidian Brain/` use Obsidian.
3. In `mixed`, files under `Logseq Brain/pages` or `Logseq Brain/journals` use Logseq.
4. Otherwise use neutral Markdown.

- [ ] **Step 7: Run parser proof and commit**

Run:

```bash
uv run pytest tests/test_vault_parsers.py -q
uv run ruff check deeper_notebook/vault/parsers tests/test_vault_parsers.py
```

Commit:

```bash
git add deeper_notebook/vault/parsers tests/fixtures/vault tests/test_vault_parsers.py
git commit -m "feat(vault): parse Obsidian and Logseq markdown"
```

---

### Task 3: Enforce Approved-Root and Read-Only Filesystem Boundaries

**Files:**

- Create: `deeper_notebook/vault/security.py`
- Create: `deeper_notebook/vault/watcher.py`
- Create: `tests/test_vault_security.py`
- Create: `tests/test_vault_watcher.py`
- Modify: `deeper_notebook/capture/watcher.py` only to extract reusable, behavior-preserving helpers if necessary.

- [ ] **Step 1: Write failing containment tests**

Prove:

- Roots must exist, be absolute after expansion, and not be system roots.
- A candidate must remain under the same canonical root after resolution.
- Symlink files and directories are not followed.
- Hidden control directories are classified, not indexed as notes.
- Temporary files are ignored.
- Files require two stable observations at least two seconds apart.
- An event storm produces one path/hash work item.
- Deletion emits `missing`; it does not delete a projection.
- No test invokes `write_text`, `replace`, `unlink`, `rename`, `mkdir`, or chmod on a source candidate after fixture setup.

- [ ] **Step 2: Implement immutable root policy**

```python
PROTECTED_GLOBS = (
    "sources/**",
    "inbox/raw/**",
    "brain-engine/**",
    ".git/**",
    ".obsidian/**",
    "logseq/**",
)
INDEXABLE_MARKDOWN = frozenset({".md", ".markdown"})
INDEXABLE_METADATA = frozenset({".canvas", ".base"})
TEMPORARY_SUFFIXES = ("~", ".tmp", ".part", ".crdownload", ".download")
```

Protected globs mean “never write”; Phase 1 may read the connector manifest under `brain-engine` only through the trust importer. `.git`, `.obsidian`, and `logseq` control files are not page content.

- [ ] **Step 3: Adapt watcher behavior without sharing persistence tables**

Create a vault-specific watcher and repository protocol:

```python
class VaultObservationRepository(Protocol):
    async def record_observation(self, observation: VaultFileObservation) -> None:
        raise NotImplementedError

    async def mark_missing(self, vault_id: str, relative_path: str) -> None:
        raise NotImplementedError
```

Reuse or extract Capture’s `_resolved_root`, `_is_within`, stability observation, and fingerprint behavior. Do not store vault files in `capture_inbox_*`.

- [ ] **Step 4: Add TOCTOU checks**

Open each file with `os.open` using `O_RDONLY` and `O_NOFOLLOW` where available. Compare `fstat` device/inode/size/mtime before and after read. Hash bytes from the open descriptor. If the file changes, return `changed_during_read` and retry on a later scan.

- [ ] **Step 5: Run security tests and commit**

Run:

```bash
uv run pytest tests/test_vault_security.py tests/test_vault_watcher.py tests/test_capture_inbox.py -q
uv run ruff check deeper_notebook/vault/security.py deeper_notebook/vault/watcher.py
```

Commit:

```bash
git add deeper_notebook/vault/security.py deeper_notebook/vault/watcher.py deeper_notebook/capture/watcher.py tests/test_vault_security.py tests/test_vault_watcher.py tests/test_capture_inbox.py
git commit -m "feat(vault): enforce read-only approved roots"
```

---

### Task 4: Persist Atomic Projections, Links, Tasks, Trust, and Receipts

**Files:**

- Create: `deeper_notebook/vault/repository.py`
- Create: `deeper_notebook/vault/trust.py`
- Create: `tests/test_vault_repository.py`
- Modify: `deeper_notebook/domain/notebook.py`

- [ ] **Step 1: Write failing repository tests**

Using a fake repository/query recorder, prove:

- One file projection commits its note, blocks, links, tasks, file status, and receipt in one transaction.
- Re-indexing the same path/hash is a no-op with one `unchanged` receipt.
- A changed parse replaces only that file’s prior block/link/task projection.
- A failed parse preserves the prior note and related records.
- Missing marks the file/note stale without deleting them.
- Receipts have create/list methods only.
- Embedding submission happens after the durable transaction.
- `artifact` relations are never created for vault links.

Add `tests/integration/test_vault_projection.py`, marked
`integration_surreal`, to prove against a throwaway real namespace:

- Migration 32 applies on a fresh schema; an up/down/up cycle succeeds; the down migration removes only vault fields/tables.
- Re-applying the guarded schema statements without a down migration is safe.
- A complete projection commits all rows.
- An injected failure between block and link insertion rolls back the entire projection.
- Re-indexing the same hash is idempotent and preserves receipt uniqueness.
- Missing state preserves the last valid note/blocks.
- Record-typed IDs and unique indexes accept the planned values.

- [ ] **Step 2: Implement repository records**

`VaultRepository` exposes:

- `create_mount(request: VaultMountCreate) -> VaultMount`
- `list_mounts() -> list[VaultMount]`
- `get_mount(vault_id: str) -> VaultMount`
- `project_document(vault, observation, parsed, operation_id) -> ProjectionResult`
- `record_failure(vault_id, observation, operation_id, error_code) -> FailureResult`
- `mark_missing(vault_id, relative_path, operation_id) -> None`
- `list_files(vault_id, prefix, limit, offset) -> list[VaultFile]`
- `get_page(vault_id, note_id) -> VaultPage`
- `backlinks(vault_id, note_id) -> list[VaultLink]`
- `outgoing_links(vault_id, note_id) -> list[VaultLink]`
- `graph(vault_id, center_note_id, depth, limit) -> VaultGraph`
- `append_receipt(receipt: VaultSyncReceipt) -> VaultSyncReceipt`
- `list_receipts(vault_id, limit, offset) -> list[VaultSyncReceipt]`
- `import_trust_manifest(vault_id, manifest_relative_path) -> TrustImportResult`
- `list_trust_records(vault_id, limit, offset) -> list[VaultTrustRecord]`
- `trust_summary(vault_id) -> VaultTrustSummary`

It intentionally has no `update_external_file`, `delete_external_file`, or receipt update/delete method.

- [ ] **Step 3: Commit projections in one Surreal transaction**

The query order is:

1. Upsert `vault_file`.
2. Upsert the external `note` by `vault_file_id`.
3. Delete the old `note_block`, `note_link`, and `knowledge_task` rows for that file.
4. Insert current blocks, links, and tasks.
5. Resolve links by normalized title within the same mount only.
6. Mark the file parsed and note current.
7. Create the success receipt.
8. Commit.

Use `BEGIN TRANSACTION` / `COMMIT TRANSACTION`; on any exception issue `CANCEL TRANSACTION` and record a bounded failure receipt in a separate transaction. Never store source bytes in a receipt.

- [ ] **Step 4: Keep embeddings eventual**

After commit, submit `embed_note` for changed notes. Store `embedding_state="pending"` in the operation response. A submission failure logs the note ID and error class only, leaves the projection ready, and is retryable.

- [ ] **Step 5: Import connector trust metadata**

`vault_trust_record` fields:

```python
manifest_id: str
vault_id: str | None
canonical_relative_path: str | None
status: Literal["approved"]
resolution_state: Literal["resolved", "unresolved"]
reviewer: str
reviewed_at: datetime
source_type: str
evidence_class: Literal["source", "synthesis"]
content_hash: str
derived_from: list[str]
manifest_relative_path: str
```

Resolve the stale absolute `sourcePath` by stripping the manifest’s old `vaultRoot` and joining the relative suffix under the newly approved root. Confirm containment and content hash. If canonical source exists, link trust to it and do not import the generated copy as another note. Hash mismatch or missing source creates an unresolved trust record and receipt; it does not mutate the manifest.

Trust identity is scoped by `vault_id + manifest_relative_path + manifest_id`;
`content_hash` and reviewed provenance determine idempotency. Re-running reports
`unchanged=21`; a changed hash stays unresolved until the canonical hash matches.

- [ ] **Step 6: Run repository tests and commit**

Run:

```bash
uv run pytest tests/test_vault_repository.py tests/test_notes_api.py tests/test_notebook_graph.py tests/test_search_api.py -q
SURREAL_INTEGRATION=1 uv run pytest tests/integration/test_vault_projection.py -q
uv run ruff check deeper_notebook/vault/repository.py deeper_notebook/vault/trust.py
```

Commit:

```bash
git add deeper_notebook/vault/repository.py deeper_notebook/vault/trust.py deeper_notebook/domain/notebook.py tests/test_vault_repository.py tests/integration/test_vault_projection.py
git commit -m "feat(vault): persist receipted knowledge projections"
```

---

### Task 5: Build the Scan Service and Live Read-Only Index

**Files:**

- Create: `deeper_notebook/vault/service.py`
- Create: `tests/test_vault_service.py`
- Modify: `api/main.py`

- [ ] **Step 1: Write failing orchestration tests**

Cover:

- Mount state transitions `disconnected -> scanning -> ready-read-only`.
- One operation ID per scan.
- Stable unchanged files skip parsing and embedding.
- Newer parse failures preserve the previous note graph while advancing file provenance to invalid/stale; equal-timestamp hash conflicts preserve both current file and graph and request reconciliation.
- Watcher bursts debounce to one rescan.
- Service shutdown stops and joins observers.
- Startup with an unavailable root marks it unavailable and does not crash the API.
- Parent mixed mount does not scan files also owned by child mounts.

- [ ] **Step 2: Implement the service**

`VaultService` implements these exact async interfaces:

- `register_mount(request: VaultMountCreate) -> VaultMount`
- `scan(vault_id: str) -> VaultScanResult`
- `start_watchers() -> None`
- `stop_watchers() -> None`
- `scan_dirty_mounts() -> list[VaultScanResult]`

The service owns one observer and one async worker. Events add `(vault_id, relative_path)` to a set. A two-second debounce batches paths. Only stable observations enter parsing.

- [ ] **Step 3: Add startup lifecycle integration**

After migrations and database readiness:

1. Load mounts with `watch_enabled=true`.
2. Start read-only observers.
3. Schedule a background dirty scan.

On shutdown, stop observers before closing the database pool. API startup remains available if a mount is unavailable.

- [ ] **Step 4: Make grounded search show mounted provenance**

Existing note search includes projected external notes automatically. Extend result metadata with:

```json
{
  "canonical_external": true,
  "vault_id": "vault_mount:obsidian-brain",
  "relative_path": "wiki/concepts/local-llms.md",
  "source_hash": "sha256:d2d369166f8a794dbab96699aefd87ccc58763163dceb4221e61cc9c8833f071"
}
```

Never send the absolute root path in a search result or LLM context citation.

Implement the enrichment in `deeper_notebook/domain/notebook.py` immediately
after `fn::text_search` and `fn::vector_search` return. Collect note result IDs
in one bounded query, fetch their vault fields and the matching
`vault_file.relative_path`, and merge a `vault_provenance` object into those
results. Do not issue one query per result. Update `api/models.py`,
`api/routers/search.py`, `frontend/src/lib/api/search.ts`, and search result
rendering to preserve the typed object.

Update `deeper_notebook/utils/context_builder.py` so a selected mounted note
produces a grounded citation containing the relative path, note ID, source hash,
and relevant block span. Add text-search, vector-search, and grounded-chat tests
that prove:

- mounted results retain relative-path/hash provenance;
- normal notes retain the existing shape;
- no absolute root reaches JSON, prompts, citations, or logs;
- a mounted block can be cited by grounded AI as `[V1]`;
- a failed embedding does not remove text-search/citation availability.

- [ ] **Step 5: Run service tests and commit**

Run:

```bash
uv run pytest tests/test_vault_service.py tests/test_search_api.py tests/test_health_endpoints.py tests/test_capture_inbox.py -q
uv run ruff check deeper_notebook/vault/service.py
```

Commit:

```bash
git add deeper_notebook/vault/service.py deeper_notebook/domain/notebook.py deeper_notebook/utils/context_builder.py api/main.py api/models.py api/routers/search.py frontend/src/lib/api/search.ts tests/test_vault_service.py tests/test_search_api.py
git commit -m "feat(vault): run a live read-only index"
```

---

### Task 6: Expose Read-Only Vault APIs

**Files:**

- Create: `api/schemas/vault.py`
- Create: `api/routers/vault.py`
- Create: `tests/test_vault_api.py`
- Modify: `api/main.py`

- [ ] **Step 1: Write failing API tests**

Required canonical endpoints:

```text
POST /api/deeper-notebook/vaults
GET  /api/deeper-notebook/vaults
GET  /api/deeper-notebook/vaults/{vault_id}
POST /api/deeper-notebook/vaults/{vault_id}/scan
GET  /api/deeper-notebook/vaults/{vault_id}/files
GET  /api/deeper-notebook/vaults/{vault_id}/pages/{note_id}
GET  /api/deeper-notebook/vaults/{vault_id}/pages/{note_id}/backlinks
GET  /api/deeper-notebook/vaults/{vault_id}/pages/{note_id}/outgoing
GET  /api/deeper-notebook/vaults/{vault_id}/graph
GET  /api/deeper-notebook/vaults/{vault_id}/receipts
POST /api/deeper-notebook/vaults/{vault_id}/trust/import
GET  /api/deeper-notebook/vaults/{vault_id}/trust
GET  /api/deeper-notebook/vaults/{vault_id}/trust/summary
```

Tests assert no `PUT`, `PATCH`, or `DELETE` route exists under this namespace.
The trust-import POST accepts only a root-contained relative manifest path and
is idempotent; it mutates the Deeper Notebook projection only and never the
manifest or source vault.

- [ ] **Step 2: Define strict schemas**

```python
class VaultMountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=4096)
    format_mode: VaultFormat
    parent_vault_id: str | None = None
    watch_enabled: bool = True


class VaultScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str
    state: VaultState
    observed: int
    parsed: int
    unchanged: int
    unsupported: int
    invalid: int
    missing: int
    embeddings_pending: int
```

Responses expose relative paths, never absolute root paths except the owner-only mount detail needed to confirm the selected folder. Receipt exports redact the home prefix.

- [ ] **Step 3: Implement error mapping**

Use stable codes:

- `vault_root_invalid` -> 422
- `vault_root_unapproved` -> 403
- `vault_unavailable` -> 409
- `vault_scan_in_progress` -> 409
- `vault_not_found` -> 404
- `vault_page_not_found` -> 404
- `vault_read_only` -> 405/409 where applicable

Do not include raw `OSError`, source content, or absolute candidate paths in response details.

- [ ] **Step 4: Register canonical routes only**

Register under `/api/deeper-notebook`. The old `/api/onp` alias applies only to pre-existing downstream-wrapper endpoints; do not create a new legacy vault API.

- [ ] **Step 5: Run API tests and commit**

Run:

```bash
uv run pytest tests/test_vault_api.py tests/test_crud_404.py tests/test_middleware_v0_7_120.py -q
uv run ruff check api/schemas/vault.py api/routers/vault.py tests/test_vault_api.py
```

Commit:

```bash
git add api/schemas/vault.py api/routers/vault.py api/main.py tests/test_vault_api.py
git commit -m "feat(api): expose read-only vault endpoints"
```

---

### Task 7: Add the Knowledge Explorer, Backlinks, and Local Graph

**Files:**

- Create: `frontend/src/lib/api/vault.ts`
- Create: `frontend/src/lib/hooks/use-vault.ts`
- Create: associated API/hook tests.
- Create: `frontend/src/app/(dashboard)/knowledge/page.tsx`
- Create: `frontend/src/components/vault/*`
- Create: component tests.
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: locale files.

- [ ] **Step 1: Write failing API contract tests**

Use Zod to validate server responses before they enter React Query:

```typescript
export const vaultFileSchema = z.object({
  id: z.string(),
  vault_id: z.string(),
  relative_path: z.string(),
  file_kind: z.string(),
  format: z.enum(['obsidian', 'logseq', 'markdown']),
  content_hash: z.string().nullable(),
  parse_status: z.enum([
    'pending', 'parsed', 'unsupported', 'invalid', 'conflict', 'missing',
  ]),
})
```

Tests reject absolute-path leakage in file/page/graph responses.

- [ ] **Step 2: Implement query keys and invalidation**

```typescript
export const vaultKeys = {
  all: ['vaults'] as const,
  detail: (id: string) => ['vaults', id] as const,
  files: (id: string) => ['vaults', id, 'files'] as const,
  page: (id: string, noteId: string) => ['vaults', id, 'pages', noteId] as const,
  backlinks: (id: string, noteId: string) =>
    ['vaults', id, 'pages', noteId, 'backlinks'] as const,
  graph: (id: string) => ['vaults', id, 'graph'] as const,
}
```

After a scan, invalidate detail, files, graph, selected page, backlinks, and global search queries.

- [ ] **Step 3: Build the three-pane read-only workspace**

Layout:

- Left: mount switcher, scan status, filterable file tree.
- Center: page title, provenance bar, Markdown reader, properties/tags, outline.
- Right: backlinks and outgoing links.
- Graph tab: React Flow local graph with resolved and unresolved links.

Every externally canonical page displays a `Read-only external file` badge. There is no save, rename, delete, move, drag-to-reorder, checkbox mutation, or inline property editor.

- [ ] **Step 4: Render portable Markdown safely**

Use `react-markdown` with `remark-gfm` and `remark-math`. Convert wikilinks to internal page-navigation anchors using the server-resolved target ID. Reject raw HTML execution. Attachment links resolve through a root-bounded read endpoint only if that endpoint is separately security-tested; otherwise render attachment names without fetching bytes in Phase 1.

- [ ] **Step 5: Reuse React Flow for a real link graph**

`VaultGraph` consumes `note_link` edges, colors Obsidian and Logseq nodes differently using Deeper Notebook brand tokens, uses dashed edges for unresolved links, disables connecting/editing, and opens the selected page. It does not reuse notebook `artifact` edges.

- [ ] **Step 6: Add navigation and localization**

Add `Knowledge` under the Process section of the sidebar. Add translated labels for mounts, scan, status, read-only, backlinks, outgoing links, properties, tags, unresolved links, and error states. The product name remains `Deeper Notebook` in every locale.

- [ ] **Step 7: Run frontend tests and build**

Run:

```bash
cd frontend
npm test -- src/lib/api/vault.test.ts src/lib/hooks/use-vault.test.tsx src/components/vault src/components/layout/AppSidebar.test.tsx
npm run build
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/api/vault.ts frontend/src/lib/hooks/use-vault.ts frontend/src/app/'(dashboard)'/knowledge frontend/src/components/vault frontend/src/components/layout/AppSidebar.tsx frontend/src/lib/locales
git commit -m "feat(knowledge): add vault explorer and backlinks"
```

---

### Task 8: Register and Prove the Actual Second Brain Without Modifying It

**Files:**

- Create: `scripts/verify_read_only_vault.py`
- Create: `tests/test_verify_read_only_vault.py`
- Create: `docs/verification/2026-07-26-second-brain-read-only-scan.md`

- [ ] **Step 1: Write failing verifier tests**

The verifier accepts `--root`, `--api`, `--output`, and `--check-only`. Tests use a temporary fixture vault and assert:

- Before/after file hashes are identical.
- Git status text is identical.
- A second scan has zero changed projections.
- Counts reconcile with the API.
- Trust records preserve all `derivedFrom` arrays.
- Report output contains relative paths only.
- A mismatch exits non-zero.

- [ ] **Step 2: Implement a check-first verifier**

Before calling the API:

1. Resolve the exact root.
2. Refuse `/`, the home directory, or a non-directory.
3. Use `git ls-files --cached --others --exclude-standard -z` to enumerate working-tree source files, excluding `.git/**`; hash every regular non-symlink result without writing. For a non-Git fixture, walk the root while excluding `.git/**`.
4. Capture `git -C <root> status --porcelain=v1 --untracked-files=all` and its exit code without staging. If the pre-existing lock files prevent status, report `git_status_unavailable` and continue hash proof without trying to repair or remove a lock.
5. Read the connector manifest and record expected trust counts.

After each scan, repeat hashes/status and compare. The report includes:

```json
{
  "source_files_changed": 0,
  "git_status_changed": false,
  "second_scan_changed_projections": 0,
  "trust_records": 21,
  "synthesis_records": 9,
  "synthesis_with_derived_from": 9
}
```

- [ ] **Step 3: Register the actual mounts**

Create:

1. Parent: name `2nd Brains`, path `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains`, mode `mixed`, `watch_enabled=false`.
2. Child: name `Obsidian Brain`, path `<root>/Obsidian Brain`, mode `obsidian`, parent set, `watch_enabled=true`.
3. Child: name `Logseq Brain`, path `<root>/Logseq Brain`, mode `logseq`, parent set, `watch_enabled=true`.

Register `<root>/brain-engine/generated/deepercode-connector/manifest.json` as trust metadata through the parent. Do not register `brain-engine` as a writable or scanned note mount.
The verifier calls the idempotent
`POST /vaults/{parent_id}/trust/import` with the root-relative manifest path,
then reads `/trust`, `/trust/summary`, and `/receipts` to reconcile the report.

- [ ] **Step 4: Run the real-workspace proof**

Run:

```bash
uv run python scripts/verify_read_only_vault.py \
  --root "/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains" \
  --api "http://127.0.0.1:5055/api/deeper-notebook" \
  --output "docs/verification/2026-07-26-second-brain-read-only-scan.md"
```

Expected minimum reconciliation from the approved design snapshot:

- 29 Obsidian Markdown files.
- 20 Logseq Markdown files.
- 183 Obsidian wikilinks.
- 133 Logseq wikilinks.
- 21 Obsidian files with frontmatter.
- 70 Logseq property lines.
- 27 open tasks.
- 21 completed tasks.
- 21 approved trust records.
- 12 source-evidence records.
- 9 synthesis records, all retaining `derivedFrom`.

If live counts differ because the user has edited the vault, report both the approved snapshot and current counts; do not alter files to force a match.

- [ ] **Step 5: Run final regression and native smoke**

Run:

```bash
uv run pytest tests/test_vault_*.py tests/test_capture_inbox.py tests/test_notes_api.py tests/test_search_api.py tests/test_notebook_graph.py -q
uv run pytest -q
cd frontend && npm test && npm run build
git diff --check
```

Then launch the native macOS app, open Knowledge, select one Obsidian page and
one Logseq page, verify backlinks and graph navigation, run a grounded search,
quit/relaunch, and verify the mounts and projections remain available.

On a Windows host, install the packaged Deeper Notebook build and use a
committed synthetic mixed fixture vault (not the user's macOS-only absolute
path). Mount its Obsidian and Logseq children, index, verify backlinks/graph and
grounded search, quit/relaunch, verify persistence, and assert fixture hashes
are unchanged. This Windows packaged smoke is required in addition to the
actual-workspace macOS proof.

- [ ] **Step 6: Commit proof artifacts**

The report must contain no source content, secrets, or unredacted absolute home paths beyond the explicitly approved root label.

```bash
git add scripts/verify_read_only_vault.py tests/test_verify_read_only_vault.py docs/verification/2026-07-26-second-brain-read-only-scan.md
git commit -m "test(vault): prove the Second Brain scan is read only"
```

---

## Completion Gate

Phase 1 is complete only when:

- The actual Obsidian and Logseq folders are mounted and indexed without changing a source hash or Git status.
- A second scan is idempotent.
- Backlinks, outgoing links, blocks, tasks, properties, tags, trust metadata, and local graph data are queryable.
- Existing full-text/vector search can return mounted notes with relative-path provenance.
- Grounded AI can cite a mounted page/block with relative-path and hash provenance and no absolute-root leakage.
- The UI exposes only read-only interactions for external files.
- Parse failures preserve the prior valid note graph; a genuinely newer failed observation advances file provenance to invalid/stale.
- Symlink, TOCTOU, encoding, oversize, and event-storm tests pass.
- All 21 manifest records are imported as trust metadata and all 9 synthesis `derivedFrom` arrays survive.
- Existing notebooks, research, Studio, Capture, podcasts, memory, and model workflows pass their regressions.
- Packaged macOS and Windows fixture-vault mount/index/search/relaunch smokes pass; the actual private vault is tested only on its macOS host.

## Explicitly Deferred

The following require later implementation plans and are not part of this Phase 1 plan:

- Tabs, panes, live-preview/source editors, command palette, and quick switcher.
- Daily notes, templates, bookmarks, composer, and workspace persistence.
- Bases, editable Canvas, task dashboards, audio recorder, slides, web viewer, and file recovery.
- Any external file write, checkbox toggle, rename, move, delete, serializer, diff preview, backup, conflict resolver, or rollback action.
- Obsidian third-party plugin binary compatibility, proprietary Obsidian Sync/Publish, and mobile applications.
