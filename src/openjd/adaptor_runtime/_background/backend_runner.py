# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import signal
from pathlib import Path
from threading import Thread, Event
import traceback
from types import FrameType
from typing import Callable, List, Optional, Union

from .server_response import ServerResponseGenerator
from .._osname import OSName
from ..adaptors import AdaptorRunner
from .._http import SocketPaths
from .._utils import secure_open

if OSName.is_posix():
    from .http_server import BackgroundHTTPServer
if OSName.is_windows():
    from ...adaptor_runtime_client.named_pipe.named_pipe_helper import NamedPipeHelper
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
        *,
        connection_file_path: Path,
        log_buffer: LogBuffer | None = None,
    ) -> None:
        self._adaptor_runner = adaptor_runner
        self._connection_file_path = connection_file_path

        self._log_buffer = log_buffer
        self._server: Optional[Union[BackgroundHTTPServer, WinBackgroundNamedPipeServer]] = None
        signal.signal(signal.SIGINT, self._sigint_handler)
        if OSName.is_posix():  # pragma: is-windows
            signal.signal(signal.SIGTERM, self._sigint_handler)
        else:  # pragma: is-posix
            signal.signal(signal.SIGBREAK, self._sigint_handler)  # type: ignore[attr-defined]

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """
        Signal handler for interrupt signals.

        This handler is invoked when the process receives a SIGTERM signal on Linux and SIGBREAK signal on Windows.
        It calls the cancel method on the adaptor runner to initiate cancellation workflow.

        Args:
            signum: The number of the received signal.
            frame: The current stack frame.
        """
        _logger.info("Interruption signal received.")
        # Open Job Description dictates that an interrupt signal should trigger cancellation
        if self._server is not None:
            ServerResponseGenerator.submit_task(
                self._server, self._adaptor_runner._cancel, force_immediate=True
            )

    def run(self, *, on_connection_file_written: List[Callable[[], None]] | None = None) -> None:
        """
        Runs the backend logic for background mode.

        This function will start an HTTP server that picks an available port to listen on, write
        that port to a connection file, and listens for HTTP requests until a shutdown is requested
        """
        _logger.info("Running in background daemon mode.")
        shutdown_event: Event = Event()

        if OSName.is_posix():  # pragma: is-windows
            server_path = SocketPaths.for_os().get_process_socket_path(
                ".openjd_adaptor_runtime",
                create_dir=True,
            )
        else:  # pragma: is-posix
            server_path = NamedPipeHelper.generate_pipe_name("AdaptorNamedPipe")

        try:
            if OSName.is_windows():  # pragma: is-posix
                self._server = WinBackgroundNamedPipeServer(
                    server_path,
                    self._adaptor_runner,
                    shutdown_event=shutdown_event,
                    log_buffer=self._log_buffer,
                )
            else:  # pragma: is-windows
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
            with secure_open(
                self._connection_file_path, open_mode="w", encoding="utf-8"
            ) as conn_file:
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
        except Exception as e:
            _logger.critical(f"Unexpected error occurred when writing to connection file: {e}")
            _logger.critical(traceback.format_exc())
            _logger.info("Shutting down server")
            shutdown_event.set()
        else:
            if on_connection_file_written:
                callbacks = list(on_connection_file_written)
                for cb in callbacks:
                    cb()
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
            if OSName.is_posix():  # pragma: is-windows
                files_for_deletion.append(server_path)
            for path in files_for_deletion:
                try:
                    os.remove(path)
                except FileNotFoundError:  # pragma: no cover
                    pass  # File is already cleaned up
                except OSError as e:  # pragma: no cover
                    _logger.warning(f"Failed to delete {path}: {e}")

            _logger.info("Background server has been shut down.")
