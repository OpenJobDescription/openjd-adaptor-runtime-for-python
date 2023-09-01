# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import logging
import re
from typing import Dict, List, Tuple
from unittest.mock import Mock

import pytest

from openjd.adaptor_runtime.app_handlers import RegexCallback, RegexHandler


class TestLoggingRegexHandler:
    """
    Tests for the RegexHandler when using the logging library
    """

    invoked_regex_list = [
        pytest.param(
            [re.compile(".*")],
            0,
            "Test input",
            ["Test input", ""],
            id="Match everything regex call once",
        ),
        pytest.param(
            [re.compile(r"input")], 0, "Test input", ["input"], id="Match a word regex call once"
        ),
        pytest.param(
            [re.compile(r"\w+")],
            0,
            "Test input",
            ["Test", "input"],
            id="Match multiple words regex call once",
        ),
        pytest.param(
            [re.compile("b"), re.compile("s")],
            1,
            "Test input",
            ["s"],
            id="Multiple regexes single match call once",
        ),
        pytest.param(
            [re.compile("t"), re.compile("s")],
            0,
            "Test input",
            ["t", "t"],
            id="Multiple regexes multiple match call once",
        ),
        pytest.param(
            [re.compile("test", flags=re.IGNORECASE)],
            0,
            "Test input",
            ["Test"],
            id="Ignore case regex",
        ),
    ]

    @pytest.mark.parametrize(
        "regex_list, match_regex_index, input, find_all_results", invoked_regex_list
    )
    def test_regex_handler_invoked(
        self,
        regex_list: List[re.Pattern],
        match_regex_index: int,
        input: str,
        find_all_results: List[str],
    ):
        # GIVEN
        callback_mock = Mock().callback
        regex_callback = RegexCallback(regex_list, callback_mock)
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.INFO)
        handler = RegexHandler([regex_callback])
        stdout_logger.addHandler(handler)

        # WHEN
        stdout_logger.info(input)

        # THEN
        callback_mock.assert_called_once()
        assert callback_mock.call_args[0][0].re == regex_list[match_regex_index]
        assert regex_list[match_regex_index].findall(input) == find_all_results

    noninvoked_regex_list = [
        pytest.param([re.compile("(?!)")], "Test input", id="Match nothing regex"),
        pytest.param([re.compile(r"a")], "Test input", id="Single letter match nothing regex"),
    ]

    @pytest.mark.parametrize("regex_list, input", noninvoked_regex_list)
    def test_regex_handler_not_invoked(
        self,
        regex_list: List[re.Pattern],
        input: str,
    ):
        # GIVEN
        callback_mock = Mock().callback
        regex_callback = RegexCallback(regex_list, callback_mock)
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.INFO)
        handler = RegexHandler([regex_callback])
        stdout_logger.addHandler(handler)

        # WHEN
        stdout_logger.info(input)

        # THEN
        callback_mock.assert_not_called()
        assert regex_list[0].findall(input) == []

    multiple_regex_list = [
        pytest.param(
            [[re.compile("Test")], [re.compile("Input", flags=re.IGNORECASE)]],
            "Test input",
            id="Match twice regexes",
        ),
        pytest.param(
            [[re.compile("T")], [re.compile("e")], [re.compile("s")], [re.compile("t")]],
            "Test input",
            id="Single letter match four times",
        ),
        pytest.param(
            [[re.compile("T"), re.compile("e")], [re.compile("s"), re.compile("t")]],
            "Test input",
            id="Multiple callbacks with multiple matching regexes match twice",
        ),
    ]

    @pytest.mark.parametrize("regex_lists, input", multiple_regex_list)
    def test_multiple_callbacks(
        self,
        regex_lists: List[List[re.Pattern]],
        input: str,
    ):
        # GIVEN
        callback_mock = Mock().callback
        regex_callbacks = [RegexCallback(regex_list, callback_mock) for regex_list in regex_lists]
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.INFO)
        handler = RegexHandler(regex_callbacks)
        stdout_logger.addHandler(handler)

        # WHEN
        stdout_logger.info(input)

        # THEN
        assert callback_mock.call_count == len(regex_lists)
        assert all(
            c[0][0].re == patterns[0]
            for c, patterns in zip(callback_mock.call_args_list, regex_lists)
        )
        for regex_list in regex_lists:
            assert regex_list[0].search(input)

    multiple_loggers = [
        pytest.param(
            {
                logging.getLogger("info_logger"): [re.compile("INFO: "), re.compile("STDOUT: ")],
                logging.getLogger("error_logger"): [re.compile("ERROR: ")],
            },
            "Test input",
        ),
    ]

    @pytest.mark.parametrize("loggers, input", multiple_loggers)
    def test_multiple_loggers(
        self,
        loggers: Dict[logging.Logger, List[re.Pattern]],
        input: str,
    ):
        # GIVEN
        regex_callbacks = {}
        for logger, regex_list in loggers.items():
            logger.setLevel(logging.INFO)
            callback_mock = Mock()
            regex_callback = RegexCallback(regex_list, callback_mock)
            handler = RegexHandler([regex_callback])
            logger.addHandler(handler)
            regex_callbacks[callback_mock] = [pattern for pattern in regex_list]

        # WHEN
        for patterns in regex_callbacks.values():
            for logger in loggers.keys():
                for pattern in patterns:
                    logger.info(f"{pattern.pattern}: {input}")

        # THEN
        for callback_mock, patterns in regex_callbacks.items():
            print(callback_mock.call_args_list)
            assert callback_mock.call_count == len(patterns)
            assert all(
                c[0][0].re == pattern for c, pattern in zip(callback_mock.call_args_list, patterns)
            )

    exit_if_matched_regexes = [
        pytest.param(
            [(re.compile("Test"), True, True), (re.compile("input"), False, True)],
            "Test input",
            id="Multiple matches, exit_if_matched first",
        ),
        pytest.param(
            [
                (re.compile("T"), False, True),
                (re.compile("e"), True, True),
                (re.compile("s"), False, True),
                (re.compile("t"), False, True),
            ],
            "Test input",
            id="Single letter match four times, exit_if_matched second",
        ),
        pytest.param(
            [
                (re.compile("a"), True, False),
                (re.compile("b"), False, False),
                (re.compile("c"), True, True),
                (re.compile("d"), False, True),
            ],
            "cd",
            id="Multiple matched, multiple exit_if_matched",
        ),
    ]

    @pytest.mark.parametrize("regex_list, input", exit_if_matched_regexes)
    @pytest.mark.parametrize("exit_if_matched", [False, True])
    def test_exit_if_matched(
        self,
        exit_if_matched: bool,
        regex_list: List[Tuple[re.Pattern, bool, bool]],
        input: str,
    ):
        # GIVEN
        callback_mock = Mock().callback
        regex_callbacks = [
            RegexCallback(
                [pattern], callback_mock, exit_if_matched=exit_if_matched and exit_this_pattern
            )
            for (pattern, exit_this_pattern, _) in regex_list
        ]
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.INFO)
        handler = RegexHandler(regex_callbacks)
        stdout_logger.addHandler(handler)

        # WHEN
        stdout_logger.info(input)

        # THEN
        if not exit_if_matched:
            patterns = [pattern for pattern, _, matches in regex_list if matches]
            assert callback_mock.call_count == len(patterns)
            assert all(
                c[0][0].re == pattern for c, pattern in zip(callback_mock.call_args_list, patterns)
            )
        else:
            patterns = []
            for pattern, exit_this_pattern, matches_input in regex_list:
                if matches_input:
                    patterns.append(pattern)
                    if exit_this_pattern:
                        break
            assert callback_mock.call_count == len(patterns)
            assert all(
                c[0][0].re == pattern for c, pattern in zip(callback_mock.call_args_list, patterns)
            )

    only_run_if_first_regexes = [
        pytest.param(
            [re.compile("Test"), re.compile("input")], 0, "Test input", id="Match twice regexes"
        ),
        pytest.param(
            [re.compile("Test"), re.compile("input")],
            1,
            "Test input",
            id="Match twice regexes only run first",
        ),
        pytest.param(
            [re.compile("T"), re.compile("e"), re.compile("s"), re.compile("t")],
            0,
            "Test input",
            id="Single letter match four times",
        ),
        pytest.param(
            [re.compile("T"), re.compile("e"), re.compile("s"), re.compile("t")],
            3,
            "Test input",
            id="Single letter match four times don't run last",
        ),
    ]

    @pytest.mark.parametrize("regex_list, first_match_index, input", only_run_if_first_regexes)
    @pytest.mark.parametrize("only_run_if_first", [False, True])
    def test_only_run_if_first_matched(
        self,
        only_run_if_first: bool,
        regex_list: List[re.Pattern],
        first_match_index: int,
        input: str,
    ):
        # GIVEN
        callback_mock = Mock().callback
        regex_callbacks = [
            RegexCallback(
                [pattern],
                callback_mock,
                only_run_if_first_matched=only_run_if_first and i == first_match_index,
            )
            for i, pattern in enumerate(regex_list)
        ]
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.INFO)
        handler = RegexHandler(regex_callbacks)
        stdout_logger.addHandler(handler)

        # WHEN
        stdout_logger.info(input)

        # THEN
        if not only_run_if_first or first_match_index == 0:
            assert callback_mock.call_count == len(regex_list)
            assert all(
                c[0][0].re == pattern
                for c, pattern in zip(callback_mock.call_args_list, regex_list)
            )
        else:
            patterns = [pattern for i, pattern in enumerate(regex_list) if i != first_match_index]
            assert callback_mock.call_count == len(regex_list) - 1
            assert all(
                c[0][0].re == pattern for c, pattern in zip(callback_mock.call_args_list, patterns)
            )
