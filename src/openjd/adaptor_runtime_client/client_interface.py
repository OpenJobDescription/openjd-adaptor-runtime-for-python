# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json as _json
import signal as _signal
import sys as _sys
from abc import ABC as _ABC
from abc import abstractmethod as _abstractmethod
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
from urllib.parse import urlencode as _urlencode

from .action import Action as _Action
from .connection import UnixHTTPConnection as _UnixHTTPConnection

# Set timeout to None so our requests are blocking calls with no timeout.
# See socket.settimeout
_REQUEST_TIMEOUT = None


# Based on adaptor runtime's PathMappingRule class
# This is needed because we cannot import from adaptor runtime directly
# due to some applications running an older Python version that can't import newer typing
@_dataclass
class PathMappingRule:
    source_path_format: str
    source_path: str
    destination_path: str
    destination_os: str


class HTTPClientInterface(_ABC):
    actions: _Dict[str, _Callable[..., None]]
    socket_path: str

    def __init__(self, socket_path: str) -> None:
        """When the client is created, we need the port number to connect to the server.

        Args:
            socket_path (str): The path to the UNIX domain socket to use.
        """
        self.socket_path = socket_path
        self.actions = {
            "close": self.close,
        }

        # NOTE: The signals SIGKILL and SIGSTOP cannot be caught, blocked, or ignored.
        # Reference: https://man7.org/linux/man-pages/man7/signal.7.html
        # SIGTERM graceful shutdown.
        _signal.signal(_signal.SIGTERM, self.graceful_shutdown)

    def _request_next_action(self) -> _Tuple[int, str, _Action | None]:
        """Sending a get request to the server on the /action endpoint.
        This will be used to poll for the next action from the Adaptor server.

        Returns:
            _Tuple[int, str, _Action | None]: Returns the status code (int), the status reason
            (str), the action if one was received (_Action | None).
        """
        headers = {
            "Content-type": "application/json",
        }
        connection = _UnixHTTPConnection(self.socket_path, timeout=_REQUEST_TIMEOUT)
        connection.request("GET", "/action", headers=headers)
        response = connection.getresponse()
        connection.close()

        action = None
        if response.length:
            action = _Action.from_bytes(response.read())
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
        headers = {
            "Content-type": "application/json",
        }
        connection = _UnixHTTPConnection(self.socket_path, timeout=_REQUEST_TIMEOUT)
        print(f"Requesting Path Mapping for path '{path}'.", flush=True)
        connection.request("GET", "/path_mapping?" + _urlencode({"path": path}), headers=headers)
        response = connection.getresponse()
        connection.close()

        if response.status == _HTTPStatus.OK and response.length:
            response_dict = _json.loads(response.read().decode())
            mapped_path = response_dict.get("path")
            if mapped_path is not None:  # pragma: no branch # HTTP 200 guarantees a mapped path
                print(f"Mapped path '{path}' to '{mapped_path}'.", flush=True)
                return mapped_path
        reason = response.read().decode() if response.length else ""
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
        headers = {
            "Content-type": "application/json",
        }
        connection = _UnixHTTPConnection(self.socket_path, timeout=_REQUEST_TIMEOUT)
        print("Requesting Path Mapping Rules.", flush=True)
        connection.request("GET", "/path_mapping_rules", headers=headers)
        response = connection.getresponse()
        connection.close()

        if response.status != _HTTPStatus.OK or not response.length:
            reason = response.read().decode() if response.length else ""
            raise RuntimeError(
                f"ERROR: Failed to get a path mapping rules. "
                f"Server response: Status: {int(response.status)}, Response: '{reason}'",
            )

        try:
            response_dict = _json.loads(response.read().decode())
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

    @_abstractmethod
    def close(self, args: _Dict[str, _Any] | None) -> None:  # pragma: no cover
        """This is the close function which will be called to cleanup the Application.

        Args:
            args (_Dict[str, _Any] | None): The arguments (if any) required to perform the
                                                cleanup.
        """
        pass

    @_abstractmethod
    def graceful_shutdown(self, signum: int, frame: _FrameType | None) -> None:  # pragma: no cover
        """This is the function when we cancel. This function is called when a SIGTERM signal is
        received. This functions will need to be implemented for each application we want to
        support because the clean up will be different for each application.

        Args:
            signum (int): The signal number.
            frame (_FrameType | None): The current stack frame (None or a frame object).
        """
        pass
