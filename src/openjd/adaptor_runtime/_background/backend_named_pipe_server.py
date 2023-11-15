# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations
import logging

import threading
import time

from queue import Queue
from typing import List, Optional

from .named_pipe_request_handler import WinBackgroundResourceRequestHandler
from .server_config import NAMED_PIPE_BUFFER_SIZE, DEFAULT_NAMED_PIPE_TIMEOUT_MILLISECONDS
from .server_response import AsyncFutureRunner
from .._osname import OSName

import win32pipe
import win32file
import pywintypes
import winerror
import win32api
from pywintypes import HANDLE

from ..adaptors import AdaptorRunner
from .log_buffers import LogBuffer


_logger = logging.getLogger(__name__)


class MultipleErrors(Exception):
    """
    Custom exception class to aggregate and handle multiple exceptions.

    This class is used to collect a list of exceptions that occur during a process, allowing
    them to be raised together as a single exception. This is particularly useful in scenarios
    where multiple operations are performed in a loop, and each operation could potentially
    raise an exception.
    """

    def __init__(self, errors: List[Exception]):
        """
        Initialize the MultipleErrors exception with a list of errors.

        Args:
            errors (List[Exception]): A list of exceptions that have been raised.
        """
        self.errors = errors

    def __str__(self) -> str:
        """
        Return a string representation of all errors aggregated in this exception.

        This method concatenates the string representations of each individual exception
        in the `errors` list, separated by semicolons.

        Returns:
            str: A formatted string containing all the error messages.
        """
        return "Multiple errors occurred: " + "; ".join(str(e) for e in self.errors)


class WinBackgroundNamedPipeServer:
    """
    A class to manage a Windows Named Pipe Server in background mode for the adaptor runtime communication.

    This class encapsulates stateful information of the adaptor backend and provides methods
    for server initialization, operation, and shutdown.
    """

    def __init__(
        self,
        pipe_name: str,
        adaptor_runner: AdaptorRunner,
        cancel_queue: Queue,
        *,
        log_buffer: LogBuffer | None = None,
    ):  # pragma: no cover
        """
        Args:
            pipe_name (str): Name of the pipe for the NamedPipe Server.
            adaptor_runner (AdaptorRunner): Adaptor runner instance for operation execution.
            cancel_queue (Queue): Queue used for signaling server shutdown.
            log_buffer (LogBuffer|None, optional): Buffer for logging activities, defaults to None.
        """
        if not OSName.is_windows():
            raise OSError(
                "WinBackgroundNamedPipeServer can be only used on Windows Operating Systems. "
                f"Current Operating System is {OSName._get_os_name()}"
            )
        self._adaptor_runner = adaptor_runner
        self._cancel_queue = cancel_queue
        self._future_runner = AsyncFutureRunner()
        self._log_buffer = log_buffer
        self._named_pipe_instances: List[HANDLE] = []
        self._pipe_name = pipe_name
        # TODO: Need to figure out how to set the itme out for NamedPipe.
        #   Unlike Linux Server, time out can only be set in the Server side instead of the client side.
        self._time_out = DEFAULT_NAMED_PIPE_TIMEOUT_MILLISECONDS

    def _create_pipe(self, pipe_name: str) -> Optional[HANDLE]:
        """
        Creates a new instance of a named pipe or an additional instance if the pipe already exists.

        Args:
            pipe_name (str): Name of the pipe for which the instance is to be created.

        Returns:
            HANDLE: The handler for the created named pipe instance.

        """

        pipe_handle = win32pipe.CreateNamedPipe(
            pipe_name,
            # A bi-directional pipe; both server and client processes can read from and write to the pipe.
            # win32file.FILE_FLAG_OVERLAPPED is used for async communication.
            win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            NAMED_PIPE_BUFFER_SIZE,  # nOutBufferSize
            NAMED_PIPE_BUFFER_SIZE,  # nInBufferSize
            self._time_out,
            None,  # TODO: Add lpSecurityAttributes here to limit the access
        )
        if pipe_handle == win32file.INVALID_HANDLE_VALUE:
            return None
        return pipe_handle

    def serve_forever(self) -> None:
        """
        Runs the Named Pipe Server continuously until a shutdown signal is received.

        This method listens to the NamedPipe Server and creates new instances of named pipes
        and corresponding threads for handling client-server communication.
        """
        _logger.info(f"Creating Named Pipe with name: {self._pipe_name}")
        # During shutdown, a `True` will be pushed to the `_cancel_queue` for ending this loop
        # TODO: Using threading.event instead of a queue to signal and termination
        while self._cancel_queue.qsize() == 0:
            pipe_handle = self._create_pipe(self._pipe_name)
            if pipe_handle is None:
                error_msg = (
                    f"Failed to create named pipe instance: "
                    f"{win32api.FormatMessage(win32api.GetLastError())}"
                )
                _logger.error(error_msg)
                raise RuntimeError(error_msg)
            self._named_pipe_instances.append(pipe_handle)
            _logger.debug("Waiting for connection from the client...")

            try:
                win32pipe.ConnectNamedPipe(pipe_handle, None)
            except pywintypes.error as e:
                if e.winerror == winerror.ERROR_PIPE_NOT_CONNECTED:
                    _logger.info(
                        "NamedPipe Server is shutdown. Exit the main thread in the backend server."
                    )
                    break
                else:
                    _logger.error(f"Error encountered while connecting to NamedPipe: {e} ")
            request_handler = WinBackgroundResourceRequestHandler(self, pipe_handle)
            threading.Thread(target=request_handler.instance_thread).start()

    def shutdown(self) -> None:
        """
        Shuts down the Named Pipe server and closes all named pipe handlers.

        Signals the `serve_forever` method to stop listening to the NamedPipe Server by
        pushing a `True` value into the `_cancel_queue`.
        """
        self._cancel_queue.put(True)
        # TODO: Need to find out a better way to wait for the communication finish
        #  After sending the shutdown command, we need to wait for the response
        #  from it before shutting down server or the client won't get the response.
        time.sleep(1)
        error_list: List[Exception] = []
        while self._named_pipe_instances:
            pipe_handle = self._named_pipe_instances.pop()
            try:
                win32pipe.DisconnectNamedPipe(pipe_handle)
                win32file.CloseHandle(pipe_handle)
            except pywintypes.error as e:
                # If the communication is finished then handler may be closed
                if e.args[0] == winerror.ERROR_INVALID_HANDLE:
                    pass
            except Exception as e:
                import traceback

                _logger.error(
                    f"Encountered the following error "
                    f"while shutting down the WinBackgroundNamedPipeServer: {str(traceback.format_exc())}"
                )
                # Store any errors to raise after closing all pipe handles,
                # allowing handling of multiple errors during shutdown.
                error_list.append(e)
        if error_list:
            raise MultipleErrors(error_list)
