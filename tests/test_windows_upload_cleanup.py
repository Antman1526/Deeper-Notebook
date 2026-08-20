from __future__ import annotations

import ctypes
from pathlib import Path

import pytest

from deeper_notebook.domain import windows_upload_cleanup


class _FakeWindowsCall:
    def __init__(self, callback):
        self.callback = callback
        self.calls: list[tuple[object, ...]] = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


def _fake_windows_upload_kernel(*, reparse_handle: int | None = None):
    handles = iter((101, 102, 103, 104))
    create_file = _FakeWindowsCall(lambda *_args: next(handles))

    def populate_information(handle, information_pointer):
        information = information_pointer._obj
        information.dwFileAttributes = (
            0x00000400
            if handle == reparse_handle
            else (0 if handle == 104 else 0x00000010)
        )
        return 1

    get_information = _FakeWindowsCall(populate_information)
    get_file_type = _FakeWindowsCall(lambda _handle: 0x00000001)
    set_information = _FakeWindowsCall(lambda *_args: 1)
    close_handle = _FakeWindowsCall(lambda _handle: 1)
    kernel = type(
        "FakeKernel32",
        (),
        {
            "CreateFileW": create_file,
            "GetFileInformationByHandle": get_information,
            "GetFileType": get_file_type,
            "SetFileInformationByHandle": set_information,
            "CloseHandle": close_handle,
        },
    )()
    return (
        kernel,
        create_file,
        set_information,
        close_handle,
    )


def test_windows_upload_cleanup_pins_chain_and_deletes_by_handle(monkeypatch):
    kernel, create_file, set_information, close_handle = _fake_windows_upload_kernel()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel,
        raising=False,
    )

    deleted = windows_upload_cleanup.secure_unlink_uploaded_file_windows(
        Path("/safe/uploads"),
        Path("nested/upload.txt"),
    )

    assert deleted is True
    assert len(create_file.calls) == 4
    for call in create_file.calls:
        assert call[2] == 0x00000003  # read/write sharing; no delete share
        assert call[5] & 0x00200000  # OPEN_REPARSE_POINT
    assert all(call[1] & 0x00010000 == 0 for call in create_file.calls[:-1])
    assert create_file.calls[-1][1] & 0x00010000  # DELETE access
    assert len(set_information.calls) == 1
    assert set_information.calls[0][1] == 4  # FileDispositionInfo
    assert set_information.calls[0][2]._obj.DeleteFile == 1
    assert [call[0] for call in close_handle.calls] == [104, 103, 102, 101]


def test_windows_upload_cleanup_refuses_reparse_component(monkeypatch):
    kernel, _create_file, set_information, close_handle = _fake_windows_upload_kernel(
        reparse_handle=102
    )
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel,
        raising=False,
    )

    with pytest.raises(
        windows_upload_cleanup.UnsafeWindowsUploadCleanupError,
        match="upload-path-is-reparse-point",
    ):
        windows_upload_cleanup.secure_unlink_uploaded_file_windows(
            Path("/safe/uploads"),
            Path("nested/upload.txt"),
        )

    assert set_information.calls == []
    assert [call[0] for call in close_handle.calls] == [102, 101]
