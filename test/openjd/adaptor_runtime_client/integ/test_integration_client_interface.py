# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import os as _os
import subprocess as _subprocess
from time import sleep as _sleep


class TestIntegrationClientInterface:
    """ "These are the integration tests for the client interface."""

    def test_graceful_shutdown(self) -> None:
        client_subprocess = _subprocess.Popen(
            [
                "python",
                _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), "fake_client.py"),
            ],
            stdin=_subprocess.PIPE,
            stderr=_subprocess.PIPE,
            stdout=_subprocess.PIPE,
            encoding="utf-8",
        )

        # To avoid a race condition, giving some extra time for the logging subprocess to start.
        _sleep(0.5)
        client_subprocess.terminate()

        # To avoid a race condition, giving some extra time for the log to be updated after
        # receiving the signal.
        _sleep(0.5)

        out, _ = client_subprocess.communicate()

        assert "Received SIGTERM signal." in out
