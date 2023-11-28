# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import signal
from threading import Thread, Event
from types import FrameType
from typing import Optional, Union

from .._osname import OSName
from ..adaptors import AdaptorRunner
from .._http import SocketDirectories
from .._utils import secure_open

if OSName.is_posix():
    from .http_server import BackgroundHTTPServer
if OSName.is_windows():
    from .backend_named_pipe_server import WinBackgroundNamedPipeServer
from .log_buffers import LogBuffer
from .model import ConnectionSettings
from .model import DataclassJSONEncoder

_logger = logging.getLogger(__name__)


class BackendRunner:
    """
    Class that runs the backend logic in background mode.
    """

    def __init__(
        self,
        adaptor_runner: AdaptorRunner,
        connection_file_path: str,
        *,
        log_buffer: LogBuffer | None = None,
    ) -> None:
        self._adaptor_runner = adaptor_runner
        self._connection_file_path = connection_file_path
        self._log_buffer = log_buffer
        self._server: Optional[Union[BackgroundHTTPServer, WinBackgroundNamedPipeServer]] = None
        # TODO: Signal handler needed to be checked in Windows
        #  The current plan is to use CTRL_BREAK.
        if OSName.is_posix():
            signal.signal(signal.SIGINT, self._sigint_handler)
            signal.signal(signal.SIGTERM, self._sigint_handler)

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """Signal handler that is invoked when the process receives a SIGINT/SIGTERM"""
        _logger.info("Interruption signal recieved.")
        # OpenJD dictates that a SIGTERM/SIGINT results in a cancel workflow being
        # kicked off.
        # TODO: Do a code refactoring to move the `submit` to the `server_response`
        if OSName.is_posix():
            if self._server is not None:
                self._server.submit(  # type: ignore
                    self._adaptor_runner._cancel, force_immediate=True
                )
        else:
            raise NotImplementedError("Signal is not implemented in Windows.")

    def run(self) -> None:
        """
        Runs the backend logic for background mode.

        This function will start an HTTP server that picks an available port to listen on, write
        that port to a connection file, and listens for HTTP requests until a shutdown is requested
        """
        _logger.info("Running in background daemon mode.")
        shutdown_event: Event = Event()

        if OSName.is_posix():
            server_path = SocketDirectories.for_os().get_process_socket_path(
                "runtime", create_dir=True
            )
        else:
            # TODO: Do a code refactoring to generate the namedpipe server path by using the SocketDirectories
            #  Need to check if the pipe name is used and the max length.
            server_path = rf"\\.\pipe\AdaptorNamedPipe_{str(os.getpid())}"

        try:
            if OSName.is_windows():
                self._server = WinBackgroundNamedPipeServer(
                    server_path,
                    self._adaptor_runner,
                    shutdown_event=shutdown_event,
                    log_buffer=self._log_buffer,
                )
            else:
                self._server = BackgroundHTTPServer(
                    server_path,
                    self._adaptor_runner,
                    shutdown_event=shutdown_event,
                    log_buffer=self._log_buffer,
                )
            _logger.debug(f"Listening on {server_path}")
            server_thread = Thread(
                name="AdaptorRuntimeBackendServerThread",
                target=self._server.serve_forever,  # type: ignore
            )
            server_thread.start()

        except Exception as e:
            _logger.error(f"Error starting in background mode: {e}")
            raise

        try:
            with secure_open(self._connection_file_path, open_mode="w") as conn_file:
                json.dump(
                    ConnectionSettings(server_path),
                    conn_file,
                    cls=DataclassJSONEncoder,
                )
        except OSError as e:
            _logger.error(f"Error writing to connection file: {e}")
            _logger.info("Shutting down server...")
            shutdown_event.set()
            raise
        finally:
            # Block until the shutdown_event is set
            shutdown_event.wait()

            # Shutdown the server
            self._server.shutdown()  # type: ignore

            server_thread.join()

            # Cleanup the connection file and socket for Linux server.
            # We don't need to call the `remove` for the NamedPipe server.
            # NamedPipe servers are managed by Named Pipe File System it is not a regular file.
            # Once all handles are closed, the system automatically cleans up the named pipe.
            files_for_deletion = [self._connection_file_path]
            if OSName.is_posix():
                files_for_deletion.append(server_path)
            for path in files_for_deletion:
                try:
                    os.remove(path)
                except FileNotFoundError:  # pragma: no cover
                    pass  # File is already cleaned up
                except OSError as e:  # pragma: no cover
                    _logger.warning(f"Failed to delete {path}: {e}")

            _logger.info("Background server has been shut down.")
