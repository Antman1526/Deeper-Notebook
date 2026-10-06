"""v0.8.130 — "switched off" and "not yet due" are not runtime faults.

Home's Runtime status panel read "Degraded" on every default install because
an off-by-default knowledge engine and a backup the launcher had simply not
written yet were both reported as non-ready components. These tests pin the
two narrow exemptions and, just as importantly, what they must not excuse.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_runtime_snapshot import _providers

THREE_DAYS = 3 * 86_400


def _write_export(directory: Path, *, age_seconds: float) -> Path:
    export = directory / "auto-export-20260101-000000.surql"
    export.write_text("-- export\n", encoding="utf-8")
    stamp = time.time() - age_seconds
    os.utime(export, (stamp, stamp))
    return export


# --- knowledge -------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_switched_off_is_ready_and_snapshot_is_ready(
    tmp_path: Path,
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=60)
    snapshot = await build_runtime_snapshot(
        _providers(
            knowledge_summary=lambda: {"enabled": False},
            auto_export_directory=lambda: tmp_path,
        )
    )

    assert snapshot.status == "ready"
    assert snapshot.reasons == []
    assert snapshot.knowledge.state == "ready"
    assert snapshot.knowledge.projected is None
    assert snapshot.knowledge.unchanged is None
    assert snapshot.knowledge.failed is None
    assert "knowledge_unknown" not in snapshot.reasons


@pytest.mark.asyncio
async def test_knowledge_enabled_but_service_missing_is_still_unknown(
    tmp_path: Path,
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=60)
    snapshot = await build_runtime_snapshot(
        _providers(
            knowledge_summary=lambda: None,
            auto_export_directory=lambda: tmp_path,
        )
    )

    assert snapshot.knowledge.state == "unknown"
    assert "knowledge_unknown" in snapshot.reasons
    assert snapshot.status != "ready"


@pytest.mark.parametrize("enabled", [True, 0, None, "false", "False"])
def test_only_exactly_false_is_the_switched_off_sentinel(enabled) -> None:
    from api.runtime_snapshot import _normalise_knowledge

    knowledge, reasons = _normalise_knowledge({"enabled": enabled})

    assert knowledge.state == "unknown"
    assert reasons == ["knowledge_unknown"]


def test_switched_off_sentinel_carries_no_reasons() -> None:
    from api.runtime_snapshot import _normalise_knowledge

    knowledge, reasons = _normalise_knowledge({"enabled": False})

    assert knowledge.state == "ready"
    assert reasons == []


# --- backup: not yet due ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["empty", "missing", "none"])
async def test_no_export_yet_is_ready_shortly_after_start(
    tmp_path: Path, kind: str
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    directory = {
        "empty": tmp_path,
        "missing": tmp_path / "never-created",
        "none": None,
    }[kind]
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: directory,
            uptime_seconds=lambda: 60,
        )
    )

    assert snapshot.backup.state == "ready"
    assert snapshot.backup.file_count == 0
    assert snapshot.backup.freshness == "unknown"
    assert "auto_export_unknown" not in snapshot.reasons
    assert snapshot.status == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize("uptime", [1800, 1800.0, 5000, None])
async def test_no_export_after_grace_or_without_uptime_is_unknown(
    tmp_path: Path, uptime
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            uptime_seconds=lambda: uptime,
        )
    )

    assert snapshot.backup.state == "unknown"
    assert snapshot.backup.file_count == 0
    assert "auto_export_unknown" in snapshot.reasons
    assert snapshot.status == "degraded"


@pytest.mark.asyncio
async def test_last_second_of_grace_still_counts(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            uptime_seconds=lambda: 1799.9,
        )
    )

    assert snapshot.backup.state == "ready"


@pytest.mark.asyncio
async def test_stale_export_is_ready_shortly_after_start_but_stays_stale(
    tmp_path: Path,
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=THREE_DAYS)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            uptime_seconds=lambda: 60,
        )
    )

    assert snapshot.backup.state == "ready"
    # The detailed backup panel must keep telling the truth about the file.
    assert snapshot.backup.freshness == "stale"
    assert snapshot.backup.file_count == 1
    assert snapshot.backup.newest_age_seconds >= THREE_DAYS - 5
    assert snapshot.backup.newest_timestamp is not None
    assert "auto_export_stale" not in snapshot.reasons
    assert snapshot.status == "ready"


@pytest.mark.asyncio
async def test_stale_export_long_after_start_is_degraded(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=THREE_DAYS)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            uptime_seconds=lambda: 5000,
        )
    )

    assert snapshot.backup.state == "degraded"
    assert snapshot.backup.freshness == "stale"
    assert "auto_export_stale" in snapshot.reasons
    assert snapshot.status == "degraded"


# --- backup: anomalies are never excused -----------------------------------


@pytest.mark.asyncio
async def test_future_dated_export_is_not_excused_by_grace(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=-86_400)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            uptime_seconds=lambda: 60,
        )
    )

    assert snapshot.backup.state == "unknown"
    assert "auto_export_unknown" in snapshot.reasons


def test_oversized_newest_export_is_not_excused_by_grace(
    tmp_path: Path, monkeypatch
) -> None:
    from api import runtime_snapshot

    _write_export(tmp_path, age_seconds=60)
    monkeypatch.setattr(runtime_snapshot, "_MAX_AUTO_EXPORT_SIZE_BYTES", 1)

    backup, reasons = runtime_snapshot._normalise_backup(tmp_path, uptime_seconds=60)

    assert backup.state == "unknown"
    assert reasons == ["auto_export_unknown"]


def test_unexpected_scan_failure_is_not_excused_by_grace() -> None:
    from api.runtime_snapshot import _normalise_backup

    # Not path-like at all: Path() raises inside the guarded block.
    backup, reasons = _normalise_backup(object(), uptime_seconds=60)

    assert backup.state == "unknown"
    assert reasons == ["auto_export_unknown"]


# --- uptime provider hygiene -----------------------------------------------


def _raise() -> float:
    raise RuntimeError("clock unavailable at /private/secret")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [
        _raise,
        lambda: float("nan"),
        lambda: float("inf"),
        lambda: -5,
        lambda: "60",
        lambda: True,
    ],
    ids=["raises", "nan", "inf", "negative", "string", "bool"],
)
async def test_unusable_uptime_grants_no_grace(tmp_path: Path, provider) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(auto_export_directory=lambda: tmp_path, uptime_seconds=provider)
    )

    assert snapshot.backup.state == "unknown"
    assert "auto_export_unknown" in snapshot.reasons
    assert "/private/secret" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_no_uptime_provider_keeps_previous_behaviour(tmp_path: Path) -> None:
    from api.runtime_snapshot import _normalise_backup, build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(auto_export_directory=lambda: tmp_path)
    )
    assert snapshot.backup.state == "unknown"
    assert "auto_export_unknown" in snapshot.reasons

    backup, reasons = _normalise_backup(tmp_path)
    assert backup.state == "unknown"
    assert reasons == ["auto_export_unknown"]


# --- router ----------------------------------------------------------------


def _request(**state):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


@pytest.mark.asyncio
async def test_router_reports_switched_off_engine_as_sentinel(monkeypatch) -> None:
    from api.routers import runtime

    seen: list[str] = []

    def flag_off(name: str) -> bool:
        seen.append(name)
        return False

    monkeypatch.setattr(runtime, "enabled_setting", flag_off)

    assert await runtime._knowledge_summary(_request()) == {"enabled": False}
    assert seen == ["DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED"]


@pytest.mark.asyncio
async def test_router_default_configuration_is_switched_off(unset_setting) -> None:
    from api.routers import runtime

    unset_setting("DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED")

    assert await runtime._knowledge_summary(_request()) == {"enabled": False}


@pytest.mark.asyncio
async def test_router_flag_on_without_service_is_still_none(monkeypatch) -> None:
    from api.routers import runtime

    monkeypatch.setattr(runtime, "enabled_setting", lambda name: True)

    assert await runtime._knowledge_summary(_request()) is None


@pytest.mark.asyncio
async def test_router_unreadable_flag_is_not_treated_as_off(monkeypatch) -> None:
    from api.routers import runtime

    def invalid(name: str) -> bool:
        raise ValueError("invalid knowledge engine boolean setting")

    monkeypatch.setattr(runtime, "enabled_setting", invalid)

    assert await runtime._knowledge_summary(_request()) is None


@pytest.mark.asyncio
async def test_router_running_engine_ignores_the_flag(monkeypatch) -> None:
    from api.routers import runtime

    def must_not_read(name: str) -> bool:
        raise AssertionError("flag must not be consulted when a service exists")

    monkeypatch.setattr(runtime, "enabled_setting", must_not_read)

    class Service:
        async def status(self):
            return {"projected": 4, "unchanged": 1, "failed": 0}

    summary = await runtime._knowledge_summary(
        _request(knowledge_engine_service=Service())
    )

    assert summary == {"projected": 4, "unchanged": 1, "failed": 0}


def test_router_supplies_process_uptime_by_default() -> None:
    from api.routers import runtime

    providers = runtime._providers_for_request(_request())
    uptime = providers.uptime_seconds()

    assert isinstance(uptime, float)
    assert 0 <= uptime < 86_400


def test_router_uptime_provider_can_be_overridden() -> None:
    from api.routers import runtime

    providers = runtime._providers_for_request(
        _request(runtime_uptime_seconds_provider=lambda: 4242.0)
    )

    assert providers.uptime_seconds() == 4242.0


# --- backup: nobody is scheduled to take one -------------------------------
# v0.8.130 — only the desktop launcher takes exports. A deployment without
# it, or one that switched exports off, is not failing to back up.


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["empty", "missing", "none"])
async def test_no_export_is_ready_when_exports_are_not_expected(
    tmp_path: Path, kind: str
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    directory = {
        "empty": tmp_path,
        "missing": tmp_path / "never-created",
        "none": None,
    }[kind]
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: directory,
            auto_export_expected=lambda: False,
        )
    )

    assert snapshot.backup.state == "ready"
    assert snapshot.backup.file_count == 0
    assert snapshot.backup.freshness == "unknown"
    assert "auto_export_unknown" not in snapshot.reasons
    assert snapshot.status == "ready"


@pytest.mark.asyncio
async def test_stale_export_is_ready_but_stays_stale_when_not_expected(
    tmp_path: Path,
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=THREE_DAYS)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            auto_export_expected=lambda: False,
            # Long past the startup grace: only "not expected" can excuse it.
            uptime_seconds=lambda: 500_000,
        )
    )

    assert snapshot.backup.state == "ready"
    assert snapshot.backup.freshness == "stale"
    assert snapshot.backup.file_count == 1
    assert snapshot.backup.newest_age_seconds >= THREE_DAYS - 5
    assert "auto_export_stale" not in snapshot.reasons
    assert snapshot.status == "ready"


@pytest.mark.asyncio
async def test_future_dated_export_is_not_excused_when_not_expected(
    tmp_path: Path,
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=-86_400)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            auto_export_expected=lambda: False,
        )
    )

    assert snapshot.backup.state == "unknown"
    assert "auto_export_unknown" in snapshot.reasons


def test_other_anomalies_are_not_excused_when_not_expected(
    tmp_path: Path, monkeypatch
) -> None:
    from api import runtime_snapshot

    not_a_directory = tmp_path / "onp-backups"
    not_a_directory.write_text("a file where the directory should be")
    backup, reasons = runtime_snapshot._normalise_backup(
        not_a_directory, auto_export_expected=False
    )
    assert (backup.state, reasons) == ("unknown", ["auto_export_unknown"])

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    backup, reasons = runtime_snapshot._normalise_backup(
        link, auto_export_expected=False
    )
    assert (backup.state, reasons) == ("unknown", ["auto_export_unknown"])

    backup, reasons = runtime_snapshot._normalise_backup(
        object(), auto_export_expected=False
    )
    assert (backup.state, reasons) == ("unknown", ["auto_export_unknown"])

    _write_export(real, age_seconds=60)
    monkeypatch.setattr(runtime_snapshot, "_MAX_AUTO_EXPORT_SIZE_BYTES", 1)
    backup, reasons = runtime_snapshot._normalise_backup(
        real, auto_export_expected=False
    )
    assert (backup.state, reasons) == ("unknown", ["auto_export_unknown"])


def _raise_expected() -> bool:
    raise RuntimeError("environment unreadable at /private/secret")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [lambda: True, lambda: None, _raise_expected, lambda: 0, lambda: "false"],
    ids=["true", "none", "raises", "zero", "string"],
)
async def test_only_exactly_false_means_exports_are_not_expected(
    tmp_path: Path, provider
) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            auto_export_expected=provider,
        )
    )

    assert snapshot.backup.state == "unknown"
    assert "auto_export_unknown" in snapshot.reasons
    assert "/private/secret" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_expected_exports_still_get_the_startup_grace(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            auto_export_expected=lambda: True,
            uptime_seconds=lambda: 60,
        )
    )

    assert snapshot.backup.state == "ready"


@pytest.mark.asyncio
async def test_expected_stale_export_after_grace_is_degraded(tmp_path: Path) -> None:
    from api.runtime_snapshot import build_runtime_snapshot

    _write_export(tmp_path, age_seconds=THREE_DAYS)
    snapshot = await build_runtime_snapshot(
        _providers(
            auto_export_directory=lambda: tmp_path,
            auto_export_expected=lambda: True,
            uptime_seconds=lambda: 5000,
        )
    )

    assert snapshot.backup.state == "degraded"
    assert "auto_export_stale" in snapshot.reasons


_EXPORT_SETTINGS = (
    "DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL",
    "DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR",
    "DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS",
)


def test_router_does_not_expect_exports_without_the_launcher(unset_setting) -> None:
    from api.routers import runtime

    unset_setting(*_EXPORT_SETTINGS)

    assert runtime._auto_export_expected() is False
    assert runtime._providers_for_request(_request()).auto_export_expected() is False


@pytest.mark.parametrize("control_url", ["http://127.0.0.1:50000", ""])
def test_router_expects_exports_under_the_launcher(
    unset_setting, monkeypatch, control_url: str
) -> None:
    from api.routers import runtime

    unset_setting(*_EXPORT_SETTINGS)
    # The launcher always sets this key for its children; it is empty when
    # the control server failed to start, but exports still run then.
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", control_url)

    assert runtime._auto_export_expected() is True


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR", "1", False),
        ("DEEPER_NOTEBOOK_DISABLE_DB_AUTOREPAIR", "", True),
        ("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "0", False),
        ("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "-1", False),
        ("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "12", True),
        # The launcher falls back to 24h for an unparsable or empty value.
        ("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "daily", True),
        ("DEEPER_NOTEBOOK_AUTO_EXPORT_HOURS", "", True),
    ],
)
def test_router_mirrors_the_launcher_export_switches(
    unset_setting, monkeypatch, name: str, value: str, expected: bool
) -> None:
    from api.routers import runtime

    unset_setting(*_EXPORT_SETTINGS)
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", "http://127.0.0.1:1")
    monkeypatch.setenv(name, value)

    assert runtime._auto_export_expected() is expected


def test_router_auto_export_expected_can_be_overridden() -> None:
    from api.routers import runtime

    providers = runtime._providers_for_request(
        _request(runtime_auto_export_expected_provider=lambda: True)
    )

    assert providers.auto_export_expected() is True
