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
    import win32file
    import win32pipe
    import pywintypes
    import winerror
    from openjd.adaptor_runtime._background.named_pipe_helper import NamedPipeHelper

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
        # TODO: Need to figure out how to set up the timeout for the Windows NamedPipe Server
        #  For Namedpipe, we can only set a timeout on the server side not on the client side.
        self._timeout_s = timeout_s
        self._heartbeat_interval = heartbeat_interval
        self._connection_file_path = connection_file_path
        self._canceled = Event()
        # TODO: Signal handler needed to be checked in Windows
        #  The current plan is to use CTRL_BREAK.
        if OSName.is_posix():
            signal.signal(signal.SIGINT, self._sigint_handler)
            signal.signal(signal.SIGTERM, self._sigint_handler)

    def init(
        self, adaptor_module: ModuleType, init_data: dict = {}, path_mapping_data: dict = {}
    ) -> None:
        """
        Creates the backend process then sends a heartbeat request to verify that it has started
        successfully.

        Args:
            adaptor_module (ModuleType): The module of the adaptor running the runtime.
            init_data (dict): Data to pass to the adaptor during initialization.
            path_mapping_data (dict): Path mapping rules to make available to the adaptor while it's running.
        """
        if adaptor_module.__package__ is None:
            raise Exception(f"Adaptor module is not a package: {adaptor_module}")

        if os.path.exists(self._connection_file_path):
            raise FileExistsError(
                "Cannot init a new backend process with an existing connection file at: "
                + self._connection_file_path
            )

        _logger.info("Initializing backend process...")
        args = [
            sys.executable,
            "-m",
            adaptor_module.__package__,
            "daemon",
            "_serve",
            "--connection-file",
            self._connection_file_path,
            "--init-data",
            json.dumps(init_data),
            "--path-mapping-rules",
            json.dumps(path_mapping_data),
        ]
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
            # TODO: Need to investigate why more time is required in Windows
            _wait_for_file(self._connection_file_path, timeout_s=5 if OSName.is_posix() else 10)
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
        if OSName.is_windows():
            return self._send_windows_request(
                method,
                path,
                params=params if params else None,
                json_body=json_body if json_body else None,
            )
        else:
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
    ) -> http_client.HTTPResponse:
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

    def _send_windows_request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> Dict:
        start_time = time.time()
        # Wait for the server pipe to become available.
        handle = None
        while handle is None:
            try:
                handle = win32file.CreateFile(
                    self.connection_settings.socket,  # pipe name
                    # Give the read / write permission
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,  # Disable the sharing Mode
                    None,  # TODO: Need to set the security descriptor. Right now, None means default security
                    win32file.OPEN_EXISTING,  # Open existing pipe
                    0,  # No Additional flags
                    None,  # A valid handle to a template file, This parameter is ignored when opening an existing pipe.
                )
            except pywintypes.error as e:
                # NamedPipe server may be not ready,
                # or no additional resource to create new instance and need to wait for previous connection release
                if e.args[0] in [winerror.ERROR_FILE_NOT_FOUND, winerror.ERROR_PIPE_BUSY]:
                    duration = time.time() - start_time
                    time.sleep(0.1)
                    # Check timeout limit
                    if duration > self._timeout_s:
                        _logger.error(
                            f"NamedPipe Server readiness timeout. Duration: {duration} seconds, "
                            f"Timeout limit: {self._timeout_s} seconds."
                        )
                        raise e
                    continue
                _logger.error(f"Could not open pipe: {e}")
                raise e

        # Switch to message-read mode for the pipe. This ensures that each write operation is treated as a
        # distinct message. For example, a single write operation like "Hello from client." will be read
        # entirely in one request, avoiding partial reads like "Hello fr".
        win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_MESSAGE, None, None)

        # Send a message to the server.
        message_dict = {
            "method": method,
            "body": json.dumps(json_body),
            "path": path,
        }
        if params:
            message_dict["params"] = json.dumps(params)
        message = json.dumps(message_dict)
        NamedPipeHelper.write_to_pipe(handle, message)
        _logger.debug(f"Message sent from frontend process: {message}")
        result = NamedPipeHelper.read_from_pipe(handle)
        handle.close()
        return json.loads(result)

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
    response: http_client.HTTPResponse

    def __init__(self, response: http_client.HTTPResponse, *args: object) -> None:
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
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock
