# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.


from __future__ import annotations

import copy
import json
import jsonschema
import logging
from json.decoder import JSONDecodeError
from typing import Any, List, Literal, Type, TypeVar

__all__ = [
    "Configuration",
    "RuntimeConfiguration",
]

_logger = logging.getLogger(__name__)


def _make_function_register_decorator():
    """
    Creates a decorator function that registers functions.

    If used on a function with the @property decorator, the outermost decorator must have
    "# type: ignore" to avoid a mypy error. See https://github.com/python/mypy/issues/1362

    See the comment block at the top of this file for more details.
    """
    registry = {}

    def register(fn):
        registry[fn.__name__] = fn
        return fn

    register.registry = registry  # type: ignore
    return register


_T = TypeVar("_T", bound="Configuration")


class Configuration:
    """
    General class for a JSON-based configuration.


    This class should not be instantiated directly. Use one of the following class methods to
    instantiate this class:
    - `Configuration.from_file`
    """

    @classmethod
    def _get_defaults_decorator(cls) -> Any:  # pragma: no cover
        """
        Virtual class method to get the defaults decorator. Defaults to an empty defaults registry.

        Override this in a subclass and return the value from _make_function_register_decorator()
        to have default values automatically applied to the .config property getter return value.

        See the comment block at the top of this file for more details.
        """

        def register(_):
            pass

        register.registry = {}  # type: ignore
        return register

    @classmethod
    def from_file(
        cls: Type[_T], config_path: str, schema_path: str | List[str] | None = None
    ) -> _T:
        """
        Loads a Configuration from a JSON file.

        Args:
            config_path (str): The path to the JSON file containing the configuration
            schema_path (str, List[str], Optional): The path(s) to the JSON Schema file to validate
            the configuration JSON with. If multiple are specified, they will be used in the order
            they are provided. If left as None, validation will be skipped.
        """

        try:
            with open(config_path, encoding="utf-8") as config_file:
                config = json.load(config_file)
        except OSError as e:
            _logger.error(f"Failed to open configuration at {config_path}: {e}")
            raise
        except JSONDecodeError as e:
            _logger.error(f"Failed to decode configuration at {config_path}: {e}")
            raise

        if schema_path is None:
            _logger.warning(
                f"JSON Schema file path not provided. "
                f"Configuration file {config_path} will not be validated."
            )
            return cls(config)
        elif not schema_path:
            raise ValueError(f"Schema path cannot be an empty {type(schema_path)}")

        schema_paths = schema_path if isinstance(schema_path, list) else [schema_path]
        for path in schema_paths:
            try:
                with open(path, encoding="utf-8") as schema_file:
                    schema = json.load(schema_file)
            except OSError as e:
                _logger.error(f"Failed to open configuration schema at {path}: {e}")
                raise
            except JSONDecodeError as e:
                _logger.error(f"Failed to decode configuration schema at {path}: {e}")
                raise

            try:
                jsonschema.validate(config, schema)
            except jsonschema.ValidationError as e:
                _logger.error(
                    f"Configuration file at {config_path} failed to validate against the JSON "
                    f"schema at {schema_path}: {e}"
                )
                raise

        return cls(config)

    def __init__(self, config: dict) -> None:
        self._config = config

    def override(self: _T, other: _T) -> _T:
        """
        Creates a new Configuration with the configuration values in this object overridden by
        another configuration.

        Args:
            other (Configuration): The configuration with the override values.

        Returns:
            Configuration: A new Configuration with overridden values.
        """
        return self.__class__(copy.deepcopy({**self._config, **other._config}))

    @property
    def config(self) -> dict:
        """
        Gets the configuration dictionary with defaults applied to any missing required fields.

        See the comment block at the top of this file for more details.
        """
        config = copy.deepcopy(self._config)
        defaults = self.__class__._get_defaults_decorator()

        for fn_name, fn in defaults.registry.items():
            if fn_name not in config:  # pragma: no branch
                config[fn_name] = fn(self)

        return config


class RuntimeConfiguration(Configuration):
    """
    Configuration for the Adaptor Runtime.
    """

    _defaults = _make_function_register_decorator()

    @classmethod
    def _get_defaults_decorator(cls) -> Any:  # pragma: no cover
        return cls._defaults

    @property  # type: ignore
    @_defaults
    def log_level(
        self,
    ) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:  # pragma: no cover # noqa: F821
        """
        The log level that is used in the runtime.
        """
        return self._config.get("log_level", "INFO")

    @property  # type: ignore
    @_defaults
    def deactivate_telemetry(self) -> bool:  # pragma: no cover
        """
        Indicates whether telemetry is deactivated or not.
        """
        return self._config.get("deactivate_telemetry", False)


class AdaptorConfiguration(Configuration):
    """
    Configuration for adaptors.
    """

    _defaults = _make_function_register_decorator()

    @classmethod
    def _get_defaults_decorator(cls) -> Any:  # pragma: no cover
        return cls._defaults

    @property  # type: ignore
    @_defaults
    def log_level(
        self,
    ) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:  # noqa: F821  # pragma: no cover
        """
        The log level that is used in this adaptor.
        """
        return self._config.get("log_level", "INFO")
