# Deeper Notebook Unified Knowledge Engine Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shadow unified knowledge engine that normalizes existing Overlay, Obsidian, Logseq, and neutral Markdown into one authority-aware domain, backfills and dual-projects canonical content, and proves equivalence without cutting over product UI or mutating external files.

**Architecture:** Add a focused `deeper_notebook/knowledge_engine/` package beside the current Overlay and vault implementations. Source adapters convert bounded canonical bytes into strict immutable snapshots; migration 38 adds sticky shadow tables; a transactional repository commits snapshots; restartable backfill and optional dual projection feed the engine while legacy reads remain authoritative. A read-only diagnostic API and equivalence verifier provide evidence before any future feature cutover.

**Tech Stack:** Python 3.12, Pydantic 2 strict models, FastAPI, SurrealDB 2.1/SurrealQL migrations, existing descriptor-bound vault security, existing Overlay storage, pytest/pytest-asyncio, Ruff.

## Global Constraints

- Work from a dedicated `codex/` feature worktree created at execution time.
- Baseline is local `main` at or after design commit `fd7ec65f`.
- Do not modify `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains` or `/Users/Antman/Desktop/2nd Brains`.
- Do not start a real mount, scan, backfill, or native proof against private user data during implementation.
- Canonical Overlay Markdown remains app-owned; mounted Obsidian, Logseq, and neutral Markdown remain external and read-only.
- SurrealDB is a rebuildable projection for canonical Markdown, not a replacement source of truth.
- No external-vault mutation route, serializer, capability, filesystem primitive, or UI control may be added.
- No JavaScript or Python template execution belongs in this plan.
- Do not implement Productivity Core UI, Tasks/Journals UI, Bases, Canvas, recovery UI, Sync, Publish, mobile, or plugin compatibility.
- Shadow projection and backfill default disabled and must fail without breaking legacy Overlay or vault operations.
- Use the existing product environment precedence contract: `DEEPER_NOTEBOOK_*` > `DN_*` > `OPEN_NOTEBOOK_*` > `ONP_*`.
- Public APIs never expose absolute canonical roots, note contents in receipts, authentication tokens, or secrets.
- No new runtime dependency is required; reuse Pydantic, SurrealDB, FastAPI, and existing parser/security code.
- All new contracts use `ConfigDict(extra="forbid", strict=True)`.
- All database mutations are transactional, idempotent, source-revision-bound, and receipt-producing.
- Migration 38 down behavior is sticky and non-destructive; rollback disables consumers rather than deleting projected knowledge.
- Run backend tests serially on this Mac; concurrent full backend/frontend runs can trigger the existing 30-second import timeout under memory pressure.

---

## File Map

### Create

- `deeper_notebook/knowledge_engine/__init__.py` — public engine exports only.
- `deeper_notebook/knowledge_engine/contracts.py` — strict domain models, source envelopes, snapshots, receipts, status and equivalence models.
- `deeper_notebook/knowledge_engine/identity.py` — deterministic engine IDs and validated canonical relative locators.
- `deeper_notebook/knowledge_engine/capabilities.py` — server-side authority-to-capability derivation.
- `deeper_notebook/knowledge_engine/adapters/__init__.py` — adapter selection by declared source kind.
- `deeper_notebook/knowledge_engine/adapters/base.py` — adapter protocol and shared ParsedDocument-to-snapshot normalization.
- `deeper_notebook/knowledge_engine/adapters/overlay.py` — Overlay identity, body, and provenance normalization.
- `deeper_notebook/knowledge_engine/adapters/obsidian.py` — Obsidian adapter using the existing safe parser.
- `deeper_notebook/knowledge_engine/adapters/logseq.py` — Logseq adapter using the existing safe parser.
- `deeper_notebook/knowledge_engine/adapters/markdown.py` — neutral Markdown adapter.
- `deeper_notebook/knowledge_engine/repository.py` — snapshot transaction, read model, receipts, checkpoints, and status.
- `deeper_notebook/knowledge_engine/backfill.py` — canonical source catalogs and restartable deterministic backfill.
- `deeper_notebook/knowledge_engine/shadow.py` — contained dual-projection coordinator.
- `deeper_notebook/knowledge_engine/service.py` — read-only engine service and status aggregation.
- `deeper_notebook/knowledge_engine/equivalence.py` — legacy/unified digest construction and deterministic comparison.
- `deeper_notebook/database/migrations/38.surrealql` — unified shadow schema and indexes.
- `deeper_notebook/database/migrations/38_down.surrealql` — sticky non-destructive rollback receipt.
- `api/schemas/knowledge_engine.py` — strict redacted diagnostic wire contracts.
- `api/routers/knowledge_engine.py` — authenticated read-only status, document, and equivalence routes.
- `scripts/verify_unified_knowledge_engine.py` — controlled synthetic backfill/restart/equivalence verifier.
- `tests/fixtures/knowledge_engine/overlay-daily.md` — canonical Overlay adapter fixture.
- `tests/fixtures/knowledge_engine/obsidian-page.md` — Obsidian adapter fixture.
- `tests/fixtures/knowledge_engine/logseq-journal.md` — Logseq adapter fixture.
- `tests/fixtures/knowledge_engine/markdown-page.md` — neutral Markdown fixture.
- `tests/test_knowledge_engine_contracts.py`
- `tests/test_knowledge_engine_adapters.py`
- `tests/test_knowledge_engine_migration.py`
- `tests/test_knowledge_engine_repository.py`
- `tests/test_knowledge_engine_backfill.py`
- `tests/test_knowledge_engine_shadow.py`
- `tests/test_knowledge_engine_service.py`
- `tests/test_knowledge_engine_lifespan.py`
- `tests/test_knowledge_engine_api.py`
- `tests/test_knowledge_engine_equivalence.py`
- `tests/test_verify_unified_knowledge_engine.py`
- `tests/integration/test_knowledge_engine_projection.py`
- `docs/verification/2026-07-30-deeper-notebook-unified-engine-foundation.md`

### Modify

- `deeper_notebook/environment.py` — register shadow/backfill setting aliases.
- `deeper_notebook/vault/service.py` — optional contained shadow callback after a successful legacy projection.
- `deeper_notebook/overlay/service.py` — optional contained shadow callback after exact canonical commit.
- `api/main.py` — construct/close the optional engine, inject it into existing services, and track optional backfill.
- `tests/test_migration_discovery.py` — assert migration 38 discovery.
- `tests/integration/test_vault_projection.py` — update latest-version expectations and prove legacy projection remains intact.
- `scripts/rebrand-allowlist.json` — only if the audit classifies accurate historical Obsidian/Logseq fixture text; use exact entries, never blanket paths.

## Interfaces Locked by This Plan

```python
from pathlib import PurePosixPath
from typing import Protocol

class KnowledgeAdapter(Protocol):
    source_kind: "SourceKind"

    def project(self, envelope: "SourceEnvelope") -> "KnowledgeSnapshot":
        raise NotImplementedError

class KnowledgeSnapshotRepository(Protocol):
    async def commit_snapshot(
        self,
        snapshot: "KnowledgeSnapshot",
        *,
        operation_id: str,
    ) -> "ProjectionReceipt":
        raise NotImplementedError

class KnowledgeShadowProjector(Protocol):
    async def project_external(
        self,
        *,
        mount: "VaultMount",
        item: "VaultWorkItem",
        resolved_source_kind: "SourceKind",
        legacy_vault_file_id: str,
        legacy_note_id: str,
        operation_id: str,
    ) -> None:
        raise NotImplementedError

    async def project_overlay(
        self,
        *,
        overlay_note: "OverlayNote",
        canonical_markdown: str,
        revision: int,
        operation_id: str,
    ) -> None:
        raise NotImplementedError
```

The concrete domain names are `KnowledgeSpace`, `KnowledgeDocument`,
`KnowledgeBlock`, `KnowledgeRelation`, `KnowledgeTask`, `KnowledgeAsset`,
`KnowledgeView`, `KnowledgeIdentityClaim`, `AdapterDiagnostic`,
`SourceRevision`, `SourceEnvelope`, `KnowledgeSnapshot`, `ProjectionReceipt`,
`BackfillCheckpoint`, `ProjectionDigest`, and `EquivalenceReport`.

---

### Task 1: Strict Domain, Identity, and Capability Contracts

**Files:**
- Create: `deeper_notebook/knowledge_engine/__init__.py`
- Create: `deeper_notebook/knowledge_engine/contracts.py`
- Create: `deeper_notebook/knowledge_engine/identity.py`
- Create: `deeper_notebook/knowledge_engine/capabilities.py`
- Test: `tests/test_knowledge_engine_contracts.py`

**Interfaces:**
- Consumes: `ParsedDocument`, `ParsedBlock`, `ParsedLink`, and `ParsedTask` only as later adapter inputs.
- Produces: every model named in **Interfaces Locked by This Plan**; `engine_record_id(kind, space_id, source_key) -> str`; `canonical_locator(value) -> str`; `capabilities_for(authority_kind, document_kind) -> frozenset[KnowledgeCapability]`.
- Produces: `validate_snapshot_spans(snapshot, *, source_size) -> None`.

