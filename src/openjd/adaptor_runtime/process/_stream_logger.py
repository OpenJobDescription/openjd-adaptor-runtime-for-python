# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""Module for the StreamLogger class"""
from __future__ import annotations

import logging
import os
from threading import Thread
from typing import IO, Sequence


class StreamLogger(Thread):
    """A thread that reads a text stream line-by-line and logs each line to a specified logger"""

    def __init__(
        self,
        *args,
        # Required keyword-only arguments
        stream: IO[str],
        loggers: Sequence[logging.Logger],
        # Optional keyword-only arguments
        level: int = logging.INFO,
        **kwargs,
    ):
        super(StreamLogger, self).__init__(*args, **kwargs)
        self._stream = stream
        self._loggers = list(loggers)
        self._level = level

        # Without setting daemon to False, we run into an issue in which all output may NOT be
        # printed. From the python docs:
        # > The entire Python program exits when no alive non-daemon threads are left.
        # Reference: https://docs.python.org/3/library/threading.html#threading.Thread.daemon
        self.daemon = False

    def _log(self, line: str, level: int | None = None):
        """
        Logs a line to each logger at the provided level or self._level is no level is provided.
        Args:
            line (str): The line to log
            level (int): The level to log the line at
        """
        if level is None:
            level = self._level

        for logger in self._loggers:
            logger.log(level, line)

    def run(self):
        try:
            for line in iter(self._stream.readline, ""):
                line = line.rstrip(os.linesep)
                self._log(line)
        except ValueError as e:
            if "I/O operation on closed file" in str(e):
                self._log(
                    "The StreamLogger could not read from the stream. This is most likely because "
                    "the stream was closed before the stream logger.",
                    logging.WARNING,
                )
            else:
                raise
