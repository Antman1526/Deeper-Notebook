"""Read-only, redacted runtime state for the desktop reliability surface.

The snapshot deliberately accepts providers rather than reaching into mutable
services.  The production defaults only read existing health, receipt, update,
vault, knowledge, and bounded auto-export metadata; tests can inject pure
providers without starting a database, watcher, model process, or update
request.
"""

from __future__ import annotations

import inspect
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from desktop.data_root import active_data_root as _active_data_root

SnapshotState = Literal["ready", "degraded", "unknown"]
DatabaseState = Literal["online", "offline", "unknown"]
MigrationState = Literal["applied", "pending", "unknown"]

# This is intentionally finite.  Values from health checks, providers, and
# persisted state are never copied into the wire contract as free-form errors.
ReasonCode = Literal[
    "readiness_unknown",
    "database_offline",
    "database_check_failed",
    "migrations_pending",
    "migrations_check_failed",
    "vault_degraded",
    "vault_unavailable",
    "vault_unknown",
    "knowledge_degraded",
    "knowledge_unknown",
    "startup_receipt_unavailable",
    "startup_receipt_invalid",
    "updates_disabled",
    "updates_unknown",
    "auto_export_unknown",
    "auto_export_stale",
    "provenance_unknown",
]

ALLOWED_REASON_CODES = frozenset(ReasonCode.__args__)
_ALLOWED_STAGES = frozenset(
    {
        "launcher_start",
        "chat_model_cache_hit",
        "chat_model_scan",
        "core_ready",
    }
)
_VERSION_RE = re.compile(
    r"^v?[0-9]+(?:\.[0-9]+){0,4}(?:[-+][A-Za-z0-9.-]{1,16})?$"
)
_MAX_AUTO_EXPORT_ENTRIES = 64
_MAX_AUTO_EXPORT_SCAN_ENTRIES = 256
_MAX_AUTO_EXPORT_SIZE_BYTES = 4_294_967_296
_STARTUP_RECEIPT_FILENAME = "startup_receipt.json"
_MAX_STARTUP_RECEIPT_BYTES = 64 * 1024
_MAX_COUNT = 1_000_000
_MAX_RUNTIME_REASONS = 15
AUTO_EXPORT_STALE_AFTER_SECONDS = 172_800
_KNOWN_VAULT_STATES = frozenset(
    {
        "disconnected",
        "scanning",
        "ready-read-only",
        "ready-write-enabled",
        "stale",
        "conflict",
        "degraded",
        "unavailable",
    }
)
_KNOWN_WRITE_POLICIES = frozenset({"read-only", "guarded-write"})


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadinessSnapshot(_Contract):
    state: SnapshotState
    database: DatabaseState
    migrations: MigrationState


class StartupStage(_Contract):
    stage: Literal[
        "launcher_start",
        "chat_model_cache_hit",
        "chat_model_scan",
        "core_ready",
    ]
    elapsed_ms: int = Field(ge=0, le=86_400_000)


class StartupSnapshot(_Contract):
    state: SnapshotState
    stages: list[StartupStage] = Field(default_factory=list)


class UpdateSnapshot(_Contract):
    state: SnapshotState
    enabled: bool | None = None
    update_available: bool | None = None
    current_version: str | None = None


class VaultSnapshot(_Contract):
    state: SnapshotState
    ready: int = Field(ge=0, le=_MAX_COUNT)
    degraded: int = Field(ge=0, le=_MAX_COUNT)
    unavailable: int = Field(ge=0, le=_MAX_COUNT)


class KnowledgeSnapshot(_Contract):
    state: SnapshotState
    projected: int | None = Field(default=None, ge=0, le=_MAX_COUNT)
    unchanged: int | None = Field(default=None, ge=0, le=_MAX_COUNT)
    failed: int | None = Field(default=None, ge=0, le=_MAX_COUNT)


