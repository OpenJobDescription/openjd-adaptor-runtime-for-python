# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import jsonschema
import logging
import os
import yaml
from typing import Any


_logger = logging.getLogger(__name__)


class AdaptorDataValidators:
    """
    Class that contains validators for Adaptor input data.
    """

    @classmethod
    def for_adaptor(cls, schema_dir: str) -> AdaptorDataValidators:
        """
        Gets the validators for the specified adaptor.

        Args:
            adaptor_name (str): The name of the adaptor
        """
        init_data_schema_path = os.path.join(schema_dir, "init_data.schema.json")
        _logger.info("Loading 'init_data' schema from %s", init_data_schema_path)
        run_data_schema_path = os.path.join(schema_dir, "run_data.schema.json")
        _logger.info("Loading 'run_data' schema from %s", run_data_schema_path)

        init_data_validator = AdaptorDataValidator.from_schema_file(init_data_schema_path)

        run_data_validator = AdaptorDataValidator.from_schema_file(run_data_schema_path)

        return AdaptorDataValidators(init_data_validator, run_data_validator)

    def __init__(
        self,
        init_data_validator: AdaptorDataValidator,
        run_data_validator: AdaptorDataValidator,
    ) -> None:
        self._init_data_validator = init_data_validator
        self._run_data_validator = run_data_validator

    @property
    def init_data(self) -> AdaptorDataValidator:
        """
        Gets the validator for init_data.
        """
        return self._init_data_validator

    @property
    def run_data(self) -> AdaptorDataValidator:
        """
        Gets the validator for run_data.
        """
        return self._run_data_validator


class AdaptorDataValidator:
    """
    Class that validates the input data for an Adaptor.
    """

    @staticmethod
    def from_schema_file(schema_path: str) -> AdaptorDataValidator:
        """
        Creates an AdaptorDataValidator with the JSON schema at the specified file path.

        Args:
            schema_path (str): The path to the JSON schema file to use.
        """
        try:
            with open(schema_path, encoding="utf-8") as schema_file:
                schema = json.load(schema_file)
        except json.JSONDecodeError as e:
            _logger.error(f"Failed to decode JSON schema file: {e}")
            raise
        except OSError as e:
            _logger.error(f"Failed to open JSON schema file at {schema_path}: {e}")
            raise

        if not isinstance(schema, dict):
            raise ValueError(f"Expected JSON schema to be a dict, but got {type(schema)}")

        return AdaptorDataValidator(schema)

    def __init__(self, schema: dict) -> None:
        self._schema = schema

    def validate(self, data: str | dict) -> None:
        """
        Validates that the data adheres to the schema.

        The data argument can be one of the following:
        - A string containing the data file path. Must be prefixed with "file://".
        - A string-encoded version of the data.
        - A dictionary containing the data.

        Args:
            data (dict): The data to validate.

        Raises:
            jsonschema.ValidationError: Raised when the data failed validate against the schema.
            jsonschema.SchemaError: Raised when the schema itself is nonvalid.
        """
        if isinstance(data, str):
            data = _load_data(data)

        jsonschema.validate(data, self._schema)


def _load_data(data: str) -> dict:
    """
    Parses an input JSON/YAML (filepath or string-encoded) into a dictionary.

    Args:
        data (str): The filepath or string representation of the JSON/YAML to parse.
        If this is a filepath, it must begin with "file://"

    Raises:
        ValueError: Raised when the JSON/YAML is not parsed to a dictionary.
    """
    try:
        loaded_data = _load_yaml_json(data)
    except OSError as e:
        _logger.error(f"Failed to open data file: {e}")
        raise
    except yaml.YAMLError as e:
        _logger.error(f"Failed to load data as JSON or YAML: {e}")
        raise

    if not isinstance(loaded_data, dict):
        raise ValueError(f"Expected loaded data to be a dict, but got {type(loaded_data)}")

    return loaded_data


def _load_yaml_json(data: str) -> Any:
    """
    Loads a YAML/JSON file/string.

    Note that yaml.safe_load() is capable of loading JSON documents.
    """
    loaded_yaml = None
    if data.startswith("file://"):
        filepath = data[len("file://") :]
        with open(filepath, encoding="utf-8") as yaml_file:
            loaded_yaml = yaml.safe_load(yaml_file)
    else:
        loaded_yaml = yaml.safe_load(data)

    return loaded_yaml
