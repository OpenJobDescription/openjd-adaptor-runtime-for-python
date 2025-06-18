# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import dataclasses

from enum import Enum

import pytest

from openjd.adaptor_runtime._background.model import DataclassMapper


class StrEnum(str, Enum):
    TEST = "test_str"
    TEST_UNI = "test_☃"


class NormalEnum(Enum):
    ONE = 1


# Define two dataclasses to use for tests
@dataclasses.dataclass
class Inner:
    key: str


@dataclasses.dataclass
class Outer:
    outer_key: str
    inner: Inner
    test_str: StrEnum
    test_str_unicode: StrEnum
    normal_enum: NormalEnum


class TestDataclassMapper:
    """
    Tests for the DataclassMapper class
    """

    def test_maps_nested_dataclass(self):
        # GIVEN
        input = {
            "outer_key": "outer_value",
            "inner": {
                "key": "value",
            },
            "test_str": "test_str",
            "test_str_unicode": "test_☃",
            "normal_enum": 1,
        }
        mapper = DataclassMapper(Outer)

        # WHEN
        result = mapper.map(input)

        # THEN
        expected_dataclass = Outer(
            outer_key="outer_value",
            inner=Inner(key="value"),
            test_str=StrEnum.TEST,
            test_str_unicode=StrEnum.TEST_UNI,
            normal_enum=NormalEnum.ONE,
        )
        assert result == expected_dataclass

    def test_raises_when_field_is_missing(self):
        # GIVEN
        input = {"outer_key": "outer_value"}
        mapper = DataclassMapper(Outer)

        # WHEN
        with pytest.raises(ValueError) as raised_err:
            mapper.map(input)

        # THEN
        assert raised_err.match("Dataclass field inner not found in dict " + str(input))
