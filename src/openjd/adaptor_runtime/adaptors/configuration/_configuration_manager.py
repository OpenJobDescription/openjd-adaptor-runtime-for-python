# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import stat
from typing import Generic, List, Type, TypeVar

from ..._utils import secure_open
from ..._osname import OSName
from ._configuration import AdaptorConfiguration, Configuration

__all__ = [
    "ConfigurationManager",
    "create_adaptor_configuration_manager",
]

_logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.realpath(__file__))

_ConfigType = TypeVar("_ConfigType", bound=Configuration)
_AdaptorConfigType = TypeVar("_AdaptorConfigType", bound=AdaptorConfiguration)
_AdaptorConfigClassType = Type[_AdaptorConfigType]


def create_adaptor_configuration_manager(
    config_cls: _AdaptorConfigClassType,
    adaptor_name: str,
    default_config_path: str,
    schema_path: str | List[str] | None = None,
    additional_config_paths: List[str] | None = None,
) -> ConfigurationManager[_AdaptorConfigType]:
    """
    Creates a ConfigurationManager for an adaptor.

    Args:
        config_cls (Type[U], optional): The adaptor configuration class to create a configuration
        manager for.
        adaptor_name (str): The name of the adaptor.
        default_config_path (str): The path to the adaptor's default configuration file.
        schema_path (str, List[str], optional): The path(s) to a JSON Schema file(s) to validate
        the configuration with. If left as None, only the base adaptor configuration values will be
        validated.
        additional_config_paths (list[str], Optional): Paths to additional configuration files. These
        will have the highest priority and will be applied in the order they are provided.
    """
    if additional_config_paths is None:
        additional_config_paths = []
    schema_paths = [os.path.abspath(os.path.join(_DIR, "_adaptor_configuration.schema.json"))]
    if isinstance(schema_path, str):
        schema_paths.append(schema_path)
    elif isinstance(schema_path, list):
        schema_paths.extend(schema_path)

    system_config_path_prefix = "/etc" if OSName.is_posix() else os.environ["PROGRAMDATA"]
    system_config_path = os.path.join(
        system_config_path_prefix,
        "openjd",
        "adaptors",
        adaptor_name,
        f"{adaptor_name}.json",
    )

    user_config_rel_path = os.path.join(".openjd", "adaptors", adaptor_name, f"{adaptor_name}.json")

    return ConfigurationManager(
        config_cls=config_cls,
        default_config_path=default_config_path,
        system_config_path=system_config_path,
        user_config_rel_path=user_config_rel_path,
        schema_path=schema_paths,
        additional_config_paths=additional_config_paths,
    )


def _ensure_config_file(filepath: str, *, create: bool = False) -> bool:
    """
    Ensures a config file path points to a file.

    Args:
        filepath (str): The file path to validate.
        create (bool): Whether to create an empty config if the file does not exist.

    Returns:
        bool: True if the path points to a file, false otherwise. If create is set to True, this
        function will return True if the file was created successfully, false otherwise.
    """
    if not os.path.exists(filepath):
        _logger.debug(f'Configuration file at "{filepath}" does not exist.')
        if not create:
            return False

        _logger.info(f"Creating empty configuration at {filepath}")
        try:
            os.makedirs(os.path.dirname(filepath), mode=stat.S_IRWXU, exist_ok=True)
            with secure_open(filepath, open_mode="w", encoding="utf-8") as f:
                json.dump({}, f)
        except OSError as e:
            _logger.warning(f"Could not write empty configuration to {filepath}: {e}")
            return False
        else:
            return True
    elif not os.path.isfile(filepath):
        _logger.debug(f'Configuration file at "{filepath}" is not a file.')
        return False
    else:
        return True


