# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

import json
import os
import pathlib
import signal
from typing import Generator
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import pytest

import openjd.adaptor_runtime._background.backend_runner as backend_runner
from openjd.adaptor_runtime._background.backend_runner import BackendRunner
from openjd.adaptor_runtime._background.model import ConnectionSettings, DataclassJSONEncoder
from openjd.adaptor_runtime._osname import OSName


class TestBackendRunner:
    """
    Tests for the BackendRunner class
    """

    @pytest.fixture(autouse=True)
    def socket_path(self, tmp_path: pathlib.Path) -> Generator[str, None, None]:
        if OSName.is_posix():
            with patch.object(backend_runner.SocketPaths, "get_process_socket_path") as mock:
                path = os.path.join(tmp_path, "socket", "1234")
                mock.return_value = path

                yield path

                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        else:
            with patch.object(backend_runner.NamedPipeHelper, "generate_pipe_name") as mock:
                path = "\\\\.\\pipe\\AdaptorNamedPipe_1234"
                mock.return_value = path

                yield path

    @pytest.fixture(autouse=True)
    def mock_server_cls(self) -> Generator[MagicMock, None, None]:
        if OSName.is_posix():
            with patch.object(backend_runner, "BackgroundHTTPServer", autospec=True) as mock:
                yield mock
        else:
            with patch.object(
                backend_runner, "WinBackgroundNamedPipeServer", autospec=True
            ) as mock:
                yield mock

    @patch.object(backend_runner.json, "dump")
    @patch.object(backend_runner.os, "remove")
    @patch.object(backend_runner, "Event")
    @patch.object(backend_runner, "Thread")
    def test_run(
        self,
        mock_thread: MagicMock,
        mock_event: MagicMock,
        mock_os_remove: MagicMock,
        mock_json_dump: MagicMock,
        mock_server_cls: MagicMock,
        socket_path: str,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        caplog.set_level("DEBUG")
        conn_file = pathlib.Path(os.sep) / "path" / "to" / "conn_file"
        connection_settings = {"socket": socket_path}
        adaptor_runner = Mock()
        runner = BackendRunner(adaptor_runner, connection_file_path=conn_file)

        # WHEN
        open_mock: MagicMock
        with patch.object(
            backend_runner,
            "secure_open",
            mock_open(read_data=json.dumps(connection_settings)),
        ) as open_mock:
            runner.run()

        # THEN
        assert caplog.messages == [
            "Running in background daemon mode.",
            f"Listening on {socket_path}",
            "Background server has been shut down.",
        ]
        mock_server_cls.assert_called_once_with(
            socket_path,
            adaptor_runner,
            mock_event.return_value,
            log_buffer=None,
        )
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        open_mock.assert_called_once_with(conn_file, open_mode="w", encoding="utf-8")
        mock_json_dump.assert_called_once_with(
            ConnectionSettings(socket_path),
            open_mock.return_value,
            cls=DataclassJSONEncoder,
        )
        mock_thread.return_value.join.assert_called_once()
        if OSName.is_posix():
            mock_os_remove.assert_has_calls([call(conn_file), call(socket_path)])
        else:
            mock_os_remove.assert_has_calls([call(conn_file)])

    def test_run_raises_when_http_server_fails_to_start(
        self,
        mock_server_cls: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        caplog.set_level("DEBUG")
        exc = Exception()
        mock_server_cls.side_effect = exc
        runner = BackendRunner(
            Mock(),
            connection_file_path=pathlib.Path(os.path.sep) / "tmp" / "connection.json",
        )

        # WHEN
        with pytest.raises(Exception) as raised_exc:
            runner.run()

        # THEN
        assert raised_exc.value is exc
        assert caplog.messages == [
            "Running in background daemon mode.",
            "Error starting in background mode: ",
        ]

    @patch.object(backend_runner, "secure_open")
    @patch.object(backend_runner.os, "remove")
    @patch.object(backend_runner, "Event")
    @patch.object(backend_runner, "Thread")
    def test_run_raises_when_writing_connection_file_fails(
        self,
        mock_thread: MagicMock,
        mock_event: MagicMock,
        mock_os_remove: MagicMock,
        open_mock: MagicMock,
        socket_path: str,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        caplog.set_level("DEBUG")
        err = OSError()
        open_mock.side_effect = err
        conn_file = pathlib.Path(os.sep) / "path" / "to" / "conn_file"
        adaptor_runner = Mock()
        runner = BackendRunner(adaptor_runner, connection_file_path=conn_file)

        # WHEN
        with pytest.raises(OSError) as raised_err:
            runner.run()

        # THEN
        assert raised_err.value is err
        mock_event.return_value.set.assert_called_once()
        assert caplog.messages == [
            "Running in background daemon mode.",
            f"Listening on {socket_path}",
            "Error writing to connection file: ",
            "Shutting down server...",
            "Background server has been shut down.",
        ]
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        open_mock.assert_called_once_with(conn_file, open_mode="w", encoding="utf-8")
        mock_thread.return_value.join.assert_called_once()
        if OSName.is_posix():
            mock_os_remove.assert_has_calls([call(conn_file), call(socket_path)])
        else:
            mock_os_remove.assert_has_calls([call(conn_file)])

    @patch.object(backend_runner.signal, "signal")
    @patch.object(backend_runner.ServerResponseGenerator, "submit_task")
    def test_signal_hook(self, mock_submit, signal_mock: MagicMock) -> None:
        # Test that we create the signal hook, and that it initiates a cancelation
        # as expected.

        # GIVEN
        conn_file_path = pathlib.Path(os.sep) / "path" / "to" / "conn_file"
        adaptor_runner = Mock()
        runner = BackendRunner(adaptor_runner, connection_file_path=conn_file_path)
        server_mock = MagicMock()
        submit_mock = MagicMock()
        server_mock.submit = submit_mock
        runner._server = server_mock

        # WHEN
        runner._sigint_handler(MagicMock(), MagicMock())

        # THEN
        signal_mock.assert_any_call(signal.SIGINT, runner._sigint_handler)
        if OSName.is_posix():
            signal_mock.assert_any_call(signal.SIGTERM, runner._sigint_handler)
        else:
            signal_mock.assert_any_call(signal.SIGBREAK, runner._sigint_handler)  # type: ignore[attr-defined]
        mock_submit.assert_called_with(server_mock, adaptor_runner._cancel, force_immediate=True)
