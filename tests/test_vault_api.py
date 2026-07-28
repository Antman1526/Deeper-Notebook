"""Public contracts for the read-only Deeper Notebook vault API."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from deeper_notebook.vault.repository import (
    TrustImportResult,
    VaultFile,
    VaultGraph,
    VaultLink,
    VaultMount,
    VaultPage,
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
        return VaultPage(note={"id": note_id, "title": "One"})

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
        target_text="Two",
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
    from api.routers.vault import router as vault_router

    prefix = "/api/deeper-notebook/vaults"
    routes = {
        f"/api/deeper-notebook{route.path}": route.methods
        for route in vault_router.routes
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
    assert test_client.get(f"{root}/files").json()[0]["relative_path"] == "notes/one.md"
    assert test_client.get(f"{root}/pages/note:one").status_code == 200
    assert test_client.get(f"{root}/pages/note:one/backlinks").status_code == 200
    assert test_client.get(f"{root}/pages/note:one/outgoing").status_code == 200
    assert test_client.get(f"{root}/graph?center_note_id=note:one").status_code == 200
    receipts = test_client.get(f"{root}/receipts")
    assert receipts.status_code == 200
    assert "/Users/owner" not in receipts.text


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