class ConfigurationManager(Generic[_ConfigType]):
    """
    Class that manages configuration.
    """

    def __init__(
        self,
        *,
        config_cls: Type[_ConfigType],
        default_config_path: str,
        system_config_path: str,
        user_config_rel_path: str,
        schema_path: str | List[str] | None = None,
        additional_config_paths: list[str] | None = None,
    ) -> None:
        """
        Initializes a ConfigurationManager object.

        Args:
            config_cls (Type[T]): The Configuration class that this class manages.
            default_config_path (str): The path to the default configuration JSON file.
            system_config_path (str): The path to the system config file.
            user_config_rel_path (str): The path to the user configuration file relative to the
            user's home directory.
            schema_path (str, List[str], Optional): The path(s) to the JSON Schema file to use.
            If multiple are given then they will be used in the order they are provided.
            If none are given then validation will be skipped for configuration files.
            additional_config_paths (list[str], Optional): Paths to additional configuration files. These
            will have the highest priority and will be applied in the order they are provided.
        """
        if additional_config_paths is None:
            additional_config_paths = []
        self._config_cls = config_cls
        self._schema_path = schema_path
        self._default_config_path = default_config_path
        self._system_config_path = system_config_path
        self._user_config_rel_path = user_config_rel_path
        self._additional_config_paths = additional_config_paths

    def get_default_config(self) -> _ConfigType:
        """
        Gets the default configuration.
        """
        if not _ensure_config_file(self._default_config_path, create=True):
            _logger.warning(
                f"Default configuration file at {self._default_config_path} is not a valid file. "
                "Using empty configuration."
            )
            return self._config_cls({})

        return self._config_cls.from_file(self._default_config_path, self._schema_path)

    def get_system_config_path(self) -> str:
        """
        Gets the system-level configuration file path.

        """

        return self._system_config_path

    def get_system_config(self) -> _ConfigType | None:
        """
        Gets the system-level configuration. Any values defined here will override the default
        configuration.
        """
        config_path = self.get_system_config_path()
        return (
            self._config_cls.from_file(config_path, self._schema_path)
            if _ensure_config_file(config_path)
            else None
        )

    def get_user_config_path(self, username: str | None = None) -> str:
        """
        Gets the user-level configuration file path.

        Args:
            username (str, optional): The username to get the configuration for. Defaults to the
            current user.
        """
        user = f"~{username}" if username else "~"

        # os.path.expanduser works cross-platform (Windows & UNIX)
        return os.path.expanduser(os.path.join(user, self._user_config_rel_path))

    def get_user_config(self, username: str | None = None) -> _ConfigType | None:
        """
        Gets the user-level configuration. Any values defined here will override the default and
        system configuration.

        Args:
            username (str, optional): The username to get the configuration for. Defaults to the
            current user.
        """
        config_path = self.get_user_config_path(username)
        return (
            self._config_cls.from_file(config_path, self._schema_path)
            if _ensure_config_file(config_path, create=True)
            else None
        )

    def build_config(self, username: str | None = None) -> _ConfigType:
        """
        Builds a Configuration with the default, system, and user level configuration files.

        Args:
            username (str, optional): The username to use for the user-level configuration.
            Defaults to the current user.
        """

        def log_diffs(a: _ConfigType, b: _ConfigType):
            def _config_to_set(config: _ConfigType):
                # Convert inner dicts to str because elements in a set must be hashable.
                # This aligns with our override logic that only overrides top-level keys.
                return set(
                    [
                        (k, v if not isinstance(v, dict) else str(v))
                        for k, v in config._config.items()
                    ]
                )

            diffs = dict(_config_to_set(a) - _config_to_set(b))
            for k, v in diffs.items():
                _logger.info(f"Set {k} to {v}")

        config: _ConfigType = self.get_default_config()

        system_config = self.get_system_config()
        if system_config:
            _logger.info(f"Applying system-level configuration: {self._system_config_path}")
            old_config = config
            config = config.override(system_config)
            log_diffs(config, old_config)

        user_config = self.get_user_config(username)
        if user_config:
            _logger.info(f"Applying user-level configuration: {self.get_user_config_path()}")
            old_config = config
            config = config.override(user_config)
            log_diffs(config, old_config)

        for path in self._additional_config_paths:
            if not _ensure_config_file(path):
                _logger.warning(f"Failed to load additional configuration: {path}. Skipping...")
                continue

            _logger.info(f"Applying additional configuration: {path}")
            old_config = config
            config = config.override(self._config_cls.from_file(path))
            log_diffs(config, old_config)

        return config
