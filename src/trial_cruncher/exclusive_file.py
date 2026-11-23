"""Create a new file without following an existing destination link."""

import os
import sys
from pathlib import Path
from typing import IO


def open_exclusive(path: Path, *, binary: bool) -> IO:
    """Use Windows CREATE_NEW so even a dangling reparse point blocks creation."""
    if sys.platform != "win32":
        return path.open("xb") if binary else path.open("x", encoding="utf-8", newline="")

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    generic_write = 0x40000000
    create_new = 1
    normal_file = 0x00000080
    open_reparse_point = 0x00200000
    error_file_exists = 80
    error_already_exists = 183
    # CREATE_NEW atomically rejects existing entries; OPEN_REPARSE_POINT avoids
    # traversing a link at the final path component.
    handle = create(
        str(path), generic_write, 0, None, create_new, normal_file | open_reparse_point, None
    )
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error in (error_file_exists, error_already_exists):
            raise FileExistsError(error, "Destination already exists", str(path))
        raise ctypes.WinError(error)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    try:
        return os.fdopen(fd, "wb") if binary else os.fdopen(fd, "w", encoding="utf-8", newline="")
    except BaseException:
        os.close(fd)
        raise
