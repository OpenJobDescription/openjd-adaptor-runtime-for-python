# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
"""
This module contains the configuration classes used for the adaptor runtime and the adaptors
themselves.

The base Configuration class exposes a "config" property that returns a dictionary of the loaded
config values with defaults injected where applicable. To do this, the following pattern is used:

1. The "config" property obtains a function with a "registry" attribute that maps function names to
functions from the virtual class method "_get_defaults_decorator".
2. For each key in the "registry" that is not in the loaded configuration, the corresponding
function is invoked to obtain the "default" value to inject into the returned configuration.

By default, "_get_defaults_decorator" returns a no-op decorator that has an empty registry.
Classes that derive the base Configuration class can override this class method to return a
decorator created by the "_make_function_register_decorator" function. This decorator actually
registers functions it is applied to, so it can be used to mark properties that should have default
values injected if none are loaded. For example, the following subclass uses this pattern to mark
the "my_config_key" property as one that uses a default value:

Note: The property name must match the corresponding key in the configuration dictionary.

class MyConfiguration(Configuration):

    _defaults = _make_function_register_decorator()

    @classmethod
    def _get_defaults_decorator(cls) -> Any:
        return cls._defaults

    @property
    @_defaults
    def my_config_key(self) -> str:
        return self._config.get("my_config_key", "default_value")
"""

from ._configuration import (
    AdaptorConfiguration,
    Configuration,
    RuntimeConfiguration,
)
from ._configuration_manager import ConfigurationManager

__all__ = ["AdaptorConfiguration", "Configuration", "ConfigurationManager", "RuntimeConfiguration"]
