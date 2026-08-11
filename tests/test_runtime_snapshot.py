"""Behavior-level tests for the redacted runtime snapshot contract."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _providers(*, readiness=None, **overrides):
    from api.runtime_snapshot import RuntimeSnapshotProviders

    values = {
        "readiness": readiness
        or (lambda: {"database": "online", "migrations": "applied"}),
        "startup_receipts": lambda: {
            "stages": [
                {"stage": "launcher_start", "elapsed_ms": 12},
                {"stage": "core_ready", "elapsed_ms": 34},
            ]
        },
        "update_status": lambda: {
            "enabled": True,
            "current": "1.8.5",
            "latest": "1.8.5",
            "update_available": False,
        },
        "vault_summary": lambda: [
            {"status": "ready-read-only", "write_policy": "read-only"}
        ],
        "knowledge_summary": lambda: {
            "projected": 3,
            "unchanged": 2,
            "failed": 0,
        },
        "auto_export_directory": lambda: None,
        "active_data_root": lambda: Path("/private/should-never-leak"),
    }
    values.update(overrides)
    return RuntimeSnapshotProviders(**values)


@pytest.mark.asyncio
async def test_ready_snapshot_uses_only_injected_read_models(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(auto_export_directory=lambda: tmp_path)
    )

    assert snapshot.status == "ready"
    assert snapshot.reasons == []
    assert snapshot.readiness.database == "online"
    assert snapshot.readiness.migrations == "applied"
    assert snapshot.startup.stages[0].stage == "launcher_start"
    assert snapshot.vault.ready == 1
    assert snapshot.knowledge.projected == 3
    assert snapshot.backup.file_count == 0
    assert "/private/should-never-leak" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_degraded_and_unknown_states_use_allowlisted_reason_codes() -> None:
    from api.runtime_snapshot import ALLOWED_REASON_CODES, build_runtime_snapshot

    degraded = await build_runtime_snapshot(
        _providers(
            readiness=lambda: {
                "database": "offline",
                "migrations": "pending",
                "database_error": "raw db details should never escape",
            },
            vault_summary=lambda: {"unexpected": object()},
        )
    )
    assert degraded.status == "degraded"
    assert set(degraded.reasons) <= ALLOWED_REASON_CODES
    assert "raw db details" not in degraded.model_dump_json()

    unknown = await build_runtime_snapshot(
        _providers(readiness=lambda: {"not_a_readiness_field": True})
    )
    assert unknown.status == "unknown"
    assert set(unknown.reasons) <= ALLOWED_REASON_CODES


@pytest.mark.asyncio
async def test_vault_summary_is_count_bounded() -> None:
    """A malformed or unexpectedly large read model cannot make the route 500."""

    from api.runtime_snapshot import build_runtime_snapshot

    class TooManyReadyMounts(Sequence[dict[str, str]]):
        def __len__(self) -> int:
            return 1_000_001

        def __getitem__(self, index: int) -> dict[str, str]:
            if 0 <= index < len(self):
                return {"status": "ready-read-only"}
            raise IndexError(index)

    snapshot = await build_runtime_snapshot(
        _providers(vault_summary=lambda: TooManyReadyMounts())
    )

    assert snapshot.vault.ready == 1_000_000
    assert snapshot.vault.state == "ready"


@pytest.mark.asyncio
async def test_provider_failures_are_redacted_without_running_side_effects():
    from api.runtime_snapshot import build_runtime_snapshot

    calls: list[str] = []

    def exploding_readiness():
        raise RuntimeError("SECRET=/Users/private/raw exception detail")

    def read_startup():
        return {"stages": []}

    def read_updates():
        return {"enabled": True, "current": "1.8.5", "update_available": False}

    def read_vault():
        return [{"status": "ready-read-only", "write_policy": "read-only"}]

    def read_knowledge():
        return {"projected": 1, "unchanged": 0, "failed": 0}

    def read_exports():
        return None

    snapshot = await build_runtime_snapshot(
        _providers(
            readiness=exploding_readiness,
            startup_receipts=read_startup,
            update_status=read_updates,
            vault_summary=read_vault,
            knowledge_summary=read_knowledge,
            auto_export_directory=read_exports,
        )
    )

    assert snapshot.status == "unknown"
    assert calls == []
    wire = snapshot.model_dump_json()
    assert "/Users/private" not in wire
    assert "SECRET=" not in wire
    assert "raw exception detail" not in wire


@pytest.mark.asyncio
async def test_auto_export_metadata_is_bounded_and_contains_no_paths(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    (tmp_path / "auto-export-001.surql").write_text("private source content")
    (tmp_path / "not-an-export.txt").write_text("ignore")

    snapshot = await build_runtime_snapshot(
        _providers(auto_export_directory=lambda: tmp_path)
    )

    assert snapshot.backup.file_count == 1
    assert str(tmp_path) not in snapshot.model_dump_json()
    assert "private source content" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_default_update_projection_does_not_check_network_or_write_state(monkeypatch):
    import api.updates_service as updates_service
    from api.runtime_snapshot import RuntimeSnapshotProviders, build_runtime_snapshot

    calls: list[str] = []

    async def forbidden_check(*args, **kwargs):
        calls.append("update_check")
        raise AssertionError("runtime snapshot must not check for updates")

    monkeypatch.setattr(updates_service, "check", forbidden_check)
    monkeypatch.setattr(
        updates_service,
        "_read_state",
        lambda: {"enabled": True, "cache": {"latest": "1.8.5"}},
    )
    monkeypatch.setattr(
        updates_service,
        "_status_from_state",
        lambda state: {
            "enabled": state["enabled"],
            "current": "1.8.5",
            "update_available": False,
        },
    )

    snapshot = await build_runtime_snapshot(
        RuntimeSnapshotProviders(
            readiness=lambda: {"database": "online", "migrations": "applied"},
            startup_receipts=lambda: {"stages": []},
            vault_summary=lambda: [],
            knowledge_summary=lambda: {"projected": 0, "unchanged": 0, "failed": 0},
            auto_export_directory=lambda: None,
        )
    )

    assert snapshot.updates.current_version == "1.8.5"
    assert calls == []


@pytest.mark.asyncio
async def test_router_uses_vault_list_only_and_never_mounts_or_scans(monkeypatch):
    from api.routers.runtime import router

    class ReadOnlyRepository:
        async def list_mounts(self):
            calls.append("list_mounts")
            return []

        async def mount(self):
            calls.append("mount")
            raise AssertionError("mount must not run")

        async def scan(self):
            calls.append("scan")
            raise AssertionError("scan must not run")

    class ReadOnlyVaultService:
        _repository = ReadOnlyRepository()

    calls: list[str] = []
    app = FastAPI()
    app.include_router(router)
    app.state.vault_service = ReadOnlyVaultService()
    app.state.runtime_readiness_provider = lambda: {
        "database": "online",
        "migrations": "applied",
    }
    app.state.runtime_startup_receipt_provider = lambda: {"stages": []}
    app.state.runtime_update_status_provider = lambda: {
        "enabled": True,
        "current": "1.8.5",
        "update_available": False,
    }
    app.state.runtime_knowledge_summary_provider = lambda: {
        "projected": 0,
        "unchanged": 0,
        "failed": 0,
    }
    app.state.runtime_auto_export_directory_provider = lambda: None
    monkeypatch.delenv("DEEPER_NOTEBOOK_PASSWORD", raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runtime/snapshot")

    assert response.status_code == 200
    assert calls == ["list_mounts"]


@pytest.mark.asyncio
async def test_authenticated_router_degrades_malformed_optional_inputs(monkeypatch) -> None:
    from api.routers.runtime import router

    app = FastAPI()
    app.include_router(router)
    app.state.runtime_snapshot_providers = _providers(
        startup_receipts=lambda: "malformed",
        update_status=lambda: {"latest": object()},
        vault_summary=lambda: None,
        knowledge_summary=lambda: {"failed": "not-an-int"},
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "snapshot-secret")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        unauthenticated = await client.get("/api/runtime/snapshot")
        authenticated = await client.get(
            "/api/runtime/snapshot",
            headers={"Authorization": "Bearer snapshot-secret"},
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    body = authenticated.json()
    assert body["status"] in {"degraded", "unknown"}
    assert "/" not in body["readiness"].get("database", "")
    assert "malformed" not in authenticated.text
    assert "snapshot-secret" not in authenticated.text
