# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, cast, Dict, List

from ._adaptor_server_response import AdaptorServerResponseGenerator
from .._named_pipe import ResourceRequestHandler

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from ._win_adaptor_server import WinAdaptorServer

from pywintypes import HANDLE
import logging

_logger = logging.getLogger(__name__)


class WinAdaptorServerResourceRequestHandler(ResourceRequestHandler):
    """
    A handler for managing requests sent to a NamedPipe instance within a Windows environment.

    This class handles incoming requests, processes them, and sends back appropriate responses.
    It is designed to work in conjunction with a WinAdaptorServer that manages the
    lifecycle of the NamedPipe server and other associated resources.
    """

    def __init__(self, server: "WinAdaptorServer", pipe_handle: HANDLE):
        """
        Initializes the WinBackgroundResourceRequestHandler with a server and pipe handle.

        Args:
            server(WinAdaptorServer): The server instance that created this handler.
                It is responsible for managing the lifecycle of the NamedPipe server and other resources.
            pipe_handle(pipe_handle): The handle to the NamedPipe instance created and managed by the server.
        """
        super().__init__(server, pipe_handle)

    @property
    def request_path_and_method_dict(self) -> Dict[str, List[str]]:
        return {
            "/path_mapping": ["GET"],
            "/path_mapping_rules": ["GET"],
            "/action": ["GET"],
        }

    def handle_request(self, data: str):
        """
        Processes an incoming request and routes it to the correct response handler based on the method
        and request path.

        Args:
            data: A string containing the message sent from the client.
        """
        request_dict = json.loads(data)
        path = request_dict["path"]
        method: str = request_dict["method"]
        if not self.validate_request_path_and_method(path, method):
            return

        if "params" in request_dict and request_dict["params"] != "null":
            query_string_params = json.loads(request_dict["params"])
        else:
            query_string_params = {}

        server_operation = AdaptorServerResponseGenerator(
            cast("WinAdaptorServer", self.server), self.send_response, query_string_params
        )
        try:
            # Ignore the leading `/` in path
            method_name = f"generate_{path[1:]}_{method.lower()}_response"
            getattr(server_operation, method_name)()
        except Exception as e:
            error_message = (
                f"Error encountered in request handling. "
                f"Path: '{path}', Method: '{method}', Error: '{str(e)}'"
            )
            _logger.error(error_message)
            self.send_response(HTTPStatus.BAD_REQUEST, error_message)
            raise
