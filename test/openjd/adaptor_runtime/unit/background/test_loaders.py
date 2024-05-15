# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import dataclasses
import pathlib
import json
import re
import typing
from unittest.mock import MagicMock, mock_open, patch

import pytest

from openjd.adaptor_runtime._background import loaders
from openjd.adaptor_runtime._background.loaders import (
    ConnectionSettingsEnvLoader,
    ConnectionSettingsFileLoader,
    ConnectionSettingsLoadingError,
)
from openjd.adaptor_runtime._background.model import (
    ConnectionSettings,
)


class TestConnectionSettingsFileLoader:
    """
    Tests for the ConnectionsettingsFileLoader class
    """

    @pytest.fixture
    def connection_settings(self) -> ConnectionSettings:
        return ConnectionSettings(socket="socket")

    @pytest.fixture(autouse=True)
    def open_mock(
        self, connection_settings: ConnectionSettings
    ) -> typing.Generator[MagicMock, None, None]:
        with patch.object(
            loaders,
            "open",
            mock_open(read_data=json.dumps(dataclasses.asdict(connection_settings))),
        ) as m:
            yield m

    @pytest.fixture
    def connection_file_path(self) -> pathlib.Path:
        return pathlib.Path("test")

    @pytest.fixture
    def loader(self, connection_file_path: pathlib.Path) -> ConnectionSettingsFileLoader:
        return ConnectionSettingsFileLoader(connection_file_path)

    def test_loads_settings(
        self,
        connection_settings: ConnectionSettings,
        loader: ConnectionSettingsFileLoader,
    ):
        # WHEN
        result = loader.load()

        # THEN
        assert result == connection_settings

    def test_raises_when_file_open_fails(
        self,
        open_mock: MagicMock,
        loader: ConnectionSettingsFileLoader,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        err = OSError()
        open_mock.side_effect = err

        # WHEN
        with pytest.raises(ConnectionSettingsLoadingError):
            loader.load()

        # THEN
        assert "Failed to open connection file: " in caplog.text

    def test_raises_when_json_decode_fails(
        self,
        loader: ConnectionSettingsFileLoader,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        err = json.JSONDecodeError("", "", 0)

        with patch.object(loaders.json, "load", side_effect=err):
            with pytest.raises(ConnectionSettingsLoadingError):
                # WHEN
                loader.load()

        # THEN
        assert "Failed to decode connection file: " in caplog.text


class TestConnectionSettingsEnvLoader:
    @pytest.fixture
    def connection_settings(self) -> ConnectionSettings:
        return ConnectionSettings(socket="socket")

    @pytest.fixture
    def mock_env(self, connection_settings: ConnectionSettings) -> dict[str, typing.Any]:
        return {
            env_name: getattr(connection_settings, attr_name)
            for attr_name, (env_name, _) in ConnectionSettingsEnvLoader().env_map.items()
        }

    @pytest.fixture(autouse=True)
    def mock_os_environ(
        self, mock_env: dict[str, typing.Any]
    ) -> typing.Generator[dict, None, None]:
        with patch.dict(loaders.os.environ, mock_env) as d:
            yield d

    @pytest.fixture
    def loader(self) -> ConnectionSettingsEnvLoader:
        return ConnectionSettingsEnvLoader()

    def test_loads_connection_settings(
        self,
        loader: ConnectionSettingsEnvLoader,
        connection_settings: ConnectionSettings,
    ) -> None:
        # WHEN
        settings = loader.load()

        # THEN
        assert connection_settings == settings

    def test_raises_error_when_required_not_provided(
        self,
        loader: ConnectionSettingsEnvLoader,
    ) -> None:
        # GIVEN
        with patch.object(loaders.os.environ, "get", return_value=None):
            with pytest.raises(loaders.ConnectionSettingsLoadingError) as raised_err:
                # WHEN
                loader.load()

        # THEN
        assert re.match(
            "Required attribute '.*' does not have its corresponding environment variable '.*' set",
            str(raised_err.value),
        )