- [ ] **Step 1: Write failing strict-contract and identity tests**

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import (
    KnowledgeDocument,
    KnowledgeSpace,
    SourceEnvelope,
)
from deeper_notebook.knowledge_engine.identity import engine_record_id

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def test_external_space_never_derives_mutation_capabilities():
    capabilities = capabilities_for("external_read_only", "note")
    assert capabilities == frozenset({"read", "copy_content", "bookmark", "cite"})
    assert "edit_body" not in capabilities
    assert "toggle_task" not in capabilities


def test_overlay_note_derives_app_owned_capabilities():
    capabilities = capabilities_for("app_owned", "note")
    assert {"read", "edit_body", "merge", "archive", "cite"} <= capabilities


def test_source_envelope_rejects_absolute_or_escaping_locator():
    for locator in ("/Users/Antman/private.md", "../private.md", "C:/private.md"):
        with pytest.raises(ValidationError):
            SourceEnvelope(
                space_id="knowledge_engine_space:external",
                space_display_name="External",
                source_ref="vault_mount:external",
                authority_kind="external_read_only",
                source_kind="obsidian",
                format_mode="obsidian",
                relative_locator=locator,
                canonical_bytes=b"# Safe\n",
                byte_size=7,
                declared_encoding="utf-8",
                declared_newline="lf",
                observed_content_hash="ae0158884831f39dc9f97511377720ffd4923e8551919e54e5f943ad79b2ce4f",
                observed_modified_ns=1,
                observed_at=NOW,
                prior_revision=None,
            )


def test_engine_ids_are_deterministic_and_authority_scoped():
    first = engine_record_id("document", "knowledge_space:a", "Pages/Test.md")
    second = engine_record_id("document", "knowledge_space:a", "Pages/Test.md")
    other = engine_record_id("document", "knowledge_space:b", "Pages/Test.md")
    assert first == second
    assert first != other
    assert first.startswith("knowledge_engine_document:")


def test_domain_models_forbid_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs"):
        KnowledgeSpace(
            id="knowledge_engine_space:test",
            display_name="Test",
            authority_kind="app_owned",
            source_kind="overlay",
            format_mode="markdown",
            source_ref="overlay_space:default",
            availability_state="available",
            projection_state="ready",
            adapter_version="knowledge-adapter-v1",
            parser_version="vault-parser-v1",
            policy_version=1,
            capabilities=["read"],
            created_at=NOW,
            updated_at=NOW,
            secret="must fail",
        )
```

- [ ] **Step 2: Run the new tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_contracts.py
```

Expected: collection fails with `ModuleNotFoundError: No module named
'deeper_notebook.knowledge_engine'`.

- [ ] **Step 3: Implement canonical locators and deterministic IDs**

`deeper_notebook/knowledge_engine/identity.py` must define:

```python
from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath

_KINDS = frozenset(
    {
        "space",
        "document",
        "block",
        "relation",
        "task",
        "asset",
        "view",
        "revision",
        "identity",
        "receipt",
    }
)


def canonical_locator(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or value.strip() != value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise ValueError("canonical locator must be relative")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("canonical locator must not escape its space")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != value:
        raise ValueError("canonical locator must be normalized")
    return canonical


def engine_record_id(kind: str, space_id: str, source_key: str) -> str:
    if kind not in _KINDS:
        raise ValueError("invalid knowledge engine record kind")
    if not space_id or len(space_id) > 128:
        raise ValueError("invalid knowledge space identity")
    key = canonical_locator(source_key) if kind != "space" else source_key
    digest = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"deeper-notebook:knowledge-engine:v1:{kind}:{space_id}:{key}",
    ).hex
    return f"knowledge_engine_{kind}:{digest}"
```

- [ ] **Step 4: Implement the capability vocabulary and fail-closed derivation**

`deeper_notebook/knowledge_engine/capabilities.py` must expose a literal type
and immutable sets:

```python
from __future__ import annotations

from typing import Literal

AuthorityKind = Literal["app_owned", "external_read_only"]
KnowledgeCapability = Literal[
    "read",
    "copy_content",
    "edit_body",
    "append_body",
    "edit_properties",
    "toggle_task",
    "rename",
    "move",
    "merge",
    "archive",
    "create_child",
    "create_link",
    "bookmark",
    "cite",
]

_EXTERNAL = frozenset[KnowledgeCapability](
    {"read", "copy_content", "bookmark", "cite"}
)
_OVERLAY_NOTE = frozenset[KnowledgeCapability](
    {
        "read",
        "copy_content",
        "edit_body",
        "append_body",
        "edit_properties",
        "toggle_task",
        "rename",
        "move",
        "merge",
        "archive",
        "create_child",
        "create_link",
        "bookmark",
        "cite",
    }
)


def capabilities_for(
    authority_kind: AuthorityKind,
    document_kind: str,
) -> frozenset[KnowledgeCapability]:
    if authority_kind == "external_read_only":
        return _EXTERNAL
    if authority_kind == "app_owned" and document_kind in {
        "note",
        "daily",
        "unique",
        "template",
    }:
        return _OVERLAY_NOTE
    if authority_kind == "app_owned":
        return frozenset({"read", "copy_content", "bookmark", "cite"})
    return frozenset()
```

- [ ] **Step 5: Implement strict Pydantic domain contracts**

Use one `_Strict` base and validators for lowercase SHA-256, source spans,
canonical locators, capability uniqueness, source-revision consistency, and
snapshot ownership. At minimum, the models must enforce this structure:

```python
SourceKind = Literal["overlay", "obsidian", "logseq", "markdown"]


class SourceEnvelope(_Strict):
    space_id: str = Field(min_length=1, max_length=128)
    space_display_name: str = Field(min_length=1, max_length=256)
    source_ref: str = Field(min_length=1, max_length=128)
    authority_kind: AuthorityKind
    source_kind: SourceKind
    format_mode: VaultFormat
    relative_locator: str = Field(min_length=1, max_length=4096)
    canonical_bytes: bytes = Field(max_length=100 * 1024 * 1024)
    byte_size: int = Field(ge=0, le=100 * 1024 * 1024)
    declared_encoding: str | None = Field(default=None, max_length=64)
    declared_newline: Literal["lf", "crlf", "mixed", "none"] | None = None
    observed_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_modified_ns: int = Field(ge=0)
    observed_at: datetime
    prior_revision: SourceRevision | None = None


class KnowledgeSnapshot(_Strict):
    space: KnowledgeSpace
    document: KnowledgeDocument
    blocks: list[KnowledgeBlock] = Field(default_factory=list, max_length=50_000)
    relations: list[KnowledgeRelation] = Field(
        default_factory=list,
        max_length=100_000,
    )
    tasks: list[KnowledgeTask] = Field(default_factory=list, max_length=50_000)
    assets: list[KnowledgeAsset] = Field(default_factory=list, max_length=50_000)
    identity_claims: list[KnowledgeIdentityClaim] = Field(
        default_factory=list,
        max_length=100_000,
    )
    diagnostics: list[AdapterDiagnostic] = Field(
        default_factory=list,
        max_length=10_000,
    )
    revision: SourceRevision
```

`SourceEnvelope` validation must require `byte_size == len(canonical_bytes)`,
the observed hash to equal the SHA-256 of those exact bytes, and any prior
revision to belong to the same space/document identity implied by the
envelope. Adapters compare declared encoding/newline evidence with the parser
result when those values are present.

The domain contracts must include every field approved in the design:
`KnowledgeSpace` carries availability and projection states, adapter/parser
versions, policy version, and created/updated timestamps; `KnowledgeDocument`
carries created/observed/updated timestamps; `KnowledgeTask` carries
properties; `KnowledgeAsset` carries provenance; `KnowledgeView` carries
space ownership, stable engine target IDs, validated view state, capabilities,
and timestamps; and `ProjectionReceipt` carries its source revision ID.
`AdapterDiagnostic` contains only a stable code, severity, optional source
span, and bounded relative context identifier—never note text.

The `KnowledgeSnapshot` after-validator must require every child
`space_id/document_id/source_revision_id` to match the snapshot document and
revision. Each `KnowledgeIdentityClaim` contains `legacy_kind`, `legacy_id`,
`engine_kind`, `engine_id`, `source_revision_id`, and `claim_hash`. Adapters
emit source-native claims; the canonical catalog and shadow coordinator append
the current `vault_mount`, `vault_file`, `note`, `overlay_space`, and
`overlay_note` claims available at their trusted boundary.

Adapter construction must call
`validate_snapshot_spans(snapshot, source_size=len(envelope.canonical_bytes))`
to reject reversed or out-of-bounds byte spans. Canonical bytes are never
stored in the snapshot.

- [ ] **Step 6: Run focused tests and Ruff**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_contracts.py
uv run ruff check deeper_notebook/knowledge_engine tests/test_knowledge_engine_contracts.py
```

Expected: all contract tests pass; Ruff reports `All checks passed!`.

- [ ] **Step 7: Commit the domain boundary**

```bash
git add deeper_notebook/knowledge_engine/__init__.py \
  deeper_notebook/knowledge_engine/contracts.py \
  deeper_notebook/knowledge_engine/identity.py \
  deeper_notebook/knowledge_engine/capabilities.py \
  tests/test_knowledge_engine_contracts.py
