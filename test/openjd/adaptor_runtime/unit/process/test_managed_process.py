# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from typing import List, Optional
from unittest import mock

import pytest

import openjd.adaptor_runtime.process._logging_subprocess as logging_subprocess
import openjd.adaptor_runtime.process._managed_process as managed_process
from openjd.adaptor_runtime.process import ManagedProcess


class TestManagedProcess(object):
    """Unit tests for ManagedProcess"""

    @pytest.fixture(autouse=True)
    def mock_popen(self):
        with mock.patch.object(logging_subprocess.subprocess, "Popen") as popen_mock:
            yield popen_mock

    @pytest.fixture(autouse=True)
    def mock_stream_logger(self):
        with mock.patch.object(logging_subprocess, "StreamLogger") as stream_logger:
            stdout_logger_mock = mock.Mock()
            stderr_logger_mock = mock.Mock()
            stream_logger.side_effect = [stdout_logger_mock, stderr_logger_mock]
            yield stream_logger

    startup_dirs = [
        pytest.param("", ["Hello World!"], "/path/for/startup", id="EmptyExecutable"),
        pytest.param("echo", ["Hello World!"], "/path/for/startup", id="EchoExecutable"),
        pytest.param("echo", [""], "/path/for/startup", id="EmptyArguments"),
        pytest.param("echo", ["Hello World!"], "", id="EmptyStartupDir"),
        pytest.param("echo", ["Hello World!"], None, id="NoStartupDir"),
        pytest.param(
            "echo",
            ["Hello World!"],
            "/path/for/startup",
            id="RandomStartupDir",
        ),
    ]

    @pytest.mark.parametrize("executable, arguments, startup_dir", startup_dirs)
    @mock.patch.object(managed_process, "LoggingSubprocess", autospec=True)
    def test_run(
        self,
        mock_LoggingSubprocess: mock.Mock,
        executable: str,
        arguments: List[str],
        startup_dir: str,
    ):
        class FakeManagedProcess(ManagedProcess):
            def __init__(self, run_data: dict):
                super(FakeManagedProcess, self).__init__(run_data)

            def get_executable(self) -> str:
                return executable

            def get_arguments(self) -> List[str]:
                return arguments

            def get_startup_directory(self) -> Optional[str]:
                return startup_dir

        mp = FakeManagedProcess({})
        mp.run()

        mock_LoggingSubprocess.assert_called_once_with(
            args=[executable] + arguments,
            startup_directory=startup_dir,
            stdout_handler=None,
            stderr_handler=None,
        )
