# Deeper Notebook Read-Only Editor Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add canonical, strictly read-only Reading, Source, Live Preview, and Graph modes with outline, footnotes, properties, tags, and safe page previews for mounted Obsidian/Logseq pages.

**Architecture:** Extend the vault page projection with its canonical file record and canonical resolved-link targets, then validate those contracts at the frontend boundary. Render Reading through the safe React Markdown pipeline and Source/Live Preview through one locked CodeMirror 6 substrate, while preserving mode per tab through the existing durable workspace store.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, SurrealDB, Next.js 16.2.3, React 19.2.3, Zustand 5, TanStack Query 5, Zod 4, React Markdown 10, CodeMirror 6, Vitest 4, Testing Library, pytest 9.

## Global Constraints

- Mounted Markdown and asset files remain canonical and read-only.
- Do not add an external-file mutation route. The existing scan `POST` remains
  index-only and must never write to the mounted source.
- Do not add local draft persistence or an editable internal copy.
- The frontend never receives an absolute vault root.
- A page opens only when its canonical vault-relative path is known.
- Configure both `EditorState.readOnly.of(true)` and `EditorView.editable.of(false)`.
- Do not include a command, keymap, toolbar, extension, or callback that changes the CodeMirror document.
- Render only projected Markdown returned by the page API.
- Do not execute embedded HTML.
- Keep external links inert; only resolved vault links navigate.
- Missing or inconsistent canonical paths fail closed.
- Preserve the Notebook Spark personality and Research Core teal/cyan colorway.
- Keep the real `/Users/Antman/Desktop/2nd Brains` source read-only; use only synthetic fixtures and projected API records in automated tests.
- Use test-driven development: every production behavior starts with a failing test observed for the expected reason.
- Pin CodeMirror packages exactly at `@codemirror/commands@6.10.4`,
  `@codemirror/lang-markdown@6.5.1`, `@codemirror/language@6.12.4`,
  `@codemirror/search@6.7.1`, `@codemirror/state@6.7.1`, and
  `@codemirror/view@6.43.7`.

---

## File Structure

### Backend

- `deeper_notebook/vault/repository.py`: canonical page/file and resolved-link projection.
- `deeper_notebook/database/migrations/35.surrealql`: optional persisted newline metadata.
- `deeper_notebook/database/migrations/35_down.surrealql`: scoped newline-field rollback.
- `api/schemas/vault.py`: public page and link response models.
- `api/routers/vault.py`: response assembly without partial fallbacks.
- `tests/test_vault_migration.py`: migration and rollback contract.
- `tests/test_vault_repository.py`: repository query and fail-closed tests.
- `tests/test_vault_api.py`: public relative-path/provenance contract tests.
- `tests/integration/test_vault_projection.py`: native migration/projection proof.

### Frontend contracts and state

- `frontend/src/lib/api/vault.ts`: Zod page/file/link consistency boundary.
- `frontend/src/lib/api/vault.test.ts`: hostile and inconsistent response tests.
- `frontend/src/lib/api/knowledge-workspace.ts`: shared canonical path schema.
- `frontend/src/lib/api/knowledge-workspace.test.ts`: hostile path parity tests.
- `frontend/src/lib/stores/knowledge-workspace-store.ts`: idempotent canonical tab reconciliation.
- `frontend/src/lib/stores/knowledge-workspace-store.test.ts`: reconciliation and revision tests.
- `frontend/src/lib/hooks/use-vault.ts`: canonical page-preview query reuse.

### Frontend document rendering

- `frontend/src/lib/vault/markdown-model.ts`: Markdown syntax-tree outline, slugs, and source ranges.
- `frontend/src/lib/vault/markdown-model.test.ts`: headings, duplicates, fences, and construct ranges.
- `frontend/src/lib/vault/remark-vault-links.ts`: span-preserving wiki-link MDAST transformer.
- `frontend/src/lib/vault/remark-vault-links.test.ts`: Unicode and duplicate-label span proof.
- `frontend/src/lib/vault/live-preview.ts`: pure visible-range decoration builder.
- `frontend/src/lib/vault/live-preview.test.ts`: supported constructs and source fallback.
- `frontend/src/components/vault/VaultCodeMirror.tsx`: locked CodeMirror lifecycle.
- `frontend/src/components/vault/VaultCodeMirror.test.tsx`: read-only, selection, search, and update proof.
- `frontend/src/components/vault/VaultEditorBoundary.tsx`: display-only Reading fallback after editor failure.
- `frontend/src/components/vault/VaultEditorBoundary.test.tsx`: fallback and reset behavior.
- `frontend/src/components/vault/VaultDocumentView.tsx`: mode-specific document boundary.
- `frontend/src/components/vault/VaultDocumentView.test.tsx`: Reading/Source/Live Preview selection.
- `frontend/src/components/vault/VaultMarkdown.tsx`: safe Reading renderer.
- `frontend/src/components/vault/VaultMarkdown.test.tsx`: GFM, footnotes, math, tasks, anchors, and links.
- `frontend/src/components/vault/VaultNoteSidebar.tsx`: outline, properties, tags, and provenance.
- `frontend/src/components/vault/VaultNoteSidebar.test.tsx`: outline and metadata accessibility.
- `frontend/src/components/vault/VaultPagePreview.tsx`: delayed safe preview.
- `frontend/src/components/vault/VaultPagePreview.test.tsx`: hover/focus/cache/failure behavior.
- `frontend/src/components/vault/KnowledgePaneContent.tsx`: canonical reconciliation and four-mode orchestration.
- `frontend/src/components/vault/KnowledgePaneContent.test.tsx`: loading, failure, mode, and reconciliation integration.
- `frontend/src/components/vault/KnowledgeExplorer.tsx`: remove synthetic path fallback.
- `frontend/src/components/vault/KnowledgeExplorer.test.tsx`: canonical-only navigation and persistence.
- `frontend/src/components/vault/vault.css`: Research Core editor styles.
- `frontend/src/lib/locales/*/index.ts`: localized mode, preview, provenance, and error labels.

---

### Task 1: Return Canonical File And Link Target Metadata

**Files:**
- Modify: `deeper_notebook/vault/repository.py:105-129`
- Modify: `deeper_notebook/vault/repository.py:1481-1541`
- Create: `deeper_notebook/database/migrations/35.surrealql`
- Create: `deeper_notebook/database/migrations/35_down.surrealql`
- Modify: `api/schemas/vault.py:80-111`
- Modify: `api/routers/vault.py:196-211`
- Test: `tests/test_vault_migration.py`
- Test: `tests/test_vault_repository.py`
- Test: `tests/test_vault_api.py`
- Test: `tests/integration/test_vault_projection.py`

**Interfaces:**
- Produces: `VaultPage.file: VaultFile`
- Produces: `VaultFile.newline: Literal["lf", "crlf", "mixed", "none"] | None`
- Produces: `VaultLink.target_note_title: str | None`
- Produces: `VaultLink.target_relative_path: str | None`
- Produces: `VaultLink.source_start: int`
- Produces: `VaultLink.source_end: int`
- Produces: `VaultPageResponse.file: VaultFileResponse`
- Produces: public `vault_canonical_file_unavailable` and `vault_page_invalid`
  error codes without filesystem details
- Consumes: existing `note.vault_file_id`, `vault_file.vault_id`, and `_db_id()`

- [ ] **Step 1: Write repository tests that require canonical page/file identity**

Add a recorder whose query sequence returns one note, its exact file, no blocks,
no tasks, and no links:

```python
@pytest.mark.asyncio
async def test_get_page_returns_its_canonical_file_record():
    class PageRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            self.calls.append((compact, variables or {}))
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": "note:alpha",
                        "vault_id": "vault_mount:test",
                        "vault_file_id": "vault_file:alpha",
                        "title": "Alpha",
                        "content": "# Alpha\n",
                    }
                ]
            if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": "vault_file:alpha",
                        "vault_id": "vault_mount:test",
                        "relative_path": "pages/alpha.md",
                        "file_kind": "markdown",
                        "format": "obsidian",
                        "content_hash": "a" * 64,
                        "encoding": "utf-8",
                        "newline": "lf",
                        "parse_status": "parsed",
                        "deleted_state": "present",
                    }
                ]
            return []

    recorder = PageRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(recorder),
    )

    page = await repository.get_page("vault_mount:test", "note:alpha")

    assert page.file.relative_path == "pages/alpha.md"
    assert page.file.content_hash == "a" * 64
    assert page.file.newline == "lf"
    file_call = next(
        variables
        for statement, variables in recorder.calls
        if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in statement
    )
    assert str(file_call["vault_file_id"]) == "vault_file:alpha"
```

Add an orphan test:

```python
@pytest.mark.asyncio
async def test_get_page_rejects_note_without_canonical_file():
    class OrphanRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": "note:alpha",
                        "vault_id": "vault_mount:test",
                        "vault_file_id": "vault_file:missing",
                        "title": "Alpha",
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(OrphanRecorder()),
    )

    with pytest.raises(LookupError, match="vault_note_file_not_found"):
        await repository.get_page("vault_mount:test", "note:alpha")
```

- [ ] **Step 2: Write resolved-link metadata tests**

Extend the backlink recorder and assertions:

```python
if "FROM note_link" in compact:
    return [
        {
            "id": "note_link:source-target",
            "source_note_id": "note:source",
            "target_note_id": "note:target",
            "target_text": "Target",
            "source_note_title": "Source title",
            "target_note_title": "Target title",
            "target_relative_path": "pages/target.md",
            "source_start": 12,
            "source_end": 22,
            "link_kind": "wikilink",
            "resolved": True,
        }
    ]
```

```python
assert backlinks[0].target_note_title == "Target title"
assert backlinks[0].target_relative_path == "pages/target.md"
assert backlinks[0].source_start == 12
assert backlinks[0].source_end == 22
assert "target_note_id.title AS target_note_title" in link_query
assert (
    "target_note_id.vault_file_id.relative_path AS target_relative_path" in link_query
)
```

Add model validation:

```python
def test_resolved_link_requires_canonical_target_identity():
    with pytest.raises(ValidationError):
        VaultLink(
            id="note_link:broken",
            source_note_id="note:source",
            target_note_id="note:target",
            target_text="Target",
            source_start=0,
            source_end=8,
            link_kind="wikilink",
            resolved=True,
        )


def test_resolved_link_allows_present_empty_canonical_title():
    link = VaultLink(
        id="note_link:empty-title",
        source_note_id="note:source",
        target_note_id="note:target",
        target_note_title="",
        target_relative_path="pages/target.md",
        target_text="Target",
        source_start=0,
        source_end=8,
        link_kind="wikilink",
        resolved=True,
    )
    assert link.target_note_title == ""


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "/absolute.md",
        "../outside.md",
        "pages\\outside.md",
        "a//b.md",
        "pages/\x00outside.md",
        "C:/outside.md",
        " pages/outside.md",
        "pages/outside.md ",
        "p" * 4097,
    ],
)
def test_vault_models_reject_noncanonical_relative_paths(relative_path):
    with pytest.raises(ValidationError, match="canonical vault-relative path"):
        VaultFile(
            id="vault_file:broken",
            note_id="note:broken",
            vault_id="vault_mount:test",
            relative_path=relative_path,
            file_kind="markdown",
            format="markdown",
            parse_status="parsed",
            deleted_state="present",
        )
```

Add text-level migration coverage:

```python
NEWLINE_UP = ROOT / "deeper_notebook/database/migrations/35.surrealql"
NEWLINE_DOWN = ROOT / "deeper_notebook/database/migrations/35_down.surrealql"


def test_migration_35_adds_optional_vault_file_newline_metadata():
    sql = NEWLINE_UP.read_text(encoding="utf-8")
    assert (
        "DEFINE FIELD IF NOT EXISTS newline ON TABLE vault_file "
        "TYPE option<string> ASSERT $value = NONE OR $value IN "
        '["lf", "crlf", "mixed", "none"];'
    ) in sql


def test_migration_35_down_removes_only_vault_file_newline_metadata():
    sql = NEWLINE_DOWN.read_text(encoding="utf-8")
    assert sql.strip() == "REMOVE FIELD IF EXISTS newline ON TABLE vault_file;"
```

Add native integration coverage in
`tests/integration/test_vault_projection.py` before creating migration 35:

- define `MIGRATION_35` and `MIGRATION_35_DOWN`;
- make `_restore_recorded_v32_state()` apply the 35 rollback and delete recorded
  migration 35 before rolling back 34/33;
- update every current-head assertion from 34 to 35;
- prove a fresh namespace exposes the `newline` field;
- create a valid v34 `vault_file` row without `newline`, run the migration
  manager, assert head 35 and `row.get("newline") is None`;
- assert `crlf` is accepted and `invalid-newline` is rejected natively;
- apply the down migration, assert only the field is absent and the row remains,
  then run up twice and assert head 35;
- extend `test_complete_projection_is_atomic_and_record_typed` to assert the
  parsed fixture persists `file_row["newline"] == "lf"`.

Add the public API fixture and assertions before the RED run. The fake
repository returns:

