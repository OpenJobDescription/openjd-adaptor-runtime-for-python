# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import signal
import sys
import subprocess as _subprocess
from os.path import dirname as _dirname, join as _join, realpath as _realpath
from time import sleep as _sleep
from typing import Dict, Any

from openjd.adaptor_runtime._osname import OSName


class TestIntegrationClientInterface:
    """These are the integration tests for the client interface."""

    def test_graceful_shutdown(self) -> None:
        # Create the subprocess
        popen_params: Dict[str, Any] = dict(
            args=[
                sys.executable,
                _join(_dirname(_realpath(__file__)), "fake_client.py"),
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

        assert client_subprocess.returncode is None
        client_subprocess.send_signal(signal_type)

        # To avoid a race condition, giving some extra time for the log to be updated after
        # receiving the signal.
        _sleep(0.5 if OSName.is_posix() else 4)

        out, _ = client_subprocess.communicate()

        assert f"Received {'SIGBREAK' if OSName.is_windows() else 'SIGTERM'} signal." in out
        # Ensure the process actually shutdown
        assert client_subprocess.returncode is not None

    def test_client_in_thread_does_not_do_graceful_shutdown(self) -> None:
        """Ensures that a client running in a thread does not crash by attempting to register a signal,
        since they can only be created in the main thread. This means the graceful shutdown is effectively
        ignored."""
        # Create the subprocess
        popen_params: Dict[str, Any] = dict(
            args=[
                sys.executable,
                _join(_dirname(_realpath(__file__)), "fake_client.py"),
                "--run-in-thread",
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
        _sleep(0.5)
        # Ensure the process is still running
        assert client_subprocess.returncode is None
        out, err = client_subprocess.communicate()
        assert "ValueError: signal only works in main thread of the main interpreter" not in err
        assert f"Received {'SIGBREAK' if OSName.is_windows() else 'SIGTERM'} signal." not in out

        # Ensure the process stops
        client_subprocess.kill()
        assert client_subprocess.returncode not in (None, 0)
