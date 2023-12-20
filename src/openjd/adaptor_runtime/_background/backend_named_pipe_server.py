# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations
import logging

from threading import Event
from typing import cast

from pywintypes import HANDLE


from .background_named_pipe_request_handler import WinBackgroundResourceRequestHandler
from .server_response import AsyncFutureRunner
from .._named_pipe import NamedPipeServer


from ..adaptors import AdaptorRunner
from .log_buffers import LogBuffer


_logger = logging.getLogger(__name__)


class WinBackgroundNamedPipeServer(NamedPipeServer):
    """
    A class to manage a Windows Named Pipe Server in background mode for the adaptor runtime communication.

    This class encapsulates stateful information of the adaptor backend and provides methods
    for server initialization, operation, and shutdown.
    """

    def __init__(
        self,
        pipe_name: str,
        adaptor_runner: AdaptorRunner,
        shutdown_event: Event,
        *,
        log_buffer: LogBuffer | None = None,
    ):  # pragma: no cover
        """
        Args:
            pipe_name (str): Name of the pipe for the NamedPipe Server.
            adaptor_runner (AdaptorRunner): Adaptor runner instance for operation execution.
            shutdown_event (Event): An Event used for signaling server shutdown.
            log_buffer (LogBuffer|None, optional): Buffer for logging activities, defaults to None.
        """
        super().__init__(pipe_name, shutdown_event)
        self._adaptor_runner = adaptor_runner
        self._shutdown_event = shutdown_event
        self._future_runner = AsyncFutureRunner()
        self._log_buffer = log_buffer

    def request_handler(self, server: "NamedPipeServer", pipe_handle: HANDLE):
        return WinBackgroundResourceRequestHandler(
            cast("WinBackgroundNamedPipeServer", server), pipe_handle
        )