git commit -m "feat(knowledge): define unified engine contracts"
```

---

### Task 2: Source Adapters and Golden Fixtures

**Files:**
- Create: `deeper_notebook/knowledge_engine/adapters/__init__.py`
- Create: `deeper_notebook/knowledge_engine/adapters/base.py`
- Create: `deeper_notebook/knowledge_engine/adapters/overlay.py`
- Create: `deeper_notebook/knowledge_engine/adapters/obsidian.py`
- Create: `deeper_notebook/knowledge_engine/adapters/logseq.py`
- Create: `deeper_notebook/knowledge_engine/adapters/markdown.py`
- Create: `tests/fixtures/knowledge_engine/overlay-daily.md`
- Create: `tests/fixtures/knowledge_engine/obsidian-page.md`
- Create: `tests/fixtures/knowledge_engine/logseq-journal.md`
- Create: `tests/fixtures/knowledge_engine/markdown-page.md`
- Test: `tests/test_knowledge_engine_adapters.py`

**Interfaces:**
- Consumes: `SourceEnvelope`, domain models, `engine_record_id`,
  `capabilities_for`, and existing `parse_document(relative_path, raw,
  format_mode=...)`.
- Produces: `KnowledgeAdapter`, `adapter_for(source_kind)`, and adapters whose
  `project(envelope) -> KnowledgeSnapshot` is deterministic and side-effect
  free.

- [ ] **Step 1: Add golden fixtures with exact supported syntax**

Use these fixture contents:

`overlay-daily.md`

```markdown
---
title: 2026-07-30
deeper_notebook:
  id: overlay_note:daily-2026-07-30
  kind: daily
  date_key: 2026-07-30
---
# 2026-07-30

- [ ] Review [[Research Plan]]
```

`obsidian-page.md`

```markdown
---
title: Research Plan
status: active
tags:
  - research
---
# Research Plan

