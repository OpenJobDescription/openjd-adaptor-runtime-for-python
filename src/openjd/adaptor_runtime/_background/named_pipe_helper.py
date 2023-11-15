# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging

import win32file
import pywintypes
import winerror
from pywintypes import HANDLE

from openjd.adaptor_runtime._background.server_config import NAMED_PIPE_BUFFER_SIZE

_logger = logging.getLogger(__name__)


class PipeDisconnectedException(Exception):
    """
    Exception raised when a Named Pipe is either broken or not connected.

    Attributes:
        message (str): Explanation of the error.
        error_code (int): The specific Windows error code associated with the pipe issue.
    """

    def __init__(self, message: str, error_code: int):
        self.message = message
        self.error_code = error_code
        super().__init__(f"{message} (Error code: {error_code})")

    def __str__(self):
        return f"{self.message} (Error code: {self.error_code})"


class NamedPipeHelper:
    """
    Helper class for reading from and writing to Named Pipes in Windows.

    This class provides static methods to interact with Named Pipes,
    facilitating data transmission between the server and the client.
    """

    @staticmethod
    def read_from_pipe(handle: HANDLE) -> str:  # type: ignore
        """
        Reads data from a Named Pipe.

        Args:
            handle (HANDLE): The handle to the Named Pipe.

        Returns:
            str: The data read from the Named Pipe.
        """
        data_parts = []
        while True:
            try:
                return_code, data = win32file.ReadFile(handle, NAMED_PIPE_BUFFER_SIZE)
                data_parts.append(data.decode("utf-8"))
                if return_code == winerror.ERROR_MORE_DATA:
                    continue
                elif return_code == winerror.NO_ERROR:
                    return "".join(data_parts)
                else:
                    raise IOError(
                        f"Got error when reading from the Named Pipe with error code: {return_code}"
                    )
            # Server maybe shutdown during reading.
            except pywintypes.error as e:
                if e.winerror in [
                    winerror.ERROR_BROKEN_PIPE,
                    winerror.ERROR_PIPE_NOT_CONNECTED,
                    winerror.ERROR_INVALID_HANDLE,
                ]:
                    raise PipeDisconnectedException(
                        "Client disconnected or pipe is not available", e.winerror
                    )
                raise

    @staticmethod
    def write_to_pipe(handle: HANDLE, message: str) -> None:  # type: ignore
        """
        Writes data to a Named Pipe.

        Args:
            handle (HANDLE): The handle to the Named Pipe.
            message (str): The message to write to the Named Pipe.

        """
        try:
            win32file.WriteFile(handle, message.encode("utf-8"))
        # Server maybe shutdown during writing.
        except pywintypes.error as e:
            if e.winerror in [
                winerror.ERROR_BROKEN_PIPE,
                winerror.ERROR_PIPE_NOT_CONNECTED,
                winerror.ERROR_INVALID_HANDLE,
            ]:
                raise PipeDisconnectedException(
                    "Client disconnected or pipe is not available", e.winerror
                )
            raise
