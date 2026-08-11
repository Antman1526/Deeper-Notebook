"""Behavior-level tests for the redacted runtime snapshot contract."""

from __future__ import annotations

import builtins
import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_packaged_startup_reader_does_not_require_desktop_package(
    monkeypatch, tmp_path: Path
) -> None:
    """The bundled API has no importable desktop package at runtime."""

    from api import runtime_snapshot

    receipt = tmp_path / "startup_receipt.json"
    receipt.write_text(
        '{"schema_version":1,"stages":['
        '{"stage":"launcher_start","elapsed_ms":0},'
        '{"stage":"core_ready","elapsed_ms":42}],"chat_model":null}',
        encoding="utf-8",
    )
    original_import = builtins.__import__

    def block_packaged_desktop_import(name, *args, **kwargs):
        if name == "desktop.startup_receipts":
            raise ModuleNotFoundError("desktop package is not bundled")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_packaged_desktop_import)

    projected = runtime_snapshot._default_startup_receipts(lambda: tmp_path)

    assert projected is not None
    assert projected["stages"][-1] == {"stage": "core_ready", "elapsed_ms": 42}


@pytest.mark.asyncio
async def test_packaged_snapshot_projects_receipt_without_desktop_package(
    monkeypatch, tmp_path: Path
) -> None:
    from api import runtime_snapshot

    receipt = tmp_path / "startup_receipt.json"
    receipt.write_text(
        '{"schema_version":1,"stages":['
        '{"stage":"launcher_start","elapsed_ms":0},'
        '{"stage":"chat_model_scan","elapsed_ms":7},'
        '{"stage":"core_ready","elapsed_ms":42}],'
        '"chat_model":{"path":"/private/user/model.gguf",'
        '"size":1,"mtime_ns":2}}',
        encoding="utf-8",
    )
    original_import = builtins.__import__

    def block_packaged_desktop_import(name, *args, **kwargs):
        if name == "desktop.startup_receipts":
            raise ModuleNotFoundError("desktop package is not bundled")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_packaged_desktop_import)

    snapshot = await runtime_snapshot.build_runtime_snapshot(
        runtime_snapshot.RuntimeSnapshotProviders(
            readiness=lambda: {"database": "online", "migrations": "applied"},
            active_data_root=lambda: tmp_path,
            update_status=lambda: {
                "enabled": True,
                "current": "1.8.5",
                "update_available": False,
            },
            vault_summary=lambda: [],
            knowledge_summary=lambda: {"projected": 0, "unchanged": 0, "failed": 0},
            auto_export_directory=lambda: None,
        )
    )

    assert snapshot.startup.state == "ready"
    assert [stage.stage for stage in snapshot.startup.stages] == [
        "launcher_start",
        "chat_model_scan",
        "core_ready",
    ]
    assert "/private/user/model.gguf" not in snapshot.model_dump_json()


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

    assert snapshot.status == "degraded"
    assert snapshot.reasons == ["auto_export_unknown"]
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
async def test_throwing_provider_containers_fail_closed_to_unknown() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    class ThrowingMapping(dict):
        def get(self, key, default=None):
            raise RuntimeError(f"raw mapping failure for {key}")

    class ThrowingSequence(Sequence[dict[str, int]]):
        def __len__(self) -> int:
            raise RuntimeError("raw sequence length failure")

        def __getitem__(self, index: int) -> dict[str, int]:
            raise RuntimeError(f"raw sequence item failure {index}")

        def __iter__(self):
            raise RuntimeError("raw sequence iteration failure")

    for readiness, startup, vault, knowledge in (
        (ThrowingMapping(), None, None, None),
        ({"database": "online", "migrations": "applied"}, {"stages": ThrowingSequence()}, None, None),
        ({"database": "online", "migrations": "applied"}, None, ThrowingMapping(), None),
        ({"database": "online", "migrations": "applied"}, None, None, ThrowingMapping()),
    ):
        snapshot = await build_runtime_snapshot(
            _providers(
                readiness=lambda value=readiness: value,
                startup_receipts=(lambda value=startup: value) if startup is not None else None,
                vault_summary=(lambda value=vault: value) if vault is not None else None,
                knowledge_summary=(lambda value=knowledge: value)
                if knowledge is not None
                else None,
            )
        )
        assert snapshot.status in {"degraded", "unknown"}
        assert all(isinstance(reason, str) for reason in snapshot.reasons)
        assert "raw mapping failure" not in snapshot.model_dump_json()
        assert "raw sequence failure" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_startup_projection_stops_after_bounded_prefix() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    class LazyStages(Sequence[dict[str, int | str]]):
        def __len__(self) -> int:
            return 1_000_000

        def __getitem__(self, index: int) -> dict[str, int | str]:
            if index >= 16:
                raise AssertionError("startup stages were read past the bound")
            return {"stage": "core_ready", "elapsed_ms": index}

        def __iter__(self):
            for index in range(16):
                yield {"stage": "core_ready", "elapsed_ms": index}
            raise AssertionError("startup stages were iterated past the bound")

    snapshot = await build_runtime_snapshot(
        _providers(startup_receipts=lambda: {"stages": LazyStages()})
    )

    assert snapshot.startup.state == "ready"
    assert len(snapshot.startup.stages) == 16


