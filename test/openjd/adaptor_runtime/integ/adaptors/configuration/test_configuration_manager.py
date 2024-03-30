# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import os
import tempfile
from typing import IO

import pytest

from openjd.adaptor_runtime.adaptors.configuration import Configuration, ConfigurationManager


class TestConfigurationManager:
    """
    Integration tests for ConfigurationManager
    """

    @pytest.fixture
    def json_schema_file(self):
        json_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "key": {"enum": ["value"]},
                "syskey": {"type": "string"},
                "usrkey": {"type": "string"},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as schema_file:
            json.dump(json_schema, schema_file.file)
            schema_file.seek(0)
            yield schema_file
        os.remove(schema_file.name)

    def test_gets_system_config(self, json_schema_file: IO[str]):
        # GIVEN
        config = {"key": "value"}

        try:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as config_file:
                json.dump(config, config_file.file)
                config_file.seek(0)
                manager = ConfigurationManager(
                    config_cls=Configuration,
                    schema_path=json_schema_file.name,
                    system_config_path=config_file.name,
                    # These fields can be empty since they will not be used in this test
                    default_config_path="",
                    user_config_rel_path="",
                )

                # WHEN
                sys_config = manager.get_system_config()

            # THEN
            assert sys_config is not None and sys_config._config == config

        finally:
            if os.path.exists(config_file.name):
                os.remove(config_file.name)

    def test_builds_config(self, json_schema_file: IO[str]):
        # GIVEN
        default_config = {
            "key": "value",
            "syskey": "value",
            "usrkey": "value",
        }
        system_config = {"syskey": "system"}
        user_config = {"usrkey": "user"}

        homedir = os.path.expanduser("~")

        try:
            with (
                tempfile.NamedTemporaryFile(mode="w+", delete=False) as default_config_file,
                tempfile.NamedTemporaryFile(mode="w+", delete=False) as system_config_file,
                tempfile.NamedTemporaryFile(
                    mode="w+", dir=homedir, delete=False
                ) as user_config_file,
            ):
                json.dump(default_config, default_config_file)
                json.dump(system_config, system_config_file)
                json.dump(user_config, user_config_file)
                default_config_file.seek(0)
                system_config_file.seek(0)
                user_config_file.seek(0)

                manager = ConfigurationManager(
                    config_cls=Configuration,
                    schema_path=json_schema_file.name,
                    default_config_path=default_config_file.name,
                    system_config_path=system_config_file.name,
                    user_config_rel_path=os.path.relpath(
                        user_config_file.name,
                        start=os.path.expanduser("~"),
                    ),
                )

                # WHEN
                result = manager.build_config()

                # THEN
                assert result._config == {**default_config, **system_config, **user_config}

        finally:
            if os.path.exists(default_config_file.name):
                os.remove(default_config_file.name)
            if os.path.exists(system_config_file.name):
                os.remove(system_config_file.name)
            if os.path.exists(user_config_file.name):
                os.remove(user_config_file.name)
