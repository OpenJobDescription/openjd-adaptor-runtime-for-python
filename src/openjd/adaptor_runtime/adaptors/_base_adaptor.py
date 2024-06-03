# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging
import math
import os
import sys
from abc import abstractproperty
from dataclasses import dataclass
from types import ModuleType
from typing import Generic
from typing import Type
from typing import TypeVar

from .._utils._constants import _OPENJD_PROGRESS_STDOUT_PREFIX, _OPENJD_STATUS_STDOUT_PREFIX
from .configuration import AdaptorConfiguration, ConfigurationManager
from .configuration._configuration_manager import (
    create_adaptor_configuration_manager as create_adaptor_configuration_manager,
)
from ._adaptor_states import AdaptorStates
from ._path_mapping import PathMappingRule
from ._versioning import SemanticVersion

__all__ = [
    "AdaptorConfigurationOptions",
    "BaseAdaptor",
]

# "{ADAPTORNAME}_" is put in front of these variables to make the full env variable
# ie. MAYAADAPTOR_CONFIG_PATH
_ENV_CONFIG_PATH_TEMPLATE = "CONFIG_PATH"
# Directory containing adaptor schemas
_ENV_CONFIG_SCHEMA_PATH_PREFIX = "ADAPTOR_CONFIG_SCHEMA_PATH"

_T = TypeVar("_T", bound=AdaptorConfiguration)

_logger = logging.getLogger(__name__)


@dataclass
class AdaptorConfigurationOptions(Generic[_T]):
    """Options for adaptor configuration."""

    config_cls: Type[_T] | None = None
    """The adaptor configuration class to use."""
    config_path: str | None = None
    """The path to the adaptor configuration file."""
    schema_path: str | list[str] | None = None
    """The path to the JSON Schema file."""