```python
return VaultPage(
    file=VaultFile(
        id="vault_file:one",
        note_id=note_id,
        vault_id=vault_id,
        relative_path="notes/one.md",
        file_kind="markdown",
        format="markdown",
        content_hash="a" * 64,
        size_bytes=7,
        modified_ns=1,
        encoding="utf-8",
        newline="lf",
        parse_status="parsed",
        deleted_state="present",
    ),
    note={"id": note_id, "title": "One", "content": "# One\n"},
)
```

Assert the page response contains `file.relative_path`, full `content_hash`,
`newline`, and no absolute root. Add an outgoing-link response assertion for
`source_start`, `source_end`, canonical target path, and a present empty target
title. Add these failure tests before the RED run:

```python
def test_page_maps_orphaned_note_to_canonical_file_error(client):
    test_client, repository, _ = client
    repository.get_page = AsyncMock(
        side_effect=LookupError("vault_note_file_not_found"),
    )
    response = test_client.get(
        "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:orphan"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ("vault_canonical_file_unavailable")
    assert "/Users/" not in response.text


def test_page_rejects_missing_or_invalid_content_hash(client):
    test_client, repository, _ = client
    for content_hash in (None, "short", "g" * 64):
        repository.get_page = AsyncMock(
            return_value=VaultPage(
                file=VaultFile(
                    id="vault_file:one",
                    note_id="note:one",
                    vault_id="vault_mount:fixture",
                    relative_path="notes/one.md",
                    file_kind="markdown",
                    format="markdown",
                    content_hash=content_hash,
                    encoding="utf-8",
                    newline="lf",
                    parse_status="parsed",
                    deleted_state="present",
                ),
                note={"id": "note:one", "title": "One", "content": "# One\n"},
            ),
        )
        response = test_client.get(
            "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one"
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "vault_page_invalid"
```

Import `AsyncMock` from `unittest.mock`. These tests intentionally use the
existing synchronous `TestClient` fixture and replace only the per-test fake
repository's async `get_page` method.

- [ ] **Step 3: Run migration, repository, integration, and API tests and observe RED**

Run:

```bash
PYTHONPATH=. uv run pytest \
  tests/test_vault_migration.py::test_migration_35_adds_optional_vault_file_newline_metadata \
  tests/test_vault_migration.py::test_migration_35_down_removes_only_vault_file_newline_metadata \
  tests/test_vault_repository.py::test_get_page_returns_its_canonical_file_record \
  tests/test_vault_repository.py::test_get_page_rejects_note_without_canonical_file \
  tests/test_vault_repository.py::test_backlinks_project_source_note_title_for_display_identity \
  tests/test_vault_repository.py::test_resolved_link_requires_canonical_target_identity \
  tests/test_vault_repository.py::test_resolved_link_allows_present_empty_canonical_title \
  tests/test_vault_repository.py::test_vault_models_reject_noncanonical_relative_paths \
  tests/test_vault_api.py -q
```

Then run the native projection test in one ownership-safe shell:

```bash
DN_SURREAL_PREEXISTING_ID="$(docker compose ps --no-trunc -q surrealdb)"
DN_SURREAL_STARTED_ID=""

dn_cleanup_surreal() {
  DN_SURREAL_EXIT_STATUS=$?
  trap - EXIT
  if [ -n "$DN_SURREAL_STARTED_ID" ]; then
    DN_SURREAL_CURRENT_ID="$(
      docker inspect --format '{{.Id}}' "$DN_SURREAL_STARTED_ID" \
        2>/dev/null || true
    )"
    if [ "$DN_SURREAL_CURRENT_ID" = "$DN_SURREAL_STARTED_ID" ]; then
      docker stop "$DN_SURREAL_STARTED_ID" >/dev/null || {
        if [ "$DN_SURREAL_EXIT_STATUS" -eq 0 ]; then
          DN_SURREAL_EXIT_STATUS=1
        fi
      }
    elif [ -n "$DN_SURREAL_CURRENT_ID" ]; then
      DN_SURREAL_EXIT_STATUS=1
    fi
  fi
  exit "$DN_SURREAL_EXIT_STATUS"
}

trap dn_cleanup_surreal EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -z "$DN_SURREAL_PREEXISTING_ID" ]; then
  make database || exit 1
  DN_SURREAL_STARTED_ID="$(docker compose ps --no-trunc -q surrealdb)"
  test -n "$DN_SURREAL_STARTED_ID" || exit 1
fi
for _attempt in {1..40}; do
  curl --fail --silent http://127.0.0.1:8000/health >/dev/null && break
  sleep 0.25
done
curl --fail --silent http://127.0.0.1:8000/health >/dev/null || exit 1
SURREAL_INTEGRATION=1 \
SURREAL_URL=ws://localhost:8000/rpc \
PYTHONPATH=. uv run pytest \
  tests/integration/test_vault_projection.py -q
```

Expected: failures because migration 35, `VaultFile.newline`, `VaultPage.file`,
canonical link target/span fields, public response fields, and their
validation/query projections do not exist. Before `make database`, apply the
ownership preflight defined in Task 9: reuse but never stop a pre-existing
Compose SurrealDB service, or record the exact container ID started by this
run and stop only that same ID afterward. The integration fixture creates and
removes a disposable namespace; the Compose runtime and `./surreal_data`
volume are persistent and must never be described or treated as disposable.
Starting the database does not launch or scan a vault.

- [ ] **Step 4: Implement strict repository contracts**

Change the models:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _canonical_vault_relative_path(value: str) -> str:
    if (
        not value
        or len(value) > 4096
        or value.strip() != value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value) is not None
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("value must be a canonical vault-relative path")
    return value


class VaultFile(_Model):
    # existing fields remain unchanged
    newline: Literal["lf", "crlf", "mixed", "none"] | None = None

    @field_validator("relative_path")
    @classmethod
    def canonical_relative_path(cls, value: str) -> str:
        return _canonical_vault_relative_path(value)


class VaultLink(_Model):
    id: str
    source_note_id: str
    source_note_title: str | None = None
    source_block_id: str | None = None
    target_note_id: str | None = None
    target_note_title: str | None = None
    target_relative_path: str | None = None
    target_block_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: str
    resolved: bool = False
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)

    @field_validator("target_relative_path")
    @classmethod
    def canonical_target_relative_path(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_vault_relative_path(value)

    @model_validator(mode="after")
    def resolved_target_is_canonical(self) -> "VaultLink":
        if self.resolved and (
            self.target_note_id is None
            or self.target_note_title is None
            or self.target_relative_path is None
        ):
            raise ValueError("resolved link is missing canonical target identity")
        if self.source_end < self.source_start:
            raise ValueError("source_end must not precede source_start")
        return self


class VaultPage(_Model):
    file: VaultFile
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLink] = Field(default_factory=list)
    backlinks: list[VaultLink] = Field(default_factory=list)
```

Create migration `35.surrealql`:

```sql
DEFINE FIELD IF NOT EXISTS newline ON TABLE vault_file TYPE option<string> ASSERT $value = NONE OR $value IN ["lf", "crlf", "mixed", "none"];
```

Create migration `35_down.surrealql`:

```sql
REMOVE FIELD IF EXISTS newline ON TABLE vault_file;
```

Persist the parser contract in `_projection_variables()`:

```python
file_data = {
    # existing fields remain unchanged
    "encoding": parsed.encoding,
    "newline": parsed.newline,
}
```

Resolve the file before dependent rows:

```python
note = notes[0]
vault_file_id = str(note.get("vault_file_id") or "")
if not vault_file_id:
    raise LookupError("vault_note_file_not_found")
files = await self._query(
    connection,
    "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id;",
    {
        "vault_file_id": _db_id(vault_file_id),
        "vault_id": _db_id(vault_id),
    },
)
if not files:
    raise LookupError("vault_note_file_not_found")
file = VaultFile.model_validate(
    {
        **files[0],
        "note_id": note_id,
    }
)
```

Return `VaultPage(file=file, note=note, ...)` and project the target fields in
`_link_rows()`:

```sql
SELECT *,
    source_note_id.title AS source_note_title,
    target_note_id.title AS target_note_title,
    target_note_id.vault_file_id.relative_path AS target_relative_path
FROM note_link
```

Keep `source_start` and `source_end` required rather than inventing defaults.
Update every existing `VaultLink` fixture in the focused repository/API tests
with its real synthetic span.

- [ ] **Step 5: Implement the tested public API fields**

Move the existing `VaultFileResponse` and `VaultLinkResponse` classes above
`VaultPageResponse`, then update the schemas so Pydantic validates the nested
response without forward references:

```python
class VaultLinkResponse(_VaultSchema):
    id: str
    source_note_id: str
    source_note_title: str | None = None
    source_block_id: str | None = None
    target_note_id: str | None = None
    target_note_title: str | None = None
    target_relative_path: str | None = None
    target_block_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: str
    resolved: bool = False
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class VaultPageResponse(_VaultSchema):
    file: VaultFileResponse
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLinkResponse] = Field(default_factory=list)
    backlinks: list[VaultLinkResponse] = Field(default_factory=list)
```

Add the same optional newline contract to `VaultFileResponse`:

```python
from typing import Any, Literal


newline: Literal["lf", "crlf", "mixed", "none"] | None = None
```

Pass `file=page.file` in the router and serialize the already-tested nested
`VaultLinkResponse` records without partial dictionary fallbacks. Before
constructing the public page response, require
`page.file.content_hash` to match `^[0-9a-fA-F]{64}$`; an opened page may not
have a nullable or partial fingerprint even though file-list rows remain
backward compatible. Import `re` in `api/routers/vault.py` and add:

```python
if re.fullmatch(r"[0-9a-fA-F]{64}", page.file.content_hash or "") is None:
    raise LookupError("vault_page_content_hash_unavailable")
```

Map that failure to a path-free `409 vault_page_invalid`.

Handle the orphan sentinel before the router's generic `LookupError` mapping:

```python
message = str(exc)
if isinstance(exc, LookupError) and "vault_note_file_not_found" in message:
    return _error(
        status.HTTP_409_CONFLICT,
        "vault_canonical_file_unavailable",
    )
if isinstance(exc, LookupError) and ("vault_page_content_hash_unavailable" in message):
    return _error(status.HTTP_409_CONFLICT, "vault_page_invalid")
```

The public error detail contains only the stable code and never echoes the
exception message, root, or relative path. Retain the existing generic
`vault_page_not_found` behavior for a genuinely absent note.

- [ ] **Step 6: Run focused backend tests and GREEN**

Run:

```bash
PYTHONPATH=. uv run pytest \
  tests/test_vault_migration.py \
  tests/test_vault_repository.py \
  tests/test_vault_api.py -q
```

Then run the GREEN native projection proof inside the same ownership-safe
lifecycle:

```bash
DN_SURREAL_PREEXISTING_ID="$(docker compose ps --no-trunc -q surrealdb)"
DN_SURREAL_STARTED_ID=""

dn_cleanup_surreal() {
  DN_SURREAL_EXIT_STATUS=$?
  trap - EXIT
  if [ -n "$DN_SURREAL_STARTED_ID" ]; then
    DN_SURREAL_CURRENT_ID="$(
      docker inspect --format '{{.Id}}' "$DN_SURREAL_STARTED_ID" \
        2>/dev/null || true
    )"
    if [ "$DN_SURREAL_CURRENT_ID" = "$DN_SURREAL_STARTED_ID" ]; then
      docker stop "$DN_SURREAL_STARTED_ID" >/dev/null || {
        if [ "$DN_SURREAL_EXIT_STATUS" -eq 0 ]; then
          DN_SURREAL_EXIT_STATUS=1
        fi
      }
    elif [ -n "$DN_SURREAL_CURRENT_ID" ]; then
      DN_SURREAL_EXIT_STATUS=1
    fi
  fi
  exit "$DN_SURREAL_EXIT_STATUS"
}

trap dn_cleanup_surreal EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -z "$DN_SURREAL_PREEXISTING_ID" ]; then
  make database || exit 1
  DN_SURREAL_STARTED_ID="$(docker compose ps --no-trunc -q surrealdb)"
  test -n "$DN_SURREAL_STARTED_ID" || exit 1
fi
for _attempt in {1..40}; do
  curl --fail --silent http://127.0.0.1:8000/health >/dev/null && break
  sleep 0.25
done
curl --fail --silent http://127.0.0.1:8000/health >/dev/null || exit 1
SURREAL_INTEGRATION=1 \
SURREAL_URL=ws://localhost:8000/rpc \
PYTHONPATH=. uv run pytest tests/integration/test_vault_projection.py -q
```

Expected: all vault repository/API/projection tests pass.

- [ ] **Step 7: Commit**

```bash
git add \
  deeper_notebook/vault/repository.py \
  deeper_notebook/database/migrations/35.surrealql \
  deeper_notebook/database/migrations/35_down.surrealql \
  api/schemas/vault.py \
  api/routers/vault.py \
  tests/test_vault_migration.py \
  tests/test_vault_repository.py \
  tests/test_vault_api.py \
  tests/integration/test_vault_projection.py
