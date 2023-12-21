# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging
import os
import re
import sys
import time
from logging import DEBUG
from unittest import mock

import pytest

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.app_handlers import RegexCallback, RegexHandler
from openjd.adaptor_runtime.process import LoggingSubprocess
from openjd.adaptor_runtime.process._logging_subprocess import _STDERR_LEVEL, _STDOUT_LEVEL


class TestIntegrationLoggingSubprocess(object):
    """Integration tests for LoggingSubprocess"""

    expected_stop_params = [
        pytest.param(0, ["Immediately stopping process (pid="], id="StopProcessImmediately"),
        pytest.param(
            2,
            [
                f"Sending the {'SIGTERM' if OSName.is_posix() else 'SIGBREAK'} signal to pid=",
                "now sending the SIGKILL signal.",
            ],
            id="StopProcessWhenSIGTERMFails",
        ),
    ]

    @pytest.mark.timeout(5)
    @pytest.mark.parametrize("grace_period, expected_output", expected_stop_params)
    def test_stop_process(self, grace_period, expected_output, caplog: pytest.LogCaptureFixture):
        """
        Testing that we stop the process immediately and after SIGTERM fails.
        """
        test_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "scripts", "signals_test.py"
        )
        caplog.set_level(DEBUG)
        p = LoggingSubprocess(args=[sys.executable, test_file, "False"])

        # This is because we are giving the subprocess time to load and
        # register the sigterm signal handler with the OS.
        while "Starting signals_test.py Script" not in caplog.text:
            time.sleep(0.2)

        p.terminate(grace_period)

        for output in expected_output:
            assert output in caplog.text

    @pytest.mark.timeout(5)
    def test_terminate_process(self, caplog):
        """
        Testing that the process was terminated successfully. This means that the process ended
        when SIGTERM was sent and SIGKILL was not needed.
        """
        test_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "scripts", "signals_test.py"
        )
        caplog.set_level(DEBUG)
        p = LoggingSubprocess(args=[sys.executable, test_file, "True"])

        # This is because we are giving the subprocess time to load and ignore the sigterm signal.
        while "Starting signals_test.py Script" not in caplog.text:
            time.sleep(0.2)

        p.terminate(5)  # Sometimes, when this is 1 second the process doesn't terminate in time.
        signal_name = "SIGTERM" if OSName.is_posix() else "SIGBREAK"
        assert (
            f"Sending the {signal_name} signal to pid=" in caplog.text
        )  # Asserting the SIGTERM signal was sent to the subprocess
        assert (
            f"Trapped: {signal_name}" in caplog.text
        )  # Asserting the SIGTERM was received by the subprocess.
        assert (
            "now sending the SIGKILL signal." not in caplog.text
        )  # Asserting the SIGKILL signal was not sent to the subprocess

    startup_dir_params = [
        pytest.param(None, id="DefaultBehaviour"),
        pytest.param(os.path.dirname(os.path.realpath(__file__)), id="CurrentDir"),
    ]

    @pytest.mark.parametrize("startup_dir", startup_dir_params)
    def test_startup_directory(self, startup_dir: str | None, caplog):
        caplog.set_level(logging.INFO)
        if OSName.is_windows():
            args = ["powershell.exe", "pwd"]
        else:
            args = ["pwd"]
        ls = LoggingSubprocess(args=args, startup_directory=startup_dir)

        # Sometimes we assert too quickly, so we are waiting for the pwd command to finish
        # running.
        ls.wait()

        # Explicitly cleanup the IO threads to ensure all output is logged
        ls._cleanup_io_threads()

        assert f"Running command: {' '.join(args)}" in caplog.text

        if startup_dir is not None:
            assert startup_dir in caplog.text

    @pytest.mark.skipif(not OSName.is_posix(), reason="Only run this test in Linux.")
    def test_startup_directory_empty_posix(self):
        """When calling LoggingSubprocess with an empty cwd, FileNotFoundError will be raised."""
        args = ["pwd"]
        with pytest.raises(FileNotFoundError) as excinfo:
            LoggingSubprocess(args=args, startup_directory="")
        assert "[Errno 2] No such file or directory: ''" in str(excinfo.value)

    @pytest.mark.skipif(not OSName.is_windows(), reason="Only run this test in Windows.")
    def test_startup_directory_empty_windows(self):
        """When calling LoggingSubprocess with an empty cwd, OSError will be raised."""
        args = ["powershell.exe", "pwd"]
        with pytest.raises(OSError) as exc_info:
            LoggingSubprocess(args=args, startup_directory="")
        assert "The filename, directory name, or volume label syntax is incorrect" in str(
            exc_info.value
        )

    @pytest.mark.parametrize("log_level", [_STDOUT_LEVEL, _STDERR_LEVEL])
    def test_log_levels(self, log_level: int, caplog):
        # GIVEN
        caplog.set_level(log_level)
        message = "Hello World"

        test_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "scripts", "echo_sleep_n_times.py"
        )
        # WHEN
        p = LoggingSubprocess(
            args=[sys.executable, test_file, message, "1"],
        )
        p.wait()

        # THEN
        records = caplog.get_records("call")
        if log_level == _STDOUT_LEVEL:
            assert any(r.message == message and r.levelno == _STDOUT_LEVEL for r in records)
        else:
            assert not any(r.message == message and r.levelno == _STDOUT_LEVEL for r in records)

        assert any(r.message == message and r.levelno == _STDERR_LEVEL for r in records)


