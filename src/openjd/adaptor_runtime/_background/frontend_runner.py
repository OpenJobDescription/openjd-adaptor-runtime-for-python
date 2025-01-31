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
import tempfile
import time
import urllib.parse as urllib_parse
import uuid
from pathlib import Path
from threading import Event
from types import FrameType
from types import ModuleType
from typing import Optional, Callable, Dict

from .._osname import OSName
from ..process._logging import _ADAPTOR_OUTPUT_LEVEL
from .._utils._constants import _OPENJD_ENV_STDOUT_PREFIX, _OPENJD_ADAPTOR_SOCKET_ENV
from .loaders import ConnectionSettingsFileLoader
from .model import (
    AdaptorState,
    AdaptorStatus,
    BufferedOutput,
    ConnectionSettings,
    DataclassJSONEncoder,
    DataclassMapper,
    HeartbeatResponse,
)

_FRONTEND_RUNNER_REQUEST_TIMEOUT: float = 5.0

if OSName.is_windows():
    from ...adaptor_runtime_client.named_pipe.named_pipe_helper import NamedPipeHelper
    import pywintypes

_logger = logging.getLogger(__name__)


class ConnectionSettingsNotProvidedError(Exception):
    """Raised when the connection settings are required but are missing"""

    pass


class FrontendRunner:
    """
    Class that runs the frontend logic in background mode.
    """

    connection_settings: ConnectionSettings | None

    def __init__(
        self,
        *,
        timeout_s: float = _FRONTEND_RUNNER_REQUEST_TIMEOUT,
        heartbeat_interval: float = 1.0,
        connection_settings: ConnectionSettings | None = None,
    ) -> None:
        """
        Args:
            timeout_s (float, optional): Timeout for HTTP requests, in seconds. Defaults to 5.
            heartbeat_interval (float, optional): Interval between heartbeats, in seconds.
                Defaults to 1.
            connection_settings (ConnectionSettings, optional): The connection settings to use.
                This option is not required for the "init" command, but is required for everything
                else. Defaults to None.
        """
        self._timeout_s = timeout_s
        self._heartbeat_interval = heartbeat_interval
        self.connection_settings = connection_settings

        self._canceled = Event()
        signal.signal(signal.SIGINT, self._sigint_handler)
        if OSName.is_posix():  # pragma: is-windows
            signal.signal(signal.SIGTERM, self._sigint_handler)
        else:  # pragma: is-posix
            signal.signal(signal.SIGBREAK, self._sigint_handler)  # type: ignore[attr-defined]

    def init(
        self,
        *,
        adaptor_module: ModuleType,
        connection_file_path: Path,
        init_data: dict | None = None,
        path_mapping_data: dict | None = None,
        reentry_exe: Path | None = None,
    ) -> None:
        """
        Creates the backend process then sends a heartbeat request to verify that it has started
        successfully.

        Args:
            adaptor_module (ModuleType): The module of the adaptor running the runtime.
            connection_file_path (Path): The path to the connection file to use for establishing
                a connection with the backend process.
            init_data (dict): Data to pass to the adaptor during initialization.
            path_mapping_data (dict): Path mapping rules to make available to the adaptor while it's running.
            reentry_exe (Path): The path to the binary executable that for adaptor reentry.
        """
        if adaptor_module.__package__ is None:
            raise Exception(f"Adaptor module is not a package: {adaptor_module}")

        if connection_file_path.exists():
            raise FileExistsError(
                "Cannot init a new backend process with an existing connection file at: "
                + str(connection_file_path)
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
                "--init-data",
                json.dumps(init_data),
                "--path-mapping-rules",
                json.dumps(path_mapping_data),
                "--connection-file",
                str(connection_file_path),
            ]
        )

        bootstrap_id = uuid.uuid4()
        bootstrap_log_dir = tempfile.gettempdir()
        bootstrap_log_path = os.path.join(
            bootstrap_log_dir, f"adaptor-runtime-background-bootstrap-{bootstrap_id}.log"
        )
        args.extend(["--bootstrap-log-file", bootstrap_log_path])

        _logger.info(f"Running process with args: {args}")
        bootstrap_output_path = os.path.join(
            bootstrap_log_dir, f"adaptor-runtime-background-bootstrap-output-{bootstrap_id}.log"
        )
        output_log_file = open(bootstrap_output_path, mode="w+", encoding="utf-8")
        try:
            process = subprocess.Popen(
                args,
                shell=False,
                close_fds=True,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=output_log_file,
                stderr=output_log_file,
            )
        except Exception as e:
            _logger.error(f"Failed to initialize backend process: {e}")
            raise
        _logger.info(f"Started backend process. PID: {process.pid}")

        # Wait for backend process to create connection file
        try:
            _wait_for_connection_file(str(connection_file_path), max_retries=5, interval_s=1)
        except TimeoutError:
            _logger.error(
                "Backend process failed to write connection file in time at: "
                + str(connection_file_path)
            )

            exit_code = process.poll()
            if exit_code is not None:
                _logger.info(f"Backend process exited with code: {exit_code}")
            else:
                _logger.info("Backend process is still running")

            raise
        finally:
            # Close file handle to prevent further writes
            # At this point, we have all the logs/output we need from the bootstrap
            output_log_file.close()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

            with open(bootstrap_output_path, mode="r", encoding="utf-8") as f:
                bootstrap_output = f.readlines()
            _logger.info("========== BEGIN BOOTSTRAP OUTPUT CONTENTS ==========")
            for line in bootstrap_output:
                _logger.info(line.strip())
            _logger.info("========== END BOOTSTRAP OUTPUT CONTENTS ==========")

            _logger.info(f"Checking for bootstrap logs at '{bootstrap_log_path}'")
            try:
                with open(bootstrap_log_path, mode="r", encoding="utf-8") as f:
                    bootstrap_logs = f.readlines()
            except Exception as e:
                _logger.error(f"Failed to get bootstrap logs at '{bootstrap_log_path}': {e}")
            else:
                _logger.info("========== BEGIN BOOTSTRAP LOG CONTENTS ==========")
                for line in bootstrap_logs:
                    _logger.info(line.strip())
                _logger.info("========== END BOOTSTRAP LOG CONTENTS ==========")

        # Load up connection settings for the heartbeat requests
        self.connection_settings = ConnectionSettingsFileLoader(connection_file_path).load()

        # Heartbeat to ensure backend process is listening for requests
        _logger.info("Verifying connection to backend...")
        self._heartbeat()
        _logger.info("Connected successfully")

        # Output the socket path to the environment via OpenJD environments
        _logger.info(
            f"{_OPENJD_ENV_STDOUT_PREFIX}{_OPENJD_ADAPTOR_SOCKET_ENV}={self.connection_settings.socket}"
        )

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
        if not self.connection_settings:
            raise ConnectionSettingsNotProvidedError(
                "Connection settings are required to send requests, but none were provided"
            )

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
        if not self.connection_settings:
            raise ConnectionSettingsNotProvidedError(
                "Connection settings are required to send requests, but none were provided"
            )

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

        if 400 <= response.status < 600:
            errmsg = f"Received unexpected HTTP status code {response.status}: {response.reason}"
            _logger.error(errmsg)
            raise HTTPError(response, errmsg)

        return response

    def _sigint_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        """
        Signal handler for interrupt signals.

        This handler is invoked when the process receives a SIGTERM signal on Linux and SIGBREAK signal on Windows.
        It calls the cancel method on the adaptor runner to initiate cancellation workflow.

        Args:
            signum: The number of the received signal.
            frame: The current stack frame.
        """

        _logger.info("Interrupt signal received.")

        # Open Job Description dictates that an interrupt signal should trigger cancellation
        self.cancel()


