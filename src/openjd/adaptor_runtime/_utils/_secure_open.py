# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import stat
import os
from contextlib import contextmanager
from typing import IO, TYPE_CHECKING, Generator
from .._osname import OSName

if OSName.is_windows():
    import ntsecuritycon as con
    import win32security
    import win32con

from openjd.adaptor_runtime._osname import OSName

if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath


@contextmanager
def secure_open(
    path: "StrOrBytesPath",
    open_mode: str,
    encoding: str | None = None,
    newline: str | None = None,
    mask: int = 0,
) -> Generator[IO, None, None]:
    """
    Opens a file with the following behavior:
        The OS-level open flags are inferred from the open mode (A combination of r, w, a, x, +)
        If the open_mode involves writing to the file, then the following permissions are set:
            OWNER read/write bit-wise OR'd with the mask argument provided
        If the open_mode only involves reading the file, the permissions are not changed.
    Args:
        path (StrOrBytesPath): The path to the file to open
        open_mode (str): The string mode for opening the file. A combination of r, w, a, x, +
        encoding (str, optional): The encoding of the file to open. Defaults to None.
        newline (str, optional): The newline character to use. Defaults to None.
        mask (int, optional): Additional masks to apply to the opened file. Defaults to 0.

    Raises:
        ValueError: If the open mode is not valid

    Returns:
        Generator: A generator that yields the opened file
    """
    flags = _get_flags_from_mode_str(open_mode)
    os_open_kwargs = {
        "path": path,
        "flags": _get_flags_from_mode_str(open_mode),
    }
    # not O_RDONLY
    if flags != 0 and OSName.is_posix():  # pragma: is-windows
        os_open_kwargs["mode"] = stat.S_IWUSR | stat.S_IRUSR | mask

    fd = os.open(**os_open_kwargs)  # type: ignore

    # not O_RDONLY. Use ACL to set the permission for the file owner.
    if flags != 0 and OSName.is_windows():  # pragma: is-posix
        if mask != 0:
            raise NotImplementedError("Additional masks are not supported in Windows.")
        set_file_permissions_in_windows(path)
    open_kwargs = {}
    if encoding is not None:
        open_kwargs["encoding"] = encoding
    if newline is not None:
        open_kwargs["newline"] = newline
    with open(fd, open_mode, **open_kwargs) as f:  # type: ignore
        yield f


def get_file_owner_in_windows(filepath: "StrOrBytesPath") -> str:  # pragma: is-posix
    """
    Retrieves the owner of the specified file in Windows OS.

    Args:
        filepath (StrOrBytesPath): The path to the file whose owner needs to be determined.

    Returns:
        str: A string in the format 'DOMAIN\\Username' representing the file's owner.
    """
    sd = win32security.GetFileSecurity(str(filepath), win32security.OWNER_SECURITY_INFORMATION)
    owner_sid = sd.GetSecurityDescriptorOwner()
    name, domain, _ = win32security.LookupAccountSid(None, owner_sid)
    return f"{domain}\\{name}"


def set_file_permissions_in_windows(filepath: "StrOrBytesPath") -> None:  # pragma: is-posix
    """
    Sets read, write and delete permissions for the owner of the specified file.

    Note: This function sets permissions only for the owner of the file and
    does not consider existing DACLs.

    Args:
        filepath (StrOrBytesPath): The path to the file for which permissions are to be set.
    """
    user_name = get_file_owner_in_windows(filepath)
    user_sid = win32security.LookupAccountName("", user_name)[0]

    dacl = win32security.ACL()

    # Add read, write and delete permissions
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_GENERIC_READ, user_sid)
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_GENERIC_WRITE, user_sid)
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.DELETE, user_sid)

    # Apply the DACL to the file
    sd = win32security.GetFileSecurity(str(filepath), win32security.DACL_SECURITY_INFORMATION)
    sd.SetSecurityDescriptorDacl(
        1,  # A flag that indicates the presence of a DACL in the security descriptor.
        dacl,  # An ACL structure that specifies the DACL for the security descriptor.
        0,  # Don't retrieve the default DACL
    )
    win32security.SetFileSecurity(str(filepath), win32security.DACL_SECURITY_INFORMATION, sd)


def _get_flags_from_mode_str(open_mode: str) -> int:
    flags = 0
    for char in open_mode:
        if char == "r":
            flags |= os.O_RDONLY
        elif char == "w":
            flags |= os.O_WRONLY | os.O_TRUNC | os.O_CREAT
        elif char == "a":
            flags |= os.O_WRONLY | os.O_APPEND | os.O_CREAT
        elif char == "x":
            flags |= os.O_EXCL | os.O_CREAT | os.O_WRONLY
        elif char == "+":
            flags |= os.O_RDWR | os.O_CREAT
        else:
            raise ValueError(f"Nonvalid mode: '{open_mode}'")
    return flags
