"""Race-resistant Windows deletion for files owned by the uploads tree."""

from __future__ import annotations

import sys
from pathlib import Path


class UnsafeWindowsUploadCleanupError(OSError):
    """A Windows upload cannot be deleted without following path names."""


def secure_unlink_uploaded_file_windows(
    root: Path,
    relative: Path,
) -> bool:
    """Delete one Windows upload through pinned no-reparse handles.

    Every directory component is opened without delete sharing before the
    next component is traversed. Windows therefore cannot rename or replace
    the pinned chain while the final file is validated and marked for deletion
    by handle.
    """
    import ctypes
    from ctypes import wintypes

    file_attribute_directory = 0x00000010
    file_attribute_reparse_point = 0x00000400
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    file_read_attributes = 0x00000080
    file_share_read_write = 0x00000003
    file_type_disk = 0x00000001
    delete_access = 0x00010000
    open_existing = 3
    file_disposition_info = 4

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    class _FileDispositionInformation(ctypes.Structure):
        _fields_ = (("DeleteFile", wintypes.BOOLEAN),)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    get_file_type = kernel32.GetFileType
    get_file_type.argtypes = (wintypes.HANDLE,)
    get_file_type.restype = wintypes.DWORD
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    invalid_handle = wintypes.HANDLE(-1).value
    handles: list[int] = []

    def open_pinned(
        path: Path,
        *,
        expect_directory: bool,
        allow_missing: bool = False,
    ) -> int | None:
        desired_access = file_read_attributes
        flags = file_flag_open_reparse_point
        if expect_directory:
            flags |= file_flag_backup_semantics
        else:
            desired_access |= delete_access
        handle = create_file(
            str(path),
            desired_access,
            file_share_read_write,
            None,
            open_existing,
            flags,
            None,
        )
        if handle == invalid_handle:
            error = ctypes.get_last_error()
            if allow_missing and error in {2, 3}:
                return None
            raise UnsafeWindowsUploadCleanupError(
                "upload-path-handle-open-failed"
            ) from ctypes.WinError(error)

        raw_handle = int(handle)
        handles.append(raw_handle)
        information = _ByHandleFileInformation()
        if not get_information(raw_handle, ctypes.byref(information)):
            raise UnsafeWindowsUploadCleanupError(
                "upload-path-handle-inspection-failed"
            ) from ctypes.WinError(ctypes.get_last_error())
        attributes = information.dwFileAttributes
        if attributes & file_attribute_reparse_point:
            raise UnsafeWindowsUploadCleanupError("upload-path-is-reparse-point")
        is_directory = bool(attributes & file_attribute_directory)
        if is_directory != expect_directory:
            raise UnsafeWindowsUploadCleanupError(
                "upload-parent-is-not-directory"
                if expect_directory
                else "upload-target-is-not-regular-file"
            )
        if get_file_type(raw_handle) != file_type_disk:
            raise UnsafeWindowsUploadCleanupError("upload-target-is-not-regular-file")
        return raw_handle

    try:
        anchor = root.anchor
        if not anchor:
            raise UnsafeWindowsUploadCleanupError("upload-root-has-no-anchor")
        current = Path(anchor)
        for component in (*root.parts[1:], *relative.parts[:-1]):
            if ":" in component:
                raise UnsafeWindowsUploadCleanupError("upload-path-is-not-a-file")
            current /= component
            open_pinned(current, expect_directory=True)

        name = relative.parts[-1]
        if ":" in name:
            raise UnsafeWindowsUploadCleanupError("upload-path-is-not-a-file")
        file_handle = open_pinned(
            current / name,
            expect_directory=False,
            allow_missing=True,
        )
        if file_handle is None:
            return False

        disposition = _FileDispositionInformation(True)
        if not set_information(
            file_handle,
            file_disposition_info,
            ctypes.byref(disposition),
            ctypes.sizeof(disposition),
        ):
            raise UnsafeWindowsUploadCleanupError(
                "upload-file-delete-by-handle-failed"
            ) from ctypes.WinError(ctypes.get_last_error())
        return True
    finally:
        active_exception = sys.exc_info()[0] is not None
        close_error: OSError | None = None
        for handle in reversed(handles):
            if not close_handle(handle) and close_error is None:
                close_error = ctypes.WinError(ctypes.get_last_error())
        if close_error is not None and not active_exception:
            raise UnsafeWindowsUploadCleanupError(
                "upload-path-handle-close-failed"
            ) from close_error
