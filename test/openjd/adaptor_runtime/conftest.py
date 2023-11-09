# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import platform
from openjd.adaptor_runtime._osname import OSName

import pytest


# TODO: Remove this one after Windows Development finish
#  https://docs.pytest.org/en/7.1.x/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems
def pytest_collection_modifyitems(items):
    if OSName.is_windows():
        # Add the tests' paths that we want to enable in Windows
        do_not_skip_paths = []
        skip_marker = pytest.mark.skip(reason="Skipping tests on Windows")
        for item in items:
            if not any(not_skip_path in item.fspath.strpath for not_skip_path in do_not_skip_paths):
                item.add_marker(skip_marker)


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
