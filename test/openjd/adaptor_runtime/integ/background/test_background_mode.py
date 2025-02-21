# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from http import HTTPStatus
from typing import Generator
from unittest.mock import patch
from pathlib import Path

import psutil
import pytest

import openjd.adaptor_runtime._entrypoint as runtime_entrypoint
from openjd.adaptor_runtime._background.frontend_runner import (
    FrontendRunner,
    HTTPError,
)
from openjd.adaptor_runtime._background.loaders import (
    ConnectionSettingsLoadingError,
    ConnectionSettingsFileLoader,
)
from openjd.adaptor_runtime._osname import OSName

mod_path = (Path(__file__).parent.parent).resolve()
sys.path.append(str(mod_path))
if (_pypath := os.environ.get("PYTHONPATH")) is not None:
    os.environ["PYTHONPATH"] = os.pathsep.join((_pypath, str(mod_path)))
else:
    os.environ["PYTHONPATH"] = str(mod_path)
from AdaptorExample import AdaptorExample  # noqa: E402


class TestDaemonMode:
    """
    Tests for background daemon mode.
    """

    @pytest.fixture(autouse=True)
    def mock_runtime_logger_level(self, tmpdir: pathlib.Path):
        # Set up a config file for the backend process
        config = {"log_level": "DEBUG"}
        config_path = os.path.join(tmpdir, "configuration.json")
        with open(config_path, mode="w", encoding="utf-8") as f:
            json.dump(config, f)

        # Override the default config path to the one we just created
        with (patch.dict(os.environ, {runtime_entrypoint._ENV_CONFIG_PATH_PREFIX: config_path}),):
            yield

    @pytest.fixture
    def connection_file_path(self, tmp_path: pathlib.Path) -> pathlib.Path:
        connection_dir = os.path.join(tmp_path.absolute(), "connection_dir")
        os.mkdir(connection_dir)
        if OSName.is_windows():
            # In Windows, to prevent false positives in tests, it's crucial to remove the "Delete subfolders and files"
            # permission from the parent folder. This step ensures that files cannot be deleted without explicit delete
            # permissions, addressing an edge case where the same user owns both the parent folder and the file,
            # bypassing delete permissions. `set_file_permissions_in_windows` will restrict the permission to read,
            # write, delete current folder, which meets the requirement.
            from openjd.adaptor_runtime._utils._secure_open import set_file_permissions_in_windows

            set_file_permissions_in_windows(connection_dir)
        return pathlib.Path(connection_dir) / "connection.json"

    @pytest.fixture
    def initialized_setup(
        self,
        connection_file_path: pathlib.Path,
        caplog: pytest.LogCaptureFixture,
    ) -> Generator[tuple[FrontendRunner, psutil.Process], None, None]:
        caplog.set_level(0)
        frontend = FrontendRunner(timeout_s=5.0)
        frontend.init(
            adaptor_module=sys.modules[AdaptorExample.__module__],
            connection_file_path=connection_file_path,
        )

        match = re.search("Started backend process. PID: ([0-9]+)", caplog.text)
        assert match is not None
        pid = int(match.group(1))
        backend_proc = psutil.Process(pid)

        yield (frontend, backend_proc)

        try:
            backend_proc.kill()
        except psutil.NoSuchProcess:
            pass  # Already stopped

        # We don't need to call the `remove` for the NamedPipe server.
        # NamedPipe servers are managed by Named Pipe File System it is not a regular file.
        # Once all handles are closed, the system automatically cleans up the named pipe.
        if OSName.is_posix():
            try:
                conn_settings = ConnectionSettingsFileLoader(connection_file_path).load()
            except ConnectionSettingsLoadingError as e:
                print(
                    f"Failed to load connection settings, socket file cleanup will be skipped: {e}"
                )
            else:
                try:
                    os.remove(conn_settings.socket)
                except FileNotFoundError:
                    pass  # Already deleted

    def test_init(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        connection_file_path: pathlib.Path,
    ) -> None:
        # GIVEN
        _, backend_proc = initialized_setup

        # THEN
        assert os.path.exists(connection_file_path)

        connection_settings = ConnectionSettingsFileLoader(connection_file_path).load()

        if OSName.is_windows():
            import pywintypes
            import win32file

            try:
                handle = win32file.CreateFile(
                    connection_settings.socket,
                    win32file.GENERIC_READ,
                    0,  # No sharing
                    None,  # Default security
                    win32file.OPEN_EXISTING,
                    0,  # Default attributes
                    None,  # No template file
                )
                win32file.CloseHandle(handle)
            except pywintypes.error as e:
                # If an error occurred, it means the pipe does not exist
                assert False, f"Named pipe is not created successfully. Fail to connect to it: {e}"

        else:
            assert any(
                [
                    conn.laddr == connection_settings.socket
                    for conn in backend_proc.connections(kind="unix")
                ]
            )

    def test_shutdown(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        connection_file_path: pathlib.Path,
    ) -> None:
        # GIVEN
        frontend, backend_proc = initialized_setup
        conn_settings = ConnectionSettingsFileLoader(connection_file_path).load()

        # WHEN
        frontend.shutdown()

        # THEN
        assert all(
            [
                _wait_for_file_deletion(p, timeout_s=1)
                for p in [str(connection_file_path), conn_settings.socket]
            ]
        )

        # "Assert" the process exits after requesting shutdown.
        # The "assertion" fails if we time out waiting.
        backend_proc.wait(timeout=1)

    def test_start(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup

        # WHEN
        frontend.start()

        # THEN
        assert "on_start" in caplog.text

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows named pipe test")
    def test_incorrect_request_path_in_windows(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup

        # WHEN
        with pytest.raises(
            HTTPError,
            match="Received unexpected HTTP status code 404: Incorrect request path None.",
        ):
            frontend._send_request("GET", "None")

    @pytest.mark.skipif(not OSName.is_windows(), reason="Windows named pipe test")
    def test_incorrect_request_method_in_windows(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup

        # WHEN
        with pytest.raises(
            HTTPError,
            match="Received unexpected HTTP status code 405: Incorrect request method none for the path /start.",
        ):
            frontend._send_request("none", "/start")  # type: ignore

    @pytest.mark.parametrize(
        argnames=["run_data"],
        argvalues=[
            [[{"one": 1}]],
            [[{"one": 1}, {"two": 2}]],
        ],
        ids=["runs once", "runs consecutively"],
    )
    def test_run(
        self,
        run_data: list[dict],
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup

        for data in run_data:
            # WHEN
            frontend.run(data)

            # THEN
            assert f"on_run: {data}" in caplog.text

    def test_stop(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup

        # WHEN
        frontend.stop()

        # THEN
        assert "on_stop" in caplog.text

    def test_heartbeat_acks(
        self,
        initialized_setup: tuple[FrontendRunner, psutil.Process],
    ) -> None:
        # GIVEN
        frontend, _ = initialized_setup
        response = frontend._heartbeat()

        # WHEN
        new_response = frontend._heartbeat(response.output.id)
        # In Windows, we need to shut down the namedpipe client,
        # or the connection of the NamedPipe server remains open
        if OSName.is_windows():
            frontend.shutdown()
        # THEN
        assert f"Received ACK for chunk: {response.output.id}" in new_response.output.output

    class TestAuthentication:
        """
        Tests for background mode authentication.

        Tests that require another OS user are in the Adaptor Runtime pipeline.
        """

        def test_accepts_same_uid_process(
            self, initialized_setup: tuple[FrontendRunner, psutil.Process]
        ) -> None:
            # GIVEN
            frontend, _ = initialized_setup

            # WHEN
            try:
                frontend._heartbeat()
            except HTTPError as e:
                if e.response.status == HTTPStatus.UNAUTHORIZED:  # type: ignore[union-attr]
                    pytest.fail("Request failed authentication when it should have succeeded")
                else:
                    pytest.fail(f"Request failed with an unexpected status code: {e}")
            else:
                # THEN
                # Heartbeat request went through, so auth succeeded
                pass


def _wait_for_file_deletion(path: str, timeout_s: float) -> bool:
    start = time.time()
    while os.path.exists(path):
        if time.time() - start < timeout_s:
            time.sleep(0.01)
        else:
            return False
    return True