git commit -m "feat(vault): expose canonical page identity"
```

---

### Task 2: Enforce Canonical Frontend Page Identity

**Files:**
- Modify: `frontend/src/lib/api/vault.ts`
- Modify: `frontend/src/lib/api/vault.test.ts`
- Modify: `frontend/src/lib/api/knowledge-workspace.ts`
- Modify: `frontend/src/lib/api/knowledge-workspace.test.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.ts`
- Modify: `frontend/src/lib/stores/knowledge-workspace-store.test.ts`

**Interfaces:**
- Produces: `VaultPage.file: VaultFile`
- Produces: `VaultLink.target_note_title?: string | null`
- Produces: `VaultLink.target_relative_path?: string | null`
- Produces: `VaultLink.source_start: number`
- Produces: `VaultLink.source_end: number`
- Produces: `VaultPageContractError.code`
- Produces: `reconcileTabReference(paneId, tabId, reference): void`
- Consumes: `VaultFile`, `KnowledgeTab`, `openKnowledgeTabSchema`

- [ ] **Step 1: Write hostile and inconsistent API response tests**

Add a valid page fixture containing `file`. Then add:

```typescript
it('rejects a page whose canonical file belongs to another vault', async () => {
  mockedGet.mockResolvedValueOnce({
    data: pageFixture({
      file: {
        ...fileFixture,
        vault_id: 'vault:other',
      },
    }),
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .rejects.toMatchObject({ code: 'page-invalid' })
})

it.each([
  '',
  '/Users/owner/private/two.md',
  '../outside.md',
  'pages\\two.md',
  'pages//two.md',
  'pages/./two.md',
  'pages/\0two.md',
  'C:/private/two.md',
  ' pages/two.md',
  'pages/two.md ',
])('rejects noncanonical target path %j', async (targetRelativePath) => {
  mockedGet.mockResolvedValueOnce({
    data: pageFixture({
      outgoing_links: [{
        ...linkFixture,
        resolved: true,
        target_note_id: 'note:two',
        target_note_title: 'Two',
        target_relative_path: targetRelativePath,
      }],
    }),
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .rejects.toMatchObject({ code: 'page-invalid' })
})

it('classifies missing canonical file metadata separately', async () => {
  mockedGet.mockResolvedValueOnce({
    data: pageFixture({ file: undefined }),
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
})

it('classifies a noncanonical page file path separately', async () => {
  mockedGet.mockResolvedValueOnce({
    data: pageFixture({
      file: { ...fileFixture, relative_path: '../outside.md' },
    }),
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
})

it.each([null, 'short', 'g'.repeat(64)])(
  'rejects page content hash %j',
  async (contentHash) => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        file: { ...fileFixture, content_hash: contentHash },
      }),
    })

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  },
)

it('translates the orphaned-note API error', async () => {
  mockedGet.mockRejectedValueOnce({
    isAxiosError: true,
    response: {
      status: 409,
      data: {
        detail: { code: 'vault_canonical_file_unavailable' },
      },
    },
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
})

it('accepts a resolved link with a present empty canonical title', async () => {
  mockedGet.mockResolvedValueOnce({
    data: pageFixture({
      outgoing_links: [{
        ...linkFixture,
        resolved: true,
        target_note_id: 'note:two',
        target_note_title: '',
        target_relative_path: 'pages/two.md',
      }],
    }),
  })

  await expect(vaultApi.page('vault:one', 'note:one'))
    .resolves.toMatchObject({
      outgoing_links: [expect.objectContaining({ target_note_title: '' })],
    })
})
```

Before RED, extend `knowledge-workspace.test.ts` with the same hostile path
table and prove both wire tabs and open-tab input reject every value.

- [ ] **Step 2: Run the API test and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/api/vault.test.ts \
  src/lib/api/knowledge-workspace.test.ts
```

Expected: failures because the page has no required file schema or requested
identity consistency check.

- [ ] **Step 3: Implement the Zod and requested-identity boundary**

Rename/export the existing workspace path schema and strengthen it as the one
canonical relative-path contract used by both APIs:

```typescript
export const canonicalVaultRelativePathSchema = z.string()
  .min(1)
  .max(4096)
  .superRefine(
  (value, context) => {
    const segments = value.split('/')
    if (
      !value
      || value.trim() !== value
      || value.startsWith('/')
      || /^[A-Za-z]:/.test(value)
      || value.includes('\\')
      || value.includes('\0')
      || segments.some((segment) =>
        !segment || segment === '.' || segment === '..')
    ) {
      context.addIssue({
        code: 'custom',
        message: 'value must be a canonical vault-relative path',
      })
    }
  },
)
```

Import the exported schema into `vault.ts`; use it for
`vaultFileSchema.relative_path`, every reconciled tab path, and resolved link
targets. Add the link fields and required page file:

```typescript
export const vaultLinkSchema = z.object({
  id: z.string(),
  source_note_id: z.string(),
  target_note_id: z.string().nullable(),
  target_note_title: z.string().nullable().optional(),
  target_relative_path: canonicalVaultRelativePathSchema.nullable().optional(),
  target_text: z.string(),
  source_note_title: z.string().nullable().optional(),
  target_heading: z.string().nullable().optional(),
  alias: z.string().nullable().optional(),
  link_kind: z.string(),
  resolved: z.boolean(),
  source_start: z.number().int().nonnegative(),
  source_end: z.number().int().nonnegative(),
}).passthrough().superRefine((link, context) => {
  if (link.resolved && (
    !link.target_note_id
    || link.target_note_title == null
    || link.target_relative_path == null
  )) {
    context.addIssue({
      code: 'custom',
      message: 'resolved link is missing canonical target identity',
    })
  }
  if (link.source_end < link.source_start) {
    context.addIssue({
      code: 'custom',
      message: 'source_end must not precede source_start',
    })
  }
})

export const vaultPageSchema = z.object({
  file: vaultFileSchema,
  note: z.object({
    id: z.string(),
    title: z.string().nullable().optional(),
    markdown: z.string().optional(),
    content: z.string().optional(),
    source_format: z.string().optional(),
    external_state: z.string().optional(),
    properties: z.record(z.string(), z.unknown()).optional(),
    tags: z.array(z.string()).optional(),
  }).passthrough(),
  blocks: z.array(vaultBlockSchema),
  tasks: z.array(z.unknown()),
  outgoing_links: z.array(vaultLinkSchema),
  backlinks: z.array(vaultLinkSchema),
}).passthrough()
```

Extend `vaultFileSchema` with the persisted parser metadata needed by Source
provenance:

```typescript
size_bytes: z.number().int().nonnegative(),
modified_ns: z.number().int().nonnegative(),
encoding: z.string().nullable(),
newline: z.enum(['lf', 'crlf', 'mixed', 'none']).nullable(),
deleted_state: z.enum(['present', 'missing']),
```

Keep `vaultFileSchema.content_hash` nullable because list responses may contain
old unscanned rows. Page acceptance is stricter: in `parseRequestedPage`,
require `page.file.content_hash` to match `/^[0-9a-f]{64}$/i` after the full
schema parse. A null, short, or non-hex fingerprint throws
`VaultPageContractError('page-invalid')`.

Use typed errors and a requested-identity parser:

```typescript
export type VaultPageContractErrorCode =
  | 'page-invalid'
  | 'canonical-path-unavailable'

export class VaultPageContractError extends Error {
  constructor(public readonly code: VaultPageContractErrorCode) {
    super(code)
    this.name = 'VaultPageContractError'
  }
}

function parseRequestedPage(
  vaultId: string,
  noteId: string,
  data: unknown,
): VaultPage {
  const canonicalFile = z.object({
    file: z.object({
      relative_path: canonicalVaultRelativePathSchema,
    }).passthrough(),
  }).passthrough().safeParse(data)
  if (!canonicalFile.success) {
    throw new VaultPageContractError('canonical-path-unavailable')
  }
  try {
    assertNoAbsolutePath(data)
  } catch {
    throw new VaultPageContractError('page-invalid')
  }
  const parsed = vaultPageSchema.safeParse(data)
  if (!parsed.success) {
    throw new VaultPageContractError('page-invalid')
  }
  const page = parsed.data
  if (
    page.file.vault_id !== vaultId
    || page.file.note_id !== noteId
    || page.note.id !== noteId
  ) {
    throw new VaultPageContractError('page-invalid')
  }
  if (!/^[0-9a-f]{64}$/i.test(page.file.content_hash ?? '')) {
    throw new VaultPageContractError('page-invalid')
  }
  return page
}
```

Call it from `vaultApi.page`. Wrap only the Axios request so the server's
stable page error codes cross the HTTP boundary:

```typescript
import axios from 'axios'

async function getRequestedPage(vaultId: string, noteId: string) {
  try {
    const response = await apiClient.get(/* existing page URL */)
    return parseRequestedPage(vaultId, noteId, response.data)
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const code = error.response?.data?.detail?.code
      if (code === 'vault_canonical_file_unavailable') {
        throw new VaultPageContractError('canonical-path-unavailable')
      }
      if (code === 'vault_page_invalid') {
        throw new VaultPageContractError('page-invalid')
      }
    }
    throw error
  }
}
```

Do not translate unrelated HTTP failures; `KnowledgePaneContent` retains its
generic load-error branch for them.

- [ ] **Step 4: Write store reconciliation tests**

```typescript
it('reconciles a hydrated tab to canonical metadata exactly once', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab({
    vaultId: 'vault:one',
    noteId: 'note:one',
    title: 'Synthetic',
    relativePath: 'note-one.md',
  })
  const before = useKnowledgeWorkspaceStore.getState()
  const tabId = before.panes['pane-1'].activeTabId!

  before.reconcileTabReference('pane-1', tabId, {
    title: 'Canonical',
    relativePath: 'pages/canonical.md',
  })
  const reconciled = useKnowledgeWorkspaceStore.getState()
  expect(reconciled.panes['pane-1'].tabs[0]).toMatchObject({
    title: 'Canonical',
    relativePath: 'pages/canonical.md',
  })
  expect(reconciled.revision).toBe(before.revision + 1)

  reconciled.reconcileTabReference('pane-1', tabId, {
    title: 'Canonical',
    relativePath: 'pages/canonical.md',
  })
  expect(useKnowledgeWorkspaceStore.getState().revision)
    .toBe(reconciled.revision)
})

it('refuses unsafe canonical reconciliation paths', () => {
  const store = useKnowledgeWorkspaceStore.getState()
  store.openTab(plan)
  const before = useKnowledgeWorkspaceStore.getState()
  const tabId = before.panes['pane-1'].activeTabId!

  before.reconcileTabReference('pane-1', tabId, {
    title: 'Unsafe',
    relativePath: '../outside.md',
  })

  expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
    .toMatchObject(plan)
})
```

- [ ] **Step 5: Run the store tests and observe RED**

Run:

```bash
cd frontend
npx vitest run src/lib/stores/knowledge-workspace-store.test.ts
```

Expected: TypeScript/runtime failure because `reconcileTabReference` is absent.

- [ ] **Step 6: Implement idempotent reconciliation**

Add the interface:

```typescript
reconcileTabReference: (
  paneId: string,
  tabId: string,
  reference: Pick<OpenKnowledgeTab, 'title' | 'relativePath'>,
) => void
```

Add the action:

```typescript
reconcileTabReference: (paneId, tabId, reference) => {
  const state = get()
  const pane = state.panes[paneId]
  const tab = pane?.tabs.find((candidate) => candidate.id === tabId)
  if (!pane || !tab) return
  const parsed = openKnowledgeTabSchema.safeParse({
    vaultId: tab.vaultId,
    noteId: tab.noteId,
    title: reference.title,
    relativePath: reference.relativePath,
    viewMode: tab.viewMode,
  })
  if (!parsed.success) return
  if (
    tab.title === parsed.data.title
    && tab.relativePath === parsed.data.relativePath
  ) {
    return
  }
  set({
    revision: state.revision + 1,
    panes: {
      ...state.panes,
      [paneId]: {
        ...pane,
        tabs: pane.tabs.map((candidate) => candidate.id === tabId
          ? {
              ...candidate,
              title: parsed.data.title,
              relativePath: parsed.data.relativePath,
            }
          : candidate),
      },
    },
  })
},
```

- [ ] **Step 7: Run focused frontend tests and GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/api/vault.test.ts \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/stores/knowledge-workspace-store.test.ts
```

Expected: both files pass.

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/src/lib/api/vault.ts \
  frontend/src/lib/api/vault.test.ts \
  frontend/src/lib/api/knowledge-workspace.ts \
  frontend/src/lib/api/knowledge-workspace.test.ts \
  frontend/src/lib/stores/knowledge-workspace-store.ts \
  frontend/src/lib/stores/knowledge-workspace-store.test.ts
git commit -m "feat(knowledge): enforce canonical page identity"
```

---

### Task 3: Add CodeMirror And The Shared Markdown Model

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/lib/vault/markdown-model.ts`
- Create: `frontend/src/lib/vault/markdown-model.test.ts`

**Interfaces:**
- Produces: `HeadingDescriptor`
- Produces: `buildMarkdownModel(markdown: string): MarkdownModel`
- Produces: stable `sourceFrom`, `sourceTo`, `slug`, `level`, and `text`
- Consumes: `markdownLanguage.parser`

- [ ] **Step 1: Install the exact CodeMirror dependency set**

Run:

```bash
cd frontend
npm install --save-exact \
  @codemirror/commands@6.10.4 \
  @codemirror/lang-markdown@6.5.1 \
  @codemirror/language@6.12.4 \
  @codemirror/search@6.7.1 \
  @codemirror/state@6.7.1 \
  @codemirror/view@6.43.7
```

Expected: only `package.json` and `package-lock.json` change.

- [ ] **Step 2: Write Markdown-model tests**

```typescript
import { describe, expect, it } from 'vitest'

import { buildMarkdownModel } from './markdown-model'

describe('buildMarkdownModel', () => {
  it('extracts six heading levels and stable duplicate slugs', () => {
    const model = buildMarkdownModel([
      '# Plan',
      '## Evidence',
      '###### Detail',
      '# Plan',
    ].join('\n'))

    expect(model.headings).toEqual([
      expect.objectContaining({ level: 1, text: 'Plan', slug: 'plan' }),
      expect.objectContaining({ level: 2, text: 'Evidence', slug: 'evidence' }),
      expect.objectContaining({ level: 6, text: 'Detail', slug: 'detail' }),
      expect.objectContaining({ level: 1, text: 'Plan', slug: 'plan-1' }),
    ])
  })

  it('does not treat fenced code headings as document headings', () => {
    const model = buildMarkdownModel([
      '```md',
      '# Not an outline item',
      '```',
      '# Real heading',
    ].join('\n'))

    expect(model.headings.map((heading) => heading.text))
      .toEqual(['Real heading'])
  })

  it('records source ranges for supported live-preview constructs', () => {
    const markdown = '# Plan\n\n**strong** and [[Evidence]] and `code`'
    const model = buildMarkdownModel(markdown)

    expect(model.constructs.map((construct) => construct.kind))
      .toEqual(expect.arrayContaining([
        'heading',
        'strong',
        'wikilink',
        'inline-code',
      ]))
    expect(model.constructs.every((construct) =>
      construct.from >= 0
      && construct.to > construct.from
      && construct.to <= markdown.length,
    )).toBe(true)
  })
})
```

- [ ] **Step 3: Run the model test and observe RED**

Run:

```bash
cd frontend
npx vitest run src/lib/vault/markdown-model.test.ts
```

Expected: module-not-found failure.

- [ ] **Step 4: Implement the syntax-tree model**

Define exact public types:

```typescript
export type MarkdownConstructKind =
  | 'heading'
  | 'emphasis'
  | 'strong'
  | 'strikethrough'
  | 'inline-code'
  | 'fenced-code'
  | 'link'
  | 'wikilink'
  | 'task-marker'
  | 'blockquote'
  | 'horizontal-rule'
  | 'list-marker'
  | 'tag'
  | 'footnote'
  | 'math'

export interface HeadingDescriptor {
  level: 1 | 2 | 3 | 4 | 5 | 6
  text: string
  slug: string
  sourceFrom: number
  sourceTo: number
}

export interface MarkdownConstruct {
  kind: MarkdownConstructKind
  from: number
  to: number
}

export interface MarkdownModel {
  headings: HeadingDescriptor[]
  constructs: MarkdownConstruct[]
}
```

Use `markdownLanguage.parser.parse(markdown)` for headings and Markdown
constructs, then run bounded regular-expression passes for Obsidian-only
wikilinks/tags not represented by the CommonMark tree. Sort constructs by
`from`, then `to`, and deduplicate exact `{kind, from, to}` triples.

Use this slug function:

```typescript
function baseSlug(text: string): string {
  const slug = text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en-US')
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
  return slug || 'section'
}
```

- [ ] **Step 5: Run tests and GREEN**

Run:

```bash
cd frontend
npx vitest run src/lib/vault/markdown-model.test.ts
npx tsc --noEmit
```

Expected: model tests and TypeScript pass.

- [ ] **Step 6: Commit**

```bash
git add \
  frontend/package.json \
  frontend/package-lock.json \
  frontend/src/lib/vault/markdown-model.ts \
  frontend/src/lib/vault/markdown-model.test.ts
git commit -m "feat(knowledge): model markdown for editor views"
```

---

### Task 4: Build The Locked CodeMirror Substrate And Source View

**Files:**
- Create: `frontend/src/components/vault/VaultCodeMirror.tsx`
- Create: `frontend/src/components/vault/VaultCodeMirror.test.tsx`
- Create: `frontend/src/components/vault/VaultSourceView.tsx`
- Create: `frontend/src/components/vault/VaultSourceView.test.tsx`
- Modify: `frontend/src/components/vault/vault.css`

**Interfaces:**
- Produces: `VaultCodeMirrorProps`
- Produces: `VaultCodeMirrorHandle.scrollToOffset(offset: number): void`
- Produces: `VaultSourceView`
- Consumes: `Extension[]`, exact projected Markdown, theme state, canonical file metadata

- [ ] **Step 1: Write locked CodeMirror and Source-view tests**

```typescript
it('exposes exact source while rejecting every mutation path', async () => {
  const ref = createRef<VaultCodeMirrorHandle>()
  const mutatingKeymap = keymap.of([{
    key: 'Mod-d',
    run: (view) => {
      view.dispatch({ changes: { from: 0, insert: 'changed' } })
      return true
    },
  }])
  render(
    <VaultCodeMirror
      ref={ref}
      ariaLabel="Plan source"
      markdown={'# Plan\r\n'}
      extensions={[mutatingKeymap]}
    />,
  )

  const editor = screen.getByRole('textbox', { name: 'Plan source' })
  expect(editor).toHaveAttribute('aria-readonly', 'true')
  expect(editor).not.toHaveAttribute('contenteditable', 'true')
  expect(ref.current?.getDocument()).toBe('# Plan\r\n')

  fireEvent.beforeInput(editor, {
    inputType: 'insertText',
    data: 'changed',
  })
  fireEvent.paste(editor, {
    clipboardData: { getData: () => 'changed' },
  })
  fireEvent.drop(editor, {
    dataTransfer: { getData: () => 'changed' },
  })
  fireEvent.keyDown(editor, { key: 'd', metaKey: true })

  const view = EditorView.findFromDOM(editor)
  expect(view).not.toBeNull()
  expect(view!.state.facet(EditorState.readOnly)).toBe(true)
  expect(view!.state.facet(EditorView.editable)).toBe(false)
  view!.dispatch({ changes: { from: 0, insert: 'changed' } })

  expect(ref.current?.getDocument()).toBe('# Plan\r\n')
})

it('offers non-mutating local search and code folding', () => {
  render(
    <VaultCodeMirror
      ariaLabel="Plan source"
      markdown={'# Plan\n\nDetails\n'}
      extensions={[]}
    />,
  )
  const editor = screen.getByRole('textbox', { name: 'Plan source' })
  const view = EditorView.findFromDOM(editor)!
  expect(document.querySelector('.cm-foldGutter')).not.toBeNull()
  expect(openSearchPanel(view)).toBe(true)
  expect(document.querySelector('.cm-search')).not.toBeNull()
  expect(view.state.doc.toString()).toBe('# Plan\n\nDetails\n')
})
```

Add a prop-update test proving that a new server snapshot replaces the editor
document only through the controlled external-update annotation. Add the Source
test before running RED:

```typescript
it('shows exact canonical source and provenance without edit controls', () => {
  render(
    <VaultSourceView
      title="Plan"
      markdown={'---\r\ntitle: Plan\r\n---\r\n# Plan\r\n'}
      file={{
        ...fileFixture,
        relative_path: 'pages/plan.md',
        format: 'obsidian',
        content_hash: 'a'.repeat(64),
        encoding: 'utf-8',
        newline: 'crlf',
        size_bytes: 39,
      }}
    />,
  )

  expect(screen.getByRole('textbox', { name: 'Plan source' }))
    .toHaveAttribute('aria-readonly', 'true')
  expect(screen.getByText('pages/plan.md')).toBeInTheDocument()
  expect(screen.getByText('aaaaaaaaaaaa')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /save/i }))
    .not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run both component tests and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultCodeMirror.test.tsx \
  src/components/vault/VaultSourceView.test.tsx
```

Expected: module-not-found failures for both components.

- [ ] **Step 3: Implement the locked editor lifecycle and capabilities**

Define the handle and props:

```typescript
export interface VaultCodeMirrorHandle {
  getDocument: () => string
  scrollToOffset: (offset: number) => void
}

export interface VaultCodeMirrorProps {
  ariaLabel: string
  markdown: string
  extensions: Extension[]
  className?: string
}
```

Create `EditorView` once in `useLayoutEffect`. The base extensions must include:

```typescript
import { markdown } from '@codemirror/lang-markdown'
import {
  defaultHighlightStyle,
  foldGutter,
  foldKeymap,
  syntaxHighlighting,
} from '@codemirror/language'
import {
  findNext,
  findPrevious,
  openSearchPanel,
} from '@codemirror/search'

const lockedExtensions: Extension[] = [
  EditorState.readOnly.of(true),
  EditorView.editable.of(false),
  EditorView.contentAttributes.of({
    role: 'textbox',
    'aria-multiline': 'true',
    'aria-readonly': 'true',
  }),
  lineNumbers(),
  foldGutter(),
  highlightActiveLine(),
  drawSelection(),
  syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
  markdown(),
  keymap.of([
    { key: 'Mod-f', run: openSearchPanel },
    { key: 'F3', run: findNext },
    { key: 'Shift-F3', run: findPrevious },
    ...foldKeymap,
  ]),
]
```

Define the external snapshot annotation and add a transaction filter:

```typescript
const externalUpdate = Annotation.define<boolean>()

const rejectDocumentChanges = EditorState.transactionFilter.of(
  (transaction) => transaction.docChanged && !transaction.annotation(externalUpdate)
    ? []
    : transaction,
)
```

Update props by dispatching one `externalUpdate` transaction. Destroy the view
in the effect cleanup.

- [ ] **Step 4: Implement `VaultSourceView` and Research Core CSS**

Render `VaultCodeMirror` plus a status bar with relative path, format,
`file.encoding`, `file.newline`, byte size, and the first 12 hash characters.
Do not accept a separate newline prop that could disagree with the canonical
file record. Add `.dn-vault-editor` styles using existing CSS variables; use
teal for active line/gutter and cyan for focus without hard-coded light-only
backgrounds.

- [ ] **Step 5: Run focused tests and GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultCodeMirror.test.tsx \
  src/components/vault/VaultSourceView.test.tsx
npx tsc --noEmit
```

Expected: tests and TypeScript pass.

- [ ] **Step 6: Commit**

```bash
git add \
  frontend/src/components/vault/VaultCodeMirror.tsx \
  frontend/src/components/vault/VaultCodeMirror.test.tsx \
  frontend/src/components/vault/VaultSourceView.tsx \
  frontend/src/components/vault/VaultSourceView.test.tsx \
  frontend/src/components/vault/vault.css
git commit -m "feat(knowledge): add read-only markdown source view"
```

---

### Task 5: Upgrade Reading, Outline, Properties, Tags, And Footnotes

**Files:**
- Modify: `frontend/src/components/vault/VaultMarkdown.tsx`
- Modify: `frontend/src/components/vault/VaultMarkdown.test.tsx`
- Create: `frontend/src/lib/vault/remark-vault-links.ts`
- Create: `frontend/src/lib/vault/remark-vault-links.test.ts`
- Create: `frontend/src/components/vault/VaultNoteSidebar.tsx`
- Create: `frontend/src/components/vault/VaultNoteSidebar.test.tsx`

**Interfaces:**
- Produces: `VaultMarkdown({ noteId, headingIdPrefix, markdown, links,
  onNavigate, onPreview, footnoteLabel })`
- Produces: `remarkVaultLinks({ links })`
- Produces: `VaultNoteSidebar({ model, page, onHeading })`
- Consumes: `MarkdownModel`, `VaultPage`, `VaultLink`

- [ ] **Step 1: Write Reading-mode behavior tests**

Extend `VaultMarkdown.test.tsx`:

```typescript
it('renders GFM footnotes math anchors and disabled tasks safely', () => {
  render(
    <VaultMarkdown
      noteId="note:plan"
      headingIdPrefix="pane-1-tab-1"
      markdown={[
        '# Plan',
        '# Plan',
        '',
        '- [ ] Review',
        '',
        'Evidence[^1] and $x^2$.',
        '',
        '[^1]: Source note',
      ].join('\n')}
      links={[]}
      onNavigate={vi.fn()}
      onPreview={vi.fn()}
      footnoteLabel="Footnotes"
    />,
  )

  const headings = screen.getAllByRole('heading', { name: 'Plan' })
  expect(headings[0]).toHaveAttribute('id', 'pane-1-tab-1-plan')
  expect(headings[1]).toHaveAttribute('id', 'pane-1-tab-1-plan-1')
  expect(screen.getByRole('checkbox', { name: /review/i }))
    .toBeDisabled()
  expect(document.querySelector('.katex')).not.toBeNull()
  expect(screen.getByRole('doc-noteref')).toBeInTheDocument()
})

it('keeps external links inert and previews resolved internal links', () => {
  const onPreview = vi.fn()
  render(
    <VaultMarkdown
      noteId="note:plan"
      headingIdPrefix="pane-1-tab-1"
      markdown={'[[Research]] and [Web](https://example.com)'}
      links={[resolvedLinkFixture]}
      onNavigate={vi.fn()}
      onPreview={onPreview}
      footnoteLabel="Footnotes"
    />,
  )

  fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
  expect(onPreview).toHaveBeenCalledWith(resolvedLinkFixture)
  expect(screen.queryByRole('link', { name: 'Web' })).not.toBeInTheDocument()
})

it('maps a resolved Markdown link by its UTF-8 source span', () => {
  const markdown = 'é [Research](pages/research.md)'
  const sourceStart = new TextEncoder().encode('é ').length
  const sourceEnd = new TextEncoder().encode(markdown).length
  const onPreview = vi.fn()
  render(
    <VaultMarkdown
      noteId="note:plan"
      headingIdPrefix="pane-1-tab-1"
      markdown={markdown}
      links={[{
        ...resolvedLinkFixture,
        link_kind: 'markdown',
        target_text: 'pages/research.md',
        source_start: sourceStart,
        source_end: sourceEnd,
      }]}
      onNavigate={vi.fn()}
      onPreview={onPreview}
      footnoteLabel="Footnotes"
    />,
  )

  fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
  expect(onPreview).toHaveBeenCalled()
})

it('leaves an unresolved Markdown link inert', () => {
  render(
    <VaultMarkdown
      noteId="note:plan"
      headingIdPrefix="pane-1-tab-1"
      markdown={'[Missing](pages/missing.md)'}
      links={[{
        ...unresolvedLinkFixture,
        link_kind: 'markdown',
        source_start: 0,
        source_end: 27,
      }]}
      onNavigate={vi.fn()}
      onPreview={vi.fn()}
      footnoteLabel="Footnotes"
    />,
  )
  expect(screen.queryByRole('button', { name: 'Missing' }))
    .not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Missing' }))
    .not.toBeInTheDocument()
})
```

Write the sidebar test before implementation:

```typescript
it('announces heading levels and navigates duplicate slugs', () => {
  const onHeading = vi.fn()
  render(
    <VaultNoteSidebar
      model={buildMarkdownModel('# Plan\n## Evidence\n# Plan')}
      page={pageFixture}
      onHeading={onHeading}
    />,
  )

  fireEvent.click(screen.getByRole('button', {
    name: 'Level 2 Evidence',
  }))
  expect(onHeading).toHaveBeenCalledWith(
    expect.objectContaining({ slug: 'evidence', level: 2 }),
  )
  expect(screen.getByText('pages/plan.md')).toBeInTheDocument()
  expect(screen.getByText('#research')).toBeInTheDocument()
})
```

- [ ] **Step 2: Write span-preserving wiki-link plugin tests**

Create `remark-vault-links.test.ts` before implementation. Parse a fixture with
a Unicode prefix and duplicate display labels:

```typescript
const markdown = 'é [[Research|Same]] then [[Research|Same]]'
const firstStart = utf8ByteLength('é ')
const firstEnd = firstStart + utf8ByteLength('[[Research|Same]]')
const secondStart = utf8ByteLength('é [[Research|Same]] then ')
const secondEnd = secondStart + utf8ByteLength('[[Research|Same]]')
```

Give the two spans different resolved target note IDs. Assert the plugin leaves
`file.value === markdown`, produces two `a` nodes with their original
JavaScript `position` ranges and exact UTF-8 `data-source-start` /
`data-source-end` values, and does not resolve by label. Extend
`VaultMarkdown.test.tsx` to click each identical “Same” button and assert the
first navigates to the first note and the second to the second note.

For an ordinary Markdown `link` node, add a Unicode-prefix test proving the
renderer converts the node's original JavaScript offsets to UTF-8 byte offsets
and matches exactly one outgoing-link record.

- [ ] **Step 3: Run Reading, plugin, and sidebar tests and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultMarkdown.test.tsx \
  src/lib/vault/remark-vault-links.test.ts \
  src/components/vault/VaultNoteSidebar.test.tsx
```

Expected: missing KaTeX renderer, duplicate IDs, preview callback, and task
accessibility failures, plus missing plugin and sidebar modules.

- [ ] **Step 4: Implement safe Reading renderers and the shared sidebar**

Use:

```tsx
<ReactMarkdown
  remarkPlugins={[
    remarkGfm,
    remarkMath,
    [remarkVaultLinks, { links }],
  ]}
  rehypePlugins={[rehypeKatex]}
  remarkRehypeOptions={{
    clobberPrefix: `dn-${noteId}-`,
    footnoteLabel,
  }}
  components={components}
>
  {markdown}
</ReactMarkdown>
```

Implement `remarkVaultLinks` as a local MDAST transformer without rewriting the
Markdown string. Walk text nodes recursively. When a node has
`position.start.offset`, split `[[target|alias]]` tokens into surrounding text
nodes and custom link nodes with:

- `data.hName = 'a'`;
- `data.hProperties['data-vault-link'] = 'wiki'`;
- exact `data-source-start` / `data-source-end` UTF-8 byte offsets computed
  from the original `file.value`;
- original JavaScript `position.start.offset` / `position.end.offset`.

Do not add a dependency merely to traverse the tree, and do not mutate
`file.value`. For standard Markdown link nodes, use their original positions
and convert those JavaScript offsets against the original Markdown to UTF-8
byte offsets. Resolve a rendered anchor only when one outgoing link has the
exact source span; duplicate labels must remain independent.

Build the heading component map from `buildMarkdownModel(markdown).headings`
using one render-order cursor per heading level. Prefix each rendered heading
ID with `headingIdPrefix`, retain its unprefixed slug in
`data-heading-slug`, and never query the global document.
Render only matched resolved wiki/Markdown links as buttons, tasks as disabled
inputs, attachments as text metadata, same-document generated footnote anchors
with their semantic roles, and external or unresolved anchors as inert spans.

Render four sections: Outline, Properties, Tags, Source. Convert property values
with a bounded formatter that renders scalars directly and JSON-stringifies
arrays/objects up to 2,000 characters. Sort property keys and tags
locale-insensitively for deterministic output.

- [ ] **Step 5: Run focused tests and GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultMarkdown.test.tsx \
  src/lib/vault/remark-vault-links.test.ts \
  src/components/vault/VaultNoteSidebar.test.tsx
```

Expected: both files pass.

- [ ] **Step 6: Commit**

```bash
git add \
  frontend/src/components/vault/VaultMarkdown.tsx \
  frontend/src/components/vault/VaultMarkdown.test.tsx \
  frontend/src/lib/vault/remark-vault-links.ts \
  frontend/src/lib/vault/remark-vault-links.test.ts \
  frontend/src/components/vault/VaultNoteSidebar.tsx \
  frontend/src/components/vault/VaultNoteSidebar.test.tsx
git commit -m "feat(knowledge): enrich read-only page reading"
```

---

### Task 6: Add Inline Live Preview

**Files:**
- Create: `frontend/src/lib/vault/live-preview.ts`
- Create: `frontend/src/lib/vault/live-preview.test.ts`
- Create: `frontend/src/components/vault/VaultLivePreview.tsx`
- Create: `frontend/src/components/vault/VaultLivePreview.test.tsx`
- Modify: `frontend/src/components/vault/vault.css`

**Interfaces:**
- Produces: `livePreviewExtension(options): Extension`
- Produces: `buildLivePreviewDecorations(view): DecorationSet`
- Produces: `VaultLivePreview`
- Consumes: `MarkdownModel`, `VaultLink[]`, visible ranges, editor selection

- [ ] **Step 1: Write pure decoration tests**

Create states with `EditorState.create()` and assert decoration ranges:

```typescript
it('collapses supported punctuation outside selection', () => {
  const state = EditorState.create({
    doc: '# Plan\n\n**Strong** and `code`',
    selection: { anchor: 7 },
    extensions: [markdown()],
  })
  const decorations = buildLivePreviewDecorationRecords(
    state,
    [{ from: 0, to: state.doc.length }],
  )

  expect(decorations).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: 'heading-mark', from: 0, to: 2 }),
    expect.objectContaining({ kind: 'strong-mark', from: 8, to: 10 }),
    expect.objectContaining({ kind: 'inline-code-mark' }),
  ]))
})

it('reveals exact tokens intersecting the selection', () => {
  const state = EditorState.create({
    doc: '**Strong**',
    selection: { anchor: 1 },
    extensions: [markdown()],
  })

  expect(buildLivePreviewDecorationRecords(
    state,
    [{ from: 0, to: 10 }],
  )).toEqual([])
})

it('leaves unsupported syntax visible', () => {
  const state = EditorState.create({
    doc: '%% Obsidian comment syntax remains inspectable %%',
    extensions: [markdown()],
  })

  expect(buildLivePreviewDecorationRecords(
    state,
    [{ from: 0, to: state.doc.length }],
  )).toEqual([])
})
```

Add a table-driven test that covers the full promised construct set, not merely
representatives:

```typescript
it.each([
  ['heading', '# Heading', 'heading-mark'],
  ['emphasis', '*emphasis*', 'emphasis-mark'],
  ['strong', '**strong**', 'strong-mark'],
  ['strikethrough', '~~strike~~', 'strikethrough-mark'],
  ['inline code', '`code`', 'inline-code-mark'],
  ['fenced code', '```ts\nconst x = 1\n```', 'fenced-code-mark'],
  ['Markdown link', '[Page](pages/page.md)', 'markdown-link'],
  ['wiki link', '[[Page]]', 'wiki-link'],
  ['task marker', '- [ ] task', 'task-marker'],
  ['blockquote', '> quote', 'blockquote-mark'],
  ['horizontal rule', '---', 'horizontal-rule'],
  ['ordered list', '1. item', 'ordered-list-mark'],
  ['unordered list', '- item', 'unordered-list-mark'],
  ['tag', '#research', 'tag'],
  ['footnote', 'evidence[^1]\n\n[^1]: source', 'footnote-mark'],
  ['math', '$x^2$', 'math-mark'],
] as const)('decorates %s', (_name, source, expectedKind) => {
  const state = previewState(source)
  const records = buildLivePreviewDecorationRecords(
    state,
    [{ from: 0, to: state.doc.length }],
  )
  expect(records).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: expectedKind }),
  ]))
})
```

The shared `MarkdownConstructKind` union includes every expected kind above.
Use the CodeMirror Markdown syntax tree where it supplies a construct and
bounded visible-range passes for wiki links, tags, footnotes, and math that the
base parser does not expose. Retain the selection-reveal and unsupported-source
tests.

Add the component test before implementation:

```typescript
it('renders live preview as a locked editor with navigable wiki links', () => {
  const onNavigate = vi.fn()
  render(
    <VaultLivePreview
      title="Plan"
      markdown={'# Plan\n\n[[Research]]'}
      links={[resolvedLinkFixture]}
      onNavigate={onNavigate}
    />,
  )

  expect(screen.getByRole('textbox', { name: 'Plan live preview' }))
    .toHaveAttribute('aria-readonly', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Research' }))
  expect(onNavigate).toHaveBeenCalledWith('note:research')
})

it('navigates a resolved Markdown link by its UTF-8 source span', () => {
  const markdown = 'é [Research](pages/research.md)'
  const onNavigate = vi.fn()
  render(
    <VaultLivePreview
      title="Plan"
      markdown={markdown}
      links={[{
        ...resolvedLinkFixture,
        link_kind: 'markdown',
        source_start: new TextEncoder().encode('é ').length,
        source_end: new TextEncoder().encode(markdown).length,
      }]}
      onNavigate={onNavigate}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Research' }))
  expect(onNavigate).toHaveBeenCalledWith('note:research')
})
```

- [ ] **Step 2: Run pure and component tests and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/vault/live-preview.test.ts \
  src/components/vault/VaultLivePreview.test.tsx
```

Expected: module-not-found failures.

- [ ] **Step 3: Implement the decoration engine and component**

Define:

```typescript
export interface PreviewDecorationRecord {
  kind: string
  from: number
  to: number
  decoration: Decoration
}

export function buildLivePreviewDecorationRecords(
  state: EditorState,
  ranges: readonly { from: number; to: number }[],
): PreviewDecorationRecord[]
```

Rules:

- Parse only constructs intersecting a visible range.
- If a construct intersects any selection range, return no punctuation-replace
  decorations for that construct.
- Use `Decoration.replace()` only within a single line.
- Use `Decoration.mark()` for rendered emphasis/strong/code/link/tag styles.
- Use disabled checkbox widgets for task markers.
- Convert only source-span-matched resolved wiki and Markdown links to atomic
  button widgets with a supplied `onNavigate(noteId)` callback. Convert parser
  UTF-8 byte spans to JavaScript string offsets before matching; never resolve
  by label alone.
- Catch per-construct errors and omit only that decoration.
- Sort by `from`, `startSide`, and `to` before building the range set.

Expose the records to tests and wrap them with a `ViewPlugin.fromClass` for
runtime updates on `docChanged`, `selectionSet`, or `viewportChanged`.

Compose `VaultCodeMirror` with:

```typescript
const extensions = useMemo(
  () => [livePreviewExtension({ links, onNavigate })],
  [links, onNavigate],
)
```

Use Research Core classes for heading, mark, internal-link, task, quote, tag,
and code decorations.

- [ ] **Step 4: Run focused tests and GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/vault/live-preview.test.ts \
  src/components/vault/VaultLivePreview.test.tsx \
  src/components/vault/VaultCodeMirror.test.tsx
npx tsc --noEmit
```

Expected: all tests and TypeScript pass.

- [ ] **Step 5: Commit**

```bash
git add \
  frontend/src/lib/vault/live-preview.ts \
  frontend/src/lib/vault/live-preview.test.ts \
  frontend/src/components/vault/VaultLivePreview.tsx \
  frontend/src/components/vault/VaultLivePreview.test.tsx \
  frontend/src/components/vault/vault.css
git commit -m "feat(knowledge): add read-only live preview"
```

---

### Task 7: Add Safe Page Previews And Canonical Navigation

**Files:**
- Modify: `frontend/src/lib/hooks/use-vault.ts`
- Create: `frontend/src/components/vault/VaultPagePreview.tsx`
- Create: `frontend/src/components/vault/VaultPagePreview.test.tsx`
- Modify: `frontend/src/components/vault/VaultMarkdown.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`

**Interfaces:**
- Produces: `useVaultPagePreview(vaultId, noteId, enabled)`
- Produces: `VaultPagePreview`
- Produces: `KnowledgeNavigate(vaultId, noteId, canonicalRelativePath, title, paneId)`
- Consumes: `VaultLink.target_relative_path`, `VaultLink.target_note_title`

- [ ] **Step 1: Write canonical-only navigation tests**

Replace synthetic-link fixtures with canonical target fields. Add:

```typescript
it('refuses resolved navigation without a canonical target path', async () => {
  vaultQueries.outgoing.mockReturnValue({
    data: [{
      ...resolvedLink,
      target_relative_path: null,
    }],
    isLoading: false,
    isError: false,
  })
  await renderExplorer()
  await selectFile('notes/one.md')

  expect(screen.queryByRole('button', { name: 'Navigate Markdown link' }))
    .not.toBeInTheDocument()
  const tabs = useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs
  expect(tabs).toHaveLength(1)
})

it('opens resolved links with their canonical target path', async () => {
  await renderExplorer()
  await selectFile('notes/one.md')
  fireEvent.click(screen.getByRole('button', {
    name: 'Navigate Markdown link',
  }))

  expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[1])
    .toMatchObject({
      noteId: 'note:linked',
      title: 'Linked',
      relativePath: 'notes/linked.md',
    })
})
```

Write preview interaction tests before implementation. Use fake timers:

```typescript
it('loads a bounded preview after hover intent and closes with Escape', async () => {
  vi.useFakeTimers()
  render(
    <VaultPagePreview
      vaultId="vault:one"
      link={resolvedLinkFixture}
      trigger={<button type="button">Research</button>}
    />,
  )

  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Research' }))
  expect(vaultApi.page).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(250)
  expect(vaultApi.page).toHaveBeenCalledWith(
    'vault:one',
    'note:research',
  )
  expect(await screen.findByText('pages/research.md')).toBeInTheDocument()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByText('pages/research.md')).not.toBeInTheDocument()
  vi.useRealTimers()
})

it('opens the same preview on keyboard focus', async () => {
  vi.useFakeTimers()
  render(previewFixture())
  fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
  await vi.advanceTimersByTimeAsync(250)
  expect(await screen.findByRole('dialog', { name: 'Research preview' }))
    .toBeInTheDocument()
  vi.useRealTimers()
})
```

Also write these cache/failure/security cases before implementation:

```typescript
it('reuses one validated page query inside the stale window', async () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      {previewFixture()}
    </QueryClientProvider>,
  )
  await openPreviewByHover()
  await closePreviewWithEscape()
  await openPreviewByFocus()
  expect(vaultApi.page).toHaveBeenCalledTimes(1)
})

it('keeps navigation available when the preview query fails', async () => {
  vaultApi.page.mockRejectedValueOnce(new Error('preview unavailable'))
  const onNavigate = vi.fn()
  render(previewFixture({ onNavigate }))
  await openPreviewByFocus()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Research' }))
  expect(onNavigate).toHaveBeenCalledWith('note:research')
})

it('never displays an absolute path returned by a hostile response', async () => {
  vaultApi.page.mockRejectedValueOnce(
    new VaultPageContractError('canonical-path-unavailable'),
  )
  render(previewFixture())
  await openPreviewByHover()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(document.body).not.toHaveTextContent('/Users/')
  expect(screen.getByRole('button', { name: 'Research' }))
    .toBeInTheDocument()
})
```

Use a fresh `QueryClient` per test, `staleTime: 30_000`, and restore real/fake
timers in `afterEach` so cache and intent timing assertions cannot leak across
tests.

- [ ] **Step 2: Run navigation and preview tests and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/VaultPagePreview.test.tsx
```

Expected: the old `fallbackRelativePath()` manufactures a path, canonical
fields are not used, and the preview module is absent.

- [ ] **Step 3: Implement canonical navigation and delayed cached previews**

Delete `fallbackRelativePath()`. Change navigation so it opens only when the
listed file, an existing canonical tab, or the resolved link supplies the path.
An empty-but-present canonical title remains valid; use `target_text` only as
the display label:

```typescript
if (!relativePathHint) return
openTab({
  vaultId: targetVaultId,
  noteId: targetNoteId,
  title: titleHint?.trim() || targetText,
  relativePath: relativePathHint,
}, paneId)
```

Pass `link.target_relative_path`, `link.target_note_title`, and
`link.target_text` from `KnowledgePaneContent.navigate()`.

Add:

```typescript
export function useVaultPagePreview(
  vaultId?: string,
  noteId?: string,
  enabled = false,
) {
  return useQuery({
    queryKey: vaultKeys.page(vaultId ?? '', noteId ?? ''),
    queryFn: () => vaultApi.page(vaultId!, noteId!),
    enabled: Boolean(vaultId && noteId && enabled),
    staleTime: 30_000,
  })
}
```

`VaultPagePreview` owns a 250 ms intent timer, uses Radix Popover, shows only
title, canonical path, format, three non-empty block excerpts capped at 240
characters each, and link counts. It opens on hover or focus, closes on Escape,
and suppresses its body on query failure while leaving the independent trigger
and its click navigation active.

- [ ] **Step 4: Run focused tests and GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/VaultMarkdown.test.tsx \
  src/components/vault/VaultPagePreview.test.tsx
```

Expected: all tests pass with no synthetic navigation path.

- [ ] **Step 5: Commit**

```bash
git add \
  frontend/src/lib/hooks/use-vault.ts \
  frontend/src/components/vault/VaultPagePreview.tsx \
  frontend/src/components/vault/VaultPagePreview.test.tsx \
  frontend/src/components/vault/VaultMarkdown.tsx \
  frontend/src/components/vault/KnowledgeExplorer.tsx \
  frontend/src/components/vault/KnowledgeExplorer.test.tsx
git commit -m "feat(knowledge): add canonical page previews"
```

---

### Task 8: Integrate Four Modes, Sidebar, Shortcuts, And Locales

**Files:**
- Create: `frontend/src/components/vault/VaultEditorBoundary.tsx`
- Create: `frontend/src/components/vault/VaultEditorBoundary.test.tsx`
- Create: `frontend/src/components/vault/VaultDocumentView.tsx`
- Create: `frontend/src/components/vault/VaultDocumentView.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgePaneContent.tsx`
- Create: `frontend/src/components/vault/KnowledgePaneContent.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`
- Modify: `frontend/src/lib/locales/bn-IN/index.ts`
- Modify: `frontend/src/lib/locales/ca-ES/index.ts`
- Modify: `frontend/src/lib/locales/de-DE/index.ts`
- Modify: `frontend/src/lib/locales/en-US/index.ts`
- Modify: `frontend/src/lib/locales/es-ES/index.ts`
- Modify: `frontend/src/lib/locales/fr-FR/index.ts`
- Modify: `frontend/src/lib/locales/it-IT/index.ts`
- Modify: `frontend/src/lib/locales/ja-JP/index.ts`
- Modify: `frontend/src/lib/locales/pl-PL/index.ts`
- Modify: `frontend/src/lib/locales/pt-BR/index.ts`
- Modify: `frontend/src/lib/locales/ru-RU/index.ts`
- Modify: `frontend/src/lib/locales/tr-TR/index.ts`
- Modify: `frontend/src/lib/locales/zh-CN/index.ts`
- Modify: `frontend/src/lib/locales/zh-TW/index.ts`
- Modify: `frontend/src/lib/locales/index.test.ts`

**Interfaces:**
- Produces: four persisted mode buttons
- Produces: workspace-scoped `Control+1` through `Control+4`
- Produces: display-only Reading fallback after editor initialization failure
- Produces: explicit empty-note state in every document mode
- Produces: pane-scoped heading anchors through `viewId`
- Consumes: `VaultDocumentView`, `VaultNoteSidebar`, `VaultPageContractError`,
  `reconcileTabReference`

- [ ] **Step 1: Write document-view selection tests**

```typescript
it.each([
  ['reading', 'Plan reading view'],
  ['source', 'Plan source'],
  ['live-preview', 'Plan live preview'],
] as const)('renders %s mode', (mode, accessibleName) => {
  render(
    <VaultDocumentView
      viewId="pane-1:tab-1"
      mode={mode}
      page={pageFixture}
      onNavigate={vi.fn()}
      onPreview={vi.fn()}
    />,
  )
  expect(screen.getByLabelText(accessibleName)).toBeInTheDocument()
})

it.each(['reading', 'source', 'live-preview'] as const)(
  'renders an explicit empty-note state in %s mode',
  (mode) => {
    render(
      <VaultDocumentView
        viewId="pane-1:tab-1"
        mode={mode}
        page={pageFixtureWithMarkdown('')}
        onNavigate={vi.fn()}
        onPreview={vi.fn()}
      />,
    )
    expect(screen.getByText('knowledge.emptyNote')).toBeInTheDocument()
  },
)

it('preserves an explicitly empty canonical content field', () => {
  render(
    <VaultDocumentView
      viewId="pane-1:tab-1"
      mode="reading"
      page={pageFixtureWith({
        note: { content: '', markdown: '# Stale fallback' },
        blocks: [{ markdown: '# Stale block' }],
      })}
      onNavigate={vi.fn()}
      onPreview={vi.fn()}
    />,
  )
  expect(screen.getByText('knowledge.emptyNote')).toBeInTheDocument()
  expect(screen.queryByText('Stale fallback')).not.toBeInTheDocument()
  expect(screen.queryByText('Stale block')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Write editor-fallback and pane integration tests**

Test the error boundary with a child that throws and a stable reset key:

```typescript
function BrokenEditor(): never {
  throw new Error('editor failed')
}

it('shows its Reading fallback and resets for another document', () => {
  const { rerender } = render(
    <VaultEditorBoundary
      resetKey="note:one"
      fallback={<div aria-label="Plan reading view" />}
    >
      <BrokenEditor />
    </VaultEditorBoundary>,
  )
  expect(screen.getByLabelText('Plan reading view')).toBeInTheDocument()

  rerender(
    <VaultEditorBoundary
      resetKey="note:two"
      fallback={<div aria-label="Evidence reading view" />}
    >
      <div aria-label="Evidence source" />
    </VaultEditorBoundary>,
  )
  expect(screen.getByLabelText('Evidence source')).toBeInTheDocument()
})
```

The boundary is display-only: `VaultDocumentView` wraps Source and Live Preview
with the safe Reading renderer as `fallback`, while `KnowledgePaneContent`
continues to read `activeTab.viewMode` unchanged. Add an integration assertion
that a mocked editor failure renders Reading while the store still contains
`viewMode: 'live-preview'`.

Add explicit page-error rendering tests:

```typescript
it.each([
  ['canonical-path-unavailable', 'knowledge.canonicalPathUnavailable'],
  ['page-invalid', 'knowledge.pageInvalid'],
] as const)('renders %s without opening an editor', async (code, message) => {
  vaultQueries.page.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: true,
    error: new VaultPageContractError(code),
  })
  await renderPane()
  expect(screen.getByText(message)).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})
```

Extend `frontend/src/lib/locales/index.test.ts` with one assertion that every
locale resolves all newly listed `knowledge.*` keys. This test must be written
before the locale objects are changed.

```typescript
it('reconciles canonical tab identity and persists all four modes', async () => {
  await renderPane()
  await waitFor(() => {
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject({
        title: 'Canonical Plan',
        relativePath: 'pages/plan.md',
      })
  })

  for (const [label, mode] of [
    ['knowledge.reader', 'reading'],
    ['knowledge.source', 'source'],
    ['knowledge.livePreview', 'live-preview'],
    ['knowledge.localGraph', 'graph'],
  ] as const) {
    fireEvent.click(screen.getByRole('button', { name: label }))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].viewMode)
      .toBe(mode)
  }
})

it('switches modes with workspace-scoped Control number shortcuts', async () => {
  await renderPane()
  const region = screen.getByRole('region', { name: /knowledge pane/i })
  fireEvent.keyDown(region, { key: '3', ctrlKey: true })
  expect(screen.getByLabelText('Canonical Plan live preview'))
    .toBeInTheDocument()
  fireEvent.keyDown(window, { key: '2', ctrlKey: true })
  expect(screen.queryByLabelText('Canonical Plan source'))
    .not.toBeInTheDocument()
})
```

- [ ] **Step 3: Run component tests and observe RED**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultEditorBoundary.test.tsx \
  src/components/vault/VaultDocumentView.test.tsx \
  src/components/vault/KnowledgePaneContent.test.tsx \
  src/lib/locales/index.test.ts
```

Expected: modules, fallback behavior, empty-note state, and four-mode controls
are absent.

- [ ] **Step 4: Implement `VaultDocumentView`**

Build the Markdown model once:

```typescript
const model = useMemo(
  () => buildMarkdownModel(markdown),
  [markdown],
)
```

Add a split-pane isolation test before implementation. Render two
`VaultDocumentView` instances for the same note and Markdown with different
`viewId` values (`pane-1:tab-1` and `pane-2:tab-2`). Stub each matching
heading's `scrollIntoView`, activate “Plan” from the second sidebar, and assert
only the second view's heading scrolls. Assert there are no duplicated heading
IDs. This test must fail if navigation uses `document.getElementById`.

Derive canonical Markdown exactly once:

```typescript
const markdown = page.note.content ?? page.note.markdown ?? ''
```

Never reconstruct Markdown from `page.blocks` and never use truthy `||`
fallbacks. If `markdown.length === 0`, render the localized `knowledge.emptyNote` state
inside the mode-labelled document surface instead of initializing CodeMirror
or the Markdown renderer.

Render the selected view and always render `VaultNoteSidebar` beside it. Accept
`viewId` from `KnowledgePaneContent` as `${pane.id}:${activeTab.id}`. Sanitize
it into a stable `headingIdPrefix` and pass that prefix to `VaultMarkdown`.
`VaultDocumentView` owns a container ref. Its Reading `onHeading` adapter
queries only within `containerRef.current`, using the prefixed heading ID or
`[data-heading-slug]`; it never calls global `document.getElementById`.
CodeMirror modes call `scrollToOffset(sourceFrom)`.

Wrap only Source and Live Preview in `VaultEditorBoundary`, use Reading as its
fallback, and pass
`${page.note.id}:${mode}:${page.file.content_hash}` as `resetKey`. Page
validation has already guaranteed the complete 64-character hash, so no empty
fallback is permitted. Pass the localized `t('knowledge.footnotes')` string as
`footnoteLabel`. The
boundary catches render/lifecycle failures, never calls a workspace setter, and
resets only when note, selected mode, or canonical server snapshot changes.

- [ ] **Step 5: Refactor `KnowledgePaneContent`**

Replace Radix document/graph tabs with four pressed buttons:

```tsx
{modeOptions.map(({ mode, label, icon: Icon }) => (
  <Button
    key={mode}
    type="button"
    size="sm"
    variant={visibleMode === mode ? 'secondary' : 'ghost'}
    aria-pressed={visibleMode === mode}
    onClick={() => setTabViewMode(pane.id, activeTab.id, mode)}
  >
    <Icon aria-hidden="true" className="mr-1.5 h-4 w-4" />
    {label}
  </Button>
))}
```

On validated page success:

```typescript
useEffect(() => {
  if (!activeTab || !page.data) return
  reconcileTabReference(pane.id, activeTab.id, {
    title: page.data.note.title?.trim() || activeTab.title,
    relativePath: page.data.file.relative_path,
  })
}, [
  activeTab,
  page.data,
  pane.id,
  reconcileTabReference,
])
```

Mode derivation must preserve all four values:

```typescript
const visibleMode = activeTab.viewMode
```

Enable the graph query only for `visibleMode === 'graph'`.

When `page.isError`, render `knowledge.canonicalPathUnavailable` only for
`VaultPageContractError.code === 'canonical-path-unavailable'`; render
`knowledge.pageInvalid` for `page-invalid`; otherwise retain the existing
generic `knowledge.loadError`. Never initialize a document mode for any error.

- [ ] **Step 6: Add all locale keys**

Add these exact English keys:

```typescript
source: "Source",
livePreview: "Live Preview",
emptyNote: "This note is empty.",
pageInvalid: "The projected page data is invalid.",
canonicalPathUnavailable: "The canonical vault path is unavailable.",
pagePreview: "{{title}} preview",
previewUnavailable: "Preview unavailable.",
footnotes: "Footnotes",
sourceProvenance: "Source provenance",
lineEnding: "Line ending",
encoding: "Encoding",
contentHash: "Content hash",
readOnlyMode: "{{mode}} is read-only",
headingLevel: "Level {{level}} {{title}}",
```

Use these exact localized values for the same keys, in the order shown above:

```text
bn-IN: "উৎস" | "লাইভ প্রিভিউ" | "এই নোটটি খালি।" | "প্রক্ষেপিত পৃষ্ঠার ডেটা অবৈধ।" | "ক্যানোনিক্যাল ভল্ট পথটি উপলভ্য নয়।" | "{{title}} পূর্বরূপ" | "পূর্বরূপ উপলভ্য নয়।" | "পাদটীকা" | "উৎসের প্রামাণ্য তথ্য" | "লাইনের সমাপ্তি" | "এনকোডিং" | "কনটেন্ট হ্যাশ" | "{{mode}} শুধু-পঠন" | "স্তর {{level}} {{title}}"
ca-ES: "Codi font" | "Previsualització en directe" | "Aquesta nota és buida." | "Les dades projectades de la pàgina no són vàlides." | "La ruta canònica de la caixa no està disponible." | "Previsualització de {{title}}" | "Previsualització no disponible." | "Notes al peu" | "Procedència de la font" | "Final de línia" | "Codificació" | "Hash del contingut" | "{{mode}} és només de lectura" | "Nivell {{level}} {{title}}"
de-DE: "Quelltext" | "Live-Vorschau" | "Diese Notiz ist leer." | "Die projizierten Seitendaten sind ungültig." | "Der kanonische Vault-Pfad ist nicht verfügbar." | "Vorschau für {{title}}" | "Vorschau nicht verfügbar." | "Fußnoten" | "Quellherkunft" | "Zeilenende" | "Kodierung" | "Inhalts-Hash" | "{{mode}} ist schreibgeschützt" | "Ebene {{level}} {{title}}"
es-ES: "Fuente" | "Vista previa en vivo" | "Esta nota está vacía." | "Los datos proyectados de la página no son válidos." | "La ruta canónica de la bóveda no está disponible." | "Vista previa de {{title}}" | "Vista previa no disponible." | "Notas al pie" | "Procedencia de la fuente" | "Fin de línea" | "Codificación" | "Hash del contenido" | "{{mode}} es de solo lectura" | "Nivel {{level}} {{title}}"
fr-FR: "Source" | "Aperçu en direct" | "Cette note est vide." | "Les données projetées de la page sont invalides." | "Le chemin canonique du coffre n’est pas disponible." | "Aperçu de {{title}}" | "Aperçu indisponible." | "Notes de bas de page" | "Provenance de la source" | "Fin de ligne" | "Encodage" | "Empreinte du contenu" | "{{mode}} est en lecture seule" | "Niveau {{level}} {{title}}"
it-IT: "Sorgente" | "Anteprima live" | "Questa nota è vuota." | "I dati proiettati della pagina non sono validi." | "Il percorso canonico del vault non è disponibile." | "Anteprima di {{title}}" | "Anteprima non disponibile." | "Note a piè di pagina" | "Provenienza della fonte" | "Fine riga" | "Codifica" | "Hash del contenuto" | "{{mode}} è di sola lettura" | "Livello {{level}} {{title}}"
ja-JP: "ソース" | "ライブプレビュー" | "このノートは空です。" | "投影されたページデータが無効です。" | "正規の保管庫パスを利用できません。" | "{{title}} のプレビュー" | "プレビューを利用できません。" | "脚注" | "ソースの来歴" | "改行コード" | "エンコーディング" | "コンテンツハッシュ" | "{{mode}} は読み取り専用です" | "レベル {{level}} {{title}}"
pl-PL: "Źródło" | "Podgląd na żywo" | "Ta notatka jest pusta." | "Dane projekcji strony są nieprawidłowe." | "Kanoniczna ścieżka sejfu jest niedostępna." | "Podgląd: {{title}}" | "Podgląd niedostępny." | "Przypisy" | "Pochodzenie źródła" | "Zakończenie linii" | "Kodowanie" | "Skrót treści" | "{{mode}} jest tylko do odczytu" | "Poziom {{level}} {{title}}"
pt-BR: "Fonte" | "Prévia ao vivo" | "Esta nota está vazia." | "Os dados projetados da página são inválidos." | "O caminho canônico do cofre não está disponível." | "Prévia de {{title}}" | "Prévia indisponível." | "Notas de rodapé" | "Proveniência da fonte" | "Fim de linha" | "Codificação" | "Hash do conteúdo" | "{{mode}} é somente leitura" | "Nível {{level}} {{title}}"
ru-RU: "Исходник" | "Живой предпросмотр" | "Эта заметка пуста." | "Данные проекции страницы недействительны." | "Канонический путь хранилища недоступен." | "Предпросмотр: {{title}}" | "Предпросмотр недоступен." | "Сноски" | "Происхождение источника" | "Окончание строки" | "Кодировка" | "Хеш содержимого" | "{{mode}} доступен только для чтения" | "Уровень {{level}} {{title}}"
tr-TR: "Kaynak" | "Canlı önizleme" | "Bu not boş." | "Yansıtılan sayfa verileri geçersiz." | "Kanonik kasa yolu kullanılamıyor." | "{{title}} önizlemesi" | "Önizleme kullanılamıyor." | "Dipnotlar" | "Kaynak kökeni" | "Satır sonu" | "Kodlama" | "İçerik karması" | "{{mode}} salt okunurdur" | "Düzey {{level}} {{title}}"
zh-CN: "源码" | "实时预览" | "此笔记为空。" | "投影的页面数据无效。" | "规范的知识库路径不可用。" | "{{title}} 预览" | "预览不可用。" | "脚注" | "来源溯源" | "换行符" | "编码" | "内容哈希" | "{{mode}} 为只读模式" | "{{level}} 级 {{title}}"
zh-TW: "原始碼" | "即時預覽" | "此筆記為空。" | "投影的頁面資料無效。" | "規範的知識庫路徑無法使用。" | "{{title}} 預覽" | "預覽無法使用。" | "註腳" | "來源溯源" | "換行符號" | "編碼" | "內容雜湊" | "{{mode}} 為唯讀模式" | "{{level}} 級 {{title}}"
```

- [ ] **Step 7: Run mode, workspace, and locale tests GREEN**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/VaultEditorBoundary.test.tsx \
  src/components/vault/VaultDocumentView.test.tsx \
  src/components/vault/KnowledgePaneContent.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/lib/stores/knowledge-workspace-store.test.ts \
  src/lib/api/knowledge-workspace.test.ts \
  src/lib/locales/index.test.ts
npx tsc --noEmit
npm run lint
```

Expected: all tests, TypeScript, and ESLint pass.

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/src/components/vault/VaultEditorBoundary.tsx \
  frontend/src/components/vault/VaultEditorBoundary.test.tsx \
  frontend/src/components/vault/VaultDocumentView.tsx \
  frontend/src/components/vault/VaultDocumentView.test.tsx \
  frontend/src/components/vault/KnowledgePaneContent.tsx \
  frontend/src/components/vault/KnowledgePaneContent.test.tsx \
  frontend/src/components/vault/KnowledgeExplorer.test.tsx \
  frontend/src/lib/locales
git commit -m "feat(knowledge): integrate four read-only page modes"
```

---

### Task 9: Prove Security, Persistence, Regression, And Native Restart

**Files:**
- Create: `frontend/e2e/fixtures/knowledge-editor-modes.ts`
- Create: `frontend/e2e/knowledge-editor-modes.spec.ts`
- Modify: `frontend/playwright.config.ts` only if the existing project match excludes the new file
- Modify: `scripts/rebrand-allowlist.json` only if exact line movement makes existing evidence stale
- Modify: `docs/verification/2026-07-28-deeper-notebook-editor-modes.md`

**Interfaces:**
- Consumes: packaged/native runtime fixtures, existing workspace API, fixture vault
- Produces: source-fingerprint and restart evidence without private source content

- [ ] **Step 1: Add a browser integration test**

Create a fixture router with mutable workspace state:

```typescript
import type { Route } from '@playwright/test'

export interface KnowledgeFixtureState {
  workspace: Record<string, unknown>
}

const file = {
  id: 'vault_file:plan',
  note_id: 'note:plan',
  vault_id: 'vault:fixture',
  relative_path: 'pages/plan.md',
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  size_bytes: 34,
  modified_ns: 1,
  encoding: 'utf-8',
  newline: 'lf',
  parse_status: 'parsed',
  deleted_state: 'present',
}

const page = {
  file,
  note: {
    id: 'note:plan',
    title: 'Plan',
    content: '# Plan\n\n[[Evidence]]',
    source_format: 'obsidian',
    properties: { status: 'active' },
    tags: ['research'],
  },
  blocks: [{
    markdown: '# Plan',
    plain_text: 'Plan',
    heading_path: ['Plan'],
    block_kind: 'heading',
  }],
  tasks: [],
  outgoing_links: [{
    id: 'note_link:plan-evidence',
    source_note_id: 'note:plan',
    target_note_id: 'note:evidence',
    target_note_title: 'Evidence',
    target_relative_path: 'pages/evidence.md',
    target_text: 'Evidence',
    link_kind: 'wikilink',
    resolved: true,
    source_start: 8,
    source_end: 20,
  }],
  backlinks: [],
}

export function initialKnowledgeFixtureState(): KnowledgeFixtureState {
  return {
    workspace: {
      version: 1,
      active_pane_id: 'pane-1',
      next_id: 2,
      panes: {
        'pane-1': {
          id: 'pane-1',
          active_tab_id: null,
          tabs: [],
        },
      },
      layout: { type: 'pane', pane_id: 'pane-1' },
    },
  }
}

export async function fulfillKnowledgeRequest(
  route: Route,
  state: KnowledgeFixtureState,
): Promise<void> {
  const request = route.request()
  const path = new URL(request.url()).pathname
  const method = request.method()
  let payload: unknown

  if (path.endsWith('/deeper-notebook/workspace/knowledge')) {
    if (method === 'PUT') {
      state.workspace = request.postDataJSON() as Record<string, unknown>
    }
    payload = state.workspace
  } else if (path.endsWith('/deeper-notebook/vaults')) {
    payload = [{
      id: 'vault:fixture',
      name: 'Fixture vault',
      format_mode: 'obsidian',
      state: 'ready-read-only',
      parent_vault_id: null,
      watch_enabled: false,
    }]
  } else if (path.endsWith('/vaults/vault%3Afixture/files')
    || path.endsWith('/vaults/vault:fixture/files')) {
    payload = [file]
  } else if (path.includes('/pages/note%3Aplan')
    || path.includes('/pages/note:plan')) {
    payload = path.endsWith('/outgoing')
      ? page.outgoing_links
      : path.endsWith('/backlinks')
        ? page.backlinks
        : page
  } else if (path.endsWith('/vaults/vault%3Afixture/graph')
    || path.endsWith('/vaults/vault:fixture/graph')) {
    payload = {
      nodes: [{
        id: 'note:plan',
        title: 'Plan',
        source_format: 'obsidian',
        external_state: 'current',
      }],
      edges: [],
    }
  } else {
    await route.fallback()
    return
  }

  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}
```

The test mounts only those synthetic API responses and proves:

```typescript
test('persists read-only editor modes without a vault mutation', async ({ page }) => {
  const writes: string[] = []
  const state = initialKnowledgeFixtureState()
  await page.route('**/api/deeper-notebook/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (
      path.includes('/deeper-notebook/vaults')
      && !['GET', 'HEAD'].includes(request.method())
    ) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`)
    }
    await fulfillKnowledgeRequest(route, state)
  })

  await page.goto('/knowledge')
  await page.getByRole('treeitem', { name: 'pages/plan.md' }).click()
  await page.getByRole('button', { name: 'Live Preview' }).click()
  await expect(page.getByLabel('Plan live preview')).toHaveAttribute(
    'aria-readonly',
    'true',
  )
  await expect.poll(() => JSON.stringify(state.workspace))
    .toContain('"view_mode":"live-preview"')
  await page.reload()
  await expect(page.getByLabel('Plan live preview')).toBeVisible()
  expect(writes).toEqual([])
})
```

- [ ] **Step 2: Run the browser acceptance test GREEN**

Tasks 1-8 already drove every production behavior through unit/component RED
and GREEN cycles. Run this higher-level acceptance test once the integrated
feature exists:

```bash
cd frontend
npx playwright test e2e/knowledge-editor-modes.spec.ts --project=mocked-browser
```

Expected GREEN: one test passes and the captured write list is empty.

- [ ] **Step 3: Run focused security searches**

Run:

```bash
rg -n \
  "vaultApi\\.(update|delete|rename|move|write|save)|apiClient\\.(put|patch|delete).*vault|contenteditable=.true.|fallbackRelativePath" \
  frontend/src/components/vault \
  frontend/src/lib/api/vault.ts \
  frontend/src/lib/hooks/use-vault.ts
