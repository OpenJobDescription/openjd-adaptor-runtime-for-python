# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import signal
from queue import Queue
from threading import Thread
from types import FrameType
from typing import Optional

from ..adaptors import AdaptorRunner
from .._http import SocketDirectories
from .._utils import secure_open
from .http_server import BackgroundHTTPServer
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
        self._http_server: Optional[BackgroundHTTPServer] = None
        signal.signal(signal.SIGINT, self._sigint_handler)
        signal.signal(signal.SIGTERM, self._sigint_handler)

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """Signal handler that is invoked when the process receives a SIGINT/SIGTERM"""
        _logger.info("Interruption signal recieved.")
        # OpenJD dictates that a SIGTERM/SIGINT results in a cancel workflow being
        # kicked off.
        if self._http_server is not None:
            self._http_server.submit(self._adaptor_runner._cancel, force_immediate=True)

    def run(self) -> None:
        """
        Runs the backend logic for background mode.

        This function will start an HTTP server that picks an available port to listen on, write
        that port to a connection file, and listens for HTTP requests until a shutdown is requested
        """
        _logger.info("Running in background daemon mode.")

        queue: Queue = Queue()

        socket_path = SocketDirectories.for_os().get_process_socket_path("runtime", create_dir=True)

        try:
            self._http_server = BackgroundHTTPServer(
                socket_path,
                self._adaptor_runner,
                cancel_queue=queue,
                log_buffer=self._log_buffer,
            )
        except Exception as e:
            _logger.error(f"Error starting in background mode: {e}")
            raise

        _logger.debug(f"Listening on {socket_path}")
        http_thread = Thread(
            name="AdaptorRuntimeBackendHttpThread", target=self._http_server.serve_forever
        )
        http_thread.start()

        try:
            with secure_open(self._connection_file_path, open_mode="w") as conn_file:
                json.dump(
                    ConnectionSettings(socket_path),
                    conn_file,
                    cls=DataclassJSONEncoder,
                )
        except OSError as e:
            _logger.error(f"Error writing to connection file: {e}")
            _logger.info("Shutting down server...")
            queue.put(True)
            raise
        finally:
            # Block until the cancel queue has been pushed to
            queue.get()

            # Shutdown the server
            self._http_server.shutdown()
            http_thread.join()

            # Cleanup the connection file and socket
            for path in [self._connection_file_path, socket_path]:
                try:
                    os.remove(path)
                except FileNotFoundError:  # pragma: no cover
                    pass  # File is already cleaned up
                except OSError as e:  # pragma: no cover
                    _logger.warning(f"Failed to delete {path}: {e}")

            _logger.info("HTTP server has shutdown.")
