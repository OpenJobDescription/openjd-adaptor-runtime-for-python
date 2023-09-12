# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from pytest import param

import openjd.adaptor_runtime.adaptors._base_adaptor as base_adaptor
from openjd.adaptor_runtime.adaptors._base_adaptor import (
    _ENV_CONFIG_PATH_TEMPLATE,
    _ENV_CONFIG_SCHEMA_PATH_PREFIX,
    AdaptorConfigurationOptions,
    BaseAdaptor,
    _ModuleInfo,
)
from openjd.adaptor_runtime.adaptors.configuration import AdaptorConfiguration

from .fake_adaptor import FakeAdaptor


class TestConfigProperty:
    """
    Tests for the configuration property in BaseAdaptor.
    """

    @patch.object(BaseAdaptor, "_load_configuration_manager")
    def test_lazily_loads_config(self, mock_load_config_manager: MagicMock):
        # GIVEN
        mock_config = MagicMock()
        mock_config_manager = MagicMock()
        mock_config_manager.build_config.return_value = mock_config
        mock_load_config_manager.return_value = mock_config_manager
        adaptor = FakeAdaptor({})

        mock_load_config_manager.assert_not_called()
        mock_config_manager.build_config.assert_not_called()

        # WHEN
        config = adaptor.config

        # THEN
        mock_load_config_manager.assert_called_once()
        mock_config_manager.build_config.assert_called_once()
        assert config is mock_config

    @patch.object(BaseAdaptor, "_load_configuration_manager")
    def test_uses_loaded_config(self, mock_load_config_manager: MagicMock):
        # GIVEN
        mock_config = MagicMock()
        mock_config_manager = MagicMock()
        mock_config_manager.build_config.return_value = mock_config
        mock_load_config_manager.return_value = mock_config_manager
        adaptor = FakeAdaptor({})

        # Get the property to lazily load the config
        adaptor.config

        # WHEN
        config = adaptor.config

        # THEN
        mock_load_config_manager.assert_called_once()
        mock_config_manager.build_config.assert_called_once()
        assert config is mock_config

    @patch.object(BaseAdaptor, "_load_configuration_manager")
    def test_lazily_loads_config_manager(self, mock_load_config_manager: MagicMock):
        # GIVEN
        mock_config_manager = MagicMock()
        mock_load_config_manager.return_value = mock_config_manager
        adaptor = FakeAdaptor({})

        mock_load_config_manager.assert_not_called()

        # WHEN
        config_manager = adaptor.config_manager

        # THEN
        mock_load_config_manager.assert_called_once()
        assert config_manager is mock_config_manager

    @patch.object(BaseAdaptor, "_load_configuration_manager")
    def test_uses_loaded_config_manager(self, mock_load_config_manager: MagicMock):
        # GIVEN
        mock_config_manager = MagicMock()
        mock_load_config_manager.return_value = mock_config_manager
        adaptor = FakeAdaptor({})

        # Get the property to lazily load the config manager
        adaptor.config_manager

        # WHEN
        config_manager = adaptor.config_manager

        # THEN
        mock_load_config_manager.assert_called_once()
        assert config_manager is mock_config_manager


