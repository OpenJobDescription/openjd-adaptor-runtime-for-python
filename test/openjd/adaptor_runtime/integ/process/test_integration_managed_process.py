# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os
import re
import sys
import time
from logging import INFO
from typing import List
from unittest import mock

import pytest

from openjd.adaptor_runtime._osname import OSName
from openjd.adaptor_runtime.app_handlers import RegexCallback, RegexHandler
from openjd.adaptor_runtime.process import ManagedProcess


class TestManagedProcess(object):
    """Integration tests for ManagedProcess"""

    def test_run(self, caplog):
        """Testing a success case for the managed process."""

        class FakeManagedProcess(ManagedProcess):
            def get_executable(self) -> str:
                if OSName.is_windows():
                    return "powershell.exe"
                else:
                    return "echo"

            def get_arguments(self) -> List[str]:
                if OSName.is_windows():
                    return ["echo", "Hello World!"]
                else:
                    return ["Hello World!"]

            def get_startup_directory(self) -> str | None:
                return None

        caplog.set_level(INFO)

        mp = FakeManagedProcess({})
        mp.run()

        assert "Hello World!" in caplog.text


class TestIntegrationRegexHandlerManagedProcess(object):
    """Integration tests for LoggingSubprocess"""

    invoked_regex_list = [
        pytest.param(
            re.compile(".*"),
            "Test output",
            5,
        ),
    ]

    @pytest.mark.parametrize("stdout, stderr", [(1, 0), (0, 1), (1, 1)])
    @pytest.mark.parametrize("regex, output, echo_count", invoked_regex_list)
    def test_regexhandler_invoked(self, regex, output, echo_count, stdout, stderr):
        # GIVEN
        class FakeManagedProcess(ManagedProcess):
            def get_executable(self) -> str:
                return sys.executable

            def get_arguments(self) -> List[str]:
                test_file = os.path.join(
                    os.path.abspath(os.path.dirname(__file__)), "scripts", "echo_sleep_n_times.py"
                )
                return [test_file, output, str(echo_count)]

            def get_startup_directory(self) -> str | None:
                return None

        callback = mock.Mock()
        regex_callbacks = [RegexCallback([regex], callback)]
        regex_handler = RegexHandler(regex_callbacks)

        # WHEN

        mp = FakeManagedProcess(
            {},
            stdout_handler=regex_handler if stdout else None,
            stderr_handler=regex_handler if stderr else None,
        )
        mp.run()
        time.sleep(0.01)  # magic sleep - logging handler has a delay and test can exit too fast

        # THEN
        assert callback.call_count == echo_count * (stdout + stderr)
        assert all(c[0][0].re == regex for c in callback.call_args_list)
