# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import dataclasses

import pytest

from openjd.adaptor_runtime._background.model import DataclassMapper


# Define two dataclasses to use for tests
@dataclasses.dataclass
class Inner:
    key: str


@dataclasses.dataclass
class Outer:
    outer_key: str
    inner: Inner


class TestDataclassMapper:
    """
    Tests for the DataclassMapper class
    """

    def test_maps_nested_dataclass(self):
        # GIVEN
        input = {"outer_key": "outer_value", "inner": {"key": "value"}}
        mapper = DataclassMapper(Outer)

        # WHEN
        result = mapper.map(input)

        # THEN
        assert isinstance(result, Outer)
        assert isinstance(result.inner, Inner)
        assert result.outer_key == "outer_value"
        assert result.inner.key == "value"

    def test_raises_when_field_is_missing(self):
        # GIVEN
        input = {"outer_key": "outer_value"}
        mapper = DataclassMapper(Outer)

        # WHEN
        with pytest.raises(ValueError) as raised_err:
            mapper.map(input)

        # THEN
        assert raised_err.match("Dataclass field inner not found in dict " + str(input))
