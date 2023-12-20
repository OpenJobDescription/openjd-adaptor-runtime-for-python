# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.


from __future__ import annotations

import json as _json
import sys as _sys
from abc import abstractmethod as _abstractmethod
from abc import ABC as _ABC

from dataclasses import dataclass as _dataclass
from functools import lru_cache as _lru_cache
from http import HTTPStatus as _HTTPStatus
from types import FrameType as _FrameType
from typing import (
    Any as _Any,
    Callable as _Callable,
    Dict as _Dict,
    List as _List,
    Tuple as _Tuple,
)
from .action import Action as _Action


# Based on adaptor runtime's PathMappingRule class
# This is needed because we cannot import from adaptor runtime directly
# due to some applications running an older Python version that can't import newer typing
@_dataclass
class PathMappingRule:
    source_path_format: str
    source_path: str
    destination_path: str
    destination_os: str


@_dataclass
class Response:
    """
    A response wrapper class
    """

    status: int
    body: str
    reason: str
    length: int


class BaseClientInterface(_ABC):
    actions: _Dict[str, _Callable[..., None]]
    server_path: str

    def __init__(self, server_path: str) -> None:
        """
        When the client is created, we need the server address to connect to the server.

        Args:
            server_path(str): Server address used for connection.
                In linux, this will be used for socket path.
                In Windows, this will be used for pipe name.
        """
        self.server_path = server_path
        self.actions = {
            "close": self.close,
        }

    @_abstractmethod
    def _send_request(
        self, method: str, request_path: str, *, query_string_params: _Dict | None = None
    ) -> Response:
        """
        Send a request to the server and return the response.

        This abstract method should be implemented by subclasses to handle
        sending the actual request.

        Args:
            method (str): The HTTP method, e.g. 'GET', 'POST'.
            request_path (str): The path for the request.
            query_string_params (_Dict | None, optional): Query string parameters to include
                in the request. Defaults to None.

        Returns:
            Response: The response from the server.
        """
        pass

    @_abstractmethod
    def close(self, args: _Dict[str, _Any] | None) -> None:
        """This is the close function which will be called to cleanup the Application.

        Args:
            args (_Dict[str, _Any] | None): The arguments (if any) required to perform the
                                                cleanup.
        """
        pass

    @_abstractmethod
    def graceful_shutdown(self, signum: int, frame: _FrameType | None) -> None:
        """This is the function when we cancel. This function is called when a SIGTERM signal is
        received. This functions will need to be implemented for each application we want to
        support because the clean up will be different for each application.

        Args:
            signum (int): The signal number.
            frame (_FrameType | None): The current stack frame (None or a frame object).
        """
        pass

    def _request_next_action(self) -> _Tuple[int, str, _Action | None]:
        """Sending a get request to the server on the /action endpoint.
        This will be used to poll for the next action from the Adaptor server.

        Returns:
            _Tuple[int, str, _Action | None]: Returns the status code (int), the status reason
            (str), the action if one was received (_Action | None).
        """
        response = self._send_request("GET", "/action")

        action = None
        if response.length:
            response_body = _json.loads(response.body)
            action = _Action(response_body["name"], response_body["args"])
        return response.status, response.reason, action

    @_lru_cache(maxsize=None)
    def map_path(self, path: str) -> str:
        """Sending a get request to the server on the /path_mapping endpoint.
        This will be used to get the Adaptor to map a given path.

        Returns:
            str: The mapped path

        Raises:
            RuntimeError: When the client fails to get a mapped path from the server.
        """
        print(f"Requesting Path Mapping for path '{path}'.", flush=True)

        response = self._send_request("GET", "/path_mapping", query_string_params={"path": path})

        if response.status == _HTTPStatus.OK and response.length:
            response_dict = _json.loads(response.body)
            mapped_path = response_dict.get("path")
            if mapped_path is not None:  # pragma: no branch # HTTP 200 guarantees a mapped path
                print(f"Mapped path '{path}' to '{mapped_path}'.", flush=True)
                return mapped_path
        reason = response.body if response.length else ""
        raise RuntimeError(
            f"ERROR: Failed to get a mapped path for path '{path}'. "
            f"Server response: Status: {int(response.status)}, Response: '{reason}'",
        )

    @_lru_cache(maxsize=None)
    def path_mapping_rules(self) -> _List[PathMappingRule]:
        """Sending a get request to the server on the /path_mapping_rules endpoint.
        This will be used to get the Adaptor to map a given path.

        Returns:
            _List[_PathMappingRule]: The list of path mapping rules

        Raises:
            RuntimeError: When the client fails to get a mapped path from the server.
        """
        print("Requesting Path Mapping Rules.", flush=True)
        response = self._send_request("GET", "/path_mapping_rules")

        if response.status != _HTTPStatus.OK or not response.length:
            reason = response.body if response.length else ""
            raise RuntimeError(
                f"ERROR: Failed to get a path mapping rules. "
                f"Server response: Status: {int(response.status)}, Response: '{reason}'",
            )

        try:
            response_dict = _json.loads(response.body)
        except _json.JSONDecodeError as e:
            raise RuntimeError(
                f"Expected JSON string from /path_mapping_rules endpoint, but got error: {e}",
            )

        rule_list = response_dict.get("path_mapping_rules")
        if not isinstance(rule_list, list):
            raise RuntimeError(
                f"Expected list for path_mapping_rules, but got: {rule_list}",
            )

        rules: _List[PathMappingRule] = []
        for rule in rule_list:
            try:
                rules.append(PathMappingRule(**rule))
            except TypeError as e:
                raise RuntimeError(
                    f"Expected PathMappingRule object, but got: {rule}\nAll rules: {rule_list}\nError: {e}",
                )

        return rules

    def poll(self) -> None:
        """
        This function will poll the server for the next task. If the server is in between Subtasks
        (no actions in the queue), a backoff function will be called to add a delay between the
        requests.
        """
        run = True
        while run:
            status, reason, action = self._request_next_action()
            if status == _HTTPStatus.OK:
                if action is not None:
                    print(
                        f"Performing action: {action}",
                        flush=True,
                    )
                    self._perform_action(action)
                    run = action.name != "close"
            else:  # Any other status or reason
                print(
                    f"ERROR: An error was raised when trying to connect to the server: {status} "
                    f"{reason}",
                    file=_sys.stderr,
                    flush=True,
                )

    def _perform_action(self, a: _Action) -> None:
        try:
            action_func = self.actions[a.name]
        except KeyError:
            print(
                f"ERROR: Attempted to perform the following action: {a}. But this action doesn't "
                "exist in the actions dictionary.",
                file=_sys.stderr,
                flush=True,
            )
        else:
            action_func(a.args)
