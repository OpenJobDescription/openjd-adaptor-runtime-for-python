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


class SocketPaths(abc.ABC):
    """
    Base class for determining the paths for sockets used in the Adaptor Runtime.
    """

    @staticmethod
    def for_os(osname: OSName = OSName()):  # pragma: no cover
        """
        Gets the SocketPaths class for a specific OS.

        Args:
            osname (OSName, optional): The OS to get socket paths for.
                Defaults to the current OS.

        Raises:
            UnsupportedPlatformException: Raised when this class is requested for an unsupported
                platform.
        """
        klass = _get_socket_paths_cls(osname)
        if not klass:
            raise UnsupportedPlatformException(osname)
        return klass()

    def get_process_socket_path(
        self,
        namespace: str | None = None,
        *,
        base_dir: str | None = None,
        create_dir: bool = False,
    ):
        """
        Gets the path for this process' socket in the given namespace.

        Args:
            namespace (Optional[str]): The optional namespace (subdirectory) where the sockets go.
            base_dir (Optional[str]): The base directory to create sockets in. Defaults to the temp directory.
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

        return self.get_socket_path(
            socket_name,
            namespace,
            base_dir=base_dir,
            create_dir=create_dir,
        )

    def get_socket_path(
        self,
        base_socket_name: str,
        namespace: str | None = None,
        *,
        base_dir: str | None = None,
        create_dir: bool = False,
    ) -> str:
        """
        Gets the path for a socket used in Adaptor IPC

        Args:
            base_socket_name (str): The name of the socket
            namespace (Optional[str]): The optional namespace (subdirectory) where the sockets go
            base_dir (Optional[str]): The base directory to create sockets in. Defaults to the temp directory.
            create_dir (bool): Whether to create the directory or not. Default is false.

        Raises:
            NonvalidSocketPathException: Raised if the user has configured a socket base directory
                that is nonvalid
            NoSocketPathFoundException: Raised if no valid socket path could be found. This will
                not be raised if the user has configured a socket base directory.
        """

        def mkdir(path: str) -> str:
            if create_dir:
                os.makedirs(path, mode=0o700, exist_ok=True)
            return path

        def gen_socket_path(dir: str, base_name: str):
            name = base_name
            i = 0
            while os.path.exists(os.path.join(dir, name)):
                i += 1
                name = f"{base_name}_{i}"
            return os.path.join(dir, name)

        if not base_dir:
            socket_dir = os.path.realpath(tempfile.gettempdir())
        else:
            socket_dir = os.path.realpath(base_dir)

        if namespace:
            socket_dir = os.path.join(socket_dir, namespace)

        mkdir(socket_dir)

        socket_path = gen_socket_path(socket_dir, base_socket_name)
        try:
            self.verify_socket_path(socket_path)
        except NonvalidSocketPathException as e:
            raise NoSocketPathFoundException(
                f"Socket path '{socket_path}' failed verification: {e}"
            ) from e

        return socket_path

    @abc.abstractmethod
    def verify_socket_path(self, path: str) -> None:  # pragma: no cover
        """
        Verifies a socket path is valid.

        Raises:
            NonvalidSocketPathException: Subclasses will raise this exception if the socket path
                is not valid.
        """
        pass


class WindowsSocketPaths(SocketPaths):
    """
    Specialization for verifying socket paths on Windows systems.
    """

    def verify_socket_path(self, path: str) -> None:
        # TODO: Verify Windows permissions of parent directories are least privileged
        pass


class UnixSocketPaths(SocketPaths):
    """
    Specialization for verifying socket paths on Unix systems.
    """

    def verify_socket_path(self, path: str) -> None:
        # Walk up directories and check that the sticky bit is set if the dir is world writable
        prev_path = path
        curr_path = os.path.dirname(path)
        while prev_path != curr_path and len(curr_path) > 0:
            path_stat = os.stat(curr_path)
            if path_stat.st_mode & stat.S_IWOTH and not path_stat.st_mode & stat.S_ISVTX:
                raise NoSocketPathFoundException(
                    f"Cannot use directory {curr_path} because it is world writable and does not "
                    "have the sticky bit (restricted deletion flag) set"
                )
            prev_path = curr_path
            curr_path = os.path.dirname(curr_path)


class LinuxSocketPaths(UnixSocketPaths):
    """
    Specialization for socket paths in Linux systems.
    """

    # This is based on the max length of socket names to 108 bytes
    # See unix(7) under "Address format"
    # In practice, only 107 bytes are accepted (one byte for null terminator)
    _socket_name_max_length = 108 - 1

    def verify_socket_path(self, path: str) -> None:
        super().verify_socket_path(path)
        path_length = len(path.encode("utf-8"))
        if path_length > self._socket_name_max_length:
            raise NonvalidSocketPathException(
                "Socket name too long. The maximum allowed size is "
                f"{self._socket_name_max_length} bytes, but the name has a size of "
                f"{path_length}: {path}"
            )


class MacOSSocketPaths(UnixSocketPaths):
    """
    Specialization for socket paths in macOS systems.
    """

    # This is based on the max length of socket names to 104 bytes
    # See https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/un.h#L79
    # In practice, only 103 bytes are accepted (one byte for null terminator)
    _socket_name_max_length = 104 - 1

    def verify_socket_path(self, path: str) -> None:
        super().verify_socket_path(path)
        path_length = len(path.encode("utf-8"))
        if path_length > self._socket_name_max_length:
            raise NonvalidSocketPathException(
                "Socket name too long. The maximum allowed size is "
                f"{self._socket_name_max_length} bytes, but the name has a size of "
                f"{path_length}: {path}"
            )


_os_map: dict[str, type[SocketPaths]] = {
    OSName.LINUX: LinuxSocketPaths,
    OSName.MACOS: MacOSSocketPaths,
    OSName.WINDOWS: WindowsSocketPaths,
}


def _get_socket_paths_cls(
    osname: OSName,
) -> type[SocketPaths] | None:  # pragma: no cover
    return _os_map.get(osname, None)
