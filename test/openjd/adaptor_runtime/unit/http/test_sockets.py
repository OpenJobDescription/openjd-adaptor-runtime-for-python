# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import os
import pathlib
import re
import stat
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

import openjd.adaptor_runtime._http.sockets as sockets
from openjd.adaptor_runtime._http.sockets import (
    LinuxSocketPaths,
    MacOSSocketPaths,
    NonvalidSocketPathException,
    NoSocketPathFoundException,
    SocketPaths,
    UnixSocketPaths,
)


class SocketPathsStub(SocketPaths):
    def verify_socket_path(self, path: str) -> None:
        pass


class TestSocketPaths:
    class TestGetProcessSocketPath:
        """
        Tests for SocketPaths.get_process_socket_path()
        """

        @patch.object(sockets.os, "getpid", return_value=1234)
        def test_gets_path(
            self,
            mock_getpid: MagicMock,
        ) -> None:
            # GIVEN
            namespace = "my-namespace"
            subject = SocketPathsStub()

            # WHEN
            result = subject.get_process_socket_path(namespace)

            # THEN
            assert result.endswith(os.path.join(namespace, str(mock_getpid.return_value)))
            mock_getpid.assert_called_once()

        @patch.object(sockets.os, "getpid", return_value="a" * (sockets._PID_MAX_LENGTH + 1))
        def test_asserts_max_pid_length(self, mock_getpid: MagicMock):
            # GIVEN
            subject = SocketPathsStub()

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
        Tests for SocketPaths.get_socket_path()
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

        @patch.object(sockets.tempfile, "gettempdir", wraps=sockets.tempfile.gettempdir)
        @patch.object(sockets.os, "stat")
        def test_gets_temp_dir(
            self,
            mock_stat: MagicMock,
            mock_gettempdir: MagicMock,
        ) -> None:
            # GIVEN
            mock_stat.return_value.st_mode = stat.S_ISVTX
            subject = UnixSocketPaths()

            # WHEN
            subject.get_socket_path("sock")

            # THEN
            mock_gettempdir.assert_called_once()
            mock_stat.assert_called()

        @pytest.mark.parametrize(
            argnames=["create"],
            argvalues=[[True], [False]],
            ids=["created", "not created"],
        )
        def test_create_dir(self, mock_makedirs: MagicMock, create: bool) -> None:
            # GIVEN
            subject = SocketPathsStub()

            # WHEN
            result = subject.get_socket_path("sock", create_dir=create)

            # THEN
            if create:
                mock_makedirs.assert_called_once_with(
                    os.path.dirname(result), mode=0o700, exist_ok=True
                )
            else:
                mock_makedirs.assert_not_called()

        def test_uses_base_dir(self, tmp_path: pathlib.Path) -> None:
            # GIVEN
            subject = SocketPathsStub()
            base_dir = str(tmp_path)

            # WHEN
            result = subject.get_socket_path("sock", base_dir=base_dir)

            # THEN
            assert result.startswith(base_dir)

        def test_uses_namespace(self) -> None:
            # GIVEN
            namespace = "my-namespace"
            subject = SocketPathsStub()

            # WHEN
            result = subject.get_socket_path("sock", namespace)

            # THEN
            assert os.path.dirname(result).endswith(namespace)

        @patch.object(SocketPathsStub, "verify_socket_path")
        def test_raises_when_no_valid_path_found(self, mock_verify_socket_path: MagicMock) -> None:
            # GIVEN
            mock_verify_socket_path.side_effect = NonvalidSocketPathException()
            subject = SocketPathsStub()

            # WHEN
            with pytest.raises(NoSocketPathFoundException) as raised_exc:
                subject.get_socket_path("sock")

            # THEN
            assert raised_exc.match("^Socket path '.*' failed verification: .*")
            assert mock_verify_socket_path.call_count == 1

        @patch.object(sockets.os.path, "exists")
        def test_handles_socket_name_collisions(
            self,
            mock_exists: MagicMock,
        ) -> None:
            # GIVEN
            sock_name = "sock"
            existing_sock_names = [sock_name, f"{sock_name}_1", f"{sock_name}_2"]
            mock_exists.side_effect = ([True] * len(existing_sock_names)) + [False]
            expected_sock_name = f"{sock_name}_3"

            subject = SocketPathsStub()

            # WHEN
            result = subject.get_socket_path(sock_name)

            # THEN
            assert result.endswith(expected_sock_name)
            assert mock_exists.call_count == (len(existing_sock_names) + 1)


