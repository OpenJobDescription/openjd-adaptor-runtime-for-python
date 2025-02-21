# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
import re
from typing import Generator as _Generator
from unittest.mock import MagicMock, call, mock_open, patch
import platform

import pytest

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.adaptors.configuration import (
    AdaptorConfiguration as _AdaptorConfiguration,
    Configuration as _Configuration,
)
import openjd.adaptor_runtime.adaptors.configuration._configuration_manager as configuration_manager
from openjd.adaptor_runtime.adaptors.configuration._configuration_manager import (
    _DIR as _configuration_manager_dir,
    ConfigurationManager,
    _ensure_config_file,
    create_adaptor_configuration_manager as _create_adaptor_configuration_manager,
)

from .stubs import ConfigurationManagerMock


class TestEnsureConfigFile:
    """
    Tests for the ConfigurationManager._ensure_config_file method
    """

    @pytest.fixture(autouse=True)
    def mock_makedirs(self) -> _Generator[MagicMock, None, None]:
        with patch.object(configuration_manager.os, "makedirs") as mock:
            yield mock

    @patch.object(configuration_manager.os.path, "isfile")
    @patch.object(configuration_manager.os.path, "exists")
    def test_returns_true_if_valid(self, mock_exists: MagicMock, mock_isfile: MagicMock):
        # GIVEN
        path = "my/path"
        mock_exists.return_value = True
        mock_isfile.return_value = True

        # WHEN
        result = _ensure_config_file(path)

        # THEN
        assert result
        mock_exists.assert_called_once_with(path)
        mock_isfile.assert_called_once_with(path)

    @patch.object(configuration_manager.os.path, "exists")
    def test_returns_false_when_file_does_not_exist(
        self, mock_exists: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        caplog.set_level(0)
        path = "my/path"
        mock_exists.return_value = False

        # WHEN
        result = _ensure_config_file(path)

        # THEN
        assert not result
        mock_exists.assert_called_once_with(path)
        assert f'Configuration file at "{path}" does not exist.' in caplog.text

    @patch.object(configuration_manager.os.path, "isfile")
    @patch.object(configuration_manager.os.path, "exists")
    def test_returns_false_when_path_points_to_nonfile(
        self, mock_exists: MagicMock, mock_isfile: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        caplog.set_level(0)
        path = "my/path"
        mock_exists.return_value = True
        mock_isfile.return_value = False

        # WHEN
        result = _ensure_config_file(path)

        # THEN
        assert not result
        mock_exists.assert_called_once_with(path)
        mock_isfile.assert_called_once_with(path)
        assert f'Configuration file at "{path}" is not a file.' in caplog.text

    @pytest.mark.parametrize(
        argnames=["created"],
        argvalues=[[True], [False]],
        ids=["created", "not created"],
    )
    @patch.object(configuration_manager.json, "dump")
    @patch.object(configuration_manager.os.path, "exists")
    def test_create(
        self,
        mock_exists: MagicMock,
        mock_dump: MagicMock,
        created: bool,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        caplog.set_level(0)
        path = "my/path"
        mock_exists.return_value = False

        open_mock: MagicMock
        with patch.object(configuration_manager, "secure_open", mock_open()) as open_mock:
            if not created:
                open_mock.side_effect = OSError()

            # WHEN
            result = _ensure_config_file(path, create=True)

        # THEN
        assert result == created
        mock_exists.assert_called_once_with(path)
        open_mock.assert_called_once_with(path, open_mode="w", encoding="utf-8")
        assert f'Configuration file at "{path}" does not exist.' in caplog.text
        assert f"Creating empty configuration at {path}" in caplog.text
        if created:
            mock_dump.assert_called_once_with({}, open_mock.return_value)
        else:
            assert f"Could not write empty configuration to {path}: " in caplog.text


@pytest.mark.skipif(not OSName.is_posix(), reason="Posix-specific tests")
class TestCreateAdaptorConfigurationManagerPosix:
    def test_creates_config_manager(self):
        """
        This test is fragile as it relies on the hardcoded path formats to adaptor config files.
        """
        # GIVEN
        adaptor_name = "adaptor"
        default_config_path = "/path/to/config"

        # WHEN
        result = _create_adaptor_configuration_manager(
            _AdaptorConfiguration,
            adaptor_name,
            default_config_path,
        )

        # THEN
        assert result._config_cls == _AdaptorConfiguration
        assert result._default_config_path == default_config_path
        assert (
            result._system_config_path == f"/etc/openjd/adaptors/{adaptor_name}/{adaptor_name}.json"
        )
        assert result._user_config_rel_path == os.path.join(
            ".openjd", "adaptors", adaptor_name, f"{adaptor_name}.json"
        )
        assert isinstance(result._schema_path, list)
        assert len(result._schema_path) == 1
        assert result._schema_path[0] == os.path.abspath(
            os.path.join(_configuration_manager_dir, "_adaptor_configuration.schema.json")
        )


@pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
class TestCreateAdaptorConfigurationManagerWindows:
    def test_creates_config_manager(self):
        """
        This test is fragile as it relies on the hardcoded path formats to adaptor config files.
        """
        # GIVEN
        adaptor_name = "adaptor"
        default_config_path = "/path/to/config"

        # WHEN
        result = _create_adaptor_configuration_manager(
            _AdaptorConfiguration,
            adaptor_name,
            default_config_path,
        )

        # THEN
        assert result._config_cls == _AdaptorConfiguration
        assert result._default_config_path == default_config_path
        assert result._system_config_path == os.path.abspath(
            os.path.join(
                os.path.sep,
                os.environ["PROGRAMDATA"],
                "openjd",
                "adaptors",
                adaptor_name,
                f"{adaptor_name}.json",
            )
        )
        assert result._user_config_rel_path == os.path.join(
            ".openjd", "adaptors", adaptor_name, f"{adaptor_name}.json"
        )
        assert isinstance(result._schema_path, list)
        assert len(result._schema_path) == 1
        assert result._schema_path[0] == os.path.abspath(
            os.path.join(_configuration_manager_dir, "_adaptor_configuration.schema.json")
        )


class TestCreateAdaptorConfigurationManager:
    """
    Tests for the create_adaptor_configuration_manager function.
    """

    def test_accepts_single_schema(self):
        # GIVEN
        adaptor_name = "adaptor"
        default_config_path = "/path/to/config"
        schema_path = "/path/to/schema"

        # WHEN
        result = _create_adaptor_configuration_manager(
            _AdaptorConfiguration,
            adaptor_name,
            default_config_path,
            schema_path,
        )

        # THEN
        assert isinstance(result._schema_path, list)
        assert len(result._schema_path) == 2
        assert result._schema_path[1] == schema_path

    def test_accepts_multiple_schemas(self):
        # GIVEN
        adaptor_name = "adaptor"
        default_config_path = "/path/to/config"
        schema_paths = [
            "/path/to/schema1",
            "/path/to/schema2",
        ]

        # WHEN
        result = _create_adaptor_configuration_manager(
            _AdaptorConfiguration,
            adaptor_name,
            default_config_path,
            schema_paths,
        )

        # THEN
        assert isinstance(result._schema_path, list)
        assert len(result._schema_path) == 1 + len(schema_paths)
        assert result._schema_path[1:] == schema_paths


@pytest.mark.skipif(not OSName.is_posix(), reason="Posix-specific tests")
class TestConfigurationManagerPosix:
    """
    Posix-specific tests for the base ConfigurationManager class
    """

    class TestSystemConfigPosix:
        @patch.object(platform, "system")
        def test_gets_linux_path(self, mock_system: MagicMock):
            # GIVEN
            mock_system.return_value = "Linux"
            expected = "path/to/linux/system/config"
            manager = ConfigurationManagerMock(system_config_path=expected)

            # WHEN
            result = manager.get_system_config_path()

            # THEN
            assert result == expected


@pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
class TestConfigurationManagerWindows:
    """
    Windows-specific tests for the base ConfigurationManager class
    """

    class TestSystemConfigWindows:
        @patch.object(platform, "system")
        def test_gets_windows_path(self, mock_system: MagicMock):
            # GIVEN
            mock_system.return_value = "Windows"
            expected = "path\\to\\windows\\system\\config"
            manager = ConfigurationManagerMock(system_config_path=expected)

            # WHEN
            result = manager.get_system_config_path()

            # THEN
            assert result == expected


class TestConfigurationManager:
    """
    Cross-platform tests for the base ConfigurationManager class
    """

    class TestBuildConfig:
        """
        Tests for the ConfigurationManager.build_config method

        These tests mock the "Configuration.override" method to return an empty
        Configuration and do not assert its correctness. They will only assert that the
        system-level and user-level overrides are applied correctly, not the actual override logic.
        The override logic is covered in the Configuration tests.
        """

        @patch.object(_Configuration, "override")
        @patch.object(ConfigurationManager, "get_user_config")
        @patch.object(ConfigurationManager, "get_user_config_path")
        @patch.object(ConfigurationManager, "get_system_config")
        @patch.object(ConfigurationManager, "get_system_config_path")
        @patch.object(ConfigurationManager, "get_default_config")
        def test_builds_config(
            self,
            mock_get_default_config: MagicMock,
            mock_get_system_config_path: MagicMock,
            mock_get_system_config: MagicMock,
            mock_get_user_config_path: MagicMock,
            mock_get_user_config: MagicMock,
            mock_override: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level(0)
            mock_override.side_effect = [_Configuration({}), _Configuration({})]
            mock_get_default_config.return_value = _Configuration({})
            mock_get_system_config_path.return_value = "fake_system_config_path"
            mock_get_system_config.return_value = _Configuration({})
            mock_get_user_config_path.return_value = "fake_user_config_path"
            mock_get_user_config.return_value = _Configuration({})

            # WHEN
            ConfigurationManagerMock().build_config()

            # THEN
            mock_get_default_config.assert_called_once()
            mock_get_system_config.assert_called_once()
            assert "Applying system-level configuration" in caplog.text
            mock_get_user_config.assert_called_once_with(None)
            assert "Applying user-level configuration" in caplog.text
            mock_override.assert_has_calls(
                [
                    call(mock_get_system_config.return_value),
                    call(mock_get_user_config.return_value),
                ]
            )

        @patch.object(_Configuration, "override")
        @patch.object(ConfigurationManager, "get_user_config")
        @patch.object(ConfigurationManager, "get_user_config_path")
        @patch.object(ConfigurationManager, "get_system_config")
        @patch.object(ConfigurationManager, "get_default_config")
        def test_skips_when_system_config_missing(
            self,
            mock_get_default_config: MagicMock,
            mock_get_system_config: MagicMock,
            mock_get_user_config_path: MagicMock,
            mock_get_user_config: MagicMock,
            mock_override: MagicMock,
        ):
            # GIVEN
            mock_override.side_effect = [_Configuration({}), _Configuration({})]
            mock_get_default_config.return_value = _Configuration({})
            mock_get_system_config.return_value = None
            mock_get_user_config.return_value = _Configuration({})
            mock_get_user_config_path.return_value = "fake_user_config_path"

            # WHEN
            ConfigurationManagerMock().build_config()

            # THEN
            mock_get_default_config.assert_called_once()
            mock_get_system_config.assert_called_once()
            mock_get_user_config.assert_called_once_with(None)
            mock_override.assert_called_once_with(mock_get_user_config.return_value)

        @patch.object(_Configuration, "override")
        @patch.object(ConfigurationManager, "get_user_config")
        @patch.object(ConfigurationManager, "get_system_config")
        @patch.object(ConfigurationManager, "get_system_config_path")
        @patch.object(ConfigurationManager, "get_default_config")
        def test_skips_user_config_when_missing(
            self,
            mock_get_default_config: MagicMock,
            mock_get_system_config_path: MagicMock,
            mock_get_system_config: MagicMock,
            mock_get_user_config: MagicMock,
            mock_override: MagicMock,
        ):
            # GIVEN
            mock_override.side_effect = [_Configuration({}), _Configuration({})]
            mock_get_default_config.return_value = _Configuration({})
            mock_get_system_config.return_value = _Configuration({})
            mock_get_system_config_path.return_value = "fake_system_config_path"
            mock_get_user_config.return_value = None

            # WHEN
            ConfigurationManagerMock().build_config()

            # THEN
            mock_get_default_config.assert_called_once()
            mock_get_system_config.assert_called_once()
            mock_get_user_config.assert_called_once_with(None)
            mock_override.assert_called_once_with(mock_get_system_config.return_value)

        @patch.object(configuration_manager, "_ensure_config_file", return_value=True)
        @patch.object(_Configuration, "from_file")
        @patch.object(_Configuration, "override")
        @patch.object(ConfigurationManager, "get_user_config")
        @patch.object(ConfigurationManager, "get_system_config")
        @patch.object(ConfigurationManager, "get_default_config")
        def test_applies_additional_config_paths(
            self,
            mock_get_default_config: MagicMock,
            mock_get_system_config: MagicMock,
            mock_get_user_config: MagicMock,
            mock_override: MagicMock,
            mock_from_file: MagicMock,
            mock_ensure_config_file: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level(0)
            mock_get_default_config.return_value = _Configuration({})
            mock_get_system_config.return_value = None
            mock_get_user_config.return_value = None

            additional_config_paths = ["/config/a.json", "/config/b.json"]
            additional_configs = [
                _Configuration({"log_level": "WARNING", "a": "a", "unchanged": "unchanged"}),
                _Configuration({"log_level": "DEBUG", "b": "b", "unchanged": "unchanged"}),
            ]

            override_retvals = [*additional_configs]
            mock_override.side_effect = override_retvals
            mock_from_file.side_effect = additional_configs

            manager = ConfigurationManagerMock(additional_config_paths=additional_config_paths)

            # WHEN
            manager.build_config()

            # THEN
            mock_get_default_config.assert_called_once()
            mock_get_system_config.assert_called_once()
            mock_get_user_config.assert_called_once_with(None)

            # Verify calls
            path_calls = [call(path) for path in additional_config_paths]
            mock_ensure_config_file.assert_has_calls(path_calls)
            mock_from_file.assert_has_calls(path_calls)
            mock_override.assert_has_calls([call(retval) for retval in override_retvals])

            # Verify diffs are logged
            expected_diffs = [
                # First diff is applying the entire first config since prior configs are empty
                {"log_level": "WARNING", "a": "a", "unchanged": "unchanged"},
                # Next diff is having log_level updated and a new "b" prop added
                {
                    "log_level": "DEBUG",
                    "b": "b",
                },
            ]
            for expected in expected_diffs:
                for k, v in expected.items():
                    assert f"Set {k} to {v}" in caplog.text

        @patch.object(configuration_manager, "_ensure_config_file")
        @patch.object(_Configuration, "from_file")
        @patch.object(_Configuration, "override")
        @patch.object(ConfigurationManager, "get_user_config")
        @patch.object(ConfigurationManager, "get_system_config")
        @patch.object(ConfigurationManager, "get_default_config")
        def test_skips_additional_config_path(
            self,
            mock_get_default_config: MagicMock,
            mock_get_system_config: MagicMock,
            mock_get_user_config: MagicMock,
            mock_override: MagicMock,
            mock_from_file: MagicMock,
            mock_ensure_config_file: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            caplog.set_level(0)
            empty_config = _Configuration({})
            mock_get_default_config.return_value = empty_config
            mock_get_system_config.return_value = None
            mock_get_user_config.return_value = None

            skipped_config = "/config/skipped.json"
            additional_config_paths = ["/config/used.json", skipped_config]
            mock_ensure_config_file.side_effect = [True, False]

            mock_override.side_effect = [empty_config] * (2 + len(additional_config_paths))
            mock_from_file.side_effect = [empty_config] * len(additional_config_paths)

            manager = ConfigurationManagerMock(additional_config_paths=additional_config_paths)

            # WHEN
            manager.build_config()

            # THEN
            mock_ensure_config_file.assert_has_calls(
                [call(path) for path in additional_config_paths]
            )
            assert (
                f"Failed to load additional configuration: {skipped_config}. Skipping..."
                in caplog.text
            )

    class TestDefaultConfig:
        """
        Tests for ConfigurationManager methods that get the default configuration
        """

        @patch.object(configuration_manager, "_ensure_config_file", return_value=True)
        @patch.object(_Configuration, "from_file")
        def test_gets_default_config(
            self,
            mock_from_file: MagicMock,
            mock_ensure_config_file: MagicMock,
        ):
            # GIVEN
            schema_path = "schema/path"
            config_path = "config/path"
            manager = ConfigurationManagerMock(
                schema_path=schema_path, default_config_path=config_path
            )

            # WHEN
            manager.get_default_config()

            # THEN
            mock_ensure_config_file.assert_called_once_with(config_path, create=True)
            mock_from_file.assert_called_once_with(config_path, schema_path)

        @patch.object(configuration_manager, "_ensure_config_file", return_value=False)
        def test_warns_when_file_is_nonvalid(
            self,
            mock_ensure_config_file: MagicMock,
            caplog: pytest.LogCaptureFixture,
        ):
            # GIVEN
            schema_path = "schema/path"
            config_path = "config/path"
            manager = ConfigurationManagerMock(
                schema_path=schema_path, default_config_path=config_path
            )
            cls_mock = MagicMock()
            manager._config_cls = cls_mock

            # WHEN
            manager.get_default_config()

            # THEN
            mock_ensure_config_file.assert_called_once_with(config_path, create=True)
            assert (
                f"Default configuration file at {config_path} is not a valid file. "
                "Using empty configuration."
            ) in caplog.text
            cls_mock.assert_called_once_with({})

    class TestSystemConfig:
        """
        Tests for methods that get the system-level configuration
        """

        @patch.object(configuration_manager, "_ensure_config_file")
        @patch.object(ConfigurationManagerMock, "get_system_config_path")
        @patch.object(_Configuration, "from_file")
        def test_loads_config_file(
            self,
            mock_from_file: MagicMock,
            mock_get_system_config_path: MagicMock,
            mock_ensure_config_file: MagicMock,
        ):
            # GIVEN
            system_config_path = "system/config/path"
            mock_get_system_config_path.return_value = system_config_path
            mock_ensure_config_file.return_value = True
            schema_path = "schema/path"
            manager = ConfigurationManagerMock(schema_path=schema_path)

            # WHEN
            result = manager.get_system_config()

            # THEN
            mock_get_system_config_path.assert_called_once()
            mock_ensure_config_file.assert_called_once_with(system_config_path)
            mock_from_file.assert_called_once_with(system_config_path, schema_path)
            assert result is not None

        @patch.object(configuration_manager, "_ensure_config_file")
        @patch.object(ConfigurationManagerMock, "get_system_config_path")
        def test_returns_none_when_path_is_not_file(
            self, mock_get_system_config_path: MagicMock, mock_ensure_config_file: MagicMock
        ):
            # GIVEN
            mock_ensure_config_file.return_value = False

            # WHEN
            result = ConfigurationManagerMock().get_system_config()

            # THEN
            mock_get_system_config_path.assert_called_once()
            mock_ensure_config_file.assert_called_once()
            assert result is None

    class TestUserConfig:
        """
        Tests for methods that get the user-level configuration
        """

        @patch.object(configuration_manager.os.path, "expanduser")
        def test_gets_path_current_user(self, mock_expanduser: MagicMock):
            # GIVEN
            def fake_expanduser(path: str):
                return path.replace("~", "/home/currentuser")

            mock_expanduser.side_effect = fake_expanduser
            expected_rel_path = "path/to/user/config"
            manager = ConfigurationManagerMock(user_config_rel_path=expected_rel_path)

            # WHEN
            result = manager.get_user_config_path()

            # THEN
            mock_expanduser.assert_called_once_with(StringStartsWith("~"))
            assert result == os.path.join("/home/currentuser", expected_rel_path)

        @patch.object(configuration_manager.os.path, "expanduser")
        def test_gets_path_specific_user(self, mock_expanduser: MagicMock):
            # GIVEN
            def fake_expanduser(path: str):
                return re.sub(r"~(.*)/(.*)", r"/home/\1/\2", path)

            mock_expanduser.side_effect = fake_expanduser
            username = "username"
            expected_rel_path = "path/to/user/config"
            manager = ConfigurationManagerMock(user_config_rel_path=expected_rel_path)

            # WHEN
            result = manager.get_user_config_path(username)

            # THEN
            mock_expanduser.assert_called_once_with(StringStartsWith(f"~{username}"))
            assert result == os.path.join(f"/home/{username}", expected_rel_path)

        @patch.object(configuration_manager, "_ensure_config_file")
        @patch.object(ConfigurationManagerMock, "get_user_config_path")
        @patch.object(_Configuration, "from_file")
        def test_loads_config_file(
            self,
            mock_from_file: MagicMock,
            mock_get_user_config_path: MagicMock,
            mock_ensure_config_file: MagicMock,
        ):
            # GIVEN
            user_config_path = "user/config/path"
            mock_get_user_config_path.return_value = user_config_path
            mock_ensure_config_file.return_value = True
            schema_path = "schema/path"
            manager = ConfigurationManagerMock(schema_path=schema_path)

            # WHEN
            result = manager.get_user_config()

            # THEN
            mock_get_user_config_path.assert_called_once_with(None)
            mock_ensure_config_file.assert_called_once_with(user_config_path, create=True)
            mock_from_file.assert_called_once_with(user_config_path, schema_path)
            assert result is not None

        @patch.object(configuration_manager, "_ensure_config_file")
        @patch.object(ConfigurationManagerMock, "get_user_config_path")
        def test_returns_none_when_path_is_not_file(
            self, mock_get_user_config_path: MagicMock, mock_ensure_config_file: MagicMock
        ):
            # GIVEN
            mock_ensure_config_file.return_value = False

            # WHEN
            result = ConfigurationManagerMock().get_user_config()

            # THEN
            mock_get_user_config_path.assert_called_once()
            mock_ensure_config_file.assert_called_once()
            assert result is None


class StringStartsWith(str):
    """
    String subclass that overrides the equality method to check if a string starts with this one.

    This is used as a "matcher" object in test assertions.
    """

    def __eq__(self, other: object):
        return isinstance(other, str) and other.startswith(self)
