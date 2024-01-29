# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import socketserver
from threading import Event
from .server_response import ServerResponseGenerator, AsyncFutureRunner
from ..adaptors import AdaptorRunner
from .._http import HTTPResponse, RequestHandler, ResourceRequestHandler
from .log_buffers import LogBuffer


from socketserver import UnixStreamServer  # type: ignore[attr-defined]

_logger = logging.getLogger(__name__)


class BackgroundHTTPServer(UnixStreamServer):
    """
    HTTP server for the background mode of the adaptor runtime communicating via Unix socket.

    This UnixStreamServer subclass stores the stateful information of the adaptor backend.
    """

    def __init__(
        self,
        socket_path: str,
        adaptor_runner: AdaptorRunner,
        shutdown_event: Event,
        *,
        log_buffer: LogBuffer | None = None,
        bind_and_activate: bool = True,
    ) -> None:  # pragma: no cover
        super().__init__(socket_path, BackgroundRequestHandler, bind_and_activate)  # type: ignore
        self._adaptor_runner = adaptor_runner
        self._shutdown_event = shutdown_event
        self._future_runner = AsyncFutureRunner()
        self._log_buffer = log_buffer


class BackgroundRequestHandler(RequestHandler):
    """
    Class that handles HTTP requests to a BackgroundHTTPServer.

    Note: The "server" argument passed to this class must be an instance of BackgroundHTTPServer
    and the server must listen for requests using UNIX domain sockets.
    """

    def __init__(
        self, request: bytes, client_address: str, server: socketserver.BaseServer
    ) -> None:
        if not isinstance(server, BackgroundHTTPServer):
            raise TypeError(
                "Received incompatible server class. "
                f"Expected {BackgroundHTTPServer.__name__}, but got {type(server)}"
            )
        super().__init__(
            request,
            client_address,
            server,
            BackgroundResourceRequestHandler,
        )


class BackgroundResourceRequestHandler(ResourceRequestHandler):
    """
    Base class that handles HTTP requests for a specific resource.

    This class only works with a BackgroundHTTPServer.
    """

    @property
    def server(self) -> BackgroundHTTPServer:
        """
        Property to "lazily type check" the HTTP server class this handler is used in.

        This is required because the socketserver.BaseRequestHandler.__init__ method actually
        handles the request. This means the self.handler.server variable is not set until that
        init method is called, so we need to do this type check outside of the init chain.

        Raises:
            TypeError: Raised when the HTTP server class is not BackgroundHTTPServer.
        """

        if not isinstance(self.handler.server, BackgroundHTTPServer):
            raise TypeError(
                f"Incompatible HTTP server class. Expected {BackgroundHTTPServer.__name__}, got: "
                + type(self.handler.server).__name__
            )

        return self.handler.server

    @property
    def server_response(self):
        """
        This property is similar to the server property. self.body variable is not set until the
        init method is called.
        """
        if not hasattr(self, "_server_response"):
            body = json.loads(self.body.decode(encoding="utf-8")) if self.body else {}
            self._server_response = ServerResponseGenerator(
                self.server, HTTPResponse, body, self.query_string_params
            )
        return self._server_response


class HeartbeatHandler(BackgroundResourceRequestHandler):
    """
    Handler for the heartbeat resource
    """

    path: str = "/heartbeat"

    def get(self) -> HTTPResponse:
        return self.server_response.generate_heartbeat_get_response()


class ShutdownHandler(BackgroundResourceRequestHandler):
    """
    Handler for the shutdown resource.
    """

    path: str = "/shutdown"

    def put(self) -> HTTPResponse:
        return self.server_response.generate_shutdown_put_response()


class RunHandler(BackgroundResourceRequestHandler):
    """
    Handler for the run resource.
    """

    path: str = "/run"

    def put(self) -> HTTPResponse:
        return self.server_response.generate_run_put_response()


class StartHandler(BackgroundResourceRequestHandler):
    """
    Handler for the start resource.
    """

    path: str = "/start"

    def put(self) -> HTTPResponse:
        return self.server_response.generate_start_put_response()


class StopHandler(BackgroundResourceRequestHandler):
    """
    Handler for the stop resource.
    """

    path: str = "/stop"

    def put(self) -> HTTPResponse:
        return self.server_response.generate_stop_put_response()


class CancelHandler(BackgroundResourceRequestHandler):
    """
    Handler for the cancel resource.
    """

    path: str = "/cancel"

    def put(self) -> HTTPResponse:
        return self.server_response.generate_cancel_put_response()
