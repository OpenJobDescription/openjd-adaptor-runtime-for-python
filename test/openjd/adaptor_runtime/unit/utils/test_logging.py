# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import re
from typing import List
from unittest.mock import patch

import pytest

import openjd.adaptor_runtime._utils._logging as logging_mod
from openjd.adaptor_runtime._utils._logging import ConditionalFormatter


class TestConditionalFormatter:
    @pytest.mark.parametrize(
        ["patterns", "message", "should_be_ignored"],
        [
            [
                [
                    re.compile(r"^IGNORE:"),
                ],
                "IGNORE: This should be ignored",
                True,
            ],
            [
                [re.compile(r"^IGNORE:"), re.compile(r"^IGNORE_TWO:")],
                "IGNORE_TWO: This should also be ignored",
                True,
            ],
            [
                [
                    re.compile(r"^IGNORE:"),
                ],
                "INFO: This should not be ignored",
                False,
            ],
        ],
    )
    def test_ignores_patterns(
        self,
        patterns: List[re.Pattern[str]],
        message: str,
        should_be_ignored: bool,
    ) -> None:
        # GIVEN
        record = logging.LogRecord("NAME", 0, "", 0, message, None, None)
        formatter = ConditionalFormatter(ignore_patterns=patterns)

        # WHEN
        with patch.object(logging_mod.logging.Formatter, "format") as mock_format:
            formatter.format(record)

        # THEN
        if should_be_ignored:
            mock_format.assert_not_called()
        else:
            mock_format.assert_called_once_with(record)
