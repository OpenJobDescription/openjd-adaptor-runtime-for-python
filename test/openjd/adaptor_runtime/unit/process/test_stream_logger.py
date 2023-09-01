# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""Tests for LoggingSubprocess"""
from __future__ import annotations

import logging
import os
from typing import List
from unittest import mock

import pytest

import openjd.adaptor_runtime.process._stream_logger as stream_logger
from openjd.adaptor_runtime.process._stream_logger import StreamLogger


class TestStreamLogger(object):
    """Tests for StreamLogger"""

    @pytest.fixture(autouse=True)
    def mock_thread(self):
        with mock.patch.object(stream_logger, "Thread") as mock_thread:
            yield mock_thread

    def test_not_daemon_default(self):
        # GIVEN
        stream = mock.Mock()
        logger = mock.Mock()

        # WHEN
        subject = StreamLogger(stream=stream, loggers=[logger])

        # THEN
        assert not subject.daemon

    @pytest.mark.parametrize(
        ("lines",),
        (
            (["foo", "bar"],),
            (["foo"],),
            ([],),
        ),
    )
    def test_level_info_default(self, lines: List[str]):
        # GIVEN
        # stream.readline() includes newline characters
        readline_returns = [f"{line}{os.linesep}" for line in lines]
        stream = mock.Mock()
        stream.closed = False
        # stream.readline() returns an empty string on EOF
        stream.readline.side_effect = readline_returns + [""]
        logger = mock.Mock()
        subject = StreamLogger(stream=stream, loggers=[logger])

        # WHEN
        subject.run()

        # THEN
        logger.log.assert_has_calls([mock.call(logging.INFO, line) for line in lines])

    def test_supplied_logging_level(self):
        # GIVEN
        level = logging.CRITICAL
        log_line = "foo"
        # stream.readline() includes newline characters
        readline_returns = [f"{log_line}{os.linesep}"]
        stream = mock.Mock()
        stream.closed = False
        # stream.readline() returns an empty string on EOF
        stream.readline.side_effect = readline_returns + [""]
        logger = mock.Mock()
        subject = StreamLogger(stream=stream, loggers=[logger], level=level)

        # WHEN
        subject.run()

        # THEN
        logger.log.assert_has_calls([mock.call(level, log_line)])

    def test_multiple_loggers(self):
        # GIVEN
        level = logging.INFO
        log_line = "foo"
        loggers = [mock.Mock() for _ in range(5)]
        # stream.readline() includes newline characters
        readline_returns = [f"{log_line}{os.linesep}"]
        stream = mock.Mock()
        stream.closed = False
        # stream.readline() returns an empty string on EOF
        stream.readline.side_effect = readline_returns + [""]
        subject = StreamLogger(stream=stream, loggers=loggers, level=level)

        # WHEN
        subject.run()

        # THEN
        for logger in loggers:
            logger.log.assert_has_calls([mock.call(level, log_line)])

    def test_readline_failure_raises(self):
        # GIVEN
        err = ValueError()
        stream = mock.Mock()
        stream.readline.side_effect = err
        subject = StreamLogger(stream=stream, loggers=[mock.Mock()])

        # WHEN
        with pytest.raises(ValueError) as raised_err:
            subject.run()

        # THEN
        assert raised_err.value is err
        stream.readline.assert_called_once()

    def test_io_failure_logs_error(self):
        # GIVEN
        err = ValueError("I/O operation on closed file")
        stream = mock.Mock()
        stream.readline.side_effect = err
        logger = mock.Mock()
        subject = StreamLogger(stream=stream, loggers=[logger])

        # WHEN
        subject.run()

        # THEN
        stream.readline.assert_called_once()
        logger.log.assert_called_once_with(
            stream_logger.logging.WARNING,
            "The StreamLogger could not read from the stream. This is most likely because "
            "the stream was closed before the stream logger.",
        )