def _wait_for_connection_file(
    filepath: str, max_retries: int, interval_s: float = 1
) -> ConnectionSettings:
    """
    Waits for a connection file at the specified path to exist, be openable, and have connection settings.

    Args:
        filepath (str): The file path to check.
        max_retries (int): The max number of retries before timing out.
        interval_s (float, optional): The interval between checks, in seconds. Default is 0.01s.

    Raises:
        TimeoutError: Raised when the file does not exist after timeout_s seconds.
    """
    wait_for(
        description=f"File '{filepath}' to exist",
        predicate=lambda: os.path.exists(filepath),
        interval_s=interval_s,
        max_retries=max_retries,
    )

    # Wait before opening to give the backend time to open it first
    time.sleep(interval_s)

    def file_is_openable() -> bool:
        try:
            with open(filepath, mode="r", encoding="utf-8"):
                pass
        except IOError:
            # File is not available yet
            return False
        else:
            return True

    wait_for(
        description=f"File '{filepath}' to be openable",
        predicate=file_is_openable,
        interval_s=interval_s,
        max_retries=max_retries,
    )

    def connection_file_loadable() -> bool:
        try:
            ConnectionSettingsFileLoader(Path(filepath)).load()
        except Exception:
            return False
        else:
            return True

    wait_for(
        description=f"File '{filepath}' to have valid ConnectionSettings",
        predicate=connection_file_loadable,
        interval_s=interval_s,
        max_retries=max_retries,
    )

    return ConnectionSettingsFileLoader(Path(filepath)).load()


def wait_for(
    *,
    description: str,
    predicate: Callable[[], bool],
    interval_s: float,
    max_retries: int | None = None,
) -> None:
    if max_retries is not None:
        assert max_retries >= 0, "max_retries must be a non-negative integer"
    assert interval_s > 0, "interval_s must be a positive number"

    _logger.info(f"Waiting for {description}")
    retry_count = 0
    while not predicate():
        if max_retries is not None and retry_count >= max_retries:
            raise TimeoutError(f"Timed out waiting for {description}")

        _logger.info(f"Retrying in {interval_s}s...")
        retry_count += 1
        time.sleep(interval_s)


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
