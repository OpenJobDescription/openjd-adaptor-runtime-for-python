# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from .action import Action
from .base_client_interface import (
    PathMappingRule,
)
from ..adaptor_runtime._osname import OSName

if OSName.is_posix():
    from .posix_client_interface import HTTPClientInterface as ClientInterface

    # This is just for backward compatible
    from .posix_client_interface import HTTPClientInterface

    __all__ = ["Action", "PathMappingRule", "HTTPClientInterface", "ClientInterface"]

else:
    from .win_client_interface import WinClientInterface as ClientInterface  # type: ignore

    __all__ = ["Action", "PathMappingRule", "ClientInterface"]