```

Expected: zero matches.

Run a separate POST inventory:

```bash
rg -n "apiClient\\.post.*vault" frontend/src/lib/api/vault.ts
```

Expected: exactly one reviewed match, the existing index-only `/scan` route.
Any other POST is a failure.

Run:

```bash
rg -n "/Users/Antman|Desktop/2nd Brains|BrainPulse Ventures" \
  frontend/src \
  api \
  deeper_notebook/vault \
  tests \
  --glob '!**/fixtures/**'
```

Expected: zero new product/runtime source-path leaks. Existing test-only approved
root constants must be reviewed individually and remain outside responses.

- [ ] **Step 4: Run full automated gates**

Run backend and frontend suites in parallel terminals:

```bash
PYTHONPATH=. uv run pytest -q
```

```bash
cd frontend
npm test
```

Expected: at least 3,758 backend tests and 516 frontend tests pass, with only
intentional skip counts and known dependency deprecation warnings.

Run:

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

Expected: all three pass and `/knowledge` is included in the production build.

Run the real SurrealDB suite inside one shell that owns startup, bounded health
polling, status propagation, and cleanup:

```bash
DN_SURREAL_PREEXISTING_ID="$(docker compose ps --no-trunc -q surrealdb)"
DN_SURREAL_STARTED_ID=""

