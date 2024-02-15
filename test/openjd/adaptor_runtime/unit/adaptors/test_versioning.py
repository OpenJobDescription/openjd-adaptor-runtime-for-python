# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

import pytest
from openjd.adaptor_runtime.adaptors import SemanticVersion


class TestSemanticVersion:
    @pytest.mark.parametrize(
        ("version_a", "version_b", "expected_result"),
        [
            (SemanticVersion(0, 1), SemanticVersion(0, 2), False),
            (SemanticVersion(0, 1), SemanticVersion(0, 1), True),
            (SemanticVersion(0, 1), SemanticVersion(0, 0), False),
            (SemanticVersion(1, 5), SemanticVersion(1, 4), True),
            (SemanticVersion(1, 5), SemanticVersion(1, 5), True),
            (SemanticVersion(1, 5), SemanticVersion(1, 6), False),
            (SemanticVersion(1, 5), SemanticVersion(2, 0), False),
            (SemanticVersion(1, 5), SemanticVersion(2, 5), False),
            (SemanticVersion(1, 5), SemanticVersion(2, 6), False),
        ],
    )
    def test_has_compatibility_with(
        self, version_a: SemanticVersion, version_b: SemanticVersion, expected_result: bool
    ):
        # WHEN
        result = version_a.has_compatibility_with(version_b)

        # THEN
        assert result == expected_result

    @pytest.mark.parametrize(
        ("version_str", "expected_result"),
        [
            ("1.0.0", ValueError),
            ("1.zero", ValueError),
            ("three.five", ValueError),
            ("1. 5", ValueError),
            (" 1.5", ValueError),
            ("a version", ValueError),
            ("-1.5", ValueError),
            ("1.-5", ValueError),
            ("-1.-5", ValueError),
            ("1.5", SemanticVersion(1, 5)),
            ("10.50", SemanticVersion(10, 50)),
        ],
    )
    def test_parse(self, version_str: str, expected_result: SemanticVersion | ValueError):
        if expected_result is ValueError:
            # WHEN/THEN
            with pytest.raises(ValueError):
                SemanticVersion.parse(version_str)
        else:
            # WHEN
            result = SemanticVersion.parse(version_str)

            # THEN
            assert result == expected_result
