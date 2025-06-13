# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os

from ._actions_queue import ActionsQueue

if os.name == "nt":  # pragma: skip-coverage-posix
    from ._win_adaptor_server import WinAdaptorServer as AdaptorServer  # type: ignore
else:  # pragma: skip-coverage-windows
    from ._adaptor_server import AdaptorServer  # type: ignore

__all__ = ["ActionsQueue", "AdaptorServer"]
