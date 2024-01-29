# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os as _os
import signal
import sys
import subprocess as _subprocess
from time import sleep as _sleep
from typing import Dict, Any

from openjd.adaptor_runtime._osname import OSName


class TestIntegrationClientInterface:
    """ "These are the integration tests for the client interface."""

    def test_graceful_shutdown(self) -> None:
        # Create the subprocess
        popen_params: Dict[str, Any] = dict(
            args=[
                sys.executable,
                _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), "fake_client.py"),
            ],
            stdin=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
            stdout=_subprocess.PIPE,
            encoding="utf-8",
        )
        if OSName.is_windows():
            # In Windows, this is required for signal. SIGBREAK will be sent to the entire process group.
            # Without this one, current process will also get the SIGBREAK and may react incorrectly.
            popen_params.update(creationflags=_subprocess.CREATE_NEW_PROCESS_GROUP)  # type: ignore[attr-defined]
        client_subprocess = _subprocess.Popen(**popen_params)

        # To avoid a race condition, giving some extra time for the logging subprocess to start.
        _sleep(0.5 if OSName.is_posix() else 4)
        if OSName.is_windows():
            signal_type = signal.CTRL_BREAK_EVENT  # type: ignore[attr-defined]
        else:
            signal_type = signal.SIGTERM

        client_subprocess.send_signal(signal_type)

        # To avoid a race condition, giving some extra time for the log to be updated after
        # receiving the signal.
        _sleep(0.5 if OSName.is_posix() else 4)

        out, _ = client_subprocess.communicate()

        assert f"Received {'SIGBREAK' if OSName.is_windows() else 'SIGTERM'} signal." in out