class TestIntegrationRegexHandler(object):
    """Integration tests for LoggingSubprocess"""

    invoked_regex_list = [
        pytest.param(
            re.compile(".*"),
            "Test output",
            5,
        ),
    ]

    @pytest.mark.parametrize("stdout, stderr", [(1, 0), (0, 1), (1, 1)])
    @pytest.mark.parametrize("regex, output, echo_count", invoked_regex_list)
    def test_stdouthandler_invoked(self, regex, output, echo_count, stdout, stderr):
        # GIVEN
        callback = mock.Mock()
        regex_callbacks = [RegexCallback([regex], callback)]
        regex_handler = RegexHandler(regex_callbacks)
        test_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "scripts", "echo_sleep_n_times.py"
        )
        # WHEN
        p = LoggingSubprocess(
            args=[sys.executable, test_file, output, str(echo_count)],
            stdout_handler=regex_handler if stdout else None,
            stderr_handler=regex_handler if stderr else None,
        )
        p.wait()
        time.sleep(0.01)  # magic sleep - logging handler has a delay and test can exit too fast
        print(
            [sys.executable, test_file, output, str(echo_count)],
        )
        # THEN
        assert callback.call_count == echo_count * (stdout + stderr)
        assert all(c[0][0].re == regex for c in callback.call_args_list)

    multiple_procs_regex_list = [
        pytest.param(
            re.compile(".*"),
            "Test output",
            5,
        ),
    ]

    @pytest.mark.parametrize("num_procs", [2])
    @pytest.mark.parametrize("regex, output, echo_count", multiple_procs_regex_list)
    def test_multiple_processes_invoked_independently(self, regex, output, echo_count, num_procs):
        """
        Creates a number of processes and validates that the stdout/stderr from each process does
        not invoke a callback in a different process' logging handler.
        """
        # GIVEN

        # Set up regex handler with a single callback for each stdout/stderr of each proc
        callbacks = (mock.Mock() for _ in range(2 * num_procs))
        regex_callbacks = [RegexCallback([regex], callback) for callback in callbacks]
        regex_handlers = [RegexHandler([regex_callback]) for regex_callback in regex_callbacks]

        stdout_handlers = regex_handlers[:num_procs]
        stderr_handlers = regex_handlers[num_procs:]

        test_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "scripts", "echo_sleep_n_times.py"
        )

        # WHEN
        procs = []
        for i in range(num_procs):
            procs.append(
                LoggingSubprocess(
                    args=[sys.executable, test_file, output, str(echo_count)],
                    stdout_handler=stdout_handlers[i],
                    stderr_handler=stderr_handlers[i],
                )
            )

        for proc in procs:
            proc.wait()

        # THEN
        for callback in callbacks:
            assert callback.call_count == echo_count
            assert all(c[0][0].re == regex for c in callback.call_args_list)