class TestConfigLoading:
    """
    Tests for the adaptor configuration loading logic.
    """

    @pytest.mark.parametrize(
        argnames="schema_exists",
        argvalues=[True, False],
        ids=["Default schema exists", "Default schema does not exist"],
    )
    @patch.object(base_adaptor, "create_adaptor_configuration_manager")
    @patch.object(_ModuleInfo, "package", new_callable=PropertyMock)
    @patch.object(_ModuleInfo, "file", new_callable=PropertyMock)
    @patch.object(base_adaptor.os.path, "abspath")
    @patch.object(base_adaptor.os.path, "exists")
    def test_loads_config_from_module_info(
        self,
        mock_exists: MagicMock,
        mock_abspath: MagicMock,
        mock_file: MagicMock,
        mock_package: MagicMock,
        mock_create_adaptor_config_manager: MagicMock,
        schema_exists: bool,
    ):
        # GIVEN
        package = "openjd_fake_adaptor"
        mock_package.return_value = package
        mock_file.return_value = "path/to/file"

        module_path = "/root/dir/module.py"
        mock_abspath.return_value = module_path
        mock_exists.return_value = schema_exists
        adaptor = FakeAdaptor({})
        adaptor_name = "FakeAdaptor"

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {adaptor.__module__: MagicMock()}):
            adaptor._load_configuration_manager()

        # THEN
        config_path = os.path.join(os.path.dirname(module_path), f"{adaptor_name}.json")
        schema_path = os.path.join(os.path.dirname(module_path), f"{adaptor_name}.schema.json")
        mock_create_adaptor_config_manager.assert_called_once_with(
            config_cls=AdaptorConfiguration,
            adaptor_name=adaptor_name,
            default_config_path=config_path,
            schema_path=schema_path if schema_exists else None,
            additional_config_paths=[],
        )
        assert mock_file.call_count == 4
        assert mock_package.call_count == 1
        assert mock_abspath.call_count == 2
        mock_exists.assert_called_once_with(schema_path)

    @patch.object(base_adaptor, "create_adaptor_configuration_manager")
    @patch.object(_ModuleInfo, "file", new_callable=PropertyMock)
    @patch.object(_ModuleInfo, "package", new_callable=PropertyMock)
    def test_loads_config_from_environment_variables(
        self,
        mock_package: MagicMock,
        mock_file: MagicMock,
        mock_create_adaptor_config_manager: MagicMock,
    ):
        # GIVEN
        package = "openjd_fake_adaptor"
        mock_package.return_value = package
        adaptor = FakeAdaptor({})
        adaptor_name = "FakeAdaptor"
        additional_config_path = f"/path/to/additional/config/{adaptor_name}.json"
        config_path = f"/path/to/config/{adaptor_name}.json"
        schema_path = f"/path/to/schema/{adaptor_name}.schema.json"

        mock_file.return_value = config_path

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {adaptor.__module__: MagicMock()}):
            with patch.dict(
                base_adaptor.os.environ,
                {
                    f"FAKEADAPTOR_{_ENV_CONFIG_PATH_TEMPLATE}": additional_config_path,
                    _ENV_CONFIG_SCHEMA_PATH_PREFIX: os.path.dirname(schema_path),
                },
            ):
                adaptor._load_configuration_manager()

        # THEN
        mock_create_adaptor_config_manager.assert_called_once_with(
            config_cls=AdaptorConfiguration,
            adaptor_name=adaptor_name,
            default_config_path=config_path,
            schema_path=schema_path,
            additional_config_paths=[additional_config_path],
        )
        assert mock_package.call_count == 1

    @patch.object(base_adaptor, "create_adaptor_configuration_manager")
    @patch.object(_ModuleInfo, "package", new_callable=PropertyMock)
    def test_loads_config_from_options(
        self, mock_package: MagicMock, mock_create_adaptor_config_manager: MagicMock
    ):
        # GIVEN
        config_path = "/path/to/config"
        schema_path = "/path/to/schema"
        package = "openjd_fake_adaptor"
        mock_package.return_value = package
        adaptor = FakeAdaptor(
            {},
            config_opts=AdaptorConfigurationOptions(
                config_cls=None,
                config_path=config_path,
                schema_path=schema_path,
            ),
        )
        adaptor_name = "FakeAdaptor"

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {adaptor.__module__: MagicMock()}):
            adaptor._load_configuration_manager()

        # THEN
        mock_create_adaptor_config_manager.assert_called_once_with(
            config_cls=AdaptorConfiguration,
            adaptor_name=adaptor_name,
            default_config_path=config_path,
            schema_path=schema_path,
            additional_config_paths=[],
        )
        assert mock_package.call_count == 1

    def test_raises_when_module_not_loaded(self):
        # GIVEN
        adaptor = FakeAdaptor({})
        module_name = adaptor.__module__

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {module_name: None}):
            with pytest.raises(KeyError) as raised_err:
                adaptor._load_configuration_manager()

        # THEN
        assert raised_err.match(f"Module not loaded: {module_name}")

    @patch.object(_ModuleInfo, "name", new_callable=PropertyMock)
    @patch.object(_ModuleInfo, "package", new_callable=PropertyMock)
    def test_raises_when_module_not_package(
        self,
        mock_package: MagicMock,
        mock_name: MagicMock,
    ):
        # GIVEN
        adaptor = FakeAdaptor({})
        module_name = adaptor.__module__
        mock_name.return_value = module_name
        mock_package.return_value = None

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {module_name: MagicMock()}):
            with pytest.raises(ValueError) as raised_err:
                adaptor._load_configuration_manager()

        # THEN
        assert raised_err.match(f"Module {module_name} is not a package")

    @patch.object(_ModuleInfo, "name", new_callable=PropertyMock)
    @patch.object(_ModuleInfo, "package", new_callable=PropertyMock)
    @patch.object(_ModuleInfo, "file", new_callable=PropertyMock)
    def test_raises_when_module_no_filepath(
        self,
        mock_file: MagicMock,
        mock_package: MagicMock,
        mock_name: MagicMock,
    ):
        # GIVEN
        adaptor = FakeAdaptor({})
        module_name = adaptor.__module__
        mock_name.return_value = module_name
        mock_package.return_value = "package"
        mock_file.return_value = None

        # WHEN
        with patch.dict(base_adaptor.sys.modules, {module_name: MagicMock()}):
            with pytest.raises(ValueError) as raised_err:
                adaptor._load_configuration_manager()

        # THEN
        assert mock_package.call_count == 1
        mock_file.assert_called_once()
        assert raised_err.match(f"Module {module_name} does not have a file path set")


