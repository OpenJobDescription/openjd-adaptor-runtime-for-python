# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import signal as _signal
import threading as _threading
import warnings

from .base_client_interface import Response as _Response
from typing import Dict as _Dict

from .base_client_interface import BaseClientInterface
from .connection import UnixHTTPConnection as _UnixHTTPConnection
from urllib.parse import urlencode as _urlencode


# Set timeout to None so our requests are blocking calls with no timeout.
# See socket.settimeout
_REQUEST_TIMEOUT = None

SOCKET_PATH_DEPRECATED_MESSAGE = (
    "The 'socket_path' parameter is deprecated; use 'server_path' instead"
)


class HTTPClientInterface(BaseClientInterface):
    def __init__(self, server_path: str, **kwargs) -> None:
        """When the client is created, we need the port number to connect to the server.

        Args:
            server_path (str): The path to the UNIX domain socket to use.
        """

        socket_path = kwargs.get("socket_path")
        if socket_path is not None:
            warnings.warn(SOCKET_PATH_DEPRECATED_MESSAGE, DeprecationWarning)
            if server_path is not None:
                raise ValueError("Cannot use both 'server_path' and 'socket_path'")
            server_path = socket_path

        super().__init__(server_path)

        if _threading.current_thread() is _threading.main_thread():
            # NOTE: The signals SIGKILL and SIGSTOP cannot be caught, blocked, or ignored.
            # Reference: https://man7.org/linux/man-pages/man7/signal.7.html
            # SIGTERM graceful shutdown.
            _signal.signal(_signal.SIGTERM, self.graceful_shutdown)

    @property
    def socket_path(self):
        warnings.warn(SOCKET_PATH_DEPRECATED_MESSAGE, DeprecationWarning)
        return self.server_path

    @socket_path.setter
    def socket_path(self, value):
        warnings.warn(SOCKET_PATH_DEPRECATED_MESSAGE, DeprecationWarning)
        self.server_path = value

    def _send_request(
        self, method: str, request_path: str, *, query_string_params: _Dict | None = None
    ) -> _Response:
        """
        Send a request to the server and return the response.

        Args:
            method (str): The HTTP method, e.g. 'GET', 'POST'.
            request_path (str): The path for the request.
            query_string_params (_Dict | None, optional): Query string parameters to include in the request.
                Defaults to None. In Linux, the query string parameters will be added to the URL

        Returns:
            Response: The response from the server.
        """
        headers = {
            "Content-type": "application/json",
        }
        connection = _UnixHTTPConnection(self.socket_path, timeout=_REQUEST_TIMEOUT)
        if query_string_params:
            request_path += "?" + _urlencode(query_string_params)
        connection.request(method, request_path, headers=headers)
        response = connection.getresponse()
        connection.close()
        length = response.length if response.length else 0
        body = response.read().decode() if length else ""
        return _Response(response.status, body, response.reason, length)
