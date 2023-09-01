# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import socket as _socket
import ctypes as _ctypes
import os as _os
from http.client import HTTPConnection as _HTTPConnection


class UnrecognizedBackgroundConnectionError(Exception):
    pass


class UCred(_ctypes.Structure):
    """
    Represents the ucred struct returned from the SO_PEERCRED socket option.

    For more info, see SO_PASSCRED in the unix(7) man page
    """

    _fields_ = [
        ("pid", _ctypes.c_int),
        ("uid", _ctypes.c_int),
        ("gid", _ctypes.c_int),
    ]

    def __str__(self):  # pragma: no cover
        return f"pid:{self.pid} uid:{self.uid} gid:{self.gid}"


class UnixHTTPConnection(_HTTPConnection):  # pragma: no cover
    """
    Specialization of http.client.HTTPConnection class that uses a UNIX domain socket.
    """

    def __init__(self, host, **kwargs):
        kwargs.pop("strict", None)  # Removed in py3
        super(UnixHTTPConnection, self).__init__(host, **kwargs)

    def connect(self):
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.host)
        self.sock = sock

        # Verify that the socket belongs to the same user
        if not self._authenticate():
            sock.detach(self.sock)
            raise UnrecognizedBackgroundConnectionError(
                "Attempted to make a connection to a background server owned by another user."
            )

    def _authenticate(self) -> bool:
        # Verify we have a UNIX socket.
        if not (
            isinstance(self.sock, _socket.socket)
            and self.sock.family == _socket.AddressFamily.AF_UNIX
        ):
            raise NotImplementedError(
                "Failed to handle request because it was not made through a UNIX socket"
            )

        # Get the credentials of the peer process
        cred_buffer = self.sock.getsockopt(
            _socket.SOL_SOCKET,
            _socket.SO_PEERCRED,
            _socket.CMSG_SPACE(_ctypes.sizeof(UCred)),
        )
        peer_cred = UCred.from_buffer_copy(cred_buffer)

        # Only allow connections from a process running as the same user
        return peer_cred.uid == _os.getuid()
