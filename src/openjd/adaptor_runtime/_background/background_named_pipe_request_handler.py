# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from typing import TYPE_CHECKING, cast

from .._named_pipe import ResourceRequestHandler

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from .backend_named_pipe_server import WinBackgroundNamedPipeServer

from openjd.adaptor_runtime._background.server_response import ServerResponseGenerator

from pywintypes import HANDLE
import logging

_logger = logging.getLogger(__name__)


class WinBackgroundResourceRequestHandler(ResourceRequestHandler):
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
            pipe_handle(HANDLE): pipe_handle(HANDLE): Handle for the NamedPipe, established by the instance.
                Utilized for message read/write operations.
        """
        super().__init__(server, pipe_handle)

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
            cast("WinBackgroundNamedPipeServer", self.server),
            self.send_response,
            body,
            query_string_params,
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