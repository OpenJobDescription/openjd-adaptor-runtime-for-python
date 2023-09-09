# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from openjd.adaptor_runtime.adaptors import PathMappingRule


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param({"source_path_format": "", "source_path": "", "destination_path": ""}),
        pytest.param({"source_path_format": None, "source_path": None, "destination_path": None}),
        pytest.param({"source_path_format": "", "source_path": None, "destination_path": ""}),
        pytest.param({"source_path_format": "", "source_path": "C:/", "destination_path": "/mnt/"}),
        pytest.param(
            {"source_path_format": "windows", "source_path": "", "destination_path": "/mnt/"}
        ),
        pytest.param(
            {"source_path_format": "windows", "source_path": "C:/", "destination_path": ""}
        ),
        pytest.param(
            {"source_path_format": "nonvalid", "source_path": "C:/", "destination_path": "/mnt/"}
        ),
        pytest.param(
            {
                "source_path_format": "windows",
                "destination_os": "nonvalid",
                "source_path": "C:/",
                "destination_path": "/mnt/",
            }
        ),
    ],
)
def test_bad_args(rule):
    # WHEN/THEN
    with pytest.raises(ValueError):
        PathMappingRule(**rule)

    with pytest.raises(ValueError):
        PathMappingRule.from_dict(rule=rule)


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param({}),
        pytest.param(None),
    ],
)
def test_no_args(rule):
    # WHEN/THEN
    with pytest.raises(TypeError):
        PathMappingRule(**rule)

    with pytest.raises(ValueError):
        PathMappingRule.from_dict(rule=rule)


def test_good_args():
    # GIVEN
    rule = {
        "source_path_format": "windows",
        "destination_os": "windows",
        "source_path": "Y:/movie1",
        "destination_path": "Z:/movie2",
    }

    # THEN
    PathMappingRule(**rule)
    PathMappingRule.from_dict(rule=rule)


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/usr"),
        pytest.param("/usr/assets"),
        pytest.param("/usr/scene/maya.mb"),
        pytest.param("/usr/scene/../../../.."),
        pytest.param("/usr/scene/../../../../who/knows/where/we/are"),
        pytest.param("/usr/scene/symbolic_path/../who/knows/where/we/are"),
    ],
)
def test_path_mapping_linux_is_match(path):
    # GIVEN
    rule = PathMappingRule(
        source_path_format="linux", source_path="/usr", destination_path="/mnt/shared"
    )
    pure_path = PurePosixPath(path)

    # WHEN
    result = rule._is_match(pure_path=pure_path)

    # THEN
    assert result


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(""),
        pytest.param("/"),
        pytest.param("/Usr/Movie1"),
        pytest.param("/usr/movie1"),
        pytest.param("/usr\\Movie1"),
        pytest.param("\\usr\\Movie1"),
        pytest.param("/usr/Movie1a"),
    ],
)
def test_path_mapping_linux_is_not_match(path):
    # GIVEN
    rule = PathMappingRule(
        source_path_format="linux", source_path="/usr/Movie1", destination_path="/mnt/shared/Movie1"
    )
    pure_path = PurePosixPath(path)

    # WHEN
    result = rule._is_match(pure_path=pure_path)

    # THEN
    assert not result


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("Z:\\Movie1"),
        pytest.param("z:\\movie1"),
        pytest.param("z:/movie1"),
        pytest.param("z:/movie1/assets"),
        pytest.param("z:/movie1/assets/texture.png"),
        pytest.param("Z://////Movie1"),
        pytest.param("Z:\\\\\\Movie1"),
    ],
)
def test_path_mapping_windows_is_match(path):
    # GIVEN
    rule = PathMappingRule(
        source_path_format="windows", source_path="Z:\\Movie1", destination_path="/mnt/shared"
    )
    pure_path = PureWindowsPath(path)

    # WHEN
    result = rule._is_match(pure_path=pure_path)

    # THEN
    assert result


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("C:\\Movie1"),
        pytest.param("Z:\\"),
        pytest.param("Z:\\Movie1a"),
    ],
)
def test_path_mapping_windows_is_not_match(path):
    # GIVEN
    rule = PathMappingRule(
        source_path_format="windows", source_path="Z:\\Movie1", destination_path="/mnt/shared"
    )
    pure_path = PureWindowsPath(path)

    # WHEN
    result = rule._is_match(pure_path=pure_path)

    # THEN
    assert not result


class TestApplyPathMapping:
    def test_no_change(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage2",
                "destination_os": "linux",
                "destination_path": "/mnt/shared/movie2",
            }
        )
        path = "/usr/assets/no_mapping.png"
        expected = False, path

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_linux_to_windows(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "linux",
                "source_path": "/mnt/shared/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        )
        path = "/mnt/shared/asset_storage1/asset.ext"
        expected = True, "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_windows_to_linux(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "windows",
                "source_path": "Z:\\asset_storage1",
                "destination_os": "linux",
                "destination_path": "/mnt/shared/asset_storage1",
            }
        )
        path = "Z:\\asset_storage1\\asset.ext"
        expected = True, "/mnt/shared/asset_storage1/asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_linux_to_linux(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "linux",
                "source_path": "/mnt/shared/my_custom_path/asset_storage1",
                "destination_os": "linux",
                "destination_path": "/mnt/shared/asset_storage1",
            }
        )

        path = "/mnt/shared/my_custom_path/asset_storage1/asset.ext"
        expected = True, "/mnt/shared/asset_storage1/asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_windows_to_windows(self):
        # GIVEN
        rule = rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        )
        path = "Z:\\my_custom_asset_path\\asset_storage1\\asset.ext"
        expected = True, "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_windows_capitalization_agnostic(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        )
        path = f"{rule.source_path.upper()}\\asset.ext"
        expected = True, "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_windows_directory_separator_agnostic(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "windows",
                "source_path": "Z:\\my_custom_asset_path\\asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        )
        path = "Z:/my_custom_asset_path/asset_storage1/asset.ext"
        expected = True, "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_windows_directory_separator_agnostic_inverted(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "windows",
                "source_path": "Z:/my_custom_asset_path/asset_storage1",
                "destination_os": "windows",
                "destination_path": "Z:\\asset_storage1",
            }
        )
        path = "Z:\\my_custom_asset_path\\asset_storage1\\asset.ext"
        expected = True, "Z:\\asset_storage1\\asset.ext"

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_starts_with_partial_match(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "linux",
                "source_path": "a/b",
                "destination_os": "linux",
                "destination_path": "/c",
            }
        )
        path = "/a/bc/asset.ext"
        expected = False, path

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_partial_match(self):
        # GIVEN
        rule = PathMappingRule.from_dict(
            rule={
                "source_path_format": "linux",
                "source_path": "/bar/baz",
                "destination_os": "linux",
                "destination_path": "/bla",
            }
        )
        path = "/foo/bar/baz"
        expected = False, path

        # WHEN
        result = rule.apply(path=path)

        # THEN
        assert result == expected

    def test_to_dict(self):
        # GIVEN
        rule_dict = {
            "source_path_format": "linux",
            "source_path": "/bar/baz",
            "destination_os": "linux",
            "destination_path": "/bla",
        }
        rule = PathMappingRule.from_dict(rule=rule_dict)

        # WHEN
        result = rule.to_dict()

        # THEN
        assert result == rule_dict
