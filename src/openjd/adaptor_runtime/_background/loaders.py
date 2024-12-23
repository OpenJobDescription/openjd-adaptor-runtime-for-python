# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import abc
import dataclasses
import logging
import json
import os
from pathlib import Path

from .model import (
    ConnectionSettings,
    DataclassMapper,
)

_logger = logging.getLogger(__name__)


class ConnectionSettingsLoadingError(Exception):
    """Raised when the connection settings cannot be loaded"""

    pass


class ConnectionSettingsLoader(abc.ABC):
    @abc.abstractmethod
    def load(self) -> ConnectionSettings:
        pass


@dataclasses.dataclass
class ConnectionSettingsFileLoader(ConnectionSettingsLoader):
    file_path: Path

    def load(self) -> ConnectionSettings:
        try:
            with open(self.file_path, encoding="utf-8") as conn_file:
                loaded_settings = json.load(conn_file)
        except OSError as e:
            errmsg = f"Failed to open connection file '{self.file_path}': {e}"
            _logger.error(errmsg)
            raise ConnectionSettingsLoadingError(errmsg) from e
        except json.JSONDecodeError as e:
            errmsg = f"Failed to decode connection file '{self.file_path}': {e}"
            _logger.error(errmsg)
            raise ConnectionSettingsLoadingError(errmsg) from e
        return DataclassMapper(ConnectionSettings).map(loaded_settings)


@dataclasses.dataclass
class ConnectionSettingsEnvLoader(ConnectionSettingsLoader):
    env_map: dict[str, tuple[str, bool]] = dataclasses.field(
        default_factory=lambda: {"socket": ("OPENJD_ADAPTOR_SOCKET", True)}
    )
    """Mapping of environment variable to a tuple of ConnectionSettings attribute name, and whether it is required"""

    def load(self) -> ConnectionSettings:
        kwargs = {}
        for attr_name, (env_name, required) in self.env_map.items():
            env_val = os.environ.get(env_name)
            if not env_val:
                if required:
                    raise ConnectionSettingsLoadingError(
                        f"Required attribute '{attr_name}' does not have its corresponding environment variable '{env_name}' set"
                    )
            else:
                kwargs[attr_name] = env_val
        return ConnectionSettings(**kwargs)
