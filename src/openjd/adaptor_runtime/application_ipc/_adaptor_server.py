# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
from .._osname import OSName

if OSName.is_windows():
    # TODO: This is for avoid type errors when enabling Github CI in Windows
    #   need to clear this up before GA
    from socketserver import TCPServer as UnixStreamServer  # type: ignore
else:
    from socketserver import UnixStreamServer  # type: ignore
from typing import TYPE_CHECKING

from .._http import SocketDirectories
from ._http_request_handler import AdaptorHTTPRequestHandler

if TYPE_CHECKING:  # pragma: no cover because pytest will think we should test for this.
    from ..adaptors import BaseAdaptor
    from ._actions_queue import ActionsQueue


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
        socket_path = SocketDirectories.for_os().get_process_socket_path("dcc", create_dir=True)
        super().__init__(socket_path, AdaptorHTTPRequestHandler)

        self.actions_queue = actions_queue
        self.adaptor = adaptor
        self.socket_path = socket_path

    def shutdown(self) -> None:  # pragma: no cover
        super().shutdown()

        try:
            os.remove(self.socket_path)
        except FileNotFoundError:
            pass