dn_cleanup_surreal() {
  DN_SURREAL_EXIT_STATUS=$?
  trap - EXIT
  if [ -n "$DN_SURREAL_STARTED_ID" ]; then
    DN_SURREAL_CURRENT_ID="$(
      docker inspect --format '{{.Id}}' "$DN_SURREAL_STARTED_ID" \
        2>/dev/null || true
    )"
    if [ "$DN_SURREAL_CURRENT_ID" = "$DN_SURREAL_STARTED_ID" ]; then
      docker stop "$DN_SURREAL_STARTED_ID" >/dev/null || {
        if [ "$DN_SURREAL_EXIT_STATUS" -eq 0 ]; then
          DN_SURREAL_EXIT_STATUS=1
        fi
      }
    elif [ -n "$DN_SURREAL_CURRENT_ID" ]; then
      DN_SURREAL_EXIT_STATUS=1
    fi
  fi
  exit "$DN_SURREAL_EXIT_STATUS"
}

trap dn_cleanup_surreal EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -z "$DN_SURREAL_PREEXISTING_ID" ]; then
  make database || exit 1
  DN_SURREAL_STARTED_ID="$(docker compose ps --no-trunc -q surrealdb)"
  test -n "$DN_SURREAL_STARTED_ID" || exit 1
fi
for _attempt in {1..40}; do
  curl --fail --silent http://127.0.0.1:8000/health >/dev/null && break
  sleep 0.25
