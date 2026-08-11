"""v0.8.70 — tests for the in-app update notifier service."""
from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path

import pytest

from api import updates_service as svc

REAL_APP_VERSION = svc.app_version


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

def _fake_release(tag: str, *, html_url: str | None = None, assets=None):
    release_url = html_url or (
        f"https://github.com/Antman1526/Deeper-Notebook/releases/tag/{tag}"
    )
    release_assets = assets if assets is not None else [
        {
            "name": "Deeper-Notebook-mac-arm64.dmg",
            "browser_download_url": release_url + "/download",
        },
        {
            "name": "SHA256SUMS",
            "browser_download_url": release_url + "/checksums",
        },
    ]

    async def _fetch():
        return {
            "tag_name": tag,
            "html_url": release_url,
            "url": release_url,
            "published_at": "2026-06-26T00:00:00Z",
            "assets": release_assets,
        }
    return _fetch


async def test_check_reports_available_update(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_latest_release", _fake_release("v0.8.70"))
    status = await svc.check(force=True)
    assert status["current"] == "0.8.69"
    assert status["latest"] == "v0.8.70"
    assert status["update_available"] is True
    assert status["skipped"] is False
    assert status["verification"] == "verified"
    assert status["release_url"].endswith("v0.8.70")


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
    assert status["verification"] == "unknown"
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
        "cache": {
            "latest": "v0.8.70",
            "verification": "verified",
            "release_url": (
                "https://github.com/Antman1526/Deeper-Notebook/releases/tag/v0.8.70"
            ),
        },
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


def test_update_service_targets_canonical_release_repository():
    assert svc.GITHUB_OWNER == "Antman1526"
    assert svc.GITHUB_REPO == "Deeper-Notebook"
    assert (
        svc.RELEASES_LATEST_URL
        == "https://api.github.com/repos/Antman1526/Deeper-Notebook/releases/latest"
    )
    assert (
        svc.RELEASES_FALLBACK_URL
        == "https://github.com/Antman1526/Deeper-Notebook/releases/latest"
    )


def test_status_uses_canonical_release_page_when_github_payload_has_no_url():
    status = svc._status_from_state(
        {"enabled": True, "cache": {"latest": "v0.8.70"}}
    )

    assert status["verification"] == "unknown"
    assert status["html_url"] is None
    assert status["release_url"] is None


@pytest.mark.parametrize(
    "release_kwargs,expected",
    [
        (
            {"html_url": "https://github.com/other/repo/releases/tag/v0.8.70"},
            "unverified",
        ),
        ({"tag": "not-a-version"}, "unverified"),
        (
            {
                "assets": [
                    {"name": "SHA256SUMS", "browser_download_url": "https://x"}
                ]
            },
            "unverified",
        ),
        (
            {
                "assets": [
                    {
                        "name": "Deeper-Notebook-mac-arm64.dmg",
                        "browser_download_url": "https://x",
                    }
                ]
            },
            "unverified",
        ),
    ],
)
async def test_release_candidate_requires_canonical_verified_metadata(
    monkeypatch, release_kwargs, expected
):
    tag = release_kwargs.pop("tag", "v0.8.70")
    monkeypatch.setattr(svc, "_fetch_latest_release", _fake_release(tag, **release_kwargs))

    status = await svc.check(force=True)

    assert status["verification"] == expected
    assert status["update_available"] is False
    assert status["release_url"] is None
    assert status["html_url"] is None


async def test_verified_release_exposes_only_manual_public_release_url(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_latest_release", _fake_release("v0.8.70"))

    status = await svc.check(force=True)

    assert status["verification"] == "verified"
    assert status["update_available"] is True
    assert status["release_url"] == (
        "https://github.com/Antman1526/Deeper-Notebook/releases/tag/v0.8.70"
    )
    assert status["html_url"] == status["release_url"]


def test_app_version_prefers_canonical_distribution(monkeypatch):
    monkeypatch.delattr(__import__("desktop"), "__version__", raising=False)
    looked_up: list[str] = []

    def distribution_version(name: str) -> str:
        looked_up.append(name)
        if name == "deeper-notebook":
            return "1.2.3"
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", distribution_version)

    assert REAL_APP_VERSION() == "1.2.3"
    assert looked_up == ["deeper-notebook"]


def test_app_version_uses_legacy_distribution_only_as_fallback(monkeypatch):
    monkeypatch.delattr(__import__("desktop"), "__version__", raising=False)
    looked_up: list[str] = []

    def distribution_version(name: str) -> str:
        looked_up.append(name)
        if name == "open-notebook":
            return "0.8.94"
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", distribution_version)

    assert REAL_APP_VERSION() == "0.8.94"
    assert looked_up == ["deeper-notebook", "open-notebook"]
