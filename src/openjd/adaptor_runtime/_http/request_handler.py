# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import abc
import ctypes
import logging
import os
import socket
import socketserver
import urllib.parse as urllib_parse
from dataclasses import dataclass
from http import HTTPStatus, server
from typing import Any, Callable, Type

from .._osname import OSName
from .exceptions import UnsupportedPlatformException

_logger = logging.getLogger(__name__)


class RequestHandler(server.BaseHTTPRequestHandler):
    """
    Class that handles HTTP requests to a HTTPServer.

    Note: The "server" argument passed to this class must listen for requests using UNIX domain
    sockets.
    """

    _DEFAULT_HANDLER: ResourceRequestHandler
    _HANDLER_TYPE: Type[ResourceRequestHandler]

    _handlers: dict[str, ResourceRequestHandler]

    # Socket variable set in parent class StreamRequestHandler.setup()
    connection: socket.socket

    def __init__(
        self,
        request: bytes,
        client_address: str,
        server: socketserver.BaseServer,
        handler_type: Type[ResourceRequestHandler],
    ) -> None:
        self._DEFAULT_HANDLER = _DefaultRequestHandler()
        self._HANDLER_TYPE = handler_type

        def _subclasses(cls: type):
            for sc in cls.__subclasses__():
                yield from _subclasses(sc)
                yield sc

        self._handlers = {
            sc.path: sc(self)
            for sc in _subclasses(self._HANDLER_TYPE)
            if sc is not _DefaultRequestHandler
        }
        super().__init__(request, client_address, server)  # type: ignore

    def address_string(self) -> str:
        # Parent class assumes this is a tuple of (address, port)
        return self.client_address  # type: ignore

    def do_GET(self) -> None:  # pragma: no cover
        parsed_path = urllib_parse.urlparse(self.path)
        handler = self._handlers.get(parsed_path.path, self._DEFAULT_HANDLER)
        self._do_request(handler.get)

    def do_PUT(self) -> None:  # pragma: no cover
        parsed_path = urllib_parse.urlparse(self.path)
        handler = self._handlers.get(parsed_path.path, self._DEFAULT_HANDLER)
        self._do_request(handler.put)

    def _do_request(self, func: Callable[[], HTTPResponse]) -> None:
        # First, authenticate the connecting peer
        try:
            authenticated = self._authenticate()
        except UnsupportedPlatformException as e:
            _logger.error(e)
            self._respond(HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR))
            return

        if not authenticated:
            self._respond(HTTPResponse(HTTPStatus.UNAUTHORIZED))
            return

        # Handle the request
        try:
            response = func()
        except Exception as e:
            _logger.error(f"Failed to handle request: {e}")
            response = HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR)

        self._respond(response)

    def _respond(self, response: HTTPResponse) -> None:
        if response.status < 400:
            self.send_response(response.status)
        else:
            self.send_error(response.status)
        path_to_log = self.path.replace("\r\n", "").replace("\n", "")
        _logger.debug(f"Sending status code {response.status} for request to {path_to_log}")

        if response.body:
            body = response.body.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.end_headers()

    # NOTE: self.connection is set by the base class socketserver.StreamRequestHandler.
    # This class is instantiated in socketserver.BaseServer.finish_request(), where the socket
    # returned by socketserver.BaseServer.get_request() is passed as the argument for "request".
    def _authenticate(self) -> bool:
        # Verify we have a UNIX socket.
        if not (
            isinstance(self.connection, socket.socket)
            and self.connection.family == socket.AddressFamily.AF_UNIX  # type: ignore[attr-defined]
        ):
            raise UnsupportedPlatformException(
                "Failed to handle request because it was not made through a UNIX socket"
            )

        peercred_opt_level: Any
        peercred_opt: Any
        cred_cls: Any
        if OSName.is_macos():  # pragma: no cover
            # SOL_LOCAL is not defined in Python's socket module, need to hardcode it
            # source: https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/un.h#L85
            peercred_opt_level = 0  # type: ignore[attr-defined]
            peercred_opt = socket.LOCAL_PEERCRED  # type: ignore[attr-defined]
            cred_cls = XUCred
        else:  # pragma: no cover
            peercred_opt_level = socket.SOL_SOCKET  # type: ignore[attr-defined]
            peercred_opt = socket.SO_PEERCRED  # type: ignore[attr-defined]
            cred_cls = UCred

        # Get the credentials of the peer process
        cred_buffer = self.connection.getsockopt(
            peercred_opt_level,
            peercred_opt,
            socket.CMSG_SPACE(ctypes.sizeof(cred_cls)),  # type: ignore[attr-defined]
        )
        peer_cred = cred_cls.from_buffer_copy(cred_buffer)

        # Only allow connections from a process running as the same user
        return peer_cred.uid == os.getuid()  # type: ignore[attr-defined]


