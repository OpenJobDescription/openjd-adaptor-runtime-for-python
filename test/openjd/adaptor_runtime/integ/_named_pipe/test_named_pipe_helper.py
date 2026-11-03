# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import time

from openjd.adaptor_runtime._osname import OSName
import getpass
import json
import os
import pytest
import threading
import uuid
from typing import Any, List, Optional, Tuple

if OSName.is_windows():
    import ntsecuritycon
    import pywintypes
    import win32con
    import win32file
    import win32pipe
    import win32security
    import win32api
    import winerror
    from openjd.adaptor_runtime_client.named_pipe.named_pipe_helper import NamedPipeHelper
else:
    # Cannot put this on the top of this file or mypy will complain
    pytest.mark.skip(reason="NamedPipe is only implemented in Windows.")

PIPE_NAME = r"\\.\pipe\TestPipe"
TIMEOUT_SECONDS = 5

# getpass.getuser() returns the first of these that is set. No account has this name, so
# resolving it with LookupAccountName fails with ERROR_NONE_MAPPED (1332).
USER_NAME_ENV_VARS = ("LOGNAME", "USER", "LNAME", "USERNAME")
UNMAPPED_USER_NAME = "no-such-user-1332"
NETWORK_SID = "S-1-5-2"


def pipe_server(pipe_name, message_to_send, return_message):
    """
    A simple pipe server for testing.
    """
    server_handle = NamedPipeHelper.create_named_pipe_server(pipe_name, TIMEOUT_SECONDS)
    win32pipe.ConnectNamedPipe(server_handle, None)
    received_message = NamedPipeHelper.read_from_pipe(server_handle)
    received_obj = json.loads(received_message)
    assert received_obj["method"] == message_to_send["method"]
    assert received_obj["path"] == message_to_send["path"]
    assert json.loads(received_obj["body"]) == message_to_send["json_body"]
    NamedPipeHelper.write_to_pipe(server_handle, return_message)
    win32file.CloseHandle(server_handle)


@pytest.fixture
def start_pipe_server():
    """
    Fixture to start the pipe server in a separate thread.
    """
    message_to_send = dict(method="POST", path="/test", json_body={"message": "Hello from client"})
    return_message = '{"Response":"Hello from server"}'
    server_thread = threading.Thread(
        target=pipe_server, args=(PIPE_NAME, message_to_send, return_message)
    )
    server_thread.start()
    yield message_to_send, return_message
    server_thread.join()


