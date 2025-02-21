# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import pathlib
import os
import re
import sys
from logging import INFO
from typing import cast
from unittest.mock import patch
from pathlib import Path

import pytest

import openjd.adaptor_runtime._entrypoint as runtime_entrypoint
from openjd.adaptor_runtime import EntryPoint
from openjd.adaptor_runtime._osname import OSName

mod_path = Path(__file__).parent.resolve()
sys.path.append(str(mod_path))
if (_pypath := os.environ.get("PYTHONPATH")) is not None:
    os.environ["PYTHONPATH"] = ":".join((_pypath, str(mod_path)))
else:
    os.environ["PYTHONPATH"] = str(mod_path)
from CommandAdaptorExample import CommandAdaptorExample  # noqa: E402


class TestCommandAdaptorRun:
    """
    Tests for the CommandAdaptor running using the `run` command-line.
    """

    def test_runs_command_adaptor(
        self, capfd: pytest.CaptureFixture, caplog: pytest.LogCaptureFixture, tmp_path: pathlib.Path
    ):
        # GIVEN
        caplog.set_level(INFO)
        test_sys_argv = [
            "program_filename.py",
            "run",
            "--init-data",
            json.dumps(
                {
                    "on_prerun": "on_prerun",
                    "on_postrun": "on_postrun",
                }
            ),
            "--run-data",
            json.dumps(
                {"args": ["echo", "hello world"] if OSName.is_windows() else ["hello world"]}
            ),
        ]
        entrypoint = EntryPoint(CommandAdaptorExample)

        # WHEN
        with (
            patch.object(runtime_entrypoint.sys, "argv", test_sys_argv),
            patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
        ):
            entrypoint.start()

        # THEN
        assert "on_prerun" in caplog.text
        assert "hello world" in caplog.text
        assert "on_postrun" in caplog.text

        # THEN
        result = cast(str, capfd.readouterr().out)
        assert re.match(".*prerun-print.*postrun-print.*", result, flags=re.RegexFlag.DOTALL)


class TestCommandAdaptorDaemon:
    """
    Tests for the CommandAdaptor running using the `daemon` command-line.
    """

    class TestUsingConnectionFile:
        """
        Daemon tests using the --connection-file option
        """

        def test_start_stop(self, caplog: pytest.LogCaptureFixture, tmp_path: Path):
            # GIVEN
            caplog.set_level(INFO)
            connection_file = tmp_path / "connection.json"
            entrypoint = EntryPoint(CommandAdaptorExample)

            # WHEN
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_start_argv(connection_file=connection_file),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_stop_argv(connection_file=connection_file),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()

            # THEN
            assert "Initializing backend process" in caplog.text
            assert "Connected successfully" in caplog.text
            assert "Running in background daemon mode." in caplog.text
            assert "Daemon background process stopped." in caplog.text
            assert "on_prerun" in caplog.text
            assert "on_postrun" in caplog.text

        def test_run(self, caplog: pytest.LogCaptureFixture, tmp_path: Path):
            # GIVEN
            caplog.set_level(INFO)
            connection_file = tmp_path / "connection.json"
            test_run_argv = [
                "program_filename.py",
                "daemon",
                "run",
                "--connection-file",
                str(connection_file),
                "--run-data",
                json.dumps(
                    {"args": ["echo", "hello world"] if OSName.is_windows() else ["hello world"]}
                ),
            ]
            entrypoint = EntryPoint(CommandAdaptorExample)

            # WHEN
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_start_argv(connection_file=connection_file),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()
            with (
                patch.object(runtime_entrypoint.sys, "argv", test_run_argv),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_stop_argv(connection_file=connection_file),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()

            # THEN
            assert "on_prerun" in caplog.text
            assert "hello world" in caplog.text
            assert "on_postrun" in caplog.text

    class TestUsingEnvVar:
        """
        Daemon tests that do not use the --connection-file option and instead use the
        OPENJD_ADAPTOR_SOCKET environment variable
        """

        def test_full_cycle(self, caplog: pytest.LogCaptureFixture) -> None:
            # GIVEN
            caplog.set_level(INFO)
            entrypoint = EntryPoint(CommandAdaptorExample)

            # WHEN
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_start_argv(connection_file=None),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
            ):
                entrypoint.start()

            # THEN
            match = re.search(
                "openjd_env: OPENJD_ADAPTOR_SOCKET=(.*)$",
                caplog.text,
                re.MULTILINE,
            )
            assert (
                match is not None
            ), f"Expected openjd_env statement not found in output: {caplog.text}"
            openjd_adaptor_socket = match.group(1)
            print(
                f"DEBUG: Using OPENJD_ADAPTOR_SOCKET={openjd_adaptor_socket} (exists={os.path.exists(openjd_adaptor_socket)})"
            )

            # WHEN
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_run_argv(connection_file=None),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
                patch.dict(
                    runtime_entrypoint.os.environ, {"OPENJD_ADAPTOR_SOCKET": openjd_adaptor_socket}
                ),
            ):
                entrypoint.start()
            with (
                patch.object(
                    runtime_entrypoint.sys,
                    "argv",
                    TestCommandAdaptorDaemon.get_stop_argv(connection_file=None),
                ),
                patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
                patch.dict(
                    runtime_entrypoint.os.environ, {"OPENJD_ADAPTOR_SOCKET": openjd_adaptor_socket}
                ),
            ):
                entrypoint.start()

            # THEN
            assert "Initializing backend process" in caplog.text
            assert "Connected successfully" in caplog.text
            assert "Running in background daemon mode." in caplog.text
            assert "on_prerun" in caplog.text
            assert "hello world" in caplog.text
            assert "on_postrun" in caplog.text
            assert "Daemon background process stopped." in caplog.text

    @staticmethod
    def get_start_argv(*, connection_file: Path | None = None) -> list[str]:
        return [
            "program_filename.py",
            "daemon",
            "start",
            *(["--connection-file", str(connection_file)] if connection_file else []),
            "--init-data",
            json.dumps(
                {
                    "on_prerun": "on_prerun",
                    "on_postrun": "on_postrun",
                }
            ),
        ]

    @staticmethod
    def get_run_argv(*, connection_file: Path | None = None) -> list[str]:
        return [
            "program_filename.py",
            "daemon",
            "run",
            *(["--connection-file", str(connection_file)] if connection_file else []),
            "--run-data",
            json.dumps(
                {"args": ["echo", "hello world"] if OSName.is_windows() else ["hello world"]}
            ),
        ]

    @staticmethod
    def get_stop_argv(*, connection_file: Path | None = None) -> list[str]:
        return [
            "program_filename.py",
            "daemon",
            "stop",
            *(
                [
                    "--connection-file",
                    str(connection_file),
                ]
                if connection_file
                else []
            ),
        ]
