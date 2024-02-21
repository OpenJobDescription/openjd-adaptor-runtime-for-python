# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import pytest
from unittest.mock import MagicMock
from openjd.adaptor_runtime.adaptors import CommandAdaptor, PathMappingRule
from openjd.adaptor_runtime.process import ManagedProcess
from openjd.adaptor_runtime.adaptors import SemanticVersion


class FakeCommandAdaptor(CommandAdaptor):
    """
    Test implementation of a CommandAdaptor
    """

    def __init__(self, path_mapping_rules: list[dict]):
        super().__init__({}, path_mapping_data={"path_mapping_rules": path_mapping_rules})

    def get_managed_process(self, run_data: dict) -> ManagedProcess:
        return MagicMock()

    @property
    def integration_data_interface_version(self) -> SemanticVersion:
        return SemanticVersion(major=0, minor=1)


class TestGetPathMappingRules:
    def test_no_rules(self) -> None:
        # GIVEN
        path_mapping_rules: list[dict] = []
        adaptor = FakeCommandAdaptor(path_mapping_rules)

        # WHEN
        result = adaptor.path_mapping_rules

        # THEN
        assert result == []

    def test_one_rule(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)

        # WHEN
        result = adaptor.path_mapping_rules

        # THEN
        # Ensure we only got 1 rule back
        assert len(result) == len(path_mapping_rules)
        assert len(result) == 1

        # Basic validation on the 1 rule we got back (ie. we can access source/destination)
        assert isinstance(result[0], PathMappingRule)
        assert result[0].source_path == path_mapping_rules[0]["source_path"]
        assert result[0].destination_path == path_mapping_rules[0]["destination_path"]

    def test_many_rules(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage0",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage0",
            },
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            },
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)

        # WHEN
        result = adaptor.path_mapping_rules

        # THEN
        assert len(result) > 1
        assert len(result) == len(path_mapping_rules)
        assert all(isinstance(rule, PathMappingRule) for rule in result)

    def test_get_order_is_preserved(self) -> None:
        # GIVEN
        rule1 = {
            "source_path_format": "linux",
            "source_path": "/mnt/shared/asset_storage1",
            "destination_os": "windows",
            "destination_path": "Z:\\asset_storage1",
        }
        rule2 = {
            "source_path_format": "windows",
            "source_path": "Z:\\asset_storage1",
            "destination_os": "windows",
            "destination_path": "Z:\\should\\not\\reach\\this",
        }
        path_mapping_rules = [rule1, rule2]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        expected_rules = [
            PathMappingRule.from_dict(rule=rule1),
            PathMappingRule.from_dict(rule=rule2),
        ]
        wrong_order_rules = [expected_rules[1], expected_rules[0]]

        # WHEN
        result = adaptor.path_mapping_rules

        # THEN
        # All lists haves the same length
        assert len(result) == len(expected_rules)
        assert len(result) == len(wrong_order_rules)
        # Compare the lists to ensure they have the correct order
        assert result == expected_rules
        assert result != wrong_order_rules

    def test_rule_list_is_read_only(self) -> None:
        # GIVEN
        expected: list[dict] = []
        adaptor = FakeCommandAdaptor(expected)
        rules = adaptor.path_mapping_rules
        new_rule = PathMappingRule(
            source_path_format="linux",
            source_path="/mnt/shared/asset_storage1",
            destination_os="windows",
            destination_path="Z:\\asset_storage1",
        )

        # WHEN/THEN
        with pytest.raises(AttributeError):
            adaptor.path_mapping_rules = [new_rule]  # type: ignore

        # WHEN/THEN
        rules.append(new_rule)
        assert adaptor.path_mapping_rules == expected
        adaptor.path_mapping_rules.append(new_rule)
        assert adaptor.path_mapping_rules == expected


class TestApplyPathMapping:
    def test_no_change(self) -> None:
        # GIVEN
        path_mapping_rules: list[dict] = []
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = expected = "/mnt/shared/asset_storage1"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_linux_to_windows(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "/mnt/shared/asset_storage1/asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_windows_to_linux(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "windows",
                "source_path": "Z:\\asset_storage1",
                "destination_os": "linux",
                "destination_path": "/mnt/shared/asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "Z:\\asset_storage1\\asset.ext"
        expected = "/mnt/shared/asset_storage1/asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_linux_to_linux(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/my_custom_path/asset_storage1",
                "destination_os": "linux",
                "destination_path": "/mnt/shared/asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)

        source_path = "/mnt/shared/my_custom_path/asset_storage1/asset.ext"
        expected = "/mnt/shared/asset_storage1/asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_windows_to_windows(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "Z:\\my_custom_asset_path\\asset_storage1\\asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_windows_capitalization_agnostic(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = f"{path_mapping_rules[0]['source_path'].upper()}\\asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_windows_directory_separator_agnostic(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "Z:/my_custom_asset_path/asset_storage1/asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_multiple_rules(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage0",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage0",
            },
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            },
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "/mnt/shared/asset_storage1/asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_only_first_applied(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            },
            {
                "source_path_format": "windows",
                "source_path": "Z:\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\should\\not\\reach\\this",
            },
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "/mnt/shared/asset_storage1/asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected

    def test_apply_order_is_preserved(self) -> None:
        # GIVEN
        path_mapping_rules = [
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            },
            {
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\should\\not\\reach\\this",
            },
        ]
        adaptor = FakeCommandAdaptor(path_mapping_rules)
        source_path = "/mnt/shared/asset_storage1/asset.ext"
        expected = "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = adaptor.map_path(source_path)

        # THEN
        assert result == expected
