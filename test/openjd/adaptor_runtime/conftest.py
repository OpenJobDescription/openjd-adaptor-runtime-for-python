# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import platform

import pytest

# List of platforms that can be used to mark tests as specific to that platform
# See [tool.pytest.ini_options] -> markers in pyproject.toml
_PLATFORMS = set(
    [
        "Linux",
        "Windows",
        "Darwin",
    ]
)


def pytest_runtest_setup(item: pytest.Item):
    """
    Hook that is run for each test.
    """

    # Skip platform-specific tests that don't apply to current platform
    supported_platforms = set(_PLATFORMS).intersection(mark.name for mark in item.iter_markers())
    plat = platform.system()
    if supported_platforms and plat not in supported_platforms:
        pytest.skip(f"Skipping non-{plat} test: {item.name}")