class TestUnixSocketPaths:
    @pytest.fixture(autouse=True)
    def mock_stat(self) -> Generator[MagicMock, None, None]:
        with patch.object(sockets.os, "stat") as m:
            yield m

    @pytest.mark.parametrize(
        argnames=["mode", "should_fail"],
        argvalues=[
            [stat.S_IWOTH & stat.S_ISVTX, False],
            [stat.S_IWOTH, True],
            [stat.S_IROTH, False],
        ],
        ids=[
            "world-writable, sticky, passes",
            "world-writable, not sticky, fails",
            "world-readable, not sticky, passes",
        ],
    )
    def test_verifies_all_parent_directories(
        self,
        mode: int,
        should_fail: bool,
        mock_stat: MagicMock,
    ) -> None:
        pass

    @patch.object(sockets.os, "stat")
    def test_raises_when_no_tmpdir_sticky_bit(
        self,
        mock_stat: MagicMock,
    ) -> None:
        # GIVEN
        mock_stat.return_value.st_mode = stat.S_IWOTH
        socket_name = "/sock"
        subject = UnixSocketPaths()

        # WHEN
        with pytest.raises(NoSocketPathFoundException) as raised_exc:
            subject.verify_socket_path(socket_name)

        # THEN
        assert raised_exc.match(
            re.escape(
                f"Cannot use directory {os.path.dirname(socket_name)} because it is world writable"
                " and does not have the sticky bit (restricted deletion flag) set"
            )
        )

    class TestLinuxSocketPaths:
        @pytest.mark.parametrize(
            argnames=["path"],
            argvalues=[
                ["a"],
                ["a" * 107],
            ],
            ids=["one byte", "107 bytes"],
        )
        def test_accepts_names_within_107_bytes(self, path: str):
            """
            Verifies the function accepts paths up to 100 bytes (108 byte max - 1 byte null terminator)
            """
            # GIVEN
            subject = LinuxSocketPaths()

            try:
                # WHEN
                subject.verify_socket_path(path)
            except NonvalidSocketPathException as e:
                pytest.fail(f"verify_socket_path raised an error when it should not have: {e}")
            else:
                # THEN
                pass  # success

        def test_rejects_names_over_107_bytes(self):
            # GIVEN
            length = 108
            path = "a" * length
            subject = LinuxSocketPaths()

            # WHEN
            with pytest.raises(NonvalidSocketPathException) as raised_exc:
                subject.verify_socket_path(path)

            # THEN
            assert raised_exc.match(
                "Socket name too long. The maximum allowed size is "
                f"{subject._socket_name_max_length} bytes, but the name has a size of "
                f"{length}: {path}"
            )

    class TestMacOSSocketPaths:
        @pytest.mark.parametrize(
            argnames=["path"],
            argvalues=[
                ["a"],
                ["a" * 103],
            ],
            ids=["one byte", "103 bytes"],
        )
        def test_accepts_paths_within_103_bytes(self, path: str):
            """
            Verifies the function accepts paths up to 103 bytes (104 byte max - 1 byte null terminator)
            """
            # GIVEN
            subject = MacOSSocketPaths()

            try:
                # WHEN
                subject.verify_socket_path(path)
            except NonvalidSocketPathException as e:
                pytest.fail(f"verify_socket_path raised an error when it should not have: {e}")
            else:
                # THEN
                pass  # success

        def test_rejects_paths_over_103_bytes(self):
            # GIVEN
            length = 104
            path = "a" * length
            subject = MacOSSocketPaths()

            # WHEN
            with pytest.raises(NonvalidSocketPathException) as raised_exc:
                subject.verify_socket_path(path)

            # THEN
            assert raised_exc.match(
                "Socket name too long. The maximum allowed size is "
                f"{subject._socket_name_max_length} bytes, but the name has a size of "
                f"{length}: {path}"
            )
