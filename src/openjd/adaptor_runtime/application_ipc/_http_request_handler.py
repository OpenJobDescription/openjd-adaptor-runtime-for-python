# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from time import sleep
from typing import TYPE_CHECKING
from typing import Optional

from .._http import HTTPResponse, RequestHandler, ResourceRequestHandler

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from openjd.adaptor_runtime_client import Action

    from ._adaptor_server import AdaptorServer


class AdaptorHTTPRequestHandler(RequestHandler):
    """This is the HTTPRequestHandler to be used by the Adaptor Server. This class is
    where we will dequeue the actions from the queue and pass it in a response to a client.
    """

    server: AdaptorServer  # This is here for type hinting.

    def __init__(
        self,
        request: bytes,
        client_address: str,
        server: AdaptorServer,
    ) -> None:
        super().__init__(request, client_address, server, AdaptorResourceRequestHandler)


class AdaptorResourceRequestHandler(ResourceRequestHandler):
    """
    Base class that handles HTTP requests for a specific resource.

    This class only works with an AdaptorServer.
    """

    server: AdaptorServer  # This is just for type hinting


class PathMappingEndpoint(AdaptorResourceRequestHandler):
    path = "/path_mapping"

    def get(self) -> HTTPResponse:
        """
        GET Handler for the Path Mapping Endpoint

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """
        try:
            if "path" in self.query_string_params:
                return HTTPResponse(
                    HTTPStatus.OK,
                    json.dumps(
                        {"path": self.server.adaptor.map_path(self.query_string_params["path"][0])}
                    ),
                )
            else:
                return HTTPResponse(HTTPStatus.BAD_REQUEST, "Missing path in query string.")
        except Exception as e:
            return HTTPResponse(HTTPStatus.INTERNAL_SERVER_ERROR, body=str(e))


class PathMappingRulesEndpoint(AdaptorResourceRequestHandler):
    path = "/path_mapping_rules"

    def get(self) -> HTTPResponse:
        """
        GET Handler for the Path Mapping Rules Endpoint

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """
        return HTTPResponse(
            HTTPStatus.OK,
            json.dumps(
                {
                    "path_mapping_rules": [
                        rule.to_dict() for rule in self.server.adaptor.path_mapping_rules
                    ]
                }
            ),
        )


class ActionEndpoint(AdaptorResourceRequestHandler):
    path = "/action"

    def get(self) -> HTTPResponse:
        """
        GET handler for the Action end point of the Adaptor Server that communicates with the client
        spawned in the DCC.

        Returns:
            HTTPResponse: A body and response code to send to the DCC Client
        """
        action = self._dequeue_action()

        # We are going to wait until we have an action in the queue. This
        # could happen between tasks.
        while action is None:
            sleep(0.01)
            action = self._dequeue_action()

        return HTTPResponse(HTTPStatus.OK, str(action))

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
