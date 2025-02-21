# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import os
from typing import Tuple
from unittest.mock import MagicMock, mock_open, patch

import pytest

import openjd.adaptor_runtime._background.log_buffers as log_buffers
from openjd.adaptor_runtime._background.log_buffers import (
    FileLogBuffer,
    InMemoryLogBuffer,
    LogBuffer,
)
from openjd.adaptor_runtime._background.model import BufferedOutput


@pytest.fixture(autouse=True)
def mocked_chunk_id():
    with patch.object(LogBuffer, "_create_id") as mock_create_id:
        chunk_id = "id"
        mock_create_id.return_value = chunk_id
        yield chunk_id, mock_create_id


class TestInMemoryLogBuffer:
    """
    Tests for InMemoryLogBuffer.
    """

    @patch.object(LogBuffer, "_format")
    def test_chunk_creates_new_chunk(
        self,
        mock_format: MagicMock,
        mocked_chunk_id: Tuple[str, MagicMock],
    ):
        # GIVEN
        chunk_id, mock_create_id = mocked_chunk_id
        mock_format.return_value = "output"
        buffer = InMemoryLogBuffer()
        buffer._buffer = [MagicMock()]

        # WHEN
        output = buffer.chunk()

        # THEN
        assert output.id == chunk_id
        assert output.output == mock_format.return_value
        mock_create_id.assert_called_once()
        assert len(buffer._buffer) == 0
        assert buffer._last_chunk == output

    @patch.object(LogBuffer, "_format")
    def test_chunk_uses_last_chunk(
        self,
        mock_format: MagicMock,
        mocked_chunk_id: Tuple[str, MagicMock],
    ):
        # GIVEN
        chunk_id, mock_create_id = mocked_chunk_id
        mock_format.return_value = "output"
        buffer = InMemoryLogBuffer()
        buffer._buffer = [MagicMock()]
        last_chunk = BufferedOutput("id", "last_chunk")
        buffer._last_chunk = last_chunk

        # WHEN
        output = buffer.chunk()

        # THEN
        assert output.id == chunk_id
        assert output.output == os.linesep.join([last_chunk.output, mock_format.return_value])
        mock_create_id.assert_called_once()
        assert len(buffer._buffer) == 0
        assert buffer._last_chunk == output

    def test_clear_clears_chunk(self):
        # GIVEN
        last_chunk = BufferedOutput("id", "last_chunk")
        buffer = InMemoryLogBuffer()
        buffer._last_chunk = last_chunk

        # WHEN
        cleared = buffer.clear(last_chunk.id)

        # THEN
        assert cleared
        assert buffer._last_chunk is None

    def test_clear_no_op_if_wrong_id(self):
        # GIVEN
        last_chunk = BufferedOutput("id", "last_chunk")
        buffer = InMemoryLogBuffer()
        buffer._last_chunk = last_chunk

        # WHEN
        cleared = buffer.clear("wrong_id")

        # THEN
        assert not cleared
        assert buffer._last_chunk == last_chunk


class TestFileLogBuffer:
    """
    Tests for the FileLogBuffer class
    """

    def test_buffer(self) -> None:
        # GIVEN
        filepath = "/filepath"
        mock_record = MagicMock(spec=logging.LogRecord)
        mock_record.msg = "hello world"
        buffer = FileLogBuffer(filepath)

        # WHEN
        open_mock: MagicMock
        with patch.object(log_buffers, "secure_open", mock_open()) as open_mock:
            buffer.buffer(mock_record)

        # THEN
        open_mock.assert_called_once_with(filepath, open_mode="a", encoding="utf-8")
        handle = open_mock.return_value
        handle.write.assert_called_once_with(mock_record.msg)

    def test_chunk(self, mocked_chunk_id: Tuple[str, MagicMock]) -> None:
        # GIVEN
        chunk_id, mock_create_id = mocked_chunk_id
        filepath = "/filepath"
        data = "hello world"
        end_pos = len(data)
        buffer = FileLogBuffer(filepath)

        # WHEN
        open_mock: MagicMock
        with patch("builtins.open", mock_open(read_data=data)) as open_mock:
            open_mock.return_value.tell.return_value = end_pos
            output = buffer.chunk()

        # THEN
        mock_create_id.assert_called_once()
        open_mock.assert_called_once_with(filepath, mode="r", encoding="utf-8")
        handle = open_mock.return_value
        handle.seek.assert_called_once_with(buffer._chunk.start)
        handle.read.assert_called_once()
        handle.tell.assert_called_once()
        assert buffer._chunk.end == end_pos
        assert buffer._chunk.id == chunk_id
        assert output.id == chunk_id
        assert output.output == data

    def test_clear(self) -> None:
        # GIVEN
        chunk_id = "id"
        end_pos = 123
        buffer = FileLogBuffer("")
        buffer._chunk.id = chunk_id
        buffer._chunk.end = end_pos

        # WHEN
        cleared = buffer.clear(chunk_id)

        # THEN
        assert cleared
        assert buffer._chunk.start == end_pos
        assert buffer._chunk.id is None

    def test_clear_no_op_if_wrong_id(self) -> None:
        # GIVEN
        buffer = FileLogBuffer("")
        buffer._chunk.id = "id"
        buffer._chunk.end = 1

        # WHEN
        cleared = buffer.clear("wrong_id")

        # THEN
        assert not cleared
        assert buffer._chunk.id == "id"
        assert buffer._chunk.start == 0
