# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Test to reproduce a bug where progress reporting via update_status() does not
propagate from the background adaptor to the frontend process's stdout.

The flow is:
  1. Application outputs progress info
  2. Background adaptor (backend process) calls update_status(progress=X)
  3. update_status writes "openjd_progress: X" to sys.stdout
  4. Frontend process should emit "openjd_progress: X" on its own stdout
     so the worker agent can detect it

The bug: In daemon/background mode, the backend process replaces its stream
handler with a LogBufferHandler. But update_status() writes directly to
sys.stdout (not through the logging framework), so the progress message
never reaches the log buffer, and thus never reaches the frontend.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from logging import INFO
from unittest.mock import patch
from pathlib import Path

import pytest

import openjd.adaptor_runtime._entrypoint as runtime_entrypoint
from openjd.adaptor_runtime import EntryPoint

mod_path = Path(__file__).parent.resolve()
sys.path.append(str(mod_path))

if (_pypath := os.environ.get("PYTHONPATH")) is not None:
    os.environ["PYTHONPATH"] = os.pathsep.join([_pypath, str(mod_path)])
else:
    os.environ["PYTHONPATH"] = str(mod_path)

from ProgressReportingAdaptor import ProgressReportingAdaptor  # noqa: E402


class TestProgressReportingInDaemonMode:
    """
    Tests that progress messages from update_status() in the background adaptor
    are propagated to the frontend process's stdout so the worker agent can
    detect them.
    """

    def test_progress_propagates_to_frontend_stdout(
        self,
        capfd: pytest.CaptureFixture,
        caplog: pytest.LogCaptureFixture,
        tmp_path: pathlib.Path,
    ):
        """
        Reproduces the bug: when running in daemon mode, calling
        update_status(progress=50) in the backend adaptor should result in
        "openjd_progress: 50" appearing on the frontend's stdout.

        The worker agent monitors the frontend process's stdout for these
        messages. If they don't appear, the worker never knows about progress.
        """
        caplog.set_level(INFO)
        connection_file = tmp_path / "connection.json"
        entrypoint = EntryPoint(ProgressReportingAdaptor)

        # Start the daemon
        start_argv = [
            "program_filename.py",
            "daemon",
            "start",
            "--connection-file",
            str(connection_file),
        ]
        with (
            patch.object(runtime_entrypoint.sys, "argv", start_argv),
            patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
        ):
            entrypoint.start()

        # Run with progress=50
        run_argv = [
            "program_filename.py",
            "daemon",
            "run",
            "--connection-file",
            str(connection_file),
            "--run-data",
            json.dumps({"progress": 50.0}),
        ]
        with (
            patch.object(runtime_entrypoint.sys, "argv", run_argv),
            patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
        ):
            entrypoint.start()

        # Stop the daemon
        stop_argv = [
            "program_filename.py",
            "daemon",
            "stop",
            "--connection-file",
            str(connection_file),
        ]
        with (
            patch.object(runtime_entrypoint.sys, "argv", stop_argv),
            patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
        ):
            entrypoint.start()

        # Verify that "openjd_progress: 50" appeared on stdout.
        # The worker agent is watching stdout for this pattern.
        captured = capfd.readouterr()
        assert "openjd_progress: 50" in captured.out, (
            f"Expected 'openjd_progress: 50' on stdout but got:\n{captured.out}\n\n"
            f"Log output:\n{caplog.text}"
        )

    def test_progress_works_in_run_mode(
        self,
        capfd: pytest.CaptureFixture,
        caplog: pytest.LogCaptureFixture,
    ):
        """
        Sanity check: progress reporting works fine in non-daemon 'run' mode
        because update_status writes directly to sys.stdout and the worker
        agent is directly reading from that process's stdout.
        """
        caplog.set_level(INFO)
        entrypoint = EntryPoint(ProgressReportingAdaptor)

        run_argv = [
            "program_filename.py",
            "run",
            "--run-data",
            json.dumps({"progress": 75.0}),
        ]
        with (
            patch.object(runtime_entrypoint.sys, "argv", run_argv),
            patch.object(runtime_entrypoint.logging.Logger, "setLevel"),
        ):
            entrypoint.start()

        captured = capfd.readouterr()
        assert (
            "openjd_progress: 75" in captured.out
        ), f"Expected 'openjd_progress: 75' on stdout but got:\n{captured.out}"
