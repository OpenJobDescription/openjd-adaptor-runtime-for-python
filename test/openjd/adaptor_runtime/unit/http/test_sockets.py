# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
import re
import stat
from typing import Generator
from unittest.mock import ANY, MagicMock, call, patch

import pytest

import openjd.adaptor_runtime._http.sockets as sockets
from openjd.adaptor_runtime._http.sockets import (
    LinuxSocketDirectories,
    MacOSSocketDirectories,
    NonvalidSocketPathException,
    NoSocketPathFoundException,
    SocketDirectories,
)


class SocketDirectoriesStub(SocketDirectories):
    def verify_socket_path(self, path: str) -> None:
        pass


class TestSocketDirectories:
    class TestGetProcessSocketPath:
        """
        Tests for SocketDirectories.get_process_socket_path()
        """

        @patch.object(sockets.os, "getpid", return_value=1234)
        def test_gets_path(
            self,
            mock_getpid: MagicMock,
        ) -> None:
            # GIVEN
            namespace = "my-namespace"
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_process_socket_path(namespace)

            # THEN
            assert result.endswith(os.path.join(namespace, str(mock_getpid.return_value)))
            mock_getpid.assert_called_once()

        @patch.object(sockets.os, "getpid", return_value="a" * (sockets._PID_MAX_LENGTH + 1))
        def test_asserts_max_pid_length(self, mock_getpid: MagicMock):
            # GIVEN
            subject = SocketDirectoriesStub()

            # WHEN
            with pytest.raises(AssertionError) as raised_err:
                subject.get_process_socket_path()

            # THEN
            assert raised_err.match(
                f"PID too long. Only PIDs up to {sockets._PID_MAX_LENGTH} digits are supported."
            )
            mock_getpid.assert_called_once()

    class TestGetSocketPath:
        """
        Tests for SocketDirectories.get_socket_path()
        """

        @pytest.fixture(autouse=True)
        def mock_exists(self) -> Generator[MagicMock, None, None]:
            with patch.object(sockets.os.path, "exists") as mock:
                mock.return_value = False
                yield mock

        @pytest.fixture(autouse=True)
        def mock_makedirs(self) -> Generator[MagicMock, None, None]:
            with patch.object(sockets.os, "makedirs") as mock:
                yield mock

        @pytest.fixture
        def home_dir(self) -> str:
            return os.path.join("home", "user")

        @pytest.fixture(autouse=True)
        def mock_expanduser(self, home_dir: str) -> Generator[MagicMock, None, None]:
            with patch.object(sockets.os.path, "expanduser", return_value=home_dir) as mock:
                yield mock

        @pytest.fixture
        def temp_dir(self) -> str:
            return "tmp"

        @pytest.fixture(autouse=True)
        def mock_gettempdir(self, temp_dir: str) -> Generator[MagicMock, None, None]:
            with patch.object(sockets.tempfile, "gettempdir", return_value=temp_dir) as mock:
                yield mock

        def test_gets_home_dir(
            self,
            mock_expanduser: MagicMock,
            home_dir: str,
        ) -> None:
            # GIVEN
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_socket_path("sock")

            # THEN
            mock_expanduser.assert_called_once_with("~")
            assert result.startswith(home_dir)

        @patch.object(sockets.os, "stat")
        @patch.object(SocketDirectoriesStub, "verify_socket_path")
        def test_gets_temp_dir(
            self,
            mock_verify_socket_path: MagicMock,
            mock_stat: MagicMock,
            mock_gettempdir: MagicMock,
            temp_dir: str,
        ) -> None:
            # GIVEN
            exc = NonvalidSocketPathException()
            mock_verify_socket_path.side_effect = [exc, None]  # Raise exc only once
            mock_stat.return_value.st_mode = stat.S_ISVTX
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_socket_path("sock")

            # THEN
            mock_gettempdir.assert_called_once()
            mock_verify_socket_path.assert_has_calls(
                [
                    call(ANY),  # home dir
                    call(result),  # temp dir
                ]
            )
            mock_stat.assert_called_once_with(temp_dir)

        @pytest.mark.parametrize(
            argnames=["create"],
            argvalues=[[True], [False]],
            ids=["created", "not created"],
        )
        def test_create_dir(self, mock_makedirs: MagicMock, create: bool) -> None:
            # GIVEN
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_socket_path("sock", create_dir=create)

            # THEN
            if create:
                mock_makedirs.assert_called_once_with(
                    os.path.dirname(result), mode=0o700, exist_ok=True
                )
            else:
                mock_makedirs.assert_not_called()

        def test_uses_namespace(self) -> None:
            # GIVEN
            namespace = "my-namespace"
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_socket_path("sock", namespace)

            # THEN
            assert os.path.dirname(result).endswith(namespace)

        @patch.object(SocketDirectoriesStub, "verify_socket_path")
        def test_raises_when_no_valid_path_found(self, mock_verify_socket_path: MagicMock) -> None:
            # GIVEN
            mock_verify_socket_path.side_effect = NonvalidSocketPathException()
            subject = SocketDirectoriesStub()

            # WHEN
            with pytest.raises(NoSocketPathFoundException) as raised_exc:
                subject.get_socket_path("sock")

            # THEN
            assert raised_exc.match(
                "Failed to find a suitable base directory to create sockets in for the following "
                "reasons: "
            )
            assert mock_verify_socket_path.call_count == 2

        @patch.object(SocketDirectoriesStub, "verify_socket_path")
        @patch.object(sockets.os, "stat")
        def test_raises_when_no_tmpdir_sticky_bit(
            self,
            mock_stat: MagicMock,
            mock_verify_socket_path: MagicMock,
            temp_dir: str,
        ) -> None:
            # GIVEN
            mock_verify_socket_path.side_effect = [NonvalidSocketPathException(), None]
            mock_stat.return_value.st_mode = 0
            subject = SocketDirectoriesStub()

            # WHEN
            with pytest.raises(NoSocketPathFoundException) as raised_exc:
                subject.get_socket_path("sock")

            # THEN
            assert raised_exc.match(
                re.escape(
                    f"Cannot use temporary directory {temp_dir} because it does not have the "
                    "sticky bit (restricted deletion flag) set"
                )
            )

        @patch.object(sockets.os.path, "exists")
        def test_handles_socket_name_collisions(
            self,
            mock_exists: MagicMock,
        ) -> None:
            # GIVEN
            sock_name = "sock"
            existing_sock_names = [sock_name, f"{sock_name}_1", f"{sock_name}_2"]
            mock_exists.side_effect = ([True] * len(existing_sock_names)) + [False]
            subject = SocketDirectoriesStub()

            # WHEN
            result = subject.get_socket_path(sock_name)

            # THEN
            assert result.endswith(f"{sock_name}_3")
            mock_exists.call_count == len(existing_sock_names) + 1


