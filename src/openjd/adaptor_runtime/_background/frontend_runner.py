# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import http.client as http_client
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
import urllib.parse as urllib_parse
from threading import Event
from types import FrameType
from types import ModuleType
from typing import Optional, Dict

from .._osname import OSName
from ..process._logging import _ADAPTOR_OUTPUT_LEVEL
from .model import (
    AdaptorState,
    AdaptorStatus,
    BufferedOutput,
    ConnectionSettings,
    DataclassJSONEncoder,
    DataclassMapper,
    HeartbeatResponse,
)

if OSName.is_windows():
    from openjd.adaptor_runtime._named_pipe.named_pipe_helper import NamedPipeHelper
    import pywintypes

_logger = logging.getLogger(__name__)


class FrontendRunner:
    """
    Class that runs the frontend logic in background mode.
    """

    def __init__(
        self,
        connection_file_path: str,
        *,
        timeout_s: float = 5.0,
        heartbeat_interval: float = 1.0,
    ) -> None:
        """
        Args:
            connection_file_path (str): Absolute path to the connection file.
            timeout_s (float, optional): Timeout for HTTP requests, in seconds. Defaults to 5.
            heartbeat_interval (float, optional): Interval between heartbeats, in seconds.
                Defaults to 1.
        """
        self._timeout_s = timeout_s
        self._heartbeat_interval = heartbeat_interval
        self._connection_file_path = connection_file_path
        self._canceled = Event()
        signal.signal(signal.SIGINT, self._sigint_handler)
        if OSName.is_posix():  # pragma: is-windows
            signal.signal(signal.SIGTERM, self._sigint_handler)
        else:  # pragma: is-posix
            signal.signal(signal.SIGBREAK, self._sigint_handler)  # type: ignore[attr-defined]

    def init(
        self,
        adaptor_module: ModuleType,
        init_data: dict | None = None,
        path_mapping_data: dict | None = None,
        reentry_exe: Path | None = None,
    ) -> None:
        """
        Creates the backend process then sends a heartbeat request to verify that it has started
        successfully.

        Args:
            adaptor_module (ModuleType): The module of the adaptor running the runtime.
            init_data (dict): Data to pass to the adaptor during initialization.
            path_mapping_data (dict): Path mapping rules to make available to the adaptor while it's running.
            reentry_exe (Path): The path to the binary executable that for adaptor reentry.
        """
        if adaptor_module.__package__ is None:
            raise Exception(f"Adaptor module is not a package: {adaptor_module}")

        if os.path.exists(self._connection_file_path):
            raise FileExistsError(
                "Cannot init a new backend process with an existing connection file at: "
                + self._connection_file_path
            )

        if init_data is None:
            init_data = {}

        if path_mapping_data is None:
            path_mapping_data = {}

        _logger.info("Initializing backend process...")
        if reentry_exe is None:
            args = [
                sys.executable,
                "-m",
                adaptor_module.__package__,
            ]
        else:
            args = [str(reentry_exe)]
        args.extend(
            [
                "daemon",
                "_serve",
                "--connection-file",
                self._connection_file_path,
                "--init-data",
                json.dumps(init_data),
                "--path-mapping-rules",
                json.dumps(path_mapping_data),
            ]
        )
        try:
            process = subprocess.Popen(
                args,
                shell=False,
                close_fds=True,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            _logger.error(f"Failed to initialize backend process: {e}")
            raise
        _logger.info(f"Started backend process. PID: {process.pid}")

        # Wait for backend process to create connection file
        try:
            _wait_for_file(self._connection_file_path, timeout_s=5)
        except TimeoutError:
            _logger.error(
                "Backend process failed to write connection file in time at: "
                + self._connection_file_path
            )
            raise

        # Heartbeat to ensure backend process is listening for requests
        _logger.info("Verifying connection to backend...")
        self._heartbeat()
        _logger.info("Connected successfully")

    def run(self, run_data: dict) -> None:
        """
        Sends a run request to the backend
        """
        self._send_request("PUT", "/run", json_body=run_data)
        self._heartbeat_until_state_complete(AdaptorState.RUN)

    def start(self) -> None:
        """
        Sends a start request to the backend
        """
        self._send_request("PUT", "/start")
        self._heartbeat_until_state_complete(AdaptorState.START)

    def stop(self) -> None:
        """
        Sends an end request to the backend
        """
        self._send_request("PUT", "/stop")
        # The backend calls end then cleanup on the adaptor, so we wait until cleanup is complete.
        self._heartbeat_until_state_complete(AdaptorState.CLEANUP)

    def shutdown(self) -> None:
        """
        Sends a shutdown request to the backend
        """
        self._send_request("PUT", "/shutdown")

    def cancel(self) -> None:
        """
        Sends a cancel request to the backend
        """
        self._send_request("PUT", "/cancel")
        self._canceled.set()

    def _heartbeat(self, ack_id: str | None = None) -> HeartbeatResponse:
        """
        Sends a heartbeat request to the backend.

        Args:
            ack_id (str): The heartbeat output ID to ACK. Defaults to None.
        """
        params: dict[str, str] | None = {"ack_id": ack_id} if ack_id else None
        response = self._send_request("GET", "/heartbeat", params=params)
        body = json.load(response.fp) if OSName.is_posix() else json.loads(response["body"])  # type: ignore
        return DataclassMapper(HeartbeatResponse).map(body)

    def _heartbeat_until_state_complete(self, state: AdaptorState) -> None:
        """
        Heartbeats with the backend until it transitions to the specified state and is idle.

        Args:
            state (AdaptorState): The final state the adaptor should be in.

        Raises:
            AdaptorFailedException: Raised when the adaptor reports a failure.
        """
        failure_message = None
        ack_id = None
        while True:
            _logger.debug("Sending heartbeat request...")
            heartbeat = self._heartbeat(ack_id)
            _logger.debug(f"Heartbeat response: {json.dumps(heartbeat, cls=DataclassJSONEncoder)}")
            for line in heartbeat.output.output.splitlines():
                _logger.log(_ADAPTOR_OUTPUT_LEVEL, line)

            if heartbeat.failed:
                failure_message = heartbeat.output.output

            ack_id = heartbeat.output.id
            if (
                heartbeat.state in [state, AdaptorState.CANCELED]
                and heartbeat.status == AdaptorStatus.IDLE
            ):
                break
            else:
                if not self._canceled.is_set():
                    self._canceled.wait(timeout=self._heartbeat_interval)
                else:
                    # We've been canceled. Do a small sleep to give it time to take effect.
                    time.sleep(0.25)

        # Send one last heartbeat to ACK the previous heartbeat output if any
        if ack_id != BufferedOutput.EMPTY:  # pragma: no branch
            _logger.debug("ACKing last heartbeat...")
            heartbeat = self._heartbeat(ack_id)

        # Raise a failure exception if the adaptor failed
        if failure_message:
            raise AdaptorFailedException(failure_message)

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> http_client.HTTPResponse | Dict:
        if OSName.is_windows():  # pragma: is-posix
            if params:
                # This is used for aligning to the Linux's behavior in order to reuse the code in handler.
                # In linux, query string params will always be put in a list.
                params = {key: [value] for key, value in params.items()}
            try:
                response = NamedPipeHelper.send_named_pipe_request(
                    self.connection_settings.socket,
                    self._timeout_s,
                    method,
                    path,
                    json_body=json_body,
                    params=params,
                )
                status = response["status"]
                if 400 <= status < 600:
                    errmsg = f"Received unexpected HTTP status code {status}: {response['body']}"
                    _logger.error(errmsg)
                    raise HTTPError(response, errmsg)
            except pywintypes.error as e:
                _logger.error(f"Failed to send {path} request: {e}")
                raise
            return response
        else:  # pragma: is-windows
            return self._send_linux_request(
                method,
                path,
                params=params if params else None,
                json_body=json_body if json_body else None,
            )

    def _send_linux_request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> http_client.HTTPResponse:  # pragma: is-windows
        conn = UnixHTTPConnection(self.connection_settings.socket, timeout=self._timeout_s)

        if params:
            query_str = urllib_parse.urlencode(params, doseq=True)
            path = f"{path}?{query_str}"

        body = json.dumps(json_body) if json_body else None

        conn.request(method, path, body=body)
        try:
            response = conn.getresponse()
        except http_client.HTTPException as e:
            _logger.error(f"Failed to send {path} request: {e}")
            raise
        finally:
            conn.close()

        if response.status >= 400 and response.status < 600:
            errmsg = f"Received unexpected HTTP status code {response.status}: {response.reason}"
            _logger.error(errmsg)
            raise HTTPError(response, errmsg)

        return response

    @property
    def connection_settings(self) -> ConnectionSettings:
        """
        Gets the lazy-loaded connection settings.
        """
        if not hasattr(self, "_connection_settings"):
            self._connection_settings = _load_connection_settings(self._connection_file_path)
        return self._connection_settings

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """Signal handler that is invoked when the process receives a SIGINT/SIGTERM"""
        _logger.info("Interruption signal recieved.")
        # OpenJD dictates that a SIGTERM/SIGINT results in a cancel workflow being
        # kicked off.
        self.cancel()


def _load_connection_settings(path: str) -> ConnectionSettings:
    try:
        with open(path) as conn_file:
            loaded_settings = json.load(conn_file)
    except OSError as e:
        _logger.error(f"Failed to open connection file: {e}")
        raise
    except json.JSONDecodeError as e:
        _logger.error(f"Failed to decode connection file: {e}")
        raise
    return DataclassMapper(ConnectionSettings).map(loaded_settings)


def _wait_for_file(filepath: str, timeout_s: float, interval_s: float = 1) -> None:
    """
    Waits for a file at the specified path to exist and to be openable.

    Args:
        filepath (str): The file path to check.
        timeout_s (float): The max duration to wait before timing out, in seconds.
        interval_s (float, optional): The interval between checks, in seconds. Default is 0.01s.

    Raises:
        TimeoutError: Raised when the file does not exist after timeout_s seconds.
    """

    def _wait():
        if time.time() - start < timeout_s:
            time.sleep(interval_s)
        else:
            raise TimeoutError(f"Timed out after {timeout_s}s waiting for file at {filepath}")

    start = time.time()
    while not os.path.exists(filepath):
        _wait()

    while True:
        # Wait before opening to give the backend time to open it first
        _wait()
        try:
            open(filepath, mode="r").close()
            break
        except IOError:
            # File is not available yet
            pass


class AdaptorFailedException(Exception):
    pass


class HTTPError(http_client.HTTPException):
    response: http_client.HTTPResponse | Dict

    def __init__(self, response: http_client.HTTPResponse | Dict, *args: object) -> None:
        super().__init__(*args)
        self.response = response


class UnixHTTPConnection(http_client.HTTPConnection):
    """
    Specialization of http.client.HTTPConnection class that uses a UNIX domain socket.
    """

    def __init__(self, host, **kwargs):
        self.socket_path = host
        kwargs.pop("strict", None)  # Removed in py3
        super(UnixHTTPConnection, self).__init__("localhost", **kwargs)

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # type: ignore[attr-defined]
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock
