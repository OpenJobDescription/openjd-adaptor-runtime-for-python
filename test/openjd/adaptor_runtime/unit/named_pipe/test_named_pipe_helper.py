# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from openjd.adaptor_runtime._osname import OSName
from typing import Any, List, Tuple
from unittest.mock import patch, MagicMock
import pytest
import os
import time

pywintypes = pytest.importorskip("pywintypes")
win32api = pytest.importorskip("win32api")
win32con = pytest.importorskip("win32con")
win32pipe = pytest.importorskip("win32pipe")
win32file = pytest.importorskip("win32file")
win32security = pytest.importorskip("win32security")
winerror = pytest.importorskip("winerror")
named_pipe_helper = pytest.importorskip(
    "openjd.adaptor_runtime_client.named_pipe.named_pipe_helper"
)

FAKE_USER_SID = "S-1-5-21-1-2-3-1001"


def dacl_entries(security_attributes: Any) -> List[Tuple[int, int, str]]:
    """Returns (ACE type, access mask, SID string) for each ACE in the attributes' DACL."""
    dacl = security_attributes.SECURITY_DESCRIPTOR.GetSecurityDescriptorDacl()
    entries = []
    for index in range(dacl.GetAceCount()):
        (ace_type, _ace_flags), mask, sid = dacl.GetAce(index)
        entries.append((ace_type, mask & 0xFFFFFFFF, win32security.ConvertSidToStringSid(sid)))
    return entries


class MockReadFile:
    @staticmethod
    def ReadFile(handle: pywintypes.HANDLE, timeout_in_seconds: float):  # type: ignore[name-defined]
        time.sleep(10)
        return winerror.NO_ERROR, bytes("fake_data", "utf-8")


@pytest.mark.skipif(not OSName.is_windows(), reason="Windows-specific tests")
class TestNamedPipeHelper:
    def test_named_pipe_read_timeout_exception(self):
        with pytest.raises(
            named_pipe_helper.NamedPipeReadTimeoutError,
            match="NamedPipe Server read timeout after 1.0 seconds.$",
        ):
            raise named_pipe_helper.NamedPipeReadTimeoutError(1.0)

    def test_named_pipe_connect_timeout_exception(self):
        exception_during_connect = Exception("Fake exception that occurred while connecting.")
        expected_error_message = os.linesep.join(
            [
                "NamedPipe Server connect timeout after 1.0 seconds.",
                f"Original error: {exception_during_connect}",
            ]
        )
        with pytest.raises(
            named_pipe_helper.NamedPipeConnectTimeoutError, match=expected_error_message
        ):
            raise named_pipe_helper.NamedPipeConnectTimeoutError(1.0, exception_during_connect)

    @patch.object(
        win32file, "CreateFile", side_effect=win32file.error(winerror.ERROR_FILE_NOT_FOUND)
    )
    def test_establish_named_pipe_connection_timeout_raises_exception(self, mock_win32file):
        with pytest.raises(
            named_pipe_helper.NamedPipeConnectTimeoutError,
            match=os.linesep.join(
                [
                    "NamedPipe Server connect timeout after \\d\\.\\d+ seconds.",
                    f"Original error: {win32file.error(winerror.ERROR_FILE_NOT_FOUND)}",
                ]
            ),
        ):
            named_pipe_helper.NamedPipeHelper.establish_named_pipe_connection("fakepipe", 1.0)

    @patch.object(win32file, "ReadFile", wraps=MockReadFile.ReadFile)
    def test_read_from_pipe_timeout_raises_exception(self, mock_win32file):
        mock_handle = MagicMock()
        with pytest.raises(
            named_pipe_helper.NamedPipeReadTimeoutError,
            match="NamedPipe Server read timeout after \\d\\.\\d+ seconds.$",
        ):
            named_pipe_helper.NamedPipeHelper.read_from_pipe(mock_handle, 1.0)

        mock_handle.close.assert_called_once()

    @patch("os.getpid", return_value=1)
    @patch(
        "openjd.adaptor_runtime_client.named_pipe.named_pipe_helper.NamedPipeHelper.check_named_pipe_exists",
        return_value=False,
    )
    def test_generate_pipe_name(self, mock_check_named_pipe_exists, mock_getpid):
        name = named_pipe_helper.NamedPipeHelper.generate_pipe_name("AdaptorTest")
        assert name == r"\\.\pipe\AdaptorTest_1"

    @patch("os.getpid", return_value=1)
    @patch(
        "openjd.adaptor_runtime_client.named_pipe.named_pipe_helper.NamedPipeHelper.check_named_pipe_exists",
        side_effect=[True, False],
    )
    def test_generate_pipe_name2(self, mock_check_named_pipe_exists, mock_getpid):
        # This test is to ensure that the pipe name will change when it already exists.
        name = named_pipe_helper.NamedPipeHelper.generate_pipe_name("AdaptorTest")
        assert r"\\.\pipe\AdaptorTest_1_0_" in name

    @patch("os.getpid", return_value=1)
    @patch(
        "openjd.adaptor_runtime_client.named_pipe.named_pipe_helper.NamedPipeHelper.check_named_pipe_exists",
        return_value=True,
    )
    def test_failed_to_generate_pipe_name(self, mock_check_named_pipe_exists, mock_getpid):
        with pytest.raises(
            named_pipe_helper.NamedPipeNamingError,
            match="Cannot find an available pipe name.",
        ):
            named_pipe_helper.NamedPipeHelper.generate_pipe_name("AdaptorTest")

    def test_create_security_attributes_uses_process_token_user(self) -> None:
        # GIVEN
        token = MagicMock()
        token_user = (win32security.ConvertStringSidToSid(FAKE_USER_SID), 0)
        with (
            patch.object(win32security, "OpenProcessToken", return_value=token) as mock_open_token,
            patch.object(
                win32security, "GetTokenInformation", return_value=token_user
            ) as mock_get_token_information,
            patch.object(win32api, "CloseHandle") as mock_close_handle,
        ):
            # WHEN
            security_attributes = named_pipe_helper.NamedPipeHelper.create_security_attributes()

        # THEN
        mock_open_token.assert_called_once_with(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        mock_get_token_information.assert_called_once_with(token, win32security.TokenUser)
        mock_close_handle.assert_called_once_with(token)
        # Canonical order: the NETWORK deny comes first, so it applies to the user's own network logons.
        assert dacl_entries(security_attributes) == [
            (win32security.ACCESS_DENIED_ACE_TYPE, win32con.GENERIC_ALL, "S-1-5-2"),
            (
                win32security.ACCESS_ALLOWED_ACE_TYPE,
                (win32con.GENERIC_READ | win32con.GENERIC_WRITE) & 0xFFFFFFFF,
                FAKE_USER_SID,
            ),
        ]

    def test_create_security_attributes_does_not_look_up_user_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN
        for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
            monkeypatch.setenv(name, "no-such-user-1332")
        none_mapped = pywintypes.error(
            winerror.ERROR_NONE_MAPPED,
            "LookupAccountName",
            "No mapping between account names and security IDs was done.",
        )
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            expected_sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        finally:
            win32api.CloseHandle(token)

        with patch.object(
            win32security, "LookupAccountName", side_effect=none_mapped
        ) as mock_lookup_account_name:
            # WHEN
            security_attributes = named_pipe_helper.NamedPipeHelper.create_security_attributes()

        # THEN
        mock_lookup_account_name.assert_not_called()
        allowed_sids = [
            sid
            for ace_type, _mask, sid in dacl_entries(security_attributes)
            if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE
        ]
        assert allowed_sids == [win32security.ConvertSidToStringSid(expected_sid)]

    def test_create_security_attributes_closes_token_when_query_fails(self) -> None:
        # GIVEN
        token = MagicMock()
        query_error = pywintypes.error(
            winerror.ERROR_ACCESS_DENIED, "GetTokenInformation", "Access is denied."
        )
        with (
            patch.object(win32security, "OpenProcessToken", return_value=token),
            patch.object(win32security, "GetTokenInformation", side_effect=query_error),
            patch.object(win32api, "CloseHandle") as mock_close_handle,
        ):
            # WHEN
            with pytest.raises(pywintypes.error) as exc_info:
                named_pipe_helper.NamedPipeHelper.create_security_attributes()

        # THEN
        assert exc_info.value is query_error
        mock_close_handle.assert_called_once_with(token)

    @patch.object(win32pipe, "SetNamedPipeHandleState")
    @patch.object(win32file, "CreateFile")
    @patch.object(named_pipe_helper.NamedPipeHelper, "create_security_attributes")
    def test_establish_named_pipe_connection_builds_no_dacl(
        self,
        mock_create_security_attributes: MagicMock,
        mock_create_file: MagicMock,
        mock_set_named_pipe_handle_state: MagicMock,
    ) -> None:
        # WHEN
        handle = named_pipe_helper.NamedPipeHelper.establish_named_pipe_connection("fakepipe", 1.0)

        # THEN
        assert handle is mock_create_file.return_value
        mock_create_security_attributes.assert_not_called()
        # Opening an existing pipe ignores the security descriptor; inheritability is unchanged.
        security_attributes = mock_create_file.call_args.args[3]
        assert security_attributes.SECURITY_DESCRIPTOR is None
        assert security_attributes.bInheritHandle == 1
        assert mock_create_file.call_args.args[4] == win32file.OPEN_EXISTING
