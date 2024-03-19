# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from openjd.adaptor_runtime._named_pipe import NamedPipeServer

from ...adaptor_runtime_client.named_pipe.named_pipe_helper import (
    NamedPipeHelper,
    PipeDisconnectedException,
)
import win32pipe
import win32file
from pywintypes import HANDLE
from http import HTTPStatus
import logging
import traceback
from abc import ABC, abstractmethod

from openjd.adaptor_runtime._osname import OSName


_logger = logging.getLogger(__name__)


class ResourceRequestHandler(ABC):
    """
    A handler for managing requests sent to a NamedPipe instance within a Windows environment.
    This class handles incoming requests, processes them, and sends back appropriate responses.
    """

    def __init__(self, server: "NamedPipeServer", pipe_handle: HANDLE):
        """
        Initializes the ResourceRequestHandler with a server and pipe handle.

        Args:
            server(NamedPipeServer): The server instance that created this handler.
                It is responsible for managing the lifecycle of the NamedPipe server and other resources.
                pipe_handle(pipe_handle): The handle to the NamedPipe instance created and managed by the server.
            pipe_handle(HANDLE): pipe_handle(HANDLE): Handle for the NamedPipe, established by the instance.
                Utilized for message read/write operations.
        """
        self._handler_type_name = self.__class__.__name__
        if not OSName.is_windows():
            raise OSError(
                f"{self._handler_type_name} can be only used on Windows Operating Systems. "
                f"Current Operating System is {OSName._get_os_name()}"
            )
        self.server = server
        self.pipe_handle = pipe_handle

    def instance_thread(self) -> None:
        """
        A method that runs in a separate thread to listen to the NamedPipe server. It handles incoming
        requests and sends back the responses.

        This method calls `send_response` and `handle_request` to process the request and send responses.
        It should be run in a thread as it continuously listens for incoming requests.
        """
        _logger.debug("An instance thread is created to handle communication.")
        try:
            request_data = NamedPipeHelper.read_from_pipe(self.pipe_handle)
            _logger.debug(f"Got following request from client: {request_data}")
            self.handle_request(request_data)
        except PipeDisconnectedException as e:
            # Server is closed
            _logger.debug(
                f"NamedPipe Server is closed during reading message. {str(e)}"
                f"{self._handler_type_name} instance thread exited."
            )
            # Server is closed. No need to flush buffers or close handle.
            return
        except Exception:
            error_message = traceback.format_exc()
            _logger.error(
                f"Encountered an error while reading from the named pipe: {error_message}."
            )
            # Try to send back the error message
            try:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR, error_message)
            except Exception:
                _logger.error(
                    f"Encountered an error while sending the error response: {traceback.format_exc()}."
                )
        try:
            # Flush the pipe to allow the client to read the pipe's contents before disconnecting.
            # Then disconnect the pipe, and close the handle to this pipe instance.
            win32file.FlushFileBuffers(self.pipe_handle)
            win32pipe.DisconnectNamedPipe(self.pipe_handle)
            win32file.CloseHandle(self.pipe_handle)
        except Exception:
            _logger.error(
                f"Encountered an error while closing the named pipe: {traceback.format_exc()}"
            )
        _logger.debug(f"{self._handler_type_name} instance thread exited.")

    def send_response(self, status: HTTPStatus, body: str = ""):
        """
        Sends a response back to the client.

        Args:
            status: An HTTPStatus object representing the HTTP status code of the response.
            body: A string containing the message body to be sent back to the client.
        """
        response = {"status": status, "body": body}
        NamedPipeHelper.write_to_pipe(self.pipe_handle, json.dumps(response))
        _logger.debug("NamedPipe Server: Sent Response.")

    def validate_request_path_and_method(self, request_path: str, request_method) -> bool:
        """
        Validate if request path or method is valid.

        Args:
            request_path(str): request path needed to be validated
            request_method(str): request method needed to be validated
        """
        if request_path not in self.request_path_and_method_dict:
            error_message = f"Incorrect request path {request_path}."
            _logger.error(error_message)
            self.send_response(HTTPStatus.NOT_FOUND, error_message)
            return False

        if request_method not in self.request_path_and_method_dict[request_path]:
            error_message = (
                f"Incorrect request method {request_method} for the path {request_path}."
            )
            _logger.error(error_message)
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED, error_message)
            return False

        return True

    @property
    @abstractmethod
    def request_path_and_method_dict(self) -> Dict[str, List[str]]:
        """
        This property is a dict used for storing all valid request path and request method.
        """
        raise NotImplementedError

    @abstractmethod
    def handle_request(self, data: str):
        raise NotImplementedError
