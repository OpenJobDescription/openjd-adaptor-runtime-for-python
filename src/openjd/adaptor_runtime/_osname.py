# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import platform
from typing import Optional


class OSName(str):
    """
    OS Name Utility Class.

    Calling the constructor without any parameters will create an OSName object initialized with the
    OS python is running on (one of Linux, macOS, Windows).

    Calling the constructor with a string will result in an OSName object with the string resolved
    to one of Linux, macOS, Windows. If the string could not be resolved to an OS, then a ValueError
    will be raised.

    This class also has an override __eq__ which can be used to compare against string types for OS
    Name equality. For example OSName('Windows') == 'nt' will evaluate to True.
    """

    LINUX = "Linux"
    MACOS = "macOS"
    WINDOWS = "Windows"
    POSIX = "Posix"

    __hash__ = str.__hash__  # needed because we define __eq__

    def __init__(self, *args, **kw):
        super().__init__()

    def __new__(cls, *args, **kw):
        if len(args) > 0:
            args = (OSName.resolve_os_name(args[0]), *args[1:])
        else:
            args = (OSName._get_os_name(),)
        return str.__new__(cls, *args, **kw)

    @staticmethod
    def is_macos(name: Optional[str] = None) -> bool:
        name = OSName._get_os_name() if name is None else name
        return OSName.resolve_os_name(name) == OSName.MACOS

    @staticmethod
    def is_windows(name: Optional[str] = None) -> bool:
        name = OSName._get_os_name() if name is None else name
        return OSName.resolve_os_name(name) == OSName.WINDOWS

    @staticmethod
    def is_linux(name: Optional[str] = None) -> bool:
        name = OSName._get_os_name() if name is None else name
        return OSName.resolve_os_name(name) == OSName.LINUX

    @staticmethod
    def is_posix(name: Optional[str] = None) -> bool:
        name = OSName._get_os_name() if name is None else name
        return (
            OSName.resolve_os_name(name) == OSName.POSIX
            or OSName.is_macos(name)
            or OSName.is_linux(name)
        )

    @staticmethod
    def _get_os_name() -> str:
        return OSName.resolve_os_name(platform.system())

    @staticmethod
    def resolve_os_name(name: str) -> str:
        """
        Resolves an OS Name from an alias. In general this works as follows:
        - macOS will resolve from: {'darwin', 'macos', 'mac', 'mac os', 'os x'}
        - Windows will resolve from {'nt', 'windows'} or any string starting with 'win' like 'win32'
        - Linux will resolve from any string starting with 'linux', like 'linux' or 'linux2'
        """
        name = name.lower().strip()
        if os_name := _osname_alias_map.get(name):
            return os_name
        elif name.startswith("win"):
            return OSName.WINDOWS
        elif name.startswith("linux"):
            return OSName.LINUX
        elif name.lower() == "posix":
            return OSName.POSIX
        else:
            raise ValueError(f"The operating system '{name}' is unknown and could not be resolved.")

    def __eq__(self, __x: object) -> bool:
        return OSName.resolve_os_name(self) == OSName.resolve_os_name(str(__x))


_osname_alias_map: dict[str, str] = {
    "darwin": OSName.MACOS,
    "macos": OSName.MACOS,
    "mac": OSName.MACOS,
    "mac os": OSName.MACOS,
    "os x": OSName.MACOS,
    "nt": OSName.WINDOWS,
    "windows": OSName.WINDOWS,
    "posix": OSName.POSIX,
}
