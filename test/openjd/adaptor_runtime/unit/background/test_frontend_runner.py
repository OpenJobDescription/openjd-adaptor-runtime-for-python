# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import http.client as http_client
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Generator, Optional
from unittest.mock import MagicMock, PropertyMock, call, mock_open, patch

import pytest

import openjd.adaptor_runtime._background.frontend_runner as frontend_runner
from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.adaptors import AdaptorState
from openjd.adaptor_runtime._background.frontend_runner import (
    AdaptorFailedException,
    FrontendRunner,
    HTTPError,
    _load_connection_settings,
    _wait_for_file,
)
from openjd.adaptor_runtime._background.model import (
    AdaptorStatus,
    BufferedOutput,
    ConnectionSettings,
    DataclassMapper,
    HeartbeatResponse,
)


class TestFrontendRunner:
    """
    Tests for the FrontendRunner class
    """

    @pytest.fixture
    def server_name(self) -> str:
        return "/path/to/socket" if OSName.is_posix() else r"\\.\pipe\TestPipe"

    @pytest.fixture(autouse=True)
    def mock_connection_settings(self, server_name: str) -> Generator[MagicMock, None, None]:
        with patch.object(FrontendRunner, "connection_settings", new_callable=PropertyMock) as mock:
            mock.return_value = ConnectionSettings(server_name)
            yield mock

    class TestInit:
        """
        Tests for the FrontendRunner.init method
        """

        @pytest.fixture(autouse=True)
        def open_mock(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner, "open") as m:
                yield m

        @pytest.mark.parametrize(
            argnames="reentry_exe",
            argvalues=[
                (None,),
                (Path("reeentry_exe_value"),),
            ],
        )
        @patch.object(frontend_runner.uuid, "uuid4", return_value="uuid")
        @patch.object(frontend_runner.sys, "argv")
        @patch.object(frontend_runner.sys, "executable")
        @patch.object(frontend_runner.json, "dumps")
        @patch.object(FrontendRunner, "_heartbeat")
        @patch.object(frontend_runner, "_wait_for_file")
        @patch.object(frontend_runner.subprocess, "Popen")
        @patch.object(frontend_runner.os.path, "exists")
        def test_initializes_backend_process(
            self,
            mock_exists: MagicMock,
            mock_Popen: MagicMock,
            mock_wait_for_file: MagicMock,
            mock_heartbeat: MagicMock,
            mock_json_dumps: MagicMock,
            mock_sys_executable: MagicMock,
            mock_sys_argv: MagicMock,
            mock_uuid: MagicMock,
            open_mock: MagicMock,
            caplog: pytest.LogCaptureFixture,
            reentry_exe: Optional[Path],
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            mock_json_dumps.return_value = "test"
            mock_exists.return_value = False
            pid = 123
            mock_Popen.return_value.pid = pid
            mock_sys_executable.return_value = "executable"
            mock_sys_argv.return_value = []
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = "/path"
            init_data = {"init": "data"}
            path_mapping_data: dict = {}
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            runner.init(adaptor_module, init_data, path_mapping_data, reentry_exe)

            # THEN
            assert all(
                m in caplog.messages
                for m in [
                    "Initializing backend process...",
                    f"Started backend process. PID: {pid}",
                    "Verifying connection to backend...",
                    "Connected successfully",
                ]
            )
            mock_exists.assert_called_once_with(conn_file_path)
            if reentry_exe is None:
                expected_args = [
                    sys.executable,
                    "-m",
                    adaptor_module.__package__,
                    "daemon",
                    "_serve",
                    "--init-data",
                    json.dumps(init_data),
                    "--path-mapping-rules",
                    json.dumps(path_mapping_data),
                    "--connection-file",
                    conn_file_path,
                ]
            else:
                expected_args = [
                    str(reentry_exe),
                    "daemon",
                    "_serve",
                    "--init-data",
                    json.dumps(init_data),
                    "--path-mapping-rules",
                    json.dumps(path_mapping_data),
                    "--connection-file",
                    conn_file_path,
                ]
            expected_args.extend(
                [
                    "--log-file",
                    os.path.join(
                        os.path.dirname(conn_file_path),
                        f"adaptor-runtime-background-bootstrap-{mock_uuid.return_value}.log",
                    ),
                ]
            )
            mock_Popen.assert_called_once_with(
                expected_args,
                shell=False,
                close_fds=True,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=open_mock.return_value,
                stderr=open_mock.return_value,
            )
            mock_wait_for_file.assert_called_once_with(conn_file_path, timeout_s=5)
            mock_heartbeat.assert_called_once()

        def test_raises_when_adaptor_module_not_package(self):
            # GIVEN
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = None
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                runner.init(adaptor_module)

            # THEN
            assert raised_exc.match(f"Adaptor module is not a package: {adaptor_module}")

        @patch.object(frontend_runner.os.path, "exists")
        def test_raises_when_connection_file_exists(
            self,
            mock_exists: MagicMock,
        ):
            # GIVEN
            mock_exists.return_value = True
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = "/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with pytest.raises(FileExistsError) as raised_err:
                runner.init(adaptor_module)

            # THEN
            assert raised_err.match(
                "Cannot init a new backend process with an existing connection file at: "
                + conn_file_path
            )
            mock_exists.assert_called_once_with(conn_file_path)

        @patch.object(frontend_runner.subprocess, "Popen")
        @patch.object(frontend_runner.os.path, "exists")
        def test_raises_when_failed_to_create_backend_process(
            self,
            mock_exists: MagicMock,
            mock_Popen: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            exc = Exception()
            mock_Popen.side_effect = exc
            mock_exists.return_value = False
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = "/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                runner.init(adaptor_module)

            # THEN
            assert raised_exc.value is exc
            assert all(
                m in caplog.messages
                for m in [
                    "Initializing backend process...",
                    "Failed to initialize backend process: ",
                ]
            )
            mock_exists.assert_called_once_with(conn_file_path)
            mock_Popen.assert_called_once()

        @patch.object(frontend_runner, "_wait_for_file")
        @patch.object(frontend_runner.subprocess, "Popen")
        @patch.object(frontend_runner.os.path, "exists")
        def test_raises_when_connection_file_wait_times_out(
            self,
            mock_exists: MagicMock,
            mock_Popen: MagicMock,
            mock_wait_for_file: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            err = TimeoutError()
            mock_wait_for_file.side_effect = err
            mock_exists.return_value = False
            pid = 123
            mock_Popen.return_value.pid = pid
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = "/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with pytest.raises(TimeoutError) as raised_err:
                runner.init(adaptor_module)

            # THEN
            assert raised_err.value is err
            assert all(
                m in caplog.messages
                for m in [
                    "Initializing backend process...",
                    f"Started backend process. PID: {pid}",
                    f"Backend process failed to write connection file in time at: {conn_file_path}",
                ]
            )
            mock_exists.assert_called_once_with(conn_file_path)
            mock_Popen.assert_called_once()
            mock_wait_for_file.assert_called_once_with(conn_file_path, timeout_s=5)

    class TestHeartbeat:
        """
        Tests for the FrontendRunner._heartbeat method
        """

        @patch.object(frontend_runner.json, "load")
        @patch.object(DataclassMapper, "map")
        @patch.object(FrontendRunner, "_send_request")
        def test_sends_heartbeat(
            self,
            mock_send_request: MagicMock,
            mock_map: MagicMock,
            mock_json_load: MagicMock,
        ):
            # GIVEN
            if OSName.is_windows():
                mock_send_request.return_value = {"body": '{"key1": "value1"}'}
            mock_response = mock_send_request.return_value
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            response = runner._heartbeat()

            # THEN
            assert response is mock_map.return_value
            if OSName.is_posix():
                mock_json_load.assert_called_once_with(mock_response.fp)
                mock_map.assert_called_once_with(mock_json_load.return_value)
            else:
                mock_map.assert_called_once_with({"key1": "value1"})
            mock_send_request.assert_called_once_with("GET", "/heartbeat", params=None)

        @patch.object(frontend_runner.json, "load")
        @patch.object(DataclassMapper, "map")
        @patch.object(FrontendRunner, "_send_request")
        def test_sends_heartbeat_with_ack_id(
            self,
            mock_send_request: MagicMock,
            mock_map: MagicMock,
            mock_json_load: MagicMock,
        ):
            # GIVEN
            ack_id = "ack_id"
            if OSName.is_windows():
                mock_send_request.return_value = {"body": '{"key1": "value1"}'}
            mock_response = mock_send_request.return_value
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            response = runner._heartbeat(ack_id)

            # THEN
            assert response is mock_map.return_value
            if OSName.is_posix():
                mock_json_load.assert_called_once_with(mock_response.fp)
                mock_map.assert_called_once_with(mock_json_load.return_value)
            else:
                mock_map.assert_called_once_with({"key1": "value1"})
            mock_send_request.assert_called_once_with(
                "GET", "/heartbeat", params={"ack_id": ack_id}
            )

    class TestHeartbeatUntilComplete:
        """
        Tests for FrontendRunner._heartbeat_until_state_complete
        """

        @patch.object(FrontendRunner, "_heartbeat")
        @patch("openjd.adaptor_runtime._background.frontend_runner.Event")
        def test_heartbeats_until_complete(
            self, mock_event_class: MagicMock, mock_heartbeat: MagicMock
        ):
            # GIVEN
            state = AdaptorState.RUN
            ack_id = "id"
            mock_heartbeat.side_effect = [
                HeartbeatResponse(
                    state=state,
                    status=status,
                    output=BufferedOutput(id=ack_id, output="output"),
                )
                # Working -> Idle -> Idle (for final ACK heartbeat)
                for status in [AdaptorStatus.WORKING, AdaptorStatus.IDLE, AdaptorStatus.IDLE]
            ]
            mock_event = MagicMock()
            mock_event_class.return_value = mock_event
            mock_event.wait = MagicMock()
            mock_event.is_set = MagicMock(return_value=False)
            heartbeat_interval = 1
            runner = FrontendRunner(
                connection_file_path="/tmp/connection.json", heartbeat_interval=heartbeat_interval
            )

            # WHEN
            runner._heartbeat_until_state_complete(state)

            # THEN
            mock_heartbeat.assert_has_calls([call(None), call(ack_id)])
            mock_event.wait.assert_called_once_with(timeout=heartbeat_interval)

        @patch.object(FrontendRunner, "_heartbeat")
        def test_raises_when_adaptor_fails(self, mock_heartbeat: MagicMock) -> None:
            # GIVEN
            state = AdaptorState.RUN
            ack_id = "id"
            failure_message = "failed"
            mock_heartbeat.side_effect = [
                HeartbeatResponse(
                    state=state,
                    status=AdaptorStatus.IDLE,
                    output=BufferedOutput(id=ack_id, output=failure_message),
                    failed=True,
                ),
                HeartbeatResponse(
                    state=state,
                    status=AdaptorStatus.IDLE,
                    output=BufferedOutput(id="id2", output="output2"),
                    failed=False,
                ),
            ]
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            with pytest.raises(AdaptorFailedException) as raised_exc:
                runner._heartbeat_until_state_complete(state)

            # THEN
            mock_heartbeat.assert_has_calls([call(None), call(ack_id)])
            assert raised_exc.match(failure_message)

    class TestShutdown:
        """
        Tests for the FrontendRunner.shutdown method
        """

        @patch.object(FrontendRunner, "_send_request")
        def test_sends_shutdown(self, mock_send_request: MagicMock):
            # GIVEN
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            runner.shutdown()

            # THEN
            mock_send_request.assert_called_once_with("PUT", "/shutdown")

    class TestRun:
        """
        Tests for the FrontendRunner.run method
        """

        @patch.object(FrontendRunner, "_heartbeat_until_state_complete")
        @patch.object(FrontendRunner, "_send_request")
        def test_sends_run(
            self,
            mock_send_request: MagicMock,
            mock_heartbeat_until_state_complete: MagicMock,
        ):
            # GIVEN
            run_data = {"run": "data"}
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            runner.run(run_data)

            # THEN
            mock_send_request.assert_called_once_with("PUT", "/run", json_body=run_data)
            mock_heartbeat_until_state_complete.assert_called_once_with(AdaptorState.RUN)

    class TestStart:
        """
        Tests for the FrontendRunner.start method
        """

        @patch.object(FrontendRunner, "_heartbeat_until_state_complete")
        @patch.object(FrontendRunner, "_send_request")
        def test_sends_start(
            self,
            mock_send_request: MagicMock,
            mock_heartbeat_until_state_complete: MagicMock,
        ):
            # GIVEN
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            runner.start()

            # THEN
            mock_send_request.assert_called_once_with("PUT", "/start")
            mock_heartbeat_until_state_complete.assert_called_once_with(AdaptorState.START)

    class TestEnd:
        """
        Tests for the FrontendRunner.end method
        """

        @patch.object(FrontendRunner, "_heartbeat_until_state_complete")
        @patch.object(FrontendRunner, "_send_request")
        def test_sends_end(
            self,
            mock_send_request: MagicMock,
            mock_heartbeat_until_state_complete: MagicMock,
        ):
            # GIVEN
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            runner.stop()

            # THEN
            mock_send_request.assert_called_once_with("PUT", "/stop")
            mock_heartbeat_until_state_complete.assert_called_once_with(AdaptorState.CLEANUP)

    class TestCancel:
        """
        Tests for the FrontendRunner.cancel method
        """

        @patch.object(FrontendRunner, "_send_request")
        def test_sends_cancel(
            self,
            mock_send_request: MagicMock,
        ):
            # GIVEN
            runner = FrontendRunner(connection_file_path="/tmp/connection.json")

            # WHEN
            runner.cancel()

            # THEN
            mock_send_request.assert_called_once_with("PUT", "/cancel")

    @pytest.mark.skipif(not OSName.is_posix(), reason="Posix-specific tests")
    class TestSendRequestInLinux:
        """
        Tests for the FrontendRunner._send_request method
        """

        @pytest.fixture
        def mock_response(self) -> MagicMock:
            return MagicMock()

        @pytest.fixture
        def mock_getresponse(self, mock_response: MagicMock) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.UnixHTTPConnection, "getresponse") as mock:
                mock.return_value = mock_response
                mock_response.status = 200
                yield mock

        @patch.object(frontend_runner.UnixHTTPConnection, "request")
        def test_sends_request(self, mock_request: MagicMock, mock_getresponse: MagicMock):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = "/conn/file/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            response = runner._send_request(method, path)

            # THEN
            mock_request.assert_called_once_with(
                method,
                path,
                body=None,
            )
            mock_getresponse.assert_called_once()
            assert response is mock_getresponse.return_value

        @patch.object(frontend_runner.UnixHTTPConnection, "request")
        def test_raises_when_request_fails(
            self,
            mock_request: MagicMock,
            mock_getresponse: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            exc = http_client.HTTPException()
            mock_getresponse.side_effect = exc
            method = "GET"
            path = "/path"
            conn_file_path = "/conn/file/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with pytest.raises(http_client.HTTPException) as raised_exc:
                runner._send_request(method, path)

            # THEN
            assert raised_exc.value is exc
            assert f"Failed to send {path} request: " in caplog.text
            mock_request.assert_called_once_with(
                method,
                path,
                body=None,
            )
            mock_getresponse.assert_called_once()

        @patch.object(frontend_runner.UnixHTTPConnection, "request")
        def test_raises_when_error_response_received(
            self,
            mock_request: MagicMock,
            mock_getresponse: MagicMock,
            mock_response: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            mock_response.status = 500
            mock_response.reason = "Something went wrong"
            method = "GET"
            path = "/path"
            conn_file_path = "/conn/file/path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with pytest.raises(HTTPError) as raised_err:
                runner._send_request(method, path)

            # THEN
            errmsg = f"Received unexpected HTTP status code {mock_response.status}: " + str(
                mock_response.reason
            )
            assert errmsg in caplog.text
            assert raised_err.match(re.escape(errmsg))
            mock_request.assert_called_once_with(
                method,
                path,
                body=None,
            )
            mock_getresponse.assert_called_once()

        @patch.object(frontend_runner.UnixHTTPConnection, "request")
        def test_formats_query_string(self, mock_request: MagicMock, mock_getresponse: MagicMock):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = "/conn/file/path"
            params = {"first param": 1, "second_param": ["one", "two three"]}
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            response = runner._send_request(method, path, params=params)

            # THEN
            mock_request.assert_called_once_with(
                method,
                f"{path}?first+param=1&second_param=one&second_param=two+three",
                body=None,
            )
            mock_getresponse.assert_called_once()
            assert response is mock_getresponse.return_value

        @patch.object(frontend_runner.UnixHTTPConnection, "request")
        def test_sends_body(self, mock_request: MagicMock, mock_getresponse: MagicMock):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = "/conn/file/path"
            json = {"the": "body"}
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            response = runner._send_request(method, path, json_body=json)

            # THEN
            mock_request.assert_called_once_with(
                method,
                path,
                body='{"the": "body"}',
            )
            mock_getresponse.assert_called_once()
            assert response is mock_getresponse.return_value

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
    class TestSendRequestInWindows:
        """
        Tests for the FrontendRunner._send_request method in Windows
        """

        @pytest.fixture
        def mock_response(self) -> str:
            return '{"status": 200, "body": "message"}'

        @pytest.fixture
        def mock_read_from_pipe(self, mock_response: MagicMock) -> Generator[MagicMock, None, None]:
            with patch.object(
                frontend_runner.NamedPipeHelper, "read_from_pipe"
            ) as mock_read_from_pipe:
                mock_read_from_pipe.return_value = mock_response
                yield mock_read_from_pipe

        def test_sends_request(
            self,
            mock_read_from_pipe: MagicMock,
            mock_response: str,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = r"C:\conn\file\path"

            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with patch.object(
                frontend_runner.NamedPipeHelper, "write_to_pipe"
            ) as mock_write_to_pipe:
                with patch.object(
                    frontend_runner.NamedPipeHelper, "establish_named_pipe_connection"
                ) as mock_establish_named_pipe_connection:
                    response = runner._send_request(method, path)

            # THEN
            mock_write_to_pipe.assert_called_once_with(
                mock_establish_named_pipe_connection(), '{"method": "GET", "path": "/path"}'
            )
            mock_read_from_pipe.assert_called_once()
            assert response == json.loads(mock_response)

        def test_raises_when_request_fails(
            self,
            mock_read_from_pipe: MagicMock,
            mock_response: str,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            import pywintypes

            error_instance = pywintypes.error(1, "FunctionName", "An error message")
            mock_read_from_pipe.side_effect = error_instance
            method = "GET"
            path = "/path"
            conn_file_path = r"C:\conn\file\path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with patch.object(
                frontend_runner.NamedPipeHelper, "write_to_pipe"
            ) as mock_write_to_pipe:
                with patch.object(
                    frontend_runner.NamedPipeHelper, "establish_named_pipe_connection"
                ) as mock_establish_named_pipe_connection:
                    with pytest.raises(pywintypes.error) as raised_exc:
                        runner._send_request(method, path)

            # THEN
            assert raised_exc.value is error_instance
            assert f"Failed to send {path} request: " in caplog.text
            mock_write_to_pipe.assert_called_once_with(
                mock_establish_named_pipe_connection(), '{"method": "GET", "path": "/path"}'
            )
            mock_read_from_pipe.assert_called_once()

        def test_raises_when_error_response_received(
            self,
            mock_response: str,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = r"C:\conn\file\path"
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with patch.object(
                frontend_runner.NamedPipeHelper, "read_from_pipe"
            ) as mock_read_from_pipe_error:
                with patch.object(
                    frontend_runner.NamedPipeHelper, "write_to_pipe"
                ) as mock_write_to_pipe:
                    with patch.object(
                        frontend_runner.NamedPipeHelper, "establish_named_pipe_connection"
                    ) as mock_establish_named_pipe_connection:
                        with pytest.raises(HTTPError) as raised_err:
                            mock_read_from_pipe_error.return_value = (
                                '{"status": 500, "body": "some errors"}'
                            )
                            runner._send_request(method, path)

            # THEN
            errmsg = "Received unexpected HTTP status code 500"
            assert errmsg in caplog.text
            assert raised_err.match(re.escape(errmsg))
            mock_write_to_pipe.assert_called_once_with(
                mock_establish_named_pipe_connection(), '{"method": "GET", "path": "/path"}'
            )
            mock_read_from_pipe_error.assert_called_once()

        def test_formats_query_string(
            self,
            mock_read_from_pipe,
            mock_response: str,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = r"C:\conn\file\path"
            params = {"first param": 1, "second_param": ["one", "two three"]}
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with patch.object(
                frontend_runner.NamedPipeHelper, "write_to_pipe"
            ) as mock_write_to_pipe:
                with patch.object(
                    frontend_runner.NamedPipeHelper, "establish_named_pipe_connection"
                ) as mock_establish_named_pipe_connection:
                    response = runner._send_request(method, path, params=params)

            # THEN
            mock_write_to_pipe.assert_called_once_with(
                mock_establish_named_pipe_connection(),
                '{"method": "GET", "path": "/path", "params": "{\\"first param\\": [1], \\"second_param\\": [[\\"one\\", \\"two three\\"]]}"}',
            )
            mock_read_from_pipe.assert_called_once()
            assert response == json.loads(mock_response)

        def test_sends_body(
            self,
            mock_read_from_pipe,
            mock_response: str,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            conn_file_path = r"C:\conn\file\path"
            json_body = {"the": "body"}
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            with patch.object(
                frontend_runner.NamedPipeHelper, "write_to_pipe"
            ) as mock_write_to_pipe:
                with patch.object(
                    frontend_runner.NamedPipeHelper, "establish_named_pipe_connection"
                ) as mock_establish_named_pipe_connection:
                    response = runner._send_request(method, path, json_body=json_body)

            # THEN
            mock_write_to_pipe.assert_called_once_with(
                mock_establish_named_pipe_connection(),
                '{"method": "GET", "path": "/path", "body": "{\\"the\\": \\"body\\"}"}',
            )
            mock_read_from_pipe.assert_called_once()
            assert response == json.loads(mock_response)

    class TestSignalHandling:
        @patch.object(FrontendRunner, "cancel")
        @patch.object(frontend_runner.signal, "signal")
        def test_hook(self, signal_mock: MagicMock, cancel_mock: MagicMock) -> None:
            # Test that we create the signal hook, and that it initiates a cancelation
            # as expected.

            # GIVEN
            conn_file_path = os.path.join(os.sep, "path", "to", "conn_file")
            runner = FrontendRunner(connection_file_path=conn_file_path)

            # WHEN
            runner._sigint_handler(MagicMock(), MagicMock())

            # THEN
            signal_mock.assert_any_call(signal.SIGINT, runner._sigint_handler)
            if OSName.is_posix():
                signal_mock.assert_any_call(signal.SIGTERM, runner._sigint_handler)
            else:
                signal_mock.assert_any_call(signal.SIGBREAK, runner._sigint_handler)  # type: ignore[attr-defined]
            cancel_mock.assert_called_once()

    class TestConnectionFileCompat:
        @pytest.fixture(autouse=True)
        def open_mock(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner, "open") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_uuid(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.uuid, "uuid4", return_value="uuid") as m:
                yield m

        @pytest.mark.parametrize(
            argnames=["connection_file", "working_dir"],
            argvalues=[
                ["path", "dir"],
                [None, None],
            ],
            ids=["both provided", "neither provided"],
        )
        def test_rejects_not_exactly_one_of_connection_file_and_working_dir(
            self,
            connection_file: str | None,
            working_dir: str | None,
        ) -> None:
            # GIVEN
            with pytest.raises(RuntimeError) as raised_err:
                # WHEN
                FrontendRunner(
                    connection_file_path=connection_file,
                    working_dir=working_dir,
                )

            # THEN
            assert (
                f"Expected exactly one of 'connection_file_path' or 'working_dir', but got: connection_file_path={connection_file} working_dir={working_dir}"
                == str(raised_err.value)
            )

        @patch.object(frontend_runner, "_wait_for_file")
        @patch.object(frontend_runner.os.path, "exists", return_value=False)
        @patch.object(frontend_runner.subprocess, "Popen")
        def test_init_provides_connection_file_arg(
            self,
            mock_popen: MagicMock,
            mock_exists: MagicMock,
            mock_wait_for_file: MagicMock,
            mock_uuid: MagicMock,
            open_mock: MagicMock,
        ) -> None:
            # GIVEN
            connection_file = os.path.join(os.sep, "path", "to", "connection.json")
            runner = FrontendRunner(connection_file_path=connection_file)
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"

            with patch.object(runner, "_heartbeat"):
                # WHEN
                runner.init(adaptor_module)

            # THEN
            mock_popen.assert_called_once_with(
                [
                    sys.executable,
                    "-m",
                    adaptor_module.__package__,
                    "daemon",
                    "_serve",
                    "--init-data",
                    json.dumps({}),
                    "--path-mapping-rules",
                    json.dumps({}),
                    "--connection-file",
                    connection_file,
                    "--log-file",
                    os.path.join(
                        os.path.dirname(connection_file),
                        f"adaptor-runtime-background-bootstrap-{mock_uuid.return_value}.log",
                    ),
                ],
                shell=False,
                close_fds=True,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=open_mock.return_value,
                stderr=open_mock.return_value,
            )

        @patch.object(frontend_runner, "_wait_for_file")
        @patch.object(frontend_runner.os.path, "exists", return_value=False)
        @patch.object(frontend_runner.subprocess, "Popen")
        def test_init_provides_working_dir_arg(
            self,
            mock_popen: MagicMock,
            mock_exists: MagicMock,
            mock_wait_for_file: MagicMock,
            mock_uuid: MagicMock,
            open_mock: MagicMock,
        ) -> None:
            # GIVEN
            working_dir = os.path.join(os.sep, "path", "to", "working")
            runner = FrontendRunner(working_dir=working_dir)
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"

            with patch.object(runner, "_heartbeat"):
                # WHEN
                runner.init(adaptor_module)

            # THEN
            mock_popen.assert_called_once_with(
                [
                    sys.executable,
                    "-m",
                    adaptor_module.__package__,
                    "daemon",
                    "_serve",
                    "--init-data",
                    json.dumps({}),
                    "--path-mapping-rules",
                    json.dumps({}),
                    "--working-dir",
                    working_dir,
                    "--log-file",
                    os.path.join(
                        working_dir,
                        f"adaptor-runtime-background-bootstrap-{mock_uuid.return_value}.log",
                    ),
                ],
                shell=False,
                close_fds=True,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=open_mock.return_value,
                stderr=open_mock.return_value,
            )


class TestLoadConnectionSettings:
    """
    Tests for the _load_connection_settings method
    """

    @patch.object(DataclassMapper, "map")
    def test_loads_settings(
        self,
        mock_map: MagicMock,
    ):
        # GIVEN
        filepath = "/path"
        connection_settings = {"port": 123}

        # WHEN
        with patch.object(
            frontend_runner, "open", mock_open(read_data=json.dumps(connection_settings))
        ):
            _load_connection_settings(filepath)

        # THEN
        mock_map.assert_called_once_with(connection_settings)

    @patch.object(frontend_runner, "open")
    def test_raises_when_file_open_fails(
        self,
        open_mock: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        filepath = "/path"
        err = OSError()
        open_mock.side_effect = err

        # WHEN
        with pytest.raises(OSError) as raised_err:
            _load_connection_settings(filepath)

        # THEN
        assert raised_err.value is err
        assert "Failed to open connection file: " in caplog.text

    @patch.object(frontend_runner.json, "load")
    def test_raises_when_json_decode_fails(
        self,
        mock_json_load: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        filepath = "/path"
        err = json.JSONDecodeError("", "", 0)
        mock_json_load.side_effect = err

        # WHEN
        with pytest.raises(json.JSONDecodeError) as raised_err:
            with patch.object(frontend_runner, "open", mock_open()):
                _load_connection_settings(filepath)

        # THEN
        assert raised_err.value is err
        assert "Failed to decode connection file: " in caplog.text


class TestWaitForFile:
    """
    Tests for the _wait_for_file method
    """

    @patch.object(frontend_runner, "open")
    @patch.object(frontend_runner.time, "time")
    @patch.object(frontend_runner.time, "sleep")
    @patch.object(frontend_runner.os.path, "exists")
    def test_waits_for_file(
        self,
        mock_exists: MagicMock,
        mock_sleep: MagicMock,
        mock_time: MagicMock,
        open_mock: MagicMock,
    ):
        # GIVEN
        filepath = "/path"
        timeout = sys.float_info.max
        interval = 0.01
        mock_time.side_effect = [1, 2, 3, 4]
        mock_exists.side_effect = [False, True]
        err = IOError()
        open_mock.side_effect = [err, MagicMock()]

        # WHEN
        _wait_for_file(filepath, timeout, interval)

        # THEN
        assert mock_time.call_count == 4
        mock_exists.assert_has_calls([call(filepath)] * 2)
        mock_sleep.assert_has_calls([call(interval)] * 3)
        open_mock.assert_has_calls([call(filepath, mode="r")] * 2)

    @patch.object(frontend_runner.time, "time")
    @patch.object(frontend_runner.time, "sleep")
    @patch.object(frontend_runner.os.path, "exists")
    def test_raises_when_timeout_reached(
        self,
        mock_exists: MagicMock,
        mock_sleep: MagicMock,
        mock_time: MagicMock,
    ):
        # GIVEN
        filepath = "/path"
        timeout = 0
        interval = 0.01
        mock_time.side_effect = [1, 2]
        mock_exists.side_effect = [False]

        # WHEN
        with pytest.raises(TimeoutError) as raised_err:
            _wait_for_file(filepath, timeout, interval)

        # THEN
        assert raised_err.match(f"Timed out after {timeout}s waiting for file at {filepath}")
        assert mock_time.call_count == 2
        mock_exists.assert_called_once_with(filepath)
        mock_sleep.assert_not_called()


@patch.object(frontend_runner, "_load_connection_settings")
def test_connection_settings_lazy_loads(mock_load_connection_settings: MagicMock):
    # GIVEN
    filepath = "/path"
    expected = ConnectionSettings("/socket")
    mock_load_connection_settings.return_value = expected
    runner = FrontendRunner(connection_file_path=filepath)

    # Assert the internal connection settings var is not set yet
    assert not hasattr(runner, "_connection_settings")

    # WHEN
    actual = runner.connection_settings

    # THEN
    assert actual is expected
    assert runner._connection_settings is expected
