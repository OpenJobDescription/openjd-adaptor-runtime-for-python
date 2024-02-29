# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import abc
import os
import stat
import tempfile

from .._osname import OSName
from .exceptions import (
    UnsupportedPlatformException,
    NonvalidSocketPathException,
    NoSocketPathFoundException,
)

# Max PID on 64-bit systems is 4194304 (2^22)
_PID_MAX_LENGTH = 7
_PID_MAX_LENGTH_PADDED = _PID_MAX_LENGTH + 1  # 1 char for path seperator


class SocketDirectories(abc.ABC):
    """
    Base class for determining the base directory for sockets used in the Adaptor Runtime.
    """

    @staticmethod
    def for_os(osname: OSName = OSName()):  # pragma: no cover
        """_summary_

        Args:
            osname (OSName, optional): The OS to get socket directories for.
                Defaults to the current OS.

        Raises:
            UnsupportedPlatformException: Raised when this class is requested for an unsupported
                platform.
        """
        klass = _get_socket_directories_cls(osname)
        if not klass:
            raise UnsupportedPlatformException(osname)
        return klass()

    def get_process_socket_path(self, namespace: str | None = None, *, create_dir: bool = False):
        """
        Gets the path for this process' socket in the given namespace.

        Args:
            namespace (Optional[str]): The optional namespace (subdirectory) where the sockets go.
            create_dir (bool): Whether to create the socket directory. Default is false.

        Raises:
            NonvalidSocketPathException: Raised if the user has configured a socket base directory
                that is nonvalid
            NoSocketPathFoundException: Raised if no valid socket path could be found. This will
                not be raised if the user has configured a socket base directory.
        """
        socket_name = str(os.getpid())
        assert (
            len(socket_name) <= _PID_MAX_LENGTH
        ), f"PID too long. Only PIDs up to {_PID_MAX_LENGTH} digits are supported."

        return os.path.join(self.get_socket_dir(namespace, create=create_dir), socket_name)

    def get_socket_dir(self, namespace: str | None = None, *, create: bool = False) -> str:
        """
        Gets the base directory for sockets used in Adaptor IPC

        Args:
            namespace (Optional[str]): The optional namespace (subdirectory) where the sockets go
            create (bool): Whether to create the directory or not. Default is false.

        Raises:
            NonvalidSocketPathException: Raised if the user has configured a socket base directory
                that is nonvalid
            NoSocketPathFoundException: Raised if no valid socket path could be found. This will
                not be raised if the user has configured a socket base directory.
        """

        def create_dir(path: str) -> str:
            if create:
                os.makedirs(path, mode=0o700, exist_ok=True)
            return path

        rel_path = os.path.join(".openjd", "adaptors", "sockets")
        if namespace:
            rel_path = os.path.join(rel_path, namespace)

        reasons: list[str] = []

        # First try home directory
        home_dir = os.path.expanduser("~")
        socket_dir = os.path.join(home_dir, rel_path)
        try:
            self.verify_socket_path(socket_dir)
        except NonvalidSocketPathException as e:
            reasons.append(f"Cannot create sockets directory in the home directory because: {e}")
        else:
            return create_dir(socket_dir)

        # Last resort is the temp directory
        temp_dir = tempfile.gettempdir()
        socket_dir = os.path.join(temp_dir, rel_path)
        try:
            self.verify_socket_path(socket_dir)
        except NonvalidSocketPathException as e:
            reasons.append(f"Cannot create sockets directory in the temp directory because: {e}")
        else:
            # Also check that the sticky bit is set on the temp dir
            if not os.stat(temp_dir).st_mode & stat.S_ISVTX:
                reasons.append(
                    f"Cannot use temporary directory {temp_dir} because it does not have the "
                    "sticky bit (restricted deletion flag) set"
                )
            else:
                return create_dir(socket_dir)

        raise NoSocketPathFoundException(
            "Failed to find a suitable base directory to create sockets in for the following "
            f"reasons: {os.linesep.join(reasons)}"
        )

    @abc.abstractmethod
    def verify_socket_path(self, path: str) -> None:  # pragma: no cover
        """
        Verifies a socket path is valid.

        Raises:
            NonvalidSocketPathException: Subclasses will raise this exception if the socket path
                is not valid.
        """
        pass


class LinuxSocketDirectories(SocketDirectories):
    """
    Specialization for socket paths in Linux systems.
    """

    # This is based on the max length of socket names to 108 bytes
    # See unix(7) under "Address format"
    _socket_path_max_length = 108
    _socket_dir_max_length = _socket_path_max_length - _PID_MAX_LENGTH_PADDED

    def verify_socket_path(self, path: str) -> None:
        path_length = len(path.encode("utf-8"))
        if path_length > self._socket_dir_max_length:
            raise NonvalidSocketPathException(
                "Socket base directory path too big. The maximum allowed size is "
                f"{self._socket_dir_max_length} bytes, but the directory has a size of "
                f"{path_length}: {path}"
            )


class MacOSSocketDirectories(SocketDirectories):
    """
    Specialization for socket paths in macOS systems.
    """

    # This is based on the max length of socket names to 104 bytes
    # See https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/un.h#L79
    _socket_path_max_length = 104
    _socket_dir_max_length = _socket_path_max_length - _PID_MAX_LENGTH_PADDED

    def verify_socket_path(self, path: str) -> None:
        path_length = len(path.encode("utf-8"))
        if path_length > self._socket_dir_max_length:
            raise NonvalidSocketPathException(
                "Socket base directory path too big. The maximum allowed size is "
                f"{self._socket_dir_max_length} bytes, but the directory has a size of "
                f"{path_length}: {path}"
            )


_os_map: dict[str, type[SocketDirectories]] = {
    OSName.LINUX: LinuxSocketDirectories,
    OSName.MACOS: MacOSSocketDirectories,
}


def _get_socket_directories_cls(
    osname: OSName,
) -> type[SocketDirectories] | None:  # pragma: no cover
    return _os_map.get(osname, None)
