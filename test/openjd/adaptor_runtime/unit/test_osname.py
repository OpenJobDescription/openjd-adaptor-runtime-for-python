# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from typing import Callable
from unittest.mock import Mock, patch

import pytest

import openjd.adaptor_runtime._osname as osname
from openjd.adaptor_runtime._osname import OSName


class TestOSName:
    @pytest.mark.parametrize("platform", ["Windows", "Darwin", "Linux"])
    @patch.object(osname, "platform")
    def test_empty_init_returns_osname(self, mock_platform: Mock, platform: str):
        # GIVEN
        mock_platform.system.return_value = platform

        # WHEN
        osname = OSName()

        # THEN
        assert isinstance(osname, OSName)
        if platform == "Darwin":
            assert str(osname) == OSName.MACOS
        else:
            assert str(osname) == platform

    alias_params = [
        pytest.param(
            (
                "Darwin",
                "darwin",
                "MacOS",
                "macos",
                "mac",
                "Mac",
                "mac os",
                "MAC OS",
                "os x",
                "OS X",
            ),
            OSName.MACOS,
            OSName.is_macos,
            id="macOS",
        ),
        pytest.param(
            ("Windows", "win", "win32", "nt", "windows"),
            OSName.WINDOWS,
            OSName.is_windows,
            id="windows",
        ),
        pytest.param(("linux", "linux2"), OSName.LINUX, OSName.is_linux, id="linux"),
        pytest.param(("posix", "Posix", "POSIX"), OSName.POSIX, OSName.is_posix, id="posix"),
    ]

    @pytest.mark.parametrize("aliases, expected, is_os_func", alias_params)
    def test_aliases(self, aliases: list[str], expected: str, is_os_func: Callable):
        for alias in aliases:
            # WHEN
            osname = OSName(alias)

            # THEN
            assert isinstance(
                osname, OSName
            ), f"OSName('{alias}') did not return object of type OSName"
            assert str(osname) == expected, f"OSName('{alias}') did not resolve to '{expected}'"
            assert (
                osname == alias
            ), f"OSName.__eq__ failed comparison with OSName('{alias}') and '{alias}'"
            assert is_os_func(alias), f"OSName.is_{expected.lower()}() failed for '{alias}'"
