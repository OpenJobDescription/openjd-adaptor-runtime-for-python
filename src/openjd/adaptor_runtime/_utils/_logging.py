# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import logging
import re
from typing import (
    List,
    Optional,
)


class ConditionalFormatter(logging.Formatter):
    """
    A Formatter subclass that applies formatting conditionally.
    """

    def __init__(
        self,
        *args,
        ignore_patterns: Optional[List[re.Pattern[str]]],
        **kwargs,
    ):
        """
        Args:
            ignore_patterns (Optional[List[re.Pattern[str]]]): List of patterns that, when matched,
                indicate a log message must not be formatted (it is "ignored" by the formatter)
        """
        self._ignore_patterns = ignore_patterns or []
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        for ignore_pattern in self._ignore_patterns:
            if ignore_pattern.match(record.msg):
                return record.getMessage()

        return super().format(record)
