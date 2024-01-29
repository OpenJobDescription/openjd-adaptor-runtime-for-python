# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from ._actions_queue import ActionsQueue
from .._osname import OSName

if OSName.is_posix():  # pragma: is-windows
    from ._adaptor_server import AdaptorServer
else:  # pragma: is-posix
    from ._win_adaptor_server import WinAdaptorServer as AdaptorServer  # type: ignore

__all__ = ["ActionsQueue", "AdaptorServer"]
