# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""Tests for StreamLogger"""
from __future__ import annotations

import subprocess
from logging import INFO
from typing import List
from unittest import mock

import pytest

import openjd.adaptor_runtime.process._logging_subprocess as logging_subprocess
from openjd.adaptor_runtime.process import LoggingSubprocess


class TestLoggingSubprocess(object):
    """Tests for LoggingSubprocess"""

    @pytest.fixture()
    def mock_popen(self):
        with mock.patch.object(logging_subprocess.subprocess, "Popen") as popen_mock:
            yield popen_mock

    @pytest.fixture(autouse=True)
    def mock_stream_logger(self):
        with mock.patch.object(logging_subprocess, "StreamLogger") as stream_logger:
            yield stream_logger

    def test_args_validation(self, mock_popen: mock.Mock):
        """Tests that passing no args raises an Exception"""
        # GIVEN
        args: List[str] = []
        logger = mock.Mock()

        # THEN
        with pytest.raises(ValueError, match="Insufficient args"):
            LoggingSubprocess(args=args, logger=logger)

        mock_popen.assert_not_called()

    def test_logging_validation(self, mock_popen: mock.Mock):
        """Tests that passing no logger raises an Exception"""
        # GIVEN
        args = ["cat", "foo.txt"]
        logger = None

        # THEN
        with pytest.raises(ValueError, match="No logger specified"):
            LoggingSubprocess(args=args, logger=logger)  # type: ignore[arg-type]

        mock_popen.assert_not_called()

    def test_process_creation(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        stdout_logger_mock = mock.Mock()
        stderr_logger_mock = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger_mock, stderr_logger_mock]

        # WHEN
        LoggingSubprocess(args=args, logger=logger)

        # EXPECT
        mock_popen.assert_called_with(
            args,
            encoding="utf-8",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=None,
        )

    def test_is_running(self, mock_popen: mock.Mock):
        # GIVEN
        proc_obj = mock.Mock()
        proc_obj.poll.return_value = None
        mock_popen.return_value = proc_obj
        args = ["cat", "foo.txt"]
        logger = mock.Mock()

        # WHEN
        subject = LoggingSubprocess(args=args, logger=logger)

        # THEN
        assert subject.is_running
        proc_obj.poll.return_value = True
        assert not subject.is_running

    def test_wait(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        # WHEN
        subject.wait()

        # THEN
        proc.wait.assert_called_once()
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

    @mock.patch.object(logging_subprocess.sys, "platform", "win32")
    def test_terminate_fails_on_windows(self, mock_popen: mock.Mock):
        args = ["cat", "foo.txt"]
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 1
        mock_popen.return_value = proc
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        with pytest.raises(NotImplementedError):
            subject.terminate()

    def test_terminate_no_process(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = False
        proc.pid = 1
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        # WHEN
        subject.terminate()

        # THEN
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        proc.stdout.close.assert_not_called()
        proc.stderr.close.assert_not_called()

    def test_terminate_no_grace(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 1
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        # WHEN
        subject.terminate(0)

        # THEN
        proc.terminate.assert_not_called()
        proc.kill.assert_called_once()
        proc.wait.assert_called_once()
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

    def test_terminate(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 1
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        # WHEN
        subject.terminate()

        # THEN
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()
        proc.wait.assert_called_once()
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

    def test_stop_after_terminate_timeout(
        self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock
    ):
        # GIVEN
        args = ["cat", "foo.txt"]
        timeout = 2
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 1

        # When a subprocess doesn't terminate in the alloted time, it throws a TimeoutExpired
        # exception. When this exception is thrown we send the SIGKILL signal, so we are
        # simulating that here.
        proc.wait.side_effect = [subprocess.TimeoutExpired(args, timeout), mock.DEFAULT]

        mock_popen.return_value = proc
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        # WHEN
        subject.terminate(timeout)

        # THEN
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        assert proc.wait.call_count == 2
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

    def test_wait_multiple(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        subject.wait()

        proc.wait.assert_called_once()
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

        # clear tracked mock calls
        mocks_to_reset = (
            proc.wait,
            stdout_logger.join,
            stderr_logger.join,
            proc.stdout.close,
            proc.stderr.close,
        )
        for mock_to_reset in mocks_to_reset:
            mock_to_reset.reset_mock()

        # WHEN
        subject.wait()

        # THEN
        proc.wait.assert_not_called()
        stdout_logger.join.assert_not_called()
        stderr_logger.join.assert_not_called()
        proc.stdout.close.assert_not_called()
        proc.stderr.close.assert_not_called()

    def test_terminate_multiple(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        subject.terminate()

        proc.terminate.assert_called_once()
        proc.kill.assert_not_called()
        proc.wait.assert_called_once()
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

        # clear tracked mock calls
        mocks_to_reset = (
            proc.terminate,
            proc.wait,
            stdout_logger.join,
            stderr_logger.join,
            proc.stdout.close,
            proc.stderr.close,
        )
        for mock_to_reset in mocks_to_reset:
            mock_to_reset.reset_mock()

        # WHEN
        subject.terminate()

        # THEN
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        proc.wait.assert_not_called()
        stdout_logger.join.assert_not_called()
        stderr_logger.join.assert_not_called()
        proc.stdout.close.assert_not_called()
        proc.stderr.close.assert_not_called()

    def test_stop_multiple(self, mock_popen: mock.Mock, mock_stream_logger: mock.Mock):
        # GIVEN
        args = ["cat", "foo.txt"]
        timeout = 2
        # mock stdout and stderr StreamLogger instances
        stdout_logger = mock.Mock()
        stderr_logger = mock.Mock()
        mock_stream_logger.side_effect = [stdout_logger, stderr_logger]
        # mock subprocess.Popen return value
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired(args, timeout), mock.DEFAULT]
        mock_popen.return_value = proc
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        subject.terminate(timeout)

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        assert proc.wait.call_count == 2
        stdout_logger.join.assert_called_once()
        stderr_logger.join.assert_called_once()
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()

        # clear tracked mock calls
        mocks_to_reset = (
            proc.terminate,
            proc.kill,
            proc.wait,
            stdout_logger.join,
            stderr_logger.join,
            proc.stdout.close,
            proc.stderr.close,
        )
        for mock_to_reset in mocks_to_reset:
            mock_to_reset.reset_mock()

        # WHEN
        subject.terminate(timeout)

        # THEN
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        proc.wait.assert_not_called()
        stdout_logger.join.assert_not_called()
        stderr_logger.join.assert_not_called()
        proc.stdout.close.assert_not_called()
        proc.stderr.close.assert_not_called()

    def test_context_manager(self):
        # GIVEN
        args = ["cat", "foo.txt"]
        logger = mock.Mock()

        # WHEN
        subject = LoggingSubprocess(args=args, logger=logger)
        with mock.patch.object(subject, "wait", wraps=subject.wait) as wait_spy:
            with subject as mgr_yield_value:
                wait_spy.assert_not_called()

            wait_spy.assert_called_once()
            assert mgr_yield_value is subject

    def test_pid(self, mock_popen: mock.Mock):
        # GIVEN
        # mock subprocess.Popen return value
        pid = 123
        proc = mock.Mock()
        proc.pid = pid
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()

        # WHEN
        subject = LoggingSubprocess(args=args, logger=logger)

        # THEN
        assert subject.pid == pid

    def test_returncode_success(self, mock_popen: mock.Mock):
        # GIVEN
        # mock subprocess.Popen return value
        returncode = 1
        proc = mock.Mock()
        proc.poll.return_value = returncode
        mock_popen.return_value = proc
        args = ["cat", "foo.txt"]
        logger = mock.Mock()

        # WHEN
        subject = LoggingSubprocess(args=args, logger=logger)

        # THEN
        assert subject.returncode == returncode
        proc.poll.assert_called_once()

    def test_returncode_subproc_running(self, mock_popen: mock.Mock):
        # GIVEN

        # mock subprocess.Popen return value
        proc = mock.Mock()
        mock_popen.return_value = proc
        # Popen.poll() returns None when the subprocess is still running
        proc.poll.return_value = None

        args = ["cat", "foo.txt"]
        logger = mock.Mock()
        subject = LoggingSubprocess(args=args, logger=logger)

        assert subject.returncode is None

    def test_command_printed(self, mock_popen: mock.Mock, caplog):
        caplog.set_level(INFO)

        # mock subprocess.Popen return value
        proc = mock.Mock()
        mock_popen.return_value = proc
        # Popen.poll() returns None when the subprocess is still running
        proc.poll.return_value = None

        args = ["cat", "foo.txt"]
        LoggingSubprocess(args=args)

        assert "Running command: cat foo.txt" in caplog.text

    @mock.patch.object(logging_subprocess.subprocess, "Popen", autospec=True)
    def test_startup_directory_default(self, mock_popen_autospec: mock.Mock):
        # mock subprocess.Popen return value
        proc = mock.Mock()
        mock_popen_autospec.return_value = proc

        args = ["cat", "foo.txt"]
        LoggingSubprocess(args=args)

        # cwd will equal the startup direcotry, since that is None by default,
        # we expect cwd to be None.
        mock_popen_autospec.assert_called_once_with(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            cwd=None,
        )

    @mock.patch.object(logging_subprocess.subprocess, "Popen", autospec=True)
    def test_start_directory(self, mock_popen_autospec: mock.Mock):
        # mock subprocess.Popen return value
        proc = mock.Mock()
        mock_popen_autospec.return_value = proc

        args = ["cat", "foo.txt"]
        LoggingSubprocess(args=args, startup_directory="startup_dir")

        mock_popen_autospec.assert_called_once_with(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            cwd="startup_dir",
        )
