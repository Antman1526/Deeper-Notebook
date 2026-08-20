from __future__ import annotations

import ctypes
import errno
import sys
from pathlib import Path

import pytest

from desktop import data_root


class _FakeNativeCall:
    def __init__(self, result: int):
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


@pytest.mark.parametrize(
    ("platform", "implementation_name"),
    [
        ("darwin", "_rename_macos_no_replace"),
        ("linux", "_rename_linux_no_replace"),
        ("win32", "_rename_windows_no_replace"),
    ],
)
def test_atomic_rename_dispatches_to_platform_primitive(
    tmp_path, monkeypatch, platform, implementation_name
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    calls: list[tuple[Path, Path]] = []

    def implementation(actual_source, actual_destination):
        calls.append((Path(actual_source), Path(actual_destination)))

    monkeypatch.setattr(data_root.sys, "platform", platform)
    monkeypatch.setattr(data_root, implementation_name, implementation)

    data_root._rename_directory_no_replace(source, destination)

    assert calls == [(source, destination)]


def test_atomic_rename_fails_closed_on_unsupported_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(data_root.sys, "platform", "freebsd")

    with pytest.raises(data_root._AtomicRenameUnavailable):
        data_root._rename_directory_no_replace(
            tmp_path / "source", tmp_path / "destination"
        )


def test_macos_rename_uses_renamex_np_exclusive_flag(tmp_path, monkeypatch):
    native_call = _FakeNativeCall(0)
    fake_libc = type("FakeLibc", (), {"renamex_np": native_call})()
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_libc)

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    data_root._rename_macos_no_replace(source, destination)

    assert native_call.calls == [(bytes(source), bytes(destination), 0x00000004)]


def test_linux_rename_uses_renameat2_noreplace_flag(tmp_path, monkeypatch):
    native_call = _FakeNativeCall(0)
    fake_libc = type("FakeLibc", (), {"renameat2": native_call})()
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_libc)

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    data_root._rename_linux_no_replace(source, destination)

    assert native_call.calls == [
        (-100, bytes(source), -100, bytes(destination), 0x00000001)
    ]


def test_windows_rename_uses_movefileex_without_replace_flag(tmp_path, monkeypatch):
    native_call = _FakeNativeCall(1)
    fake_kernel32 = type("FakeKernel32", (), {"MoveFileExW": native_call})()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: fake_kernel32,
        raising=False,
    )

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    data_root._rename_windows_no_replace(source, destination)

    assert native_call.calls == [(str(source), str(destination), 0x00000008)]


@pytest.mark.parametrize(
    ("platform", "native_error"),
    [
        ("darwin", errno.EEXIST),
        ("linux", errno.ENOTEMPTY),
        ("win32", 183),
    ],
)
def test_native_destination_exists_maps_to_file_exists(
    tmp_path, monkeypatch, platform, native_error
):
    native_call = _FakeNativeCall(0 if platform == "win32" else -1)
    if platform == "darwin":
        fake_library = type("FakeLibc", (), {"renamex_np": native_call})()
        monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_library)
        monkeypatch.setattr(ctypes, "get_errno", lambda: native_error)
        operation = data_root._rename_macos_no_replace
    elif platform == "linux":
        fake_library = type("FakeLibc", (), {"renameat2": native_call})()
        monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: fake_library)
        monkeypatch.setattr(ctypes, "get_errno", lambda: native_error)
        operation = data_root._rename_linux_no_replace
    else:
        fake_library = type("FakeKernel32", (), {"MoveFileExW": native_call})()
        monkeypatch.setattr(
            ctypes,
            "WinDLL",
            lambda *_args, **_kwargs: fake_library,
            raising=False,
        )
        monkeypatch.setattr(
            ctypes, "get_last_error", lambda: native_error, raising=False
        )
        operation = data_root._rename_windows_no_replace

    with pytest.raises(FileExistsError):
        operation(tmp_path / "source", tmp_path / "destination")


@pytest.mark.parametrize(
    ("platform", "attribute"),
    [
        ("darwin", "renamex_np"),
        ("linux", "renameat2"),
    ],
)
def test_missing_posix_native_symbol_fails_closed(
    tmp_path, monkeypatch, platform, attribute
):
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: object())
    operation = (
        data_root._rename_macos_no_replace
        if platform == "darwin"
        else data_root._rename_linux_no_replace
    )

    with pytest.raises(data_root._AtomicRenameUnavailable, match=attribute):
        operation(tmp_path / "source", tmp_path / "destination")


@pytest.mark.skipif(
    sys.platform not in {"darwin", "linux"},
    reason="live proof requires a POSIX no-replace primitive",
)
def test_live_posix_directory_rename_never_replaces_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "source-marker").write_text("source")

    data_root._rename_directory_no_replace(source, destination)

    assert not source.exists()
    assert (destination / "source-marker").read_text() == "source"

    racing_source = tmp_path / "racing-source"
    racing_destination = tmp_path / "racing-destination"
    racing_source.mkdir()
    racing_destination.mkdir()
    (racing_source / "source-marker").write_text("source")
    (racing_destination / "destination-marker").write_text("destination")

    with pytest.raises(FileExistsError):
        data_root._rename_directory_no_replace(racing_source, racing_destination)

    assert (racing_source / "source-marker").read_text() == "source"
    assert (racing_destination / "destination-marker").read_text() == "destination"
