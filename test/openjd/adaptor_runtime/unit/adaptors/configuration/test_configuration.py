# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

from json.decoder import JSONDecodeError
from typing import Any
from typing import List as _List
from unittest.mock import MagicMock, call, patch, ANY

import jsonschema
import pytest

import openjd.adaptor_runtime.adaptors.configuration._configuration as configuration
from openjd.adaptor_runtime.adaptors.configuration import (
    Configuration,
)
from openjd.adaptor_runtime.adaptors.configuration._configuration import (
    _make_function_register_decorator,
)


def test_make_register_decorator():
    # GIVEN
    decorator = _make_function_register_decorator()

    # WHEN
    @decorator
    def my_func():
        pass

    # THEN
    key, value = my_func.__name__, my_func
    assert key in decorator.registry and value == decorator.registry[key]


class TestFromFile:
    """
    Tests for the Configuration.from_file method
    """

    @patch.object(configuration.jsonschema, "validate")
    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_loads_schema(
        self, mock_open: MagicMock, mock_load: MagicMock, mock_validate: MagicMock
    ):
        # GIVEN
        schema_path = "/path/to/schema"
        config_path = "/path/to/config"
        schema = {"json": "schema"}
        config = {"my": "config"}
        mock_load.side_effect = [config, schema]

        # WHEN
        result = Configuration.from_file(config_path, schema_path)

        # THEN
        mock_open.assert_has_calls(
            [
                call(config_path, encoding="utf-8"),
                # The __enter__ and __exit__ are context manager
                # calls for opening files safely.
                call().__enter__(),
                call().__exit__(None, None, None),
                call(schema_path, encoding="utf-8"),
                call().__enter__(),
                call().__exit__(None, None, None),
            ]
        )
        assert mock_load.call_count == 2
        mock_validate.assert_called_once_with(config, schema)
        assert result._config is config

    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_skips_validation_when_no_schema(
        self,
        mock_open: MagicMock,
        mock_load: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        config_path = "/path/to/config"
        config = {"my": "config"}
        mock_load.return_value = config

        # WHEN
        result = Configuration.from_file(config_path)

        # THEN
        mock_open.assert_called_once_with(config_path, encoding="utf-8")
        mock_load.assert_called_once()
        assert (
            f"JSON Schema file path not provided. Configuration file {config_path} will not be "
            "validated."
        ) in caplog.text
        assert result._config is config

    @patch.object(configuration.jsonschema, "validate")
    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_validates_against_multiple_schemas(
        self,
        mock_open: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
    ):
        # GIVEN
        schema_path = "/path/to/schema"
        schema = {"json": "schema"}
        schema2_path = "path/2/schema"
        schema2 = {"json2": "schema2"}
        config_path = "/path/to/config"
        config = {"my": "config"}
        mock_load.side_effect = [config, schema, schema2]

        # WHEN
        result = Configuration.from_file(config_path, [schema_path, schema2_path])

        # THEN
        mock_open.assert_has_calls(
            [
                call(config_path, encoding="utf-8"),
                # The __enter__ and __exit__ are context manager
                # calls for opening files safely.
                call().__enter__(),
                call().__exit__(None, None, None),
                call(schema_path, encoding="utf-8"),
                call().__enter__(),
                call().__exit__(None, None, None),
                call(schema2_path, encoding="utf-8"),
                call().__enter__(),
                call().__exit__(None, None, None),
            ]
        )
        assert mock_load.call_count == 3
        mock_validate.assert_has_calls([call(config, schema), call(config, schema2)])
        assert result._config is config

    @pytest.mark.parametrize("schema_path", [[], ""])
    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_raises_when_nonvalid_schema_path_value(
        self, mock_open: MagicMock, mock_load: MagicMock, schema_path: _List | str
    ):
        # GIVEN
        config_path = "/path/to/config"
        mock_open.return_value = MagicMock()

        # WHEN
        with pytest.raises(ValueError) as raised_err:
            Configuration.from_file(config_path, schema_path)

        # THEN
        mock_load.assert_called_once()
        mock_open.assert_called_once_with(config_path, encoding="utf-8")
        assert raised_err.match(f"Schema path cannot be an empty {type(schema_path)}")

    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_raises_when_schema_open_fails(
        self, mock_open: MagicMock, mock_load: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        config_path = "/path/to/config"
        schema_path = "/path/to/schema"
        err = OSError()
        mock_open.side_effect = [MagicMock(), err]

        # WHEN
        with pytest.raises(OSError) as raised_err:
            Configuration.from_file(config_path, schema_path)

        # THEN
        mock_load.assert_called_once()
        mock_open.assert_has_calls(
            [call(config_path, encoding="utf-8"), call(schema_path, encoding="utf-8")]
        )
        assert raised_err.value is err
        assert f"Failed to open configuration schema at {schema_path}: " in caplog.text

    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_raises_when_schema_json_decode_fails(
        self, mock_open: MagicMock, mock_load: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        config_path = "/path/to/config"
        schema_path = "/path/to/schema"
        err = JSONDecodeError("", "", 0)
        mock_load.side_effect = [{}, err]

        # WHEN
        with pytest.raises(JSONDecodeError) as raised_err:
            Configuration.from_file(config_path, schema_path)

        # THEN
        assert mock_load.call_count == 2
        mock_open.assert_has_calls(
            [
                call(config_path, encoding="utf-8"),
                # The __enter__ and __exit__ are context manager
                # calls for opening files safely.
                call().__enter__(),
                call().__exit__(None, None, None),
                call(schema_path, encoding="utf-8"),
                call().__enter__(),
                call().__exit__(JSONDecodeError, ANY, ANY),
            ]
        )
        assert raised_err.value is err
        assert f"Failed to decode configuration schema at {schema_path}: " in caplog.text

    @patch.object(configuration, "open")
    def test_raises_when_config_open_fails(
        self, mock_open: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        config_path = "/path/to/config"
        err = OSError()
        mock_open.side_effect = err

        # WHEN
        with pytest.raises(OSError) as raised_err:
            Configuration.from_file(config_path, "")

        # THEN
        mock_open.assert_called_once_with(config_path, encoding="utf-8")
        assert raised_err.value is err
        assert f"Failed to open configuration at {config_path}: " in caplog.text

    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_raises_when_config_json_decode_fails(
        self, mock_open: MagicMock, mock_load: MagicMock, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        config_path = "/path/to/config"
        err = JSONDecodeError("", "", 0)
        mock_load.side_effect = err

        # WHEN
        with pytest.raises(JSONDecodeError) as raised_err:
            Configuration.from_file(config_path, "")

        # THEN
        mock_open.assert_called_once_with(config_path, encoding="utf-8")
        mock_load.assert_called_once()
        assert raised_err.value is err
        assert f"Failed to decode configuration at {config_path}: " in caplog.text

    @patch.object(configuration.jsonschema, "validate")
    @patch.object(configuration.json, "load")
    @patch.object(configuration, "open")
    def test_raises_when_config_fails_jsonschema_validation(
        self,
        mock_open: MagicMock,
        mock_load: MagicMock,
        mock_validate: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        # GIVEN
        schema_path = "/path/to/schema"
        config_path = "/path/to/config"
        schema = {"json": "schema"}
        config = {"my": "config"}
        mock_load.side_effect = [config, schema]
        mock_validate.side_effect = jsonschema.ValidationError("")

        # WHEN
        with pytest.raises(jsonschema.ValidationError) as raised_err:
            Configuration.from_file(config_path, schema_path)

        # THEN
        mock_open.assert_has_calls(
            [
                call(config_path, encoding="utf-8"),
                # The __enter__ and __exit__ are context manager
                # calls for opening files safely.
                call().__enter__(),
                call().__exit__(None, None, None),
                call(schema_path, encoding="utf-8"),
                call().__enter__(),
                call().__exit__(None, None, None),
            ]
        )
        assert mock_load.call_count == 2
        mock_validate.assert_called_once_with(config, schema)
        assert raised_err.value is mock_validate.side_effect
        assert (
            f"Configuration file at {config_path} failed to validate "
            f"against the JSON schema at {schema_path}: " in caplog.text
        )


class TestConfiguration:
    """
    Tests for the base Configuration instance methods
    """

    def test_override(self):
        # GIVEN
        config1 = Configuration({"a": 1, "b": 2})
        config2 = Configuration({"b": 3, "c": 4})

        # WHEN
        result = config1.override(config2)

        # THEN
        assert {"a": 1, "b": 3, "c": 4} == result._config

    def test_config_populates_defaults(self):
        # GIVEN
        class TestConfiguration(Configuration):
            _defaults = _make_function_register_decorator()

            @classmethod
            def _get_defaults_decorator(cls) -> Any:
                return cls._defaults

            @property  # type: ignore
            @_defaults
            def default_property(self) -> str:
                return "default"

        initial_config = {"existing_property": "existing"}
        expected = {"existing_property": "existing", "default_property": "default"}

        # WHEN
        config = TestConfiguration(initial_config)

        # THEN
        assert expected == config.config
