# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from .backend_named_pipe_server import WinBackgroundNamedPipeServer
from openjd.adaptor_runtime._background.named_pipe_helper import (
    NamedPipeHelper,
    PipeDisconnectedException,
)
from openjd.adaptor_runtime._background.server_response import ServerResponseGenerator
import win32pipe
import win32file
from pywintypes import HANDLE
from http import HTTPStatus
import logging
import traceback

from openjd.adaptor_runtime._osname import OSName


_logger = logging.getLogger(__name__)


class WinBackgroundResourceRequestHandler:
    """
    A handler for managing requests sent to a NamedPipe instance within a Windows environment.

    This class handles incoming requests, processes them, and sends back appropriate responses.
    It is designed to work in conjunction with a WinBackgroundNamedPipeServer that manages the
    lifecycle of the NamedPipe server and other associated resources.
    """

    def __init__(self, server: "WinBackgroundNamedPipeServer", pipe_handle: HANDLE):
        """
        Initializes the WinBackgroundResourceRequestHandler with a server and pipe handle.

        Args:
            server(WinBackgroundNamedPipeServer): The server instance that created this handler.
                It is responsible for managing the lifecycle of the NamedPipe server and other resources.
                pipe_handle(pipe_handle): The handle to the NamedPipe instance created and managed by the server.
        """
        if not OSName.is_windows():
            raise OSError(
                "WinBackgroundResourceRequestHandler can be only used on Windows Operating Systems. "
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
        while True:
            try:
                request_data = NamedPipeHelper.read_from_pipe(self.pipe_handle)
                _logger.debug(f"Got following request from client: {request_data}")
                self.handle_request(request_data)
            except PipeDisconnectedException as e:
                # Server is closed
                _logger.info(f"NamedPipe Server is closed during reading message. {str(e)}")
                break
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
            win32pipe.DisconnectNamedPipe(self.pipe_handle)
            win32file.CloseHandle(self.pipe_handle)
        except Exception:
            _logger.error(
                f"Encountered an error while closing the named pipe: {traceback.format_exc()}"
            )
        _logger.debug("WinBackgroundResourceRequestHandler instance thread exited.")

    def send_response(self, status: HTTPStatus, body: str = ""):
        """
        Sends a response back to the client.

        Args:
            status: An HTTPStatus object representing the HTTP status code of the response.
            body: A string containing the message body to be sent back to the client.
        """
        response = {"status": status, "body": body}
        _logger.debug(f"NamedPipe Server: Send Response: {response}")
        NamedPipeHelper.write_to_pipe(self.pipe_handle, json.dumps(response))

    def handle_request(self, data: str):
        """
        Processes an incoming request and routes it to the correct response handler based on the method
        and request path.

        Args:
            data: A string containing the message sent from the client.
        """
        request_dict = json.loads(data)
        path = request_dict["path"]
        body = json.loads(request_dict["body"])
        method = request_dict["method"]

        if "params" in request_dict and request_dict["params"] != "null":
            query_string_params = json.loads(request_dict["params"])
        else:
            query_string_params = {}

        server_operation = ServerResponseGenerator(
            self.server, self.send_response, body, query_string_params
        )
        try:
            # TODO: Code refactoring to get rid of the `if...elif..` by using getattr
            if path == "/run" and method == "PUT":
                server_operation.generate_run_put_response()

            elif path == "/shutdown" and method == "PUT":
                server_operation.generate_shutdown_put_response()

            elif path == "/heartbeat" and method == "GET":
                _ACK_ID_KEY = ServerResponseGenerator.ACK_ID_KEY

                def _parse_ack_id():
                    if _ACK_ID_KEY in query_string_params:
                        return query_string_params[_ACK_ID_KEY]

                server_operation.generate_heartbeat_get_response(_parse_ack_id)

            elif path == "/start" and method == "PUT":
                server_operation.generate_start_put_response()

            elif path == "/stop" and method == "PUT":
                server_operation.generate_stop_put_response()

            elif path == "/cancel" and method == "PUT":
                server_operation.generate_cancel_put_response()
        except Exception as e:
            _logger.error(
                f"Error encountered in request handling. "
                f"Path: '{path}', Method: '{method}', Error: '{str(e)}'"
            )
            raise