done
curl --fail --silent http://127.0.0.1:8000/health >/dev/null || exit 1
SURREAL_INTEGRATION=1 \
SURREAL_URL=ws://localhost:8000/rpc \
PYTHONPATH=. \
uv run pytest tests/integration -q
```

Expected: the complete real-SurrealDB integration suite passes at migration
head 35. The EXIT trap preserves the pytest status. The fixture owns and
removes only its unique test namespace. If
`DN_SURREAL_PREEXISTING_ID` is non-empty, the persistent service is reused and
left running. Otherwise cleanup revalidates and stops exactly the recorded
container ID, including on HUP, INT, or TERM. Never run `docker compose down`,
delete `./surreal_data`, or act on a container selected by name/glob alone.
Task 1 uses the same lifecycle.

Run:

```bash
PYTHONPATH=. uv run ruff check \
  api/routers/vault.py \
  api/schemas/vault.py \
  deeper_notebook/vault/repository.py \
  tests/test_vault_api.py \
  tests/test_vault_repository.py
python scripts/rebrand_audit.py --check
git diff --check main...HEAD
```

Expected: Ruff passes, the rebrand audit reports zero unexpected identities and
zero stale entries, and the diff has no whitespace errors.

- [ ] **Step 5: Run native restart proof with a synthetic vault**

Create a disposable copy of the synthetic fixture and its baseline:

```bash
proof_root=$(mktemp -d /tmp/deeper-notebook-editor-proof.XXXXXX)
cp -R tests/fixtures/vault "$proof_root/fixture-vault"
find -P "$proof_root/fixture-vault" -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > "$proof_root/source-before.sha256"
```

Start the persistent native launcher in a dedicated terminal:

```bash
PYTHONPATH=. uv run python -m desktop
```

In the native app, register only the displayed path ending in
`fixture-vault`, select Markdown format, scan it, open one projected Markdown
page, select Source, then select Live Preview. Quit through the native Quit
action, relaunch with the same command, and confirm the same tab and Live
Preview mode return.

After the second quit, run:

```bash
find -P "$proof_root/fixture-vault" -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > "$proof_root/source-after.sha256"
diff -u \
  "$proof_root/source-before.sha256" \
  "$proof_root/source-after.sha256"