class TestLinuxSocketDirectories:
    @pytest.mark.parametrize(
        argnames=["path"],
        argvalues=[
            ["a"],
            ["a" * 100],
        ],
        ids=["one byte", "100 bytes"],
    )
    def test_accepts_paths_within_100_bytes(self, path: str):
        """
        Verifies the function accepts paths up to 100 bytes (108 byte max - 8 byte padding
        for socket name portion (path sep + PID))
        """
        # GIVEN
        subject = LinuxSocketDirectories()

        try:
            # WHEN
            subject.verify_socket_path(path)
        except NonvalidSocketPathException as e:
            pytest.fail(f"verify_socket_path raised an error when it should not have: {e}")
        else:
            # THEN
            pass  # success

    def test_rejects_paths_over_100_bytes(self):
        # GIVEN
        length = 101
        path = "a" * length
        subject = LinuxSocketDirectories()

        # WHEN
        with pytest.raises(NonvalidSocketPathException) as raised_exc:
            subject.verify_socket_path(path)

        # THEN
        assert raised_exc.match(
            "Socket base directory path too big. The maximum allowed size is "
            f"{subject._socket_dir_max_length} bytes, but the directory has a size of "
            f"{length}: {path}"
        )


class TestMacOSSocketDirectories:
    @pytest.mark.parametrize(
        argnames=["path"],
        argvalues=[
            ["a"],
            ["a" * 96],
        ],
        ids=["one byte", "96 bytes"],
    )
    def test_accepts_paths_within_100_bytes(self, path: str):
        """
        Verifies the function accepts paths up to 96 bytes (104 byte max - 8 byte padding
        for socket name portion (path sep + PID))
        """
        # GIVEN
        subject = MacOSSocketDirectories()

        try:
            # WHEN
            subject.verify_socket_path(path)
        except NonvalidSocketPathException as e:
            pytest.fail(f"verify_socket_path raised an error when it should not have: {e}")
        else:
            # THEN
            pass  # success

    def test_rejects_paths_over_96_bytes(self):
        # GIVEN
        length = 97
        path = "a" * length
        subject = MacOSSocketDirectories()

        # WHEN
        with pytest.raises(NonvalidSocketPathException) as raised_exc:
            subject.verify_socket_path(path)

        # THEN
        assert raised_exc.match(
            "Socket base directory path too big. The maximum allowed size is "
            f"{subject._socket_dir_max_length} bytes, but the directory has a size of "
            f"{length}: {path}"
        )
