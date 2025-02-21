# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from .._utils import secure_open
from .model import BufferedOutput


class LogBuffer(ABC):  # pragma: no cover
    """
    Base class for a log buffer.
    """

    def __init__(self, *, formatter: logging.Formatter | None = None) -> None:
        self._formatter = formatter

    @abstractmethod
    def buffer(self, record: logging.LogRecord) -> None:
        """
        Store the log record in this buffer.
        """
        pass

    @abstractmethod
    def chunk(self) -> BufferedOutput:
        """
        Returns the currently buffered output as a BufferedOutput.
        """
        pass

    @abstractmethod
    def clear(self, chunk_id: str) -> bool:
        """
        Clears the chunk with the specified ID from this buffer. Returns True if the chunk was
        cleared, false otherwise.

        Args:
            chunk_id (str): The ID of the chunk to clear.
        """
        pass

    def _format(self, record: logging.LogRecord) -> str:
        return self._formatter.format(record) if self._formatter else record.msg

    def _create_id(self) -> str:
        return str(time.time())


class InMemoryLogBuffer(LogBuffer):
    """
    In-memory log buffer implementation.

    This buffer stores a single chunk that grows until it is explicitly cleared. If a new chunk is
    created without clearing the previous one, the new chunk stores all data in the previous
    chunk, in addition to new buffered data, and replaces it.
    """

    _buffer: List[logging.LogRecord]
    _last_chunk: BufferedOutput | None

    def __init__(self, *, formatter: logging.Formatter | None = None) -> None:
        super().__init__(formatter=formatter)
        self._buffer = []
        self._last_chunk = None
        self._buffer_lock = threading.Lock()
        self._last_chunk_lock = threading.Lock()

    def buffer(self, record: logging.LogRecord) -> None:  # pragma: no cover
        with self._buffer_lock:
            self._buffer.append(record)

    def chunk(self) -> BufferedOutput:
        id = self._create_id()
        with self._buffer_lock:
            logs = [*self._buffer]
            self._buffer.clear()

        output = os.linesep.join([self._format(log) for log in logs])

        with self._last_chunk_lock:
            if self._last_chunk:
                output = os.linesep.join([self._last_chunk.output, output])
            chunk = BufferedOutput(id, output)
            self._last_chunk = chunk

        return chunk

    def clear(self, chunk_id: str) -> bool:
        with self._last_chunk_lock:
            if self._last_chunk and self._last_chunk.id == chunk_id:
                self._last_chunk = None
                return True

        return False


@dataclass
class _FileChunk:
    id: str | None
    start: int
    end: int


class FileLogBuffer(LogBuffer):
    """
    Log buffer that uses a file to buffer the output.

    This buffer keeps track of a section in a file with start/end stream positions. This section
    grows until it is explicitly cleared. If a new chunk is created without clearing the previous
    one, the new chunk's section includes all data in the previous chunk's section, in addition to
    new buffered data, and replaces it.
    """

    _filepath: str
    _chunk: _FileChunk

    def __init__(self, filepath: str, *, formatter: logging.Formatter | None = None) -> None:
        super().__init__(formatter=formatter)
        self._filepath = filepath
        self._chunk = _FileChunk(id=None, start=0, end=0)
        self._file_lock = threading.Lock()
        self._chunk_lock = threading.Lock()

    def buffer(self, record: logging.LogRecord) -> None:
        with (
            self._file_lock,
            secure_open(self._filepath, open_mode="a", encoding="utf-8") as f,
        ):
            f.write(self._format(record))

    def chunk(self) -> BufferedOutput:
        id = self._create_id()

        with (
            self._chunk_lock,
            self._file_lock,
            open(self._filepath, mode="r", encoding="utf-8") as f,
        ):
            self._chunk.id = id
            f.seek(self._chunk.start)
            output = f.read()
            self._chunk.end = f.tell()

        return BufferedOutput(id, output)

    def clear(self, chunk_id: str) -> bool:
        with self._chunk_lock:
            if self._chunk.id == chunk_id:
                self._chunk.start = self._chunk.end
                self._chunk.id = None
                return True

        return False


class LogBufferHandler(logging.Handler):  # pragma: no cover
    """
    Class for a handler that buffers logs.
    """

    def __init__(self, buffer: LogBuffer, level: logging._Level = logging.NOTSET) -> None:
        super().__init__(level)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.buffer(record)
