# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
import warnings

from socketserver import UnixStreamServer  # type: ignore[attr-defined]
from typing import TYPE_CHECKING

from .._http import SocketPaths
from ._http_request_handler import AdaptorHTTPRequestHandler

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from ..adaptors import BaseAdaptor
    from ._actions_queue import ActionsQueue

SOCKET_PATH_DUPLICATED_MESSAGE = (
    "The 'socket_path' parameter is deprecated; use 'server_path' instead"
)


class AdaptorServer(UnixStreamServer):
    """
    This is the Adaptor server which will be passed the populated ActionsQueue from the Adaptor.
    """

    actions_queue: ActionsQueue
    adaptor: BaseAdaptor

    def __init__(
        self,
        actions_queue: ActionsQueue,
        adaptor: BaseAdaptor,
    ) -> None:  # pragma: no cover
        socket_path = SocketPaths.for_os().get_process_socket_path(
            ".openjd_adaptor_server",
            create_dir=True,
        )
        super().__init__(socket_path, AdaptorHTTPRequestHandler)

        self.actions_queue = actions_queue
        self.adaptor = adaptor
        self.server_path = socket_path

    @property
    def socket_path(self):
        warnings.warn(SOCKET_PATH_DUPLICATED_MESSAGE, DeprecationWarning)
        return self.server_path

    @socket_path.setter
    def socket_path(self, value):
        warnings.warn(SOCKET_PATH_DUPLICATED_MESSAGE, DeprecationWarning)
        self.server_path = value

    def shutdown(self) -> None:  # pragma: no cover
        super().shutdown()

        try:
            os.remove(self.socket_path)
        except FileNotFoundError:
            pass