class BaseAdaptor(AdaptorStates, Generic[_T]):
    """
    Base class for adaptors.
    """

    _OPENJD_PROGRESS_STDOUT_PREFIX: str = _OPENJD_PROGRESS_STDOUT_PREFIX
    _OPENJD_STATUS_STDOUT_PREFIX: str = _OPENJD_STATUS_STDOUT_PREFIX

    def __init__(
        self,
        init_data: dict,
        *,
        config_opts: AdaptorConfigurationOptions[_T] | None = None,
        path_mapping_data: dict[str, list[dict[str, str]]] | None = None,
    ):
        """
        Args:
            init_data (dict): Data required to initialize the adaptor.
            config_opts (AdaptorConfigurationOptions[T], optional): Options for adaptor
            configuration.
        """
        self.init_data = init_data
        self._config_opts = config_opts
        self._path_mapping_data: dict = path_mapping_data or {}
        self._path_mapping_rules: list[PathMappingRule] = [
            PathMappingRule.from_dict(rule=rule)
            for rule in self._path_mapping_data.get("path_mapping_rules", [])
        ]

    def on_cancel(self):  # pragma: no cover
        """
        Invoked at the end of the `cancel` method.
        """
        pass

    def cancel(self):  # pragma: no cover
        """
        Cancels the run of this adaptor.
        """
        self.on_cancel()

    @abstractproperty
    def integration_data_interface_version(self) -> SemanticVersion:
        """
        Returns a SemanticVersion of the data-interface.
        Should be incremented when changes are made to any of the integration's:
            - init-data schema
            - run-data schema
        """
        pass

    @property
    def config_manager(self) -> ConfigurationManager[_T]:
        """
        Gets the lazily-loaded configuration manager for this adaptor.
        """
        if not hasattr(self, "_config_manager"):
            self._config_manager = self._load_configuration_manager()

        return self._config_manager

    @property
    def config(self) -> _T:
        """
        Gets the configuration for this adaptor.
        """
        if not hasattr(self, "_config"):
            self._config = self.config_manager.build_config()

        return self._config

    def _load_configuration_manager(self) -> ConfigurationManager[_T]:
        """
        Loads a configuration manager using the module of this instance.

        Raises:
            KeyError: Raised when the module is not loaded.
            ValueError: Raised when the module is not a package or does not have a file path set.
        """
        module = sys.modules.get(self.__module__)
        if module is None:
            raise KeyError(f"Module not loaded: {self.__module__}")

        module_info = _ModuleInfo(module)
        if not module_info.package:
            raise ValueError(f"Module {module_info.name} is not a package")

        adaptor_name = type(self).__name__
        config_cls = (
            self._config_opts.config_cls
            if self._config_opts and self._config_opts.config_cls
            else AdaptorConfiguration
        )
        config_path = (
            self._config_opts.config_path
            if self._config_opts and self._config_opts.config_path
            else None
        )
        schema_path = self._config_opts.schema_path if self._config_opts else None

        def module_dir() -> str:
            if not module_info.file:
                raise ValueError(f"Module {module_info.name} does not have a file path set")
            return os.path.dirname(os.path.abspath(module_info.file))

        if not config_path:
            config_path = os.path.join(module_dir(), f"{adaptor_name}.json")
        if not schema_path:
            schema_dir = os.environ.get(_ENV_CONFIG_SCHEMA_PATH_PREFIX)
            if schema_dir:
                # Schema dir was provided, so we assume a schema file exists at that location
                schema_path = os.path.join(schema_dir, f"{adaptor_name}.schema.json")
            else:
                # Schema dir was not provided, so we only provide the default schema path if it
                # exists
                schema_path = os.path.join(module_dir(), f"{adaptor_name}.schema.json")
                schema_path = schema_path if os.path.exists(schema_path) else None

        additional_config_paths = []
        adaptor_config_path_env = f"{adaptor_name.upper()}_{_ENV_CONFIG_PATH_TEMPLATE}"
        if additional_config_path := os.environ.get(adaptor_config_path_env):
            _logger.info(f"Found adaptor config environment variable: {adaptor_config_path_env}")
            additional_config_paths.append(additional_config_path)

        return create_adaptor_configuration_manager(
            config_cls=config_cls,
            adaptor_name=adaptor_name,
            default_config_path=config_path,
            schema_path=schema_path,
            additional_config_paths=additional_config_paths,
        )

    @classmethod
    def update_status(
        cls, *, progress: float | None = None, status_message: str | None = None
    ) -> None:
        """Using OpenJD stdout prefixes the adaptor will notify the
        Worker Agent about the progress, status message, or both"""
        if progress is None and status_message is None:
            _logger.warning("Both progress and status message were None. Ignoring status update.")
            return

        if progress is not None:
            if math.isfinite(progress):
                sys.stdout.write(f"{cls._OPENJD_PROGRESS_STDOUT_PREFIX}{progress}{os.linesep}")
                sys.stdout.flush()
            else:
                _logger.warning(
                    f"Attempted to set progress to something non-finite: {progress}. "
                    "Ignoring progress update."
                )
        if status_message is not None:
            sys.stdout.write(f"{cls._OPENJD_STATUS_STDOUT_PREFIX}{status_message}{os.linesep}")
            sys.stdout.flush()

    @property
    def path_mapping_rules(self) -> list[PathMappingRule]:
        """Returns the list of path mapping rules"""
        return self._path_mapping_rules.copy()

    def map_path(self, path: str) -> str:
        """Applies path mapping rules to the given path.
        Returns original path if no rules matched"""
        for rule in self._path_mapping_rules:
            changed, new_path = rule.apply(path=path)
            if changed:
                return new_path

        return path


class _ModuleInfo:  # pragma: no cover
    """
    This class wraps the ModuleType class and provides getters for magic attributes (e.g. __name__)
    so that they can be mocked in unit tests, since unittest.mock does not allow some magic
    attributes to be mocked.
    """

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def package(self) -> str | None:
        return self._module.__package__

    @property
    def file(self) -> str | None:
        return self._module.__file__

    @property
    def name(self) -> str:
        return self._module.__name__