def set_unmapped_user_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes getpass.getuser() return a name that LookupAccountName cannot resolve."""
    for name in USER_NAME_ENV_VARS:
        monkeypatch.setenv(name, UNMAPPED_USER_NAME)
    assert getpass.getuser() == UNMAPPED_USER_NAME
    # Precondition: if this name resolved, a name-based SID lookup would pass too and the
    # tests using it would pin nothing.
    with pytest.raises(pywintypes.error) as excinfo:
        win32security.LookupAccountName("", UNMAPPED_USER_NAME)
    assert excinfo.value.winerror == winerror.ERROR_NONE_MAPPED


def process_token_user_sid() -> str:
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        win32api.CloseHandle(token)
    return win32security.ConvertSidToStringSid(sid)


def as_file_rights(mask: int) -> int:
    """Maps generic rights to file rights, since Windows may store an ACE mask in either form."""
    mask &= 0xFFFFFFFF
    for generic, specific in (
        (win32con.GENERIC_READ & 0xFFFFFFFF, ntsecuritycon.FILE_GENERIC_READ),
        (win32con.GENERIC_WRITE, ntsecuritycon.FILE_GENERIC_WRITE),
        (win32con.GENERIC_ALL, ntsecuritycon.FILE_ALL_ACCESS),
    ):
        if mask & generic:
            mask = (mask & ~generic) | specific
    return mask


def read_pipe_dacl(pipe_handle: Any) -> List[Tuple[int, int, str]]:
    """Returns (ACE type, access mask as file rights, SID string) for each ACE on the pipe."""
    security_descriptor = win32security.GetSecurityInfo(
        pipe_handle, win32security.SE_KERNEL_OBJECT, win32security.DACL_SECURITY_INFORMATION
    )
    dacl = security_descriptor.GetSecurityDescriptorDacl()
    entries = []
    for index in range(dacl.GetAceCount()):
        (ace_type, _ace_flags), mask, sid = dacl.GetAce(index)
        entries.append((ace_type, as_file_rights(mask), win32security.ConvertSidToStringSid(sid)))
    return entries


def serve_one_request(
    server_handle: Any, response: str, received: List[str], errors: List[Exception]
) -> None:
    try:
        win32pipe.ConnectNamedPipe(server_handle, None)
        received.append(NamedPipeHelper.read_from_pipe(server_handle))
        NamedPipeHelper.write_to_pipe(server_handle, response)
    except Exception as e:
        errors.append(e)


@pytest.mark.skipif(not OSName.is_windows(), reason="NamedPipe is only implemented in Windows.")
class TestNamedPipeHelper:
    def test_named_pipe_communication(self, start_pipe_server):
        """
        A test for validating basic NamedPipe functions, Connect, Read, Write
        """
        # GIVEN
        message_to_send, expected_response = start_pipe_server

        # WHEN
        response = NamedPipeHelper.send_named_pipe_request(
            PIPE_NAME, TIMEOUT_SECONDS, **message_to_send
        )

        # THEN
        assert response == json.loads(expected_response)

    def test_check_named_pipe_exists(self):
        """
        Test if the script can check if a named pipe exists.
        """

        # GIVEN
        pipe_name = r"\\.\pipe\test_if_named_pipe_exist"
        assert not NamedPipeHelper.check_named_pipe_exists(pipe_name)
        server_handle = NamedPipeHelper.create_named_pipe_server(pipe_name, TIMEOUT_SECONDS)

        # WHEN
        is_existed = False
        # Need to wait for launching the NamedPipe Server
        for _ in range(10):
            if NamedPipeHelper.check_named_pipe_exists(pipe_name):
                is_existed = True
                break
            time.sleep(1)

        # THEN
        win32file.CloseHandle(server_handle)
        assert is_existed

    @pytest.mark.skipif(
        os.getenv("GITHUB_ACTIONS") != "true",
        reason="Skip this test in local env to avoid user creation with elevated privilege.",
    )
    def test_fail_to_connect_to_named_pipe_with_different_user(
        self, win_test_user, start_pipe_server
    ):
        """
        This test is used for validating the security descriptor is working.
        Only the user who start running the named pipe server can connect to it.
        Any other users will get the error `Access is denied`
        """
        # GIVEN
        user_name, password = win_test_user
        logon_type = win32security.LOGON32_LOGON_INTERACTIVE
        provider = win32security.LOGON32_PROVIDER_DEFAULT
        message_to_send, expected_response = start_pipe_server

        # WHEN
        # Log on with the user's credentials and get the token handle
        token_handle = win32security.LogonUser(user_name, "", password, logon_type, provider)
        # Impersonate the user
        win32security.ImpersonateLoggedOnUser(token_handle)

        # THEN
        with pytest.raises(pywintypes.error) as excinfo:
            NamedPipeHelper.send_named_pipe_request(PIPE_NAME, TIMEOUT_SECONDS, **message_to_send)
            assert "Access is denied" in str(excinfo.value)

        # Revert the impersonation
        win32security.RevertToSelf()

        # Close the token handle
        win32api.CloseHandle(token_handle)

        # Send a message to unblock the I/O
        NamedPipeHelper.send_named_pipe_request(PIPE_NAME, TIMEOUT_SECONDS, **message_to_send)

    @pytest.mark.parametrize(
        "unmapped_user_name_for",
        [
            pytest.param(None, id="ambient-user-name"),
            pytest.param("server-and-client", id="unmapped-user-name-for-server-and-client"),
            pytest.param("client", id="unmapped-user-name-for-client"),
        ],
    )
    def test_pipe_security_does_not_depend_on_user_name(
        self, monkeypatch: pytest.MonkeyPatch, unmapped_user_name_for: Optional[str]
    ) -> None:
        """
        The pipe's DACL comes from the process token, so a getpass.getuser() name that maps to
        no account (ERROR_NONE_MAPPED, 1332) breaks neither the server nor the client.
        The ambient-user-name case is the control: the normal environment must still work.
        """
        # GIVEN
        pipe_name = rf"\\.\pipe\openjd_token_sid_{os.getpid()}_{uuid.uuid4().hex}"
        request_body = {"message": "Hello from client"}
        server_response = '{"Response": "Hello from server"}'
        received: List[str] = []
        errors: List[Exception] = []
        if unmapped_user_name_for == "server-and-client":
            set_unmapped_user_name(monkeypatch)
        server_handle = NamedPipeHelper.create_named_pipe_server(pipe_name, TIMEOUT_SECONDS)
        assert server_handle is not None
        # A daemon thread, so a failed client cannot hang the run in ConnectNamedPipe.
        server_thread = threading.Thread(
            target=serve_one_request,
            args=(server_handle, server_response, received, errors),
            daemon=True,
        )

        try:
            if unmapped_user_name_for == "client":
                set_unmapped_user_name(monkeypatch)
            dacl = read_pipe_dacl(server_handle)
            server_thread.start()

            # WHEN
            response = NamedPipeHelper.send_named_pipe_request(
                pipe_name, TIMEOUT_SECONDS, "POST", "/token-sid", json_body=request_body
            )
            server_thread.join(TIMEOUT_SECONDS)
        finally:
            win32file.CloseHandle(server_handle)

        # THEN
        assert not server_thread.is_alive()
        assert errors == []
        assert [json.loads(message) for message in received] == [
            {"method": "POST", "path": "/token-sid", "body": json.dumps(request_body)}
        ]
        assert response == json.loads(server_response)
        # Canonical order: the NETWORK deny comes first, so it applies to the user's own network logons.
        assert dacl == [
            (
                win32security.ACCESS_DENIED_ACE_TYPE,
                as_file_rights(win32con.GENERIC_ALL),
                NETWORK_SID,
            ),
            (
                win32security.ACCESS_ALLOWED_ACE_TYPE,
                as_file_rights(win32con.GENERIC_READ | win32con.GENERIC_WRITE),
                process_token_user_sid(),
            ),
        ]