See [[Evidence#Sources]] and ![[diagram.png]].

- [ ] Validate evidence ^task-one
```

`logseq-journal.md`

```markdown
title:: July 30th, 2026
tags:: journal, research

- TODO Review [[Research Plan]]
  scheduled:: <2026-07-30 Thu>
  id:: 67a2471e-4a93-4f63-b3b1-a10227f1777e
- DONE Capture result
```

`markdown-page.md`

```markdown
# Portable Page

An ordinary [reference](Other.md) with no source-specific control metadata.
```

- [ ] **Step 2: Write failing adapter tests**

```python
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import SourceEnvelope

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge_engine"
NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def envelope(name: str, source_kind: str, authority: str) -> SourceEnvelope:
    raw = (FIXTURES / name).read_bytes()
    return SourceEnvelope(
        space_id=f"knowledge_engine_space:{source_kind}",
        space_display_name=f"{source_kind.title()} Test Space",
        source_ref=f"fixture:{source_kind}",
        authority_kind=authority,
        source_kind=source_kind,
        format_mode="markdown" if source_kind == "overlay" else source_kind,
        relative_locator=f"Pages/{name}",
        canonical_bytes=raw,
        byte_size=len(raw),
        declared_encoding=None,
        declared_newline=None,
        observed_content_hash=sha256(raw).hexdigest(),
        observed_modified_ns=1,
        observed_at=NOW,
        prior_revision=None,
    )


@pytest.mark.parametrize(
    ("fixture", "source_kind", "authority"),
    [
        ("overlay-daily.md", "overlay", "app_owned"),
        ("obsidian-page.md", "obsidian", "external_read_only"),
        ("logseq-journal.md", "logseq", "external_read_only"),
        ("markdown-page.md", "markdown", "external_read_only"),
    ],
)
def test_adapters_are_deterministic_and_authority_preserving(
    fixture,
    source_kind,
    authority,
):
    source = envelope(fixture, source_kind, authority)
    first = adapter_for(source_kind).project(source)
    second = adapter_for(source_kind).project(source)
    assert first == second
    assert first.document.space_id == source.space_id
    assert first.document.authority_kind == authority
    assert first.revision.content_hash == source.observed_content_hash


def test_external_adapters_never_emit_mutation_capabilities():
    snapshot = adapter_for("obsidian").project(
        envelope("obsidian-page.md", "obsidian", "external_read_only")
    )
    assert "edit_body" not in snapshot.document.capabilities
    assert "toggle_task" not in snapshot.tasks[0].capabilities


def test_obsidian_embed_projects_an_asset_reference():
    snapshot = adapter_for("obsidian").project(
        envelope("obsidian-page.md", "obsidian", "external_read_only")
    )
    assert [asset.relative_locator for asset in snapshot.assets] == ["diagram.png"]
    assert snapshot.assets[0].availability == "referenced"


def test_overlay_adapter_preserves_reserved_identity_and_body():
    snapshot = adapter_for("overlay").project(
        envelope("overlay-daily.md", "overlay", "app_owned")
    )
    assert snapshot.document.source_native_id == "overlay_note:daily-2026-07-30"
    assert snapshot.document.journal_date.isoformat() == "2026-07-30"
    assert snapshot.document.normalized_body.startswith("# 2026-07-30")
    assert "deeper_notebook:" not in snapshot.document.normalized_body


def test_logseq_adapter_normalizes_tasks_without_erasing_raw_state():
    snapshot = adapter_for("logseq").project(
        envelope("logseq-journal.md", "logseq", "external_read_only")
    )
    assert [task.normalized_status for task in snapshot.tasks] == ["open", "done"]
    assert snapshot.tasks[0].raw_status == "TODO"
```

- [ ] **Step 3: Run the adapter tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_adapters.py
```

Expected: collection fails because the adapter package does not exist.

- [ ] **Step 4: Implement the shared normalization function**

`adapters/base.py` must define a protocol and
`snapshot_from_parsed(envelope, parsed, *, source_native_id, document_kind,
journal_date)` that:

- derives every engine ID through `engine_record_id`;
- converts parser byte spans without changing offsets;
- maps `todo -> open`, `doing -> in_progress`, `done -> done`,
  `canceled -> cancelled`, and everything else to `unknown`;
- combines parsed links and embeds into `KnowledgeRelation`;
- emits referenced `KnowledgeAsset` records for attachment-like embeds while
  retaining unresolved targets;
- emits tag relations without inventing target documents;
- copies properties as JSON-safe values;
- keeps raw task state;
- emits source-native document/block identity claims and no legacy database
  claim it cannot prove from the envelope;
- calculates capabilities from the envelope authority;
- stores body-only Markdown for Overlay and full parsed Markdown for external
  documents;
- validates and returns one `KnowledgeSnapshot`.

The public protocol is:

```python
class KnowledgeAdapter(Protocol):
    source_kind: SourceKind

    def project(self, envelope: SourceEnvelope) -> KnowledgeSnapshot:
        raise NotImplementedError
```

- [ ] **Step 5: Implement the four adapters and explicit selector**

Each adapter must reject an envelope whose declared `source_kind` or authority
does not match its contract. Use existing safe parsers:

```python
_ADAPTERS: dict[SourceKind, KnowledgeAdapter] = {
    "overlay": OverlayKnowledgeAdapter(),
    "obsidian": ObsidianKnowledgeAdapter(),
    "logseq": LogseqKnowledgeAdapter(),
    "markdown": MarkdownKnowledgeAdapter(),
}


def adapter_for(source_kind: SourceKind) -> KnowledgeAdapter:
    try:
        return _ADAPTERS[source_kind]
    except KeyError:
        raise ValueError("unsupported knowledge source kind") from None
```

The Overlay adapter must call `decode_source` to obtain `body_markdown`, validate
the reserved `deeper_notebook` mapping, and then use
`parse_document(..., format_mode="markdown")` for structural projection.

External adapters call `parse_document` with their exact format mode and never
perform filesystem access.

- [ ] **Step 6: Add adversarial adapter tests**

Add tests proving:

- content hash mismatch rejects the envelope before parsing;
- an external source declared `app_owned` fails;
- an Overlay source without valid reserved identity fails;
- absolute target paths remain unresolved text rather than local locators;
- malformed frontmatter produces only the stable parser code;
- adapters cannot access a monkeypatched network, environment, or filesystem
  function because they receive bytes only.

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_contracts.py \
  tests/test_knowledge_engine_adapters.py
uv run ruff check deeper_notebook/knowledge_engine tests/test_knowledge_engine_*.py
```

Expected: all focused tests pass; Ruff reports no errors.

- [ ] **Step 7: Commit adapters**

```bash
git add deeper_notebook/knowledge_engine/adapters \
  tests/fixtures/knowledge_engine \
  tests/test_knowledge_engine_adapters.py
git commit -m "feat(knowledge): normalize canonical source adapters"
```

---

### Task 3: Sticky Shadow Schema Migration 38

**Files:**
- Create: `deeper_notebook/database/migrations/38.surrealql`
- Create: `deeper_notebook/database/migrations/38_down.surrealql`
- Create: `tests/test_knowledge_engine_migration.py`
- Modify: `tests/test_migration_discovery.py`
- Modify: `tests/integration/test_vault_projection.py`

**Interfaces:**
- Consumes: domain field names from Task 1.
- Produces: schemafull tables prefixed `knowledge_engine_`; migration version 38;
  non-destructive down receipt `{ schema_preserved: true }`.

- [ ] **Step 1: Write failing static migration tests**

```python
from pathlib import Path

from deeper_notebook.database.async_migrate import AsyncMigrationManager

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/38.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/38_down.surrealql"

TABLES = (
    "knowledge_engine_space",
    "knowledge_engine_document",
    "knowledge_engine_block",
    "knowledge_engine_relation",
    "knowledge_engine_task",
    "knowledge_engine_asset",
    "knowledge_engine_view",
    "knowledge_engine_source_revision",
    "knowledge_engine_identity_map",
    "knowledge_engine_projection_receipt",
    "knowledge_engine_backfill_checkpoint",
)


def test_migration_38_is_schemafull_and_idempotent():
    sql = UP.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    definitions = [
        line.strip()
        for line in sql.splitlines()
        if line.strip().startswith("DEFINE ")
    ]
    assert definitions
    assert all("IF NOT EXISTS" in line for line in definitions)


def test_migration_38_down_is_sticky_and_non_destructive():
    sql = DOWN.read_text(encoding="utf-8")
    assert "schema_preserved: true" in sql
    assert "REMOVE TABLE" not in sql
    assert "DELETE " not in sql


def test_migration_discovery_includes_unified_engine_38():
    ups, downs = AsyncMigrationManager._discover_migrations()
    assert ups[37].version == 38
    assert "knowledge_engine_document" in ups[37].sql
    assert downs[37] is not None
    assert "schema_preserved: true" in downs[37].sql
```

- [ ] **Step 2: Run migration tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_migration.py \
  tests/test_migration_discovery.py
```

Expected: failure because `38.surrealql` and `38_down.surrealql` are absent.

- [ ] **Step 3: Implement all schemafull tables and indexes**

Use `knowledge_engine_*` physical table names so the current `knowledge_task`,
`note`, `note_block`, and `note_link` tables remain untouched.

Every engine table has `schema_version int DEFAULT 1`, created/updated
timestamps as appropriate, and explicit field types. The table field contract
is:

- `knowledge_engine_space`: `display_name`, `authority_kind`, `source_kind`,
  `source_ref`, `format_mode`, `availability_state`, `projection_state`,
  `adapter_version`, `parser_version`, `policy_version`, `capabilities`,
  `created_at`, `updated_at`.
- `knowledge_engine_document`: `space_id`, `source_native_id`,
  `authority_kind`, `relative_locator`, `document_kind`, `title`, `normalized_body`,
  `properties`, `tags`, `content_hash`, `source_revision_id`, `provenance`,
  `availability`, `parse_state`, `journal_date`, `capabilities`, `created_at`,
  `observed_at`, `updated_at`.
- `knowledge_engine_block`: `space_id`, `document_id`, `parent_block_id`,
  `position`, `source_key`, `block_kind`, `markdown`, `plain_text`,
  `properties`, `raw_task_state`, `normalized_task_state`, `heading_path`,
  `source_start`, `source_end`, `source_revision_id`, `capabilities`.
- `knowledge_engine_relation`: `space_id`, `source_document_id`,
  `source_block_id`, `target_document_id`, `target_block_id`, `target_text`,
  `target_heading`, `target_block`, `alias`, `relation_kind`, `resolved`,
  `source_start`, `source_end`, `source_revision_id`.
- `knowledge_engine_task`: `space_id`, `document_id`, `block_id`,
  `raw_status`, `normalized_status`, `scheduled`, `due`, `completed`,
  `priority`, `recurrence`, `tags`, `properties`, `source_start`, `source_end`,
  `source_revision_id`, `capabilities`.
- `knowledge_engine_asset`: `space_id`, `source_document_id`,
  `relative_locator`, `media_kind`, `content_hash`, `byte_size`,
  `availability`, `metadata`, `provenance`, `source_revision_id`.
- `knowledge_engine_view`: `space_id`, `view_kind`, `name`, `revision`,
  `target_ids`, `definition`, `view_state`, `capabilities`, `created_at`,
  `updated_at`.
- `knowledge_engine_source_revision`: `space_id`, `document_id`,
  `content_hash`, `byte_size`, `encoding`, `newline`,
  `observed_modified_ns`, `adapter_version`, `parser_version`, `parse_status`,
  `diagnostics`, `observed_at`, `created_at`.
- `knowledge_engine_identity_map`: `legacy_kind`, `legacy_id`,
  `engine_kind`, `engine_id`, `source_revision_id`, `claim_hash`,
  `created_at`.
- `knowledge_engine_projection_receipt`: `operation_id`, `space_id`,
  `document_id`, `source_revision_id`, `relative_locator`, `input_hash`,
  `output_hash`, `adapter_version`, `schema_version`, `status`, `error_code`,
  `started_at`, `completed_at`.
- `knowledge_engine_backfill_checkpoint`: `space_id`,
  `last_relative_locator`, `last_source_hash`, `status`, `projected`,
  `unchanged`, `failed`, `updated_at`.

Required indexes:

```surql
DEFINE INDEX IF NOT EXISTS idx_ke_space_source
  ON TABLE knowledge_engine_space COLUMNS source_kind, source_ref UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_document_locator
  ON TABLE knowledge_engine_document COLUMNS space_id, relative_locator UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_document_native
  ON TABLE knowledge_engine_document COLUMNS space_id, source_native_id;
DEFINE INDEX IF NOT EXISTS idx_ke_block_source
  ON TABLE knowledge_engine_block COLUMNS document_id, source_key UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_relation_source_span
  ON TABLE knowledge_engine_relation
  COLUMNS source_document_id, source_start, source_end, relation_kind UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_task_block
  ON TABLE knowledge_engine_task COLUMNS document_id, block_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_revision_hash
  ON TABLE knowledge_engine_source_revision
  COLUMNS document_id, content_hash UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_identity_legacy
  ON TABLE knowledge_engine_identity_map
  COLUMNS legacy_kind, legacy_id, source_revision_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_receipt_operation
  ON TABLE knowledge_engine_projection_receipt COLUMNS operation_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ke_checkpoint_space
  ON TABLE knowledge_engine_backfill_checkpoint COLUMNS space_id UNIQUE;
```

Capabilities are stored as `array<string>`. Absolute roots and canonical bytes
have no field in any engine table.

- [ ] **Step 4: Implement sticky down migration**

`38_down.surrealql` contains no destructive statement:

```surql
RETURN {
  schema_preserved: true,
  reason: "unified knowledge projections are sticky; disable consumers instead"
};
```

- [ ] **Step 5: Update discovery and integration version expectations**

Add the migration-38 assertion to `tests/test_migration_discovery.py`. In
`tests/integration/test_vault_projection.py`, helpers that intentionally restore
older recorded states must first execute `38_down.surrealql` and delete the
recorded migration-38 version marker without expecting table removal. Latest
fresh-schema assertions become version 38.

- [ ] **Step 6: Run static and native migration lifecycle tests**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_migration.py \
  tests/test_migration_discovery.py tests/test_vault_migration.py \
  tests/test_overlay_migration.py
uv run pytest -q tests/integration/test_vault_projection.py \
  -m integration_surreal
```

Expected: static migration tests pass; the native integration test upgrades a
fresh schema to 38 and existing vault/overlay projection tests remain green.

- [ ] **Step 7: Commit migration 38**

```bash
git add deeper_notebook/database/migrations/38.surrealql \
  deeper_notebook/database/migrations/38_down.surrealql \
  tests/test_knowledge_engine_migration.py \
  tests/test_migration_discovery.py \
  tests/integration/test_vault_projection.py
git commit -m "feat(knowledge): add sticky unified shadow schema"
```

---

### Task 4: Transactional Snapshot Repository

**Files:**
- Create: `deeper_notebook/knowledge_engine/repository.py`
- Create: `tests/test_knowledge_engine_repository.py`
- Modify: `tests/integration/test_knowledge_engine_projection.py`

**Interfaces:**
- Consumes: `KnowledgeSnapshot`, `ProjectionReceipt`, `BackfillCheckpoint`.
- Produces: `KnowledgeRepository.commit_snapshot`, `get_document`,
  `list_documents`, `projection_status`, `record_projection_failure`,
  `get_checkpoint`, and `save_checkpoint`.

- [ ] **Step 1: Write failing repository transaction tests with a fake connection**

```python
import pytest

from deeper_notebook.knowledge_engine.repository import (
    KnowledgeRepository,
    KnowledgeRepositoryError,
)


@pytest.mark.asyncio
async def test_commit_snapshot_uses_one_transaction(snapshot, fake_connection):
    repository = KnowledgeRepository(
        connection_factory=fake_connection.factory
    )
    receipt = await repository.commit_snapshot(
        snapshot,
        operation_id="shadow-project-one",
    )
    statement = fake_connection.queries[-1].statement
    assert "BEGIN TRANSACTION;" in statement
    assert "COMMIT TRANSACTION;" in statement
    assert "knowledge_engine_document" in statement
    assert "knowledge_engine_projection_receipt" in statement
    assert receipt.status == "projected"


@pytest.mark.asyncio
async def test_commit_snapshot_rejects_operation_replay_with_other_hash(
    snapshot,
    fake_connection,
):
    repository = KnowledgeRepository(
        connection_factory=fake_connection.factory
    )
    await repository.commit_snapshot(snapshot, operation_id="same-operation")
    changed = snapshot.model_copy(
        update={
            "revision": snapshot.revision.model_copy(
                update={"content_hash": "b" * 64}
            )
        }
    )
    with pytest.raises(KnowledgeRepositoryError, match="operation_conflict"):
        await repository.commit_snapshot(changed, operation_id="same-operation")
```

- [ ] **Step 2: Run repository tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_repository.py
```

Expected: collection fails because `knowledge_engine.repository` is absent.

- [ ] **Step 3: Implement sanitized connection and record-ID boundaries**

Follow the established `OverlayRepository` pattern:

```python
class KnowledgeRepositoryError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class KnowledgeRepository:
    def __init__(self, *, connection_factory=None) -> None:
        self._connection_factory = connection_factory or db_connection

    async def _query(self, connection, statement, variables=None):
        try:
            result = await connection.query(statement, variables)
        except KnowledgeRepositoryError:
            raise
        except Exception:
            raise KnowledgeRepositoryError(
                "knowledge_engine_repository_unavailable"
            ) from None
        if isinstance(result, str):
            raise KnowledgeRepositoryError(
                "knowledge_engine_repository_unavailable"
            )
        parsed = parse_record_ids(result)
        return parsed if isinstance(parsed, list) else [parsed]
```

Validate every supplied ID prefix before `ensure_record_id`. Never interpolate
user-controlled table, field, sort, or locator text into SurrealQL.

- [ ] **Step 4: Implement one atomic snapshot transaction**

The transaction must:

1. reject an existing operation receipt whose input hash differs;
2. replay a successful identical operation without rewriting;
3. upsert the space and source revision;
4. replace the current document projection;
5. delete only prior engine blocks, relations, tasks, and assets owned by that
   exact document;
6. create the new child records;
7. append identity mappings without overwriting a conflicting legacy mapping;
8. create the success receipt;
9. return the resulting document revision and status.

All variables come from `snapshot.model_dump(mode="python")` transformed into
validated record IDs. The operation transaction contains no canonical bytes or
absolute root.

- [ ] **Step 5: Implement read and checkpoint methods**

Required signatures:

```python
async def get_document(self, document_id: str) -> KnowledgeDocument
async def list_documents(
    self,
    *,
    space_id: str | None,
    limit: int,
    offset: int,
) -> list[KnowledgeDocument]
async def projection_status(self) -> EngineProjectionStatus
async def record_projection_failure(
    self,
    *,
    operation_id: str,
    space_id: str,
    relative_locator: str,
    input_hash: str,
    error_code: str,
) -> ProjectionReceipt
async def get_checkpoint(self, space_id: str) -> BackfillCheckpoint | None
async def save_checkpoint(
    self,
    checkpoint: BackfillCheckpoint,
) -> BackfillCheckpoint
```

Pagination is bounded to `1 <= limit <= 500` and
`0 <= offset <= 1_000_000`.

- [ ] **Step 6: Add native transaction and rollback integration tests**

`tests/integration/test_knowledge_engine_projection.py` must run against the
isolated SurrealDB integration namespace and prove:

- snapshot commit creates all records;
- exact replay is unchanged;
- conflicting replay is rejected;
- a forced child-insert error exposes no partial new snapshot;
- the previous valid snapshot remains after failure;
- no absolute path or canonical bytes appear in the receipt;
- migration 38 down/up preserves records.

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_repository.py
uv run pytest -q tests/integration/test_knowledge_engine_projection.py \
  -m integration_surreal
```

Expected: unit and native repository tests pass.

- [ ] **Step 7: Commit repository**

```bash
git add deeper_notebook/knowledge_engine/repository.py \
  tests/test_knowledge_engine_repository.py \
  tests/integration/test_knowledge_engine_projection.py
git commit -m "feat(knowledge): persist unified snapshots atomically"
```

---

### Task 5: Canonical Catalog and Restartable Backfill

**Files:**
- Create: `deeper_notebook/knowledge_engine/backfill.py`
- Create: `tests/test_knowledge_engine_backfill.py`

**Interfaces:**
- Consumes: `OverlayRepository`, `OverlayStorage`, `VaultRepository`,
  `approve_vault_root`, `secure_read`, adapters, and `KnowledgeRepository`.
- Produces: `CanonicalSourceCatalog.iter_sources()`,
  `KnowledgeBackfillService.run() -> BackfillResult`.

- [ ] **Step 1: Write failing catalog and checkpoint tests**

```python
import pytest

from deeper_notebook.knowledge_engine.backfill import KnowledgeBackfillService


@pytest.mark.asyncio
async def test_backfill_orders_sources_and_resumes_after_checkpoint(backfill):
    backfill.catalog.sources = [
        backfill.source("space:b", "Pages/Z.md"),
        backfill.source("space:a", "Pages/B.md"),
        backfill.source("space:a", "Pages/A.md"),
    ]
    backfill.repository.checkpoint = backfill.checkpoint(
        "space:a",
        "Pages/A.md",
    )
    result = await backfill.service.run()
    assert backfill.projected_locators == [
        ("space:a", "Pages/B.md"),
        ("space:b", "Pages/Z.md"),
    ]
    assert result.projected == 2


@pytest.mark.asyncio
async def test_backfill_never_writes_canonical_sources(backfill):
    before = backfill.source_fingerprints()
    await backfill.service.run()
    assert backfill.source_fingerprints() == before
    assert backfill.external_write_calls == []
    assert backfill.overlay_write_calls == []


@pytest.mark.asyncio
async def test_failed_item_keeps_prior_snapshot_and_advances_only_failure_receipt(
    backfill,
):
    backfill.catalog.sources = [backfill.invalid_source("space:a", "Bad.md")]
    result = await backfill.service.run()
    assert result.failed == 1
    assert backfill.repository.committed_snapshots == []
    assert backfill.repository.failure_codes == ["knowledge_adapter_invalid"]
```

- [ ] **Step 2: Run backfill tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_backfill.py
```

Expected: collection fails because `knowledge_engine.backfill` is absent.

- [ ] **Step 3: Implement a canonical read-only catalog**

Define:

```python
@dataclass(frozen=True, slots=True)
class CanonicalSource:
    space_id: str
    space_display_name: str
    source_ref: str
    authority_kind: AuthorityKind
    source_kind: SourceKind
    format_mode: VaultFormat
    relative_locator: str
    canonical_bytes: bytes
    byte_size: int
    declared_encoding: str | None
    declared_newline: Literal["lf", "crlf", "mixed", "none"] | None
    observed_content_hash: str
    observed_modified_ns: int
    observed_at: datetime
    prior_revision: SourceRevision | None
    legacy_identities: tuple[KnowledgeIdentityClaim, ...]


class CanonicalSourceCatalog:
    async def iter_sources(self) -> AsyncIterator[CanonicalSource]:
        raise NotImplementedError
```

The production catalog:

- lists Overlay notes and reads them through `OverlayStorage.read`;
- lists present parsed/invalid vault files in stable `vault_id,
  relative_path` order;
- derives external `source_kind` from the persisted resolved `VaultFile.format`
  and preserves the mount's declared `format_mode` (including `mixed`);
- supplies only legacy IDs proven by current records (`vault_mount`,
  `vault_file`, `note`, `overlay_space`, and `overlay_note`);
- opens each external root with `approve_vault_root`;
- reads each file with `secure_read` and the configured Markdown limit;
- checks the resulting hash against the cataloged observation;
- yields no root path;
- closes every approved root descriptor;
- skips missing records without deleting their engine snapshot.

- [ ] **Step 4: Implement deterministic restartable backfill**

`KnowledgeBackfillService.run()` must:

- acquire one process-local lock;
- sort by `(space_id, relative_locator)`;
- resume strictly after the persisted checkpoint;
- build `SourceEnvelope`;
- select and run the adapter;
- append catalog-proven legacy identity claims and revalidate the snapshot;
- call `commit_snapshot` with deterministic operation ID
  `backfill-v1:<space-id>:<source-hash>`;
- save checkpoint only after success or a durable failure receipt;
- return counts for projected, unchanged, failed, and skipped;
- accept cancellation between items without losing the last checkpoint.

It must never call a vault or Overlay mutation method.

- [ ] **Step 5: Add cancellation, restart, and descriptor-safety tests**

Tests must prove:

- cancellation after item N resumes at N+1;
- exact second run produces unchanged receipts;
- changed canonical hash creates a new source revision;
- vault root drift and unsafe symlink produce stable failure codes;
- an unavailable root does not expose its absolute path;
- Overlay reserved frontmatter is normalized to body-only content;
- checkpoint corruption fails closed instead of restarting from an arbitrary
  path.

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_backfill.py \
  tests/test_vault_security.py tests/test_overlay_storage.py
uv run ruff check deeper_notebook/knowledge_engine/backfill.py \
  tests/test_knowledge_engine_backfill.py
```

Expected: all focused tests pass and Ruff is clean.

- [ ] **Step 6: Commit backfill**

```bash
git add deeper_notebook/knowledge_engine/backfill.py \
  tests/test_knowledge_engine_backfill.py
git commit -m "feat(knowledge): backfill canonical sources safely"
```

---

### Task 6: Contained Dual Projection

**Files:**
- Create: `deeper_notebook/knowledge_engine/shadow.py`
- Create: `tests/test_knowledge_engine_shadow.py`
- Modify: `deeper_notebook/vault/service.py`
- Modify: `deeper_notebook/overlay/service.py`
- Modify: `tests/test_vault_service.py`
- Modify: `tests/test_overlay_service.py`

**Interfaces:**
- Consumes: adapters and `KnowledgeRepository`.
- Produces: `KnowledgeShadowCoordinator.project_external` and
  `project_overlay`; optional `shadow_projector` constructor dependency on both
  existing services.

- [ ] **Step 1: Write failing containment tests**

```python
import pytest


@pytest.mark.asyncio
async def test_vault_legacy_projection_succeeds_when_shadow_fails(vault_fixture):
    vault_fixture.shadow.fail_with("knowledge_engine_repository_unavailable")
    result = await vault_fixture.service.scan(vault_fixture.mount.id)
    assert result.projected == 1
    assert vault_fixture.legacy_projection_count == 1
    assert vault_fixture.shadow.failure_receipts == [
        "knowledge_engine_repository_unavailable"
    ]


@pytest.mark.asyncio
async def test_overlay_save_succeeds_when_shadow_fails(overlay_fixture):
    overlay_fixture.shadow.fail_with("knowledge_engine_repository_unavailable")
    page = await overlay_fixture.create_unique("Research")
    assert page.overlay.revision == 1
    assert overlay_fixture.canonical_markdown().startswith("---\n")
    assert overlay_fixture.shadow.failure_receipts == [
        "knowledge_engine_repository_unavailable"
    ]


@pytest.mark.asyncio
async def test_shadow_receives_exact_canonical_bytes(vault_fixture):
    await vault_fixture.service.scan(vault_fixture.mount.id)
    envelope = vault_fixture.shadow.envelopes[0]
    assert envelope.canonical_bytes == vault_fixture.source_bytes
    assert envelope.observed_content_hash == vault_fixture.source_hash
```

- [ ] **Step 2: Run containment tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_shadow.py \
  tests/test_vault_service.py tests/test_overlay_service.py
```

Expected: failures because the services have no shadow dependency.

- [ ] **Step 3: Implement `KnowledgeShadowCoordinator`**

The coordinator:

- builds source envelopes from exact `VaultWorkItem.content` or exact Overlay
  canonical Markdown bytes;
- runs the selected adapter;
- appends only legacy identity claims proven by the supplied mount, vault-file,
  projected note, Overlay space, and Overlay note records;
- commits with deterministic operation IDs derived from the legacy operation
  plus source hash;
- attempts a sanitized engine failure receipt when adapter or repository work
  fails; if the receipt repository itself is unavailable, emits only stable
  code `knowledge_engine_failure_receipt_unavailable`;
- logs only space/operation IDs and stable error codes;
- returns `None`; it never returns content to the legacy service.

Do not catch `BaseException`; cancellation must propagate during shutdown.

- [ ] **Step 4: Inject optional shadow projection after legacy success**

Add a keyword-only constructor dependency to `VaultService`:

```python
def __init__(
    self,
    repository: _Repository,
    *,
    shadow_projector: KnowledgeShadowProjector | None = None,
    stable_after_seconds: float = 2.0,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    self._shadow_projector = shadow_projector
```

After `repository.project_document` returns status `projected` or `unchanged`
without reconciliation, invoke `project_external` with
`parsed.source_format`, `result.vault_file_id`, and `result.note_id`.
`parsed.source_format` must be one of `obsidian`, `logseq`, or `markdown`;
`mixed` is a mount detection policy, never an adapter source kind. Catch
`Exception`, require the coordinator to attempt its failure receipt, and
continue the proven watcher handoff.

Add the analogous optional dependency to `OverlayService`. Invoke
`project_overlay` only after `commit_revision` succeeds and before returning
the hydrated page. Replay paths may re-submit the same deterministic shadow
operation and must remain unchanged.

- [ ] **Step 5: Prove no shadow path can mutate external sources**

Add tests that inject objects whose write, replace, delete, rename, move, and
scan methods raise if called. Project external content and assert those methods
remain untouched. Also inspect the public vault router OpenAPI inventory and
assert no new mutating route exists.

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_shadow.py \
  tests/test_vault_service.py tests/test_overlay_service.py \
  tests/test_vault_note_read_only.py tests/test_overlay_api.py
```

Expected: legacy behavior remains green and shadow failures are contained.

- [ ] **Step 6: Commit dual projection**

```bash
git add deeper_notebook/knowledge_engine/shadow.py \
  deeper_notebook/vault/service.py deeper_notebook/overlay/service.py \
  tests/test_knowledge_engine_shadow.py tests/test_vault_service.py \
  tests/test_overlay_service.py
git commit -m "feat(knowledge): shadow proven projection paths"
```

---

### Task 7: Runtime Flags, Lifespan, and Backfill Ownership

**Files:**
- Modify: `deeper_notebook/environment.py`
- Create: `deeper_notebook/knowledge_engine/service.py`
- Create: `tests/test_knowledge_engine_service.py`
- Create: `tests/test_knowledge_engine_lifespan.py`
- Modify: `api/main.py`
- Modify: `tests/test_environment_aliases.py`

**Interfaces:**
- Consumes: repository, catalog, backfill, and shadow coordinator.
- Produces: `KnowledgeEngineService`, app state
  `knowledge_engine_service`, optional tracked backfill task.

- [ ] **Step 1: Write failing environment and lifecycle tests**

```python
from deeper_notebook.environment import resolve_env


def test_knowledge_engine_flags_use_product_precedence(monkeypatch):
    values = {
        "DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED": "true",
        "DN_KNOWLEDGE_ENGINE_SHADOW_ENABLED": "false",
    }
    assert resolve_env(
        "DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED",
        getter=values.get,
    ) == "true"


def test_knowledge_engine_flags_default_disabled(monkeypatch):
    assert resolve_env(
        "DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED",
        "false",
        getter=lambda _name: None,
    ) == "false"
```

Lifecycle tests must assert:

- disabled flags create no engine service or task;
- shadow enabled constructs the service and injects one coordinator into both
  legacy services;
- backfill enabled without shadow enabled logs
  `knowledge_engine_configuration_invalid`, disables engine/backfill, and
  leaves legacy startup available;
- shutdown cancels and awaits only the exact backfill task;
- engine startup failure logs a type/stable code and leaves legacy services
  available.

- [ ] **Step 2: Run environment/lifecycle tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_environment_aliases.py \
  tests/test_knowledge_engine_service.py \
  tests/test_knowledge_engine_lifespan.py
```

Expected: unknown product environment setting, missing engine service, and
missing lifespan wiring failures.

- [ ] **Step 3: Register canonical environment settings**

Add these suffixes to `_SHORT_SUFFIXES` in
`deeper_notebook/environment.py`:

```python
"KNOWLEDGE_ENGINE_BACKFILL_ENABLED",
"KNOWLEDGE_ENGINE_SHADOW_ENABLED",
```

Use a strict boolean parser in the engine service:

```python
def enabled_setting(canonical_name: str) -> bool:
    value = resolve_env(canonical_name, "false")
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("invalid knowledge engine boolean setting")
```

- [ ] **Step 4: Implement the service status boundary**

`KnowledgeEngineService` owns:

- the repository;
- shadow coordinator;
- canonical catalog;
- backfill service;
- optional `asyncio.Lock` for status/backfill transitions.

It exposes:

```python
async def status(self) -> EngineProjectionStatus
async def get_document(self, document_id: str) -> KnowledgeDocument
async def list_documents(
    self,
    *,
    space_id: str | None,
    limit: int,
    offset: int,
) -> list[KnowledgeDocument]
async def run_backfill(self) -> BackfillResult
```

No method exposes canonical bytes or absolute roots.

- [ ] **Step 5: Wire optional lifespan ownership**

In `api/main.py`, after migrations and before constructing legacy services:

1. resolve both flags;
2. fail closed to legacy-only mode with stable code
   `knowledge_engine_configuration_invalid` when `backfill=true` and
   `shadow=false`;
3. construct repository, service, and coordinator only when shadow is enabled;
4. pass the same coordinator into `OverlayService` and `VaultService`;
5. set `app.state.knowledge_engine_service`;
6. create one named backfill task only when enabled;
7. on shutdown, cancel/await the exact task, then clear app state;
8. contain engine failures without disabling legacy services.

Do not start a backfill merely because the diagnostic router is imported.

- [ ] **Step 6: Run lifecycle and existing startup tests**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_service.py \
  tests/test_knowledge_engine_lifespan.py tests/test_environment_aliases.py \
  tests/test_vault_service.py tests/test_overlay_service.py \
  tests/test_health_endpoints.py
```

Expected: all focused lifecycle tests pass.

- [ ] **Step 7: Commit runtime ownership**

```bash
git add deeper_notebook/environment.py \
  deeper_notebook/knowledge_engine/service.py api/main.py \
  tests/test_knowledge_engine_service.py tests/test_environment_aliases.py \
  tests/test_knowledge_engine_lifespan.py
git commit -m "feat(knowledge): own shadow engine lifecycle"
```

---

### Task 8: Redacted Read-Only Diagnostic API

**Files:**
- Create: `api/schemas/knowledge_engine.py`
- Create: `api/routers/knowledge_engine.py`
- Create: `tests/test_knowledge_engine_api.py`
- Modify: `api/main.py`

**Interfaces:**
- Consumes: `KnowledgeEngineService`.
- Produces:
  `GET /api/deeper-notebook/knowledge-engine/status`,
  `GET /api/deeper-notebook/knowledge-engine/documents`,
  `GET /api/deeper-notebook/knowledge-engine/documents/{document_id}`.

- [ ] **Step 1: Write failing route and OpenAPI safety tests**

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_diagnostic_routes_are_read_only(app_with_engine):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        status = await client.get(
            "/api/deeper-notebook/knowledge-engine/status"
        )
        documents = await client.get(
            "/api/deeper-notebook/knowledge-engine/documents"
        )
    assert status.status_code == 200
    assert documents.status_code == 200
    paths = app_with_engine.openapi()["paths"]
    engine_paths = {
        path: set(methods)
        for path, methods in paths.items()
        if "/knowledge-engine/" in path
    }
    assert engine_paths
    assert all(methods <= {"get", "parameters"} for methods in engine_paths.values())


def test_wire_contract_never_contains_absolute_root(valid_document_response):
    serialized = valid_document_response.model_dump_json()
    assert "/Users/" not in serialized
    assert "root_path" not in serialized
    assert "canonical_bytes" not in serialized
```

- [ ] **Step 2: Run API tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_api.py
```

Expected: routes return 404 and schema imports fail.

- [ ] **Step 3: Implement strict redacted schemas**

Wire contracts include:

- logical space ID, display name, source kind, authority kind, state, and
  capabilities;
- document ID, space ID, relative display locator, title, kind, source hash,
  source revision, provenance, state, and capabilities;
- counts and stable error codes in status.

They exclude normalized body from list responses. The detail response may
include normalized body because it is an authenticated local page read, but it
must still exclude canonical bytes and absolute roots.

- [ ] **Step 4: Implement GET-only authenticated router**

Use the existing app authentication middleware and error envelope
`{"detail": {"code": "<stable-code>"}}`.

Map:

- disabled service -> 404 `knowledge_engine_disabled`;
- unavailable repository -> 503 `knowledge_engine_unavailable`;
- absent document -> 404 `knowledge_document_not_found`;
- invalid pagination/ID -> 422 `knowledge_engine_request_invalid`.

Never log exception text, document content, or a root.

- [ ] **Step 5: Wire the router and compatibility alias policy**

Include only the canonical prefix:

```python
app.include_router(
    knowledge_engine.router,
    prefix="/api/deeper-notebook",
    tags=["deeper-notebook-knowledge-engine"],
)
```

Do not add a new `/api/onp` alias for a feature that did not exist under the
legacy brand.

- [ ] **Step 6: Run API, auth, and route-safety tests**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_api.py \
  tests/test_overlay_api.py tests/test_vault_api.py \
  tests/test_vault_note_read_only.py
```

Expected: all routes and existing safety tests pass.

- [ ] **Step 7: Commit diagnostic API**

```bash
git add api/schemas/knowledge_engine.py api/routers/knowledge_engine.py \
  api/main.py \
  tests/test_knowledge_engine_api.py
git commit -m "feat(knowledge): expose redacted shadow diagnostics"
```

---

### Task 9: Deterministic Equivalence Engine and Verifier

**Files:**
- Create: `deeper_notebook/knowledge_engine/equivalence.py`
- Create: `tests/test_knowledge_engine_equivalence.py`
- Create: `scripts/verify_unified_knowledge_engine.py`
- Create: `tests/test_verify_unified_knowledge_engine.py`
- Modify: `deeper_notebook/knowledge_engine/service.py`
- Modify: `api/schemas/knowledge_engine.py`
- Modify: `api/routers/knowledge_engine.py`
- Modify: `tests/test_knowledge_engine_api.py`

**Interfaces:**
- Consumes: legacy vault/Overlay repositories, `KnowledgeRepository`, and
  redacted engine status.
- Produces: `ProjectionDigest`, `EquivalenceDifference`,
  `EquivalenceReport`, `compare_projection_digests`,
  `GET /api/deeper-notebook/knowledge-engine/equivalence`, and verifier exit
  codes.

- [ ] **Step 1: Write failing comparator tests**

```python
from deeper_notebook.knowledge_engine.contracts import ProjectionDigest
from deeper_notebook.knowledge_engine.equivalence import (
    compare_projection_digests,
)


def test_equal_digests_pass_without_differences():
    digest = ProjectionDigest(
        space_id="knowledge_engine_space:test",
        document_count=2,
        block_count=4,
        relation_count=3,
        task_count=1,
        asset_count=0,
        document_hashes={
            "Pages/A.md": "a" * 64,
            "Pages/B.md": "b" * 64,
        },
        identity_pairs={
            "note:a": "knowledge_engine_document:a",
            "note:b": "knowledge_engine_document:b",
        },
        graph_edges=["note:a->note:b:wikilink"],
        exact_search_membership={"research": ["Pages/A.md"]},
    )
    report = compare_projection_digests(digest, digest)
    assert report.passed is True
    assert report.differences == []


def test_hash_or_authority_drift_blocks_equivalence():
    legacy = projection_digest(hash_value="a" * 64, authority="external_read_only")
    unified = projection_digest(hash_value="b" * 64, authority="app_owned")
    report = compare_projection_digests(legacy, unified)
    assert report.passed is False
    assert {item.code for item in report.differences} == {
        "document_hash_mismatch",
        "authority_mismatch",
    }
```

- [ ] **Step 2: Run comparator tests and confirm RED**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_equivalence.py
```

Expected: missing equivalence module or missing digest contracts.

- [ ] **Step 3: Implement sorted redacted digests and comparator**

Digest builders must normalize ordering and compare:

- identity pairs;
- relative locators and canonical hashes;
- document, block, relation, task, property, tag, and asset counts;
- outgoing/backlink membership;
- graph edge membership;
- exact-search membership for an explicit bounded query set;
- source authority, format, provenance, and capabilities;
- Overlay revision mappings.

The report stores counts, hashes, IDs, relative locators, and stable codes. It
does not store note bodies, tokens, or absolute roots.

- [ ] **Step 4: Add the authenticated redacted equivalence endpoint**

Add a bounded service method and GET-only route:

```python
async def equivalence_report(
    self,
    *,
    space_id: str,
    exact_queries: tuple[str, ...],
) -> EquivalenceReport
```

The server builds both digests because it owns the legacy and unified
repository boundaries. Inject explicit `legacy_digest_builder` and
`unified_digest_builder` callables into `KnowledgeEngineService`; do not let the
router query SurrealDB directly. Accept 1–32 non-empty queries of at most 256
characters each. Return only the redacted report fields described above.
Disabled, unavailable, invalid, and mismatch states use the stable API error
policy from Task 8; an equivalence mismatch is still a successful GET response
whose `passed` field is false. Extend the OpenAPI test to prove this route is
GET only.

- [ ] **Step 5: Write failing CLI safety tests**

Tests invoke the verifier with a fake API/repository boundary and prove:

- `0` when every selected space passes;
- `2` for invalid arguments or unsafe report path;
- `3` when engine is disabled/unavailable;
- `4` for equivalence mismatch;
- report path must be outside source roots and token paths;
- report publication is mode 0600, fsynced, and atomic;
- malformed or empty source inventory fails closed;
- output never contains note text or authentication tokens.

- [ ] **Step 6: Implement controlled verifier CLI**

The CLI arguments are:

```text
--api-url
--auth-token-file
--report-path
--space-id (repeatable)
--exact-query (repeatable, max 32)
--require-shadow-enabled
```

Use the hardened path-disjointness, token-permission, private temporary file,
and atomic replacement patterns from `scripts/verify_overlay_foundation.py`
without importing private functions from that script.

In its base equivalence mode, the verifier performs only read-only API calls
to the server-side equivalence endpoint. It does not create mounts, trigger
vault scans, run backfill, or modify canonical content.

- [ ] **Step 7: Run equivalence and verifier tests**

Run:

```bash
uv run pytest -q tests/test_knowledge_engine_equivalence.py \
  tests/test_verify_unified_knowledge_engine.py \
  tests/test_knowledge_engine_api.py
uv run ruff check deeper_notebook/knowledge_engine/equivalence.py \
  deeper_notebook/knowledge_engine/service.py \
  api/schemas/knowledge_engine.py api/routers/knowledge_engine.py \
  scripts/verify_unified_knowledge_engine.py \
  tests/test_knowledge_engine_equivalence.py \
  tests/test_knowledge_engine_api.py \
  tests/test_verify_unified_knowledge_engine.py
```

Expected: comparator/verifier tests pass and Ruff is clean.

- [ ] **Step 8: Commit equivalence proof tooling**

```bash
git add deeper_notebook/knowledge_engine/equivalence.py \
  deeper_notebook/knowledge_engine/service.py \
  api/schemas/knowledge_engine.py api/routers/knowledge_engine.py \
  scripts/verify_unified_knowledge_engine.py \
  tests/test_knowledge_engine_equivalence.py \
  tests/test_knowledge_engine_api.py \
  tests/test_verify_unified_knowledge_engine.py
git commit -m "feat(knowledge): verify legacy projection equivalence"
```

---

### Task 10: Controlled Synthetic Restart Proof and Foundation Record

**Files:**
- Modify: `scripts/verify_unified_knowledge_engine.py`
- Modify: `tests/test_verify_unified_knowledge_engine.py`
- Modify: `tests/integration/test_knowledge_engine_projection.py`
- Create: `docs/verification/2026-07-30-deeper-notebook-unified-engine-foundation.md`
- Modify: `scripts/rebrand-allowlist.json` only for exact audit findings.

**Interfaces:**
- Consumes: all foundation components.
- Produces: a two-phase synthetic proof with external restart boundary and a
  committed verification record. No product feature cutover.

- [ ] **Step 1: Add failing two-phase proof tests**

The verifier test harness must require:

1. a marked disposable Overlay root;
2. disjoint marked synthetic parent and child external vault roots;
3. a fresh SurrealDB namespace upgraded to migration 38;
4. synthetic legacy records and canonical files prepared before API launch;
5. phase 1 startup backfill followed by one Overlay update and one external
   child scan through existing authenticated APIs to prove dual projection;
6. one relative trust-manifest import followed by exact idempotent replay;
7. an externally performed API restart;
8. phase 2 persistence/equivalence verification for documents, backlinks,
   graph edges, exact search, tasks, and trust records;
9. before/after file fingerprints and synthetic Git status;
10. cleanup ownership evidence.

Phase 1 exits `5` with stable state
`knowledge_engine_restart_required`. Phase 2 exits `0` only when process nonce
and PID changed while database, projection IDs, hashes, and checkpoints
persisted.

Extend the verifier with a separately gated controlled-proof mode:

```text
--proof-phase prepare|verify
--synthetic-manifest
--expected-prior-state
```

The manifest names only marked disposable roots and expected synthetic
identities. `prepare` may call the existing authenticated Overlay update and
parent/child mount, scan, and trust-import endpoints only after every marker
and disjointness check passes. It repeats the exact trust import and requires
an unchanged/idempotent result. It never mounts or scans an unmarked root.
`verify` is read-only.
Outside controlled-proof mode, the Task 9 verifier remains strictly read-only.

- [ ] **Step 2: Implement strict controlled-proof markers**

Accepted synthetic roots must:

- exist beneath the canonical system temporary directory;
- contain an exact marker file created by the test harness;
- be pairwise disjoint from report, token, database, and state paths;
- contain no symlink/hardlink escape;
- not equal or contain a user home, Desktop, repository root, or mounted private
  vault.

Reject `/Users/Antman/Desktop/BrainPulse Ventures LLC/2nd Brains` and
`/Users/Antman/Desktop/2nd Brains` by general root policy, not a username-only
special case.

- [ ] **Step 3: Extend the native integration test**

The integration test must prove:

- fresh database `0 -> 38`;
- recorded `37 -> 38`;
- sticky `38 down -> 38 up` preserves unified records;
- backfill checkpoint survives repository/service reconstruction;
- dual projection persists one Overlay and one external synthetic document;
- a synthetic child mount retains its parent identity and projects its own
  canonical files without aliasing the parent space;
- relative trust import replays idempotently and remains a compatibility
  record without granting external write capability;
- identical replay is unchanged;
- an adapter failure retains the last valid snapshot;
- no legacy table or record is removed.

- [ ] **Step 4: Run focused foundation gates**

Run:

```bash
uv run pytest -q \
  tests/test_knowledge_engine_contracts.py \
  tests/test_knowledge_engine_adapters.py \
  tests/test_knowledge_engine_migration.py \
  tests/test_knowledge_engine_repository.py \
  tests/test_knowledge_engine_backfill.py \
  tests/test_knowledge_engine_shadow.py \
  tests/test_knowledge_engine_service.py \
  tests/test_knowledge_engine_lifespan.py \
  tests/test_knowledge_engine_api.py \
  tests/test_knowledge_engine_equivalence.py \
  tests/test_verify_unified_knowledge_engine.py
uv run pytest -q tests/integration/test_knowledge_engine_projection.py \
  -m integration_surreal
```

Expected: every focused unit and native integration test passes.

- [ ] **Step 5: Run complete project gates serially**

Run in this order:

```bash
uv run pytest -q
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
npm run test:e2e:mocked
cd ..
uv run python scripts/rebrand_audit.py --check
git diff --check
```

Expected:

- Python suite: zero failures;
- frontend unit: zero failures;
- lint and TypeScript: exit 0;
- production build: exit 0;
- mocked browser: zero failures;
- rebrand audit: `unexpected_active_identity = 0` and no stale allowlist entry;
- diff hygiene: exit 0.

Restore any tracked Playwright `.last-run.json` fixture exactly and remove only
new generated `__pycache__` files before recording a clean status.

- [ ] **Step 6: Run the controlled native two-phase proof**

Start a native SurrealDB 2.1 process and API through the existing desktop/native
runtime path with:

```text
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED=true
DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_BACKFILL_ENABLED=true
```

Use only disposable marked synthetic roots. Run phase 1, restart the exact API
process, then run phase 2. Before the first launch, use the test harness—not
production APIs—to create canonical synthetic files and the minimum valid
legacy Overlay/vault records needed for startup backfill. During phase 1, wait
for the tracked startup backfill to reach a terminal status, then perform the
marker-gated Overlay update, parent verification, child registration/scan, and trust
import/replay. Record PIDs, nonces, database version, stable engine IDs,
parent/child identities, counts, hashes, checkpoint state, equivalence result,
trust-import idempotency, source fingerprints, Git-status digest, and
port/process cleanup. Do not record note contents or tokens.

- [ ] **Step 7: Write the verification record**

The record must identify:

- exact tested implementation commit;
- commands, exit codes, and counts;
- migration 38 lifecycle;
- shadow-disabled and shadow-enabled behavior;
- backfill restart/idempotency;
- dual-projection containment;
- synthetic child-scan isolation and parent identity;
- relative trust-import idempotency;
- equivalence digests;
- external synthetic fingerprint preservation;
- native restart identity;
- cleanup proof;
- independent review verdict;
- Windows packaged proof as an explicit later release gate;
- real `2nd Brains` proof as not run and not inferred.

- [ ] **Step 8: Independent read-only review**

Request a `verifier` role under the AGENTS.md orchestration rules. Give it the
exact implementation commit, specification, plan, verification record, and
commands already run. It must not edit files. Resolve all Critical and
Important findings with focused regressions and repeat review before claiming
the foundation ready.

- [ ] **Step 9: Commit the proof record**

```bash
git add scripts/verify_unified_knowledge_engine.py \
  tests/test_verify_unified_knowledge_engine.py \
  tests/integration/test_knowledge_engine_projection.py \
  docs/verification/2026-07-30-deeper-notebook-unified-engine-foundation.md
# Only when the exact audit in Step 5 changed and validated this tracked file:
git add scripts/rebrand-allowlist.json
git commit -m "docs(knowledge): record unified engine foundation proof"
```

Stage `scripts/rebrand-allowlist.json` only if the exact audit required and
validated a change.

---

## Plan Completion Boundary

This plan is complete when the shadow unified engine:

- normalizes all four initial source kinds into strict snapshots;
- persists those snapshots transactionally under migration 38;
- backfills canonical content idempotently and resumes after restart;
- dual-projects exact canonical bytes without breaking legacy operations;
- exposes only authenticated redacted GET diagnostics;
- proves deterministic legacy/unified equivalence;
- preserves external source fingerprints and synthetic Git state;
- passes controlled native macOS restart proof;
- leaves every product feature on its existing compatibility read path;
- leaves no live proof runtime, mount, scan, or backfill;
- has no unresolved Critical or Important independent-review finding.

Productivity Core implementation begins under its own plan only after this
foundation is merged and accepted. Tasks and Journals remain the third plan.