class UCred(ctypes.Structure):
    """
    Represents the ucred struct returned from the SO_PEERCRED socket option.

    For more info, see SO_PASSCRED in the unix(7) man page
    """

    _fields_ = [
        ("pid", ctypes.c_int),
        ("uid", ctypes.c_int),
        ("gid", ctypes.c_int),
    ]

    def __str__(self):  # pragma: no cover
        return f"pid:{self.pid} uid:{self.uid} gid:{self.gid}"


class XUCred(ctypes.Structure):
    """
    Represents the xucred struct returned from the LOCAL_PEERCRED socket option.

    For more info, see LOCAL_PEERCRED in the unix(4) man page
    """

    _fields_ = [
        ("version", ctypes.c_uint),
        ("uid", ctypes.c_uint),
        ("ngroups", ctypes.c_short),
        # cr_groups is a uint array of NGROUPS elements, which is defined as 16
        # source:
        # - https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/ucred.h#L207
        # - https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/param.h#L100
        # - https://github.com/apple-oss-distributions/xnu/blob/1031c584a5e37aff177559b9f69dbd3c8c3fd30a/bsd/sys/syslimits.h#L100
        ("groups", ctypes.c_uint * 16),
    ]


@dataclass
class HTTPResponse:
    """
    Dataclass to model an HTTP response.
    """

    status: HTTPStatus
    body: str | None = None


class ResourceRequestHandler(abc.ABC):
    """
    Base class that handles HTTP requests for a specific resource.
    """

    path: str = "/"

    def __init__(
        self,
        handler: RequestHandler,
    ) -> None:
        self.handler = handler

    def get(self) -> HTTPResponse:  # pragma: no cover
        """
        Handles HTTP GET
        """
        return HTTPResponse(HTTPStatus.NOT_IMPLEMENTED, None)

    def put(self) -> HTTPResponse:  # pragma: no cover
        """
        Handles HTTP PUT
        """
        return HTTPResponse(HTTPStatus.NOT_IMPLEMENTED, None)

    @property
    def server(self) -> socketserver.BaseServer:
        """
        Property to "lazily type check" the HTTP server class this handler is used in.

        This is required because the socketserver.BaseRequestHandler.__init__ method actually
        handles the request. This means the self.handler.server variable is not set until that
        init method is called, so we need to do this type check outside of the init chain.
        """
        return self.handler.server

    @property
    def query_string_params(self) -> dict[str, list[str]]:
        """
        Gets the query string parameters for the request.

        Note: Parameter values are stored in an array to support duplicate keys
        """
        if not hasattr(self, "_query_string_params"):
            parsed_path = urllib_parse.urlparse(self.handler.path)
            self._query_string_params = urllib_parse.parse_qs(parsed_path.query)
        return self._query_string_params

    @property
    def body(self) -> bytes | None:
        """
        Gets the request body or None if there was no body.
        """
        if not hasattr(self, "_body"):
            body_length = int(self.handler.headers.get("Content-Length", 0))
            self._body = self.handler.rfile.read(body_length) if body_length else None
        return self._body


class _DefaultRequestHandler(ResourceRequestHandler):  # pragma: no cover
    """
    Request handler that always returns 501 Not Implemented (see base class implementation)
    """

    def __init__(self) -> None:
        pass