class AutoExportSnapshot(_Contract):
    state: SnapshotState
    freshness: Literal["valid", "stale", "unknown"] = "unknown"
    integrity: Literal["verified", "unknown"] = "unknown"
    file_count: int = Field(ge=0, le=_MAX_AUTO_EXPORT_ENTRIES)
    newest_age_seconds: int | None = Field(default=None, ge=0, le=31_536_000_000)
    newest_size_bytes: int | None = Field(default=None, ge=0, le=_MAX_AUTO_EXPORT_SIZE_BYTES)
    newest_timestamp: str | None = Field(default=None, min_length=1, max_length=40)


class ProvenanceSnapshot(_Contract):
    state: SnapshotState
    mount_count: int = Field(ge=0, le=_MAX_COUNT)
    external_read_only_count: int = Field(ge=0, le=_MAX_COUNT)
    source_fingerprint_state: Literal["available", "unknown"] = "unknown"


class RuntimeSnapshot(_Contract):
    """Stable, content-free runtime snapshot returned by the API."""

    schema_version: Literal["runtime-snapshot-v1"] = "runtime-snapshot-v1"
    status: SnapshotState
    reasons: list[ReasonCode] = Field(default_factory=list, max_length=_MAX_RUNTIME_REASONS)
    readiness: ReadinessSnapshot
    startup: StartupSnapshot
    updates: UpdateSnapshot
    vault: VaultSnapshot
    knowledge: KnowledgeSnapshot
    backup: AutoExportSnapshot
    provenance: ProvenanceSnapshot


Provider = Callable[[], Any] | Callable[[], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RuntimeSnapshotProviders:
    """Read-only seams used by the builder and deterministic API tests."""

    readiness: Provider | None = None
    active_data_root: Callable[[], Path] = _active_data_root
    startup_receipts: Provider | None = None
    update_status: Provider | None = None
    vault_summary: Provider | None = None
    knowledge_summary: Provider | None = None
    auto_export_directory: Provider | None = None
    provenance_summary: Provider | None = None


async def _invoke(provider: Provider | None) -> Any:
    if provider is None:
        return None
    try:
        value = provider()
        if inspect.isawaitable(value):
            return await value
        return value
    except Exception:
        # Provider details are deliberately not exposed to callers.
        return None


async def default_readiness_provider() -> Mapping[str, Any]:
    """Read database/migration health without invoking repair or mutation."""

    database = "unknown"
    database_check_failed = False
    try:
        from api.routers.config import check_database_health

        health = await check_database_health()
        candidate = health.get("status") if isinstance(health, Mapping) else None
        if candidate in {"online", "offline"}:
            database = candidate
        else:
            database_check_failed = True
    except Exception:
        database_check_failed = True

    migrations = "unknown"
    migrations_check_failed = False
    try:
        from deeper_notebook.database import async_migrate

        pending = await async_migrate.AsyncMigrationManager().needs_migration()
        if isinstance(pending, bool):
            migrations = "pending" if pending else "applied"
        else:
            migrations_check_failed = True
    except Exception:
        migrations_check_failed = True

    return {
        "database": database,
        "migrations": migrations,
        "database_check_failed": database_check_failed,
        "migrations_check_failed": migrations_check_failed,
    }


def _default_startup_receipts(root_provider: Callable[[], Path]) -> Mapping[str, Any] | None:
    try:
        root = Path(root_provider()).expanduser()
    except Exception:
        return None

    try:
        from desktop.startup_receipts import StartupReceiptStore

        # StartupReceiptStore._read is a bounded, fail-closed read API.  Do
        # not use record/load methods here: they mutate the receipt or model.
        return StartupReceiptStore(root)._read()
    except (ImportError, ModuleNotFoundError):
        # The packaged API runs from the frozen upstream tree, which does not
        # contain the desktop launcher package.  Keep the API read-only and
        # project only the bounded receipt fields it already normalizes.
        receipt_path = root / _STARTUP_RECEIPT_FILENAME
        try:
            if (
                receipt_path.is_symlink()
                or not receipt_path.is_file()
                or receipt_path.stat().st_size > _MAX_STARTUP_RECEIPT_BYTES
            ):
                return None
            parsed = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, Mapping) or parsed.get("schema_version") != 1:
                return None
            stages = parsed.get("stages")
            if not isinstance(stages, list) or len(stages) > 16:
                return None
            return {"schema_version": 1, "stages": stages}
        except (OSError, TypeError, ValueError):
            return None
    except Exception:
        return None


