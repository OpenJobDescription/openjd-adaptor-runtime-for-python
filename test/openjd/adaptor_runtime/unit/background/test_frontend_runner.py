# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import http.client as http_client
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Generator, Optional
from unittest.mock import MagicMock, call, patch

import pytest

from openjd.adaptor_runtime._background import frontend_runner
from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.adaptors import AdaptorState
from openjd.adaptor_runtime._background.frontend_runner import (
    AdaptorFailedException,
    FrontendRunner,
    HTTPError,
    _wait_for_connection_file,
)
from openjd.adaptor_runtime._background.model import (
    AdaptorStatus,
    BufferedOutput,
    ConnectionSettings,
    HeartbeatResponse,
)


class TestFrontendRunner:
    """
    Tests for the FrontendRunner class
    """

    @pytest.fixture
    def server_name(self) -> str:
        return "/path/to/socket" if OSName.is_posix() else r"\\.\pipe\TestPipe"

    @pytest.fixture
    def connection_settings(self, server_name: str) -> ConnectionSettings:
        return ConnectionSettings(server_name)

    @pytest.fixture(autouse=True)
    def mock_connection_settings(
        self, connection_settings: ConnectionSettings
    ) -> Generator[None, None, None]:
        with patch.object(
            FrontendRunner,
            "connection_settings",
            return_value=connection_settings,
            create=True,
        ):
            yield

    class TestInit:
        """
        Tests for the FrontendRunner.init method
        """

        @pytest.fixture(autouse=True)
        def open_mock(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner, "open") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_path_exists(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.Path, "exists") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_uuid(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.uuid, "uuid4") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_gettempdir(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.tempfile, "gettempdir") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_Popen(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.subprocess, "Popen") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_wait_for_connection_file(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner, "_wait_for_connection_file") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_heartbeat(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.FrontendRunner, "_heartbeat") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_sys_argv(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.sys, "argv", return_value=[]) as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_sys_executable(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.sys, "executable", return_value="executable") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_connection_settings_file_load(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.ConnectionSettingsFileLoader, "load") as m:
                yield m

        @pytest.mark.parametrize(
            argnames="reentry_exe",
            argvalues=[
                (None,),
                (Path("reeentry_exe_value"),),
            ],
        )
        def test_initializes_backend_process(
            self,
            mock_path_exists: MagicMock,
            mock_Popen: MagicMock,
            mock_wait_for_connection_file: MagicMock,
            mock_heartbeat: MagicMock,
            mock_sys_executable: MagicMock,
            mock_sys_argv: MagicMock,
            mock_uuid: MagicMock,
            open_mock: MagicMock,
            caplog: pytest.LogCaptureFixture,
            reentry_exe: Optional[Path],
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            mock_path_exists.return_value = False
            pid = 123
            mock_Popen.return_value.pid = pid
            mock_sys_executable.return_value = "executable"
            mock_sys_argv.return_value = []
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            init_data = {"init": "data"}
            path_mapping_data: dict = {}
            connection_file_path = Path("connection.test")
            runner = FrontendRunner()

            # WHEN
            runner.init(
                adaptor_module=adaptor_module,
                connection_file_path=connection_file_path,
                init_data=init_data,
                path_mapping_data=path_mapping_data,
                reentry_exe=reentry_exe,
            )

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
            mock_path_exists.assert_called_once_with()
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
                    str(connection_file_path),
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
                    str(connection_file_path),
                ]
            expected_args.extend(
                [
                    "--bootstrap-log-file",
                    os.path.join(
                        tempfile.gettempdir(),
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
            mock_wait_for_connection_file.assert_called_once_with(
                str(connection_file_path),
                max_retries=5,
                interval_s=1,
            )
            mock_heartbeat.assert_called_once()

        def test_raises_when_adaptor_module_not_package(self):
            # GIVEN
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = None
            runner = FrontendRunner()

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                runner.init(
                    adaptor_module=adaptor_module,
                    connection_file_path="/path",
                )

            # THEN
            assert raised_exc.match(f"Adaptor module is not a package: {adaptor_module}")

        def test_raises_when_connection_file_exists(
            self,
            mock_path_exists: MagicMock,
        ):
            # GIVEN
            mock_path_exists.return_value = True
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = Path("/path")
            runner = FrontendRunner()

            # WHEN
            with pytest.raises(FileExistsError) as raised_err:
                runner.init(
                    adaptor_module=adaptor_module,
                    connection_file_path=conn_file_path,
                )

            # THEN
            assert raised_err.match(
                re.escape(
                    f"Cannot init a new backend process with an existing connection file at: {conn_file_path}"
                )
            )
            mock_path_exists.assert_called_once_with()

        def test_raises_when_failed_to_create_backend_process(
            self,
            mock_path_exists: MagicMock,
            mock_Popen: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            exc = Exception()
            mock_Popen.side_effect = exc
            mock_path_exists.return_value = False
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = Path("/path")
            runner = FrontendRunner()

            # WHEN
            with pytest.raises(Exception) as raised_exc:
                runner.init(
                    adaptor_module=adaptor_module,
                    connection_file_path=conn_file_path,
                )

            # THEN
            assert raised_exc.value is exc
            assert all(
                m in caplog.messages
                for m in [
                    "Initializing backend process...",
                    "Failed to initialize backend process: ",
                ]
            )
            mock_path_exists.assert_called_once_with()
            mock_Popen.assert_called_once()

        def test_raises_when_connection_file_wait_times_out(
            self,
            mock_path_exists: MagicMock,
            mock_Popen: MagicMock,
            mock_wait_for_connection_file: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level("DEBUG")
            err = TimeoutError()
            mock_wait_for_connection_file.side_effect = err
            mock_path_exists.return_value = False
            pid = 123
            mock_Popen.return_value.pid = pid
            adaptor_module = ModuleType("")
            adaptor_module.__package__ = "package"
            conn_file_path = Path("/path")
            runner = FrontendRunner()

            # WHEN
            with pytest.raises(TimeoutError) as raised_err:
                runner.init(
                    adaptor_module=adaptor_module,
                    connection_file_path=conn_file_path,
                )

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
            mock_path_exists.assert_called_once_with()
            mock_Popen.assert_called_once()
            mock_wait_for_connection_file.assert_called_once_with(
                str(conn_file_path),
                max_retries=5,
                interval_s=1,
            )

    class TestHeartbeat:
        """
        Tests for the FrontendRunner._heartbeat method
        """

        @pytest.fixture(autouse=True)
        def mock_json_load(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.json, "load") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_dataclass_mapper_map(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.DataclassMapper, "map") as m:
                yield m

        @pytest.fixture(autouse=True)
        def mock_send_request(self) -> Generator[MagicMock, None, None]:
            with patch.object(frontend_runner.FrontendRunner, "_send_request") as m:
                yield m

        def test_sends_heartbeat(
            self,
            mock_send_request: MagicMock,
            mock_dataclass_mapper_map: MagicMock,
            mock_json_load: MagicMock,
        ):
            # GIVEN
            if OSName.is_windows():
                mock_send_request.return_value = {"body": '{"key1": "value1"}'}
            mock_response = mock_send_request.return_value
            runner = FrontendRunner()

            # WHEN
            response = runner._heartbeat()

            # THEN
            assert response is mock_dataclass_mapper_map.return_value
            if OSName.is_posix():
                mock_json_load.assert_called_once_with(mock_response.fp)
                mock_dataclass_mapper_map.assert_called_once_with(mock_json_load.return_value)
            else:
                mock_dataclass_mapper_map.assert_called_once_with({"key1": "value1"})
            mock_send_request.assert_called_once_with("GET", "/heartbeat", params=None)

        def test_sends_heartbeat_with_ack_id(
            self,
            mock_send_request: MagicMock,
            mock_dataclass_mapper_map: MagicMock,
            mock_json_load: MagicMock,
        ):
            # GIVEN
            ack_id = "ack_id"
            if OSName.is_windows():
                mock_send_request.return_value = {"body": '{"key1": "value1"}'}
            mock_response = mock_send_request.return_value
            runner = FrontendRunner()

            # WHEN
            response = runner._heartbeat(ack_id)

            # THEN
            assert response is mock_dataclass_mapper_map.return_value
            if OSName.is_posix():
                mock_json_load.assert_called_once_with(mock_response.fp)
                mock_dataclass_mapper_map.assert_called_once_with(mock_json_load.return_value)
            else:
                mock_dataclass_mapper_map.assert_called_once_with({"key1": "value1"})
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
            runner = FrontendRunner(heartbeat_interval=heartbeat_interval)

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
            runner = FrontendRunner()

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
            runner = FrontendRunner()

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
            runner = FrontendRunner()

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
            runner = FrontendRunner()

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
            runner = FrontendRunner()

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
            runner = FrontendRunner()

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
        def test_sends_request(
            self,
            mock_request: MagicMock,
            mock_getresponse: MagicMock,
            connection_settings: ConnectionSettings,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            runner = FrontendRunner(connection_settings=connection_settings)

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
            connection_settings: ConnectionSettings,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            exc = http_client.HTTPException()
            mock_getresponse.side_effect = exc
            method = "GET"
            path = "/path"
            runner = FrontendRunner(connection_settings=connection_settings)

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
            connection_settings: ConnectionSettings,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            mock_response.status = 500
            mock_response.reason = "Something went wrong"
            method = "GET"
            path = "/path"
            runner = FrontendRunner(connection_settings=connection_settings)

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
        def test_formats_query_string(
            self,
            mock_request: MagicMock,
            mock_getresponse: MagicMock,
            connection_settings: ConnectionSettings,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            params = {"first param": 1, "second_param": ["one", "two three"]}
            runner = FrontendRunner(connection_settings=connection_settings)

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
        def test_sends_body(
            self,
            mock_request: MagicMock,
            mock_getresponse: MagicMock,
            connection_settings: ConnectionSettings,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            json = {"the": "body"}
            runner = FrontendRunner(connection_settings=connection_settings)

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

        @pytest.fixture
        def connection_settings(self) -> ConnectionSettings:
            return ConnectionSettings("\\\\.\\pipe")

        @pytest.fixture
        def runner(self, connection_settings: ConnectionSettings) -> FrontendRunner:
            return FrontendRunner(connection_settings=connection_settings)

        def test_sends_request(
            self,
            mock_read_from_pipe: MagicMock,
            mock_response: str,
            runner: FrontendRunner,
        ):
            # GIVEN
            method = "GET"
            path = "/path"

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
            runner: FrontendRunner,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            import pywintypes

            error_instance = pywintypes.error(1, "FunctionName", "An error message")
            mock_read_from_pipe.side_effect = error_instance
            method = "GET"
            path = "/path"

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
            runner: FrontendRunner,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"

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
            runner: FrontendRunner,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            params = {"first param": 1, "second_param": ["one", "two three"]}

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
            runner: FrontendRunner,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            method = "GET"
            path = "/path"
            json_body = {"the": "body"}

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
            runner = FrontendRunner()

            # WHEN
            runner._sigint_handler(MagicMock(), MagicMock())

            # THEN
            signal_mock.assert_any_call(signal.SIGINT, runner._sigint_handler)
            if OSName.is_posix():
                signal_mock.assert_any_call(signal.SIGTERM, runner._sigint_handler)
            else:
                signal_mock.assert_any_call(signal.SIGBREAK, runner._sigint_handler)  # type: ignore[attr-defined]
            cancel_mock.assert_called_once()


class TestWaitForConnectionFile:
    """
    Tests for the _wait_for_connection_file method
    """

    @patch.object(frontend_runner.ConnectionSettingsFileLoader, "load")
    @patch.object(frontend_runner, "open")
    @patch.object(frontend_runner.time, "sleep")
    @patch.object(frontend_runner.os.path, "exists")
    def test_waits_for_file(
        self,
        mock_exists: MagicMock,
        mock_sleep: MagicMock,
        open_mock: MagicMock,
        mock_conn_file_loader_load: MagicMock,
    ):
        # GIVEN
        filepath = "/path"
        max_retries = 9999
        interval = 0.01
        mock_exists.side_effect = [False, True]
        err = IOError()
        open_mock.side_effect = [err, MagicMock()]
        mock_conn_file_loader_load.return_value = ConnectionSettings("/server")

        # WHEN
        _wait_for_connection_file(filepath, max_retries, interval)

        # THEN
        mock_exists.assert_has_calls([call(filepath)] * 2)
        mock_sleep.assert_has_calls([call(interval)] * 3)
        open_mock.assert_has_calls([call(filepath, mode="r", encoding="utf-8")] * 2)

    @patch.object(frontend_runner.time, "sleep")
    @patch.object(frontend_runner.os.path, "exists")
    def test_raises_when_retries_reached(
        self,
        mock_exists: MagicMock,
        mock_sleep: MagicMock,
    ):
        # GIVEN
        filepath = "/path"
        max_retries = 0
        interval = 0.01
        mock_exists.return_value = False

        # WHEN
        with pytest.raises(TimeoutError) as raised_err:
            _wait_for_connection_file(filepath, max_retries, interval)

        # THEN
        assert raised_err.match(f"Timed out waiting for File '{filepath}' to exist")
        mock_exists.assert_called_once_with(filepath)
        mock_sleep.assert_not_called()