```

Expected: `diff` exits zero. Verify:

```text
active tab: unchanged
active mode: live-preview
canonical relative path: unchanged
content hash: unchanged
source fixture hashes before/after: identical
vault mutation requests: zero
```

Do not mount or scan `/Users/Antman/Desktop/2nd Brains`.

- [ ] **Step 6: Build and smoke the macOS package**

Build with the repository's ad-hoc signing default and verify the exact
artifacts:

```bash
make build-mac
codesign --verify --deep --strict "dist/Deeper Notebook.app"
hdiutil verify "dist/Deeper-Notebook-mac-$(uname -m).dmg"
shasum -a 256 \
  "dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook" \
  "dist/Deeper-Notebook-mac-$(uname -m).dmg"
```

Launch the packaged executable in a persistent terminal:

```bash
"dist/Deeper Notebook.app/Contents/MacOS/Deeper Notebook"
```

Repeat the synthetic-vault Source → Live Preview → Quit → relaunch sequence,
then run the same before/after fixture `diff`. Verify the app closes only after
the workspace durability flush completes and the relaunched app restores Live
Preview.

Record the `.app` path, packaged executable SHA-256, `.dmg` path and SHA-256,
`hdiutil verify` result, launch result, and test timestamp. Do not describe the
executable hash as an `.app` bundle hash.

- [ ] **Step 7: Write the verification report**

Create `docs/verification/2026-07-28-deeper-notebook-editor-modes.md` with:

- exact commit SHA;
- exact commands and pass counts;
- macOS `.app` path, packaged executable hash, and `.dmg` path/hash;
- synthetic fixture label only, never source content;
- before/after fixture fingerprint result;
- zero-write request result;
- known warnings;
- explicit Windows packaged proof status.

If no Windows host is available, state that Windows package verification
remains a release gate. Do not claim cross-platform completion.

- [ ] **Step 8: Commit verification**

```bash
git add \
  frontend/e2e/fixtures/knowledge-editor-modes.ts \
  frontend/e2e/knowledge-editor-modes.spec.ts \
  frontend/playwright.config.ts \
  scripts/rebrand-allowlist.json \
  docs/verification/2026-07-28-deeper-notebook-editor-modes.md
