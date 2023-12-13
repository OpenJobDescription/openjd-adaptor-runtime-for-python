# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime._osname import OSName
from unittest.mock import patch, MagicMock
import pytest
import os
import time

pywintypes = pytest.importorskip("pywintypes")
win32pipe = pytest.importorskip("win32pipe")
win32file = pytest.importorskip("win32file")
winerror = pytest.importorskip("winerror")
named_pipe_helper = pytest.importorskip("openjd.adaptor_runtime._named_pipe.named_pipe_helper")


class MockReadFile:
    @staticmethod
    def ReadFile(handle: pywintypes.HANDLE, timeout_in_seconds: float):  # type: ignore[name-defined]
        time.sleep(10)
        return winerror.NO_ERROR, bytes("fake_data", "utf-8")


@pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
class TestNamedPipeHelper:
    def test_named_pipe_read_timeout_exception(self):
        with pytest.raises(
            named_pipe_helper.NamedPipeReadTimeoutError,
            match="NamedPipe Server read timeout after 1.0 seconds.$",
        ):
            raise named_pipe_helper.NamedPipeReadTimeoutError(1.0)

    def test_named_pipe_connect_timeout_exception(self):
        exception_during_connect = Exception("Fake exception that occurred while connecting.")
        expected_error_message = os.linesep.join(
            [
                "NamedPipe Server connect timeout after 1.0 seconds.",
                f"Original error: {exception_during_connect}",
            ]
        )
        with pytest.raises(
            named_pipe_helper.NamedPipeConnectTimeoutError, match=expected_error_message
        ):
            raise named_pipe_helper.NamedPipeConnectTimeoutError(1.0, exception_during_connect)

    @patch.object(
        win32file, "CreateFile", side_effect=win32file.error(winerror.ERROR_FILE_NOT_FOUND)
    )
    def test_establish_named_pipe_connection_timeout_raises_exception(self, mock_win32file):
        with pytest.raises(
            named_pipe_helper.NamedPipeConnectTimeoutError,
            match=os.linesep.join(
                [
                    "NamedPipe Server connect timeout after \\d\\.\\d+ seconds.",
                    f"Original error: {win32file.error(winerror.ERROR_FILE_NOT_FOUND)}",
                ]
            ),
        ):
            named_pipe_helper.NamedPipeHelper.establish_named_pipe_connection("fakepipe", 1.0)

    @patch.object(win32file, "ReadFile", wraps=MockReadFile.ReadFile)
    def test_read_from_pipe_timeout_raises_exception(self, mock_win32file):
        mock_handle = MagicMock()
        with pytest.raises(
            named_pipe_helper.NamedPipeReadTimeoutError,
            match="NamedPipe Server read timeout after \\d\\.\\d+ seconds.$",
        ):
            named_pipe_helper.NamedPipeHelper.read_from_pipe(mock_handle, 1.0)

        mock_handle.close.assert_called_once()