@pytest.mark.asyncio
async def test_router_bounds_lazy_mount_projection_before_materializing() -> None:
    from api.routers.runtime import router

    mount_bound = 256

    class LazyMounts:
        def __iter__(self):
            for index in range(mount_bound):
                yield type("Mount", (), {"status": "ready-read-only", "write_policy": "read-only"})()
            raise AssertionError("mount summary was materialized past the bound")

    class Repository:
        async def list_mounts(self):
            return LazyMounts()

    class VaultService:
        _repository = Repository()

    app = FastAPI()
    app.include_router(router)
    app.state.vault_service = VaultService()
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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runtime/snapshot")

    assert response.status_code == 200
    assert response.json()["vault"]["ready"] == mount_bound


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


@pytest.mark.asyncio
async def test_auto_export_receipt_projects_bounded_valid_and_stale_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    from api import runtime_snapshot
    from api.runtime_snapshot import build_runtime_snapshot

    now = 1_800_000_000.0
    monkeypatch.setattr(runtime_snapshot.time, "time", lambda: now)
    export = tmp_path / "auto-export-20260101-000000.surql"
    export.write_text("private source content", encoding="utf-8")
    os.utime(export, (now, now))

    valid = await build_runtime_snapshot(_providers(auto_export_directory=lambda: tmp_path))
    assert valid.backup.freshness == "valid"
    assert valid.backup.newest_size_bytes == len("private source content")
    assert valid.backup.newest_timestamp is not None
    assert valid.backup.integrity == "unknown"
    assert str(tmp_path) not in valid.model_dump_json()
    assert "private source content" not in valid.model_dump_json()

    stale_timestamp = now - (runtime_snapshot.AUTO_EXPORT_STALE_AFTER_SECONDS + 1)
    os.utime(export, (stale_timestamp, stale_timestamp))
    stale = await build_runtime_snapshot(_providers(auto_export_directory=lambda: tmp_path))
    assert stale.backup.freshness == "stale"
    assert stale.backup.state == "degraded"
    assert "auto_export_stale" in stale.reasons


@pytest.mark.asyncio
async def test_absent_auto_export_receipt_is_unknown_without_paths() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(_providers(auto_export_directory=lambda: None))

    assert snapshot.backup.freshness == "unknown"
    assert snapshot.backup.newest_timestamp is None
    assert snapshot.backup.newest_size_bytes is None
    assert snapshot.backup.integrity == "unknown"
    assert "/" not in snapshot.backup.model_dump_json()


@pytest.mark.asyncio
async def test_provenance_aggregates_read_only_mounts_without_hashes_or_paths() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            vault_summary=lambda: [
                {
                    "status": "ready-read-only",
                    "write_policy": "read-only",
                    "root_path": "/Volumes/private-vault",
                    "source_fingerprint": "a" * 64,
                },
                {
                    "status": "ready-write-enabled",
                    "write_policy": "guarded-write",
                    "source_fingerprint": "b" * 64,
                },
            ]
        )
    )

    assert snapshot.provenance.state == "ready"
    assert snapshot.provenance.mount_count == 2
    assert snapshot.provenance.external_read_only_count == 1
    assert snapshot.provenance.source_fingerprint_state == "available"
    wire = snapshot.model_dump_json()
    assert "/Volumes/private-vault" not in wire
    assert "a" * 64 not in wire
    assert "b" * 64 not in wire


@pytest.mark.asyncio
async def test_malformed_provenance_degrades_without_raw_details() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            vault_summary=lambda: {
                "mounts": "not-a-mount-list",
                "root_path": "/private/raw",
                "source_hash": "c" * 64,
            }
        )
    )

    assert snapshot.provenance.state == "unknown"
    assert snapshot.provenance.mount_count == 0
    assert snapshot.provenance.external_read_only_count == 0
    wire = snapshot.model_dump_json()
    assert "/private/raw" not in wire
    assert "c" * 64 not in wire


@pytest.mark.asyncio
async def test_existing_backup_directory_without_exports_is_unknown(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    (tmp_path / "manual-export.txt").write_text("not an auto export", encoding="utf-8")

    snapshot = await build_runtime_snapshot(
        _providers(auto_export_directory=lambda: tmp_path)
    )

    assert snapshot.backup.state == "unknown"
    assert snapshot.backup.file_count == 0
    assert snapshot.backup.freshness == "unknown"
    assert "auto_export_unknown" in snapshot.reasons


@pytest.mark.asyncio
async def test_provenance_requires_recognized_aggregate_fields() -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    for malformed in ([{}], [{"root_path": "/private/raw"}]):
        snapshot = await build_runtime_snapshot(
            _providers(vault_summary=lambda value=malformed: value)
        )

        assert snapshot.provenance.state == "unknown"
        assert snapshot.provenance.mount_count == 0
        assert snapshot.provenance.external_read_only_count == 0
        assert "provenance_unknown" in snapshot.reasons
        assert "/private/raw" not in snapshot.model_dump_json()
