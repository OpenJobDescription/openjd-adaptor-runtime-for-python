# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import os
import pathlib as _pathlib
import tempfile

import pytest

from openjd.adaptor_runtime.adaptors.configuration import Configuration


class TestFromFile:
    """
    Integration tests for the Configuration.from_file method
    """

    def test_loads_config(self):
        # GIVEN
        json_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"key": {"enum": ["value"]}},
        }
        config = {"key": "value"}

        # On Windows, delete=False is needed, because the OS doesn't allow a named temporary file to be opened a second
        # time while the first file handle is still open.
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+", delete=False
            ) as schema_file, tempfile.NamedTemporaryFile(mode="w+", delete=False) as config_file:
                json.dump(json_schema, schema_file.file)
                json.dump(config, config_file.file)
                schema_file.seek(0)
                config_file.seek(0)

            # WHEN
            result = Configuration.from_file(
                config_path=config_file.name,
                schema_path=schema_file.name,
            )

            # THEN
            assert result._config == config
        finally:
            if os.path.exists(schema_file.name):
                os.remove(schema_file.name)
            if os.path.exists(config_file.name):
                os.remove(config_file.name)

    def test_raises_when_config_file_fails_to_open(
        self, tmp_path: _pathlib.Path, caplog: pytest.LogCaptureFixture
    ):
        # GIVEN
        with tempfile.NamedTemporaryFile(mode="w+") as schema_file:
            json.dump({}, schema_file.file)
            schema_file.seek(0)
            non_existent_filepath = os.path.join(tmp_path.absolute(), "non_existent_file")

            # WHEN
            with pytest.raises(OSError) as raised_err:
                Configuration.from_file(
                    schema_path=schema_file.name,
                    config_path=non_existent_filepath,
                )

        # THEN
        assert isinstance(raised_err.value, OSError)
        assert f"Failed to open configuration at {non_existent_filepath}: " in caplog.text
