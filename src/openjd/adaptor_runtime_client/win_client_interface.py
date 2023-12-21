# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from .base_client_interface import Response as _Response
import http.client
import signal as _signal


from .base_client_interface import BaseClientInterface
from ..adaptor_runtime._named_pipe.named_pipe_helper import NamedPipeHelper

_DEFAULT_TIMEOUT_IN_SECONDS = 15


class WinClientInterface(BaseClientInterface):
    def __init__(self, server_path: str) -> None:
        """When the client is created, we need the port number to connect to the server.

        Args:
            server_path (str): Used as pipe name in Named Pipe Server.
        """
        super().__init__(server_path)
        _signal.signal(_signal.SIGTERM, self.graceful_shutdown)  # type: ignore[attr-defined]

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        query_string_params: dict | None = None,
    ):
        if query_string_params:
            # This is used for aligning to the Linux's behavior in order to reuse the code in handler.
            # In linux, query string params will always be put in a list.
            query_string_params = {key: [value] for key, value in query_string_params.items()}
        json_result = NamedPipeHelper.send_named_pipe_request(
            self.server_path,
            _DEFAULT_TIMEOUT_IN_SECONDS,
            method,
            path,
            params=query_string_params,
        )
        return _Response(
            json_result["status"],
            json_result["body"],
            http.client.responses[json_result["status"]],
            len(json_result["body"]),
        )
