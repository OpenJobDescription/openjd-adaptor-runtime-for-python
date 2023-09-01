# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from typing import IO, TYPE_CHECKING, Generator

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
        file (StrOrBytesPath): The path to the file to open
        mode (str): The string mode for opening the file. A combination of r, w, a, x, +
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
    if flags != 0:  # not O_RDONLY
        os_open_kwargs["mode"] = stat.S_IWUSR | stat.S_IRUSR | mask

    fd = os.open(**os_open_kwargs)  # type: ignore

    open_kwargs = {}
    if encoding is not None:
        open_kwargs["encoding"] = encoding
    if newline is not None:
        open_kwargs["newline"] = newline
    with open(fd, open_mode, **open_kwargs) as f:  # type: ignore
        yield f


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
