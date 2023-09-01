# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import re
import socketserver
import time
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from queue import Queue
from typing import Callable

from ..adaptors._adaptor_runner import _OPENJD_FAIL_STDOUT_PREFIX
from ..adaptors import AdaptorRunner
from .._http import HTTPResponse, RequestHandler, ResourceRequestHandler
from .log_buffers import LogBuffer
from .model import (
    AdaptorState,
    AdaptorStatus,
    BufferedOutput,
    DataclassJSONEncoder,
    HeartbeatResponse,
)

_logger = logging.getLogger(__name__)


class AsyncFutureRunner:
    """
    Class that models an asynchronous worker thread using concurrent.futures.
    """

    _WAIT_FOR_START_INTERVAL = 0.01

    def __init__(self) -> None:
        self._thread_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="AdaptorRuntimeBackendWorkerThread"
        )
        self._future: Future | None = None

    def submit(self, fn: Callable, *args, **kwargs) -> None:
        if self.is_running:
            raise Exception("Cannot submit new task while another task is running")
        self._future = self._thread_pool.submit(fn, *args, **kwargs)

    @property
    def is_running(self) -> bool:
        if self._future is None:
            return False
        return self._future.running()

    @property
    def has_started(self) -> bool:
        if self._future is None:
            return False  # pragma: no cover
        return self._future.running() or self._future.done()

    def wait_for_start(self):
        """Blocks until the Future has started"""
        while not self.has_started:
            time.sleep(self._WAIT_FOR_START_INTERVAL)


class BackgroundHTTPServer(socketserver.UnixStreamServer):
    """
    HTTP server for the background mode of the adaptor runtime communicating via Unix socket.

    This UnixStreamServer subclass stores the stateful information of the adaptor backend.
    """

    def __init__(
        self,
        socket_path: str,
        adaptor_runner: AdaptorRunner,
        cancel_queue: Queue,
        *,
        log_buffer: LogBuffer | None = None,
        bind_and_activate: bool = True,
    ) -> None:  # pragma: no cover
        super().__init__(socket_path, BackgroundRequestHandler, bind_and_activate)
        self._adaptor_runner = adaptor_runner
        self._cancel_queue = cancel_queue
        self._future_runner = AsyncFutureRunner()
        self._log_buffer = log_buffer

    def submit(self, fn: Callable, *args, force_immediate=False, **kwargs) -> HTTPResponse:
        """
        Submits work to the server.

        Args:
            force_immediate (bool): Force the server to immediately start the work. This work will
            be performed concurrently with any ongoing work.
        """
        future_runner = self._future_runner if not force_immediate else AsyncFutureRunner()
        try:
            future_runner.submit(fn, *args, **kwargs)
        except Exception as e:
            _logger.error(f"Failed to submit work: {e}")
            return HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR, body=str(e))

        # Wait for the worker thread to start working before sending the response
        self._future_runner.wait_for_start()
        return HTTPResponse(HTTPStatus.OK)


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


class HeartbeatHandler(BackgroundResourceRequestHandler):
    """
    Handler for the heartbeat resource
    """

    # Failure messages are in the form: "<log-level>: openjd_fail: <message>"
    _FAILURE_REGEX = f"^(?:\\w+: )?{re.escape(_OPENJD_FAIL_STDOUT_PREFIX)}"
    _ACK_ID_KEY = "ack_id"

    path: str = "/heartbeat"

    def get(self) -> HTTPResponse:
        failed = False
        if not self.server._log_buffer:
            output = BufferedOutput(BufferedOutput.EMPTY, "")
        else:
            # Check for chunk ID ACKs
            ack_id = self._parse_ack_id()
            if ack_id:
                if self.server._log_buffer.clear(ack_id):
                    _logger.debug(f"Received ACK for chunk: {ack_id}")
                else:
                    _logger.warning(f"Received ACK for old or invalid chunk: {ack_id}")

            output = self.server._log_buffer.chunk()

            if re.search(self._FAILURE_REGEX, output.output, re.MULTILINE):
                failed = True

        status = (
            AdaptorStatus.WORKING if self.server._future_runner.is_running else AdaptorStatus.IDLE
        )

        heartbeat = HeartbeatResponse(
            state=self.server._adaptor_runner.state, status=status, output=output, failed=failed
        )
        return HTTPResponse(HTTPStatus.OK, json.dumps(heartbeat, cls=DataclassJSONEncoder))

    def _parse_ack_id(self) -> str | None:
        """
        Parses chunk ID ACK from the query string. Returns None if the chunk ID ACK was not found.
        """
        if self._ACK_ID_KEY in self.query_string_params:
            ack_ids: list[str] = self.query_string_params[self._ACK_ID_KEY]
            if len(ack_ids) > 1:
                raise ValueError(
                    f"Expected one value for {self._ACK_ID_KEY}, but found: {len(ack_ids)}"
                )
            return ack_ids[0]

        return None


class ShutdownHandler(BackgroundResourceRequestHandler):
    """
    Handler for the shutdown resource.
    """

    path: str = "/shutdown"

    def put(self) -> HTTPResponse:
        self.server._cancel_queue.put(True)
        return HTTPResponse(HTTPStatus.OK)


class RunHandler(BackgroundResourceRequestHandler):
    """
    Handler for the run resource.
    """

    path: str = "/run"

    def put(self) -> HTTPResponse:
        if self.server._future_runner.is_running:
            return HTTPResponse(HTTPStatus.BAD_REQUEST)

        run_data: dict = json.loads(self.body.decode(encoding="utf-8")) if self.body else {}

        return self.server.submit(
            self.server._adaptor_runner._run,
            run_data,
        )


class StartHandler(BackgroundResourceRequestHandler):
    """
    Handler for the start resource.
    """

    path: str = "/start"

    def put(self) -> HTTPResponse:
        if self.server._future_runner.is_running:
            return HTTPResponse(HTTPStatus.BAD_REQUEST)

        return self.server.submit(self.server._adaptor_runner._start)


class StopHandler(BackgroundResourceRequestHandler):
    """
    Handler for the stop resource.
    """

    path: str = "/stop"

    def put(self) -> HTTPResponse:
        if self.server._future_runner.is_running:
            return HTTPResponse(HTTPStatus.BAD_REQUEST)

        return self.server.submit(self._stop_adaptor)

    def _stop_adaptor(self):  # pragma: no cover
        try:
            self.server._adaptor_runner._stop()
            _logger.info("Daemon background process stopped.")
        finally:
            self.server._adaptor_runner._cleanup()


class CancelHandler(BackgroundResourceRequestHandler):
    """
    Handler for the cancel resource.
    """

    path: str = "/cancel"

    def put(self) -> HTTPResponse:
        if not (
            self.server._future_runner.is_running
            and self.server._adaptor_runner.state in [AdaptorState.START, AdaptorState.RUN]
        ):
            return HTTPResponse(HTTPStatus.OK, body="No action required")

        return self.server.submit(
            self.server._adaptor_runner._cancel,
            force_immediate=True,
        )