class TestStatusUpdate:
    """Tests for sending status updates"""

    _OPENJD_PROGRESS_STDOUT_PREFIX: str = "openjd_progress: "
    _OPENJD_STATUS_STDOUT_PREFIX: str = "openjd_status: "

    @pytest.mark.parametrize(
        "progress",
        [
            param(-10000.0),
            param(0),
            param(0.0),
            param(33.3333333333333),
            param(50.0),
            param(100.0),
            param(100000.0),
            param(1e5),
            param(1e-5),
        ],
    )
    def test_progress_update(self, capsys, progress: float):
        """Tests just updating the progress"""
        # GIVEN
        expected = f"{self._OPENJD_PROGRESS_STDOUT_PREFIX}{progress}"

        # WHEN
        BaseAdaptor.update_status(progress=progress)

        # THEN
        assert expected in capsys.readouterr().out

    @pytest.mark.parametrize(
        "status_message",
        [
            param("my epic new status message"),
            param("33.33333"),
            param(""),
        ],
    )
    def test_status_message_update(self, capsys, status_message: str):
        """Tests just updating the status message"""
        # GIVEN
        expected = f"{self._OPENJD_STATUS_STDOUT_PREFIX}{status_message}"

        # WHEN
        BaseAdaptor.update_status(status_message=status_message)

        # THEN
        assert expected in capsys.readouterr().out

    @pytest.mark.parametrize(
        "progress,status_message",
        [
            param(-350.0, "...negative progress?"),
            param(0.0, ""),
            param(10.0, "making some progress"),
            param(33.33333, "33.33333"),
            param(100.0, "just finished!"),
            param(
                100000.0,
                "this farm accepts a lot of progress and this is a really long status message",
            ),
        ],
    )
    def test_status_update(self, capsys, progress: float, status_message: str):
        """Tests updating both progress and status messages"""
        # GIVEN
        expected_progress = f"{self._OPENJD_PROGRESS_STDOUT_PREFIX}{progress}"
        expected_status_message = f"{self._OPENJD_STATUS_STDOUT_PREFIX}{status_message}"

        # WHEN
        BaseAdaptor.update_status(progress=progress, status_message=status_message)

        # THEN
        result = capsys.readouterr().out
        assert expected_progress in result
        assert expected_status_message in result

    def test_ignore_status_update(self, capsys):
        """Tests we don't send any message if there's nothing to report"""
        # GIVEN
        expected = ""  # nothing was captured in stdout

        # WHEN
        BaseAdaptor.update_status(progress=None, status_message=None)
        BaseAdaptor.update_status(progress=float("NaN"))
        BaseAdaptor.update_status(progress=float("inf"))

        # THEN
        result = capsys.readouterr().out
        assert expected == result
