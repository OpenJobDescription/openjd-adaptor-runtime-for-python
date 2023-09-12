# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Sequence


@dataclass
class RegexCallback:
    """
    Dataclass for regex callbacks
    """

    regex_list: List[re.Pattern[str]]
    callback: Callable[[re.Match], None]
    exit_if_matched: bool = False
    only_run_if_first_matched: bool = False

    def __init__(
        self,
        regex_list: Sequence[re.Pattern[str]],
        callback: Callable[[re.Match], None],
        exit_if_matched: bool = False,
        only_run_if_first_matched: bool = False,
    ) -> None:
        """
        Initializes a RegexCallback

        Args:
            regex_list (Sequence[re.Pattern[str]]): A sequence of regex patterns which will invoke
                the callback if any single regex matches a logged string. This will be stored as a
                separate list object than the sequence passed in the constructor.
            callback (Callable[[re.Match], None]): A callable which takes a re.Match object as the
                only argument. The re.Match object is from the pattern that matched the string
                tested against it.
            exit_if_matched (bool, optional): Indicates if the handler should exit early if this
                RegexCallback is matched. This will prevent future RegexCallbacks from being
                invoked if this RegexCallback matched first. Defaults to False.
            only_run_if_first_matched (bool, optional): Indicates if the handler should only
                call the callback if this RegexCallback was the first to have a regex match a logged
                line.
        """
        self.regex_list = list(regex_list)
        self.callback = callback
        self.exit_if_matched = exit_if_matched
        self.only_run_if_first_matched = only_run_if_first_matched

    def get_match(self, msg: str) -> re.Match | None:
        """
        Provides the first regex in self.regex_list that matches a given msg.

        Args:
            msg (str): A message to test against each regex in the regex_list

        Returns:
            re.Match | None: The match object from the first regex that matched the message, none
                if no regex matched.
        """
        for regex in self.regex_list:
            if match := regex.search(msg):
                return match
        return None


class RegexHandler(logging.Handler):
    """
    A Logging Handler that adds the ability to call Callbacks based on Regex
    Matches of logged lines.
    """

    regex_callbacks: List[RegexCallback]

    def __init__(
        self, regex_callbacks: Sequence[RegexCallback], level: int = logging.NOTSET
    ) -> None:
        """
        Initializes a RegexHandler

        Args:
            regex_callbacks (Sequence[RegexCallback]): A sequence of RegexCallback objects which
                will be iterated through on each logged message. RegexCallbacks are tested and
                called in the same order as they are provided in the sequence.

                A new list object will be created from the provided sequence, if the callback list
                needs to be modified then you must access the new list through the regex_callbacks
                property.
            level (int, optional): A minimum level of message that will be handled.
                Defaults to logging.NOTSET.
        """
        super().__init__(level)
        self.regex_callbacks = list(regex_callbacks)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Method which is called by the logger when a string is logged to a logger
        this handler has been added to.
        Args:
            record (logging.LogRecord): The log record of the logged string
        """
        matched = False
        for regex_callback in self.regex_callbacks:
            if matched and regex_callback.only_run_if_first_matched:
                continue
            if match := regex_callback.get_match(record.msg):
                regex_callback.callback(match)
            if match and regex_callback.exit_if_matched:
                break
            matched = matched or match is not None
