"""Tests for the deterministic package-smoke fixture authority."""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.build.package_smoke_fixture import (
    MODEL_PLACEHOLDERS,
    SmokeFixture,
    prepare_smoke_fixture,
)
from desktop.config import load_or_create


def test_prepare_smoke_fixture_is_private_offline_and_mode_exact(
    tmp_path: Path,
) -> None:
    uv_cache_dir = tmp_path / "uv"
    default = prepare_smoke_fixture(
        tmp_path / "default", source_visuals=True, uv_cache_dir=uv_cache_dir
    )
    off = prepare_smoke_fixture(
        tmp_path / "off", source_visuals=False, uv_cache_dir=uv_cache_dir
    )

    assert isinstance(default, SmokeFixture)
    assert load_or_create(default.data_dir / "config.toml").provider == "none"
    assert load_or_create(default.data_dir / "config.toml").default_model == ""
    assert load_or_create(default.data_dir / "config.toml").theme == (
        "gemini-forward-light"
    )
    assert load_or_create(default.data_dir / "config.toml").execution_policy == (
        "strict_local"
    )
    assert load_or_create(default.data_dir / "config.toml").openchronicle_choice == (
        "skip"
    )
    assert default.environment["HOME"] == str(default.home)
    assert default.environment["DEEPER_NOTEBOOK_DATA_DIR"] == str(default.data_dir)
    assert default.environment["UV_CACHE_DIR"] == str(uv_cache_dir)
    assert default.environment["UV_OFFLINE"] == "1"
    assert default.environment["OPENCHRONICLE_MCP_URL"] == "http://[::1]:1/mcp"
    assert default.environment["OPENCHRONICLE_MCP_URL"] != ("http://127.0.0.1:8742/mcp")
    assert default.readiness_file == (
        default.data_dir / "logs" / "desktop-readiness.json"
    )
    assert default.readiness_file.parent.is_dir()
    assert "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED" not in default.environment
    assert off.environment["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED"] == "0"

    default_config = load_or_create(default.data_dir / "config.toml")
    off_config = load_or_create(off.data_dir / "config.toml")
    assert default_config.surreal_password != off_config.surreal_password
    assert default_config.encryption_key != off_config.encryption_key

    if os.name == "posix":
        assert stat.S_IMODE(default.root.stat().st_mode) == 0o700
        assert stat.S_IMODE(default.home.stat().st_mode) == 0o700
        assert stat.S_IMODE(default.data_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((default.data_dir / "config.toml").stat().st_mode) == 0o600


def test_ipv6_placeholder_fails_closed_before_openchronicle_post(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from desktop import app as app_mod

    fixture = prepare_smoke_fixture(
        tmp_path / "fixture", source_visuals=True, uv_cache_dir=tmp_path / "uv"
    )
    observed: dict[str, object] = {}

    class GuardedSocket:
        def __init__(self, family: int, socket_type: int, *_args, **_kwargs):
            observed["family"] = family
            observed["socket_type"] = socket_type
            assert family == socket.AF_INET

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, timeout: float) -> None:
            observed["timeout"] = timeout

        def connect(self, address: tuple[str, int]) -> None:
            observed["address"] = address
            raise OSError("AF_INET cannot connect to an IPv6 literal")

    post_calls: list[tuple[object, dict[str, object]]] = []

    def forbidden_post(url: object, **kwargs: object) -> None:
        post_calls.append((url, kwargs))

    monkeypatch.setenv(
        "OPENCHRONICLE_MCP_URL", fixture.environment["OPENCHRONICLE_MCP_URL"]
    )
    monkeypatch.setattr(socket, "socket", GuardedSocket)
    monkeypatch.setattr("httpx.post", forbidden_post)
    ctx = SimpleNamespace(
        cfg=SimpleNamespace(openchronicle_choice="skip"),
        openchronicle_available=True,
        progress_bus=None,
        log_dir=None,
    )

    app_mod._phase_detect_openchronicle(ctx)

    assert ctx.openchronicle_available is False
    assert observed == {
        "family": socket.AF_INET,
        "socket_type": socket.SOCK_STREAM,
        "timeout": 0.3,
        "address": ("::1", 1),
    }
    assert post_calls == []


def test_prepare_smoke_fixture_requires_a_new_root(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    sentinel = root / "sentinel"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError):
        prepare_smoke_fixture(root, source_visuals=True, uv_cache_dir=tmp_path / "uv")

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(root.iterdir()) == [sentinel]


def test_prepare_smoke_fixture_rejects_a_symlink_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(FileExistsError):
        prepare_smoke_fixture(link, source_visuals=True, uv_cache_dir=tmp_path / "uv")

    assert not (target / "config.toml").exists()


def test_prepare_smoke_fixture_rejects_a_dangling_symlink_root(
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing-target"
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(FileExistsError):
        prepare_smoke_fixture(link, source_visuals=True, uv_cache_dir=tmp_path / "uv")

    assert not target.exists()


def test_prepare_smoke_fixture_rejects_a_symlinked_ancestor_before_creation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="symlink"):
        prepare_smoke_fixture(
            link / "fixture", source_visuals=True, uv_cache_dir=tmp_path / "uv"
        )

    assert not target.exists()


def test_prepare_smoke_fixture_creates_size_valid_model_placeholders(
    tmp_path: Path,
) -> None:
    fixture = prepare_smoke_fixture(
        tmp_path / "fixture", source_visuals=True, uv_cache_dir=tmp_path / "uv"
    )

    for relative_path, minimum_size in MODEL_PLACEHOLDERS.items():
        placeholder = fixture.model_dir / relative_path
        assert placeholder.is_file()
        assert placeholder.stat().st_size == minimum_size
        assert fixture.model_dir in placeholder.parents


def test_prepare_smoke_fixture_rejects_escaping_model_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "desktop.build.package_smoke_fixture.MODEL_PLACEHOLDERS",
        {Path("../../../../outside.bin"): 1},
    )

    with pytest.raises(ValueError, match="inside the smoke fixture root"):
        prepare_smoke_fixture(
            tmp_path / "fixture", source_visuals=True, uv_cache_dir=tmp_path / "uv"
        )

    assert not (tmp_path / "outside.bin").exists()
