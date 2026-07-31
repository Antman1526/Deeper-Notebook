"""Public contracts for the read-only Deeper Notebook vault API."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from deeper_notebook.vault.repository import (
    TrustImportResult,
    VaultFile,
    VaultGraph,
    VaultLink,
    VaultMount,
    VaultPage,
    VaultProjectionError,
    VaultSyncReceipt,
    VaultTrustRecord,
    VaultTrustSummary,
)
from deeper_notebook.vault.service import VaultScanResult


class _Repository:
    def __init__(self) -> None:
        self.imported: list[str] = []

    async def list_mounts(self):
        return [_mount()]

    async def get_mount(self, vault_id: str):
        if vault_id != "vault_mount:fixture":
            raise LookupError("vault_mount_not_found")
        return _mount()

    async def list_files(self, vault_id: str, prefix: str, limit: int, offset: int):
        return [
            VaultFile(
                id="vault_file:one",
                note_id="note:derived-projection-id",
                vault_id=vault_id,
                relative_path="notes/one.md",
                file_kind="markdown",
                format="markdown",
                parse_status="parsed",
                deleted_state="present",
            )
        ]

    async def get_page(self, vault_id: str, note_id: str):
        if note_id != "note:one":
            raise LookupError("vault_note_not_found")
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
            blocks=[
                {
                    "parser_id": "parser-one",
                    "stable_source_id": "block-one",
                    "markdown": "# One",
                },
                {"parser_id": "parser-two", "markdown": "Two"},
            ],
        )

    async def backlinks(self, vault_id: str, note_id: str):
        return [_link("note_link:back", "note:two", note_id)]

    async def outgoing_links(self, vault_id: str, note_id: str):
        return [_link("note_link:out", note_id, "note:two")]

    async def graph(self, vault_id: str, center_note_id: str, depth: int, limit: int):
        return VaultGraph(nodes=[{"id": center_note_id, "title": "One"}], edges=[])

    async def list_receipts(self, vault_id: str, limit: int, offset: int):
        return [
            VaultSyncReceipt(
                operation_id="scan-1",
                vault_id=vault_id,
                vault_file_id="vault_file:one",
                operation="project",
                parser_version="test",
                status="success",
                started_at="2026-01-01T00:00:00Z",
            )
        ]

    async def import_trust_manifest(self, vault_id: str, manifest_relative_path: str):
        self.imported.append(manifest_relative_path)
        return TrustImportResult(
            changed=0 if len(self.imported) > 1 else 1,
            unchanged=1 if len(self.imported) > 1 else 0,
        )

    async def list_trust_records(self, vault_id: str, limit: int, offset: int):
        return [
            VaultTrustRecord(
                manifest_id="approved-one",
                vault_id=vault_id,
                canonical_relative_path="sources/one.md",
                status="approved",
                resolution_state="resolved",
                reviewer="owner",
                reviewed_at="2026-01-01T00:00:00Z",
                source_type="markdown",
                evidence_class="source",
                content_hash="a" * 64,
                derived_from=[],
                manifest_relative_path="brain-engine/trust.json",
            )
        ]

    async def trust_summary(self, vault_id: str):
        return VaultTrustSummary(total=1, resolved=1, unresolved=0)


class _Service:
    def __init__(self, repository: _Repository) -> None:
        self._repository = repository
        self.request = None

    async def register_mount(self, request):
        self.request = request
        return _mount()

    async def scan(self, vault_id: str):
        if vault_id != "vault_mount:fixture":
            raise LookupError("vault_mount_not_found")
        return VaultScanResult(
            vault_id=vault_id,
            status="ready-read-only",
            operation_id="vault-scan-1",
            projected=2,
            unchanged=3,
            failed=1,
        )


def _mount() -> VaultMount:
    return VaultMount(
        id="vault_mount:fixture",
        name="Fixture",
        root_path="/Users/owner/fixture",
        format_mode="markdown",
        status="ready-read-only",
        watch_enabled=True,
        parser_version="test",
    )


def _link(link_id: str, source: str, target: str) -> VaultLink:
    return VaultLink(
        id=link_id,
        source_note_id=source,
        target_note_id=target,
        target_note_title="",
        target_relative_path="notes/two.md",
        target_text="Two",
        source_note_title="Source note",
        source_start=12,
        source_end=22,
        link_kind="wikilink",
        resolved=True,
    )


@pytest.fixture()
def client(monkeypatch):
    from api.main import app

    repository = _Repository()
    app.state.vault_service = _Service(repository)
    monkeypatch.setattr(
        "api.routers.vault.approve_vault_root", lambda _path: nullcontext()
    )
    test_client = TestClient(app)
    try:
        yield test_client, repository, app.state.vault_service
    finally:
        test_client.close()
        del app.state.vault_service


def test_canonical_vault_endpoints_are_read_only_and_omit_legacy_alias(client):
    test_client, _, _ = client

    prefix = "/api/deeper-notebook/vaults"
    routes = {
        path: {method.upper() for method in operations}
        for path, operations in test_client.app.openapi()["paths"].items()
    }
    required = {
        prefix,
        f"{prefix}/{{vault_id}}",
        f"{prefix}/{{vault_id}}/scan",
        f"{prefix}/{{vault_id}}/files",
        f"{prefix}/{{vault_id}}/pages/{{note_id}}",
        f"{prefix}/{{vault_id}}/pages/{{note_id}}/backlinks",
        f"{prefix}/{{vault_id}}/pages/{{note_id}}/outgoing",
        f"{prefix}/{{vault_id}}/graph",
        f"{prefix}/{{vault_id}}/receipts",
        f"{prefix}/{{vault_id}}/trust/import",
        f"{prefix}/{{vault_id}}/trust",
        f"{prefix}/{{vault_id}}/trust/summary",
    }
    assert required <= routes.keys()
    assert test_client.get("/api/onp/vaults").status_code == 404
    assert all(
        not methods & {"PUT", "PATCH", "DELETE"}
        for path, methods in routes.items()
        if path.startswith(prefix)
    )


def test_mount_create_is_strict_and_owner_detail_is_not_returned_by_list(client):
    test_client, _, service = client
    payload = {
        "name": "Fixture",
        "path": "/Users/owner/fixture",
        "format_mode": "markdown",
    }
    created = test_client.post("/api/deeper-notebook/vaults", json=payload)
    assert created.status_code == 201
    assert service.request.watch_enabled is True
    assert created.json()["root_path"] == "/Users/owner/fixture"
    assert "root_path" not in test_client.get("/api/deeper-notebook/vaults").json()[0]
    assert (
        test_client.post(
            "/api/deeper-notebook/vaults", json={**payload, "extra": True}
        ).status_code
        == 422
    )


def test_read_only_vault_resources_return_relative_data_only(client):
    test_client, _, _ = client
    root = "/api/deeper-notebook/vaults/vault_mount:fixture"
    assert test_client.get(f"{root}").status_code == 200
    assert test_client.post(f"{root}/scan").json() == {
        "operation_id": "vault-scan-1",
        "state": "ready-read-only",
        "observed": 6,
        "parsed": 2,
        "unchanged": 3,
        "unsupported": 0,
        "invalid": 1,
        "missing": 0,
        "embeddings_pending": 2,
    }
    file = test_client.get(f"{root}/files").json()[0]
    assert file["relative_path"] == "notes/one.md"
    assert file["note_id"] == "note:derived-projection-id"
    page = test_client.get(f"{root}/pages/note:one")
    assert page.status_code == 200
    assert page.json()["file"]["relative_path"] == "notes/one.md"
    assert page.json()["file"]["content_hash"] == "a" * 64
    assert page.json()["file"]["encoding"] == "utf-8"
    assert page.json()["file"]["newline"] == "lf"
    assert "/Users/" not in page.text
    backlinks = test_client.get(f"{root}/pages/note:one/backlinks")
    assert backlinks.status_code == 200
    assert backlinks.json()[0]["source_note_title"] == "Source note"
    assert "/Users/owner" not in backlinks.text
    outgoing = test_client.get(f"{root}/pages/note:one/outgoing")
    assert outgoing.status_code == 200
    assert outgoing.json()[0]["source_start"] == 12
    assert outgoing.json()[0]["source_end"] == 22
    assert outgoing.json()[0]["target_relative_path"] == "notes/two.md"
    assert outgoing.json()[0]["target_note_title"] == ""
    assert test_client.get(f"{root}/graph?center_note_id=note:one").status_code == 200
    receipts = test_client.get(f"{root}/receipts")
    assert receipts.status_code == 200
    assert "/Users/owner" not in receipts.text


def test_page_enriches_unified_identity_in_one_batched_lookup(client):
    test_client, _, _ = client

    class _IdentityService:
        calls: list[tuple[str, tuple[str, ...]]] = []

        async def resolve_legacy_page(self, *, legacy_note_id, block_keys):
            self.calls.append((legacy_note_id, block_keys))
            return {
                "document_id": "knowledge_engine_document:current",
                "block_ids": {
                    "block-one": "knowledge_engine_block:one",
                    "parser-two": "knowledge_engine_block:two",
                },
            }

    service = _IdentityService()
    test_client.app.state.knowledge_engine_service = service
    try:
        response = test_client.get(
            "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one"
        )
    finally:
        del test_client.app.state.knowledge_engine_service

    assert response.status_code == 200
    assert (
        response.json()["knowledge_document_id"] == "knowledge_engine_document:current"
    )
    assert [block["knowledge_block_id"] for block in response.json()["blocks"]] == [
        "knowledge_engine_block:one",
        "knowledge_engine_block:two",
    ]
    assert service.calls == [("note:one", ("block-one", "parser-two"))]


def test_page_identity_enrichment_fails_open_for_malformed_service_data(client):
    test_client, _, _ = client

    class _MalformedIdentityService:
        async def resolve_legacy_page(self, **_kwargs):
            return {
                "document_id": "knowledge_engine_document:bad/id",
                "block_ids": {"block-one": "knowledge_engine_block:bad/id"},
            }

    test_client.app.state.knowledge_engine_service = _MalformedIdentityService()
    try:
        response = test_client.get(
            "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one"
        )
    finally:
        del test_client.app.state.knowledge_engine_service

    assert response.status_code == 200
    assert response.json()["knowledge_document_id"] is None
    assert all("knowledge_block_id" not in block for block in response.json()["blocks"])


@pytest.mark.asyncio
async def test_page_identity_enrichment_times_out_without_blocking_canonical_reads(
    monkeypatch,
):
    from api.routers import vault as vault_router

    class _NeverCompletes:
        async def resolve_legacy_page(self, **_kwargs):
            await asyncio.Event().wait()

    monkeypatch.setattr(
        vault_router, "_IDENTITY_ENRICHMENT_TIMEOUT_SECONDS", 0.01, raising=False
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(knowledge_engine_service=_NeverCompletes())
        )
    )

    result = await asyncio.wait_for(
        vault_router._page_identity(
            request,
            legacy_note_id="note:one",
            blocks=[{"parser_id": "heading", "markdown": "# One"}],
        ),
        timeout=0.1,
    )

    assert result == (None, [{"parser_id": "heading", "markdown": "# One"}])


def test_unresolved_link_response_keeps_null_target_identity_and_spans(client):
    test_client, repository, _ = client
    repository.outgoing_links = AsyncMock(
        return_value=[
            VaultLink(
                id="note_link:unresolved",
                source_note_id="note:one",
                target_text="Missing",
                source_start=4,
                source_end=15,
                link_kind="wikilink",
                resolved=False,
            )
        ]
    )

    response = test_client.get(
        "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one/outgoing"
    )

    assert response.status_code == 200
    assert response.json()[0]["target_note_title"] is None
    assert response.json()[0]["target_relative_path"] is None
    assert response.json()[0]["source_start"] == 4
    assert response.json()[0]["source_end"] == 15


def test_trust_import_is_relative_and_idempotent(client):
    test_client, repository, _ = client
    root = "/api/deeper-notebook/vaults/vault_mount:fixture"
    payload = {"manifest_relative_path": "brain-engine/trust.json"}
    assert test_client.post(f"{root}/trust/import", json=payload).json()["changed"] == 1
    assert (
        test_client.post(f"{root}/trust/import", json=payload).json()["unchanged"] == 1
    )
    assert repository.imported == ["brain-engine/trust.json", "brain-engine/trust.json"]
    assert (
        test_client.post(
            f"{root}/trust/import", json={"manifest_relative_path": "../trust.json"}
        ).status_code
        == 422
    )
    assert (
        test_client.post(
            f"{root}/trust/import", json={"manifest_relative_path": "/tmp/trust.json"}
        ).status_code
        == 422
    )
    assert test_client.get(f"{root}/trust").status_code == 200
    assert test_client.get(f"{root}/trust/summary").json() == {
        "total": 1,
        "resolved": 1,
        "unresolved": 0,
    }


def test_domain_failures_have_stable_safe_responses(client):
    test_client, _, service = client
    root = "/api/deeper-notebook/vaults/vault_mount:fixture"

    async def missing(_vault_id):
        raise LookupError("vault_mount_not_found")

    service.scan = missing
    response = test_client.post(f"{root}/scan")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "vault_not_found"}}

    async def scanning(_vault_id):
        return VaultScanResult(
            vault_id="vault_mount:fixture",
            status="scanning",
            operation_id="vault-scan-2",
        )

    service.scan = scanning
    response = test_client.post(f"{root}/scan")
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "vault_scan_in_progress"}}


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


def test_page_maps_invalid_persisted_file_to_safe_projection_error(client):
    test_client, repository, _ = client
    repository.get_page = AsyncMock(
        side_effect=VaultProjectionError(
            "invalid persisted path /Users/private/alpha.md"
        ),
    )

    response = test_client.get(
        "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "vault_page_invalid"}}
    assert "vault_root_invalid" not in response.text
    assert "/Users/" not in response.text


def test_outgoing_maps_invalid_resolved_link_to_safe_projection_error(client):
    test_client, repository, _ = client
    repository.outgoing_links = AsyncMock(
        side_effect=VaultProjectionError("incomplete resolved link pages/private.md"),
    )

    response = test_client.get(
        "/api/deeper-notebook/vaults/vault_mount:fixture/pages/note:one/outgoing"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "vault_page_invalid"}}
    assert "vault_root_invalid" not in response.text
    assert "pages/private.md" not in response.text
