# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import re

import time
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import Callable, Dict, TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from .backend_named_pipe_server import WinBackgroundNamedPipeServer
    from .http_server import BackgroundHTTPServer


from ..adaptors._adaptor_runner import _OPENJD_FAIL_STDOUT_PREFIX
from .._http import HTTPResponse
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


class ServerResponseGenerator:
    """
    This class is used for generating responses for all requests to the server.
    Response methods follow format: `generate_{request_path}_{method}_response`
    """

    ACK_ID_KEY = "ack_id"

    def __init__(
        self,
        server: Union[BackgroundHTTPServer, WinBackgroundNamedPipeServer],
        response_fn: Callable,
        body: Dict,
        query_string_params: Dict[str, Any],
    ):
        """
        Response generator

        Args:
            server: The server used for communication. For Linux, this will
                be a BackgroundHTTPServer instance.
            response_fn: The function used to return the result to the client.
                For Linux, this will be an HTTPResponse instance.
            body: The request body sent by the client.
            query_string_params: The request parameters sent by the client.
                For Linux, these will be extracted from the URL.
        """
        self.server = server
        self.response_method = response_fn
        self.body = body
        self.query_string_params = query_string_params

    def generate_cancel_put_response(self) -> HTTPResponse:
        """
        Handle PUT request to /cancel path.

        Returns:
            Linux: return HTTPResponse.
        """
        if not (
            self.server._future_runner.is_running
            and self.server._adaptor_runner.state in [AdaptorState.START, AdaptorState.RUN]
        ):
            return self.response_method(HTTPStatus.OK, body="No action required")

        return self.submit(
            self.server._adaptor_runner._cancel,
            force_immediate=True,
        )

    def generate_heartbeat_get_response(self, parse_ack_id_fn: Callable) -> HTTPResponse:
        """
        Handle Get request to /heartbeat path.

        Args:
            parse_ack_id_fn(Callable): A function used for extracting the ack id.

        Returns:
            Linux: return HTTPResponse.
        """
        # Failure messages are in the form: "<log-level>: openjd_fail: <message>"
        _FAILURE_REGEX = f"^(?:\\w+: )?{re.escape(_OPENJD_FAIL_STDOUT_PREFIX)}"

        failed = False
        if not self.server._log_buffer:
            output = BufferedOutput(BufferedOutput.EMPTY, "")
        else:
            # Check for chunk ID ACKs
            ack_id = parse_ack_id_fn()
            if ack_id:
                if self.server._log_buffer.clear(ack_id):
                    _logger.debug(f"Received ACK for chunk: {ack_id}")
                else:
                    _logger.warning(f"Received ACK for old or invalid chunk: {ack_id}")

            output = self.server._log_buffer.chunk()

            if re.search(_FAILURE_REGEX, output.output, re.MULTILINE):
                failed = True

        status = (
            AdaptorStatus.WORKING if self.server._future_runner.is_running else AdaptorStatus.IDLE
        )

        heartbeat = HeartbeatResponse(
            state=self.server._adaptor_runner.state, status=status, output=output, failed=failed
        )
        return self.response_method(HTTPStatus.OK, json.dumps(heartbeat, cls=DataclassJSONEncoder))

    def generate_shutdown_put_response(self) -> HTTPResponse:
        """
        Handle Put request to /shutdown path.

        Returns:
            Linux: return HTTPResponse.
        """

        self.server._shutdown_event.set()
        return self.response_method(HTTPStatus.OK)

    def generate_run_put_response(self) -> HTTPResponse:
        """
        Handle Put request to /run path.

        Returns:
            Linux: return HTTPResponse.
        """
        if self.server._future_runner.is_running:
            return self.response_method(HTTPStatus.BAD_REQUEST)

        return self.submit(
            self.server._adaptor_runner._run,
            self.body if self.body else {},
        )

    def generate_start_put_response(self) -> HTTPResponse:
        """
        Handle Put request to /start path.

        Returns:
            Linux: return HTTPResponse.
        """
        if self.server._future_runner.is_running:
            return self.response_method(HTTPStatus.BAD_REQUEST)

        return self.submit(self.server._adaptor_runner._start)

    def generate_stop_put_response(self) -> HTTPResponse:
        """
        Handle Put request to /stop path.

        Returns:
            Linux: return HTTPResponse.
        """

        if self.server._future_runner.is_running:
            return self.response_method(HTTPStatus.BAD_REQUEST)

        return self.submit(self._stop_adaptor)

    def _stop_adaptor(self) -> None:  # pragma: no cover
        """
        Stop and clean up the adaptor runner.
        """
        try:
            self.server._adaptor_runner._stop()
            _logger.info("Daemon background process stopped.")
        finally:
            self.server._adaptor_runner._cleanup()

    def submit(self, fn: Callable, *args, force_immediate=False, **kwargs) -> HTTPResponse:
        """
        Submits work to the server.

        Args:
            force_immediate (bool): Force the server to immediately start the work. This work will
            be performed concurrently with any ongoing work.

        Returns:
            Linux: return HTTPResponse.
        """
        future_runner = self.server._future_runner if not force_immediate else AsyncFutureRunner()
        try:
            future_runner.submit(fn, *args, **kwargs)
        except Exception as e:
            _logger.error(f"Failed to submit work: {e}")
            return self.response_method(HTTPStatus.INTERNAL_SERVER_ERROR, body=str(e))

        # Wait for the worker thread to start working before sending the response
        self.server._future_runner.wait_for_start()
        return self.response_method(HTTPStatus.OK)