def _default_update_status() -> Mapping[str, Any] | None:
    try:
        from api import updates_service

        # Both helpers only read the local update state.  In particular, do
        # not call updates_service.check(), which may contact the network and
        # persist a refreshed state file.
        return updates_service._status_from_state(updates_service._read_state())
    except Exception:
        return None


def default_auto_export_directory() -> Path:
    from desktop.paths import user_home

    return user_home() / "onp-backups"


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _bounded_items(value: Sequence[Any], limit: int):
    """Yield at most ``limit`` values without requesting the next one."""

    iterator = iter(value)
    for _ in range(limit):
        try:
            yield next(iterator)
        except StopIteration:
            return


def _safe_version(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 32 or not _VERSION_RE.fullmatch(value):
        return None
    return value


def _normalise_readiness(value: Any) -> tuple[ReadinessSnapshot, list[ReasonCode]]:
    try:
        raw = _as_mapping(value)
        if raw is None:
            raise TypeError("readiness provider did not return a mapping")
        nested = _as_mapping(raw.get("checks"))
        checks = nested if nested is not None else raw
        database = checks.get("database")
        if database not in {"online", "offline"}:
            database = "unknown"
        migration_value = checks.get("migrations")
        if migration_value not in {"applied", "pending", "unknown"}:
            pending = checks.get("migrations_pending")
            migration_value = (
                "pending" if pending is True else "applied" if pending is False else "unknown"
            )
        migrations: MigrationState = migration_value

        reasons: list[ReasonCode] = []
        if checks.get("database_check_failed") is True:
            reasons.append("database_check_failed")
        if checks.get("migrations_check_failed") is True:
            reasons.append("migrations_check_failed")
        if database == "offline":
            reasons.append("database_offline")
        if migrations == "pending":
            reasons.append("migrations_pending")
        if database == "unknown" or migrations == "unknown":
            reasons.append("readiness_unknown")
        if database == "online" and migrations == "applied":
            state: SnapshotState = "ready"
        elif database == "unknown" or migrations == "unknown":
            state = "unknown"
        else:
            state = "degraded"
        return ReadinessSnapshot(state=state, database=database, migrations=migrations), reasons
    except Exception:
        return (
            ReadinessSnapshot(state="unknown", database="unknown", migrations="unknown"),
            ["readiness_unknown"],
        )


def _normalise_startup(value: Any) -> tuple[StartupSnapshot, list[ReasonCode]]:
    try:
        raw = _as_mapping(value)
        if raw is None:
            return StartupSnapshot(state="unknown"), ["startup_receipt_unavailable"]
        stages_raw = raw.get("stages")
        if not isinstance(stages_raw, Sequence) or isinstance(stages_raw, (str, bytes)):
            return StartupSnapshot(state="unknown"), ["startup_receipt_invalid"]
        stages: list[StartupStage] = []
        saw_item = False
        for item in _bounded_items(stages_raw, 16):
            saw_item = True
            entry = _as_mapping(item)
            stage = entry.get("stage") if entry else None
            elapsed = entry.get("elapsed_ms") if entry else None
            if (
                stage not in _ALLOWED_STAGES
                or not isinstance(elapsed, int)
                or isinstance(elapsed, bool)
            ):
                continue
            if 0 <= elapsed <= 86_400_000:
                stages.append(StartupStage(stage=stage, elapsed_ms=elapsed))
        if saw_item and not stages:
            return StartupSnapshot(state="unknown"), ["startup_receipt_invalid"]
        return StartupSnapshot(state="ready", stages=stages), []
    except Exception:
        return StartupSnapshot(state="unknown"), ["startup_receipt_invalid"]


def _normalise_updates(value: Any) -> tuple[UpdateSnapshot, list[ReasonCode]]:
    try:
        raw = _as_mapping(value)
        if raw is None:
            return UpdateSnapshot(state="unknown"), ["updates_unknown"]
        enabled = raw.get("enabled")
        enabled_value = enabled if isinstance(enabled, bool) else None
        available = raw.get("update_available")
        available_value = available if isinstance(available, bool) else None
        current = _safe_version(raw.get("current"))
        if enabled_value is None and available_value is None and current is None:
            return UpdateSnapshot(state="unknown"), ["updates_unknown"]
        reasons: list[ReasonCode] = []
        if enabled_value is False:
            reasons.append("updates_disabled")
        return (
            UpdateSnapshot(
                state="ready",
                enabled=enabled_value,
                update_available=available_value,
                current_version=current,
            ),
            reasons,
        )
    except Exception:
        return UpdateSnapshot(state="unknown"), ["updates_unknown"]


def _normalise_vault(value: Any) -> tuple[VaultSnapshot, list[ReasonCode]]:
    try:
        raw = value.get("mounts") if isinstance(value, Mapping) else value
        if raw is None:
            return VaultSnapshot(state="unknown", ready=0, degraded=0, unavailable=0), ["vault_unknown"]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return VaultSnapshot(state="unknown", ready=0, degraded=0, unavailable=0), ["vault_unknown"]
        ready = degraded = unavailable = 0
        saw_item = False
        # A mounted-source summary is normally tiny, but this boundary must
        # also tolerate a bad adapter result without doing unbounded work or
        # violating the response model's count cap.
        for item in _bounded_items(raw, _MAX_COUNT):
            saw_item = True
            entry = _as_mapping(item)
            status = entry.get("status") if entry else None
            if status in {"ready-read-only", "ready-write-enabled"}:
                ready += 1
            elif status in {"scanning", "stale", "conflict", "degraded"}:
                degraded += 1
            elif status in {"disconnected", "unavailable"}:
                unavailable += 1
        if saw_item and not (ready or degraded or unavailable):
            return VaultSnapshot(state="unknown", ready=0, degraded=0, unavailable=0), ["vault_unknown"]
        reasons: list[ReasonCode] = []
        if degraded:
            reasons.append("vault_degraded")
        if unavailable:
            reasons.append("vault_unavailable")
        state: SnapshotState = "degraded" if (degraded or unavailable) else "ready"
        return VaultSnapshot(state=state, ready=ready, degraded=degraded, unavailable=unavailable), reasons
    except Exception:
        return VaultSnapshot(state="unknown", ready=0, degraded=0, unavailable=0), ["vault_unknown"]


def _bounded_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_COUNT:
        return value
    return None


def _normalise_knowledge(value: Any) -> tuple[KnowledgeSnapshot, list[ReasonCode]]:
    try:
        raw = _as_mapping(value)
        if raw is None:
            return KnowledgeSnapshot(state="unknown"), ["knowledge_unknown"]
        projected = _bounded_count(raw.get("projected"))
        unchanged = _bounded_count(raw.get("unchanged"))
        failed = _bounded_count(raw.get("failed"))
        if projected is None and unchanged is None and failed is None:
            return KnowledgeSnapshot(state="unknown"), ["knowledge_unknown"]
        if failed and failed > 0:
            return (
                KnowledgeSnapshot(
                    state="degraded", projected=projected, unchanged=unchanged, failed=failed
                ),
                ["knowledge_degraded"],
            )
        return (
            KnowledgeSnapshot(
                state="ready", projected=projected, unchanged=unchanged, failed=failed
            ),
            [],
        )
    except Exception:
        return KnowledgeSnapshot(state="unknown"), ["knowledge_unknown"]


def _normalise_backup(value: Any) -> tuple[AutoExportSnapshot, list[ReasonCode]]:
    if value is None:
        return (
            AutoExportSnapshot(state="unknown", file_count=0),
            ["auto_export_unknown"],
        )
    try:
        directory = Path(value).expanduser()
        if directory.is_symlink() or not directory.is_dir():
            raise OSError("not a directory")
        count = 0
        newest_mtime: float | None = None
        newest_size: int | None = None
        for seen, entry in enumerate(directory.iterdir()):
            if seen >= _MAX_AUTO_EXPORT_SCAN_ENTRIES or count >= _MAX_AUTO_EXPORT_ENTRIES:
                break
            try:
                if (
                    entry.is_symlink()
                    or not entry.is_file()
                    or not entry.name.startswith("auto-export-")
                    or entry.suffix != ".surql"
                ):
                    continue
                metadata = entry.stat()
                mtime = metadata.st_mtime
                size = metadata.st_size
                if (
                    not isinstance(mtime, (int, float))
                    or not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 0
                ):
                    continue
            except (OSError, ValueError, TypeError):
                continue
            count += 1
            if newest_mtime is None or mtime > newest_mtime:
                newest_mtime = float(mtime)
                newest_size = size
        if newest_mtime is None:
            return (
                AutoExportSnapshot(state="unknown", file_count=count),
                ["auto_export_unknown"],
            )

        age_raw = time.time() - newest_mtime
        if age_raw < 0:
            return (
                AutoExportSnapshot(
                    state="unknown",
                    file_count=count,
                    newest_size_bytes=(
                        newest_size
                        if newest_size is not None and newest_size <= _MAX_AUTO_EXPORT_SIZE_BYTES
                        else None
                    ),
                ),
                ["auto_export_unknown"],
            )
        newest_age = min(int(age_raw), 31_536_000_000)
        newest_timestamp = datetime.fromtimestamp(
            newest_mtime, tz=timezone.utc
        ).isoformat()
        if newest_size is None or newest_size > _MAX_AUTO_EXPORT_SIZE_BYTES:
            return (
                AutoExportSnapshot(
                    state="unknown",
                    file_count=count,
                    newest_age_seconds=newest_age,
                    newest_timestamp=newest_timestamp,
                ),
                ["auto_export_unknown"],
            )
        freshness: Literal["valid", "stale", "unknown"] = (
            "valid" if newest_age <= AUTO_EXPORT_STALE_AFTER_SECONDS else "stale"
        )
        state: SnapshotState = "ready" if freshness == "valid" else "degraded"
        reasons: list[ReasonCode] = (
            [] if freshness == "valid" else ["auto_export_stale"]
        )
        return (
            AutoExportSnapshot(
                state=state,
                freshness=freshness,
                integrity="unknown",
                file_count=count,
                newest_age_seconds=newest_age,
                newest_size_bytes=newest_size,
                newest_timestamp=newest_timestamp,
            ),
            reasons,
        )
    except Exception:
        return AutoExportSnapshot(state="unknown", file_count=0), ["auto_export_unknown"]


_SOURCE_FINGERPRINT_RE = re.compile(r"^[a-f0-9]{64}$")


def _normalise_provenance(value: Any) -> tuple[ProvenanceSnapshot, list[ReasonCode]]:
    try:
        raw = value.get("mounts") if isinstance(value, Mapping) else value
        if raw is None or not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise TypeError("provenance mounts are not a bounded sequence")
        mount_count = 0
        external_read_only_count = 0
        fingerprints_available = False
        saw_item = False
        recognized_item = False
        for item in _bounded_items(raw, _MAX_COUNT):
            saw_item = True
            entry = _as_mapping(item)
            if entry is None:
                continue
            status = entry.get("status")
            write_policy = entry.get("write_policy")
            if status not in _KNOWN_VAULT_STATES and write_policy not in _KNOWN_WRITE_POLICIES:
                continue
            recognized_item = True
            mount_count += 1
            if write_policy == "read-only" or status == "ready-read-only":
                external_read_only_count += 1
            fingerprint = (
                entry.get("source_fingerprint")
                or entry.get("source_hash")
                or entry.get("content_hash")
            )
            if isinstance(fingerprint, str) and _SOURCE_FINGERPRINT_RE.fullmatch(fingerprint):
                fingerprints_available = True
        if saw_item and not recognized_item:
            raise TypeError("provenance mount entries are invalid")
        return (
            ProvenanceSnapshot(
                state="ready",
                mount_count=mount_count,
                external_read_only_count=external_read_only_count,
                source_fingerprint_state=(
                    "available" if fingerprints_available else "unknown"
                ),
            ),
            [],
        )
    except Exception:
        return (
            ProvenanceSnapshot(
                state="unknown",
                mount_count=0,
                external_read_only_count=0,
            ),
            ["provenance_unknown"],
        )


def _aggregate_status(
    readiness: ReadinessSnapshot,
    components: Sequence[SnapshotState],
) -> SnapshotState:
    if readiness.state == "unknown":
        return "unknown"
    if readiness.state == "degraded" or any(state != "ready" for state in components):
        return "degraded"
    return "ready"


async def build_runtime_snapshot(
    providers: RuntimeSnapshotProviders | None = None,
) -> RuntimeSnapshot:
    """Compose a redacted snapshot from read-only provider results."""

    configured = providers or RuntimeSnapshotProviders()
    readiness_raw = await _invoke(configured.readiness or default_readiness_provider)
    startup_provider = configured.startup_receipts
    startup_raw = await _invoke(startup_provider)
    if startup_provider is None:
        startup_raw = _default_startup_receipts(configured.active_data_root)
    updates_raw = await _invoke(configured.update_status or _default_update_status)
    vault_raw = await _invoke(configured.vault_summary)
    knowledge_raw = await _invoke(configured.knowledge_summary)
    backup_raw = await _invoke(configured.auto_export_directory or default_auto_export_directory)

    readiness, reasons = _normalise_readiness(readiness_raw)
    startup, startup_reasons = _normalise_startup(startup_raw)
    updates, update_reasons = _normalise_updates(updates_raw)
    vault, vault_reasons = _normalise_vault(vault_raw)
    knowledge, knowledge_reasons = _normalise_knowledge(knowledge_raw)
    backup, backup_reasons = _normalise_backup(backup_raw)
    provenance_raw = await _invoke(configured.provenance_summary)
    if configured.provenance_summary is None:
        provenance_raw = vault_raw
    provenance, provenance_reasons = _normalise_provenance(provenance_raw)
    for code in (
        *startup_reasons,
        *update_reasons,
        *vault_reasons,
        *knowledge_reasons,
        *backup_reasons,
        *provenance_reasons,
    ):
        if code in ALLOWED_REASON_CODES and code not in reasons:
            reasons.append(code)

    reasons = reasons[:_MAX_RUNTIME_REASONS]

    status = _aggregate_status(
        readiness,
        [
            startup.state,
            updates.state,
            vault.state,
            knowledge.state,
            backup.state,
            provenance.state,
        ],
    )
    return RuntimeSnapshot(
        status=status,
        reasons=reasons,
        readiness=readiness,
        startup=startup,
        updates=updates,
        vault=vault,
        knowledge=knowledge,
        backup=backup,
        provenance=provenance,
    )


__all__ = [
    "ALLOWED_REASON_CODES",
    "AutoExportSnapshot",
    "KnowledgeSnapshot",
    "ProvenanceSnapshot",
    "ReadinessSnapshot",
    "RuntimeSnapshot",
    "RuntimeSnapshotProviders",
    "StartupSnapshot",
    "UpdateSnapshot",
    "VaultSnapshot",
    "build_runtime_snapshot",
    "default_auto_export_directory",
    "default_readiness_provider",
]
