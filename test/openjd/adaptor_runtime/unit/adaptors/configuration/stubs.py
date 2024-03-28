# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from typing_extensions import Literal

from openjd.adaptor_runtime.adaptors.configuration import (
    AdaptorConfiguration,
    Configuration,
    ConfigurationManager,
    RuntimeConfiguration,
)


class RuntimeConfigurationStub(RuntimeConfiguration):
    """
    Stub implementation of RuntimeConfiguration
    """

    def __init__(self) -> None:
        super().__init__({})

    @property
    def log_level(self) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        return "DEBUG"

    @property
    def deactivate_telemetry(self) -> bool:
        return True

    @property
    def plugin_configuration(self) -> dict | None:
        return None


class AdaptorConfigurationStub(AdaptorConfiguration):
    """
    Stub implementation of AdaptorConfiguration
    """

    def __init__(self) -> None:
        super().__init__({})

    @property
    def log_level(
        self,
    ) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None:
        return "DEBUG"


class ConfigurationManagerMock(ConfigurationManager):
    """
    Mock implementation of ConfigurationManager with empty defaults.
    """

    def __init__(
        self,
        *,
        schema_path="",
        default_config_path="",
        system_config_path="",
        user_config_rel_path="",
        additional_config_paths=None,
    ) -> None:
        if additional_config_paths is None:
            additional_config_paths = []
        super().__init__(
            config_cls=Configuration,
            schema_path=schema_path,
            default_config_path=default_config_path,
            system_config_path=system_config_path,
            user_config_rel_path=user_config_rel_path,
            additional_config_paths=additional_config_paths,
        )
