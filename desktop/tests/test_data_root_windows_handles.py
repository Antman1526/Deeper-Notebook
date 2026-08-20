from __future__ import annotations

import ctypes
import os
import sys
from types import SimpleNamespace

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


def test_windows_owned_directory_uses_held_handle_for_path_operations(
    tmp_path, monkeypatch
):
    handles = iter((101, 102))
    closed: list[int] = []
    hardened = []
    monkeypatch.setattr(data_root.sys, "platform", "win32")
    monkeypatch.setattr(
        data_root,
        "_open_windows_directory_handle",
        lambda _path: next(handles),
    )
    monkeypatch.setattr(data_root, "_close_windows_handle", closed.append)

    def create_owned(path, _reason):
        path.mkdir()
        return True

    monkeypatch.setattr(
        data_root,
        "_create_windows_owned_directory",
        create_owned,
    )
    monkeypatch.setattr(
        data_root, "_windows_path_is_reparse_point", lambda _path: False
    )
    monkeypatch.setattr(
        data_root,
        "_harden_windows_owned_directory",
        lambda path, reason: hardened.append((path, reason)),
    )
    monkeypatch.setattr(
        data_root,
        "_open_windows_append_file",
        lambda path: os.open(
            path,
            os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        ),
    )
    monkeypatch.setattr(data_root, "_fsync_directory", lambda _path: None)

    owned = tmp_path / "owned"
    with data_root.open_owned_directory(owned) as directory:
        assert directory.windows_handle == 102
        data_root.atomic_replace_json(directory, "receipt.json", {"status": "started"})
        data_root.append_recovery_log(directory, "launcher.log", b"failure\n")
        data_root.unlink_owned_file(directory, "receipt.json")

        assert not (owned / "receipt.json").exists()
        assert (owned / "launcher.log").read_bytes() == b"failure\n"

    assert closed == [102, 101]
    assert hardened == [(owned, "owned-directory-not-owned")]


def test_windows_private_directory_creation_sets_owner_and_protected_acl(
    tmp_path, monkeypatch
):
    convert = _FakeNativeCall(1)
    create = _FakeNativeCall(1)
    local_free = _FakeNativeCall(0)
    advapi32 = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=convert,
    )
    kernel32 = SimpleNamespace(
        CreateDirectoryW=create,
        LocalFree=local_free,
    )
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **_kwargs: advapi32 if name == "advapi32" else kernel32,
        raising=False,
    )
    monkeypatch.setattr(
        data_root,
        "_windows_current_user_sid",
        lambda: "S-1-5-21-1000",
    )

    assert data_root._create_windows_owned_directory(
        tmp_path / "owned",
        "owned-directory-not-owned",
    )

    sddl = convert.calls[0][0]
    assert sddl.startswith("O:S-1-5-21-1000D:P")
    assert "(A;OICI;FA;;;S-1-5-21-1000)" in sddl
    assert create.calls[0][0] == str(tmp_path / "owned")
    assert create.calls[0][1] is not None
    assert len(local_free.calls) == 1


def test_windows_directory_flush_requests_write_access(tmp_path, monkeypatch):
    create = _FakeNativeCall(123)
    flush = _FakeNativeCall(1)
    close = _FakeNativeCall(1)
    kernel32 = type(
        "FakeKernel32",
        (),
        {
            "CreateFileW": create,
            "FlushFileBuffers": flush,
            "CloseHandle": close,
        },
    )()
    monkeypatch.setattr(data_root.sys, "platform", "win32")
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel32,
        raising=False,
    )

    data_root._fsync_directory(tmp_path)

    assert create.calls[0][1] == 0x40000000
    assert flush.calls == [(123,)]
    assert close.calls == [(123,)]


def test_windows_directory_handle_closes_when_reparse_query_fails(
    tmp_path, monkeypatch
):
    create = _FakeNativeCall(201)
    kernel32 = SimpleNamespace(CreateFileW=create)
    closed: list[int] = []
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel32,
        raising=False,
    )
    monkeypatch.setattr(
        data_root,
        "_windows_path_is_reparse_point",
        lambda _path: (_ for _ in ()).throw(OSError("probe failed")),
    )
    monkeypatch.setattr(data_root, "_close_windows_handle", closed.append)

    with pytest.raises(OSError, match="probe failed"):
        data_root._open_windows_directory_handle(tmp_path)

    assert closed == [201]


def test_windows_append_handle_closes_when_reparse_query_fails(tmp_path, monkeypatch):
    create = _FakeNativeCall(202)
    kernel32 = SimpleNamespace(CreateFileW=create)
    closed: list[int] = []
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel32,
        raising=False,
    )
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(
            open_osfhandle=lambda *_args: pytest.fail(
                "descriptor transfer must not run after a failed query"
            )
        ),
    )
    monkeypatch.setattr(
        data_root,
        "_windows_path_is_reparse_point",
        lambda _path: (_ for _ in ()).throw(OSError("probe failed")),
    )
    monkeypatch.setattr(data_root, "_close_windows_handle", closed.append)

    with pytest.raises(OSError, match="probe failed"):
        data_root._open_windows_append_file(tmp_path / "launcher.log")

    desired_access = create.calls[0][1]
    assert desired_access & 0x00000004  # FILE_APPEND_DATA
    assert desired_access & 0x00120089 == 0x00120089  # FILE_GENERIC_READ
    assert desired_access & 0x00000002 == 0  # no FILE_WRITE_DATA
    assert closed == [202]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="live Windows handle and ACL proof",
)
def test_live_windows_owned_directory_hardens_acl_and_appends_safely(tmp_path):
    owned = tmp_path / "owned"

    with data_root.open_owned_directory(owned) as directory:
        assert (
            data_root._windows_path_owner_sid(owned)
            == data_root._windows_current_user_sid()
        )
        data_root.append_recovery_log(
            directory,
            "launcher.log",
            b"first-native-windows\n",
        )
        data_root.append_recovery_log(
            directory,
            "launcher.log",
            b"second-native-windows\n",
        )

    assert (owned / "launcher.log").read_bytes() == (
        b"first-native-windows\nsecond-native-windows\n"
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="live Windows reparse-point proof",
)
def test_live_windows_append_refuses_file_reparse_point(tmp_path):
    owned = tmp_path / "owned"
    target = tmp_path / "outside.log"
    target.write_text("sentinel\n", encoding="utf-8")

    with data_root.open_owned_directory(owned) as directory:
        link = owned / "launcher.log"
        link.symlink_to(target)
        with pytest.raises(
            data_root._CriticalPathError,
            match="recovery-log-file-unsafe",
        ):
            data_root.append_recovery_log(
                directory,
                "launcher.log",
                b"must-not-follow\n",
            )

    assert target.read_text(encoding="utf-8") == "sentinel\n"