git commit -m "test(knowledge): prove read-only editor durability"
```

Stage only files that actually changed; omit unchanged optional files from the
`git add` command.

---

## Completion Gate

The editor-mode slice is ready for review only when:

- Every page response contains its canonical file record.
- Canonical file responses preserve encoding and newline metadata through
  migration, projection, API validation, and frontend validation.
- Every resolved link contains canonical target title and relative path.
- Every link preserves its validated UTF-8 source span, and malformed canonical
  page/link paths fail closed.
- Synthetic path fallback is removed.
- Reading, Source, Live Preview, and Graph persist independently per tab.
- Source and Live Preview are locked by both CodeMirror read-only facets.
- Source retains non-mutating local search and code folding.
- Editor initialization failure displays Reading without changing persisted
  mode, and empty Markdown has an explicit state in every document mode.
- Canonical-path and general page-validation failures render distinct stable
  error states without opening an editor.
- No vault mutation route or client call exists.
- Reading covers GFM, footnotes, math, anchors, safe links, disabled tasks,
  properties, and tags.
- Live Preview supports every construct listed in the design and leaves unknown
  syntax visible.
- Outline and page previews are keyboard-accessible.
- Full backend/frontend, lint, TypeScript, build, Ruff, rebrand, and diff gates
  pass.
- Native macOS restart proof preserves workspace state and source fingerprints.
- Windows packaged proof remains explicitly open until performed on Windows.
