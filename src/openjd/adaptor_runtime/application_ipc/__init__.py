# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from ._actions_queue import ActionsQueue
from .._osname import OSName

if OSName.is_posix():
    from ._adaptor_server import AdaptorServer

    __all__ = ["ActionsQueue", "AdaptorServer"]
else:
    __all__ = ["ActionsQueue"]
