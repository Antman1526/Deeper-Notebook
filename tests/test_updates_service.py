"""v0.8.70 — tests for the in-app update notifier service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import updates_service as svc


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Redirect the state file into a tmp dir and pin a known app version."""
    state_file = tmp_path / "update_state.json"
    monkeypatch.setattr(svc, "_state_path", lambda: state_file)
    monkeypatch.setattr(svc, "app_version", lambda: "0.8.69")
    return state_file


# --- version parsing -------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("v0.8.70", (0, 8, 70)),
        ("0.8.70", (0, 8, 70)),
        ("V1.0", (1, 0)),
        ("0.8.70-rc1", (0, 8, 70)),
        ("0.8.70+build5", (0, 8, 70)),
        ("garbage", (0,)),
        ("", (0,)),
        (None, (0,)),
    ],
)
def test_parse_version(raw, expected):
    assert svc._parse_version(raw) == expected


@pytest.mark.parametrize(
    "latest,current,newer",
    [
        ("0.8.70", "0.8.69", True),
        ("v0.8.70", "0.8.69", True),
        ("0.8.69", "0.8.69", False),
        ("0.8.68", "0.8.69", False),
        ("0.9.0", "0.8.69", True),
        ("1.0.0", "0.8.69", True),
        (None, "0.8.69", False),
        ("", "0.8.69", False),
    ],
)
def test_is_newer(latest, current, newer):
    assert svc._is_newer(latest, current) is newer


# --- check() with a fake GitHub response ----------------------------------

def _fake_release(tag: str):
    async def _fetch():
        return {
            "tag_name": tag,
            "html_url": f"https://example.test/releases/{tag}",
            "published_at": "2026-06-26T00:00:00Z",
        }
    return _fetch


async def test_check_reports_available_update(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_latest_release", _fake_release("v0.8.70"))
    status = await svc.check(force=True)
    assert status["current"] == "0.8.69"
    assert status["latest"] == "v0.8.70"
    assert status["update_available"] is True
    assert status["skipped"] is False
    assert status["html_url"].endswith("v0.8.70")


async def test_check_no_update_when_same_version(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_latest_release", _fake_release("0.8.69"))
    status = await svc.check(force=True)
    assert status["update_available"] is False


async def test_check_network_failure_is_safe(monkeypatch):
    async def _boom():
        return None  # service maps every failure mode to None
    monkeypatch.setattr(svc, "_fetch_latest_release", _boom)
    status = await svc.check(force=True)
    assert status["update_available"] is False
    assert status["latest"] is None
    # last_check is still stamped so we back off rather than hammering GitHub.
    assert status["last_check"] is not None


async def test_disabled_skips_network(monkeypatch, _isolated_state):
    called = {"n": 0}

    async def _tracked():
        called["n"] += 1
        return {"tag_name": "v0.8.70"}

    monkeypatch.setattr(svc, "_fetch_latest_release", _tracked)
    svc.set_enabled(False)
    status = await svc.check(force=True)
    assert called["n"] == 0  # no network call when disabled
    assert status["enabled"] is False
    assert status["update_available"] is False


async def test_cache_avoids_second_network_call(monkeypatch):
    called = {"n": 0}

    async def _tracked():
        called["n"] += 1
        return {"tag_name": "v0.8.70", "html_url": "https://x", "published_at": "p"}

    monkeypatch.setattr(svc, "_fetch_latest_release", _tracked)
    await svc.check(force=True)          # hits network
    await svc.check(force=False)         # within TTL → cached
    assert called["n"] == 1


def test_skip_version_marks_skipped(_isolated_state):
    # Seed a cached "available" state, then skip it.
    svc._write_state({
        "enabled": True,
        "cache": {"latest": "v0.8.70", "html_url": "https://x"},
        "last_check": "2026-06-26T00:00:00+00:00",
    })
    status = svc.skip_version("v0.8.70")
    assert status["skipped_version"] == "v0.8.70"
    assert status["update_available"] is True
    assert status["skipped"] is True  # banner should now hide this version


def test_corrupt_state_file_is_tolerated(_isolated_state):
    _isolated_state.write_text("{ not json", encoding="utf-8")
    assert svc.is_enabled() is True  # defaults, no crash


def test_set_enabled_persists(_isolated_state):
    svc.set_enabled(False)
    on_disk = json.loads(Path(_isolated_state).read_text())
    assert on_disk["enabled"] is False
    assert svc.is_enabled() is False
