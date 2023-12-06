# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from time import sleep
from typing import TYPE_CHECKING, Callable, Dict, Any, Optional, Union

from .._http import HTTPResponse

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from openjd.adaptor_runtime_client import Action
    from ._adaptor_server import AdaptorServer
    from ._win_adaptor_server import WinAdaptorServer


class AdaptorServerResponseGenerator:
    """
    This class is used for generating responses for all requests to the Adaptor server.
    Response methods follow format: `generate_{request_path}_{method}_response`
    """

    def __init__(
        self,
        server: Union[AdaptorServer, WinAdaptorServer],
        response_fn: Callable,
        query_string_params: Dict[str, Any],
    ) -> None:
        """
        Response generator

        Args:
            server: The server used for communication. For Linux, this will
                be a AdaptorServer instance.
            response_fn: The function used to return the result to the client.
                For Linux, this will be an HTTPResponse instance.
            query_string_params: The request parameters sent by the client.
                For Linux, these will be extracted from the URL.
        """
        self.server = server
        self.response_method = response_fn
        self.query_string_params = query_string_params

    def generate_path_mapping_get_response(self) -> HTTPResponse:
        """
        Handle GET request to /path_mapping path.

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """

        if "path" in self.query_string_params:
            return self.response_method(
                HTTPStatus.OK,
                json.dumps(
                    {"path": self.server.adaptor.map_path(self.query_string_params["path"][0])}
                ),
            )
        else:
            return self.response_method(HTTPStatus.BAD_REQUEST, "Missing path in query string.")

    def generate_path_mapping_rules_get_response(self) -> HTTPResponse:
        """
        Handle GET request to /path_mapping_rules path.

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """
        return self.response_method(
            HTTPStatus.OK,
            json.dumps(
                {
                    "path_mapping_rules": [
                        rule.to_dict() for rule in self.server.adaptor.path_mapping_rules
                    ]
                }
            ),
        )

    def generate_action_get_response(self) -> HTTPResponse:
        """
        Handle GET request to /action path.

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """
        action = self._dequeue_action()

        # We are going to wait until we have an action in the queue. This
        # could happen between tasks.
        while action is None:
            sleep(0.01)
            action = self._dequeue_action()

        return self.response_method(HTTPStatus.OK, str(action))

    def _dequeue_action(self) -> Optional[Action]:
        """This function will dequeue the first action in the queue.

        Returns:
            Action: A tuple containing the next action structured:
            ("action_name", { "args1": "val1", "args2": "val2" })

            None: If the Actions Queue is empty.

        Raises:
            TypeError: If the server isn't an AdaptorServer.
        """
        # This condition shouldn't matter, because we have typehinted the server above.
        # This is only here for type hinting (as is the return None below).
        if hasattr(self, "server") and hasattr(self.server, "actions_queue"):
            return self.server.actions_queue.dequeue_action()

        print(
            "ERROR: Could not retrieve the next action because the server or actions queue "
            "wasn't set.",
            file=sys.stderr,
            flush=True,
        )
        return None
